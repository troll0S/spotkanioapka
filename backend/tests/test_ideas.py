"""Reguły etapu 1. Najważniejsze: kto może co i czego nie da się odrzucić."""

import pytest

from app import ideas
from app.ideas import IdeaError
from app.models import Role
from app.state_machine import SessionStatus


@pytest.fixture()
def zbieranie(db, sample_session):
    """Sesja przestawiona na etap 1 — inaczej każda operacja jest odrzucana."""
    sample_session.status = SessionStatus.COLLECTING.value
    db.commit()
    return sample_session


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


# ── podstawy ────────────────────────────────────────────────────────────────


def test_gosc_dodaje_pomysl(db, zbieranie):
    idea = ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ania"), "Wyjazd w góry")

    assert idea.title == "Wyjazd w góry"
    assert idea.description is None
    assert idea.is_special is False
    assert ideas.list_ideas(db, zbieranie.id) == [idea]


def test_opis_jest_opcjonalny_i_obcinany(db, zbieranie):
    idea = ideas.create_idea(
        db, zbieranie, osoba(zbieranie, "Ania"), "  Kino  ", "   "
    )

    assert idea.title == "Kino", "tytuł przycięty z białych znaków"
    assert idea.description is None, "opis z samych spacji to brak opisu"


def test_pusty_tytul_odrzucony(db, zbieranie):
    with pytest.raises(IdeaError, match="tytuł"):
        ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ania"), "   ")


def test_zbyt_dlugi_tytul_odrzucony(db, zbieranie):
    with pytest.raises(IdeaError, match="znaków"):
        ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ania"), "x" * 121)


def test_limit_na_osobe(db, zbieranie):
    ania = osoba(zbieranie, "Ania")
    for i in range(ideas.MAX_PER_PARTICIPANT):
        ideas.create_idea(db, zbieranie, ania, f"Pomysł {i}")

    with pytest.raises(IdeaError, match="maksimum"):
        ideas.create_idea(db, zbieranie, ania, "O jeden za dużo")

    # Limit jest na osobę, nie na sesję.
    ideas.create_idea(db, zbieranie, osoba(zbieranie, "Bartek"), "Mój pierwszy")
    assert len(ideas.list_ideas(db, zbieranie.id)) == ideas.MAX_PER_PARTICIPANT + 1


# ── kto może dodawać ────────────────────────────────────────────────────────


def test_host_nie_dodaje_pomyslow(db, zbieranie):
    """Host prowadzi proces i nie bierze w nim udziału — także na etapie 1."""
    with pytest.raises(IdeaError, match="prowadzącego"):
        ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ekran"), "Mój pomysł")


def test_tylko_admin_dodaje_wpisy_specjalne(db, zbieranie):
    with pytest.raises(IdeaError, match="administrator"):
        ideas.create_idea(
            db, zbieranie, osoba(zbieranie, "Ania"), "Ustalone", is_special=True
        )


def test_admin_dodaje_wpis_specjalny(db, zbieranie):
    idea = ideas.create_idea(
        db,
        zbieranie,
        osoba(zbieranie, "Admin"),
        "Urodziny babci",
        "Tego nie przeskoczymy",
        is_special=True,
    )

    assert idea.is_special is True
    assert idea.description == "Tego nie przeskoczymy"


def test_admin_moze_dodac_zwykly_pomysl(db, zbieranie):
    """Admin to osoba z uprawnieniami, nie osobny tryb — zwykły wpis też może."""
    idea = ideas.create_idea(db, zbieranie, osoba(zbieranie, "Admin"), "Kręgle")
    assert idea.is_special is False


# ── edycja i usuwanie ───────────────────────────────────────────────────────


def test_autor_edytuje_swoj_pomysl(db, zbieranie):
    ania = osoba(zbieranie, "Ania")
    idea = ideas.create_idea(db, zbieranie, ania, "Kino")

    zmieniony = ideas.update_idea(db, zbieranie, ania, idea.id, "Kino letnie", "W parku")

    assert zmieniony.title == "Kino letnie"
    assert zmieniony.description == "W parku"


def test_nie_da_sie_edytowac_cudzego_pomyslu(db, zbieranie):
    idea = ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ania"), "Kino")

    with pytest.raises(IdeaError, match="tylko swoje"):
        ideas.update_idea(db, zbieranie, osoba(zbieranie, "Bartek"), idea.id, "Przejmuję")


def test_admin_tez_nie_rusza_cudzych_wpisow_na_tym_etapie(db, zbieranie):
    """Moderacja cudzych wpisów to uprawnienie z panelu admina (K8)."""
    idea = ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ania"), "Kino")

    with pytest.raises(IdeaError, match="tylko swoje"):
        ideas.update_idea(db, zbieranie, osoba(zbieranie, "Admin"), idea.id, "Zmieniam")


def test_autor_usuwa_swoj_pomysl(db, zbieranie):
    ania = osoba(zbieranie, "Ania")
    idea = ideas.create_idea(db, zbieranie, ania, "Kino")

    ideas.delete_idea(db, zbieranie, ania, idea.id)

    assert ideas.list_ideas(db, zbieranie.id) == []


