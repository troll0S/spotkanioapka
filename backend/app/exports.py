"""Eksport wyników sesji.

Cztery formaty, z których każdy odpowiada na inne pytanie:

* **PDF** — to, co można wydrukować i powiesić na lodówce.
* **ICS** — ⭐ jedno kliknięcie i wydarzenia lądują w kalendarzu telefonu.
  Dla uczestnika to najbardziej użyteczny plik z całej czwórki.
* **CSV** — dla kogoś, kto chce to wrzucić do arkusza.
* **TXT** — lista odrzuconych, bez żadnej oprawy.

PDF składamy z HTML-a i CSS-a przez WeasyPrint, a **układ kalendarza bierzemy
gotowy z `calendar_view`** — tego samego, który karmi ekran w przeglądarce.
To była cała stawka decyzji z K6: rozkładanie wydarzeń na siatkę tygodni
istnieje w jednym miejscu, więc wydruk i ekran nie mają jak się rozjechać.
"""

import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from sqlalchemy.orm import Session as DbSession

from . import assignments, availability, calendar_view
from .models import Session

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)

#: Stała kolejność odpowiedzi we wszystkich eksportach.
ANSWER_ORDER = [(odp.value, etykieta) for odp, etykieta in availability.ANSWER_LABELS.items()]


def _css() -> Markup:
    """Arkusz stylów wstrzykiwany do szablonu.

    `Markup` jest tu konieczne. Bez niego Jinja potraktuje CSS jak tekst
    i zamieni cudzysłowy na encje — `font-family: "DejaVu Sans"` stanie się
    `font-family: &#34;DejaVu Sans&#34;`, reguła przestanie obowiązywać,
    a PDF po cichu wyjdzie innym krojem. Objaw jest podstępny, bo plik
    nadal się generuje i wygląda poprawnie.
    """
    return Markup((TEMPLATES_DIR / "base.css").read_text(encoding="utf-8"))


def _stamp(today: date | None) -> str:
    return (today or date.today()).strftime("%d.%m.%Y")


def safe_filename(name: str, suffix: str) -> str:
    """Nazwa pliku bezpieczna dla przeglądarki i systemu plików.

    Polskie znaki zostają — nagłówek Content-Disposition radzi sobie z nimi
    przez `filename*`. Wycinamy tylko to, co potrafi zepsuć ścieżkę.
    """
    czyste = "".join(z for z in name if z.isalnum() or z in " -_").strip()
    czyste = czyste.replace(" ", "-") or "sesja"
    return f"{czyste[:60]}-{suffix}"


# ── kalendarz ───────────────────────────────────────────────────────────────


def calendar_html(
    db: DbSession, session: Session, layout: str = "calendar", today: date | None = None
) -> str:
    dane = calendar_view.build(db, session, today=today)
    return _env.get_template("calendar.html").render(
        session={"name": session.name, "code": session.code},
        calendar=dane,
        layout=layout,
        css=_css(),
        answer_order=ANSWER_ORDER,
        generated=_stamp(today),
    )


def calendar_pdf(
    db: DbSession, session: Session, layout: str = "calendar", today: date | None = None
) -> bytes:
    # Import lokalny: WeasyPrint wciąga przy starcie biblioteki systemowe
    # i kilkaset milisekund. Aplikacja, która nigdy nie generuje PDF-a,
    # nie ma powodu tego płacić.
    from weasyprint import HTML

    html = calendar_html(db, session, layout, today)
    return HTML(string=html).write_pdf()


