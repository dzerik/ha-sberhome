"""API clients for SberDevices smart home."""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from datetime import datetime, timezone

from authlib.common.security import generate_token
from authlib.integrations.httpx_client import AsyncOAuth2Client
from httpx import AsyncClient, ConnectError, ReadTimeout, Timeout

from .const import (
    AUTH_ENDPOINT,
    CLIENT_ID,
    COMPANION_URL,
    GATEWAY_BASE_URL,
    LOGGER,
    REDIRECT_URI,
    ROOT_CA_PEM,
    TOKEN_ENDPOINT,
    USER_AGENT,
)
from .exceptions import SberApiError, SberAuthError, SberConnectionError
from .utils import extract_devices

REQUEST_TIMEOUT = Timeout(10.0, connect=5.0)
COMMAND_RETRY_DELAY = 1.0


_ssl_context: ssl.SSLContext | None = None


def _get_ssl_context() -> ssl.SSLContext:
    """Get or create SSL context with Russian Trusted Root CA."""
    global _ssl_context  # noqa: PLW0603
    if _ssl_context is None:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cadata=ROOT_CA_PEM)
        _ssl_context = ctx
    return _ssl_context


async def async_init_ssl(hass) -> None:
    """Initialize SSL context in executor (non-blocking)."""
    await hass.async_add_executor_job(_get_ssl_context)


def _parse_jwt_exp(token: str) -> float | None:
    """Extract expiration time from a JWT token without verification."""
    try:
        import base64

        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        # Add padding
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("exp")
    except Exception:
        return None


class SberAPI:
    """OAuth2 client for Sber ID authorization."""

    def __init__(self, token: dict | None = None) -> None:
        self._verify_token = generate_token(64)
        self._oauth_client = AsyncOAuth2Client(
            client_id=CLIENT_ID,
            authorization_endpoint=TOKEN_ENDPOINT,
            token_endpoint=TOKEN_ENDPOINT,
            redirect_uri=REDIRECT_URI,
            code_challenge_method="S256",
            scope="openid",
            grant_type="authorization_code",
            token=token,
            verify=_get_ssl_context(),
            timeout=REQUEST_TIMEOUT,
        )

    @property
    def token(self) -> dict | None:
        return self._oauth_client.token

    def create_authorization_url(self) -> str:
        return self._oauth_client.create_authorization_url(
            AUTH_ENDPOINT,
            nonce=generate_token(),
            code_verifier=self._verify_token,
            partner_name="Салют! Умный дом",
        )[0]

    async def authorize_by_url(self, url: str) -> bool:
        try:
            token = await self._oauth_client.fetch_token(
                TOKEN_ENDPOINT,
                authorization_response=url,
                code_verifier=self._verify_token,
            )
            return token is not None
        except Exception:
            LOGGER.debug("OAuth token exchange failed", exc_info=True)
            return False

    async def fetch_home_token(self) -> str:
        """Fetch IoT gateway token from companion service."""
        try:
            response = await self._oauth_client.get(
                COMPANION_URL,
                headers={"User-Agent": USER_AGENT},
            )
            LOGGER.debug(
                "Companion response: status=%s, length=%s",
                response.status_code,
                len(response.content),
            )
            if response.status_code != 200:
                raise SberAuthError(
                    f"Companion returned HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )
            try:
                data = response.json()
            except (ValueError, TypeError) as err:
                raise SberAuthError(
                    f"Companion returned invalid JSON "
                    f"(status {response.status_code}): {response.text[:200]}"
                ) from err
            if "token" not in data:
                raise SberAuthError(
                    f"No token in companion response: {data}"
                )
            return data["token"]
        except SberAuthError:
            raise
        except (ConnectError, ReadTimeout) as err:
            raise SberConnectionError(
                f"Failed to reach companion service: {err}"
            ) from err
        except Exception as err:
            LOGGER.debug("Failed to fetch home token", exc_info=True)
            raise SberAuthError(f"Failed to fetch home token: {err}") from err

    async def aclose(self) -> None:
        await self._oauth_client.aclose()


class HomeAPI:
    """Client for SberDevices IoT gateway API."""

    def __init__(self, sber: SberAPI) -> None:
        self._sber = sber
        self._client = AsyncClient(
            base_url=GATEWAY_BASE_URL,
            verify=_get_ssl_context(),
            timeout=REQUEST_TIMEOUT,
        )
        self._gateway_token: str | None = None
        self._gateway_token_exp: float = 0
        self._cached_devices: dict = {}

    def get_cached_devices_dto(self) -> dict:
        """Lazy-конвертит raw → DeviceDto для sbermap (PR #2 совместимость)."""
        from .aiosber.dto.device import DeviceDto

        out: dict = {}
        for device_id, raw in self._cached_devices.items():
            dto = DeviceDto.from_dict(raw)
            if dto is not None:
                out[device_id] = dto
        return out

    async def update_token(self) -> None:
        """Refresh gateway token if expired or about to expire."""
        now = time.time()
        if self._gateway_token and now < self._gateway_token_exp - 60:
            return
        token = await self._sber.fetch_home_token()
        self._client.headers.update({"X-AUTH-jwt": token})
        self._gateway_token = token
        exp = _parse_jwt_exp(token)
        self._gateway_token_exp = exp if exp else now + 3600
        LOGGER.debug(
            "Gateway token refreshed, expires in %ds",
            int(self._gateway_token_exp - now),
        )

    async def request(
        self, method: str, url: str, retry: bool = True, **kwargs
    ) -> dict:
        """Make an authenticated request to the gateway API."""
        await self.update_token()

        try:
            res = await self._client.request(method, url, **kwargs)
        except (ConnectError, ReadTimeout) as err:
            raise SberConnectionError(
                f"Connection error: {err}"
            ) from err

        if res.status_code == 429:
            retry_after = int(res.headers.get("Retry-After", "60"))
            LOGGER.warning("API rate limited, retry after %ds", retry_after)
            raise SberApiError(
                code=429,
                status_code=429,
                message=f"Rate limited, retry after {retry_after}s",
                retry_after=retry_after,
            )

        if res.status_code != 200:
            try:
                obj = res.json()
                code = obj.get("code", -1)
                message = obj.get("message", "Unknown error")
            except (ValueError, KeyError):
                raise SberApiError(
                    code=-1,
                    status_code=res.status_code,
                    message=res.text,
                )
            # code 16 = expired token
            if code == 16:
                LOGGER.debug("Gateway token expired, forcing refresh")
                self._gateway_token_exp = 0
                if retry:
                    return await self.request(
                        method, url, retry=False, **kwargs
                    )
                raise SberAuthError("Token expired and retry failed")
            raise SberApiError(
                code=code, status_code=res.status_code, message=message
            )

        return res.json()

    async def get_device_tree(self) -> dict:
        return (await self.request("GET", "/device_groups/tree"))["result"]

    async def update_devices_cache(self) -> None:
        device_data = await self.get_device_tree()
        self._cached_devices = extract_devices(device_data)

    def get_cached_devices(self) -> dict:
        return self._cached_devices

    def get_cached_device(self, device_id: str) -> dict:
        return self._cached_devices[device_id]

    async def set_device_state(
        self, device_id: str, state: list[dict]
    ) -> None:
        """Set device state via the gateway API with retry on network errors."""
        try:
            await self._set_device_state_inner(device_id, state)
        except SberConnectionError:
            LOGGER.debug(
                "Command failed for %s, retrying in %ss",
                device_id,
                COMMAND_RETRY_DELAY,
            )
            await asyncio.sleep(COMMAND_RETRY_DELAY)
            await self._set_device_state_inner(device_id, state)

    async def _set_device_state_inner(
        self, device_id: str, state: list[dict]
    ) -> None:
        """Send device state update to the gateway API."""
        await self.request(
            "PUT",
            f"/devices/{device_id}/state",
            json={
                "device_id": device_id,
                "desired_state": state,
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
        )

        # Merge into local cache
        if device_id in self._cached_devices:
            for state_val in state:
                for attribute in self._cached_devices[device_id][
                    "desired_state"
                ]:
                    if attribute["key"] == state_val["key"]:
                        attribute.update(state_val)
                        break

    async def aclose(self) -> None:
        await self._client.aclose()
