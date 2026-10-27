"""WebSocket sesji.

Jedno połączenie na uczestnika. Serwer jest jedynym źródłem prawdy — klient
nie trzyma własnej wersji stanu, tylko renderuje ostatni otrzymany snapshot.

**Sesja bazy jest otwierana na każdą wiadomość, nie na całe połączenie.**
To nie jest ostrożność na zapas. Połączenia żyją przez całą sesję planowania,
a stan zmienia się z innych sesji bazy: host przestawia etap swoim połączeniem,
admin awansuje przez REST. Sesja trzymana na całe połączenie zapamiętałaby stan
z chwili nawiązania i po cichu pracowałaby na nieaktualnych danych — brama etapu
dawałaby się obejść, a awansowany admin wciąż byłby gościem.

Kody zamknięcia (4xxx są zarezerwowane dla aplikacji):
  4404 — nie ma takiej sesji
  4401 — token nieznany, z innej sesji albo uczestnik został usunięty
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session as DbSession

from .. import (
    admin_ops,
    assignments,
    availability,
    codes,
    ideas,
    schedules,
    swipes,
    urls,
)
from ..db import SessionLocal
from ..models import Participant, Role, Session
from ..participants import by_token
from ..realtime import broadcast_state
from ..state_machine import InvalidTransition, SessionStatus, abort, advance
from ..ws_manager import manager, next_spectator_id

log = logging.getLogger("spotkanioapka.ws")

router = APIRouter()

WS_SESSION_NOT_FOUND = 4404
WS_BAD_TOKEN = 4401
WS_SESSION_CLOSED = 4409


@router.websocket("/ws/session/{code}")
async def session_socket(
    websocket: WebSocket,
    code: str,
    token: str | None = None,
    spectator: bool = False,
) -> None:
    if spectator:
        await _spectator_socket(websocket, code)
        return

    # Faza 1: ustalenie tożsamości. Zapamiętujemy identyfikatory, nie obiekty —
    # obiekty ORM przywiązane do zamkniętej sesji są bezużyteczne.
    with SessionLocal() as db:
        session = db.query(Session).filter(Session.code == codes.normalize(code)).one_or_none()
        if session is None:
            await websocket.close(code=WS_SESSION_NOT_FOUND, reason="Nie ma sesji o tym kodzie.")
            return

        participant = by_token(db, token) if token else None
        if participant is None or participant.session_id != session.id:
            await websocket.close(code=WS_BAD_TOKEN, reason="Nieznany token uczestnika.")
            return

        session_id, participant_id, session_code = session.id, participant.id, session.code

    join_url = urls.join_url(
        session_code,
        websocket.headers.get("host"),
        urls.scheme_from(websocket.headers),
    )

    await manager.connect(session_code, participant_id, websocket)

    # Jeden broadcast obsługuje oba zadania naraz: nowo podłączony dostaje
    # snapshot decydujący o tym, który ekran zobaczy, a pozostali — zmianę
    # obecności. Osobna wysyłka do siebie oznaczałaby dwa snapshoty pod rząd
    # i klienta, który musi zgadywać, który z nich jest aktualny.
    #
    # Dołączenie w trakcie etapu 3 nie jest przypadkiem szczególnym —
    # po prostu przychodzi snapshot ze statusem SCHEDULING.
    with SessionLocal() as db:
        _set_presence(db, participant_id, connected=True)
        await broadcast_state(db, db.get(Session, session_id), join_url)

    try:
        while True:
            message = await websocket.receive_json()

            with SessionLocal() as db:
                session = db.get(Session, session_id)
                participant = db.get(Participant, participant_id)

                if session is None or participant is None:
                    await websocket.close(
                        code=WS_BAD_TOKEN, reason="Nie ma cię już w tej sesji."
                    )
                    return

                await _handle(db, websocket, session, participant, message, join_url)
    except WebSocketDisconnect:
        pass
    finally:
        went_offline = manager.disconnect(session_code, participant_id, websocket)
        if went_offline:
            with SessionLocal() as db:
                _set_presence(db, participant_id, connected=False)
                current = db.get(Session, session_id)
                if current is not None:
                    await broadcast_state(db, current, join_url)


async def _spectator_socket(websocket: WebSocket, code: str) -> None:
    """Podgląd tylko do odczytu — bez tokenu, bez tożsamości, bez sterowania.

    Po co to istnieje: w jednym pomieszczeniu wszyscy patrzą na ekran hosta,
    a etapy 2, 3 i 5 dzieją się właśnie tam. Zdalnie nikt go nie widzi, więc
    bez tego widoku uczestnik siedzi przez cały etap 3 przed napisem „czekaj".

    Widz nie zostaje zapisany w bazie i nie wpływa na żadne liczniki poza
    własnym. Nie może wysłać niczego poza podtrzymaniem połączenia — nie jest
    to kwestia ukrytych przycisków, tylko tego, że ta pętla nic więcej nie
    przyjmuje.
    """
    with SessionLocal() as db:
        session = db.query(Session).filter(Session.code == codes.normalize(code)).one_or_none()
        if session is None:
            await websocket.close(code=WS_SESSION_NOT_FOUND, reason="Nie ma sesji o tym kodzie.")
            return

        # Zamkniętej sesji nie udostępniamy anonimowo. Uczestnik z tokenem wciąż
        # zobaczy jej stan, ale przez publiczny adres tunelu nie ma powodu
        # pokazywać archiwum komukolwiek, kto zna sam kod.
        if session.status_enum is SessionStatus.CLOSED:
            await websocket.close(code=WS_SESSION_CLOSED, reason="Ta sesja jest już zakończona.")
            return

        session_id, session_code = session.id, session.code

    join_url = urls.join_url(
        session_code,
        websocket.headers.get("host"),
        urls.scheme_from(websocket.headers),
    )
    connection_id = next_spectator_id()

    await manager.connect(session_code, connection_id, websocket)
    try:
        with SessionLocal() as db:
            await broadcast_state(db, db.get(Session, session_id), join_url)

        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            else:
                await _error(websocket, "Podgląd jest tylko do odczytu.")
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(session_code, connection_id, websocket)
        with SessionLocal() as db:
            current = db.get(Session, session_id)
            if current is not None:
                await broadcast_state(db, current, join_url)


def _set_presence(db: DbSession, participant_id: int, *, connected: bool) -> None:
    participant = db.get(Participant, participant_id)
    if participant is None:
        return
    participant.connected = connected
    participant.last_seen = datetime.now(timezone.utc)
    db.commit()


async def _handle(
    db: DbSession,
    websocket: WebSocket,
    session: Session,
    participant: Participant,
    message: dict,
    join_url: str,
) -> None:
    kind = message.get("type")

    if kind == "ping":
        # Utrzymuje połączenie przy życiu. Pośrednicy (w tym tunel Cloudflare
        # w trybie zdalnym) zamykają bezczynne WebSockety po około minucie.
        await websocket.send_json({"type": "pong"})
        return

    if kind and kind.startswith("idea."):
        await _handle_idea(
            db, websocket, session, participant, kind, message.get("payload") or {}, join_url
        )
        return

    if kind in ("swipe", "host.decide"):
        payload = message.get("payload") or {}
        try:
            if kind == "swipe":
                swipes.swipe(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("ideaId", 0)),
                    direction=str(payload.get("direction", "")),
                )
            else:
                swipes.decide(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("ideaId", 0)),
                    accepted=bool(payload.get("accepted")),
                )
        except swipes.SwipeError as exc:
            await _error(websocket, str(exc))
            return
        except (TypeError, ValueError):
            await _error(websocket, "Niepoprawne dane głosu.")
            return

        await broadcast_state(db, session, join_url)
        return

    if kind and kind.startswith("schedule."):
        payload = message.get("payload") or {}
        try:
            if kind == "schedule.set":
                schedules.set_schedule(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("ideaId", 0)),
                    kind=str(payload.get("kind", "")),
                    date=payload.get("date"),
                    date_from=payload.get("dateFrom"),
                    date_to=payload.get("dateTo"),
                    year=payload.get("year"),
                    month=payload.get("month"),
                )
            elif kind == "schedule.clear":
                schedules.clear_schedule(
                    db, session, participant, idea_id=int(payload.get("ideaId", 0))
                )
            else:
                await _error(websocket, f"Nieznana operacja: {kind!r}")
                return
        except schedules.ScheduleError as exc:
            await _error(websocket, str(exc))
            return
        except (TypeError, ValueError):
            await _error(websocket, "Niepoprawne dane terminu.")
            return

        await broadcast_state(db, session, join_url)
        return

    if kind in ("availability.answer", "host.availability.next", "host.availability.prev"):
        payload = message.get("payload") or {}
        try:
            if kind == "availability.answer":
                availability.answer(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("ideaId", 0)),
                    value=str(payload.get("answer", "")),
                )
            else:
                availability.move(
                    db, session, participant, 1 if kind.endswith("next") else -1
                )
        except availability.AvailabilityError as exc:
            await _error(websocket, str(exc))
            return
        except (TypeError, ValueError):
            await _error(websocket, "Niepoprawne dane odpowiedzi.")
            return

        await broadcast_state(db, session, join_url)
        return

    if kind and kind.startswith("assignment."):
        payload = message.get("payload") or {}
        try:
            if kind == "assignment.add":
                assignments.add_person(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("ideaId", 0)),
                    name=str(payload.get("name", "")),
                    linked_participant_id=payload.get("participantId"),
                )
            elif kind == "assignment.remove":
                assignments.remove_person(
                    db, session, participant, assignment_id=int(payload.get("id", 0))
                )
            elif kind == "assignment.decide":
                assignments.decide(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("ideaId", 0)),
                    confirmed=bool(payload.get("confirmed")),
                )
            elif kind in ("assignment.next", "assignment.prev"):
                assignments.move(db, session, participant, 1 if kind.endswith("next") else -1)
            else:
                await _error(websocket, f"Nieznana operacja: {kind!r}")
                return
        except assignments.AssignmentError as exc:
            await _error(websocket, str(exc))
            return
        except (TypeError, ValueError):
            await _error(websocket, "Niepoprawne dane przydziału.")
            return

        await broadcast_state(db, session, join_url)
        return

    if kind and kind.startswith("admin."):
        payload = message.get("payload") or {}
        try:
            if kind == "admin.correctAnswer":
                admin_ops.correct_answer(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("ideaId", 0)),
                    participant_id=int(payload.get("participantId", 0)),
                    value=str(payload.get("answer", "")),
                )
            elif kind == "admin.editIdea":
                admin_ops.edit_idea(
                    db,
                    session,
                    participant,
                    idea_id=int(payload.get("id", 0)),
                    title=payload.get("title"),
                    description=payload.get("description"),
                )
            elif kind == "admin.deleteIdea":
                admin_ops.delete_idea(
                    db, session, participant, idea_id=int(payload.get("id", 0))
                )
            elif kind == "admin.removeParticipant":
                admin_ops.remove_participant(
                    db, session, participant, participant_id=int(payload.get("id", 0))
                )
            else:
                await _error(websocket, f"Nieznana operacja: {kind!r}")
                return
        except admin_ops.AdminError as exc:
            await _error(websocket, str(exc))
            return
        except (TypeError, ValueError):
            await _error(websocket, "Niepoprawne dane operacji.")
            return

        await broadcast_state(db, session, join_url)
        return

    if kind in ("host.advance", "host.abort"):
        if participant.role_enum is not Role.HOST:
            await _error(websocket, "Tylko host steruje przebiegiem sesji.")
            return

        current = session.status_enum

        # Etap 4 pokazuje każde wydarzenie razem z terminem, a etap 5 rysuje
        # z nich kalendarz. Pomysł bez daty nie ma się gdzie pojawić, więc
        # zamiast go po cichu zgubić — zatrzymujemy się tutaj.
        if kind == "host.advance" and current is SessionStatus.SCHEDULING:
            bez_terminu = schedules.missing(db, session.id)
            if bez_terminu:
                nazwy = ", ".join(f"„{i.title}”" for i in bez_terminu[:3])
                reszta = f" i {len(bez_terminu) - 3} innych" if len(bez_terminu) > 3 else ""
                await _error(
                    websocket,
                    f"Bez terminu: {nazwy}{reszta}. Ustal je, zanim przejdziesz dalej.",
                )
                return

        # Wydarzenie, którego nikt nie zobaczył, nie ma ani jednej deklaracji —
        # w kalendarzu byłoby pustym wierszem. Lepiej zatrzymać hosta tutaj
        # niż tłumaczyć potem, czemu połowa planu jest bez ludzi.
        if kind == "host.advance" and current is SessionStatus.AVAILABILITY:
            zostalo = availability.remaining(session)
            if zostalo:
                await _error(
                    websocket,
                    f"Zostało {zostalo} wydarzeń, których nikt jeszcze nie widział. "
                    "Przejdź przez nie albo przerwij sesję.",
                )
                return

        # Wydarzenie bez rozstrzygnięcia nie wiadomo, czy ma trafić do
        # kalendarza. Zamiast zgadywać za hosta — zatrzymujemy się.
        if kind == "host.advance" and current is SessionStatus.ASSIGNMENT:
            bez_decyzji = assignments.undecided(db, session)
            if bez_decyzji:
                nazwy = ", ".join(f"„{i.title}”" for i in bez_decyzji[:3])
                reszta = f" i {len(bez_decyzji) - 3} innych" if len(bez_decyzji) > 3 else ""
                await _error(
                    websocket,
                    f"Bez rozstrzygnięcia: {nazwy}{reszta}. "
                    "Zatwierdź je albo odrzuć, zanim pokażesz kalendarz.",
                )
                return
        try:
            new_status = advance(current) if kind == "host.advance" else abort(current)
        except InvalidTransition as exc:
            await _error(websocket, str(exc))
            return

        session.status = new_status.value
        if new_status is SessionStatus.CLOSED:
            session.closed_at = datetime.now(timezone.utc)
        db.commit()

        # Kolejność wydarzeń w etapie 4 losujemy raz, przy wejściu w etap.
        # Tasowanie przy każdym odczycie przestawiałoby ekran pod ludźmi.
        if new_status is SessionStatus.AVAILABILITY:
            availability.build_order(db, session)

        log.info("Sesja %s: %s -> %s", session.code, current.value, new_status.value)
        await broadcast_state(db, session, join_url)
        return

    await _error(websocket, f"Nieznany typ wiadomości: {kind!r}")


async def _handle_idea(
    db: DbSession,
    websocket: WebSocket,
    session: Session,
    participant: Participant,
    kind: str,
    payload: dict,
    join_url: str,
) -> None:
    """Etap 1 — dodawanie, edycja i usuwanie pomysłów.

    Uprawnienia i walidacja są w `ideas.py`. Tutaj zostaje tłumaczenie
    wyjątku na komunikat dla tego jednego klienta i rozesłanie nowego stanu.
    """
    try:
        if kind == "idea.create":
            ideas.create_idea(
                db,
                session,
                participant,
                title=payload.get("title", ""),
                description=payload.get("description"),
                is_special=bool(payload.get("isSpecial")),
            )
        elif kind == "idea.update":
            ideas.update_idea(
                db,
                session,
                participant,
                idea_id=int(payload.get("id", 0)),
                title=payload.get("title", ""),
                description=payload.get("description"),
            )
        elif kind == "idea.delete":
            ideas.delete_idea(db, session, participant, idea_id=int(payload.get("id", 0)))
        else:
            await _error(websocket, f"Nieznana operacja: {kind!r}")
            return
    except ideas.IdeaError as exc:
        await _error(websocket, str(exc))
        return
    except (TypeError, ValueError):
        await _error(websocket, "Niepoprawne dane pomysłu.")
        return

    await broadcast_state(db, session, join_url)


async def _error(websocket: WebSocket, text: str) -> None:
    await websocket.send_json({"type": "error", "payload": {"text": text}})
