# Uruchomienie aplikacji z automatycznie ustalonym adresem laptopa.
#
#   .\start.ps1              - tryb lokalny (jedno Wi-Fi)
#   .\start.ps1 -Remote      - dodatkowo tunel Cloudflare
#   .\start.ps1 -Rebuild     - przebudowa obrazu przed startem
#
# Po co osobny skrypt: adresu laptopa w sieci NIE da się wykryć z wnętrza
# kontenera. Docker pokazuje tam wyłącznie adresy swojej wewnętrznej sieci
# (172.x), a to nie jest adres, pod który mają wejść telefony. Ten skrypt
# działa po stronie Windowsa, więc widzi prawdziwy adres karty Wi-Fi —
# i podaje go aplikacji przy każdym starcie.
#
# Dzięki temu przeniesienie laptopa do innej sieci nie wymaga edycji żadnego
# pliku. Wystarczy uruchomić apkę ponownie.

param(
    [switch]$Remote,
    [switch]$Rebuild,
    # Pozwala wystartowac tunel mimo slabego hasla. Swiadoma decyzja, nie pomylka.
    [switch]$Force,
    # Sprawdza haslo wedlug polityki i konczy dzialanie -- bez uruchamiania
    # czegokolwiek. Przydatne, zanim wpiszesz haslo do .env albo zalozysz konto.
    [string]$CheckPassword,
    # Wypisuje mocne haslo spelniajace polityke i konczy dzialanie.
    [switch]$NewPassword
)

#: Ponizej tej dlugosci haslo nie ma sensu przy publicznym adresie.
$MinRemotePasswordLength = 12

# Celowo NIE ustawiamy tu "Stop". Docker pisze zwykle komunikaty postepu na
# stderr, a przy przekierowanym strumieniu PowerShell zamienilby je w blad
# krytyczny i przerwal skrypt w polowie budowania. Powodzenie sprawdzamy
# po kodzie wyjscia, nie po tym, czy cos trafilo na stderr.
$ErrorActionPreference = "Continue"
$port = 8000

function Get-LanAddress {
    # Bierzemy adres z interfejsu, którym system faktycznie wychodzi na świat.
    # Odsiewamy wirtualne karty Dockera i WSL-a (172.x, 169.254.x) — wpisanie
    # ich w telefonie nic nie da.
    $candidates = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -notlike '127.*' -and
            $_.IPAddress -notlike '169.254.*' -and
            $_.InterfaceAlias -notlike '*WSL*' -and
            $_.InterfaceAlias -notlike '*Docker*' -and
            $_.InterfaceAlias -notlike '*Hyper-V*'
        }

    # Wi-Fi ma pierwszeństwo, bo telefony są w tej samej sieci bezprzewodowej.
    $wifi = $candidates | Where-Object { $_.InterfaceAlias -like '*Wi-Fi*' } | Select-Object -First 1
    if ($wifi) { return $wifi.IPAddress }

    $ethernet = $candidates | Where-Object { $_.InterfaceAlias -like '*Ethernet*' } | Select-Object -First 1
    if ($ethernet) { return $ethernet.IPAddress }

    $any = $candidates | Select-Object -First 1
    if ($any) { return $any.IPAddress }
    return $null
}

function Get-EnvValue($name) {
    $path = Join-Path $PSScriptRoot ".env"
    if (-not (Test-Path $path)) { return $null }
    foreach ($line in Get-Content $path) {
        if ($line -match "^\s*$name\s*=\s*(.*)$") { return $matches[1].Trim() }
    }
    return $null
}

function New-StrongPassword {
    # Po jednym znaku z kazdej wymaganej klasy, reszta losowo -- haslo musi
    # spelniac te sama polityke, co kazde inne w aplikacji.
    $male = 'abcdefghijkmnpqrstuvwxyz'
    $duze = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    $cyfry = '23456789'
    $znaki = '!@#$%^&*-_=+?'
    $wszystko = $male + $duze + $cyfry + $znaki

    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    function Losuj($pula, $ile) {
        $bytes = New-Object byte[] $ile
        $rng.GetBytes($bytes)
        return (0..($ile - 1) | ForEach-Object { $pula[$bytes[$_] % $pula.Length] })
    }

    $znakiHasla = @(Losuj $male 1) + @(Losuj $duze 1) + @(Losuj $cyfry 1) +
                  @(Losuj $znaki 1) + @(Losuj $wszystko 16)
    # Tasowanie, zeby klasy nie stały zawsze w tej samej kolejnosci.
    return -join ($znakiHasla | Sort-Object { Get-Random })
}

