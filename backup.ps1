# Kopia zapasowa bazy sesji.
#
#   .\backup.ps1                  - robi kopie do katalogu backups\
#   .\backup.ps1 -List            - pokazuje, co juz jest
#   .\backup.ps1 -Restore <plik>  - przywraca wskazana kopie
#
# Dlaczego skrypt, a nie zwykle skopiowanie pliku: baza chodzi w trybie WAL,
# wiec czesc zapisow siedzi w spotkania.db-wal, a nie w samym spotkania.db.
# Skopiowany "na piechote" plik potrafi byc starszy, niz sie wydaje, albo
# wrecz uszkodzony, jesli trafi w srodek zapisu.
#
# Zamiast tego prosimy SQLite o spojna kopie (VACUUM INTO). Dziala przy
# uruchomionej aplikacji i daje jeden plik bez ogona WAL.

param(
    [switch]$List,
    [string]$Restore,
    # Pomija pytanie o potwierdzenie przy przywracaniu.
    [switch]$Yes,
    # Ile kopii zostawiamy. 0 = nie kasuj nic.
    [int]$Keep = 20
)

$ErrorActionPreference = "Continue"

$katalog = Join-Path $PSScriptRoot "backups"
$baza = Join-Path $PSScriptRoot "data\spotkania.db"


function Invoke-WAplikacji($polecenie) {
    <#
        Uruchamia polecenie Pythona w aplikacji. Jesli kontener chodzi,
        korzystamy z niego (szybciej i widzi ten sam stan bazy); jesli nie,
        podnosimy jednorazowy.
    #>
    $biegnie = (docker compose ps --status running --services 2>$null) -contains "app"
    if ($biegnie) {
        return ($polecenie | docker compose exec -T app python -)
    }
    return ($polecenie | docker compose run --rm --no-deps -T app python -)
}


function Show-Backups {
    if (-not (Test-Path $katalog)) {
        Write-Host "Nie ma jeszcze zadnych kopii."
        return @()
    }
    $pliki = Get-ChildItem $katalog -Filter "*.db" | Sort-Object LastWriteTime -Descending
    if ($pliki.Count -eq 0) {
        Write-Host "Nie ma jeszcze zadnych kopii."
        return @()
    }
    Write-Host ""
    Write-Host "Kopie w $katalog :" -ForegroundColor Cyan
    foreach ($p in $pliki) {
        $kb = [math]::Round($p.Length / 1KB)
        Write-Host ("  {0,-34} {1,6} KB   {2}" -f $p.Name, $kb, $p.LastWriteTime)
    }
    Write-Host ""
    return $pliki
}


# ── lista ───────────────────────────────────────────────────────────────────

if ($List) {
    Show-Backups | Out-Null
    exit 0
}


# ── przywracanie ────────────────────────────────────────────────────────────

if ($Restore) {
    $zrodlo = $Restore
    if (-not (Test-Path $zrodlo)) { $zrodlo = Join-Path $katalog $Restore }
    if (-not (Test-Path $zrodlo)) {
        Write-Host "Nie znalazlem kopii: $Restore" -ForegroundColor Red
        Show-Backups | Out-Null
        exit 1
    }

    Write-Host ""
    Write-Host "Przywrocenie nadpisze biezaca baze danymi z:" -ForegroundColor Yellow
    Write-Host "  $zrodlo"
    Write-Host "Wszystkie sesje i konta zapisane po tej kopii przepadna."
    if (-not $Yes) {
        $odp = Read-Host "Wpisz 'tak', zeby kontynuowac"
        if ($odp -ne "tak") {
            Write-Host "Anulowane."
            exit 0
        }
    }

    # Aplikacja musi stac: podmiana pliku pod otwartym polaczeniem SQLite
    # to prosta droga do uszkodzonej bazy.
    Write-Host "Zatrzymuje aplikacje..."
    docker compose down | Out-Null

    if (Test-Path $baza) {
        # Zanim nadpiszemy, odkladamy to, co jest teraz. Jesli przywracana
        # kopia okaze sie nie ta, bedzie do czego wrocic.
        $przed = Join-Path $katalog ("przed-przywroceniem-{0}.db" -f (Get-Date -Format "yyyy-MM-dd-HHmm"))
        New-Item -ItemType Directory -Force -Path $katalog | Out-Null
        Copy-Item $baza $przed -Force
        Write-Host "Stan sprzed przywrocenia zachowany: $(Split-Path $przed -Leaf)" -ForegroundColor Cyan
    }

    # Pliki WAL i SHM musza zniknac — inaczej SQLite doklei je do nowej bazy.
    Remove-Item "$baza-wal", "$baza-shm" -ErrorAction SilentlyContinue
    Copy-Item $zrodlo $baza -Force

    Write-Host ""
    Write-Host "Przywrocone. Uruchom aplikacje:  .\start.ps1" -ForegroundColor Green
    exit 0
}


# ── kopia ───────────────────────────────────────────────────────────────────

if (-not (Test-Path $baza)) {
    Write-Host "Nie ma jeszcze bazy ($baza) — nie ma czego kopiowac." -ForegroundColor Yellow
    exit 0
}

New-Item -ItemType Directory -Force -Path $katalog | Out-Null
$nazwa = "spotkania-{0}.db" -f (Get-Date -Format "yyyy-MM-dd-HHmm")
$cel = Join-Path $katalog $nazwa

# VACUUM INTO robi spojna kopie przy dzialajacej aplikacji i od razu
# scala WAL, wiec na wyjsciu jest jeden samodzielny plik.
$skrypt = @'
import os
import sqlite3
import sys

zrodlo = os.environ.get("DB_PATH", "/data/spotkania.db")
cel = "/data/__kopia_tymczasowa.db"
if os.path.exists(cel):
    os.remove(cel)
try:
    polaczenie = sqlite3.connect(zrodlo)
    polaczenie.execute("VACUUM INTO ?", (cel,))
    polaczenie.close()
    sesje = sqlite3.connect(cel).execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    konta = sqlite3.connect(cel).execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]
    print(f"OK {sesje} {konta}")
except Exception as blad:
    print(f"BLAD {blad}", file=sys.stderr)
    sys.exit(1)
'@

Write-Host "Robie kopie..." -ForegroundColor Cyan
$wynik = Invoke-WAplikacji $skrypt
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nie udalo sie zrobic kopii. Czy Docker dziala?" -ForegroundColor Red
    Write-Host $wynik
    exit 1
}

$tymczasowa = Join-Path $PSScriptRoot "data\__kopia_tymczasowa.db"
if (-not (Test-Path $tymczasowa)) {
    Write-Host "Aplikacja nie zapisala kopii." -ForegroundColor Red
    exit 1
}
Move-Item $tymczasowa $cel -Force

$podsumowanie = ($wynik | Select-String "^OK ").ToString() -split " "
$kb = [math]::Round((Get-Item $cel).Length / 1KB)

Write-Host ""
Write-Host "Kopia gotowa:" -ForegroundColor Green
Write-Host "  $cel"
Write-Host "  $kb KB · $($podsumowanie[1]) sesji · $($podsumowanie[2]) kont"

# Starsze kopie kasujemy dopiero po udanym zapisie nowej.
if ($Keep -gt 0) {
    $stare = Get-ChildItem $katalog -Filter "spotkania-*.db" |
             Sort-Object LastWriteTime -Descending |
             Select-Object -Skip $Keep
    foreach ($p in $stare) {
        Remove-Item $p.FullName -Force
        Write-Host "  usunieto stara kopie: $($p.Name)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Przywrocenie:  .\backup.ps1 -Restore $nazwa"
