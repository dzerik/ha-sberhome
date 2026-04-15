"""HTTP views for SberHome OAuth2 authorization flow."""

from __future__ import annotations

from pathlib import Path
from string import Template
from urllib.parse import unquote

from aiohttp import web

from homeassistant.components.http import HomeAssistantView

from .const import LOGGER

_TEMPLATE_PATH = Path(__file__).parent / "auth_page.html"
_AUTH_PAGE_TEMPLATE: Template | None = None


async def _get_template(hass) -> Template:
    """Load and cache the auth page HTML template."""
    global _AUTH_PAGE_TEMPLATE  # noqa: PLW0603
    if _AUTH_PAGE_TEMPLATE is None:
        content = await hass.async_add_executor_job(
            _TEMPLATE_PATH.read_text, "utf-8"
        )
        _AUTH_PAGE_TEMPLATE = Template(content)
    return _AUTH_PAGE_TEMPLATE


class SberAuthStartView(HomeAssistantView):
    """Serve the SberHome authorization helper page."""

    requires_auth = False
    url = "/auth/sberhome"
    name = "auth:sberhome"

    async def get(self, request: web.Request) -> web.Response:
        """Return the auth helper HTML page."""
        flow_id = request.query.get("flow_id", "")
        auth_url = unquote(request.query.get("auth_url", ""))

        hass = request.app["hass"]
        template = await _get_template(hass)
        html = template.substitute(flow_id=flow_id, auth_url=auth_url)
        return web.Response(text=html, content_type="text/html")


class SberAuthCallbackView(HomeAssistantView):
    """Handle the OAuth callback from the auth page."""

    requires_auth = False
    url = "/auth/sberhome/callback"
    name = "auth:sberhome:callback"

    async def post(self, request: web.Request) -> web.Response:
        """Receive the companionapp:// URL, validate auth, and complete the flow."""
        from .auth_state import pending_auth_flows

        try:
            data = await request.json()
        except (ValueError, TypeError):
            return web.json_response(
                {"status": "error", "error": "Invalid request"}, status=400
            )

        flow_id = data.get("flow_id")
        url = data.get("url", "")

        if not flow_id or not url.startswith("companionapp://"):
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

        client = pending_auth_flows.get(flow_id)
        if not client:
            return web.json_response(
                {"status": "error", "error": "Flow not found or already completed"},
                status=404,
            )

        result = await client.authorize_by_url(url)
        if not result:
            return web.json_response(
                {
                    "status": "error",
                    "error": "Ошибка авторизации. Код мог устареть — "
                    "попробуйте заново.",
                },
                status=401,
            )

        hass = request.app["hass"]
        try:
            await hass.config_entries.flow.async_configure(flow_id, user_input={})
        except Exception:
            LOGGER.debug("Failed to configure flow %s", flow_id, exc_info=True)
            return web.json_response(
                {"status": "error", "error": "Flow configuration failed"},
                status=500,
            )

        return web.json_response({"status": "ok"})
