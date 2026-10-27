"""Kody sesji — sześć znaków przepisywanych z ekranu hosta na telefon."""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

#: Bez znaków, które ludzie mylą przy przepisywaniu: 0/O, 1/I/L, 2/Z, 5/S, 8/B.
#: Kod ma być czytany z drugiego końca stołu, nie tylko skanowany z QR.
ALPHABET = "ACDEFGHJKMNPQRTUVWXY34679"
LENGTH = 6


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def unique_code(db: DbSession) -> str:
    """Kod niekolidujący z istniejącą sesją.

    Przestrzeń to 25^6 ≈ 244 mln, więc kolizja jest teoretyczna — ale sprawdzenie
    kosztuje jedno zapytanie, a bez niego sesja mogłaby cicho przejąć cudzy kod.
    """
    from .models import Session  # import lokalny: codes.py nie zależy od modeli

    for _ in range(50):
        code = new_code()
        if db.scalar(select(Session).where(Session.code == code)) is None:
            return code
    raise RuntimeError("Nie udało się wylosować wolnego kodu sesji.")


def normalize(code: str) -> str:
    """Kod wpisany na telefonie: znosi małe litery i przypadkowe spacje."""
    return code.strip().replace(" ", "").replace("-", "").upper()
