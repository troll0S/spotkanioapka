"""Logika etapu 4 — deklaracje dostępności.

Przebieg jest prowadzony przez hosta, jak w Kahoocie: jedno wydarzenie naraz,
wszyscy odpowiadają na to samo, host przechodzi dalej. Kolejność jest losowa,
ale **wylosowana raz** i zapisana — przy każdym odczycie tasowałaby ekran, a
host i telefony muszą patrzeć na to samo wydarzenie.

Odpowiedź jest wiążąca. Zmiana wyłącznie z panelu admina (K8).
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import schedules, swipes
from .models import Answer, Availability, Idea, Participant, Role, Session
from .participants import voting_participants
from .state_machine import SessionStatus

#: Kolejność wyświetlania i opisy — jedno źródło dla przycisków i podsumowań.
ANSWER_LABELS: dict[Answer, str] = {
    Answer.WANT: "chcę",
    Answer.CAN: "mogę",
    Answer.DONT_WANT: "nie chcę",
    Answer.ABSOLUTELY_NOT: "absolutnie nie",
}


class AvailabilityError(Exception):
    """Naruszenie reguł etapu 4 — komunikat jest przeznaczony dla użytkownika."""


# ── kolejność wydarzeń ──────────────────────────────────────────────────────


def build_order(db: DbSession, session: Session) -> list[int]:
    """Losuje kolejność wydarzeń i zapisuje ją w sesji.

    Wołane raz, przy wejściu w etap 4. Losowość jest tu celowa: przy stałej
    kolejności ostatnie wydarzenia zawsze trafiałyby na zmęczoną grupę.
    """
    ids = [i.id for i in swipes.accepted_ideas(db, session.id)]
    random.shuffle(ids)
    session.availability_order = ",".join(str(i) for i in ids)
    session.availability_index = 0
    db.commit()
    return ids


def order(session: Session) -> list[int]:
    if not session.availability_order:
        return []
    return [int(x) for x in session.availability_order.split(",") if x]


def current_idea_id(session: Session) -> int | None:
    kolejnosc = order(session)
    indeks = session.availability_index
    if 0 <= indeks < len(kolejnosc):
        return kolejnosc[indeks]
    return None


def all_presented(session: Session) -> bool:
    """Czy host dotarł do ostatniego wydarzenia."""
    kolejnosc = order(session)
    return bool(kolejnosc) and session.availability_index >= len(kolejnosc) - 1


def remaining(session: Session) -> int:
    kolejnosc = order(session)
    return max(0, len(kolejnosc) - 1 - session.availability_index)


# ── operacje ────────────────────────────────────────────────────────────────


def _require_availability(session: Session) -> None:
    if session.status_enum is not SessionStatus.AVAILABILITY:
        raise AvailabilityError("Etap deklarowania dostępności nie jest aktywny.")


def answer(
    db: DbSession,
    session: Session,
    participant: Participant,
    idea_id: int,
    value: str,
) -> Availability:
    """Odpowiedź uczestnika na bieżące wydarzenie. Raz i na zawsze."""
    _require_availability(session)

    if participant.role_enum is Role.HOST:
        raise AvailabilityError("Ekran prowadzącego nie deklaruje dostępności.")
    if not participant.is_voting:
        raise AvailabilityError("Nie bierzesz udziału w głosowaniu.")

    try:
        odpowiedz = Answer(value)
    except ValueError:
        raise AvailabilityError("Nieznana odpowiedź.") from None

    biezace = current_idea_id(session)
    if biezace is None:
        raise AvailabilityError("Nie ma teraz żadnego wydarzenia.")
    # Odpowiadamy wyłącznie na to, co host właśnie pokazuje. Inaczej telefon
    # z nieodświeżonym ekranem mógłby wpisać głos do poprzedniego wydarzenia.
    if idea_id != biezace:
        raise AvailabilityError("To wydarzenie nie jest już na ekranie.")

    istniejaca = db.scalar(
        select(Availability)
        .where(Availability.idea_id == idea_id)
        .where(Availability.participant_id == participant.id)
    )
    if istniejaca is not None:
        raise AvailabilityError("Już odpowiedziałeś na to wydarzenie.")

    wpis = Availability(
        idea_id=idea_id, participant_id=participant.id, answer=odpowiedz.value
    )
    db.add(wpis)
    db.commit()
    return wpis


def move(db: DbSession, session: Session, participant: Participant, delta: int) -> None:
    """Przesunięcie do kolejnego albo poprzedniego wydarzenia.

    Cofanie jest dopuszczone świadomie: host może kliknąć „dalej" za wcześnie,
    a odpowiedzi są i tak zablokowane, więc powrót niczego nie psuje.
    """
    _require_availability(session)

    if participant.role_enum is not Role.HOST:
        raise AvailabilityError("Przebiegiem steruje prowadzący.")

    kolejnosc = order(session)
    if not kolejnosc:
        raise AvailabilityError("Nie ma żadnych wydarzeń.")

    nowy = session.availability_index + delta
    if nowy < 0:
        raise AvailabilityError("To już pierwsze wydarzenie.")
    if nowy >= len(kolejnosc):
        raise AvailabilityError("To już ostatnie wydarzenie.")

    session.availability_index = nowy
    db.commit()


# ── odczyt ──────────────────────────────────────────────────────────────────


def answers_for(db: DbSession, idea_id: int) -> list[Availability]:
    return list(
        db.scalars(select(Availability).where(Availability.idea_id == idea_id))
    )


def tally(db: DbSession, idea_id: int) -> dict[str, int]:
    wynik = {a.value: 0 for a in Answer}
    for wpis in answers_for(db, idea_id):
        wynik[wpis.answer] = wynik.get(wpis.answer, 0) + 1
    return wynik


def your_answer(db: DbSession, idea_id: int, participant_id: int) -> str | None:
    wpis = db.scalar(
        select(Availability)
        .where(Availability.idea_id == idea_id)
        .where(Availability.participant_id == participant_id)
    )
    return wpis.answer if wpis else None


def event_view(db: DbSession, session: Session, idea_id: int) -> dict | None:
    """Wydarzenie tak, jak ma się pokazać: tytuł, opis i termin.

    Termin jest tu obowiązkowy — etap 3 nie przepuszcza pomysłów bez daty.
    """
    idea = db.get(Idea, idea_id)
    if idea is None or idea.session_id != session.id:
        return None

    termin = schedules.by_idea(db, session.id).get(idea.id)
    return {
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
        },
    }


def summary(db: DbSession, session: Session, ideas_subset=None) -> list[dict]:
    """Zestawienie wydarzeń z odpowiedziami — podstawa etapów 5 i 6.

    Zwraca imiona, bo etap 5 ma pokazać, kto jak odpowiedział. W trakcie
    samej rundy z etapu 4 imion nie ujawniamy.

    `ideas_subset` pozwala zawęzić zestawienie — kalendarz bierze tylko
    wydarzenia zatwierdzone w etapie 5.
    """
    ludzie = {p.id: p.display_name for p in session.participants}
    terminy = schedules.by_idea(db, session.id)

    wynik = []
    for idea in (
        swipes.accepted_ideas(db, session.id) if ideas_subset is None else ideas_subset
    ):
        termin = terminy.get(idea.id)
        wpisy = answers_for(db, idea.id)
        wedlug_odpowiedzi: dict[str, list[str]] = {a.value: [] for a in Answer}
        for wpis in wpisy:
            wedlug_odpowiedzi.setdefault(wpis.answer, []).append(
                ludzie.get(wpis.participant_id, "—")
            )

        wynik.append(
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
                },
                "tally": tally(db, idea.id),
                "people": wedlug_odpowiedzi,
                "answered": len(wpisy),
            }
        )

    wynik.sort(key=lambda p: p["schedule"]["dateFrom"] if p["schedule"] else "")
    return wynik


def expected_voters(db: DbSession, session_id: int) -> int:
    return len(voting_participants(db, session_id))
