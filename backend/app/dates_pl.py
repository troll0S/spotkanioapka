"""Polskie opisy terminów.

Etykietę buduje serwer, nie frontend. Powód jest prozaiczny: ten sam napis
musi trafić na ekran hosta, na telefony w etapie 4, do kalendarza, do PDF-a
i do pliku ICS. Gdyby każde z tych miejsc formatowało datę u siebie, po kilku
kamieniach mielibyśmy pięć różnych zapisów tego samego terminu.
"""

from datetime import date

MIESIACE_MIANOWNIK = (
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
)

MIESIACE_DOPELNIACZ = (
    "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
    "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
)

DNI_TYGODNIA = (
    "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela",
)


def miesiac_mianownik(numer: int) -> str:
    return MIESIACE_MIANOWNIK[numer - 1]


def miesiac_dopelniacz(numer: int) -> str:
    return MIESIACE_DOPELNIACZ[numer - 1]


def dzien_tygodnia(dzien: date) -> str:
    return DNI_TYGODNIA[dzien.weekday()]


def dokladna_data(dzien: date) -> str:
    """„sobota, 14 marca 2026" — dzień tygodnia jest tu istotny.

    Przy planowaniu spotkań to pierwsza rzecz, o którą pyta człowiek
    patrzący na datę.
    """
    return f"{dzien_tygodnia(dzien)}, {dzien.day} {miesiac_dopelniacz(dzien.month)} {dzien.year}"


def przedzial(od: date, do: date) -> str:
    """„10–20 marca 2026", „28 marca – 4 kwietnia 2026", „28.12.2026 – 3.01.2027".

    Powtarzamy tylko to, co się zmienia — zapis ma być czytany, nie parsowany.
    """
    if od == do:
        return dokladna_data(od)
    if od.year != do.year:
        return (
            f"{od.day} {miesiac_dopelniacz(od.month)} {od.year} – "
            f"{do.day} {miesiac_dopelniacz(do.month)} {do.year}"
        )
    if od.month != do.month:
        return (
            f"{od.day} {miesiac_dopelniacz(od.month)} – "
            f"{do.day} {miesiac_dopelniacz(do.month)} {do.year}"
        )
    return f"{od.day}–{do.day} {miesiac_dopelniacz(od.month)} {od.year}"


def tydzien(od: date, do: date) -> str:
    """„tydzień 12: 16–22 marca 2026"."""
    numer = od.isocalendar().week
    return f"tydzień {numer}: {przedzial(od, do)}"


def miesiac(dzien: date) -> str:
    """„marzec 2026"."""
    return f"{miesiac_mianownik(dzien.month)} {dzien.year}"
