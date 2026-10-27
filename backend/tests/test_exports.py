"""Eksport wyników — PDF, ICS, CSV i lista odrzuconych."""

from datetime import date

import pytest

from app import assignments, availability, exports, ideas, schedules, swipes
from app.state_machine import SessionStatus


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


def pomysl(db, session, tytul):
    return next(i for i in ideas.list_ideas(db, session.id) if i.title == tytul)


@pytest.fixture()
def gotowa(db, sample_session):
    """Sesja po całym przebiegu: coś przeszło, coś odpadło na każdym etapie."""
    s = sample_session
    ania, bartek = osoba(s, "Ania"), osoba(s, "Bartek")
    ekran, admin = osoba(s, "Ekran"), osoba(s, "Admin")

    s.status = SessionStatus.COLLECTING.value
    db.commit()
    for tytul in ("Kajaki", "Kino", "Grill", "Nudny pomysł"):
        ideas.create_idea(db, s, ania, tytul, f"Opis: {tytul.lower()}")
    ideas.create_idea(db, s, admin, "Urodziny babci", is_special=True)

    s.status = SessionStatus.SWIPING.value
    db.commit()
    # Kino odrzucone przez hosta, "Nudny pomysł" bez rozstrzygnięcia.
    swipes.decide(db, s, ekran, pomysl(db, s, "Kajaki").id, True)
    swipes.decide(db, s, ekran, pomysl(db, s, "Kino").id, False)
    swipes.decide(db, s, ekran, pomysl(db, s, "Grill").id, True)

    s.status = SessionStatus.SCHEDULING.value
    db.commit()
    schedules.set_schedule(db, s, ekran, pomysl(db, s, "Kajaki").id, "EXACT_DATE", date="2026-03-14")
    schedules.set_schedule(
        db, s, ekran, pomysl(db, s, "Grill").id, "RANGE",
        date_from="2026-03-28", date_to="2026-04-05",
    )
    schedules.set_schedule(
        db, s, ekran, pomysl(db, s, "Urodziny babci").id, "MONTH", year=2026, month=5
    )

    s.status = SessionStatus.AVAILABILITY.value
    db.commit()
    availability.build_order(db, s)
    # Odpowiadamy na pierwsze wydarzenie z rundy.
    biezace = availability.current_idea_id(s)
    availability.answer(db, s, ania, biezace, "WANT")
    availability.answer(db, s, bartek, biezace, "ABSOLUTELY_NOT")

    s.status = SessionStatus.ASSIGNMENT.value
    db.commit()
    # Grill odrzucony dopiero tutaj.
    for idea in assignments.order(db, s):
        assignments.decide(db, s, ekran, idea.id, idea.title != "Grill")
    assignments.add_person(db, s, ekran, pomysl(db, s, "Kajaki").id, "Ania", ania.id)
    assignments.add_person(db, s, ekran, pomysl(db, s, "Kajaki").id, "Marek z pracy")

    s.status = SessionStatus.CALENDAR.value
    db.commit()
    return s


# ── odrzucone ───────────────────────────────────────────────────────────────


def test_odrzucone_z_kazdego_etapu(db, gotowa):
    """„Nieważne na którym etapie odrzucone" — zbieramy wszystko."""
    wynik = {idea.title: powod for idea, powod in assignments.rejected_ideas(db, gotowa.id)}

    assert wynik["Kino"] == "odrzucony przy wyborze"
    assert wynik["Nudny pomysł"] == "nierozstrzygnięty przy wyborze"
    assert wynik["Grill"] == "odrzucony przy przydziale"
    assert "Kajaki" not in wynik, "przyjęte nie może być na liście odrzuconych"
    assert "Urodziny babci" not in wynik


def test_wpis_ustalony_moze_odpasc_tylko_w_etapie_5(db, gotowa):
    """Etapu 2 nie przechodzi, więc nie może zostać tam odrzucony."""
    ekran = osoba(gotowa, "Ekran")
    gotowa.status = SessionStatus.ASSIGNMENT.value
    db.commit()
    assignments.decide(db, gotowa, ekran, pomysl(db, gotowa, "Urodziny babci").id, False)
    gotowa.status = SessionStatus.CALENDAR.value
    db.commit()

    wynik = {idea.title: powod for idea, powod in assignments.rejected_ideas(db, gotowa.id)}
    assert wynik["Urodziny babci"] == "odrzucony przy przydziale"


def test_txt_ma_wpis_i_opis(db, gotowa):
    """Format prosty do bólu: tytuł, powód, opis."""
    tekst = exports.rejected_txt(db, gotowa).decode("utf-8")

    assert "Kino" in tekst
    assert "Opis: kino" in tekst
    assert "odrzucony przy wyborze" in tekst
    assert "Kajaki" not in tekst