function Test-PasswordPolicy($haslo) {
    if ([string]::IsNullOrEmpty($haslo)) { return @("co najmniej 8 znakow") }
    $braki = @()
    if ($haslo.Length -lt 8) { $braki += "co najmniej 8 znakow" }
    if ($haslo -cnotmatch '[A-Z]') { $braki += "wielka litera" }
    if ($haslo -cnotmatch '[a-z]') { $braki += "mala litera" }
    if ($haslo -notmatch '[0-9]') { $braki += "cyfra" }
    if ($haslo -notmatch '[^a-zA-Z0-9\s]') { $braki += "znak specjalny" }
    return $braki
}

# Wygenerowanie hasla: .\start.ps1 -NewPassword
# Write-Output, nie Write-Host -- ma dac sie przekazac dalej potokiem.
if ($NewPassword) {
    Write-Output (New-StrongPassword)
    exit 0
}

# Sprawdzenie pojedynczego hasla: .\start.ps1 -CheckPassword "Moje-Haslo1!"
if ($PSBoundParameters.ContainsKey("CheckPassword")) {
    $braki = Test-PasswordPolicy $CheckPassword
    if ($braki.Count -eq 0) {
        Write-Host "Haslo spelnia wymagania." -ForegroundColor Green
        exit 0
    }
    Write-Host "Haslu brakuje: $($braki -join ', ')" -ForegroundColor Red
    Write-Host "Propozycja: $(New-StrongPassword)" -ForegroundColor Cyan
    exit 1
}

function Get-AccountsState {
    <#
        Dwa pytania do aplikacji naraz:

        1. Czy sa juz jakies konta? To decyduje, czy ADMIN_PASSWORD z .env
           ma jeszcze znaczenie -- sluzy wylacznie do zalozenia konta
           startowego przy pustej bazie.

        2. Czy ktorekolwiek konto nadal otwiera sie haslem z .env? Samo
           istnienie kont nie wystarcza: zaraz po pierwszym uruchomieniu
           konto startowe ma dokladnie to haslo, ktore stoi w .env -- a przy
           instalacji "z pudelka" jest to haslo z .env.example, czyli jawne.

        Gdyby pytanie sie nie udalo (brak obrazu, zatrzymany Docker),
        zakladamy najostrozniejszy wariant: brak kont, czyli pelne sprawdzenie.
    #>
    # Kod lezie przez standardowe wejscie (python -), a NIE przez python -c.
    # PowerShell kaleczy cudzyslowy w argumentach polecen natywnych: kod
    # podany po -c dociera z rozwalonymi stringami i wywala sie na skladni,
    # a wtedy ten strażnik po cichu uznaje, ze kont nie ma.
    $skrypt = @'
import os
try:
    from app.accounts import all_users
    from app.db import SessionLocal
    from app.security import verify_password

    haslo = os.environ.get("ADMIN_PASSWORD", "")
    with SessionLocal() as db:
        konta = all_users(db)
        domyslne = any(
            k.is_active and haslo and verify_password(haslo, k.password_hash)
            for k in konta
        )
    print(f"WYNIK {len(konta)} {int(domyslne)}")
except Exception:
    print("WYNIK 0 0")
'@
    $wynik = $skrypt | docker compose run --rm --no-deps -T app python - 2>$null

    # Szukamy swojej linii po znaczniku: Docker miesza do wyjscia komunikaty
    # o tworzeniu kontenera, wiec "ostatnia linia" bywa czyms innym.
    $linia = $wynik | Where-Object { $_ -match '^WYNIK \d+ \d+$' } | Select-Object -Last 1
    if (-not $linia) {
        return [pscustomobject]@{ Count = 0; EnvPasswordWorks = $false }
    }
    $czesci = $linia -split '\s+'
    return [pscustomobject]@{
        Count            = [int]$czesci[1]
        EnvPasswordWorks = ($czesci[2] -eq "1")
    }
}

