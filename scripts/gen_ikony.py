"""Generuje ikony PWA bez zadnych zaleznosci — czysty zlib + struct.

Ikona jest pelnoplaszczyznowa (bez przezroczystych rogow), bo tak dziala
'maskable': system sam przycina ja do swojego ksztaltu. Rysunek trzyma sie
srodkowych ~60% plotna, czyli w strefie bezpiecznej.
"""

import struct
import zlib
from pathlib import Path

# Ścieżka liczona względem tego pliku, żeby skrypt działał niezależnie
# od katalogu, z którego go uruchomisz.
WYJSCIE = Path(__file__).resolve().parent.parent / "frontend" / "public"

TLO = (15, 23, 42)        # #0f172a — to samo co theme-color
PAPIER = (241, 245, 249)  # jasna kartka kalendarza
AKCENT = (56, 189, 248)   # #38bdf8 — pasek naglowka
KROPKA = (15, 23, 42)


def zapisz_png(sciezka: Path, piksele: list[list[tuple[int, int, int]]]) -> None:
    wysokosc = len(piksele)
    szerokosc = len(piksele[0])

    surowe = bytearray()
    for wiersz in piksele:
        surowe.append(0)  # filtr: brak
        for r, g, b in wiersz:
            surowe += bytes((r, g, b))

    def kawalek(typ: bytes, dane: bytes) -> bytes:
        return (
            struct.pack(">I", len(dane))
            + typ
            + dane
            + struct.pack(">I", zlib.crc32(typ + dane) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", szerokosc, wysokosc, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + kawalek(b"IHDR", ihdr)
        + kawalek(b"IDAT", zlib.compress(bytes(surowe), 9))
        + kawalek(b"IEND", b"")
    )
    sciezka.write_bytes(png)


def narysuj(rozmiar: int) -> list[list[tuple[int, int, int]]]:
    s = rozmiar
    plotno = [[TLO for _ in range(s)] for _ in range(s)]

    def prostokat(x0, y0, x1, y1, kolor, promien=0):
        for y in range(max(0, int(y0)), min(s, int(y1))):
            for x in range(max(0, int(x0)), min(s, int(x1))):
                if promien:
                    # Zaokraglamy rogi, sprawdzajac odleglosc od srodka luku.
                    cx = min(max(x, x0 + promien), x1 - promien)
                    cy = min(max(y, y0 + promien), y1 - promien)
                    if (x - cx) ** 2 + (y - cy) ** 2 > promien**2:
                        continue
                plotno[y][x] = kolor

    def kolo(cx, cy, r, kolor):
        for y in range(max(0, int(cy - r)), min(s, int(cy + r + 1))):
            for x in range(max(0, int(cx - r)), min(s, int(cx + r + 1))):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    plotno[y][x] = kolor

    j = s / 512  # wszystkie wymiary liczone dla 512 i skalowane

    # Kolka spinajace kartki, nad kalendarzem.
    kolo(188 * j, 140 * j, 22 * j, PAPIER)
    kolo(324 * j, 140 * j, 22 * j, PAPIER)

    # Karta kalendarza.
    prostokat(120 * j, 150 * j, 392 * j, 400 * j, PAPIER, promien=28 * j)
    # Pasek naglowka.
    prostokat(120 * j, 150 * j, 392 * j, 212 * j, AKCENT, promien=28 * j)
    prostokat(120 * j, 190 * j, 392 * j, 212 * j, AKCENT)

    # Siatka dni: 3 kolumny, 2 rzedy.
    for rzad in range(2):
        for kol in range(3):
            kolo(
                (172 + kol * 84) * j,
                (268 + rzad * 76) * j,
                17 * j,
                KROPKA,
            )

    return plotno


def wygladz(rozmiar: int, krotnosc: int = 4) -> list[list[tuple[int, int, int]]]:
    """Rysuje w powiekszeniu i usrednia — bez tego luki sa postrzepione.

    Taniej niz pisanie antyaliasingu dla kazdego ksztaltu z osobna, a wynik
    przy ikonie jest nie do odroznienia.
    """
    dokladne = narysuj(rozmiar * krotnosc)
    wynik = []
    for y in range(rozmiar):
        wiersz = []
        for x in range(rozmiar):
            r = g = b = 0
            for dy in range(krotnosc):
                for dx in range(krotnosc):
                    pr, pg, pb = dokladne[y * krotnosc + dy][x * krotnosc + dx]
                    r += pr
                    g += pg
                    b += pb
            n = krotnosc * krotnosc
            wiersz.append((r // n, g // n, b // n))
        wynik.append(wiersz)
    return wynik


WYJSCIE.mkdir(parents=True, exist_ok=True)
for rozmiar, nazwa in ((512, "icon-512.png"), (192, "icon-192.png"), (180, "apple-touch-icon.png")):
    zapisz_png(WYJSCIE / nazwa, wygladz(rozmiar))
    print(f"{nazwa}: {(WYJSCIE / nazwa).stat().st_size} B")