def test_txt_gdy_nic_nie_odpadlo(db, sample_session):
    tekst = exports.rejected_txt(db, sample_session).decode("utf-8")
    assert "Nic nie odpadło" in tekst


def test_rejected_pdf_to_prawdziwy_pdf(db, gotowa):
    dane = exports.rejected_pdf(db, gotowa)

    assert dane.startswith(b"%PDF-")
    assert len(dane) > 1000


def test_css_nie_jest_escapowany(db, gotowa):
    """Regresja: Jinja escapowała wstrzykiwany arkusz.

    `font-family: "DejaVu Sans"` zamieniało się w `&#34;DejaVu Sans&#34;`,
    reguła przestawała obowiązywać i PDF wychodził innym krojem — mimo że
    plik generował się bez żadnego błędu.
    """
    html = exports.rejected_html(db, gotowa)

    assert '"DejaVu Sans"' in html
    assert "&#34;" not in html


# ── kalendarz ───────────────────────────────────────────────────────────────


def test_pdf_kalendarza_to_prawdziwy_pdf(db, gotowa):
    dane = exports.calendar_pdf(db, gotowa, today=date(2026, 3, 1))

    assert dane.startswith(b"%PDF-")
    assert len(dane) > 2000


def test_html_kalendarza_zawiera_plan(db, gotowa):
    """Szablon czyta ten sam układ, co ekran — sprawdzamy, że go użył."""
    html = exports.calendar_html(db, gotowa, today=date(2026, 3, 1))

    assert "Kajaki" in html
    assert "marzec 2026" in html
    assert "Marek z pracy" in html, "przypisane osoby muszą być w wydruku"
    assert "Grill" not in html, "odrzucone nie wchodzi do kalendarza"
    assert "grid-column" in html, "pasy ustawione na siatce policzonej przez serwer"


def test_uklad_lista_pomija_siatke(db, gotowa):
    z_siatka = exports.calendar_html(db, gotowa, layout="calendar", today=date(2026, 3, 1))
    sama_lista = exports.calendar_html(db, gotowa, layout="list", today=date(2026, 3, 1))

    assert "grid-column" in z_siatka
    assert "grid-column" not in sama_lista
    assert "Kajaki" in sama_lista, "lista wydarzeń zostaje"


# ── ICS ─────────────────────────────────────────────────────────────────────


def test_ics_ma_wydarzenia(db, gotowa):
    tekst = exports.calendar_ics(db, gotowa).decode("utf-8")

    assert "BEGIN:VCALENDAR" in tekst
    assert "SUMMARY:Kajaki" in tekst
    assert "Grill" not in tekst, "odrzucone nie trafia do kalendarza telefonu"


def test_ics_ma_koniec_wylaczny(db, gotowa):
    """W ICS koniec całodniowego wydarzenia to dzień PO ostatnim.

    Bez tego jednodniowe wydarzenie zniknęłoby z kalendarza telefonu.
    """
    tekst = exports.calendar_ics(db, gotowa).decode("utf-8")

    assert "DTSTART;VALUE=DATE:20260314" in tekst
    assert "DTEND;VALUE=DATE:20260315" in tekst


def test_ics_opisuje_termin_orientacyjny(db, gotowa):
    """Miesiąc trafia do kalendarza jako pas — warto powiedzieć, że to zgrubne."""
    tekst = exports.calendar_ics(db, gotowa).decode("utf-8")
    assert "orientacyjny" in tekst


def test_ics_ma_przypisane_osoby_w_opisie(db, gotowa):
    tekst = exports.calendar_ics(db, gotowa).decode("utf-8")
    assert "Marek z pracy" in tekst.replace("\r\n ", "")


# ── CSV ─────────────────────────────────────────────────────────────────────


def test_csv_ma_naglowek_i_wiersze(db, gotowa):
    dane = exports.calendar_csv(db, gotowa)

    assert dane.startswith(b"\xef\xbb\xbf"), "BOM dla Excela na Windowsie"
    tekst = dane.decode("utf-8-sig")
    assert tekst.splitlines()[0].startswith("Wydarzenie;Termin")
    assert "Kajaki" in tekst
    assert "Grill" not in tekst


# ── nazwy plików ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "nazwa,oczekiwane",
    [
        # Polskie znaki zostają — Content-Disposition radzi sobie z nimi
        # przez filename* z kodowaniem UTF-8.
        ("Plany na wiosnę", "Plany-na-wiosnę-plan.pdf"),
        ("a/b\\c", "abc-plan.pdf"),
        ("   ", "sesja-plan.pdf"),
    ],
)
def test_nazwa_pliku_jest_bezpieczna(nazwa, oczekiwane):
    assert exports.safe_filename(nazwa, "plan.pdf") == oczekiwane