# Slabe haslo w sieci domowej nikomu nie szkodzi -- tam chroni sama siec.
# Publiczny adres tunelu zdejmuje te ochrone, wiec sprawdzamy haslo dokladnie
# w momencie, w ktorym zaczyna miec znaczenie.
if ($Remote -and -not $Force) {
    Write-Host "Sprawdzam konta administratorow..." -ForegroundColor Cyan
    $stan = Get-AccountsState

    if ($stan.EnvPasswordWorks) {
        # Konto istnieje, ale wciaz otwiera sie haslem z .env -- czyli nikt
        # go nie zmienil po instalacji. Przy instalacji z .env.example to
        # haslo jest jawne, wiec publikowanie w tym stanie nie ma sensu.
        Write-Host ""
        Write-Host "==============================================================" -ForegroundColor Red
        Write-Host "  Konto startowe ma wciaz haslo z .env" -ForegroundColor Red
        Write-Host "==============================================================" -ForegroundColor Red
        Write-Host "  Przynajmniej jedno konto otwiera sie haslem, ktore stoi"
        Write-Host "  w pliku .env. Jesli pochodzi ono z .env.example, zna je"
        Write-Host "  kazdy, kto widzial to repozytorium."
        Write-Host ""
        Write-Host "  Zmien haslo w panelu przed wystawieniem:" -ForegroundColor Cyan
        Write-Host "    1. uruchom lokalnie:  .\start.ps1"
        Write-Host "    2. wejdz na /archive -> zakladka Konta -> Zmien haslo"
        Write-Host "    3. wroc tutaj:        .\start.ps1 -Remote"
        Write-Host ""
        Write-Host "  Propozycja hasla: $(New-StrongPassword)" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Swiadomie mimo wszystko:  .\start.ps1 -Remote -Force"
        Write-Host "==============================================================" -ForegroundColor Red
        Write-Host ""
        exit 1
    }

    if ($stan.Count -gt 0) {
        Write-Host ""
        Write-Host "  Konta administratorow sa w bazie, zadne nie uzywa hasla" -ForegroundColor Cyan
        Write-Host "  z .env. Aplikacji broni haslo konta, nie ten plik."
    } else {
        $haslo = Get-EnvValue "ADMIN_PASSWORD"
        $braki = Test-PasswordPolicy $haslo
        $zaKrotkie = (-not [string]::IsNullOrEmpty($haslo)) -and
                     ($haslo.Length -lt $MinRemotePasswordLength)

        if ($braki.Count -gt 0 -or $zaKrotkie) {
            Write-Host ""
            Write-Host "==============================================================" -ForegroundColor Red
            Write-Host "  Nie wystawiam aplikacji z takim haslem" -ForegroundColor Red
            Write-Host "==============================================================" -ForegroundColor Red
            Write-Host "  Baza nie ma jeszcze zadnego konta, wiec ADMIN_PASSWORD"
            Write-Host "  z .env zalozy konto startowe superadmina."
            Write-Host ""
            if ($braki.Count -gt 0) {
                Write-Host "  Brakuje: $($braki -join ', ')" -ForegroundColor Yellow
            }
            if ($zaKrotkie) {
                Write-Host "  Dla trybu zdalnego minimum to $MinRemotePasswordLength znakow (jest $($haslo.Length))." -ForegroundColor Yellow
            }
            Write-Host ""
            Write-Host "  Tunel daje adres publiczny. To haslo jest wtedy jedyna"
            Write-Host "  rzecza miedzy internetem a prawem do zakladania sesji"
            Write-Host "  i korygowania cudzych odpowiedzi."
            Write-Host ""
            Write-Host "  Wpisz do .env na przyklad:" -ForegroundColor Cyan
            Write-Host "    ADMIN_PASSWORD=$(New-StrongPassword)" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "  Tryb lokalny dziala bez zmian:  .\start.ps1"
            Write-Host "  Swiadomie mimo wszystko:        .\start.ps1 -Remote -Force"
            Write-Host "==============================================================" -ForegroundColor Red
            Write-Host ""
            exit 1
        }
    }
}

