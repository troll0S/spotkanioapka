"""REST: tworzenie sesji, dołączanie, awans na admina, kod QR."""

import io
import time

import segno
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from .. import accounts, admin_auth, codes, participants as people, ratelimit, urls
from ..db import get_db
from ..models import Participant, Role, Session
from ..realtime import broadcast_state
from ..schemas import CreateSessionIn, IdentityOut, JoinIn, PromoteIn, SessionInfoOut
from ..security import new_token
from ..state_machine import LABELS, SessionStatus

router = APIRouter(prefix="/api", tags=["sesja"])


def _get_session(db: DbSession, code: str) -> Session:
    session = db.query(Session).filter(Session.code == codes.normalize(code)).one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma sesji o tym kodzie.")
    return session


def _identity(session: Session, participant: Participant) -> IdentityOut:
    return IdentityOut(
        code=session.code,
        token=participant.token,
        participant_id=participant.id,
        display_name=participant.display_name,
        role=participant.role,
        is_voting=participant.is_voting,
    )


def _guard_auth(request: Request) -> str:
    """Odrzuca dalsze próby hasła, gdy z tego adresu było ich już zbyt wiele."""
    key = ratelimit.client_key(request.headers, request.client.host if request.client else None)
    if ratelimit.failed_auth.exceeded(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zbyt wiele nieudanych prób. Spróbuj później.",
            headers={"Retry-After": str(ratelimit.failed_auth.retry_after(key))},
        )
    return key


def _reject_credentials(key: str) -> None:
    ratelimit.failed_auth.hit(key)
    if ratelimit.FAILED_AUTH_DELAY:
        time.sleep(ratelimit.FAILED_AUTH_DELAY)
    # Jeden komunikat na zły login i złe hasło — inaczej dałoby się sprawdzać,
    # które konta istnieją.
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Błędny login lub hasło.")


def _login(db: DbSession, request: Request, login: str, password: str):
    """Logowanie kontem administratora, pod limitem prób."""
    key = _guard_auth(request)
    konto = accounts.authenticate(db, login, password)
    if konto is None:
        _reject_credentials(key)
    ratelimit.failed_auth.reset(key)
    return konto


def _resolve_admin(db: DbSession, request: Request, login: str | None, password: str | None):
    """Konto administratora — z tokenu panelu albo z loginu i hasła.

    Token ma pierwszeństwo: kto jest już zalogowany, nie powinien podawać
    danych drugi raz tylko dlatego, że przeszedł z archiwum na ekran
    prowadzącego. To jedno logowanie na całą aplikację.
    """
    naglowek = request.headers.get("authorization") or ""
    token = naglowek[7:].strip() if naglowek.lower().startswith("bearer ") else ""

    dane = admin_auth.info(token)
    if dane is not None:
        konto = accounts.by_login(db, dane.login)
        if konto is None or not konto.is_active:
            # Konto zniknęło albo zostało wyłączone w trakcie — token wciąż
            # istnieje, ale nie reprezentuje już nikogo uprawnionego.
            admin_auth.revoke(token)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Twoje konto straciło dostęp. Zaloguj się ponownie.",
            )
        return konto

    if not login or not password:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Zaloguj się jako administrator."
        )
    return _login(db, request, login, password)


@router.post("/session", response_model=IdentityOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: CreateSessionIn, request: Request, db: DbSession = Depends(get_db)
) -> IdentityOut:
    """Zakłada sesję i tworzy uczestnika w roli HOST.

    Wymaga konta administratora — bez tego każdy w sieci mógłby zakładać
    sesje, a w trybie zdalnym każdy w internecie.
    """
    accounts.bootstrap(db)
    if accounts.count(db) == 0:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Nie ma żadnego konta administratora. Ustaw ADMIN_PASSWORD w pliku .env "
            f"({accounts.WYMAGANIA_HASLA}) i uruchom aplikację ponownie.",
        )

    konto = _resolve_admin(db, request, payload.login, payload.password)

    session = Session(
        code=codes.unique_code(db),
        name=payload.name.strip(),
        status=SessionStatus.LOBBY.value,
        # Sesja pamięta, kto ją prowadził — przydaje się w archiwum.
        created_by=konto.login,
    )
    db.add(session)
    db.flush()

    host = Participant(
        session_id=session.id,
        display_name=payload.host_name.strip(),
        token=new_token(),
        role=Role.HOST.value,
        is_voting=False,  # host prowadzi, nie głosuje
    )
    db.add(host)
    db.commit()

    return _identity(session, host)


