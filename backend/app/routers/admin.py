"""Archiwum sesji — dostęp ponad pojedynczą sesją, więc za osobnym logowaniem.

Operacje wewnątrz trwającej sesji (korekta odpowiedzi, moderacja wpisów,
usuwanie uczestników) idą WebSocketem, gdzie admin jest już rozpoznany po roli.
Tutaj są tylko rzeczy, które dotyczą wielu sesji naraz.
"""

import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from .. import accounts, admin_auth, assignments, codes, ratelimit, schedules, swipes
from ..db import get_db
from ..ideas import list_ideas
from ..models import Idea, Participant, Session
from ..state_machine import LABELS, SessionStatus

router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1)


class CreateUserIn(BaseModel):
    login: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1)
    is_superadmin: bool = False


class UpdateUserIn(BaseModel):
    password: str | None = None
    is_active: bool | None = None
    is_superadmin: bool | None = None


def _bearer(authorization: str | None) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def require_admin(authorization: str | None = Header(default=None)) -> admin_auth.TokenInfo:
    """Zależność chroniąca cały router."""
    dane = admin_auth.info(_bearer(authorization))
    if dane is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Zaloguj się jako administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return dane


def require_superadmin(
    dane: admin_auth.TokenInfo = Depends(require_admin),
) -> admin_auth.TokenInfo:
    if not dane.is_superadmin:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "To uprawnienie ma tylko superadmin."
        )
    return dane


@router.post("/login")
def login(payload: LoginIn, request: Request, db: DbSession = Depends(get_db)) -> dict:
    # Pierwsze konto zakładamy z .env — inaczej nie dałoby się zalogować,
    # żeby założyć pierwsze konto.
    accounts.bootstrap(db)
    if accounts.count(db) == 0:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Nie ma żadnego konta administratora. Ustaw ADMIN_PASSWORD w pliku .env "
            f"({accounts.WYMAGANIA_HASLA}) i uruchom aplikację ponownie.",
        )

    key = ratelimit.client_key(
        request.headers, request.client.host if request.client else None
    )
    if ratelimit.failed_auth.exceeded(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zbyt wiele nieudanych prób. Spróbuj później.",
            headers={"Retry-After": str(ratelimit.failed_auth.retry_after(key))},
        )

    konto = accounts.authenticate(db, payload.login, payload.password)
    if konto is None:
        ratelimit.failed_auth.hit(key)
        if ratelimit.FAILED_AUTH_DELAY:
            time.sleep(ratelimit.FAILED_AUTH_DELAY)
        # Jeden komunikat na zły login i złe hasło — inaczej dałoby się
        # sprawdzać, które konta istnieją.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny login lub hasło.")

    ratelimit.failed_auth.reset(key)
    token, ttl = admin_auth.issue(konto.login, konto.is_superadmin)
    return {
        "token": token,
        "expiresIn": ttl,
        "login": konto.login,
        "isSuperadmin": konto.is_superadmin,
    }


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    admin_auth.revoke(_bearer(authorization))
    return {"ok": True}


@router.get("/me")
def me(dane: admin_auth.TokenInfo = Depends(require_admin)) -> dict:
    return {"login": dane.login, "isSuperadmin": dane.is_superadmin}


# ── zarządzanie kontami (tylko superadmin) ──────────────────────────────────


def _user_view(konto) -> dict:
    return {
        "login": konto.login,
        "isSuperadmin": konto.is_superadmin,
        "isActive": konto.is_active,
        "createdAt": konto.created_at.isoformat(),
        "lastLoginAt": konto.last_login_at.isoformat() if konto.last_login_at else None,
    }


@router.get("/users")
def list_users(
    _: admin_auth.TokenInfo = Depends(require_superadmin),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    return [_user_view(k) for k in accounts.all_users(db)]


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserIn,
    _: admin_auth.TokenInfo = Depends(require_superadmin),
    db: DbSession = Depends(get_db),
) -> dict:
    try:
        konto = accounts.create(
            db, payload.login, payload.password, is_superadmin=payload.is_superadmin
        )
    except accounts.AccountError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    return _user_view(konto)


@router.patch("/users/{login}")
def update_user(
    login: str,
    payload: UpdateUserIn,
    dane: admin_auth.TokenInfo = Depends(require_superadmin),
    db: DbSession = Depends(get_db),
) -> dict:
    konto = accounts.by_login(db, login)
    if konto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego konta.")

    try:
        if payload.password is not None:
            accounts.set_password(db, konto, payload.password)
        if payload.is_superadmin is not None:
            accounts.set_superadmin(db, konto, payload.is_superadmin)
        if payload.is_active is not None:
            accounts.set_active(db, konto, payload.is_active)
    except accounts.AccountError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    # Odebranie dostępu musi działać od razu, nie po ośmiu godzinach.
    if payload.password is not None or payload.is_active is False:
        admin_auth.revoke_login(konto.login)
    elif payload.is_superadmin is not None:
        # Uprawnienia siedzą w tokenie, więc po zmianie trzeba się przelogować.
        admin_auth.revoke_login(konto.login)

    return _user_view(konto)


