"""Panel admina: korekta odpowiedzi, moderacja wpisów, skład sesji."""

import pytest

from app import admin_ops, assignments, availability, ideas, schedules, swipes
from app.admin_ops import AdminError
from app.models import Idea, Role
from app.state_machine import SessionStatus


def osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


def pomysl(db, session, tytul):
    return next(i for i in ideas.list_ideas(db, session.id) if i.title == tytul)


@pytest.fixture()
def zbieranie(db, sample_session):
    sample_session.status = SessionStatus.COLLECTING.value
    db.commit()
    ania = osoba(sample_session, "Ania")
    ideas.create_idea(db, sample_session, ania, "Kajaki", "Opis kajaków")
    ideas.create_idea(db, sample_session, osoba(sample_session, "Bartek"), "Kino")
    return sample_session


@pytest.fixture()
def po_rundzie(db, zbieranie):
    """Sesja w etapie 4, po deklaracjach obu gości."""
    s = zbieranie
    ekran = osoba(s, "Ekran")

    s.status = SessionStatus.SWIPING.value
    db.commit()
    for tytul in ("Kajaki", "Kino"):
        swipes.decide(db, s, ekran, pomysl(db, s, tytul).id, True)

    s.status = SessionStatus.SCHEDULING.value
    db.commit()
    for numer, tytul in enumerate(("Kajaki", "Kino"), start=1):
        schedules.set_schedule(
            db, s, ekran, pomysl(db, s, tytul).id, "EXACT_DATE", date=f"2026-0{numer}-10"
        )

    s.status = SessionStatus.AVAILABILITY.value
    db.commit()
    availability.build_order(db, s)
    biezace = availability.current_idea_id(s)
    availability.answer(db, s, osoba(s, "Ania"), biezace, "ABSOLUTELY_NOT")
    availability.answer(db, s, osoba(s, "Bartek"), biezace, "WANT")
    return s


# ── korekta odpowiedzi ──────────────────────────────────────────────────────


def test_admin_poprawia_odpowiedz(db, po_rundzie):
    """Jedyna droga do zmiany zablokowanego głosu — cztery duże przyciski
    na telefonie bardzo łatwo kliknąć nie tam."""
    biezace = availability.current_idea_id(po_rundzie)
    ania = osoba(po_rundzie, "Ania")

    wpis = admin_ops.correct_answer(
        db, po_rundzie, osoba(po_rundzie, "Admin"), biezace, ania.id, "WANT"
    )

    assert wpis.answer == "WANT"
    assert wpis.original_answer == "ABSOLUTELY_NOT", "pierwotny głos zostaje zapisany"
    assert wpis.edited_by_admin_at is not None
    assert availability.tally(db, biezace) == {
        "WANT": 2, "CAN": 0, "DONT_WANT": 0, "ABSOLUTELY_NOT": 0,
    }


def test_druga_poprawka_nie_nadpisuje_pierwotnego_glosu(db, po_rundzie):
    """Chodzi o odróżnienie głosu od korekty, nie o pełną historię zmian."""
    biezace = availability.current_idea_id(po_rundzie)
    ania = osoba(po_rundzie, "Ania")
    admin = osoba(po_rundzie, "Admin")

    admin_ops.correct_answer(db, po_rundzie, admin, biezace, ania.id, "WANT")
    wpis = admin_ops.correct_answer(db, po_rundzie, admin, biezace, ania.id, "CAN")

    assert wpis.answer == "CAN"
    assert wpis.original_answer == "ABSOLUTELY_NOT"


def test_admin_odpowiada_za_kogos_kto_nie_zdazyl(db, po_rundzie):
    """Komuś padł telefon w trakcie rundy — da się to uzupełnić."""
    s = po_rundzie
    # Kolejność w etapie 4 jest losowa, więc bierzemy wydarzenie, na które
    # nikt jeszcze nie odpowiadał — czyli to, które nie jest na ekranie.
    biezace = availability.current_idea_id(s)
    inne = next(i for i in ideas.list_ideas(db, s.id) if i.id != biezace)
    ania = osoba(s, "Ania")

    wpis = admin_ops.correct_answer(db, s, osoba(s, "Admin"), inne.id, ania.id, "CAN")

    assert wpis.answer == "CAN"
    assert wpis.original_answer is None, "nie było czego nadpisywać"
    assert wpis.edited_by_admin_at is not None


