"""Zapytania o uczestników.

Cały moduł istnieje po to, żeby `voting_participants` miało jedno miejsce.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .models import Participant, Role


def voting_participants(db: DbSession, session_id: int) -> list[Participant]:
    """JEDYNE źródło mianownika dla liczników postępu.

    Host i admin są podłączeni, ale nie głosują. Gdyby trafili do mianownika,
    etap nigdy by się nie domknął — czekałbyś na głos kogoś, kto z definicji
    nie głosuje. Objaw wygląda jak zawieszona aplikacja, nie jak błąd.

    Każdy licznik "X / Y" w etapach 2 i 4 bierze Y stąd i tylko stąd.

    Uwaga projektowa: liczymy wszystkich głosujących, którzy dołączyli —
    także chwilowo rozłączonych. Inaczej mianownik skakałby przy każdej
    blokadzie ekranu telefonu. Obsługa osób, które wyszły na dobre, to
    decyzja hosta (K3), nie automat.
    """
    return list(
        db.scalars(
            select(Participant)
            .where(Participant.session_id == session_id)
            .where(Participant.is_voting.is_(True))
            .order_by(Participant.joined_at)
        )
    )


def voting_count(db: DbSession, session_id: int) -> int:
    return len(voting_participants(db, session_id))


def by_token(db: DbSession, token: str) -> Participant | None:
    return db.scalar(select(Participant).where(Participant.token == token))


def by_name(db: DbSession, session_id: int, display_name: str) -> Participant | None:
    return db.scalar(
        select(Participant)
        .where(Participant.session_id == session_id)
        .where(Participant.display_name == display_name)
    )


def host_of(db: DbSession, session_id: int) -> Participant | None:
    return db.scalar(
        select(Participant)
        .where(Participant.session_id == session_id)
        .where(Participant.role == Role.HOST.value)
    )
