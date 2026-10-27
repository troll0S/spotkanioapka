"""Pobieranie wyników sesji.

Zwykłe adresy GET, bo pliki pobiera przeglądarka zwykłym linkiem — nie da się
tego zrobić przez WebSocket, którym płynie reszta aplikacji.

Dostęp: sam kod sesji, ale wyłącznie po jej zakończeniu (etap 6 albo sesja
zamknięta). Kod wystarcza również do dołączenia, więc nie odsłaniamy tu niczego,
czego uczestnik nie zobaczyłby na własnym ekranie.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session as DbSession

from .. import codes, exports
from ..db import get_db
from ..models import Session
from ..state_machine import SessionStatus

router = APIRouter(prefix="/api/session/{code}/export", tags=["eksport"])

#: Etapy, na których wyniki są już ostateczne.
GOTOWE = (SessionStatus.CALENDAR, SessionStatus.CLOSED)


def _session_ready(code: str, db: DbSession) -> Session:
    session = db.query(Session).filter(Session.code == codes.normalize(code)).one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie ma sesji o tym kodzie.")
    if session.status_enum not in GOTOWE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Sesja jeszcze trwa — pobieranie będzie możliwe po ustaleniu planu.",
        )
    return session


def _download(content: bytes, media_type: str, filename: str) -> Response:
    # filename* z kodowaniem UTF-8 — bez tego polskie znaki w nazwie sesji
    # zamieniają się w krzaki albo psują nagłówek.
    dyspozycja = f"attachment; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": dyspozycja, "Cache-Control": "no-store"},
    )


@router.get("/calendar.pdf")
def calendar_pdf(code: str, layout: str = "calendar", db: DbSession = Depends(get_db)) -> Response:
    """Kalendarz do wydruku. `layout=list` pomija siatkę i zostawia samą listę."""
    session = _session_ready(code, db)
    if layout not in ("calendar", "list"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nieznany układ.")

    return _download(
        exports.calendar_pdf(db, session, layout),
        "application/pdf",
        exports.safe_filename(session.name, "plan.pdf"),
    )


@router.get("/calendar.ics")
def calendar_ics(code: str, db: DbSession = Depends(get_db)) -> Response:
    """Wydarzenia do kalendarza w telefonie."""
    session = _session_ready(code, db)
    return _download(
        exports.calendar_ics(db, session),
        "text/calendar; charset=utf-8",
        exports.safe_filename(session.name, "plan.ics"),
    )


@router.get("/calendar.csv")
def calendar_csv(code: str, db: DbSession = Depends(get_db)) -> Response:
    session = _session_ready(code, db)
    return _download(
        exports.calendar_csv(db, session),
        "text/csv; charset=utf-8",
        exports.safe_filename(session.name, "plan.csv"),
    )


@router.get("/rejected.pdf")
def rejected_pdf(code: str, db: DbSession = Depends(get_db)) -> Response:
    """Pomysły, które nie weszły do planu — odrzucone na dowolnym etapie."""
    session = _session_ready(code, db)
    return _download(
        exports.rejected_pdf(db, session),
        "application/pdf",
        exports.safe_filename(session.name, "odrzucone.pdf"),
    )


@router.get("/rejected.txt")
def rejected_txt(code: str, db: DbSession = Depends(get_db)) -> Response:
    session = _session_ready(code, db)
    return _download(
        exports.rejected_txt(db, session),
        "text/plain; charset=utf-8",
        exports.safe_filename(session.name, "odrzucone.txt"),
    )
