"""Budowanie snapshotu stanu sesji.

Wysyłamy pełny snapshot, nie deltę. Przy 30 uczestnikach koszt jest pomijalny,
a znika cała klasa błędów desynchronizacji: klient nigdy nie "dokleja" zmian
do stanu, którego mógł nie otrzymać.

Snapshot jest filtrowany per rola. Gość nie dostaje danych, których nie powinien
widzieć — nie liczymy na to, że frontend je ukryje. W trybie zdalnym adres jest
publiczny, więc to nie jest teoretyczne rozważanie.
"""

from sqlalchemy.orm import Session as DbSession

from . import assignments, availability, calendar_view, schedules, swipes
from .ideas import limits as idea_limits
from .ideas import list_ideas
from .models import Idea, Participant, Role, Session
from .participants import voting_participants
from .state_machine import LABELS, SessionStatus, can_advance, next_status
from .urls import looks_unreachable


def _idea_view(idea: Idea, author_names: dict[int, str]) -> dict:
    return {
        "id": idea.id,
        "title": idea.title,
        "description": idea.description,
        "isSpecial": idea.is_special,
        "authorId": idea.author_id,
        # Autor jest jawny: to sesja planowania w gronie znajomych, a nie
        # anonimowa ankieta — wiedza „kto to zaproponował" jest tu użyteczna.
        # Gdyby miało być anonimowo, wystarczy nie wysyłać tych dwóch pól.
        "authorName": author_names.get(idea.author_id, "—"),
        "createdAt": idea.created_at.isoformat(),
    }


def _swiping_section(
    db: DbSession,
    session: Session,
    viewer: Participant | None,
    privileged: bool,
) -> dict:
    """Etap 2 widziany oczami odbiorcy.

    Uczestnik dostaje wyłącznie swoje karty — bez liczników. Podanie mu, ilu
    już zagłosowało na tak, przesądzałoby o jego własnym głosie, a chodzi
    o zdanie każdego z osobna.

    Host i widz dostają tablicę z licznikami: to jest ten ekran, na który
    w opisie „pojawiają się kolejne pomysły, ile przesunięć w prawo, ile
    w lewo".
    """
    pula = swipes.pool(db, session.id)
    podjete = swipes.decisions(db, session.id)
    glosujacych = len(voting_participants(db, session.id))

    section: dict = {"poolSize": len(pula), "votersExpected": glosujacych}

    if viewer is not None and viewer.is_voting:
        moje = swipes.your_swipes(db, viewer.id)
        # Pomysł rozstrzygnięty przez hosta znika z talii: głos i tak nic
        # by już nie zmienił.
        do_zrobienia = [i for i in pula if i.id not in moje and i.id not in podjete]
        section["cards"] = [
            {
                "id": i.id,
                "title": i.title,
                "description": i.description,
            }
            for i in do_zrobienia
        ]
        section["yourDone"] = len(pula) - len(do_zrobienia)
        section["yourTotal"] = len(pula)
        section["youAreDone"] = not do_zrobienia
    else:
        section["cards"] = []
        section["yourDone"] = 0
        section["yourTotal"] = 0
        # Host i admin bez prawa głosu nie mają tu nic do przesuwania.
        section["youAreDone"] = True

    if privileged or viewer is None:
        liczniki = swipes.tally(db, session.id)
        section["board"] = [
            {
                "id": i.id,
                "title": i.title,
                "description": i.description,
                "right": liczniki.get(i.id, {}).get("right", 0),
                "left": liczniki.get(i.id, {}).get("left", 0),
                "voted": sum(liczniki.get(i.id, {}).values()),
                "decision": podjete.get(i.id),
            }
            for i in pula
        ]
        section["decided"] = len(podjete)
        section["accepted"] = sum(1 for v in podjete.values() if v)

    return section