def test_ta_sama_odpowiedz_nie_oznacza_korekty(db, po_rundzie):
    biezace = availability.current_idea_id(po_rundzie)
    bartek = osoba(po_rundzie, "Bartek")

    wpis = admin_ops.correct_answer(
        db, po_rundzie, osoba(po_rundzie, "Admin"), biezace, bartek.id, "WANT"
    )

    assert wpis.original_answer is None
    assert wpis.edited_by_admin_at is None


def test_host_nie_poprawia_odpowiedzi(db, po_rundzie):
    """Prowadzący prowadzi, admin poprawia treść — to dwie różne role."""
    biezace = availability.current_idea_id(po_rundzie)
    ania = osoba(po_rundzie, "Ania")

    with pytest.raises(AdminError, match="tylko administrator"):
        admin_ops.correct_answer(
            db, po_rundzie, osoba(po_rundzie, "Ekran"), biezace, ania.id, "WANT"
        )


def test_gosc_nie_poprawia_odpowiedzi(db, po_rundzie):
    biezace = availability.current_idea_id(po_rundzie)
    ania = osoba(po_rundzie, "Ania")

    with pytest.raises(AdminError, match="tylko administrator"):
        admin_ops.correct_answer(
            db, po_rundzie, osoba(po_rundzie, "Bartek"), biezace, ania.id, "WANT"
        )


# ── moderacja wpisów ────────────────────────────────────────────────────────


def test_admin_poprawia_cudzy_wpis(db, zbieranie):
    kajaki = pomysl(db, zbieranie, "Kajaki")

    zmieniony = admin_ops.edit_idea(
        db, zbieranie, osoba(zbieranie, "Admin"), kajaki.id,
        title="Kajaki na Mazurach", description="",
    )

    assert zmieniony.title == "Kajaki na Mazurach"
    assert zmieniony.description is None, "pusty opis czyści pole"


def test_admin_usuwa_cudzy_wpis_w_etapie_1(db, zbieranie):
    kino = pomysl(db, zbieranie, "Kino")
    admin_ops.delete_idea(db, zbieranie, osoba(zbieranie, "Admin"), kino.id)

    assert [i.title for i in ideas.list_ideas(db, zbieranie.id)] == ["Kajaki"]


def test_po_etapie_1_wpisu_sie_nie_usuwa(db, po_rundzie):
    """Pomysł ma już głosy, termin i deklaracje — wyrwanie go zostawiłoby
    sesję w stanie, którego nikt nie zamawiał."""
    kino = pomysl(db, po_rundzie, "Kino")

    with pytest.raises(AdminError, match="tylko w etapie 1"):
        admin_ops.delete_idea(db, po_rundzie, osoba(po_rundzie, "Admin"), kino.id)


def test_poprawianie_tytulu_dziala_na_kazdym_etapie(db, po_rundzie):
    """Literówka przeszkadza najbardziej wtedy, gdy trafia do kalendarza."""
    kino = pomysl(db, po_rundzie, "Kino")

    zmieniony = admin_ops.edit_idea(
        db, po_rundzie, osoba(po_rundzie, "Admin"), kino.id, title="Kino letnie"
    )
    assert zmieniony.title == "Kino letnie"


def test_pusty_tytul_odrzucony(db, zbieranie):
    kajaki = pomysl(db, zbieranie, "Kajaki")

    with pytest.raises(AdminError, match="nie może być pusty"):
        admin_ops.edit_idea(db, zbieranie, osoba(zbieranie, "Admin"), kajaki.id, title="  ")


# ── skład sesji ─────────────────────────────────────────────────────────────


def test_usuniecie_uczestnika_zostawia_jego_pomysly(db, zbieranie):
    """Treść, dla której sesja się odbyła, nie może wylatywać przy porządkach."""
    ania = osoba(zbieranie, "Ania")

    imie = admin_ops.remove_participant(
        db, zbieranie, osoba(zbieranie, "Admin"), ania.id
    )

    assert imie == "Ania"
    tytuly = [i.title for i in ideas.list_ideas(db, zbieranie.id)]
    assert "Kajaki" in tytuly, "pomysł przeżył swojego autora"

    osierocony = db.get(Idea, pomysl(db, zbieranie, "Kajaki").id)
    assert osierocony.author_id is None


