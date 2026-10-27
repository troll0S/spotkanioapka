"""Etap 5 — przydział wykonawców i ostatnia brama przed kalendarzem."""

import pytest

from app import assignments, availability, ideas, schedules, swipes
from app.assignments import AssignmentError
from app.state_machine import SessionStatus


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


def pomysl(db, session, tytul):
    return next(i for i in ideas.list_ideas(db, session.id) if i.title == tytul)


@pytest.fixture()
def przydzial(db, sample_session):
    """Sesja na etapie 5: trzy wydarzenia z terminami i deklaracjami."""
    sample_session.status = SessionStatus.COLLECTING.value
    db.commit()
    ania = osoba(sample_session, "Ania")
    for tytul in ("Kajaki", "Kino", "Wyjazd"):
        ideas.create_idea(db, sample_session, ania, tytul)

    sample_session.status = SessionStatus.SWIPING.value
    db.commit()
    ekran = osoba(sample_session, "Ekran")
    for tytul in ("Kajaki", "Kino", "Wyjazd"):
        swipes.decide(db, sample_session, ekran, pomysl(db, sample_session, tytul).id, True)

    sample_session.status = SessionStatus.SCHEDULING.value
    db.commit()
    for numer, tytul in enumerate(("Wyjazd", "Kino", "Kajaki"), start=1):
        schedules.set_schedule(
            db, sample_session, ekran, pomysl(db, sample_session, tytul).id,
            "EXACT_DATE", date=f"2026-0{numer}-15",
        )

    sample_session.status = SessionStatus.AVAILABILITY.value
    db.commit()
    availability.build_order(db, sample_session)
    biezace = availability.current_idea_id(sample_session)
    availability.answer(db, sample_session, ania, biezace, "WANT")
    availability.answer(db, sample_session, osoba(sample_session, "Bartek"), biezace, "CAN")

    sample_session.status = SessionStatus.ASSIGNMENT.value
    db.commit()
    return sample_session


# ── kolejność ───────────────────────────────────────────────────────────────


def test_kolejnosc_jest_chronologiczna(db, przydzial):
    """Inaczej niż w etapie 4 — tu nikt nie głosuje, więc losowość nie ma sensu."""
    tytuly = [i.title for i in assignments.order(db, przydzial)]
    assert tytuly == ["Wyjazd", "Kino", "Kajaki"]


def test_host_przechodzi_i_wraca(db, przydzial):
    ekran = osoba(przydzial, "Ekran")

    assignments.move(db, przydzial, ekran, 1)
    assert assignments.current(db, przydzial).title == "Kino"

    assignments.move(db, przydzial, ekran, -1)
    assert assignments.current(db, przydzial).title == "Wyjazd"


def test_nie_da_sie_wyjsc_poza_zakres(db, przydzial):
    ekran = osoba(przydzial, "Ekran")
    with pytest.raises(AssignmentError, match="pierwsze"):
        assignments.move(db, przydzial, ekran, -1)


def test_gosc_nie_steruje(db, przydzial):
    with pytest.raises(AssignmentError, match="prowadzący"):
        assignments.move(db, przydzial, osoba(przydzial, "Ania"), 1)


# ── przypisywanie osób ──────────────────────────────────────────────────────