def _scheduling_section(db: DbSession, session: Session, detailed: bool) -> dict:
    """Etap 3 dzieje się na ekranie hosta — telefony tylko czekają.

    Uczestnik dostaje sam postęp. Wystarczy mu, żeby wiedzieć, że coś się
    dzieje i ile jeszcze zostało; pełna lista zamieniłaby jego telefon
    w drugi ekran hosta, a etap z założenia nie jest interaktywny.

    Widz dostaje wszystko — po to, żeby zdalny uczestnik mógł podejrzeć
    ekran prowadzącego.
    """
    pozycje = schedules.agenda(db, session.id)
    ustalone = sum(1 for p in pozycje if p["schedule"] is not None)

    section: dict = {
        "total": len(pozycje),
        "scheduled": ustalone,
        "missing": len(pozycje) - ustalone,
    }
    if detailed:
        section["items"] = pozycje
    return section


def _availability_section(
    db: DbSession,
    session: Session,
    viewer: Participant | None,
    detailed: bool,
) -> dict:
    """Etap 4 — jedno wydarzenie naraz, wszyscy odpowiadają na to samo.

    Uczestnik nie widzi rozkładu odpowiedzi. Pokazanie, że „sześć osób już
    chce", przesądzałoby kolejne deklaracje — a chodzi o to, kto rzeczywiście
    może przyjść, nie o to, za czym idzie większość. Wyniki odsłaniamy
    w etapie 5.
    """
    kolejnosc = availability.order(session)
    biezace_id = availability.current_idea_id(session)

    section: dict = {
        "total": len(kolejnosc),
        "index": session.availability_index,
        "remaining": availability.remaining(session),
        "allPresented": availability.all_presented(session),
        "expected": availability.expected_voters(db, session.id),
        "current": None
        if biezace_id is None
        else availability.event_view(db, session, biezace_id),
        "options": [
            {"value": odp.value, "label": etykieta}
            for odp, etykieta in availability.ANSWER_LABELS.items()
        ],
    }

    if viewer is not None and biezace_id is not None:
        section["yourAnswer"] = availability.your_answer(db, biezace_id, viewer.id)
        section["canAnswer"] = viewer.is_voting and viewer.role_enum is not Role.HOST
    else:
        section["yourAnswer"] = None
        section["canAnswer"] = False

    if detailed and biezace_id is not None:
        section["tally"] = availability.tally(db, biezace_id)
        section["answered"] = sum(section["tally"].values())

    return section


def _assignment_section(db: DbSession, session: Session, viewer: Participant | None) -> dict:
    """Etap 5 — przegląd wydarzeń, przydział wykonawców, zatwierdzenie.

    Wszyscy dostają ten sam ładunek; różni ich tylko to, czy mogą działać.
    Sterowanie jest i tak pilnowane po stronie serwera — `canEdit` służy
    wyłącznie do tego, żeby nie pokazywać przycisków, które i tak odmówią.
    """
    kolejnosc = assignments.order(db, session)
    podjete = assignments.plans(db, session.id)
    biezace = assignments.current(db, session)
    przypisania = assignments.assignments_by_idea(db, session.id)

    def pozycja(idea) -> dict:
        podsumowanie = availability.summary(db, session, ideas_subset=[idea])[0]
        return podsumowanie | {
            "decision": podjete.get(idea.id),
            "assigned": [
                {"id": w.id, "name": w.name, "isParticipant": w.participant_id is not None}
                for w in przypisania.get(idea.id, [])
            ],
        }

    glosujacy = [
        {"id": p.id, "displayName": p.display_name}
        for p in voting_participants(db, session.id)
    ]

    return {
        "total": len(kolejnosc),
        "index": session.assignment_index,
        "decided": len(podjete),
        "confirmed": sum(1 for v in podjete.values() if v),
        "remaining": len(kolejnosc) - len(podjete),
        "isLast": session.assignment_index >= len(kolejnosc) - 1,
        "current": None if biezace is None else pozycja(biezace),
        # Uczestnicy sesji do szybkiego dodania jednym kliknięciem. Wpisać
        # można też kogoś spoza tej listy.
        "roster": glosujacy,
        "answerLabels": {
            odp.value: etykieta for odp, etykieta in availability.ANSWER_LABELS.items()
        },
        "canEdit": viewer is not None and viewer.role_enum is Role.HOST,
        "maxPeople": assignments.MAX_OSOB_NA_WYDARZENIE,
    }


