"""HA-side имплементация `aiosber.auth.TokenStore` через ConfigEntry.data.

Это HA-зависимый код, поэтому живёт ВНЕ `aiosber/` (соблюдаем правило
"zero HA imports в aiosber/"). Здесь aiosber используется как зависимость.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .aiosber.auth import CompanionTokens, SberIdTokens
from .const import CONF_TOKEN

CONF_COMPANION_TOKENS = "companion_tokens"
CONF_SBERID_TOKENS = "sberid_tokens"  # reserved (если когда-нибудь будем хранить отдельно)


class HATokenStore:
    """Persist `CompanionTokens` в `config_entry.data[CONF_COMPANION_TOKENS]`.

    HA сам сохраняет config_entry.data в `.storage/core.config_entries`.
    Поэтому нам достаточно вызвать `hass.config_entries.async_update_entry(...)`.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

    async def load(self) -> CompanionTokens | None:
        data = self._entry.data.get(CONF_COMPANION_TOKENS)
        if not data:
            return None
        return CompanionTokens.from_dict(data)

    async def save(self, tokens: CompanionTokens) -> None:
        new_data = {**self._entry.data, CONF_COMPANION_TOKENS: tokens.to_dict()}
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)

    async def clear(self) -> None:
        new_data: dict[str, Any] = {
            k: v for k, v in self._entry.data.items() if k != CONF_COMPANION_TOKENS
        }
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)

    async def save_sberid(self, tokens: SberIdTokens) -> None:
        """Persist ротированные SberID-токены в `entry.data["token"]`.

        Вызывается `AuthManager` callback'ом после каждой успешной ротации
        refresh_token'а. Без этого новый refresh_token остаётся только
        в памяти и после рестарта HA используется устаревший (invalid)
        → forced reauth.
        """
        new_data = {**self._entry.data, CONF_TOKEN: tokens.to_dict()}
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)
