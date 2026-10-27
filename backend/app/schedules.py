"""Logika etapu 3 — ustalanie terminów.

Cały etap dzieje się na urządzeniu hostującego, więc nie ma tu głosowania ani
wyścigów. Jest za to jedna rzecz warta uwagi: **normalizacja**.

Host wybiera termin na cztery sposoby — konkretny dzień, tydzień, przedział
albo miesiąc — ale zapisujemy zawsze to samo: parę dat `(od, do)` plus rodzaj
do wyświetlania. Dzięki temu kalendarz z etapu 5 i eksporty rysują jeden
kształt danych zamiast rozgałęziać się na cztery przypadki.
"""

import calendar
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import dates_pl, swipes
from .models import Idea, Participant, Role, Schedule, ScheduleKind, Session
from .state_machine import SessionStatus

#: Poza tym zakresem to prawie na pewno pomyłka przy wpisywaniu, a nie plan.
MIN_ROK = 2000
MAX_ROK = 2100


class ScheduleError(Exception):
    """Naruszenie reguł etapu 3 — komunikat jest przeznaczony dla użytkownika."""


# ── normalizacja czterech rodzajów terminu ──────────────────────────────────


def week_bounds(dzien: date) -> tuple[date, date]:
    """Poniedziałek i niedziela tygodnia, w którym leży podana data.

    Host wskazuje dowolny dzień, a my bierzemy z niego cały tydzień. To pewniej
    niż natywny wybór tygodnia w przeglądarce, którego Safari w ogóle nie zna,
    a Firefox obsługuje inaczej niż Chrome.
    """
    poniedzialek = dzien - timedelta(days=dzien.weekday())
    return poniedzialek, poniedzialek + timedelta(days=6)


def month_bounds(rok: int, miesiac: int) -> tuple[date, date]:
    ostatni = calendar.monthrange(rok, miesiac)[1]
    return date(rok, miesiac, 1), date(rok, miesiac, ostatni)


def normalize(kind: ScheduleKind, **pola) -> tuple[date, date, str]:
    """Zamienia wybór hosta na `(od, do, etykieta)`.

    To jedyne miejsce, które wie, czym różnią się cztery rodzaje terminu.
    Wszystko dalej widzi już tylko przedział.
    """
    if kind is ScheduleKind.EXACT_DATE:
        dzien = _wymagana_data(pola.get("date"), "date")
        return dzien, dzien, dates_pl.dokladna_data(dzien)

    if kind is ScheduleKind.WEEK:
        dzien = _wymagana_data(pola.get("date"), "date")
        od, do = week_bounds(dzien)
        return od, do, dates_pl.tydzien(od, do)

    if kind is ScheduleKind.RANGE:
        od = _wymagana_data(pola.get("date_from"), "date_from")
        do = _wymagana_data(pola.get("date_to"), "date_to")
        if do < od:
            raise ScheduleError("Koniec przedziału wypada przed jego początkiem.")
        return od, do, dates_pl.przedzial(od, do)

    if kind is ScheduleKind.MONTH:
        rok = _wymagana_liczba(pola.get("year"), "year")
        miesiac = _wymagana_liczba(pola.get("month"), "month")
        if not 1 <= miesiac <= 12:
            raise ScheduleError("Nie ma takiego miesiąca.")
        _sprawdz_rok(rok)
        od, do = month_bounds(rok, miesiac)
        return od, do, dates_pl.miesiac(od)

    raise ScheduleError("Nieznany rodzaj terminu.")


def _wymagana_data(wartosc, nazwa: str) -> date:
    if isinstance(wartosc, date):
        dzien = wartosc
    elif isinstance(wartosc, str) and wartosc:
        try:
            dzien = date.fromisoformat(wartosc)
        except ValueError:
            raise ScheduleError("Niepoprawna data.") from None
    else:
        raise ScheduleError(f"Brakuje daty ({nazwa}).")
    _sprawdz_rok(dzien.year)
    return dzien


def _wymagana_liczba(wartosc, nazwa: str) -> int:
    try:
        return int(wartosc)
    except (TypeError, ValueError):
        raise ScheduleError(f"Brakuje wartości ({nazwa}).") from None