def test_usuniecie_uczestnika_zabiera_jego_glosy(db, po_rundzie):
    """Bez osoby głos nic nie znaczy, a zostawiony psułby liczniki."""
    biezace = availability.current_idea_id(po_rundzie)
    ania = osoba(po_rundzie, "Ania")
    assert availability.tally(db, biezace)["ABSOLUTELY_NOT"] == 1

    admin_ops.remove_participant(db, po_rundzie, osoba(po_rundzie, "Admin"), ania.id)

    assert availability.tally(db, biezace)["ABSOLUTELY_NOT"] == 0
    assert availability.expected_voters(db, po_rundzie.id) == 1, "mianownik też maleje"


def test_nie_da_sie_usunac_hosta(db, zbieranie):
    with pytest.raises(AdminError, match="ekranu prowadzącego"):
        admin_ops.remove_participant(
            db, zbieranie, osoba(zbieranie, "Admin"), osoba(zbieranie, "Ekran").id
        )


def test_admin_nie_usuwa_sam_siebie(db, zbieranie):
    admin = osoba(zbieranie, "Admin")

    with pytest.raises(AdminError, match="samego siebie"):
        admin_ops.remove_participant(db, zbieranie, admin, admin.id)


def test_gosc_nie_usuwa_uczestnikow(db, zbieranie):
    with pytest.raises(AdminError, match="tylko administrator"):
        admin_ops.remove_participant(
            db, zbieranie, osoba(zbieranie, "Ania"), osoba(zbieranie, "Bartek").id
        )


# ── snapshot ────────────────────────────────────────────────────────────────


def test_tylko_admin_dostaje_sekcje_panelu(db, po_rundzie):
    from app.snapshots import build_snapshot

    assert "admin" in build_snapshot(db, po_rundzie, osoba(po_rundzie, "Admin"))
    assert "admin" not in build_snapshot(db, po_rundzie, osoba(po_rundzie, "Ekran"))
    assert "admin" not in build_snapshot(db, po_rundzie, osoba(po_rundzie, "Ania"))
    assert "admin" not in build_snapshot(db, po_rundzie, None)


def test_panel_pokazuje_odpowiedzi_biezacego_wydarzenia(db, po_rundzie):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, po_rundzie, osoba(po_rundzie, "Admin"))
    wedlug_imion = {o["displayName"]: o for o in snap["admin"]["answers"]}

    assert wedlug_imion["Ania"]["answer"] == "ABSOLUTELY_NOT"
    assert wedlug_imion["Bartek"]["answer"] == "WANT"
    assert snap["admin"]["currentIdeaId"] == availability.current_idea_id(po_rundzie)


def test_panel_oznacza_poprawione_odpowiedzi(db, po_rundzie):
    from app.snapshots import build_snapshot

    biezace = availability.current_idea_id(po_rundzie)
    ania = osoba(po_rundzie, "Ania")
    admin = osoba(po_rundzie, "Admin")
    admin_ops.correct_answer(db, po_rundzie, admin, biezace, ania.id, "WANT")

    snap = build_snapshot(db, po_rundzie, admin)
    wpis = next(o for o in snap["admin"]["answers"] if o["displayName"] == "Ania")

    assert wpis["wasEdited"] is True
    assert wpis["originalAnswer"] == "ABSOLUTELY_NOT"


def test_panel_wie_kiedy_wolno_usuwac_wpisy(db, zbieranie, po_rundzie):
    from app.snapshots import build_snapshot

    snap = build_snapshot(db, po_rundzie, osoba(po_rundzie, "Admin"))
    assert snap["admin"]["canDeleteIdeas"] is False

    po_rundzie.status = SessionStatus.COLLECTING.value
    db.commit()
    snap = build_snapshot(db, po_rundzie, osoba(po_rundzie, "Admin"))
    assert snap["admin"]["canDeleteIdeas"] is True


def test_pomysl_bez_autora_nie_wywraca_snapshotu(db, zbieranie):
    """Po usunięciu uczestnika jego pomysły zostają bez autora."""
    from app.snapshots import build_snapshot

    admin = osoba(zbieranie, "Admin")
    admin_ops.remove_participant(db, zbieranie, admin, osoba(zbieranie, "Ania").id)

    snap = build_snapshot(db, zbieranie, admin)
    osierocony = next(i for i in snap["ideas"] if i["title"] == "Kajaki")

    assert osierocony["authorName"] == "—"
