"""Tests for the SberHome auth views."""

from __future__ import annotations

import html
import re
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import custom_components.sberhome.auth_view as auth_view_module
from custom_components.sberhome.api import SberAPI
from custom_components.sberhome.auth_state import PendingFlow, pending_auth_flows
from custom_components.sberhome.auth_view import (
    SberAuthCallbackView,
    SberAuthStartView,
)
from custom_components.sberhome.const import DOMAIN


@pytest.fixture(autouse=True)
def reset_template_cache():
    """Reset the cached auth page template between tests."""
    auth_view_module._AUTH_PAGE_TEMPLATE = None
    yield
    auth_view_module._AUTH_PAGE_TEMPLATE = None


FLOW_ID = "01JABCDEFGHJKMNPQRSTVWXYZ0"
"""flow_id в формате ULID, как его выдаёт Home Assistant."""


def _real_auth_url() -> str:
    """Build a genuine Sber ID authorization URL the way config_flow does."""
    return SberAPI(http=MagicMock()).create_authorization_url()


def _make_hass(*flow_ids: str) -> MagicMock:
    """Mock hass with the given flow_ids in progress for the sberhome handler."""
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))

    def _progress(handler, *args, **kwargs):
        if handler != DOMAIN:
            return []
        return [{"flow_id": fid, "handler": DOMAIN} for fid in flow_ids]

    hass.config_entries.flow.async_progress_by_handler = MagicMock(side_effect=_progress)
    return hass


def _make_start_request(query: str, hass: MagicMock) -> web.Request:
    """Create a mocked GET request to the auth start view."""
    request = make_mocked_request("GET", f"/auth/sberhome?{query}")
    request.app["hass"] = hass
    return request


def _nonce_from_csp(csp: str) -> str:
    match = re.search(r"script-src 'nonce-([A-Za-z0-9_-]+)'", csp)
    assert match, csp
    return match.group(1)


async def test_start_view_renders_legitimate_flow():
    """Настоящий flow: ссылка на Сбер ID из состояния flow, CSP с nonce."""
    auth_url = _real_auth_url()
    hass = _make_hass(FLOW_ID)
    request = _make_start_request(f"flow_id={FLOW_ID}", hass)

    with patch.dict(
        pending_auth_flows, {FLOW_ID: PendingFlow(client=MagicMock(), auth_url=auth_url)}
    ):
        response = await SberAuthStartView().get(request)

    assert response.status == 200
    assert response.content_type == "text/html"
    body = response.text
    assert f'data-flow-id="{FLOW_ID}"' in body
    assert f'href="{html.escape(auth_url, quote=True)}"' in body
    assert "companionapp://" in body
    for placeholder in ("$flow_id", "$auth_url", "$nonce"):
        assert placeholder not in body

    csp = response.headers["Content-Security-Policy"]
    nonce = _nonce_from_csp(csp)
    assert f"style-src 'nonce-{nonce}'" in csp
    assert "default-src 'none'" in csp
    assert "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    # Оба inline-блока помечены тем же nonce, иначе браузер их заблокирует.
    assert f'<script nonce="{nonce}">' in body
    assert f'<style nonce="{nonce}">' in body
    assert body.count("<script") == 1
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    hass.config_entries.flow.async_progress_by_handler.assert_called_with(DOMAIN)


async def test_start_view_nonce_is_unique_per_response():
    """Nonce генерируется заново для каждого ответа."""
    hass = _make_hass(FLOW_ID)
    pending = {FLOW_ID: PendingFlow(client=MagicMock(), auth_url=_real_auth_url())}
    with patch.dict(pending_auth_flows, pending):
        first = await SberAuthStartView().get(_make_start_request(f"flow_id={FLOW_ID}", hass))
        second = await SberAuthStartView().get(_make_start_request(f"flow_id={FLOW_ID}", hass))
    assert _nonce_from_csp(first.headers["Content-Security-Policy"]) != _nonce_from_csp(
        second.headers["Content-Security-Policy"]
    )


async def test_start_view_ignores_auth_url_from_query():
    """auth_url из query не попадает в страницу — только из состояния flow."""
    auth_url = _real_auth_url()
    hass = _make_hass(FLOW_ID)
    query = f"flow_id={FLOW_ID}&auth_url=" + quote("javascript:alert(document.domain)", safe="")
    with patch.dict(
        pending_auth_flows, {FLOW_ID: PendingFlow(client=MagicMock(), auth_url=auth_url)}
    ):
        response = await SberAuthStartView().get(_make_start_request(query, hass))

    assert response.status == 200
    assert "javascript:" not in response.text
    assert "alert(" not in response.text
    assert f'href="{html.escape(auth_url, quote=True)}"' in response.text