@router.delete("/users/{login}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    login: str,
    dane: admin_auth.TokenInfo = Depends(require_superadmin),
    db: DbSession = Depends(get_db),
) -> None:
    konto = accounts.by_login(db, login)
    if konto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma takiego konta.")
    if konto.login == dane.login:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Nie usuwaj własnego konta — stracisz dostęp."
        )

    try:
        accounts.delete(db, konto)
    except accounts.AccountError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    admin_auth.revoke_login(konto.login)


@router.get("/sessions")
def list_sessions(
    _: admin_auth.TokenInfo = Depends(require_admin), db: DbSession = Depends(get_db)
) -> list[dict]:
    """Wszystkie sesje, najnowsze na górze — także te wciąż trwające."""
    wiersze = db.execute(
        select(
            Session,
            func.count(Participant.id).filter(Participant.role != "HOST"),
        )
        .outerjoin(Participant, Participant.session_id == Session.id)
        .group_by(Session.id)
        .order_by(Session.created_at.desc())
    ).all()

    wynik = []
    for session, uczestnicy in wiersze:
        status_enum = session.status_enum
        wynik.append(
            {
                "code": session.code,
                "name": session.name,
                "status": session.status,
                "statusLabel": LABELS[status_enum],
                "isActive": status_enum is not SessionStatus.CLOSED,
                "createdAt": session.created_at.isoformat(),
                "closedAt": session.closed_at.isoformat() if session.closed_at else None,
                "createdBy": session.created_by,
                "participants": uczestnicy or 0,
                "ideas": db.scalar(
                    select(func.count(Idea.id)).where(Idea.session_id == session.id)
                )
                or 0,
            }
        )
    return wynik


def _get(db: DbSession, code: str) -> Session:
    session = db.query(Session).filter(Session.code == codes.normalize(code)).one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma sesji o tym kodzie.")
    return session


@router.get("/sessions/{code}")
def session_detail(
    code: str, _: admin_auth.TokenInfo = Depends(require_admin), db: DbSession = Depends(get_db)
) -> dict:
    """Pełny obraz sesji — wszystko, co po niej zostało.

    Tylko do odczytu. Edycja treści odbywa się w trakcie sesji, z panelu
    admina podpiętego pod jej WebSocket.
    """
    session = _get(db, code)

    decyzje = swipes.decisions(db, session.id)
    plany = assignments.plans(db, session.id)
    terminy = schedules.by_idea(db, session.id)
    przypisania = assignments.assignments_by_idea(db, session.id)
    autorzy = {p.id: p.display_name for p in session.participants}

    return {
        "code": session.code,
        "name": session.name,
        "status": session.status,
        "statusLabel": LABELS[session.status_enum],
        "isActive": session.status_enum is not SessionStatus.CLOSED,
        "createdAt": session.created_at.isoformat(),
        "closedAt": session.closed_at.isoformat() if session.closed_at else None,
        "createdBy": session.created_by,
        "participants": [
            {
                "displayName": p.display_name,
                "role": p.role,
                "isVoting": p.is_voting,
                "joinedAt": p.joined_at.isoformat(),
            }
            for p in session.participants
        ],
        "ideas": [
            {
                "id": idea.id,
                "title": idea.title,
                "description": idea.description,
                "isSpecial": idea.is_special,
                # Pomysł może nie mieć autora — jego autor został usunięty
                # z sesji, a treść została.
                "author": autorzy.get(idea.author_id) if idea.author_id else None,
                "swipeDecision": decyzje.get(idea.id),
                "planDecision": plany.get(idea.id),
                "schedule": terminy[idea.id].label if idea.id in terminy else None,
                "assigned": [w.name for w in przypisania.get(idea.id, [])],
            }
            for idea in list_ideas(db, session.id)
        ],
        "rejected": [
            {"title": idea.title, "reason": powod}
            for idea, powod in assignments.rejected_ideas(db, session.id)
        ],
        "canExport": session.status_enum
        in (SessionStatus.CALENDAR, SessionStatus.CLOSED),
        "exportBase": f"/api/session/{session.code}/export",
    }


@router.delete("/sessions/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    code: str, _: admin_auth.TokenInfo = Depends(require_admin), db: DbSession = Depends(get_db)
) -> None:
    """Skasowanie sesji wraz z całą zawartością.

    Kaskady w kluczach obcych zabierają pomysły, głosy, terminy i przypisania.
    Nie da się tego cofnąć — potwierdzenie jest po stronie interfejsu.
    """
    session = _get(db, code)
    db.delete(session)
    db.commit()
