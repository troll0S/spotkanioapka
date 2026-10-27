"""Etap 4 — deklaracje dostępności prowadzone przez hosta."""

import pytest

from app import availability, ideas, schedules, swipes
from app.availability import AvailabilityError
from app.models import Answer
from app.state_machine import SessionStatus


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


def pomysl(db, session, tytul):
    return next(i for i in ideas.list_ideas(db, session.id) if i.title == tytul)


@pytest.fixture()
def dostepnosc(db, sample_session):
    """Sesja na etapie 4: trzy wydarzenia z terminami, kolejność wylosowana."""
    sample_session.status = SessionStatus.COLLECTING.value
    db.commit()

    ania = osoba(sample_session, "Ania")
    admin = osoba(sample_session, "Admin")
    for tytul in ("Kajaki", "Kino"):
        ideas.create_idea(db, sample_session, ania, tytul)
    ideas.create_idea(db, sample_session, admin, "Urodziny babci", is_special=True)

    sample_session.status = SessionStatus.SWIPING.value
    db.commit()
    ekran = osoba(sample_session, "Ekran")
    for tytul in ("Kajaki", "Kino"):
        swipes.decide(db, sample_session, ekran, pomysl(db, sample_session, tytul).id, True)

    sample_session.status = SessionStatus.SCHEDULING.value
    db.commit()
    for numer, tytul in enumerate(("Kajaki", "Kino", "Urodziny babci"), start=1):
        schedules.set_schedule(
            db,
            sample_session,
            ekran,
            pomysl(db, sample_session, tytul).id,
            "EXACT_DATE",
            date=f"2026-0{numer}-10",
        )

    sample_session.status = SessionStatus.AVAILABILITY.value
    db.commit()
    availability.build_order(db, sample_session)
    return sample_session


# ── kolejność ───────────────────────────────────────────────────────────────


def test_kolejnosc_obejmuje_wszystkie_wydarzenia(db, dostepnosc):
    kolejnosc = availability.order(dostepnosc)

    assert len(kolejnosc) == 3
    assert set(kolejnosc) == {i.id for i in swipes.accepted_ideas(db, dostepnosc.id)}


def test_kolejnosc_jest_stala_miedzy_odczytami(db, dostepnosc):
    """Losowanie przy każdym odczycie przestawiałoby ekran pod ludźmi."""
    assert availability.order(dostepnosc) == availability.order(dostepnosc)


def test_zaczynamy_od_pierwszego_wydarzenia(db, dostepnosc):
    assert dostepnosc.availability_index == 0
    assert availability.current_idea_id(dostepnosc) == availability.order(dostepnosc)[0]


def test_host_przechodzi_dalej_i_wraca(db, dostepnosc):
    ekran = osoba(dostepnosc, "Ekran")
    kolejnosc = availability.order(dostepnosc)

    availability.move(db, dostepnosc, ekran, 1)
    assert availability.current_idea_id(dostepnosc) == kolejnosc[1]

    # Cofanie jest dozwolone: host może kliknąć „dalej" za wcześnie.
    availability.move(db, dostepnosc, ekran, -1)
    assert availability.current_idea_id(dostepnosc) == kolejnosc[0]


def test_nie_da_sie_wyjsc_poza_zakres(db, dostepnosc):
    ekran = osoba(dostepnosc, "Ekran")

    with pytest.raises(AvailabilityError, match="pierwsze"):
        availability.move(db, dostepnosc, ekran, -1)

    availability.move(db, dostepnosc, ekran, 1)
    availability.move(db, dostepnosc, ekran, 1)
    with pytest.raises(AvailabilityError, match="ostatnie"):
        availability.move(db, dostepnosc, ekran, 1)


def test_gosc_nie_steruje_przebiegiem(db, dostepnosc):
    with pytest.raises(AvailabilityError, match="prowadzący"):
        availability.move(db, dostepnosc, osoba(dostepnosc, "Ania"), 1)


def test_wszystkie_pokazane_dopiero_na_ostatnim(db, dostepnosc):
    ekran = osoba(dostepnosc, "Ekran")

    assert availability.all_presented(dostepnosc) is False
    assert availability.remaining(dostepnosc) == 2

    availability.move(db, dostepnosc, ekran, 1)
    availability.move(db, dostepnosc, ekran, 1)

    assert availability.all_presented(dostepnosc) is True
    assert availability.remaining(dostepnosc) == 0


# ── odpowiedzi ──────────────────────────────────────────────────────────────


def test_gosc_odpowiada(db, dostepnosc):
    biezace = availability.current_idea_id(dostepnosc)
    availability.answer(db, dostepnosc, osoba(dostepnosc, "Ania"), biezace, "WANT")

    assert availability.tally(db, biezace)["WANT"] == 1


def test_odpowiedz_jest_wiazaca(db, dostepnosc):
    """Gość odpowiada raz i nie może się rozmyślić — korekta tylko z panelu admina."""
    biezace = availability.current_idea_id(dostepnosc)
    ania = osoba(dostepnosc, "Ania")
    availability.answer(db, dostepnosc, ania, biezace, "WANT")

    with pytest.raises(AvailabilityError, match="Już odpowiedziałeś"):
        availability.answer(db, dostepnosc, ania, biezace, "ABSOLUTELY_NOT")

    assert availability.tally(db, biezace)["WANT"] == 1


def test_nie_da_sie_odpowiedziec_na_inne_wydarzenie(db, dostepnosc):
    """Telefon z nieodświeżonym ekranem nie może wpisać głosu wstecz."""
    kolejnosc = availability.order(dostepnosc)

    with pytest.raises(AvailabilityError, match="nie jest już na ekranie"):
        availability.answer(db, dostepnosc, osoba(dostepnosc, "Ania"), kolejnosc[2], "WANT")