@pytest.mark.parametrize(
    "flow_id",
    [
        '";alert(1)//',
        "</script><script>alert(1)</script>",
        '" onmouseover="alert(1)',
        "abc<svg/onload=alert(1)>",
        "a" * 65,
        "",
    ],
)
async def test_start_view_rejects_malformed_flow_id(flow_id: str):
    """Попытки выйти из JS-строки/атрибута отклоняются 400 без отражения ввода."""
    hass = _make_hass(flow_id)
    pending = {flow_id: PendingFlow(client=MagicMock(), auth_url=_real_auth_url())}
    request = _make_start_request("flow_id=" + quote(flow_id, safe=""), hass)

    with patch.dict(pending_auth_flows, pending):
        response = await SberAuthStartView().get(request)

    assert response.status == 400
    assert response.content_type == "text/plain"
    assert "alert" not in response.text
    assert "<" not in response.text
    hass.async_add_executor_job.assert_not_called()


async def test_start_view_missing_flow_id():
    """Без flow_id страница не отдаётся."""
    response = await SberAuthStartView().get(_make_start_request("", _make_hass()))
    assert response.status == 400


async def test_start_view_unknown_flow_id():
    """Правильный формат, но мост не начинал OAuth для этого flow — 404."""
    hass = _make_hass("OTHERFLOW")
    with patch.dict(pending_auth_flows, {}, clear=True):
        response = await SberAuthStartView().get(_make_start_request("flow_id=OTHERFLOW", hass))
    assert response.status == 404
    assert "OTHERFLOW" not in response.text


async def test_start_view_pending_but_not_in_progress():
    """OAuth начат, но flow уже прерван в HA (или принадлежит другой интеграции) — 404."""
    hass = MagicMock()
    hass.config_entries.flow.async_progress_by_handler = MagicMock(return_value=[])
    pending = {FLOW_ID: PendingFlow(client=MagicMock(), auth_url=_real_auth_url())}
    with patch.dict(pending_auth_flows, pending):
        response = await SberAuthStartView().get(_make_start_request(f"flow_id={FLOW_ID}", hass))
    assert response.status == 404
    hass.config_entries.flow.async_progress_by_handler.assert_called_once_with(DOMAIN)


@pytest.mark.parametrize(
    "stored_url",
    [
        "",
        "javascript:alert(1)",
        "http://online.sberbank.ru/CSAFront/oidc/authorize.do?x=1",
        "https://evil.example/CSAFront/oidc/authorize.do",
        "https://online.sberbank.ru.evil.example/CSAFront/oidc/authorize.do",
        "https://online.sberbank.ru@evil.example/",
        "https://evil@online.sberbank.ru/CSAFront/oidc/authorize.do",
        "https://online.sberbank.ru:4431/CSAFront/oidc/authorize.do",
        "https://online.sberbank.ru:bad/",
        'https://online.sberbank.ru/"><script>alert(1)</script>',
    ],
)
async def test_start_view_rejects_untrusted_auth_url(stored_url: str):
    """Даже серверная ссылка рендерится только если это https на хосте Сбер ID."""
    hass = _make_hass(FLOW_ID)
    pending = {FLOW_ID: PendingFlow(client=MagicMock(), auth_url=stored_url)}
    with patch.dict(pending_auth_flows, pending):
        response = await SberAuthStartView().get(_make_start_request(f"flow_id={FLOW_ID}", hass))

    if stored_url.startswith('https://online.sberbank.ru/"'):
        # Хост верный — страница отдаётся, но значение экранировано и инертно.
        assert response.status == 200
        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
        assert 'href="https://online.sberbank.ru/&quot;&gt;' in response.text
    else:
        assert response.status == 400
        assert response.content_type == "text/plain"


def _make_callback_request(json_data, hass=None, content_type="application/json"):
    """Create a mocked POST request with JSON body for callback view."""
    request = make_mocked_request(
        "POST",
        "/auth/sberhome/callback",
        headers={"Content-Type": content_type},
    )
    request.json = AsyncMock(return_value=json_data)
    request.app["hass"] = hass if hass is not None else _make_hass()
    return request


async def test_callback_view_success():
    """Test successful callback authorizes and configures the flow."""
    mock_client = AsyncMock()
    mock_client.authorize_by_url = AsyncMock(return_value=True)

    mock_hass = _make_hass("test-flow")
    mock_hass.config_entries.flow.async_configure = AsyncMock()

    request = _make_callback_request(
        {"flow_id": "test-flow", "url": "companionapp://host?code=abc&state=xyz"},
        hass=mock_hass,
    )

    with patch.dict(pending_auth_flows, {"test-flow": PendingFlow(client=mock_client)}):
        response = await SberAuthCallbackView().post(request)

    assert response.status == 200
    mock_client.authorize_by_url.assert_awaited_once_with("companionapp://host?code=abc&state=xyz")
    mock_hass.config_entries.flow.async_configure.assert_awaited_once_with(
        "test-flow", user_input={}
    )


