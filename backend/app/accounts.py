"""Konta administratorów.

Zastępują jedno wspólne hasło. Zmiana jest głębsza, niż wygląda: wcześniej
„admin" był jedną tajemnicą, teraz jest konkretną osobą — widać, kto założył
sesję, a odebranie dostępu jednej osobie nie wywraca reszty.

Konto z `.env` nie znika: przy pustej bazie zakładamy z niego pierwszego
superadmina, żeby nie było problemu kury i jajka.
"""

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from . import config
from .models import AdminUser
from .security import hash_password, verify_password

log = logging.getLogger("spotkanioapka.accounts")

#: Login to identyfikator, nie nazwa wyświetlana — bez spacji i znaków
#: diakrytycznych, żeby nie dało się założyć dwóch kont wyglądających
#: identycznie.
LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,39}$")

MIN_HASLO = 8

#: Opis wymagań — jedno źródło dla komunikatów błędów, podpowiedzi
#: w interfejsie i dokumentacji.
WYMAGANIA_HASLA = (
    f"co najmniej {MIN_HASLO} znaków, w tym wielka litera, mała litera, "
    "cyfra i znak specjalny"
)


class AccountError(Exception):
    """Problem z kontem — komunikat jest przeznaczony dla użytkownika."""


def normalize_login(login: str) -> str:
    return (login or "").strip().lower()


def password_problems(password: str) -> list[str]:
    """Czego brakuje w haśle. Pusta lista oznacza, że jest w porządku.

    Zwracamy listę braków, a nie samo „za słabe": człowiek ma wiedzieć,
    co dopisać, zamiast zgadywać.
    """
    braki = []
    if len(password or "") < MIN_HASLO:
        braki.append(f"co najmniej {MIN_HASLO} znaków")
    if not any(z.isupper() for z in password):
        braki.append("wielką literę")
    if not any(z.islower() for z in password):
        braki.append("małą literę")
    if not any(z.isdigit() for z in password):
        braki.append("cyfrę")
    # Spacja nie liczy się jako znak specjalny — inaczej „Haslo 1a" przechodziłoby
    # jako spełniające wymóg, nic realnie nie zyskując.
    if not any(not z.isalnum() and not z.isspace() for z in password):
        braki.append("znak specjalny")
    return braki


def validate_password(password: str) -> None:
    braki = password_problems(password or "")
    if braki:
        raise AccountError("Hasło musi zawierać " + ", ".join(braki) + ".")


def _validate(login: str, password: str | None) -> str:
    czysty = normalize_login(login)
    if not LOGIN_RE.match(czysty):
        raise AccountError(
            "Login: 2–40 znaków, małe litery, cyfry oraz . _ -, zaczynając od litery lub cyfry."
        )
    if password is not None:
        validate_password(password)
    return czysty


def count(db: DbSession) -> int:
    return db.scalar(select(func.count(AdminUser.id))) or 0


def by_login(db: DbSession, login: str) -> AdminUser | None:
    return db.scalar(select(AdminUser).where(AdminUser.login == normalize_login(login)))


def all_users(db: DbSession) -> list[AdminUser]:
    return list(db.scalars(select(AdminUser).order_by(AdminUser.login)))


def authenticate(db: DbSession, login: str, password: str) -> AdminUser | None:
    """Sprawdza dane logowania. Zwraca konto albo None.

    Konto nieaktywne nie zaloguje się nigdy — sprawdzamy to po haśle, żeby
    po czasie odpowiedzi nie dało się odgadnąć, które loginy istnieją.
    """
    konto = by_login(db, login)
    if konto is None:
        # Liczymy hash mimo braku konta — inaczej nieistniejący login
        # odpowiadałby zauważalnie szybciej niż istniejący.
        verify_password(password, "pbkdf2_sha256$200000$00$00")
        return None
    if not verify_password(password, konto.password_hash):
        return None
    if not konto.is_active:
        return None

    konto.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return konto


def create(
    db: DbSession, login: str, password: str, *, is_superadmin: bool = False
) -> AdminUser:
    czysty = _validate(login, password)
    if by_login(db, czysty) is not None:
        raise AccountError(f"Konto „{czysty}” już istnieje.")

    konto = AdminUser(
        login=czysty,
        password_hash=hash_password(password),
        is_superadmin=is_superadmin,
        is_active=True,
    )
    db.add(konto)
    db.commit()
    return konto


def set_password(db: DbSession, konto: AdminUser, password: str) -> None:
    validate_password(password)
    konto.password_hash = hash_password(password)
    db.commit()


def set_active(db: DbSession, konto: AdminUser, active: bool) -> None:
    if not active and konto.is_superadmin and _active_superadmins(db) <= 1:
        raise AccountError("To ostatni aktywny superadmin — nie da się go wyłączyć.")
    konto.is_active = active
    db.commit()


def set_superadmin(db: DbSession, konto: AdminUser, value: bool) -> None:
    if not value and konto.is_superadmin and _active_superadmins(db) <= 1:
        raise AccountError("To ostatni superadmin — ktoś musi zarządzać kontami.")
    konto.is_superadmin = value
    db.commit()


def delete(db: DbSession, konto: AdminUser) -> None:
    if konto.is_superadmin and _active_superadmins(db) <= 1:
        raise AccountError("To ostatni superadmin — bez niego nikt nie doda kont.")
    db.delete(konto)
    db.commit()


def _active_superadmins(db: DbSession) -> int:
    return (
        db.scalar(
            select(func.count(AdminUser.id))
            .where(AdminUser.is_superadmin.is_(True))
            .where(AdminUser.is_active.is_(True))
        )
        or 0
    )


def bootstrap(db: DbSession) -> AdminUser | None:
    """Pierwszy superadmin z pliku `.env`, gdy nie ma jeszcze żadnego konta.

    Bez tego nie dałoby się zalogować, żeby założyć pierwsze konto. Po
    utworzeniu kont zmienne z `.env` przestają mieć znaczenie — hasła żyją
    w bazie i zmienia się je w panelu.
    """
    if count(db) > 0:
        return None
    if not config.ADMIN_PASSWORD:
        return None

    # Konto startowe to superadmin — gdyby omijało politykę haseł, cała
    # polityka byłaby dekoracją.
    braki = password_problems(config.ADMIN_PASSWORD)
    if braki:
        log.warning(
            "ADMIN_PASSWORD nie spełnia wymagań (%s) — konto startowe nie powstało.",
            ", ".join(braki),
        )
        return None

    login = normalize_login(config.SUPERADMIN_LOGIN)
    if not LOGIN_RE.match(login):
        login = "admin"

    konto = AdminUser(
        login=login,
        password_hash=hash_password(config.ADMIN_PASSWORD),
        is_superadmin=True,
        is_active=True,
    )
    db.add(konto)
    db.commit()
    return konto