def test_host_nie_deklaruje_dostepnosci(db, dostepnosc):
    biezace = availability.current_idea_id(dostepnosc)

    with pytest.raises(AvailabilityError, match="prowadzącego"):
        availability.answer(db, dostepnosc, osoba(dostepnosc, "Ekran"), biezace, "WANT")


def test_admin_bez_prawa_glosu_nie_deklaruje(db, dostepnosc):
    biezace = availability.current_idea_id(dostepnosc)

    with pytest.raises(AvailabilityError, match="Nie bierzesz udziału"):
        availability.answer(db, dostepnosc, osoba(dostepnosc, "Admin"), biezace, "WANT")


def test_nieznana_odpowiedz_odrzucona(db, dostepnosc):
    biezace = availability.current_idea_id(dostepnosc)

    with pytest.raises(AvailabilityError, match="Nieznana odpowiedź"):
        availability.answer(db, dostepnosc, osoba(dostepnosc, "Ania"), biezace, "MOŻE_BYĆ")


@pytest.mark.parametrize("odpowiedz", [a.value for a in Answer])
def test_wszystkie_cztery_opcje_dzialaja(db, dostepnosc, odpowiedz):
    biezace = availability.current_idea_id(dostepnosc)
    availability.answer(db, dostepnosc, osoba(dostepnosc, "Ania"), biezace, odpowiedz)

    assert availability.tally(db, biezace)[odpowiedz] == 1


@pytest.mark.parametrize(
    "status", [SessionStatus.SCHEDULING, SessionStatus.CALENDAR, SessionStatus.CLOSED]
)
def test_poza_etapem_4_nie_da_sie_odpowiadac(db, dostepnosc, status):
    biezace = availability.current_idea_id(dostepnosc)
    dostepnosc.status = status.value
    db.commit()

    with pytest.raises(AvailabilityError, match="nie jest aktywny"):
        availability.answer(db, dostepnosc, osoba(dostepnosc, "Ania"), biezace, "WANT")


# ── zestawienie dla etapu 5 ─────────────────────────────────────────────────


def test_podsumowanie_ma_imiona_przy_odpowiedziach(db, dostepnosc):
    """Kalendarz ma pokazywać, kto na co przyjdzie."""
    biezace = availability.current_idea_id(dostepnosc)
    availability.answer(db, dostepnosc, osoba(dostepnosc, "Ania"), biezace, "WANT")
    availability.answer(db, dostepnosc, osoba(dostepnosc, "Bartek"), biezace, "ABSOLUTELY_NOT")

    pozycja = next(p for p in availability.summary(db, dostepnosc) if p["ideaId"] == biezace)

    assert pozycja["people"]["WANT"] == ["Ania"]
    assert pozycja["people"]["ABSOLUTELY_NOT"] == ["Bartek"]
    assert pozycja["answered"] == 2


def test_podsumowanie_sortuje_po_dacie(db, dostepnosc):
    tytuly = [p["title"] for p in availability.summary(db, dostepnosc)]
    assert tytuly == ["Kajaki", "Kino", "Urodziny babci"]


def test_podsumowanie_zawiera_termin(db, dostepnosc):
    pozycja = availability.summary(db, dostepnosc)[0]
    assert pozycja["schedule"]["label"].startswith("sobota") or pozycja["schedule"]["label"]


# ── snapshot ────────────────────────────────────────────────────────────────


def test_gosc_nie_widzi_rozkladu_odpowiedzi(db, dostepnosc):
    """„Sześć osób już chce" przesądzałoby kolejne deklaracje."""
    from app.snapshots import build_snapshot

    biezace = availability.current_idea_id(dostepnosc)
    availability.answer(db, dostepnosc, osoba(dostepnosc, "Bartek"), biezace, "WANT")

    snap = build_snapshot(db, dostepnosc, osoba(dostepnosc, "Ania"))

    assert "tally" not in snap["availability"]
    assert snap["availability"]["current"]["ideaId"] == biezace
    assert snap["availability"]["yourAnswer"] is None
    assert snap["availability"]["canAnswer"] is True


def test_gosc_widzi_wlasna_odpowiedz(db, dostepnosc):
    from app.snapshots import build_snapshot

    biezace = availability.current_idea_id(dostepnosc)
    ania = osoba(dostepnosc, "Ania")
    availability.answer(db, dostepnosc, ania, biezace, "CAN")

    snap = build_snapshot(db, dostepnosc, ania)
    assert snap["availability"]["yourAnswer"] == "CAN"


def test_host_widzi_rozklad_i_postep(db, dostepnosc):
    from app.snapshots import build_snapshot

    biezace = availability.current_idea_id(dostepnosc)
    availability.answer(db, dostepnosc, osoba(dostepnosc, "Ania"), biezace, "WANT")

    snap = build_snapshot(db, dostepnosc, osoba(dostepnosc, "Ekran"))

    assert snap["availability"]["tally"]["WANT"] == 1
    assert snap["availability"]["answered"] == 1
    assert snap["availability"]["expected"] == 2, "mianownik to tylko głosujący goście"
    assert snap["availability"]["canAnswer"] is False


def test_wydarzenie_zawiera_termin(db, dostepnosc):
    """Z opisu: host wyświetla wydarzenie, opis oraz datę."""
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, dostepnosc, osoba(dostepnosc, "Ania"))
    assert snap["availability"]["current"]["schedule"]["label"]


def test_widz_widzi_rozklad(db, dostepnosc):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, dostepnosc, None)
    assert "tally" in snap["availability"]
