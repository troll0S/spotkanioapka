"""Snapshot musi ukrywać przed gościem to, czego nie powinien widzieć.

W trybie zdalnym adres jest publiczny, więc "frontend to schowa" nie jest
odpowiedzią.
"""

from app.models import Role
from app.snapshots import build_snapshot


def _osoba(session, imie):
    return next(p for p in session.participants if p.display_name == imie)


def test_gosc_nie_widzi_rol_ani_sterowania(db, sample_session):
    snap = build_snapshot(db, sample_session, _osoba(sample_session, "Ania"))

    assert "host" not in snap, "Gość nie może dostać sekcji sterującej"
    for osoba in snap["participants"]:
        assert "role" not in osoba
        assert "isVoting" not in osoba


def test_gosc_nie_widzi_hosta_na_liscie(db, sample_session):
    """Host to ekran, nie uczestnik — nie ma go w składzie sesji."""
    snap = build_snapshot(db, sample_session, _osoba(sample_session, "Ania"))
    imiona = {p["displayName"] for p in snap["participants"]}

    assert "Ekran" not in imiona
    assert imiona == {"Admin", "Ania", "Bartek"}


def test_host_widzi_role_i_sterowanie(db, sample_session):
    snap = build_snapshot(db, sample_session, _osoba(sample_session, "Ekran"), "http://x/join")

    assert snap["host"]["canAdvance"] is True
    assert snap["host"]["joinUrl"] == "http://x/join"
    assert all("role" in p for p in snap["participants"])


def test_admin_ma_podglad_ale_nie_sterowanie(db, sample_session):
    """Admin ma uprawnienia do treści, ale procesu nie prowadzi."""
    snap = build_snapshot(db, sample_session, _osoba(sample_session, "Admin"))

    assert "host" not in snap
    assert all("role" in p for p in snap["participants"])


def test_liczniki_biora_mianownik_z_glosujacych(db, sample_session):
    snap = build_snapshot(db, sample_session, _osoba(sample_session, "Ekran"))

    assert snap["counts"]["voting"] == 2
    assert snap["counts"]["total"] == 4


def test_token_nigdy_nie_wychodzi_w_snapshocie(db, sample_session):
    for widz in (_osoba(sample_session, "Ekran"), _osoba(sample_session, "Ania"), None):
        snap = build_snapshot(db, sample_session, widz)
        assert "token" not in repr(snap)


def test_widz_dostaje_podglad_bez_sterowania(db, sample_session):
    """Rola SPECTATOR (kamień KZ) — widzi to co host, nie może nic zrobić."""
    snap = build_snapshot(db, sample_session, None)

    assert "host" not in snap
    assert snap["you"] is None
    assert len(snap["participants"]) == 4
