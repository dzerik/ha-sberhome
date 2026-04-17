"""SberClient — высокоуровневый фасад над всеми API-доменами.

Это **public entry point** для 80% задач. Низкоуровневые модули
(`auth/`, `transport/`, `api/`) — для оставшихся 20% продвинутых случаев.

Использование:

    # Если companion-токен уже есть (например в config_entry.data):
    async with SberClient.from_companion_token("eyJ...") as client:
        devices = await client.devices.list()
        await client.devices.set_state(devices[0].id, [
            AttributeValueDto.of_bool(AttrKey.ON_OFF, True),
        ])

    # Если нужен полный OAuth setup:
    async with SberClient.from_oauth_setup(
        sberid_tokens=SberIdTokens(...),
        token_store=InMemoryTokenStore(),
    ) as client:
        ...

    # Если нужно полное управление (DI всех слоёв):
    http = httpx.AsyncClient(verify=ssl_context)
    auth = AuthManager(http=http, store=store, sberid_tokens=...)
    transport = HttpTransport(http=http, auth=auth)
    client = SberClient(transport=transport)

Жизненный цикл: `aclose()` закрывает только **`transport`** (вместе с `http`).
Если httpx-клиент инжектируется снаружи — управляйте им сами.
"""

from __future__ import annotations

from typing import Any

import httpx

from .api import DeviceAPI, GroupAPI, IndicatorAPI, PairingAPI, ScenarioAPI
from .auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
    SberIdTokens,
    TokenStore,
)
from .const import (
    COMPANION_BASE_URL,
    COMPANION_TOKEN_PATH,
    DEFAULT_CLIENT_ID,
    GATEWAY_BASE_URL,
    TOKEN_ENDPOINT,
)
from .service import DeviceService, GroupService, ScenarioService, StateCache
from .transport import HttpTransport, SslContextProvider


class SberClient:
    """Async client for the Sber Smart Home Gateway API.

    Args:
        transport: pre-configured `HttpTransport` (DI). SberClient владеет
            этим транспортом и закрывает его при `aclose()`.
    """

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport
        # Low-level API (endpoint-per-method)
        self._devices = DeviceAPI(transport)
        self._groups = GroupAPI(transport)
        self._scenarios = ScenarioAPI(transport)
        self._pairing = PairingAPI(transport)
        self._indicator = IndicatorAPI(transport)
        # Service layer (high-level, typed, with state cache)
        self._state = StateCache()
        self._device_service = DeviceService(self._devices, self._state)
        self._group_service = GroupService(self._groups, self._state)
        self._scenario_service = ScenarioService(self._scenarios)

    # ----- Low-level API domains -----
    @property
    def devices(self) -> DeviceAPI:
        return self._devices

    @property
    def groups(self) -> GroupAPI:
        return self._groups

    @property
    def scenarios(self) -> ScenarioAPI:
        return self._scenarios

    @property
    def pairing(self) -> PairingAPI:
        return self._pairing

    @property
    def indicator(self) -> IndicatorAPI:
        return self._indicator

    @property
    def transport(self) -> HttpTransport:
        """Доступ к низкоуровневому транспорту (для редких custom-запросов)."""
        return self._transport

    # ----- Service layer (high-level) -----
    @property
    def state(self) -> StateCache:
        """Typed in-memory state cache."""
        return self._state

    @property
    def device_service(self) -> DeviceService:
        """High-level device operations."""
        return self._device_service

    @property
    def group_service(self) -> GroupService:
        """High-level group/room operations."""
        return self._group_service

    @property
    def scenario_service(self) -> ScenarioService:
        """High-level scenario operations."""
        return self._scenario_service

    async def refresh(self) -> None:
        """Full refresh: fetch tree → update state cache."""
        await self._device_service.refresh()

    # ----- Lifecycle -----
    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> SberClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ----- Factories -----
    @classmethod
    async def from_companion_token(
        cls,
        access_token: str,
        *,
        refresh_token: str | None = None,
        expires_in: int = 86400,
        ssl_provider: SslContextProvider | None = None,
        base_url: str = GATEWAY_BASE_URL,
    ) -> SberClient:
        """Quick constructor: companion-токен уже известен.

        НЕ умеет refresh токенов (нет SberID). При истечении токена кинется
        `InvalidGrant` и нужно будет пересоздать клиент.

        Подходит для:
        - CLI-сценариев с долгоживущим токеном.
        - Тестов.
        """
        ssl_provider = ssl_provider or SslContextProvider()
        ssl_ctx = await ssl_provider.get()
        http = httpx.AsyncClient(verify=ssl_ctx)
        store = InMemoryTokenStore(
            initial=CompanionTokens(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
            )
        )
        auth = AuthManager(http=http, store=store)
        transport = HttpTransport(http=http, auth=auth, base_url=base_url)
        return cls(transport=transport)

    @classmethod
    async def from_oauth_setup(
        cls,
        sberid_tokens: SberIdTokens,
        *,
        token_store: TokenStore | None = None,
        client_id: str = DEFAULT_CLIENT_ID,
        ssl_provider: SslContextProvider | None = None,
        base_url: str = GATEWAY_BASE_URL,
        token_endpoint: str = TOKEN_ENDPOINT,
        companion_endpoint: str = COMPANION_BASE_URL + COMPANION_TOKEN_PATH,
    ) -> SberClient:
        """Полная инициализация после успешного OAuth-flow.

        Args:
            sberid_tokens: токены из `exchange_code_for_tokens()`.
            token_store: где хранить companion-токены.
                По умолчанию — InMemoryTokenStore (теряется при перезапуске).
            ...

        Поддерживает auto-refresh через AuthManager.
        """
        ssl_provider = ssl_provider or SslContextProvider()
        ssl_ctx = await ssl_provider.get()
        http = httpx.AsyncClient(verify=ssl_ctx)
        store = token_store or InMemoryTokenStore()
        auth = AuthManager(
            http=http,
            store=store,
            sberid_tokens=sberid_tokens,
            client_id=client_id,
            token_endpoint=token_endpoint,
            companion_endpoint=companion_endpoint,
        )
        transport = HttpTransport(http=http, auth=auth, base_url=base_url)
        return cls(transport=transport)


__all__ = ["SberClient"]
