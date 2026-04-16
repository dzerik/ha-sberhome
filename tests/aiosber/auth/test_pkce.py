"""Тесты PKCE: verifier/challenge gen, URL builder, code extraction."""

from __future__ import annotations

import base64
import hashlib

import pytest

from custom_components.sberhome.aiosber.auth import (
    PkceParams,
    build_authorize_url,
    extract_code_from_redirect,
)
from custom_components.sberhome.aiosber.exceptions import PkceError


# ---- PkceParams.generate ----
def test_generate_produces_correct_lengths():
    p = PkceParams.generate()
    # RFC 7636: 43-128 символов
    assert 43 <= len(p.verifier) <= 128
    # SHA256 → base64url без padding = 43 символа
    assert len(p.challenge) == 43
    assert p.method == "S256"
    assert len(p.state) >= 16
    assert len(p.nonce) >= 16


def test_challenge_matches_verifier():
    """challenge = base64url(SHA256(verifier)) без padding (RFC 7636 §4.2)."""
    p = PkceParams.generate()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(p.verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert p.challenge == expected


def test_each_generation_is_unique():
    a = PkceParams.generate()
    b = PkceParams.generate()
    assert a.verifier != b.verifier
    assert a.state != b.state
    assert a.nonce != b.nonce


def test_pkce_params_immutable():
    p = PkceParams.generate()
    with pytest.raises((AttributeError, TypeError)):
        p.verifier = "evil"  # type: ignore[misc]


# ---- build_authorize_url ----
def test_authorize_url_has_required_params():
    p = PkceParams.generate()
    url = build_authorize_url(p)
    assert url.startswith("https://id.sber.ru/CSAFront/oidc/authorize.do?")
    for key in (
        "response_type=code",
        "client_id=b1f0f0c6",
        f"state={p.state}",
        f"nonce={p.nonce}",
        f"code_challenge={p.challenge}",
        "code_challenge_method=S256",
    ):
        assert key in url, f"missing {key}"


def test_authorize_url_redirect_encoded():
    p = PkceParams.generate()
    url = build_authorize_url(p, redirect_uri="companionapp://host")
    # URL-encoded
    assert "redirect_uri=companionapp%3A%2F%2Fhost" in url


def test_authorize_url_custom_client_id():
    p = PkceParams.generate()
    url = build_authorize_url(p, client_id="my-client-id")
    assert "client_id=my-client-id" in url


# ---- extract_code_from_redirect ----
def test_extract_code_from_query():
    code = extract_code_from_redirect("companionapp://host?code=ABC123&state=xyz")
    assert code == "ABC123"


def test_extract_code_from_fragment():
    """Иногда параметры приходят в fragment вместо query."""
    code = extract_code_from_redirect("companionapp://host#code=DEF456&state=zyx")
    assert code == "DEF456"


def test_extract_code_validates_state():
    code = extract_code_from_redirect(
        "companionapp://host?code=OK&state=expected", expected_state="expected"
    )
    assert code == "OK"


def test_extract_code_state_mismatch_raises():
    with pytest.raises(PkceError, match="State mismatch"):
        extract_code_from_redirect(
            "companionapp://host?code=OK&state=evil", expected_state="expected"
        )


def test_extract_code_missing_raises():
    with pytest.raises(PkceError, match="No 'code'"):
        extract_code_from_redirect("companionapp://host?error=denied")


def test_extract_code_handles_https_redirect():
    code = extract_code_from_redirect("https://example.com/cb?code=https-flow&state=s")
    assert code == "https-flow"
