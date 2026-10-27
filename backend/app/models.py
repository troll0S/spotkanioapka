"""Tabele. Na K1 wystarczają dwie — sesja i uczestnik."""

from __future__ import annotations

import enum
from datetime import date as dt_date
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .state_machine import SessionStatus


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    """Trzy role — rozróżnienie przenika cały system.

    HOST  — ekran laptopa. Prowadzi proces, nie głosuje.
    ADMIN — osoba zalogowana hasłem, może być na telefonie. Domyślnie nie głosuje.
    GUEST — uczestnik. Głosuje.
    """

    HOST = "HOST"
    ADMIN = "ADMIN"
    GUEST = "GUEST"


class AdminUser(Base):
    """Konto administratora.

    Zastępuje jedno wspólne hasło ze zmiennej środowiskowej. Powód jest
    praktyczny: przy kilku osobach prowadzących spotkania wspólne hasło
    oznacza, że zmiana dla jednej osoby odcina wszystkie pozostałe, a po
    sesji nie wiadomo, kto ją prowadził.

    `is_superadmin` daje dodatkowo zarządzanie kontami. Poza tym superadmin
    może dokładnie to samo, co zwykły admin.
    """

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))

    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Dezaktywacja zamiast usuwania: sesje, które ta osoba poprowadziła,
    # mają dalej wskazywać na konkretne konto.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(6), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.LOBBY.value)

    # Login konta, które założyło sesję. Zapisany jako tekst, nie klucz obcy:
    # sesja ma pamiętać, kto ją prowadził, nawet gdy konto zniknie.
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Etap 4 — kolejność prezentowania wydarzeń, losowana raz przy wejściu
    # w ten etap i zapisana. Losowanie przy każdym odczycie tasowałoby ekran
    # przy każdym odświeżeniu; a kolejność musi być wspólna dla hosta
    # i wszystkich telefonów.
    availability_order: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability_index: Mapped[int] = mapped_column(Integer, default=0)

    # Etap 5 — na którym wydarzeniu stoi przegląd. Tu kolejność jest
    # chronologiczna, nie losowa: przydzielanie ludzi do zadań czyta się
    # naturalnie od najbliższego terminu.
    assignment_index: Mapped[int] = mapped_column(Integer, default=0)

    participants: Mapped[list[Participant]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Participant.joined_at",
    )
    ideas: Mapped[list["Idea"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        # Najnowsze na górze — lista ma pokazywać, że coś się właśnie dzieje.
        order_by="Idea.created_at.desc()",
    )

    @property
    def status_enum(self) -> SessionStatus:
        return SessionStatus(self.status)


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (UniqueConstraint("session_id", "display_name", name="uq_participant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)

    display_name: Mapped[str] = mapped_column(String(40))

    # Token trafia do localStorage telefonu. Po utracie łączności klient wraca
    # z tym samym tokenem i odzyskuje tożsamość wraz z dotychczasowymi głosami.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    role: Mapped[str] = mapped_column(String(10), default=Role.GUEST.value)

    # HOST zawsze False. ADMIN domyślnie False, ale z przełącznikiem przy
    # dołączaniu — na wypadek, gdy proces prowadzi kto inny niż admin.
    is_voting: Mapped[bool] = mapped_column(Boolean, default=True)

    connected: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[Session] = relationship(back_populates="participants")

    @property
    def role_enum(self) -> Role:
        return Role(self.role)


class Idea(Base):
    """Pomysł z etapu 1.

    `is_special` to wpis admina, którego nie da się odrzucić: pomija etap 2
    w całości (nikt go nie swipe'uje, host go nie ocenia), ale bierze pełny
    udział w etapach 3, 4 i 5 — dostaje termin, uczestnicy deklarują przy nim
    dostępność, trafia do kalendarza.
    """

    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)

    # Pole jest opcjonalne, bo pomysł może przeżyć swojego autora: gdy admin
    # usuwa uczestnika, najpierw odpinamy od niego pomysły (patrz
    # `admin_ops.remove_participant`), a dopiero potem kasujemy osobę.
    # Kaskada zostaje jako zabezpieczenie przy kasowaniu całej sesji.
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_special: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    session: Mapped[Session] = relationship(back_populates="ideas")
    author: Mapped[Participant] = relationship()


class Direction(str, enum.Enum):
    RIGHT = "RIGHT"  # tak
    LEFT = "LEFT"  # nie


class Swipe(Base):
    """Głos uczestnika z etapu 2.

    Doradczy: ostateczne zdanie ma host. Te głosy są dla niego obrazem tego,
    co myśli grupa — nie automatem, który za niego decyduje.
    """

    __tablename__ = "swipes"
    __table_args__ = (UniqueConstraint("idea_id", "participant_id", name="uq_swipe_once"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )

    direction: Mapped[str] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Answer(str, enum.Enum):
    WANT = "WANT"  # chcę
    CAN = "CAN"  # mogę
    DONT_WANT = "DONT_WANT"  # nie chcę
    ABSOLUTELY_NOT = "ABSOLUTELY_NOT"  # absolutnie nie


class Availability(Base):
    """Deklaracja uczestnika z etapu 4.

    Samo istnienie wiersza jest blokadą — gość odpowiada raz i nie może się
    rozmyślić. Nie trzymamy osobnej flagi `locked`, bo mogłaby rozjechać się
    z rzeczywistością; wiersz jest albo go nie ma.

    Korekta jest możliwa **wyłącznie z panelu admina** (K8). Wtedy poprzednia
    wartość ląduje w `original_answer`, żeby przy przeglądaniu archiwum dało
    się odróżnić głos uczestnika od poprawki.
    """

    __tablename__ = "availabilities"
    __table_args__ = (
        UniqueConstraint("idea_id", "participant_id", name="uq_availability_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )

    answer: Mapped[str] = mapped_column(String(16))

    original_answer: Mapped[str | None] = mapped_column(String(16), nullable=True)
    edited_by_admin_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def answer_enum(self) -> Answer:
        return Answer(self.answer)


class EventPlan(Base):
    """Rozstrzygnięcie z etapu 5: czy wydarzenie wchodzi do kalendarza.

    Odrzucone tutaj znika z kalendarza i z eksportów — mimo że przeszło
    etap 2 i dostało termin. To ostatnia brama przed planem końcowym.
    """

    __tablename__ = "event_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(
        ForeignKey("ideas.id", ondelete="CASCADE"), unique=True, index=True
    )
    confirmed: Mapped[bool] = mapped_column(Boolean)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventAssignment(Base):
    """Osoba przypisana do wydarzenia w etapie 5.

    `participant_id` bywa puste i to jest zamierzone: przypisać można kogoś
    z sesji, ale też osobę, której w sesji nie było — „Marek z pracy",
    „tata", „ktoś z wypożyczalni". Dlatego nazwisko trzymamy zawsze jako
    tekst, a powiązanie z uczestnikiem jest tylko dodatkiem.
    """

    __tablename__ = "event_assignments"
    __table_args__ = (UniqueConstraint("idea_id", "name", name="uq_assignment_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participants.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScheduleKind(str, enum.Enum):
    EXACT_DATE = "EXACT_DATE"  # konkretny dzień
    WEEK = "WEEK"  # któryś dzień w danym tygodniu
    RANGE = "RANGE"  # przedział dat
    MONTH = "MONTH"  # gdzieś w tym miesiącu


class Schedule(Base):
    """Termin pomysłu z etapu 3.

    Cztery rodzaje terminu trzymamy **zawsze** jako przedział `(date_from,
    date_to)` plus `kind` do wyświetlania. To ta jedna decyzja sprawia, że
    kalendarz z etapu 5 oraz eksport do PDF-a i ICS-a mają do obsłużenia jeden
    kształt danych, a nie cztery osobne przypadki.

    `label` jest wyliczoną etykietą po polsku — zapisaną, żeby wszystkie widoki
    i eksporty mówiły o terminie dokładnie tak samo.
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(
        ForeignKey("ideas.id", ondelete="CASCADE"), unique=True, index=True
    )

    kind: Mapped[str] = mapped_column(String(12))
    date_from: Mapped[dt_date] = mapped_column(Date)
    date_to: Mapped[dt_date] = mapped_column(Date)
    label: Mapped[str] = mapped_column(String(80))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def kind_enum(self) -> ScheduleKind:
        return ScheduleKind(self.kind)


class HostDecision(Base):
    """Rozstrzygnięcie hosta — jedyne, które się liczy.

    Wprost z opisu: „w momencie kiedy host przesunie na którąś ze stron to
    wtedy dopiero jest zatwierdzony i ostateczny niezależnie od poprzednich
    głosów".
    """

    __tablename__ = "host_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(
        ForeignKey("ideas.id", ondelete="CASCADE"), unique=True, index=True
    )
    accepted: Mapped[bool] = mapped_column(Boolean)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