$ip = Get-LanAddress

if ($Remote) {
    # W trybie zdalnym PUBLIC_URL zostaje PUSTE i to jest celowe.
    #
    # Aplikacja jest wtedy osiagalna pod dwoma adresami naraz: lokalnym
    # i tunelowym. Wpisanie tu ktoregokolwiek z nich sprawiloby, ze wygrywa
    # zawsze ten jeden -- i kod QR wysylalby wszystkich pod adres LAN, ktorego
    # osoby spoza sieci nie otworza. Puste pole oznacza "bierz adres z tego,
    # jak host sam wszedl", wiec kazdy dostaje adres, ktory u niego dziala.
    $env:PUBLIC_URL = ""
} elseif (-not $ip) {
    Write-Host "Nie znalazlem adresu w sieci lokalnej." -ForegroundColor Yellow
    Write-Host "Aplikacja wstanie, ale kod QR bedzie wskazywal adres, z ktorego wejdziesz w przegladarce."
    $env:PUBLIC_URL = ""
} else {
    $env:PUBLIC_URL = "http://${ip}:${port}"
}

$profile_ = Get-NetConnectionProfile | Select-Object -First 1

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  Spotkaniooapka" -ForegroundColor Cyan
Write-Host "==============================================================" -ForegroundColor Cyan
if ($ip) {
    Write-Host "  siec:        $($profile_.Name) [$($profile_.NetworkCategory)]"
    Write-Host "  dla telefonow:  http://${ip}:${port}" -ForegroundColor Green
    Write-Host "  ekran hosta:    http://${ip}:${port}/host" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Otworz ekran hosta pod adresem IP, nie przez localhost --"
    Write-Host "  wtedy kod QR na pewno bedzie wskazywal wlasciwy adres."
}
if ($profile_.NetworkCategory -ne "Private") {
    Write-Host ""
    Write-Host "  UWAGA: ta siec nie jest oznaczona jako prywatna." -ForegroundColor Yellow
    Write-Host "  Firewall Windows moze odrzucac polaczenia z telefonow." -ForegroundColor Yellow
}
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

$args_ = @("compose")
if ($Remote) { $args_ += @("--profile", "remote") }
$args_ += @("up", "-d")
if ($Rebuild) { $args_ += "--build" }

& docker @args_
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($Remote) {
    Write-Host ""
    Write-Host "Czekam na adres tunelu..." -ForegroundColor Cyan

    $deadline = (Get-Date).AddSeconds(90)
    $url = $null
    while ((Get-Date) -lt $deadline -and -not $url) {
        $logs = (docker compose logs tunnel) -join "`n"
        $match = [regex]::Match($logs, 'https://[a-z0-9-]+\.trycloudflare\.com')
        if ($match.Success) { $url = $match.Value }
        if (-not $url) { Start-Sleep -Seconds 3 }
    }

    Write-Host ""
    if ($url) {
        Write-Host "==============================================================" -ForegroundColor Green
        Write-Host "  TRYB ZDALNY - dziala z dowolnej sieci" -ForegroundColor Green
        Write-Host "==============================================================" -ForegroundColor Green
        Write-Host "  ekran hosta:   $url/host" -ForegroundColor Green
        Write-Host "  dla telefonow: $url" -ForegroundColor Green
        Write-Host "  podglad:       $url/spectator" -ForegroundColor Green
        Write-Host ""
        Write-Host "  Otworz ekran hosta WLASNIE POD TYM ADRESEM -- wtedy kod QR"
        Write-Host "  bedzie wskazywal tunel, a nie siec lokalna."
        Write-Host ""
        Write-Host "  Ten adres jest publiczny. Znika po zatrzymaniu tunelu" -ForegroundColor Yellow
        Write-Host "  i przy kazdym starcie jest inny." -ForegroundColor Yellow
        Write-Host "==============================================================" -ForegroundColor Green
    } else {
        Write-Host "Nie doczekalem sie adresu tunelu. Sprawdz:" -ForegroundColor Yellow
        Write-Host "  docker compose logs tunnel"
    }
}

Write-Host ""
Write-Host "Logi:  docker compose logs -f app"
Write-Host "Stop:  docker compose down"