def calendar_ics(db: DbSession, session: Session) -> bytes:
    """Wydarzenia do kalendarza telefonu.

    Wszystko jest całodniowe — także dokładna data. Sesja ustala „którego
    dnia", nie „o której godzinie", więc wpisywanie sztucznej godziny
    zmyśliłoby informację, której nikt nie podał.
    """
    from icalendar import Calendar, Event

    kal = Calendar()
    kal.add("prodid", "-//Spotkaniooapka//PL")
    kal.add("version", "2.0")
    kal.add("x-wr-calname", session.name)

    zatwierdzone = assignments.confirmed_ideas(db, session.id)
    przypisania = assignments.assignments_by_idea(db, session.id)

    for pozycja in availability.summary(db, session, ideas_subset=zatwierdzone):
        if not pozycja["schedule"]:
            continue

        wydarzenie = Event()
        wydarzenie.add("summary", pozycja["title"])
        wydarzenie.add("uid", f"spotkanioapka-{session.code}-{pozycja['ideaId']}")

        od = date.fromisoformat(pozycja["schedule"]["dateFrom"])
        do = date.fromisoformat(pozycja["schedule"]["dateTo"])
        wydarzenie.add("dtstart", od)
        # W ICS koniec wydarzenia całodniowego jest wyłączny: dzień po
        # ostatnim. Bez tego jednodniowe wydarzenie zniknęłoby z kalendarza,
        # a wielodniowe skróciło się o dobę.
        wydarzenie.add("dtend", do + timedelta(days=1))
        wydarzenie.add("dtstamp", datetime.now())

        opis = []
        if pozycja["description"]:
            opis.append(pozycja["description"])
        osoby = [w.name for w in przypisania.get(pozycja["ideaId"], [])]
        if osoby:
            opis.append("Kto: " + ", ".join(osoby))
        if pozycja["schedule"]["kind"] != "EXACT_DATE":
            opis.append(f"Termin orientacyjny: {pozycja['schedule']['label']}")
        if opis:
            wydarzenie.add("description", "\n".join(opis))

        kal.add_component(wydarzenie)

    return kal.to_ical()


def calendar_csv(db: DbSession, session: Session) -> bytes:
    bufor = io.StringIO()
    zapis = csv.writer(bufor, delimiter=";")
    zapis.writerow(
        ["Wydarzenie", "Termin", "Od", "Do", "Opis", "Kto to zrobi", *[e for _, e in ANSWER_ORDER]]
    )

    zatwierdzone = assignments.confirmed_ideas(db, session.id)
    przypisania = assignments.assignments_by_idea(db, session.id)

    for pozycja in availability.summary(db, session, ideas_subset=zatwierdzone):
        termin = pozycja["schedule"] or {}
        zapis.writerow(
            [
                pozycja["title"],
                termin.get("label", ""),
                termin.get("dateFrom", ""),
                termin.get("dateTo", ""),
                pozycja["description"] or "",
                ", ".join(w.name for w in przypisania.get(pozycja["ideaId"], [])),
                *[pozycja["tally"].get(v, 0) for v, _ in ANSWER_ORDER],
            ]
        )

    # BOM, bo inaczej Excel na Windowsie pokaże polskie znaki jako krzaki.
    return bufor.getvalue().encode("utf-8-sig")


# ── odrzucone ───────────────────────────────────────────────────────────────


def _rejected_rows(db: DbSession, session: Session) -> list[dict]:
    return [
        {
            "title": idea.title,
            "description": idea.description,
            "isSpecial": idea.is_special,
            "reason": powod,
        }
        for idea, powod in assignments.rejected_ideas(db, session.id)
    ]


def rejected_html(db: DbSession, session: Session, today: date | None = None) -> str:
    return _env.get_template("rejected.html").render(
        session={"name": session.name, "code": session.code},
        rejected=_rejected_rows(db, session),
        css=_css(),
        generated=_stamp(today),
    )


def rejected_pdf(db: DbSession, session: Session, today: date | None = None) -> bytes:
    from weasyprint import HTML

    return HTML(string=rejected_html(db, session, today)).write_pdf()


def rejected_txt(db: DbSession, session: Session, today: date | None = None) -> bytes:
    """Ta sama treść bez żadnej oprawy — wpis, opis i tyle."""
    wiersze = [f"{session.name} — odrzucone pomysły", f"wygenerowano {_stamp(today)}", ""]

    odrzucone = _rejected_rows(db, session)
    if not odrzucone:
        wiersze.append("Nic nie odpadło — wszystko trafiło do planu.")
    else:
        for pozycja in odrzucone:
            wiersze.append(f"{pozycja['title']}  [{pozycja['reason']}]")
            if pozycja["description"]:
                wiersze.append(f"  {pozycja['description']}")
            wiersze.append("")

    return "\r\n".join(wiersze).encode("utf-8")
