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


# ---------------------------------------------------------------------------
# /devices/enums кэш
# ---------------------------------------------------------------------------


def _mock_handler(routes: dict[str, dict]):
    """Build a MockTransport handler dispatching by URL path suffix."""

    def handler(req: httpx.Request) -> httpx.Response:
        for suffix, payload in routes.items():
            if req.url.path.endswith(suffix):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "no route"})

    return handler


@pytest.mark.asyncio
async def test_update_devices_cache_fetches_enums_once() -> None:
    """update_devices_cache подтягивает /devices/enums при первом refresh
    и не дёргает endpoint повторно при следующих refresh — это справочник,
    а не live state."""
    enums_calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal enums_calls
        if req.url.path.endswith("/device_groups/tree"):
            return httpx.Response(200, json={"result": {"devices": [], "children": []}})
        if req.url.path.endswith("/devices/enums"):
            enums_calls += 1
            return httpx.Response(
                200,
                json={
                    "result": {
                        "vacuum_cleaner_status": ["docked", "cleaning", "idle"],
                        "hvac_work_mode": {"values": ["auto", "cool", "heat"]},
                    }
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        sber = _make_sber(http=http)
        store = InMemoryTokenStore(
            initial=CompanionTokens(access_token="C", expires_in=3600)
        )
        home = HomeAPI(sber, http=http, token_store=store)
        await home.update_devices_cache()
        await home.update_devices_cache()
        assert enums_calls == 1
        assert home.get_enum_values("vacuum_cleaner_status") == [
            "docked",
            "cleaning",
            "idle",
        ]
        assert home.get_enum_values("hvac_work_mode") == ["auto", "cool", "heat"]
        # Unknown key — пустой list, не KeyError.
        assert home.get_enum_values("nonexistent") == []
        await home.aclose()
        await sber.aclose()


@pytest.mark.asyncio
async def test_enum_fetch_failure_does_not_break_cache_refresh() -> None:
    """Если /devices/enums недоступен (500/404) — НЕ валим polling.
    Кэш остаётся пустым, при следующем успешном refresh попытаемся снова."""
    enums_calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal enums_calls
        if req.url.path.endswith("/device_groups/tree"):
            return httpx.Response(200, json={"result": {"devices": [], "children": []}})
        if req.url.path.endswith("/devices/enums"):
            enums_calls += 1
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        sber = _make_sber(http=http)
        store = InMemoryTokenStore(
            initial=CompanionTokens(access_token="C", expires_in=3600)
        )
        home = HomeAPI(sber, http=http, token_store=store)
        await home.update_devices_cache()  # не должен пробросить
        assert home.get_cached_enums() == {}
        # Так как кэш пуст — повторно попытаемся при следующем refresh.
        await home.update_devices_cache()
        assert enums_calls == 2
        await home.aclose()
        await sber.aclose()


@pytest.mark.asyncio
async def test_enum_fetch_normalizes_dict_with_objects() -> None:
    """Для list[dict] с полями value/id/name берём первое непустое."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/device_groups/tree"):
            return httpx.Response(200, json={"result": {"devices": [], "children": []}})
        if req.url.path.endswith("/devices/enums"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "fan_mode": [
                            {"value": "low", "name": "Low"},
                            {"value": "high", "name": "High"},
                            {"name": "Garbled — no value"},
                        ],
                    }
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        sber = _make_sber(http=http)
        store = InMemoryTokenStore(
            initial=CompanionTokens(access_token="C", expires_in=3600)
        )
        home = HomeAPI(sber, http=http, token_store=store)
        await home.update_devices_cache()
        # Объекты без value/id попадают в кэш через name (последний fallback).
        assert home.get_enum_values("fan_mode") == ["low", "high", "Garbled — no value"]
        await home.aclose()
        await sber.aclose()
