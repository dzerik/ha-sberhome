"""Tests for `HomeAPI` wiring — token_store + shared http DI."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import (
    CompanionTokens,
    InMemoryTokenStore,
    SberIdTokens,
)
from custom_components.sberhome.api import HomeAPI, SberAPI


def _make_sber(*, http: httpx.AsyncClient | None = None) -> SberAPI:
    return SberAPI(
        token={
            "access_token": "sid_access",
            "refresh_token": "sid_refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
            "obtained_at": 0,
        },
        http=http,
        owns_http=False,
    )


@pytest.mark.asyncio
async def test_home_api_defaults_to_in_memory_store() -> None:
    """Без явного `token_store=` HomeAPI должен использовать
    `InMemoryTokenStore` — сохраняет обратную совместимость для
    вызывающих кода (CLI / unit-тесты), которые не хотят персистить
    токены."""
    async with httpx.AsyncClient() as http:
        sber = _make_sber(http=http)
        home = HomeAPI(sber, http=http)

        assert isinstance(home._store, InMemoryTokenStore)
        await home.aclose()
        await sber.aclose()


@pytest.mark.asyncio
async def test_home_api_uses_injected_token_store() -> None:
    """Когда передан кастомный `token_store`, он должен попасть в
    `AuthManager` и использоваться для `load`/`save` companion-токенов
    (HA-адаптер прокидывает `HATokenStore`, который пишет в
    config_entry.data — чтобы токены переживали рестарт)."""
    async with httpx.AsyncClient() as http:
        sber = _make_sber(http=http)

        captured: list[CompanionTokens] = []

        class RecordingStore:
            async def load(self) -> CompanionTokens | None:
                return None

            async def save(self, tokens: CompanionTokens) -> None:
                captured.append(tokens)

            async def clear(self) -> None:
                pass

        store = RecordingStore()
        home = HomeAPI(sber, http=http, token_store=store)

        assert home._store is store
        tokens = CompanionTokens(access_token="companion", expires_in=3600)
        home._auth.set_companion_tokens(tokens)
        await home._auth.persist()
        assert captured == [tokens]

        await home.aclose()
        await sber.aclose()


@pytest.mark.asyncio
async def test_home_api_passes_sberid_tokens_to_auth_manager() -> None:
    """Sanity check: SberID токены из `SberAPI` передаются в AuthManager
    — без этого refresh companion-токена фейлится с `InvalidGrant`."""
    async with httpx.AsyncClient() as http:
        sber = _make_sber(http=http)
        home = HomeAPI(sber, http=http)

        assert home._auth._sberid is not None
        assert isinstance(home._auth._sberid, SberIdTokens)
        assert home._auth._sberid.access_token == "sid_access"

        await home.aclose()
        await sber.aclose()


@pytest.mark.asyncio
async def test_home_api_does_not_close_injected_http() -> None:
    """DI-инжектированный http НЕ должен закрываться в `HomeAPI.aclose()` —
    owner его снаружи (coordinator или config_flow)."""
    async with httpx.AsyncClient() as http:
        sber = _make_sber(http=http)
        home = HomeAPI(sber, http=http)

        await home.aclose()
        await sber.aclose()

        # http ещё жив: _state не закрыт
        assert not http.is_closed


@pytest.mark.asyncio
async def test_sber_api_owns_http_when_flag_set() -> None:
    """При `owns_http=True` SberAPI сам закрывает http в aclose() —
    это паттерн для config_flow OAuth, где SberAPI единственный
    владелец временного httpx."""
    http = httpx.AsyncClient()
    sber = SberAPI(http=http, owns_http=True)

    await sber.aclose()

    assert http.is_closed
