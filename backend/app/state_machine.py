"""Maszyna stanów sesji — jedyne miejsce, które wie, co po czym następuje.

Stan trzyma serwer, nie klient. Telefon przy każdym (re)połączeniu dostaje
snapshot i renderuje ekran właściwy dla aktualnego statusu. Dzięki temu
dołączenie w trakcie, odświeżenie strony i utrata Wi-Fi to jeden mechanizm,
a nie trzy osobne przypadki.

Ten moduł celowo nie importuje modeli ani bazy — ma być testowalny w izolacji.
"""

from enum import Enum


class SessionStatus(str, Enum):
    LOBBY = "LOBBY"
    COLLECTING = "COLLECTING"        # etap 1 — wpisywanie pomysłów
    SWIPING = "SWIPING"              # etap 2 — swipe + decyzje hosta
    SCHEDULING = "SCHEDULING"        # etap 3 — terminy, tylko host
    AVAILABILITY = "AVAILABILITY"    # etap 4 — chcę / mogę / nie chcę / absolutnie nie
    ASSIGNMENT = "ASSIGNMENT"        # etap 5 — kto to zrobi, zatwierdzenie lub odrzucenie
    CALENDAR = "CALENDAR"            # etap 6 — kalendarz i eksport
    CLOSED = "CLOSED"                # archiwum, tylko do odczytu


#: Kolejność etapów. CLOSED nie jest częścią sekwencji — wchodzi się w niego
#: albo z CALENDAR (naturalne zakończenie), albo przerwaniem z dowolnego stanu.
SEQUENCE: tuple[SessionStatus, ...] = (
    SessionStatus.LOBBY,
    SessionStatus.COLLECTING,
    SessionStatus.SWIPING,
    SessionStatus.SCHEDULING,
    SessionStatus.AVAILABILITY,
    SessionStatus.ASSIGNMENT,
    SessionStatus.CALENDAR,
)

#: Etykiety dla interfejsu — trzymane przy stanach, żeby nie rozjechały się
#: między widokiem hosta a widokiem gościa.
LABELS: dict[SessionStatus, str] = {
    SessionStatus.LOBBY: "Poczekalnia",
    SessionStatus.COLLECTING: "Etap 1 — zbieranie pomysłów",
    SessionStatus.SWIPING: "Etap 2 — wybór pomysłów",
    SessionStatus.SCHEDULING: "Etap 3 — terminy",
    SessionStatus.AVAILABILITY: "Etap 4 — dostępność",
    SessionStatus.ASSIGNMENT: "Etap 5 — kto to zrobi",
    SessionStatus.CALENDAR: "Etap 6 — kalendarz",
    SessionStatus.CLOSED: "Sesja zakończona",
}


class InvalidTransition(Exception):
    """Próba przejścia, którego maszyna stanów nie przewiduje."""


def is_active(status: SessionStatus) -> bool:
    return status is not SessionStatus.CLOSED


def next_status(status: SessionStatus) -> SessionStatus:
    """Następny etap w sekwencji.

    Z CALENDAR prowadzi do CLOSED — to naturalne zakończenie sesji.
    Z CLOSED nie prowadzi nigdzie.
    """
    if status is SessionStatus.CLOSED:
        raise InvalidTransition("Sesja jest już zamknięta.")
    if status is SessionStatus.CALENDAR:
        return SessionStatus.CLOSED
    return SEQUENCE[SEQUENCE.index(status) + 1]


def can_advance(status: SessionStatus) -> bool:
    return status is not SessionStatus.CLOSED


def advance(status: SessionStatus) -> SessionStatus:
    """Przejście do kolejnego etapu. Wywołuje wyłącznie host."""
    if not can_advance(status):
        raise InvalidTransition(f"Nie można kontynuować ze stanu {status.value}.")
    return next_status(status)


def abort(status: SessionStatus) -> SessionStatus:
    """Przerwanie sesji — dozwolone z każdego stanu poza CLOSED.

    Wprost z opisu: "host może przerwać sesję w dowolnym momencie".
    """
    if status is SessionStatus.CLOSED:
        raise InvalidTransition("Sesja jest już zamknięta.")
    return SessionStatus.CLOSED


def allowed_transitions(status: SessionStatus) -> set[SessionStatus]:
    """Zbiór stanów osiągalnych z danego — używane w testach i walidacji."""
    if status is SessionStatus.CLOSED:
        return set()
    return {next_status(status), SessionStatus.CLOSED}
