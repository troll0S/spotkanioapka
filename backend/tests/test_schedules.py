"""Etap 3 — normalizacja czterech rodzajów terminu do jednego kształtu.

To jest ten fragment, w którym błąd rozlewa się najdalej: kalendarz z etapu 5
oraz eksport do PDF-a i ICS-a czytają wyłącznie parę `(od, do)`.
"""

from datetime import date

import pytest

from app import ideas, schedules, swipes
from app.models import ScheduleKind
from app.schedules import ScheduleError
from app.state_machine import SessionStatus


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


@pytest.fixture()
def terminy(db, sample_session):
    """Sesja na etapie 3: jeden pomysł przyjęty, jeden ustalony, jeden odrzucony."""
    sample_session.status = SessionStatus.COLLECTING.value
    db.commit()

    ania = osoba(sample_session, "Ania")
    admin = osoba(sample_session, "Admin")
    ideas.create_idea(db, sample_session, ania, "Kajaki")
    ideas.create_idea(db, sample_session, ania, "Kino")
    ideas.create_idea(db, sample_session, admin, "Urodziny babci", is_special=True)

    sample_session.status = SessionStatus.SWIPING.value
    db.commit()

    ekran = osoba(sample_session, "Ekran")
    lista = {i.title: i for i in ideas.list_ideas(db, sample_session.id)}
    swipes.decide(db, sample_session, ekran, lista["Kajaki"].id, accepted=True)
    swipes.decide(db, sample_session, ekran, lista["Kino"].id, accepted=False)

    sample_session.status = SessionStatus.SCHEDULING.value
    db.commit()
    return sample_session


def pomysl(db, session, tytul):
    return next(i for i in ideas.list_ideas(db, session.id) if i.title == tytul)


# ── normalizacja ────────────────────────────────────────────────────────────


def test_dokladna_data_to_przedzial_jednodniowy():
    od, do, etykieta = schedules.normalize(ScheduleKind.EXACT_DATE, date="2026-03-14")

    assert (od, do) == (date(2026, 3, 14), date(2026, 3, 14))
    assert etykieta == "sobota, 14 marca 2026"


def test_tydzien_rozciaga_sie_od_poniedzialku_do_niedzieli():
    """Host wskazuje dowolny dzień, my bierzemy z niego cały tydzień."""
    od, do, etykieta = schedules.normalize(ScheduleKind.WEEK, date="2026-03-18")

    assert od == date(2026, 3, 16), "poniedziałek"
    assert do == date(2026, 3, 22), "niedziela"
    assert etykieta == "tydzień 12: 16–22 marca 2026"


def test_tydzien_wskazany_w_niedziele_nie_przeskakuje_dalej():
    """Niedziela należy do tygodnia, który się właśnie kończy, nie do następnego."""
    od, do, _ = schedules.normalize(ScheduleKind.WEEK, date="2026-03-22")

    assert (od, do) == (date(2026, 3, 16), date(2026, 3, 22))


def test_miesiac_obejmuje_wszystkie_dni():
    od, do, etykieta = schedules.normalize(ScheduleKind.MONTH, year=2026, month=3)

    assert (od, do) == (date(2026, 3, 1), date(2026, 3, 31))
    assert etykieta == "marzec 2026"


def test_luty_w_roku_przestepnym():
    od, do, _ = schedules.normalize(ScheduleKind.MONTH, year=2028, month=2)
    assert do == date(2028, 2, 29)


def test_luty_w_roku_zwyklym():
    od, do, _ = schedules.normalize(ScheduleKind.MONTH, year=2026, month=2)
    assert do == date(2026, 2, 28)


def test_przedzial_zostaje_jak_podany():
    od, do, etykieta = schedules.normalize(
        ScheduleKind.RANGE, date_from="2026-03-10", date_to="2026-03-20"
    )

    assert (od, do) == (date(2026, 3, 10), date(2026, 3, 20))
    assert etykieta == "10–20 marca 2026"


