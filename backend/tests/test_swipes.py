"""Reguły etapu 2.

Najważniejsza z nich jest wprost z opisu: decyzja hosta jest ostateczna
niezależnie od tego, jak zagłosowali pozostali.
"""

import pytest

from app import ideas, swipes
from app.models import Direction, Role
from app.state_machine import SessionStatus
from app.swipes import SwipeError


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


@pytest.fixture()
def wybieranie(db, sample_session):
    """Sesja z trzema zwykłymi pomysłami i jednym ustalonym, na etapie 2."""
    sample_session.status = SessionStatus.COLLECTING.value
    db.commit()

    ania = osoba(sample_session, "Ania")
    admin = osoba(sample_session, "Admin")
    ideas.create_idea(db, sample_session, ania, "Kajaki")
    ideas.create_idea(db, sample_session, ania, "Kino")
    ideas.create_idea(db, sample_session, osoba(sample_session, "Bartek"), "Kręgle")
    ideas.create_idea(db, sample_session, admin, "Urodziny babci", is_special=True)

    sample_session.status = SessionStatus.SWIPING.value
    db.commit()
    return sample_session


def pomysl(db, session, tytul):
    return next(i for i in ideas.list_ideas(db, session.id) if i.title == tytul)


# ── pula ────────────────────────────────────────────────────────────────────


def test_wpis_ustalony_nie_wchodzi_do_puli(db, wybieranie):
    """Nie da się go odrzucić, więc nie ma o czym głosować."""
    tytuly = [i.title for i in swipes.pool(db, wybieranie.id)]

    assert tytuly == ["Kajaki", "Kino", "Kręgle"]
    assert "Urodziny babci" not in tytuly


def test_nie_da_sie_zaglosowac_na_wpis_ustalony(db, wybieranie):
    ustalony = pomysl(db, wybieranie, "Urodziny babci")

    with pytest.raises(SwipeError, match="ustalonego"):
        swipes.swipe(db, wybieranie, osoba(wybieranie, "Ania"), ustalony.id, "LEFT")


def test_kolejnosc_puli_jest_stala(db, wybieranie):
    """Wszyscy widzą karty w tej samej kolejności — inaczej licznik u hosta
    mówiłby o czym innym niż ekran uczestnika."""
    a = [i.id for i in swipes.pool(db, wybieranie.id)]
    b = [i.id for i in swipes.pool(db, wybieranie.id)]

    assert a == b


# ── głosy uczestników ───────────────────────────────────────────────────────


def test_gosc_glosuje(db, wybieranie):
    kajaki = pomysl(db, wybieranie, "Kajaki")
    swipes.swipe(db, wybieranie, osoba(wybieranie, "Ania"), kajaki.id, "RIGHT")

    assert swipes.tally(db, wybieranie.id)[kajaki.id] == {"right": 1, "left": 0}


def test_jeden_glos_na_pomysl(db, wybieranie):
    kajaki = pomysl(db, wybieranie, "Kajaki")
    ania = osoba(wybieranie, "Ania")
    swipes.swipe(db, wybieranie, ania, kajaki.id, "RIGHT")

    with pytest.raises(SwipeError, match="już za sobą"):
        swipes.swipe(db, wybieranie, ania, kajaki.id, "LEFT")


def test_host_nie_glosuje_tylko_rozstrzyga(db, wybieranie):
    kajaki = pomysl(db, wybieranie, "Kajaki")

    with pytest.raises(SwipeError, match="rozstrzyga"):
        swipes.swipe(db, wybieranie, osoba(wybieranie, "Ekran"), kajaki.id, "RIGHT")


def test_admin_bez_prawa_glosu_nie_glosuje(db, wybieranie):
    kajaki = pomysl(db, wybieranie, "Kajaki")

    with pytest.raises(SwipeError, match="Nie bierzesz udziału"):
        swipes.swipe(db, wybieranie, osoba(wybieranie, "Admin"), kajaki.id, "RIGHT")


