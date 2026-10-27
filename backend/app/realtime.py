"""Most między zmianą stanu a telefonami.

Każda operacja, która coś zmienia (dołączenie, awans, przejście etapu, wpis),
kończy się wywołaniem `broadcast_state`. Nie ma ścieżki, w której klient
dowiaduje się o zmianie inaczej niż przez świeży snapshot.
"""

from sqlalchemy.orm import Session as DbSession

from .models import Participant, Session
from .snapshots import build_snapshot
from .ws_manager import is_spectator, manager


def state_message(
    db: DbSession,
    session: Session,
    viewer: Participant | None,
    join_url: str | None,
    spectators: int = 0,
) -> dict:
    return {
        "type": "state",
        "payload": build_snapshot(db, session, viewer, join_url, spectators),
    }


async def broadcast_state(db: DbSession, session: Session, join_url: str | None = None) -> None:
    """Rozsyła aktualny stan wszystkim podłączonym do sesji.

    Snapshot budujemy osobno dla każdego odbiorcy, bo jego treść zależy od roli.
    Widzowie (ujemne identyfikatory) dostają wariant bez tożsamości i bez
    sterowania.
    """
    db.refresh(session)
    people = {p.id: p for p in session.participants}
    spectators = manager.spectator_count(session.code)

    def build_for(connection_id: int) -> dict | None:
        if is_spectator(connection_id):
            return state_message(db, session, None, join_url, spectators)
        viewer = people.get(connection_id)
        if viewer is None:
            return None
        return state_message(db, session, viewer, join_url, spectators)

    await manager.broadcast(session.code, build_for)


async def notify(code: str, participant_id: int, level: str, text: str) -> None:
    """Komunikat punktowy — to, czego nie da się wyrazić stanem sesji."""
    await manager.send_to(
        code, participant_id, {"type": "notice", "payload": {"level": level, "text": text}}
    )
