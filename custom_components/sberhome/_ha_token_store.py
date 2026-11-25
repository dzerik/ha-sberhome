"""HA-side имплементации aiosber TokenStore-протоколов через ConfigEntry.data.

Это HA-зависимый код, поэтому живёт ВНЕ `aiosber/` (соблюдаем правило
"zero HA imports в aiosber/"). Здесь aiosber используется как зависимость.

Два независимых store:
- `HATokenStore` — SberID + companion flow (стандарт).
- `HACsafrontTokenStore` — SMS-OTP beta flow.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .aiosber.auth import CompanionTokens, CsafrontTokens, SberIdTokens
from .const import CONF_TOKEN

CONF_COMPANION_TOKENS = "companion_tokens"
CONF_SBERID_TOKENS = "sberid_tokens"  # reserved (если когда-нибудь будем хранить отдельно)
CONF_CSAFRONT_TOKENS = "csafront_tokens"


CONF_AUTH_GENERATION = "auth_generation"
_AUTH_DATA_KEYS = frozenset(
    {
        CONF_TOKEN,
        CONF_COMPANION_TOKENS,
        CONF_CSAFRONT_TOKENS,
        CONF_SBERID_TOKENS,
        "companion_settings_tokens",
    }
)


def async_clear_auth_data(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Forget every local credential bundle and invalidate old token stores."""
    data = {key: value for key, value in entry.data.items() if key not in _AUTH_DATA_KEYS}
    data[CONF_AUTH_GENERATION] = entry.data.get(CONF_AUTH_GENERATION, 0) + 1
    hass.config_entries.async_update_entry(entry, data=data)


class _HATokenStore:
    """Bind credential access to the entry's current authentication generation."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._generation = entry.data.get(CONF_AUTH_GENERATION, 0)

    def _is_current(self) -> bool:
        return self._generation == self._entry.data.get(CONF_AUTH_GENERATION, 0)

    def _update(self, data: dict[str, Any]) -> None:
        if self._is_current():
            self._hass.config_entries.async_update_entry(self._entry, data=data)


class HATokenStore(_HATokenStore):
    """Persist gateway and Sber ID credentials in the HA config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        sberid_key: str = CONF_TOKEN,
    ) -> None:
        super().__init__(hass, entry)
        self._sberid_key = sberid_key

    async def load(self) -> CompanionTokens | None:
        if not self._is_current():
            return None
        data = self._entry.data.get(CONF_COMPANION_TOKENS)
        if not data:
            return None
        return CompanionTokens.from_dict(data)

    async def save(self, tokens: CompanionTokens) -> None:
        self._update({**self._entry.data, CONF_COMPANION_TOKENS: tokens.to_dict()})

    async def clear(self) -> None:
        self._update(
            {key: value for key, value in self._entry.data.items() if key != CONF_COMPANION_TOKENS}
        )

    async def save_sberid(self, tokens: SberIdTokens) -> None:
        """Persist rotated Sber ID tokens only while this session is current."""
        self._update({**self._entry.data, self._sberid_key: tokens.to_dict()})


class HACsafrontTokenStore(_HATokenStore):
    """Persist the SMS/OIDC, gateway and client UUID bundle in HA."""

    async def load(self) -> CsafrontTokens | None:
        if not self._is_current():
            return None
        data = self._entry.data.get(CONF_CSAFRONT_TOKENS)
        if not data:
            return None
        return CsafrontTokens.from_dict(data)

    async def save(self, tokens: CsafrontTokens) -> None:
        self._update({**self._entry.data, CONF_CSAFRONT_TOKENS: tokens.to_dict()})

    async def clear(self) -> None:
        self._update(
            {key: value for key, value in self._entry.data.items() if key != CONF_CSAFRONT_TOKENS}
        )

    async def save_refreshed(self, tokens: CsafrontTokens) -> None:
        """Persist the callback result without reviving an obsolete session."""
        await self.save(tokens)