@router.get("/session/{code}", response_model=SessionInfoOut)
def session_info(code: str, db: DbSession = Depends(get_db)) -> SessionInfoOut:
    """Minimum dla ekranu dołączania — bez składu sesji."""
    session = _get_session(db, code)
    return SessionInfoOut(
        code=session.code,
        name=session.name,
        status=session.status,
        status_label=LABELS[session.status_enum],
        is_active=session.status_enum is not SessionStatus.CLOSED,
        participants=len(session.participants),
    )


@router.post("/session/{code}/join", response_model=IdentityOut)
async def join(
    code: str, payload: JoinIn, request: Request, db: DbSession = Depends(get_db)
) -> IdentityOut:
    """Dołączenie gościa albo powrót po utracie łączności.

    Token z localStorage ma pierwszeństwo: jeśli pasuje do tej sesji, oddajemy
    tę samą tożsamość razem z dotychczasową rolą. Bez tego każde odświeżenie
    strony tworzyłoby nowego uczestnika i psuło liczniki.
    """
    session = _get_session(db, code)

    if payload.token:
        existing = people.by_token(db, payload.token)
        if existing is not None and existing.session_id == session.id:
            # Powrót po utracie łączności nie jest nową próbą — nie liczymy go.
            return _identity(session, existing)

    join_key = ratelimit.client_key(
        request.headers, request.client.host if request.client else None
    )
    if ratelimit.joins.exceeded(join_key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Zbyt wiele prób dołączenia. Odczekaj chwilę.",
            headers={"Retry-After": str(ratelimit.joins.retry_after(join_key))},
        )
    ratelimit.joins.hit(join_key)

    if session.status_enum is SessionStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ta sesja jest już zakończona.")

    name = payload.display_name.strip()
    if people.by_name(db, session.id, name) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Ktoś w tej sesji ma już nick „{name}”. Wybierz inny.",
        )

    participant = Participant(
        session_id=session.id,
        display_name=name,
        token=new_token(),
        role=Role.GUEST.value,
        is_voting=True,
    )
    db.add(participant)
    db.commit()

    await broadcast_state(db, session)
    return _identity(session, participant)


@router.post("/session/{code}/promote", response_model=IdentityOut)
async def promote(
    code: str, payload: PromoteIn, request: Request, db: DbSession = Depends(get_db)
) -> IdentityOut:
    """Awans dołączonego uczestnika na ADMIN-a — działa także z telefonu.

    Nie budujemy osobnego przepływu dołączania: to ta sama sesja WebSocket,
    tylko z podniesionymi uprawnieniami i przebudowanym snapshotem.
    """
    session = _get_session(db, code)
    participant = people.by_token(db, payload.token)

    if participant is None or participant.session_id != session.id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nieznany token uczestnika.")
    if participant.role_enum is Role.HOST:
        raise HTTPException(status.HTTP_409_CONFLICT, "Host ma już pełne uprawnienia.")

    _resolve_admin(db, request, payload.login, payload.password)

    participant.role = Role.ADMIN.value
    # Domyślnie admin nie głosuje — zwykle to ta sama osoba, co host.
    # Przełącznik istnieje na wypadek, gdy proces prowadzi kto inny.
    participant.is_voting = payload.is_voting
    db.commit()

    await broadcast_state(db, session)
    return _identity(session, participant)


@router.get("/session/{code}/qr.svg")
def qr_code(
    code: str,
    request: Request,
    origin: str | None = None,
    db: DbSession = Depends(get_db),
) -> Response:
    """Kod QR z adresem dołączania.

    `origin` pozwala ekranowi hosta nadpisać adres — przydaje się, gdy host
    wszedł przez `localhost` albo gdy trzeba wskazać adres tunelu.
    """
    session = _get_session(db, code)
    target = urls.join_url(
        session.code,
        request.headers.get("host"),
        urls.scheme_from(request.headers, request.url.scheme),
        origin,
    )

    # BytesIO, nie StringIO — segno zapisuje bajty także dla SVG.
    buffer = io.BytesIO()
    segno.make(target, error="m").save(buffer, kind="svg", scale=8, border=2, dark="#0f172a")
    return Response(
        content=buffer.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )
