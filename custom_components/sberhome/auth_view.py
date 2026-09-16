"""HTTP views for SberHome OAuth2 authorization flow.

Оба view открыты без авторизации HA (``requires_auth = False``): страницу
открывает попап внешнего шага config flow, у которого нет Bearer-токена.
Поэтому ни одно значение из запроса не попадает в ответ как есть:

- ``flow_id`` проверяется по формату и должен принадлежать незавершённому
  flow этой интеграции, для которого мост сам начал OAuth;
- ссылка на Сбер ID берётся из серверного состояния flow, а не из query,
  и дополнительно сверяется со схемой и хостом эндпоинта авторизации;
- значения в HTML экранируются, inline-скрипт и стили разрешены только по
  одноразовому nonce из Content-Security-Policy.
"""

from __future__ import annotations

import html
import re
import secrets
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .aiosber.const import AUTHORIZE_ENDPOINT
from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .auth_state import PendingFlow

_TEMPLATE_PATH = Path(__file__).parent / "auth_page.html"
_AUTH_PAGE_TEMPLATE: Template | None = None

_FLOW_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
"""Допустимый формат flow_id: ULID/UUID-hex HA, без спецсимволов."""

_AUTH_URL_PARTS = urlsplit(AUTHORIZE_ENDPOINT)
"""Схема, хост и порт эндпоинта авторизации Сбер ID — единственный допустимый адрес."""

_INVALID_LINK_MESSAGE = (
    "Ссылка авторизации недействительна или устарела. "
    "Закройте это окно и начните настройку интеграции SberHome заново."
)
"""Текст ответа на неверный/чужой flow_id — без отражения входных данных."""


async def _get_template(hass: HomeAssistant) -> Template:
    """Load and cache the auth page HTML template."""
    global _AUTH_PAGE_TEMPLATE
    if _AUTH_PAGE_TEMPLATE is None:
        content = await hass.async_add_executor_job(_TEMPLATE_PATH.read_text, "utf-8")
        _AUTH_PAGE_TEMPLATE = Template(content)
    return _AUTH_PAGE_TEMPLATE


def _is_valid_flow_id(flow_id: Any) -> bool:
    """Return True if ``flow_id`` is a string in the expected HA flow_id format."""
    return isinstance(flow_id, str) and _FLOW_ID_RE.fullmatch(flow_id) is not None


def _is_trusted_auth_url(url: str) -> bool:
    """Return True if ``url`` points to the Sber ID authorization endpoint over https.

    Args:
        url: URL, который будет подставлен в ссылку «Войти через Сбер ID».

    Returns:
        True только для ``https`` на хосте и порту ``AUTHORIZE_ENDPOINT``.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname == _AUTH_URL_PARTS.hostname
        and port == _AUTH_URL_PARTS.port
        and not parts.username
        and not parts.password
    )


def _flow_in_progress(hass: HomeAssistant, flow_id: str) -> bool:
    """Return True if ``flow_id`` is an in-progress config/reauth flow of this domain."""
    return any(
        flow.get("flow_id") == flow_id
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    )


def _find_pending_flow(hass: HomeAssistant, flow_id: Any) -> PendingFlow | None:
    """Return the pending OAuth flow for ``flow_id`` if it is valid and still active.

    Args:
        hass: Home Assistant instance.
        flow_id: Значение из запроса (ещё не проверенное).

    Returns:
        ``PendingFlow`` или None, если flow_id неверного формата, мост не
        начинал для него OAuth или flow уже не выполняется в HA.
    """
    from .auth_state import pending_auth_flows

    if not _is_valid_flow_id(flow_id):
        return None
    pending = pending_auth_flows.get(flow_id)
    if pending is None or not _flow_in_progress(hass, flow_id):
        return None
    return pending


def _error_response(status: int) -> web.Response:
    """Build a plain-text error response that never echoes request input."""
    return web.Response(
        text=_INVALID_LINK_MESSAGE,
        status=status,
        content_type="text/plain",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


class SberAuthStartView(HomeAssistantView):
    """Serve the SberHome authorization helper page."""

    requires_auth = False
    url = "/auth/sberhome"
    name = "auth:sberhome"

    async def get(self, request: web.Request) -> web.Response:
        """Return the auth helper HTML page.

        Args:
            request: GET-запрос с ``flow_id`` в query. Параметр ``auth_url``,
                если передан, игнорируется — ссылка берётся из состояния flow.

        Returns:
            HTML-страница (200), 400 при неверном формате ``flow_id`` или
            404, если flow не найден / уже завершён.
        """
        flow_id = request.query.get("flow_id", "")
        if not _is_valid_flow_id(flow_id):
            return _error_response(400)

        hass = request.app["hass"]
        pending = _find_pending_flow(hass, flow_id)
        if pending is None:
            return _error_response(404)
        if not _is_trusted_auth_url(pending.auth_url):
            LOGGER.warning("SberHome auth page: unexpected authorization URL, refusing to render")
            return _error_response(400)

        nonce = secrets.token_urlsafe(16)
        template = await _get_template(hass)
        page = template.substitute(
            flow_id=html.escape(flow_id, quote=True),
            auth_url=html.escape(pending.auth_url, quote=True),
            nonce=nonce,
        )
        csp = (
            "default-src 'none'; "
            f"script-src 'nonce-{nonce}'; "
            f"style-src 'nonce-{nonce}'; "
            "connect-src 'self'; "
            "base-uri 'none'; "
            "form-action 'none'; "
            "frame-ancestors 'none'"
        )
        return web.Response(
            text=page,
            content_type="text/html",
            headers={
                "Content-Security-Policy": csp,
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            },
        )


class SberAuthCallbackView(HomeAssistantView):
    """Handle the OAuth callback from the auth page."""

    requires_auth = False
    url = "/auth/sberhome/callback"
    name = "auth:sberhome:callback"

    async def post(self, request: web.Request) -> web.Response:
        """Receive the companionapp:// URL, validate auth, and complete the flow."""
        # Страница шлёт только application/json. «Простые» кросс-доменные
        # POST (text/plain, form) без CORS preflight сюда не пропускаем.
        if request.content_type != "application/json":
            return web.json_response({"status": "error", "error": "Invalid request"}, status=415)

        try:
            data = await request.json()
        except (ValueError, TypeError):
            return web.json_response({"status": "error", "error": "Invalid request"}, status=400)

        if not isinstance(data, dict):
            return web.json_response({"status": "error", "error": "Invalid request"}, status=400)

        flow_id = data.get("flow_id")
        url = data.get("url", "")

        if not _is_valid_flow_id(flow_id) or not isinstance(url, str):
            return web.json_response(
                {"status": "error", "error": "Missing flow_id or invalid URL"},
                status=400,
            )
        if not url.startswith("companionapp://"):
            return web.json_response(
                {"status": "error", "error": "Missing flow_id or invalid URL"},
                status=400,
            )

        if "code=" not in url:
            return web.json_response(
                {
                    "status": "error",
                    "error": "URL не содержит код авторизации. "
                    "Убедитесь, что вы прошли авторизацию в Сбер ID "
                    "и скопировали URL с параметром code=...",
                },
                status=400,
            )

        hass = request.app["hass"]
        flow = _find_pending_flow(hass, flow_id)
        if not flow:
            return web.json_response(
                {"status": "error", "error": "Flow not found or already completed"},
                status=404,
            )

        result = await flow.client.authorize_by_url(url)
        if not result:
            return web.json_response(
                {
                    "status": "error",
                    "error": "Ошибка авторизации. Код мог устареть — попробуйте заново.",
                },
                status=401,
            )

        try:
            await hass.config_entries.flow.async_configure(flow_id, user_input={})
        except Exception:
            safe_flow_id = str(flow_id).replace("\r", "").replace("\n", "")
            LOGGER.debug("Failed to configure flow %s", safe_flow_id, exc_info=True)
            return web.json_response(
                {"status": "error", "error": "Flow configuration failed"},
                status=500,
            )

        return web.json_response({"status": "ok"})
