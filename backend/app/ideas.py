"""Logika etapu 1 — zbieranie pomysłów.

Wszystkie reguły uprawnień siedzą tutaj, a nie w warstwie WebSocketu i nie
w interfejsie. Frontend może je powtarzać dla wygody użytkownika, ale decyduje
wyłącznie serwer: w trybie zdalnym adres jest publiczny, więc „przycisk jest
ukryty" nie jest zabezpieczeniem.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .models import Idea, Participant, Role, Session
from .state_machine import SessionStatus

MAX_TITLE = 120
MAX_DESCRIPTION = 500

#: Limit na osobę. Nie chodzi o oszczędzanie bazy, tylko o to, żeby jedna osoba
#: nie zasypała etapu 2 pięćdziesięcioma kartami do przeswipowania.
MAX_PER_PARTICIPANT = 15


class IdeaError(Exception):
    """Naruszenie reguł etapu 1 — komunikat jest przeznaczony dla użytkownika."""


def list_ideas(db: DbSession, session_id: int) -> list[Idea]:
    return list(
        db.scalars(
            select(Idea)
            .where(Idea.session_id == session_id)
            .order_by(Idea.created_at.desc())
        )
    )


def count_by_author(db: DbSession, author_id: int) -> int:
    return (
        db.scalar(select(func.count(Idea.id)).where(Idea.author_id == author_id)) or 0
    )


def _require_collecting(session: Session) -> None:
    if session.status_enum is not SessionStatus.COLLECTING:
        raise IdeaError("Etap zbierania pomysłów nie jest aktywny.")


def _clean_title(title: str) -> str:
    cleaned = (title or "").strip()
    if not cleaned:
        raise IdeaError("Pomysł musi mieć tytuł.")
    if len(cleaned) > MAX_TITLE:
        raise IdeaError(f"Tytuł może mieć najwyżej {MAX_TITLE} znaków.")
    return cleaned


def _clean_description(description: str | None) -> str | None:
    cleaned = (description or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_DESCRIPTION:
        raise IdeaError(f"Opis może mieć najwyżej {MAX_DESCRIPTION} znaków.")
    return cleaned


def create_idea(
    db: DbSession,
    session: Session,
    author: Participant,
    title: str,
    description: str | None = None,
    is_special: bool = False,
) -> Idea:
    _require_collecting(session)

    # Host prowadzi proces i nie bierze w nim udziału — także na etapie 1.
    if author.role_enum is Role.HOST:
        raise IdeaError("Ekran prowadzącego nie dodaje pomysłów.")

    # Wpis, którego nie da się odrzucić, może powstać tylko z ręki admina.
    if is_special and author.role_enum is not Role.ADMIN:
        raise IdeaError("Wpisy specjalne może dodawać tylko administrator.")

    if count_by_author(db, author.id) >= MAX_PER_PARTICIPANT:
        raise IdeaError(f"Masz już {MAX_PER_PARTICIPANT} pomysłów — to maksimum.")

    idea = Idea(
        session_id=session.id,
        author_id=author.id,
        title=_clean_title(title),
        description=_clean_description(description),
        is_special=is_special,
    )
    db.add(idea)
    db.commit()
    return idea


def _own_idea(db: DbSession, session: Session, actor: Participant, idea_id: int) -> Idea:
    idea = db.get(Idea, idea_id)
    if idea is None or idea.session_id != session.id:
        raise IdeaError("Nie ma takiego pomysłu.")
    # Autorstwo sprawdzamy po stronie serwera. Interfejs ukrywa obce przyciski,
    # ale to tylko wygoda — regułą jest ten warunek.
    if idea.author_id != actor.id:
        raise IdeaError("Możesz zmieniać tylko swoje pomysły.")
    return idea


def update_idea(
    db: DbSession,
    session: Session,
    actor: Participant,
    idea_id: int,
    title: str,
    description: str | None = None,
) -> Idea:
    _require_collecting(session)
    idea = _own_idea(db, session, actor, idea_id)

    idea.title = _clean_title(title)
    idea.description = _clean_description(description)
    db.commit()
    return idea


def delete_idea(db: DbSession, session: Session, actor: Participant, idea_id: int) -> None:
    _require_collecting(session)
    idea = _own_idea(db, session, actor, idea_id)

    db.delete(idea)
    db.commit()


def limits() -> dict:
    """Limity wysyłane w snapshocie, żeby frontend nie trzymał własnej kopii."""
    return {
        "maxTitle": MAX_TITLE,
        "maxDescription": MAX_DESCRIPTION,
        "maxPerParticipant": MAX_PER_PARTICIPANT,
    }