def test_przedzial_przez_granice_miesiaca():
    _, _, etykieta = schedules.normalize(
        ScheduleKind.RANGE, date_from="2026-03-28", date_to="2026-04-04"
    )
    assert etykieta == "28 marca – 4 kwietnia 2026"


def test_przedzial_przez_granice_roku():
    _, _, etykieta = schedules.normalize(
        ScheduleKind.RANGE, date_from="2026-12-28", date_to="2027-01-03"
    )
    assert etykieta == "28 grudnia 2026 – 3 stycznia 2027"


def test_przedzial_odwrocony_jest_odrzucany():
    with pytest.raises(ScheduleError, match="przed jego początkiem"):
        schedules.normalize(ScheduleKind.RANGE, date_from="2026-03-20", date_to="2026-03-10")


def test_przedzial_jednodniowy_opisujemy_jak_date():
    _, _, etykieta = schedules.normalize(
        ScheduleKind.RANGE, date_from="2026-03-14", date_to="2026-03-14"
    )
    assert etykieta == "sobota, 14 marca 2026"


@pytest.mark.parametrize("zly", ["", None, "14.03.2026", "2026-13-01", "wczoraj"])
def test_niepoprawna_data_odrzucona(zly):
    with pytest.raises(ScheduleError):
        schedules.normalize(ScheduleKind.EXACT_DATE, date=zly)


def test_rok_poza_zakresem_odrzucony():
    with pytest.raises(ScheduleError, match="pomyłkę"):
        schedules.normalize(ScheduleKind.EXACT_DATE, date="1999-01-01")


def test_nieistniejacy_miesiac_odrzucony():
    with pytest.raises(ScheduleError, match="takiego miesiąca"):
        schedules.normalize(ScheduleKind.MONTH, year=2026, month=13)


# ── zapis ───────────────────────────────────────────────────────────────────


def test_host_ustala_termin(db, terminy):
    kajaki = pomysl(db, terminy, "Kajaki")
    t = schedules.set_schedule(
        db, terminy, osoba(terminy, "Ekran"), kajaki.id, "EXACT_DATE", date="2026-03-14"
    )

    assert t.date_from == date(2026, 3, 14)
    assert t.label == "sobota, 14 marca 2026"


def test_ponowne_ustalenie_nadpisuje(db, terminy):
    kajaki = pomysl(db, terminy, "Kajaki")
    ekran = osoba(terminy, "Ekran")

    schedules.set_schedule(db, terminy, ekran, kajaki.id, "EXACT_DATE", date="2026-03-14")
    schedules.set_schedule(db, terminy, ekran, kajaki.id, "MONTH", year=2026, month=5)

    wszystkie = schedules.by_idea(db, terminy.id)
    assert len(wszystkie) == 1, "jeden termin na pomysł, nie dwa"
    assert wszystkie[kajaki.id].label == "maj 2026"


def test_termin_da_sie_wyczyscic(db, terminy):
    kajaki = pomysl(db, terminy, "Kajaki")
    ekran = osoba(terminy, "Ekran")
    schedules.set_schedule(db, terminy, ekran, kajaki.id, "EXACT_DATE", date="2026-03-14")

    schedules.clear_schedule(db, terminy, ekran, kajaki.id)

    assert schedules.by_idea(db, terminy.id) == {}


def test_tylko_host_ustala_terminy(db, terminy):
    """Z opisu: „tu wszystko dzieje się na urządzeniu hostującym"."""
    kajaki = pomysl(db, terminy, "Kajaki")

    for imie in ("Ania", "Admin"):
        with pytest.raises(ScheduleError, match="prowadzący"):
            schedules.set_schedule(
                db, terminy, osoba(terminy, imie), kajaki.id, "EXACT_DATE", date="2026-03-14"
            )


