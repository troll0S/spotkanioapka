"""Etap 5 — układ kalendarza liczony po stronie serwera.

Ta sama struktura nakarmi w K7 szablon PDF-a, więc testujemy dane, nie wygląd.
"""

from datetime import date

import pytest

from app import assignments, availability, calendar_view, ideas, schedules, swipes
from app.state_machine import SessionStatus


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


def pomysl(db, session, tytul):
    return next(i for i in ideas.list_ideas(db, session.id) if i.title == tytul)


@pytest.fixture()
def kalendarz(db, sample_session):
    """Sesja na etapie 5 z trzema wydarzeniami o różnych rodzajach terminu."""
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
    schedules.set_schedule(
        db, sample_session, ekran, pomysl(db, sample_session, "Kajaki").id,
        "EXACT_DATE", date="2026-03-14",
    )
    schedules.set_schedule(
        db, sample_session, ekran, pomysl(db, sample_session, "Kino").id,
        "WEEK", date="2026-03-18",
    )
    schedules.set_schedule(
        db, sample_session, ekran, pomysl(db, sample_session, "Wyjazd").id,
        "RANGE", date_from="2026-03-28", date_to="2026-04-05",
    )

    sample_session.status = SessionStatus.AVAILABILITY.value
    db.commit()
    availability.build_order(db, sample_session)
    return sample_session


def zatwierdz_wszystko(db, session):
    """Etap 5 — do kalendarza wchodzi tylko to, co host zatwierdził."""
    poprzedni = session.status
    session.status = SessionStatus.ASSIGNMENT.value
    db.commit()
    ekran = osoba(session, "Ekran")
    for idea in assignments.order(db, session):
        assignments.decide(db, session, ekran, idea.id, True)
    session.status = poprzedni
    db.commit()


def widok(db, session):
    zatwierdz_wszystko(db, session)
    return calendar_view.build(db, session, today=date(2026, 3, 1))


# ── siatka ──────────────────────────────────────────────────────────────────


def test_kalendarz_obejmuje_miesiace_z_wydarzeniami(db, kalendarz):
    dane = widok(db, kalendarz)

    assert [(m["year"], m["month"]) for m in dane["months"]] == [(2026, 3), (2026, 4)]
    assert dane["months"][0]["label"] == "marzec 2026"


def test_tydzien_ma_siedem_dni_od_poniedzialku(db, kalendarz):
    tydzien = widok(db, kalendarz)["months"][0]["weeks"][0]

    assert len(tydzien["days"]) == 7
    assert date.fromisoformat(tydzien["days"][0]["date"]).weekday() == 0
    assert tydzien["days"][5]["isWeekend"] is True
    assert tydzien["days"][6]["isWeekend"] is True


def test_dni_z_sasiednich_miesiecy_sa_oznaczone(db, kalendarz):
    marzec = widok(db, kalendarz)["months"][0]
    pierwszy = marzec["weeks"][0]["days"][0]

    # 1 marca 2026 to niedziela, więc pierwszy tydzień zaczyna się w lutym.
    assert pierwszy["inMonth"] is False


def test_dzisiaj_jest_oznaczone(db, kalendarz):
    dane = widok(db, kalendarz)
    dzisiejsze = [
        d
        for m in dane["months"]
        for t in m["weeks"]
        for d in t["days"]
        if d["isToday"]
    ]
    assert {d["date"] for d in dzisiejsze} == {"2026-03-01"}


# ── pasy wydarzeń ───────────────────────────────────────────────────────────


def _pasy(dane, tytul):
    return [
        (m["month"], nr, pas)
        for m in dane["months"]
        for nr, t in enumerate(m["weeks"])
        for pas in t["bands"]
        if pas["title"] == tytul
    ]


def test_dokladna_data_to_pas_jednodniowy(db, kalendarz):
    pasy = _pasy(widok(db, kalendarz), "Kajaki")

    assert len(pasy) == 1
    _, _, pas = pasy[0]
    assert pas["span"] == 1
    assert pas["continuesLeft"] is False
    assert pas["continuesRight"] is False


