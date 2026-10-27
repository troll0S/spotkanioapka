"""Logika etapu 5 — kto to zrobi.

Po zebraniu deklaracji host przechodzi po kolei przez wszystkie wydarzenia.
Dla każdego widzi tytuł, opis, termin i to, kto jak odpowiedział — **to jest
moment odsłonięcia wyników**. Przypisuje wykonawców i albo zatwierdza
wydarzenie, albo je odrzuca; odrzucone nie trafia do kalendarza.

Przypisać można uczestnika sesji, ale też kogoś spoza niej. Stąd nazwisko
trzymamy zawsze jako tekst, a powiązanie z uczestnikiem jest opcjonalne.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from . import schedules, swipes
from .models import EventAssignment, EventPlan, Idea, Participant, Role, Session
from .state_machine import SessionStatus

MAX_NAZWY = 40

#: Zabezpieczenie przed przypadkowym zalaniem listy — nie ograniczenie
#: merytoryczne. Trzydzieści osób przy jednym wydarzeniu to i tak dużo.
MAX_OSOB_NA_WYDARZENIE = 30


class AssignmentError(Exception):
    """Naruszenie reguł etapu 5 — komunikat jest przeznaczony dla użytkownika."""


# ── kolejność przeglądu ─────────────────────────────────────────────────────


def order(db: DbSession, session: Session) -> list[Idea]:
    """Wydarzenia w kolejności chronologicznej.

    Inaczej niż w etapie 4, gdzie kolejność jest losowa dla uczciwości głosowania.
    Tutaj nikt nie głosuje — przydzielanie ludzi czyta się najnaturalniej od
    najbliższego terminu.
    """
    terminy = schedules.by_idea(db, session.id)
    pomysly = swipes.accepted_ideas(db, session.id)
    # Brak terminu nie powinien się zdarzyć — etap 3 tego pilnuje — ale
    # sortowanie nie może się na tym wywrócić, więc takie idą na koniec.
    return sorted(
        pomysly,
        key=lambda i: (terminy[i.id].date_from if i.id in terminy else date.max, i.id),
    )


def current(db: DbSession, session: Session) -> Idea | None:
    kolejnosc = order(db, session)
    indeks = session.assignment_index
    if 0 <= indeks < len(kolejnosc):
        return kolejnosc[indeks]
    return None


def move(db: DbSession, session: Session, participant: Participant, delta: int) -> None:
    _require_assignment(session)
    _require_host(participant)

    kolejnosc = order(db, session)
    if not kolejnosc:
        raise AssignmentError("Nie ma żadnych wydarzeń.")

    nowy = session.assignment_index + delta
    if nowy < 0:
        raise AssignmentError("To już pierwsze wydarzenie.")
    if nowy >= len(kolejnosc):
        raise AssignmentError("To już ostatnie wydarzenie.")

    session.assignment_index = nowy
    db.commit()


# ── reguły wspólne ──────────────────────────────────────────────────────────


def _require_assignment(session: Session) -> None:
    if session.status_enum is not SessionStatus.ASSIGNMENT:
        raise AssignmentError("Etap przydzielania nie jest aktywny.")


def _require_host(participant: Participant) -> None:
    if participant.role_enum is not Role.HOST:
        raise AssignmentError("Wykonawców przypisuje prowadzący.")


def _event(db: DbSession, session: Session, idea_id: int) -> Idea:
    idea = db.get(Idea, idea_id)
    if idea is None or idea.session_id != session.id:
        raise AssignmentError("Nie ma takiego wydarzenia.")
    if idea not in swipes.accepted_ideas(db, session.id):
        raise AssignmentError("To wydarzenie nie doszło do tego etapu.")
    return idea


# ── przypisywanie osób ──────────────────────────────────────────────────────


def add_person(
    db: DbSession,
    session: Session,
    participant: Participant,
    idea_id: int,
    name: str,
    linked_participant_id: int | None = None,
) -> EventAssignment:
    _require_assignment(session)
    _require_host(participant)
    idea = _event(db, session, idea_id)

    czyste = (name or "").strip()
    if not czyste:
        raise AssignmentError("Podaj imię.")
    if len(czyste) > MAX_NAZWY:
        raise AssignmentError(f"Imię może mieć najwyżej {MAX_NAZWY} znaków.")

    istniejace = assignments_for(db, idea.id)
    if len(istniejace) >= MAX_OSOB_NA_WYDARZENIE:
        raise AssignmentError(f"Przy jednym wydarzeniu zmieści się {MAX_OSOB_NA_WYDARZENIE} osób.")
    # Porównanie bez względu na wielkość liter: „Ania" i „ania" to ta sama osoba.
    if any(w.name.casefold() == czyste.casefold() for w in istniejace):
        raise AssignmentError(f"„{czyste}” jest już przypisany do tego wydarzenia.")

    if linked_participant_id is not None:
        osoba = db.get(Participant, linked_participant_id)
        if osoba is None or osoba.session_id != session.id:
            raise AssignmentError("Nieznany uczestnik.")
        czyste = osoba.display_name

    wpis = EventAssignment(
        idea_id=idea.id, participant_id=linked_participant_id, name=czyste
    )
    db.add(wpis)
    db.commit()
    return wpis


def remove_person(
    db: DbSession, session: Session, participant: Participant, assignment_id: int
) -> None:
    _require_assignment(session)
    _require_host(participant)

    wpis = db.get(EventAssignment, assignment_id)
    if wpis is None:
        raise AssignmentError("Nie ma takiego przypisania.")
    _event(db, session, wpis.idea_id)

    db.delete(wpis)
    db.commit()


def assignments_for(db: DbSession, idea_id: int) -> list[EventAssignment]:
    return list(
        db.scalars(
            select(EventAssignment)
            .where(EventAssignment.idea_id == idea_id)
            .order_by(EventAssignment.created_at, EventAssignment.id)
        )
    )


def assignments_by_idea(db: DbSession, session_id: int) -> dict[int, list[EventAssignment]]:
    rows = db.scalars(
        select(EventAssignment)
        .join(Idea, Idea.id == EventAssignment.idea_id)
        .where(Idea.session_id == session_id)
        .order_by(EventAssignment.created_at, EventAssignment.id)
    )
    wynik: dict[int, list[EventAssignment]] = {}
    for wpis in rows:
        wynik.setdefault(wpis.idea_id, []).append(wpis)
    return wynik


# ── zatwierdzanie i odrzucanie ──────────────────────────────────────────────


def decide(
    db: DbSession,
    session: Session,
    participant: Participant,
    idea_id: int,
    confirmed: bool,
) -> EventPlan:
    """Zatwierdzenie albo odrzucenie wydarzenia. Da się zmienić zdanie."""
    _require_assignment(session)
    _require_host(participant)
    idea = _event(db, session, idea_id)

    plan = db.scalar(select(EventPlan).where(EventPlan.idea_id == idea.id))
    if plan is None:
        plan = EventPlan(idea_id=idea.id, confirmed=confirmed)
        db.add(plan)
    else:
        plan.confirmed = confirmed
    db.commit()
    return plan


def plans(db: DbSession, session_id: int) -> dict[int, bool]:
    rows = db.execute(
        select(EventPlan.idea_id, EventPlan.confirmed)
        .join(Idea, Idea.id == EventPlan.idea_id)
        .where(Idea.session_id == session_id)
    ).all()
    return {idea_id: confirmed for idea_id, confirmed in rows}


def undecided(db: DbSession, session: Session) -> list[Idea]:
    podjete = plans(db, session.id)
    return [i for i in order(db, session) if i.id not in podjete]


#: Dlaczego pomysł nie trafił do planu. Kolejność ma znaczenie: sprawdzamy
#: od najwcześniejszego etapu, bo tam pomysł odpadł naprawdę.
ODRZUCENIA = {
    "swipe_rejected": "odrzucony przy wyborze",
    "swipe_undecided": "nierozstrzygnięty przy wyborze",
    "plan_rejected": "odrzucony przy przydziale",
    "plan_undecided": "nierozstrzygnięty przy przydziale",
}


def rejected_ideas(db: DbSession, session_id: int) -> list[tuple[Idea, str]]:
    """Wszystko, co nie weszło do planu — z etapu 2 albo z etapu 5.

    Zwraca pary (pomysł, powód). Sesja ma zostawić ślad także po tym, co
    odpadło: przy następnym planowaniu to bywa cenniejsze niż sam kalendarz.
    """
    from .models import HostDecision

    decyzje = {
        idea_id: accepted
        for idea_id, accepted in db.execute(
            select(HostDecision.idea_id, HostDecision.accepted)
            .join(Idea, Idea.id == HostDecision.idea_id)
            .where(Idea.session_id == session_id)
        ).all()
    }
    plany = plans(db, session_id)

    wynik: list[tuple[Idea, str]] = []
    wszystkie = db.scalars(
        select(Idea).where(Idea.session_id == session_id).order_by(Idea.created_at, Idea.id)
    )

    for idea in wszystkie:
        # Wpis ustalony pomija etap 2, więc odpaść mógł wyłącznie w etapie 5.
        if not idea.is_special:
            if decyzje.get(idea.id) is False:
                wynik.append((idea, ODRZUCENIA["swipe_rejected"]))
                continue
            if idea.id not in decyzje:
                wynik.append((idea, ODRZUCENIA["swipe_undecided"]))
                continue

        if plany.get(idea.id) is False:
            wynik.append((idea, ODRZUCENIA["plan_rejected"]))
        elif idea.id not in plany:
            wynik.append((idea, ODRZUCENIA["plan_undecided"]))

    return wynik


def confirmed_ideas(db: DbSession, session_id: int) -> list[Idea]:
    """Co trafia do kalendarza i eksportów.

    Jedyne źródło tej reguły — kalendarz ma z niej korzystać, a nie
    odtwarzać ją u siebie.
    """
    podjete = plans(db, session_id)
    return [i for i in swipes.accepted_ideas(db, session_id) if podjete.get(i.id) is True]