def test_nie_da_sie_usunac_cudzego_pomyslu(db, zbieranie):
    idea = ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ania"), "Kino")

    with pytest.raises(IdeaError, match="tylko swoje"):
        ideas.delete_idea(db, zbieranie, osoba(zbieranie, "Bartek"), idea.id)


def test_nieistniejacy_pomysl(db, zbieranie):
    with pytest.raises(IdeaError, match="Nie ma takiego"):
        ideas.update_idea(db, zbieranie, osoba(zbieranie, "Ania"), 9999, "Cokolwiek")


# ── brama etapu ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [
        SessionStatus.LOBBY,
        SessionStatus.SWIPING,
        SessionStatus.SCHEDULING,
        SessionStatus.AVAILABILITY,
        SessionStatus.CALENDAR,
        SessionStatus.CLOSED,
    ],
)
def test_poza_etapem_1_nie_da_sie_nic_dodac(db, sample_session, status):
    """Po zamknięciu etapu 1 lista pomysłów jest zamknięta na dobre."""
    sample_session.status = status.value
    db.commit()

    with pytest.raises(IdeaError, match="nie jest aktywny"):
        ideas.create_idea(db, sample_session, osoba(sample_session, "Ania"), "Za późno")


def test_po_zamknieciu_etapu_nie_da_sie_edytowac(db, zbieranie):
    ania = osoba(zbieranie, "Ania")
    idea = ideas.create_idea(db, zbieranie, ania, "Kino")

    zbieranie.status = SessionStatus.SWIPING.value
    db.commit()

    with pytest.raises(IdeaError, match="nie jest aktywny"):
        ideas.update_idea(db, zbieranie, ania, idea.id, "Poprawka")
    with pytest.raises(IdeaError, match="nie jest aktywny"):
        ideas.delete_idea(db, zbieranie, ania, idea.id)


# ── snapshot ────────────────────────────────────────────────────────────────


def test_snapshot_zawiera_pomysly_i_liczniki(db, zbieranie):
    from app.snapshots import build_snapshot

    ideas.create_idea(db, zbieranie, osoba(zbieranie, "Ania"), "Kino")
    ideas.create_idea(
        db, zbieranie, osoba(zbieranie, "Admin"), "Urodziny", is_special=True
    )

    snap = build_snapshot(db, zbieranie, osoba(zbieranie, "Ania"))

    assert snap["ideaCounts"] == {"total": 2, "special": 1}
    assert snap["you"]["ideaCount"] == 1
    assert snap["you"]["canAddIdeas"] is True
    assert snap["you"]["canAddSpecial"] is False

    specjalny = next(i for i in snap["ideas"] if i["isSpecial"])
    assert specjalny["authorName"] == "Admin"


def test_snapshot_hosta_mowi_ze_nie_dodaje_pomyslow(db, zbieranie):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, zbieranie, osoba(zbieranie, "Ekran"))

    assert snap["you"]["canAddIdeas"] is False
    assert snap["you"]["canAddSpecial"] is False


def test_snapshot_admina_pozwala_na_wpisy_specjalne(db, zbieranie):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, zbieranie, osoba(zbieranie, "Admin"))

    assert snap["you"]["canAddIdeas"] is True
    assert snap["you"]["canAddSpecial"] is True


def test_cudzy_wpis_nie_rusza_mojego_licznika(db, zbieranie):
    """Niezmiennik, na którym stoi czyszczenie pola na telefonie.

    Formularz kasuje wpisany tytuł dopiero wtedy, gdy **moja** liczba wpisów
    wzrośnie — czyli gdy serwer potwierdzi mój zapis. Wcześniej patrzył na
    licznik całej sesji i czyjekolwiek dodanie pomysłu kasowało tekst
    wszystkim, którzy akurat pisali.
    """
    from app.snapshots import build_snapshot

    ania = osoba(zbieranie, "Ania")
    przed = build_snapshot(db, zbieranie, ania)

    ideas.create_idea(db, zbieranie, osoba(zbieranie, "Bartek"), "Pomysł Bartka")
    po = build_snapshot(db, zbieranie, ania)

    assert po["ideaCounts"]["total"] == przed["ideaCounts"]["total"] + 1
    assert po["you"]["ideaCount"] == przed["you"]["ideaCount"], "cudzy wpis, mój licznik stoi"

    ideas.create_idea(db, zbieranie, ania, "Pomysł Ani")
    moj = build_snapshot(db, zbieranie, ania)
    assert moj["you"]["ideaCount"] == przed["you"]["ideaCount"] + 1, "własny wpis podnosi licznik"


def test_najnowsze_pomysly_na_gorze(db, zbieranie):
    ania = osoba(zbieranie, "Ania")
    pierwszy = ideas.create_idea(db, zbieranie, ania, "Pierwszy")
    drugi = ideas.create_idea(db, zbieranie, ania, "Drugi")

    lista = ideas.list_ideas(db, zbieranie.id)
    assert [i.id for i in lista] == [drugi.id, pierwszy.id]