def test_tydzien_to_pas_przez_siedem_dni(db, kalendarz):
    """Z ARCHITEKTURY: wydarzenia rozmyte mają być pasem, nie punktem."""
    pasy = _pasy(widok(db, kalendarz), "Kino")

    assert len(pasy) == 1
    _, _, pas = pasy[0]
    assert pas["startCol"] == 0
    assert pas["span"] == 7


def test_przedzial_przez_granice_miesiaca_jest_ciety_na_tygodnie(db, kalendarz):
    """28.03–05.04 przechodzi przez tydzień i przez granicę miesiąca."""
    pasy = _pasy(widok(db, kalendarz), "Wyjazd")

    assert len(pasy) > 1, "pas musi być pocięty na kawałki tygodniowe"

    # Kawałek, który biegnie dalej w prawo, musi to sygnalizować.
    assert any(pas["continuesRight"] for _, _, pas in pasy)
    assert any(pas["continuesLeft"] for _, _, pas in pasy)

    # Żaden kawałek nie wychodzi poza tydzień.
    assert all(pas["startCol"] + pas["span"] <= 7 for _, _, pas in pasy)


def test_nachodzace_wydarzenia_dostaja_osobne_pasy(db, kalendarz):
    """Kajaki (14.03) leżą w tygodniu 9–15.03, Kino w 16–22.03 — bez kolizji.
    Sprawdzamy tydzień, w którym naprawdę coś się nakłada."""
    ekran = osoba(kalendarz, "Ekran")
    kalendarz.status = SessionStatus.SCHEDULING.value
    db.commit()
    schedules.set_schedule(
        db, kalendarz, ekran, pomysl(db, kalendarz, "Kino").id,
        "RANGE", date_from="2026-03-13", date_to="2026-03-15",
    )
    kalendarz.status = SessionStatus.CALENDAR.value
    db.commit()

    dane = widok(db, kalendarz)
    tydzien = next(
        t
        for m in dane["months"]
        for t in m["weeks"]
        if len(t["bands"]) >= 2 and any(b["title"] == "Kajaki" for b in t["bands"])
    )

    pasy = {b["title"]: b["lane"] for b in tydzien["bands"]}
    assert pasy["Kajaki"] != pasy["Kino"], "nakładające się pasy nie mogą być w jednym rzędzie"
    assert tydzien["lanes"] >= 2


def test_kolor_wydarzenia_jest_staly(db, kalendarz):
    """Ten sam odcień w kalendarzu, na liście i w przyszłym PDF-ie."""
    dane = widok(db, kalendarz)
    indeksy = {
        pas["title"]: pas["colorIndex"]
        for m in dane["months"]
        for t in m["weeks"]
        for pas in t["bands"]
    }
    for m in dane["months"]:
        for t in m["weeks"]:
            for pas in t["bands"]:
                assert pas["colorIndex"] == indeksy[pas["title"]]


# ── kolizje ─────────────────────────────────────────────────────────────────


def test_dwa_wydarzenia_tego_samego_dnia_to_kolizja(db, kalendarz):
    ekran = osoba(kalendarz, "Ekran")
    kalendarz.status = SessionStatus.SCHEDULING.value
    db.commit()
    schedules.set_schedule(
        db, kalendarz, ekran, pomysl(db, kalendarz, "Kino").id,
        "EXACT_DATE", date="2026-03-14",
    )
    kalendarz.status = SessionStatus.CALENDAR.value
    db.commit()

    kolizje = widok(db, kalendarz)["conflicts"]
    tytuly = {frozenset((k["a"]["title"], k["b"]["title"])) for k in kolizje}

    assert frozenset(("Kajaki", "Kino")) in tytuly