def _admin_section(db: DbSession, session: Session, status: SessionStatus) -> dict:
    """Dane widoczne wyłącznie dla admina — do poprawiania tego, co poszło nie tak.

    Odpowiedzi podajemy dla **bieżącego wydarzenia**, a nie dla wszystkich.
    Pomyłkę zauważa się wtedy, gdy wydarzenie jest na ekranie: albo zaraz po
    kliknięciu w etapie 4, albo przy przeglądaniu w etapie 5. Wysyłanie całej
    macierzy odpowiedzi zawsze byłoby rozdmuchiwaniem snapshotu pod funkcję
    używaną raz na sesję.
    """
    biezace = None
    if status is SessionStatus.AVAILABILITY:
        biezace = availability.current_idea_id(session)
    elif status is SessionStatus.ASSIGNMENT:
        idea = assignments.current(db, session)
        biezace = idea.id if idea else None

    odpowiedzi = []
    if biezace is not None:
        wpisy = {w.participant_id: w for w in availability.answers_for(db, biezace)}
        for osoba in voting_participants(db, session.id):
            wpis = wpisy.get(osoba.id)
            odpowiedzi.append(
                {
                    "participantId": osoba.id,
                    "displayName": osoba.display_name,
                    "answer": wpis.answer if wpis else None,
                    "wasEdited": bool(wpis and wpis.edited_by_admin_at),
                    "originalAnswer": wpis.original_answer if wpis else None,
                }
            )

    return {
        "currentIdeaId": biezace,
        "answers": odpowiedzi,
        "options": [
            {"value": odp.value, "label": etykieta}
            for odp, etykieta in availability.ANSWER_LABELS.items()
        ],
        # Usuwanie wpisów ma sens tylko w etapie 1 — później pomysł ma już
        # głosy i termin, a do pozbycia się go służy odrzucenie.
        "canDeleteIdeas": status is SessionStatus.COLLECTING,
    }


def _participant_public(p: Participant) -> dict:
    """Dane widoczne dla wszystkich — bez tokenów."""
    return {
        "id": p.id,
        "displayName": p.display_name,
        "connected": p.connected,
    }


def _participant_privileged(p: Participant) -> dict:
    """Dodatkowo rola i prawo głosu — tylko dla hosta i admina."""
    return _participant_public(p) | {
        "role": p.role,
        "isVoting": p.is_voting,
    }