def test_admin_z_prawem_glosu_glosuje(db, wybieranie):
    admin = osoba(wybieranie, "Admin")
    admin.is_voting = True
    db.commit()

    kajaki = pomysl(db, wybieranie, "Kajaki")
    swipes.swipe(db, wybieranie, admin, kajaki.id, "RIGHT")

    assert swipes.tally(db, wybieranie.id)[kajaki.id]["right"] == 1


def test_nieznany_kierunek_odrzucony(db, wybieranie):
    kajaki = pomysl(db, wybieranie, "Kajaki")

    with pytest.raises(SwipeError, match="kierunek"):
        swipes.swipe(db, wybieranie, osoba(wybieranie, "Ania"), kajaki.id, "UP")


# ── rozstrzygnięcie hosta ───────────────────────────────────────────────────


def test_decyzja_hosta_nadpisuje_glosy(db, wybieranie):
    """Sedno etapu: „ostateczny niezależnie od poprzednich głosów"."""
    kajaki = pomysl(db, wybieranie, "Kajaki")
    swipes.swipe(db, wybieranie, osoba(wybieranie, "Ania"), kajaki.id, "RIGHT")
    swipes.swipe(db, wybieranie, osoba(wybieranie, "Bartek"), kajaki.id, "RIGHT")

    swipes.decide(db, wybieranie, osoba(wybieranie, "Ekran"), kajaki.id, accepted=False)

    assert swipes.decisions(db, wybieranie.id)[kajaki.id] is False
    assert kajaki not in swipes.accepted_ideas(db, wybieranie.id)
    # Głosy zostają w bazie — to obraz zdania grupy, nie śmieć do skasowania.
    assert swipes.tally(db, wybieranie.id)[kajaki.id]["right"] == 2


def test_po_decyzji_hosta_glosy_sa_odrzucane(db, wybieranie):
    kajaki = pomysl(db, wybieranie, "Kajaki")
    swipes.decide(db, wybieranie, osoba(wybieranie, "Ekran"), kajaki.id, accepted=True)

    with pytest.raises(SwipeError, match="już rozstrzygnął"):
        swipes.swipe(db, wybieranie, osoba(wybieranie, "Ania"), kajaki.id, "LEFT")


def test_host_moze_poprawic_swoja_decyzje(db, wybieranie):
    """Uczestnik przesuwa raz, host może się rozmyślić — decyduje za wszystkich."""
    kajaki = pomysl(db, wybieranie, "Kajaki")
    ekran = osoba(wybieranie, "Ekran")

    swipes.decide(db, wybieranie, ekran, kajaki.id, accepted=True)
    swipes.decide(db, wybieranie, ekran, kajaki.id, accepted=False)

    assert swipes.decisions(db, wybieranie.id)[kajaki.id] is False


def test_gosc_nie_rozstrzyga(db, wybieranie):
    kajaki = pomysl(db, wybieranie, "Kajaki")

    with pytest.raises(SwipeError, match="Tylko prowadzący"):
        swipes.decide(db, wybieranie, osoba(wybieranie, "Ania"), kajaki.id, accepted=True)


def test_admin_tez_nie_rozstrzyga(db, wybieranie):
    """Admin ma uprawnienia do treści, ale procesu nie prowadzi."""
    kajaki = pomysl(db, wybieranie, "Kajaki")

    with pytest.raises(SwipeError, match="Tylko prowadzący"):
        swipes.decide(db, wybieranie, osoba(wybieranie, "Admin"), kajaki.id, accepted=True)


# ── co przechodzi dalej ─────────────────────────────────────────────────────


def test_do_etapu_3_ida_przyjete_i_ustalone(db, wybieranie):
    ekran = osoba(wybieranie, "Ekran")
    swipes.decide(db, wybieranie, ekran, pomysl(db, wybieranie, "Kajaki").id, accepted=True)
    swipes.decide(db, wybieranie, ekran, pomysl(db, wybieranie, "Kino").id, accepted=False)
    # "Kręgle" bez rozstrzygnięcia — host nie zdążył

    tytuly = [i.title for i in swipes.accepted_ideas(db, wybieranie.id)]

    assert tytuly == ["Kajaki", "Urodziny babci"]
    assert "Kino" not in tytuly, "odrzucone odpada"
    assert "Kręgle" not in tytuly, "nierozstrzygnięte nie przechodzi samo z siebie"


