"""Тесты SberIdTokens / CompanionTokens."""

from __future__ import annotations

import time

from custom_components.sberhome.aiosber.auth import CompanionTokens, SberIdTokens


def test_sberid_from_dict_full():
    src = {
        "access_token": "AT",
        "refresh_token": "RT",
        "id_token": "JWT",
        "token_type": "Bearer",
        "expires_in": 3600,
        "scope": "openid profile",
    }
    t = SberIdTokens.from_dict(src)
    assert t.access_token == "AT"
    assert t.refresh_token == "RT"
    assert t.id_token == "JWT"
    assert t.expires_in == 3600
    assert t.scope == "openid profile"
    assert t.obtained_at > 0


def test_sberid_from_dict_minimal():
    t = SberIdTokens.from_dict({"access_token": "x"})
    assert t.access_token == "x"
    assert t.refresh_token is None
    assert t.expires_in == 3600  # default


def test_sberid_to_dict_roundtrip():
    src = {
        "access_token": "x",
        "refresh_token": "y",
        "id_token": None,
        "token_type": "Bearer",
        "expires_in": 100,
        "scope": "openid",
        "obtained_at": 12345.0,
    }
    t = SberIdTokens.from_dict(src)
    assert t.to_dict() == src


def test_sberid_expires_at_calc():
    t = SberIdTokens(access_token="x", expires_in=100, obtained_at=1000)
    assert t.expires_at == 1100


def test_sberid_is_expired_now_false():
    t = SberIdTokens(access_token="x", expires_in=3600)
    assert not t.is_expired()


def test_sberid_is_expired_with_leeway():
    t = SberIdTokens(access_token="x", expires_in=30)
    assert t.is_expired(leeway=60)


def test_sberid_is_expired_past():
    t = SberIdTokens(access_token="x", expires_in=10, obtained_at=time.time() - 1000)
    assert t.is_expired()


# ---- CompanionTokens ----
def test_companion_default_24h():
    t = CompanionTokens(access_token="x")
    assert t.expires_in == 86400  # 24h


def test_companion_roundtrip():
    src = {
        "access_token": "C",
        "refresh_token": "R",
        "token_type": "Bearer",
        "expires_in": 7200,
        "obtained_at": 9999.0,
    }
    t = CompanionTokens.from_dict(src)
    assert t.access_token == "C"
    assert t.refresh_token == "R"
    assert t.expires_in == 7200
    assert t.to_dict() == src


def test_companion_is_expired_logic():
    fresh = CompanionTokens(access_token="x", expires_in=3600)
    assert not fresh.is_expired()

    stale = CompanionTokens(access_token="x", expires_in=10, obtained_at=time.time() - 100)
    assert stale.is_expired()
