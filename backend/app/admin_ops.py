"""Uprawnienia administratora — rzeczy, których nie wolno nikomu innemu.

Wszystkie operacje tutaj świadomie omijają reguły, które chronią zwykły
przebieg sesji: blokadę odpowiedzi, autorstwo wpisów, nienaruszalność składu.
Dlatego siedzą w osobnym module — żeby było widać, że to wyjątki, a nie
zwykła ścieżka.

Czego tu **nie ma**: sterowania etapami. To zostaje przy roli HOST, także dla
admina. Admin poprawia treść, prowadzący prowadzi.
"""

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from .models import Answer, Availability, Idea, Participant, Role, Session
from .state_machine import SessionStatus


class AdminError(Exception):
    """Naruszenie reguł panelu admina — komunikat jest dla użytkownika."""


def _require_admin(participant: Participant) -> None:
    if participant.role_enum is not Role.ADMIN:
        raise AdminError("To uprawnienie ma tylko administrator.")


# ── korekta odpowiedzi z etapu 4 ────────────────────────────────────────────


def correct_answer(
    db: DbSession,
    session: Session,
    actor: Participant,
    idea_id: int,
    participant_id: int,
    value: str,
) -> Availability:
    """Zmiana zablokowanej odpowiedzi — jedyna droga do jej poprawienia.

    Uczestnik odpowiada raz i nie może się rozmyślić; cztery duże przyciski
    na telefonie bardzo łatwo kliknąć nie tam, gdzie się chciało. Ta funkcja
    jest furtką na takie pomyłki.

    Poprzednia wartość ląduje w `original_answer`, więc przy przeglądaniu
    archiwum widać, co było głosem uczestnika, a co poprawką.
    """
    _require_admin(actor)

    try:
        nowa = Answer(value)
    except ValueError:
        raise AdminError("Nieznana odpowiedź.") from None

    wpis = db.scalar(
        select(Availability)
        .where(Availability.idea_id == idea_id)
        .where(Availability.participant_id == participant_id)
    )

    if wpis is None:
        # Admin może też odpowiedzieć za kogoś, kto nie zdążył — na przykład
        # za osobę, której padł telefon w trakcie rundy.
        idea = db.get(Idea, idea_id)
        osoba = db.get(Participant, participant_id)
        if idea is None or idea.session_id != session.id:
            raise AdminError("Nie ma takiego wydarzenia.")
        if osoba is None or osoba.session_id != session.id:
            raise AdminError("Nie ma takiego uczestnika.")

        wpis = Availability(
            idea_id=idea_id,
            participant_id=participant_id,
            answer=nowa.value,
            edited_by_admin_at=datetime.now(timezone.utc),
        )
        db.add(wpis)
    else:
        if wpis.answer == nowa.value:
            return wpis
        # Zapisujemy tylko pierwotną odpowiedź uczestnika, nie każdą kolejną
        # poprawkę — chodzi o odróżnienie głosu od korekty, nie o historię.
        if wpis.original_answer is None:
            wpis.original_answer = wpis.answer
        wpis.answer = nowa.value
        wpis.edited_by_admin_at = datetime.now(timezone.utc)

    db.commit()
    return wpis


# ── moderacja pomysłów ──────────────────────────────────────────────────────


def edit_idea(
    db: DbSession,
    session: Session,
    actor: Participant,
    idea_id: int,
    title: str | None = None,
    description: str | None = None,
) -> Idea:
    """Poprawka cudzego wpisu — literówka, obraźliwe słowo, zbędny szczegół.

    Inaczej niż w etapie 1, gdzie każdy rusza tylko swoje. Działa na każdym
    etapie, bo literówka w tytule przeszkadza najbardziej wtedy, gdy wydarzenie
    trafia już do kalendarza.
    """
    _require_admin(actor)

    idea = db.get(Idea, idea_id)
    if idea is None or idea.session_id != session.id:
        raise AdminError("Nie ma takiego pomysłu.")

    if title is not None:
        czysty = title.strip()
        if not czysty:
            raise AdminError("Tytuł nie może być pusty.")
        if len(czysty) > 120:
            raise AdminError("Tytuł może mieć najwyżej 120 znaków.")
        idea.title = czysty

    if description is not None:
        czysty = description.strip()
        if len(czysty) > 500:
            raise AdminError("Opis może mieć najwyżej 500 znaków.")
        idea.description = czysty or None

    db.commit()
    return idea


def delete_idea(db: DbSession, session: Session, actor: Participant, idea_id: int) -> None:
    """Usunięcie cudzego wpisu.

    Dozwolone wyłącznie w etapie 1. Później pomysł ma już głosy, termin,
    deklaracje i być może przypisane osoby — wyrwanie go spod tego wszystkiego
    zostawiłoby sesję w stanie, którego nikt nie zamawiał. Od etapu 2 służy
    do tego odrzucenie, które zostawia ślad.
    """
    _require_admin(actor)

    if session.status_enum is not SessionStatus.COLLECTING:
        raise AdminError(
            "Pomysły można usuwać tylko w etapie 1. Później użyj odrzucenia."
        )

    idea = db.get(Idea, idea_id)
    if idea is None or idea.session_id != session.id:
        raise AdminError("Nie ma takiego pomysłu.")

    db.delete(idea)
    db.commit()


# ── skład sesji ─────────────────────────────────────────────────────────────


def remove_participant(
    db: DbSession, session: Session, actor: Participant, participant_id: int
) -> str:
    """Usunięcie uczestnika — zwykle kogoś, kto dołączył dwa razy.

    Jego głosy i deklaracje znikają razem z nim: bez osoby nic nie znaczą,
    a zostawione psułyby liczniki. **Pomysły zostają**, tylko tracą autora —
    treść, dla której sesja się odbyła, nie może wylatywać przy porządkach.
    """
    _require_admin(actor)

    osoba = db.get(Participant, participant_id)
    if osoba is None or osoba.session_id != session.id:
        raise AdminError("Nie ma takiego uczestnika.")
    if osoba.role_enum is Role.HOST:
        raise AdminError("Nie da się usunąć ekranu prowadzącego.")
    if osoba.id == actor.id:
        raise AdminError("Nie usuwaj samego siebie — stracisz dostęp do panelu.")

    imie = osoba.display_name

    # Odpinamy autorstwo PRZED usunięciem osoby. Gdyby zrobić to odwrotnie,
    # kaskada klucza obcego zabrałaby pomysły ze sobą.
    db.execute(
        update(Idea).where(Idea.author_id == osoba.id).values(author_id=None)
    )
    db.delete(osoba)
    db.commit()
    return imie