def test_host_przypisuje_uczestnika(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")
    ania = osoba(przydzial, "Ania")

    wpis = assignments.add_person(
        db, przydzial, osoba(przydzial, "Ekran"), wyjazd.id, "cokolwiek",
        linked_participant_id=ania.id,
    )

    assert wpis.name == "Ania", "imię bierzemy z uczestnika, nie z pola"
    assert wpis.participant_id == ania.id


def test_host_przypisuje_kogos_spoza_sesji(db, przydzial):
    """Sedno etapu: wykonawcą może być ktoś, kogo w sesji nie było."""
    wyjazd = pomysl(db, przydzial, "Wyjazd")

    wpis = assignments.add_person(
        db, przydzial, osoba(przydzial, "Ekran"), wyjazd.id, "  Marek z pracy  "
    )

    assert wpis.name == "Marek z pracy"
    assert wpis.participant_id is None


def test_kilka_osob_przy_jednym_wydarzeniu(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")
    ekran = osoba(przydzial, "Ekran")

    for imie in ("Ania", "Marek", "tata"):
        assignments.add_person(db, przydzial, ekran, wyjazd.id, imie)

    assert [w.name for w in assignments.assignments_for(db, wyjazd.id)] == [
        "Ania", "Marek", "tata",
    ]


def test_ta_sama_osoba_nie_dwa_razy(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")
    ekran = osoba(przydzial, "Ekran")
    assignments.add_person(db, przydzial, ekran, wyjazd.id, "Marek")

    with pytest.raises(AssignmentError, match="już przypisany"):
        assignments.add_person(db, przydzial, ekran, wyjazd.id, "marek")


def test_pusta_nazwa_odrzucona(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")

    with pytest.raises(AssignmentError, match="Podaj imię"):
        assignments.add_person(db, przydzial, osoba(przydzial, "Ekran"), wyjazd.id, "   ")


def test_da_sie_usunac_przypisanie(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")
    ekran = osoba(przydzial, "Ekran")
    wpis = assignments.add_person(db, przydzial, ekran, wyjazd.id, "Marek")

    assignments.remove_person(db, przydzial, ekran, wpis.id)

    assert assignments.assignments_for(db, wyjazd.id) == []


def test_gosc_nie_przypisuje(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")

    with pytest.raises(AssignmentError, match="prowadzący"):
        assignments.add_person(db, przydzial, osoba(przydzial, "Ania"), wyjazd.id, "Marek")


def test_admin_tez_nie_przypisuje(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")

    with pytest.raises(AssignmentError, match="prowadzący"):
        assignments.add_person(db, przydzial, osoba(przydzial, "Admin"), wyjazd.id, "Marek")


# ── zatwierdzanie i odrzucanie ──────────────────────────────────────────────


def test_zatwierdzone_trafia_do_kalendarza(db, przydzial):
    ekran = osoba(przydzial, "Ekran")
    for tytul in ("Wyjazd", "Kino", "Kajaki"):
        assignments.decide(db, przydzial, ekran, pomysl(db, przydzial, tytul).id, tytul != "Kino")

    tytuly = [i.title for i in assignments.confirmed_ideas(db, przydzial.id)]
    assert sorted(tytuly) == ["Kajaki", "Wyjazd"]


def test_odrzucone_znika_z_kalendarza(db, przydzial):
    from app import calendar_view

    ekran = osoba(przydzial, "Ekran")
    for tytul in ("Wyjazd", "Kino", "Kajaki"):
        assignments.decide(db, przydzial, ekran, pomysl(db, przydzial, tytul).id, tytul != "Kino")
    przydzial.status = SessionStatus.CALENDAR.value
    db.commit()

    dane = calendar_view.build(db, przydzial)
    assert [w["title"] for w in dane["events"]] == ["Wyjazd", "Kajaki"]


def test_host_moze_zmienic_zdanie(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")
    ekran = osoba(przydzial, "Ekran")

    assignments.decide(db, przydzial, ekran, wyjazd.id, True)
    assignments.decide(db, przydzial, ekran, wyjazd.id, False)

    assert assignments.plans(db, przydzial.id)[wyjazd.id] is False


def test_gosc_nie_rozstrzyga(db, przydzial):
    wyjazd = pomysl(db, przydzial, "Wyjazd")

    with pytest.raises(AssignmentError, match="prowadzący"):
        assignments.decide(db, przydzial, osoba(przydzial, "Ania"), wyjazd.id, True)


def test_nierozstrzygniete_sa_wyliczane(db, przydzial):
    ekran = osoba(przydzial, "Ekran")
    assert len(assignments.undecided(db, przydzial)) == 3

    assignments.decide(db, przydzial, ekran, pomysl(db, przydzial, "Wyjazd").id, True)
    assert [i.title for i in assignments.undecided(db, przydzial)] == ["Kino", "Kajaki"]


@pytest.mark.parametrize(
    "status", [SessionStatus.AVAILABILITY, SessionStatus.CALENDAR, SessionStatus.CLOSED]
)
def test_poza_etapem_5_nie_da_sie_przypisywac(db, przydzial, status):
    wyjazd = pomysl(db, przydzial, "Wyjazd")
    przydzial.status = status.value
    db.commit()

    with pytest.raises(AssignmentError, match="nie jest aktywny"):
        assignments.add_person(db, przydzial, osoba(przydzial, "Ekran"), wyjazd.id, "Marek")


# ── snapshot ────────────────────────────────────────────────────────────────


def test_etap_5_odslania_kto_jak_odpowiedzial(db, przydzial):
    """To jest moment ujawnienia wyników — wcześniej trzymaliśmy je w ukryciu."""
    from app.snapshots import build_snapshot

    z_odpowiedziami = availability.order(przydzial)[0]
    przydzial.assignment_index = [
        i.id for i in assignments.order(db, przydzial)
    ].index(z_odpowiedziami)
    db.commit()

    snap = build_snapshot(db, przydzial, osoba(przydzial, "Ania"))
    biezace = snap["assignment"]["current"]

    assert biezace["people"]["WANT"] == ["Ania"]
    assert biezace["people"]["CAN"] == ["Bartek"]
    assert biezace["schedule"]["label"]


def test_uczestnik_widzi_to_samo_ale_bez_sterowania(db, przydzial):
    from app.snapshots import build_snapshot

    snap_host = build_snapshot(db, przydzial, osoba(przydzial, "Ekran"))
    snap_gosc = build_snapshot(db, przydzial, osoba(przydzial, "Ania"))

    assert snap_host["assignment"]["canEdit"] is True
    assert snap_gosc["assignment"]["canEdit"] is False
    assert snap_gosc["assignment"]["current"]["title"] == snap_host["assignment"]["current"]["title"]


def test_snapshot_ma_liste_uczestnikow_do_szybkiego_dodania(db, przydzial):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, przydzial, osoba(przydzial, "Ekran"))
    imiona = {p["displayName"] for p in snap["assignment"]["roster"]}

    assert imiona == {"Ania", "Bartek"}, "tylko głosujący goście"


def test_snapshot_pokazuje_przypisanych_i_decyzje(db, przydzial):
    from app.snapshots import build_snapshot

    wyjazd = assignments.current(db, przydzial)
    ekran = osoba(przydzial, "Ekran")
    assignments.add_person(db, przydzial, ekran, wyjazd.id, "Marek z pracy")
    assignments.decide(db, przydzial, ekran, wyjazd.id, True)

    snap = build_snapshot(db, przydzial, ekran)
    biezace = snap["assignment"]["current"]

    assert biezace["assigned"][0]["name"] == "Marek z pracy"
    assert biezace["assigned"][0]["isParticipant"] is False
    assert biezace["decision"] is True
    assert snap["assignment"]["confirmed"] == 1


def test_kalendarz_pokazuje_przypisane_osoby(db, przydzial):
    from app.snapshots import build_snapshot

    ekran = osoba(przydzial, "Ekran")
    wyjazd = pomysl(db, przydzial, "Wyjazd")
    assignments.add_person(db, przydzial, ekran, wyjazd.id, "Marek")
    for tytul in ("Wyjazd", "Kino", "Kajaki"):
        assignments.decide(db, przydzial, ekran, pomysl(db, przydzial, tytul).id, True)

    przydzial.status = SessionStatus.CALENDAR.value
    db.commit()

    snap = build_snapshot(db, przydzial, ekran)
    pozycja = next(w for w in snap["calendar"]["events"] if w["title"] == "Wyjazd")

    assert [o["name"] for o in pozycja["assigned"]] == ["Marek"]