def build_snapshot(
    db: DbSession,
    session: Session,
    viewer: Participant | None,
    join_url: str | None = None,
    spectators: int = 0,
) -> dict:
    """Snapshot widziany oczami `viewer`.

    `viewer is None` oznacza widza (rola SPECTATOR, kamień KZ) — dostaje to,
    co host, ale bez czegokolwiek, czym dałoby się sterować sesją.
    """
    status = session.status_enum
    privileged = viewer is not None and viewer.role_enum in (Role.HOST, Role.ADMIN)

    voters = voting_participants(db, session.id)
    people = list(session.participants)
    author_names = {p.id: p.display_name for p in people}
    all_ideas = list_ideas(db, session.id)

    snapshot: dict = {
        "session": {
            "code": session.code,
            "name": session.name,
            "status": status.value,
            "statusLabel": LABELS[status],
            "isActive": status is not SessionStatus.CLOSED,
            "createdAt": session.created_at.isoformat(),
            "closedAt": session.closed_at.isoformat() if session.closed_at else None,
        },
        "counts": {
            # Mianownik wszystkich liczników postępu w etapach 2 i 4.
            "voting": len(voters),
            "votingConnected": sum(1 for p in voters if p.connected),
            "connected": sum(1 for p in people if p.connected),
            "total": len(people),
            # Widzowie nie są uczestnikami: nie ma ich w bazie, nie głosują
            # i nie liczą się do niczego poza tą jedną liczbą.
            "spectators": spectators,
        },
        "you": None,
        "participants": [],
        "ideas": [_idea_view(idea, author_names) for idea in all_ideas],
        "ideaCounts": {
            "total": len(all_ideas),
            "special": sum(1 for idea in all_ideas if idea.is_special),
        },
        # Limity płyną z serwera, żeby frontend nie trzymał własnej kopii,
        # która mogłaby się z nimi rozjechać.
        "limits": idea_limits(),
    }

    if viewer is not None:
        snapshot["you"] = {
            "id": viewer.id,
            "displayName": viewer.display_name,
            "role": viewer.role,
            "isVoting": viewer.is_voting,
            "ideaCount": sum(1 for idea in all_ideas if idea.author_id == viewer.id),
            # Host prowadzi proces i nie bierze w nim udziału — także na etapie 1.
            "canAddIdeas": viewer.role_enum is not Role.HOST,
            "canAddSpecial": viewer.role_enum is Role.ADMIN,
        }

    if privileged or viewer is None:
        snapshot["participants"] = [_participant_privileged(p) for p in people]
    else:
        # Gość widzi, kto jest w sesji — to buduje poczucie wspólnej przestrzeni
        # i nie zdradza niczego wrażliwego. Ale nie widzi ról ani prawa głosu.
        snapshot["participants"] = [
            _participant_public(p) for p in people if p.role_enum is not Role.HOST
        ]

    # Sterowanie dostaje wyłącznie host. Admin ma uprawnienia do treści
    # (wpisy specjalne, korekty), ale nie prowadzi procesu.
    if status is SessionStatus.SWIPING:
        snapshot["swiping"] = _swiping_section(db, session, viewer, privileged)

    if status is SessionStatus.SCHEDULING:
        snapshot["scheduling"] = _scheduling_section(db, session, privileged or viewer is None)

    # Etap 5 odsłania wszystko: głosowanie się skończyło, więc nie ma już czego
    # ukrywać przed uczestnikami. Każdy widzi ten sam kalendarz — także po to,
    # by w K7 mógł go stąd pobrać.
    if status is SessionStatus.CALENDAR:
        snapshot["calendar"] = calendar_view.build(db, session)

    # Pobieranie działa też po zamknięciu sesji — plan zostaje, sesja się kończy.
    if status in (SessionStatus.CALENDAR, SessionStatus.CLOSED):
        snapshot["exports"] = {
            "base": f"/api/session/{session.code}/export",
            "rejectedCount": len(assignments.rejected_ideas(db, session.id)),
        }

    # Etap 5 to moment odsłonięcia: uczestnicy widzą dokładnie to, co host,
    # tylko bez możliwości kliknięcia czegokolwiek.
    if status is SessionStatus.ASSIGNMENT:
        snapshot["assignment"] = _assignment_section(db, session, viewer)

    if status is SessionStatus.AVAILABILITY:
        snapshot["availability"] = _availability_section(
            db, session, viewer, privileged or viewer is None
        )

    if viewer is not None and viewer.role_enum is Role.ADMIN:
        snapshot["admin"] = _admin_section(db, session, status)

    if viewer is not None and viewer.role_enum is Role.HOST:
        upcoming = next_status(status) if can_advance(status) else None
        snapshot["host"] = {
            "canAdvance": can_advance(status),
            # Etykietę następnego etapu liczy serwer — inaczej frontend musiałby
            # trzymać własną kopię sekwencji i obie mogłyby się rozjechać.
            "nextStatus": upcoming.value if upcoming else None,
            "nextLabel": LABELS[upcoming] if upcoming else None,
            "joinUrl": join_url,
            "joinUrlSuspicious": bool(join_url) and looks_unreachable(join_url or ""),
            "qrUrl": f"/api/session/{session.code}/qr.svg",
        }

    return snapshot
