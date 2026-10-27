import pytest

from app.state_machine import (
    SEQUENCE,
    InvalidTransition,
    SessionStatus,
    abort,
    advance,
    allowed_transitions,
    can_advance,
)


def test_pelna_sekwencja_konczy_sie_zamknieciem():
    """Przejście przez wszystkie pięć etapów musi dojść do CLOSED."""
    status = SessionStatus.LOBBY
    odwiedzone = [status]
    for _ in range(len(SEQUENCE)):
        status = advance(status)
        odwiedzone.append(status)

    assert odwiedzone == [
        SessionStatus.LOBBY,
        SessionStatus.COLLECTING,
        SessionStatus.SWIPING,
        SessionStatus.SCHEDULING,
        SessionStatus.AVAILABILITY,
        SessionStatus.ASSIGNMENT,
        SessionStatus.CALENDAR,
        SessionStatus.CLOSED,
    ]


@pytest.mark.parametrize("status", SEQUENCE)
def test_przerwanie_dziala_z_kazdego_etapu(status):
    """Wprost z opisu: host może przerwać sesję w dowolnym momencie."""
    assert abort(status) is SessionStatus.CLOSED


def test_z_zamknietej_sesji_nie_ma_wyjscia():
    assert not can_advance(SessionStatus.CLOSED)
    with pytest.raises(InvalidTransition):
        advance(SessionStatus.CLOSED)
    with pytest.raises(InvalidTransition):
        abort(SessionStatus.CLOSED)
    assert allowed_transitions(SessionStatus.CLOSED) == set()


def test_nie_da_sie_przeskoczyc_etapu():
    """Z LOBBY osiągalne są tylko COLLECTING i CLOSED — nic poza tym."""
    assert allowed_transitions(SessionStatus.LOBBY) == {
        SessionStatus.COLLECTING,
        SessionStatus.CLOSED,
    }
    assert SessionStatus.SWIPING not in allowed_transitions(SessionStatus.LOBBY)


def test_kalendarz_prowadzi_do_zamkniecia():
    assert advance(SessionStatus.CALENDAR) is SessionStatus.CLOSED
