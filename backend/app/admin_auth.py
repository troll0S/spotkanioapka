"""Token administratora do panelu i archiwum.

Po co osobny mechanizm, skoro w sesji admin jest już rozpoznawany po roli:
rola działa **wewnątrz jednej sesji**, a archiwum i zarządzanie kontami są
ponad nimi. Lista wszystkich spotkań to jedyne miejsce w aplikacji widoczne
spoza bieżącej sesji — i jedyne, które przez publiczny adres tunelu
wyciekłoby komuś, kto nie zna żadnego kodu.

Tokeny żyją w pamięci procesu. Restart je unieważnia i to jest w porządku:
to aplikacja uruchamiana na spotkanie, nie usługa z ciągłością sesji.
"""

import secrets
import time
from dataclasses import dataclass

#: Osiem godzin — dłużej niż najdłuższe spotkanie, krócej niż doba.
TTL_SEKUND = 8 * 3600


@dataclass(frozen=True)
class TokenInfo:
    login: str
    is_superadmin: bool
    expires_at: float


_tokeny: dict[str, TokenInfo] = {}


def _sprzatnij(teraz: float) -> None:
    for token, info in list(_tokeny.items()):
        if info.expires_at <= teraz:
            _tokeny.pop(token, None)


def issue(login: str, is_superadmin: bool) -> tuple[str, int]:
    teraz = time.monotonic()
    _sprzatnij(teraz)
    token = secrets.token_urlsafe(32)
    _tokeny[token] = TokenInfo(login, is_superadmin, teraz + TTL_SEKUND)
    return token, TTL_SEKUND


def info(token: str | None) -> TokenInfo | None:
    if not token:
        return None
    teraz = time.monotonic()
    _sprzatnij(teraz)
    dane = _tokeny.get(token)
    return dane if dane and dane.expires_at > teraz else None


def revoke(token: str | None) -> None:
    if token:
        _tokeny.pop(token, None)


def revoke_login(login: str) -> None:
    """Unieważnia wszystkie tokeny konta.

    Wołane po wyłączeniu, usunięciu albo zmianie hasła konta — inaczej
    odebranie dostępu działałoby dopiero po ośmiu godzinach.
    """
    for token, dane in list(_tokeny.items()):
        if dane.login == login:
            _tokeny.pop(token, None)


def clear() -> None:
    _tokeny.clear()