def _sprawdz_rok(rok: int) -> None:
    if not MIN_ROK <= rok <= MAX_ROK:
        raise ScheduleError(f"Rok {rok} wygląda na pomyłkę.")


# ── operacje ────────────────────────────────────────────────────────────────


def _require_scheduling(session: Session) -> None:
    if session.status_enum is not SessionStatus.SCHEDULING:
        raise ScheduleError("Etap ustalania terminów nie jest aktywny.")


def _require_host(participant: Participant) -> None:
    # Wprost z opisu: „tu wszystko dzieje się na urządzeniu hostującym".
    if participant.role_enum is not Role.HOST:
        raise ScheduleError("Terminy ustala prowadzący.")


def _schedulable_idea(db: DbSession, session: Session, idea_id: int) -> Idea:
    idea = db.get(Idea, idea_id)
    if idea is None or idea.session_id != session.id:
        raise ScheduleError("Nie ma takiego pomysłu.")
    if idea not in swipes.accepted_ideas(db, session.id):
        raise ScheduleError("Ten pomysł nie przeszedł do etapu terminów.")
    return idea


def set_schedule(
    db: DbSession,
    session: Session,
    participant: Participant,
    idea_id: int,
    kind: str,
    **pola,
) -> Schedule:
    _require_scheduling(session)
    _require_host(participant)

    try:
        rodzaj = ScheduleKind(kind)
    except ValueError:
        raise ScheduleError("Nieznany rodzaj terminu.") from None

    idea = _schedulable_idea(db, session, idea_id)
    od, do, etykieta = normalize(rodzaj, **pola)

    termin = db.scalar(select(Schedule).where(Schedule.idea_id == idea.id))
    if termin is None:
        termin = Schedule(idea_id=idea.id)
        db.add(termin)

    termin.kind = rodzaj.value
    termin.date_from = od
    termin.date_to = do
    termin.label = etykieta
    db.commit()
    return termin


def clear_schedule(
    db: DbSession, session: Session, participant: Participant, idea_id: int
) -> None:
    _require_scheduling(session)
    _require_host(participant)

    idea = _schedulable_idea(db, session, idea_id)
    termin = db.scalar(select(Schedule).where(Schedule.idea_id == idea.id))
    if termin is not None:
        db.delete(termin)
        db.commit()


# ── odczyt ──────────────────────────────────────────────────────────────────


def by_idea(db: DbSession, session_id: int) -> dict[int, Schedule]:
    rows = db.scalars(
        select(Schedule).join(Idea, Idea.id == Schedule.idea_id).where(Idea.session_id == session_id)
    )
    return {t.idea_id: t for t in rows}


def missing(db: DbSession, session_id: int) -> list[Idea]:
    """Pomysły, które przeszły dalej, ale nie mają jeszcze terminu."""
    terminy = by_idea(db, session_id)
    return [i for i in swipes.accepted_ideas(db, session_id) if i.id not in terminy]


def agenda(db: DbSession, session_id: int, today: date | None = None) -> list[dict]:
    """Pełna lista pozycji etapu 3, gotowa do wyświetlenia.

    Sortowanie: najpierw po dacie początku, pomysły bez terminu na końcu.
    Kalendarz z etapu 5 skorzysta z tego samego porządku.
    """
    dzis = today or date.today()
    terminy = by_idea(db, session_id)

    pozycje = []
    for idea in swipes.accepted_ideas(db, session_id):
        termin = terminy.get(idea.id)
        pozycje.append(
            {
                "ideaId": idea.id,
                "title": idea.title,
                "description": idea.description,
                "isSpecial": idea.is_special,
                "schedule": None
                if termin is None
                else {
                    "kind": termin.kind,
                    "dateFrom": termin.date_from.isoformat(),
                    "dateTo": termin.date_to.isoformat(),
                    "label": termin.label,
                    # Ostrzeżenie, nie blokada — host może świadomie planować
                    # coś, co już minęło (np. porządkować starą sesję).
                    "isPast": termin.date_to < dzis,
                },
            }
        )

    pozycje.sort(key=lambda p: (p["schedule"] is None, p["schedule"]["dateFrom"] if p["schedule"] else ""))
    return pozycje