def test_sam_wpis_ustalony_przechodzi_bez_zadnej_decyzji(db, wybieranie):
    tytuly = [i.title for i in swipes.accepted_ideas(db, wybieranie.id)]
    assert tytuly == ["Urodziny babci"]


# ── brama etapu ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [SessionStatus.COLLECTING, SessionStatus.SCHEDULING, SessionStatus.CLOSED],
)
def test_poza_etapem_2_nie_da_sie_glosowac(db, wybieranie, status):
    kajaki = pomysl(db, wybieranie, "Kajaki")
    wybieranie.status = status.value
    db.commit()

    with pytest.raises(SwipeError, match="nie jest aktywny"):
        swipes.swipe(db, wybieranie, osoba(wybieranie, "Ania"), kajaki.id, "RIGHT")
    with pytest.raises(SwipeError, match="nie jest aktywny"):
        swipes.decide(db, wybieranie, osoba(wybieranie, "Ekran"), kajaki.id, accepted=True)


# ── snapshot ────────────────────────────────────────────────────────────────


def test_gosc_nie_widzi_licznikow(db, wybieranie):
    """Podanie uczestnikowi, ilu już było na tak, przesądzałoby jego głos."""
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, wybieranie, osoba(wybieranie, "Ania"))

    assert "board" not in snap["swiping"]
    assert len(snap["swiping"]["cards"]) == 3
    assert snap["swiping"]["yourDone"] == 0
    assert snap["swiping"]["youAreDone"] is False


def test_karta_znika_z_talii_po_zaglosowaniu(db, wybieranie):
    from app.snapshots import build_snapshot

    ania = osoba(wybieranie, "Ania")
    swipes.swipe(db, wybieranie, ania, pomysl(db, wybieranie, "Kajaki").id, "RIGHT")

    snap = build_snapshot(db, wybieranie, ania)

    assert [c["title"] for c in snap["swiping"]["cards"]] == ["Kino", "Kręgle"]
    assert snap["swiping"]["yourDone"] == 1


def test_rozstrzygniety_pomysl_znika_z_talii_uczestnika(db, wybieranie):
    """Głos i tak nic by nie zmienił — pokazywanie karty byłoby oszustwem."""
    from app.snapshots import build_snapshot

    swipes.decide(
        db, wybieranie, osoba(wybieranie, "Ekran"), pomysl(db, wybieranie, "Kino").id, True
    )

    snap = build_snapshot(db, wybieranie, osoba(wybieranie, "Ania"))

    assert [c["title"] for c in snap["swiping"]["cards"]] == ["Kajaki", "Kręgle"]


def test_host_widzi_tablice_z_licznikami(db, wybieranie):
    from app.snapshots import build_snapshot

    kajaki = pomysl(db, wybieranie, "Kajaki")
    swipes.swipe(db, wybieranie, osoba(wybieranie, "Ania"), kajaki.id, "RIGHT")
    swipes.swipe(db, wybieranie, osoba(wybieranie, "Bartek"), kajaki.id, "LEFT")

    snap = build_snapshot(db, wybieranie, osoba(wybieranie, "Ekran"))
    wpis = next(b for b in snap["swiping"]["board"] if b["title"] == "Kajaki")

    assert wpis["right"] == 1
    assert wpis["left"] == 1
    assert wpis["voted"] == 2
    assert wpis["decision"] is None
    assert snap["swiping"]["votersExpected"] == 2, "mianownik to tylko głosujący goście"


def test_host_nie_ma_wlasnej_talii(db, wybieranie):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, wybieranie, osoba(wybieranie, "Ekran"))

    assert snap["swiping"]["cards"] == []
    assert snap["swiping"]["youAreDone"] is True


def test_widz_widzi_tablice_jak_host(db, wybieranie):
    """To jest cały sens podglądu: ekran hosta ogląda ktoś spoza pokoju."""
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, wybieranie, None)

    assert len(snap["swiping"]["board"]) == 3
    assert snap["swiping"]["cards"] == []