def test_dwa_okna_miesieczne_to_nie_kolizja(db, kalendarz):
    """„Gdzieś w marcu" i „gdzieś w marcu" mogą spokojnie współistnieć.

    Gdyby to liczyć jako kolizję, ekran zalałyby ostrzeżenia do zignorowania.
    """
    ekran = osoba(kalendarz, "Ekran")
    kalendarz.status = SessionStatus.SCHEDULING.value
    db.commit()
    for tytul in ("Kajaki", "Kino", "Wyjazd"):
        schedules.set_schedule(
            db, kalendarz, ekran, pomysl(db, kalendarz, tytul).id,
            "MONTH", year=2026, month=3,
        )
    kalendarz.status = SessionStatus.CALENDAR.value
    db.commit()

    assert widok(db, kalendarz)["conflicts"] == []


# ── ostrzeżenia ─────────────────────────────────────────────────────────────


def test_brak_odpowiedzi_jest_oznaczony(db, kalendarz):
    dane = widok(db, kalendarz)
    assert all(w["level"] == "empty" for w in dane["events"])


def test_silny_sprzeciw_jest_wyrozniony(db, kalendarz):
    """Sygnał dla człowieka — system niczego nie odrzuca."""
    biezace = availability.current_idea_id(kalendarz)
    availability.answer(db, kalendarz, osoba(kalendarz, "Ania"), biezace, "ABSOLUTELY_NOT")
    availability.answer(db, kalendarz, osoba(kalendarz, "Bartek"), biezace, "WANT")

    kalendarz.status = SessionStatus.CALENDAR.value
    db.commit()

    pozycja = next(w for w in widok(db, kalendarz)["events"] if w["ideaId"] == biezace)
    assert pozycja["level"] == "blocked", "połowa na absolutnie nie"
    assert pozycja["attending"] == 1


def test_komplet_zgod_bez_ostrzezenia(db, kalendarz):
    biezace = availability.current_idea_id(kalendarz)
    availability.answer(db, kalendarz, osoba(kalendarz, "Ania"), biezace, "WANT")
    availability.answer(db, kalendarz, osoba(kalendarz, "Bartek"), biezace, "CAN")

    kalendarz.status = SessionStatus.CALENDAR.value
    db.commit()

    pozycja = next(w for w in widok(db, kalendarz)["events"] if w["ideaId"] == biezace)
    assert pozycja["level"] == "ok"
    assert pozycja["attending"] == 2


# ── snapshot ────────────────────────────────────────────────────────────────


def test_na_etapie_6_wszyscy_widza_to_samo(db, kalendarz):
    """Głosowanie się skończyło — nie ma już czego ukrywać przed uczestnikami."""
    from app.snapshots import build_snapshot

    zatwierdz_wszystko(db, kalendarz)
    kalendarz.status = SessionStatus.CALENDAR.value
    db.commit()

    for widz in (
        osoba(kalendarz, "Ekran"),
        osoba(kalendarz, "Ania"),
        osoba(kalendarz, "Admin"),
        None,
    ):
        snap = build_snapshot(db, kalendarz, widz)
        assert len(snap["calendar"]["events"]) == 3
        assert len(snap["calendar"]["months"]) == 2


def test_lista_wydarzen_ma_imiona(db, kalendarz):
    """Pod kalendarzem ma być lista z osobami — wprost z opisu."""
    from app.snapshots import build_snapshot

    biezace = availability.current_idea_id(kalendarz)
    availability.answer(db, kalendarz, osoba(kalendarz, "Ania"), biezace, "WANT")
    zatwierdz_wszystko(db, kalendarz)
    kalendarz.status = SessionStatus.CALENDAR.value
    db.commit()

    snap = build_snapshot(db, kalendarz, osoba(kalendarz, "Ekran"))
    pozycja = next(w for w in snap["calendar"]["events"] if w["ideaId"] == biezace)

    assert pozycja["people"]["WANT"] == ["Ania"]
    assert pozycja["schedule"]["label"]
