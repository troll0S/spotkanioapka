"""Logika etapu 2 — wybór pomysłów.

Dwa niezależne biegi w tym samym czasie:

* **Uczestnicy** przechodzą swoje karty we własnym tempie. Ich głosy są
  doradcze.
* **Host** idzie przez te same pomysły i przesuwa ostatecznie. Jego decyzja
  nadpisuje wszystko, co zagłosowali pozostali — wprost z opisu.

Wpisy specjalne nie wchodzą do tej puli w ogóle. Nie da się ich odrzucić, więc
nie ma o czym głosować; przechodzą wprost do etapu 3.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .models import Direction, HostDecision, Idea, Participant, Role, Session, Swipe
from .state_machine import SessionStatus


class SwipeError(Exception):
    """Naruszenie reguł etapu 2 — komunikat jest przeznaczony dla użytkownika."""


def pool(db: DbSession, session_id: int) -> list[Idea]:
    """Pomysły podlegające ocenie: wszystko poza wpisami specjalnymi.

    Kolejność jest stała i taka sama dla wszystkich — od najstarszego. Dzięki
    temu ekran hosta i telefony mówią o tych samych kartach w tej samej
    kolejności, a licznik „X na Y" znaczy to samo u każdego.
    """
    return list(
        db.scalars(
            select(Idea)
            .where(Idea.session_id == session_id)
            .where(Idea.is_special.is_(False))
            .order_by(Idea.created_at, Idea.id)
        )
    )


def decisions(db: DbSession, session_id: int) -> dict[int, bool]:
    rows = db.execute(
        select(HostDecision.idea_id, HostDecision.accepted)
        .join(Idea, Idea.id == HostDecision.idea_id)
        .where(Idea.session_id == session_id)
    ).all()
    return {idea_id: accepted for idea_id, accepted in rows}


def tally(db: DbSession, session_id: int) -> dict[int, dict[str, int]]:
    """Liczniki „za" i „przeciw" dla każdego pomysłu — jednym zapytaniem."""

    rows = db.execute(
        select(Swipe.idea_id, Swipe.direction, func.count(Swipe.id))
        .join(Idea, Idea.id == Swipe.idea_id)
        .where(Idea.session_id == session_id)
        .group_by(Swipe.idea_id, Swipe.direction)
    ).all()

    wynik: dict[int, dict[str, int]] = {}
    for idea_id, direction, liczba in rows:
        wpis = wynik.setdefault(idea_id, {"right": 0, "left": 0})
        wpis["right" if direction == Direction.RIGHT.value else "left"] = liczba
    return wynik


def your_swipes(db: DbSession, participant_id: int) -> dict[int, str]:

    rows = db.execute(
        select(Swipe.idea_id, Swipe.direction).where(Swipe.participant_id == participant_id)
    ).all()
    return {idea_id: direction for idea_id, direction in rows}


def _require_swiping(session: Session) -> None:
    if session.status_enum is not SessionStatus.SWIPING:
        raise SwipeError("Etap wybierania pomysłów nie jest aktywny.")


def _idea_in_pool(db: DbSession, session: Session, idea_id: int) -> Idea:
    idea = db.get(Idea, idea_id)
    if idea is None or idea.session_id != session.id:
        raise SwipeError("Nie ma takiego pomysłu.")
    if idea.is_special:
        raise SwipeError("Wpisu ustalonego nie da się odrzucić.")
    return idea


def swipe(
    db: DbSession,
    session: Session,
    participant: Participant,
    idea_id: int,
    direction: str,
):
    """Głos uczestnika. Jeden na pomysł, bez cofania."""

    _require_swiping(session)

    if participant.role_enum is Role.HOST:
        raise SwipeError("Ekran prowadzącego nie głosuje — rozstrzyga.")
    if not participant.is_voting:
        raise SwipeError("Nie bierzesz udziału w głosowaniu.")

    if direction not in (Direction.RIGHT.value, Direction.LEFT.value):
        raise SwipeError("Nieznany kierunek.")

    idea = _idea_in_pool(db, session, idea_id)

    # Po rozstrzygnięciu hosta głos nie ma już żadnego znaczenia — przyjmowanie
    # go sugerowałoby uczestnikowi, że coś zmienia.
    if db.scalar(select(HostDecision).where(HostDecision.idea_id == idea.id)) is not None:
        raise SwipeError("Prowadzący już rozstrzygnął ten pomysł.")

    istniejacy = db.scalar(
        select(Swipe)
        .where(Swipe.idea_id == idea.id)
        .where(Swipe.participant_id == participant.id)
    )
    if istniejacy is not None:
        raise SwipeError("Ten pomysł masz już za sobą.")

    glos = Swipe(idea_id=idea.id, participant_id=participant.id, direction=direction)
    db.add(glos)
    db.commit()
    return glos


def decide(
    db: DbSession,
    session: Session,
    participant: Participant,
    idea_id: int,
    accepted: bool,
) -> HostDecision:
    """Rozstrzygnięcie hosta. Nadpisuje głosy i można je poprawić.

    Asymetria wobec uczestników jest zamierzona: uczestnik przesuwa raz, bo
    głosów ma być wiele i mają być szybkie. Host decyduje sam za całą grupę,
    więc pomyłka jednego kliknięcia musi dać się cofnąć.
    """
    _require_swiping(session)

    if participant.role_enum is not Role.HOST:
        raise SwipeError("Tylko prowadzący rozstrzyga pomysły.")

    idea = _idea_in_pool(db, session, idea_id)

    decyzja = db.scalar(select(HostDecision).where(HostDecision.idea_id == idea.id))
    if decyzja is None:
        decyzja = HostDecision(idea_id=idea.id, accepted=accepted)
        db.add(decyzja)
    else:
        decyzja.accepted = accepted
    db.commit()
    return decyzja


def accepted_ideas(db: DbSession, session_id: int) -> list[Idea]:
    """Co przechodzi do etapu 3: wpisy specjalne oraz przyjęte przez hosta.

    To jedyne miejsce, które tę regułę definiuje — etap 3 i kalendarz mają
    z niej korzystać, a nie odtwarzać ją u siebie.
    """
    podjete = decisions(db, session_id)
    wszystkie = db.scalars(
        select(Idea).where(Idea.session_id == session_id).order_by(Idea.created_at, Idea.id)
    )
    return [i for i in wszystkie if i.is_special or podjete.get(i.id) is True]
