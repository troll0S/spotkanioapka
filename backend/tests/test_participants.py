"""Testy najłatwiejszego do przeoczenia błędu w projekcie.

Gdyby host albo admin trafili do mianownika liczników, etap nigdy by się nie
domknął — a objaw wyglądałby jak zawieszona aplikacja, nie jak błąd.
"""

from app.models import Participant, Role
from app.participants import voting_count, voting_participants
from app.security import new_token


def test_host_i_admin_nie_licza_sie_do_glosujacych(db, sample_session):
    voters = voting_participants(db, sample_session.id)
    imiona = {p.display_name for p in voters}

    assert imiona == {"Ania", "Bartek"}, "W mianowniku mogą być tylko goście"
    assert voting_count(db, sample_session.id) == 2
    assert len(sample_session.participants) == 4, "ale w sesji są cztery osoby"


def test_admin_z_wlaczonym_glosowaniem_wchodzi_do_mianownika(db, sample_session):
    """Przełącznik dla sytuacji, gdy proces prowadzi kto inny niż admin."""
    admin = next(p for p in sample_session.participants if p.role_enum is Role.ADMIN)
    admin.is_voting = True
    db.commit()

    assert voting_count(db, sample_session.id) == 3


def test_rozlaczony_gosc_zostaje_w_mianowniku(db, sample_session):
    """Blokada ekranu telefonu nie może zmieniać liczby oczekiwanych głosów."""
    ania = next(p for p in sample_session.participants if p.display_name == "Ania")
    ania.connected = False
    db.commit()

    assert voting_count(db, sample_session.id) == 2


def test_nowy_gosc_powieksza_mianownik(db, sample_session):
    db.add(
        Participant(
            session_id=sample_session.id,
            display_name="Czarek",
            token=new_token(),
            role=Role.GUEST.value,
            is_voting=True,
        )
    )
    db.commit()

    assert voting_count(db, sample_session.id) == 3