def test_odrzucony_pomysl_nie_dostanie_terminu(db, terminy):
    kino = pomysl(db, terminy, "Kino")

    with pytest.raises(ScheduleError, match="nie przeszedł"):
        schedules.set_schedule(
            db, terminy, osoba(terminy, "Ekran"), kino.id, "EXACT_DATE", date="2026-03-14"
        )


def test_wpis_ustalony_dostaje_termin_na_rowni(db, terminy):
    """Pomija etap 2, ale w etapie 3 bierze pełny udział."""
    babcia = pomysl(db, terminy, "Urodziny babci")
    schedules.set_schedule(
        db, terminy, osoba(terminy, "Ekran"), babcia.id, "MONTH", year=2026, month=6
    )

    assert schedules.by_idea(db, terminy.id)[babcia.id].label == "czerwiec 2026"


@pytest.mark.parametrize(
    "status", [SessionStatus.SWIPING, SessionStatus.AVAILABILITY, SessionStatus.CLOSED]
)
def test_poza_etapem_3_nie_da_sie_ustalac(db, terminy, status):
    kajaki = pomysl(db, terminy, "Kajaki")
    terminy.status = status.value
    db.commit()

    with pytest.raises(ScheduleError, match="nie jest aktywny"):
        schedules.set_schedule(
            db, terminy, osoba(terminy, "Ekran"), kajaki.id, "EXACT_DATE", date="2026-03-14"
        )


# ── zestawienie ─────────────────────────────────────────────────────────────


def test_brakujace_terminy(db, terminy):
    """Do etapu 3 weszły dwa pomysły: przyjęty i ustalony."""
    assert {i.title for i in schedules.missing(db, terminy.id)} == {"Kajaki", "Urodziny babci"}

    kajaki = pomysl(db, terminy, "Kajaki")
    schedules.set_schedule(
        db, terminy, osoba(terminy, "Ekran"), kajaki.id, "EXACT_DATE", date="2026-03-14"
    )

    assert [i.title for i in schedules.missing(db, terminy.id)] == ["Urodziny babci"]


def test_agenda_sortuje_po_dacie_a_bez_terminu_na_koncu(db, terminy):
    ekran = osoba(terminy, "Ekran")
    schedules.set_schedule(
        db, terminy, ekran, pomysl(db, terminy, "Kajaki").id, "EXACT_DATE", date="2026-06-01"
    )
    schedules.set_schedule(
        db,
        terminy,
        ekran,
        pomysl(db, terminy, "Urodziny babci").id,
        "EXACT_DATE",
        date="2026-03-14",
    )

    tytuly = [p["title"] for p in schedules.agenda(db, terminy.id)]
    assert tytuly == ["Urodziny babci", "Kajaki"]


def test_agenda_oznacza_terminy_z_przeszlosci(db, terminy):
    """Ostrzeżenie, nie blokada — host może wiedzieć, co robi."""
    kajaki = pomysl(db, terminy, "Kajaki")
    schedules.set_schedule(
        db, terminy, osoba(terminy, "Ekran"), kajaki.id, "EXACT_DATE", date="2020-01-01"
    )

    pozycja = next(p for p in schedules.agenda(db, terminy.id) if p["title"] == "Kajaki")
    assert pozycja["schedule"]["isPast"] is True


# ── snapshot ────────────────────────────────────────────────────────────────


def test_gosc_dostaje_tylko_postep(db, terminy):
    """Etap 3 nie jest interaktywny — telefon nie ma być drugim ekranem hosta."""
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, terminy, osoba(terminy, "Ania"))

    assert snap["scheduling"]["total"] == 2
    assert snap["scheduling"]["missing"] == 2
    assert "items" not in snap["scheduling"]


def test_host_dostaje_pelna_liste(db, terminy):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, terminy, osoba(terminy, "Ekran"))

    assert len(snap["scheduling"]["items"]) == 2
    assert all(p["schedule"] is None for p in snap["scheduling"]["items"])


def test_widz_dostaje_pelna_liste(db, terminy):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, terminy, None)
    assert len(snap["scheduling"]["items"]) == 2