async def test_callback_view_configure_failure():
    """Ошибка async_configure отдаёт 500 без деталей."""
    mock_client = AsyncMock()
    mock_client.authorize_by_url = AsyncMock(return_value=True)
    mock_hass = _make_hass("test-flow")
    mock_hass.config_entries.flow.async_configure = AsyncMock(side_effect=RuntimeError("boom"))
    request = _make_callback_request(
        {"flow_id": "test-flow", "url": "companionapp://host?code=abc&state=xyz"},
        hass=mock_hass,
    )
    with patch.dict(pending_auth_flows, {"test-flow": PendingFlow(client=mock_client)}):
        response = await SberAuthCallbackView().post(request)
    assert response.status == 500
    assert b"boom" not in response.body


async def test_callback_view_missing_flow_id():
    """Test callback with missing flow_id returns 400."""
    request = _make_callback_request({"url": "companionapp://host?code=abc"})
    response = await SberAuthCallbackView().post(request)
    assert response.status == 400


@pytest.mark.parametrize(
    "flow_id",
    ['";alert(1)//', "</script>", ["test-flow"], {"a": 1}, 123, "a" * 65],
)
async def test_callback_view_rejects_malformed_flow_id(flow_id):
    """Неверный тип/формат flow_id — 400, а не TypeError/500."""
    request = _make_callback_request({"flow_id": flow_id, "url": "companionapp://host?code=abc"})
    response = await SberAuthCallbackView().post(request)
    assert response.status == 400


@pytest.mark.parametrize("body", [["flow_id"], "text", None, 42])
async def test_callback_view_rejects_non_object_body(body):
    """JSON не-объект — 400, а не AttributeError/500."""
    response = await SberAuthCallbackView().post(_make_callback_request(body))
    assert response.status == 400


@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data"]
)
async def test_callback_view_rejects_simple_cross_origin_content_types(content_type):
    """Тела без application/json (кросс-доменный POST без preflight) отклоняются."""
    request = _make_callback_request(
        {"flow_id": "test-flow", "url": "companionapp://host?code=abc"},
        content_type=content_type,
    )
    response = await SberAuthCallbackView().post(request)
    assert response.status == 415
    request.json.assert_not_awaited()


async def test_callback_view_invalid_json():
    """Битый JSON — 400."""
    request = _make_callback_request(None)
    request.json = AsyncMock(side_effect=ValueError("bad json"))
    response = await SberAuthCallbackView().post(request)
    assert response.status == 400


@pytest.mark.parametrize("url", ["https://evil.com", "javascript:alert(1)", 42, None])
async def test_callback_view_invalid_url(url):
    """Test callback with non-companionapp URL returns 400."""
    request = _make_callback_request({"flow_id": "test-flow", "url": url})
    response = await SberAuthCallbackView().post(request)
    assert response.status == 400


async def test_callback_view_url_without_code():
    """Test callback with URL missing code= parameter returns 400."""
    request = _make_callback_request(
        {
            "flow_id": "test-flow",
            "url": "companionapp://host&scope=openid&state=xxx",
        }
    )
    response = await SberAuthCallbackView().post(request)
    assert response.status == 400


async def test_callback_view_flow_not_found():
    """Test callback returns 404 when flow is not in pending_auth_flows."""
    request = _make_callback_request(
        {"flow_id": "gone-flow", "url": "companionapp://host?code=abc"},
        hass=_make_hass("gone-flow"),
    )
    with patch.dict(pending_auth_flows, {}, clear=True):
        response = await SberAuthCallbackView().post(request)
    assert response.status == 404


async def test_callback_view_flow_not_in_progress():
    """OAuth-flow ещё в pending, но в HA уже прерван — 404, код не обменивается."""
    mock_client = AsyncMock()
    mock_client.authorize_by_url = AsyncMock(return_value=True)
    request = _make_callback_request(
        {"flow_id": "test-flow", "url": "companionapp://host?code=abc"},
        hass=_make_hass(),
    )
    with patch.dict(pending_auth_flows, {"test-flow": PendingFlow(client=mock_client)}):
        response = await SberAuthCallbackView().post(request)
    assert response.status == 404
    mock_client.authorize_by_url.assert_not_awaited()


async def test_callback_view_auth_failed():
    """Test callback returns 401 when authorize_by_url fails."""
    mock_client = AsyncMock()
    mock_client.authorize_by_url = AsyncMock(return_value=False)

    request = _make_callback_request(
        {"flow_id": "test-flow", "url": "companionapp://host?code=expired"},
        hass=_make_hass("test-flow"),
    )

    with patch.dict(pending_auth_flows, {"test-flow": PendingFlow(client=mock_client)}):
        response = await SberAuthCallbackView().post(request)

    assert response.status == 401


def test_find_pending_flow_rejects_malformed_flow_id():
    """Хелпер сам отбрасывает неверный flow_id, даже если он есть в pending."""
    bad = '";alert(1)//'
    hass = _make_hass(bad)
    with patch.dict(pending_auth_flows, {bad: PendingFlow(client=MagicMock())}):
        assert auth_view_module._find_pending_flow(hass, bad) is None
    hass.config_entries.flow.async_progress_by_handler.assert_not_called()
