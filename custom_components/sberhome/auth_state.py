"""Shared state для pending OAuth flows.

Раньше `pending_auth_flows` был простым dict, без TTL — если пользователь
начал OAuth и закрыл вкладку, `SberAPI` с открытым httpx.AsyncClient
висел до рестарта HA (P1 #11 из аудита 2026-04-17).

Теперь — PendingFlow с created_at и функция `cleanup_expired` для GC.
Cleanup вызывается лениво при каждом новом flow в `config_flow`, так
что не требует background task'а.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from time import monotonic
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import SberAPI

_LOGGER = logging.getLogger(__name__)

_TTL_SECONDS = 600.0  # 10 минут — достаточно для browser roundtrip


@dataclass(slots=True)
class PendingFlow:
    """OAuth flow в процессе выполнения.

    `client` — SberAPI с открытым httpx, `created_at` — momotonic timestamp
    для TTL-проверки.
    """

    client: SberAPI
    created_at: float = field(default_factory=monotonic)


# Shared storage для pending auth flows: flow_id -> PendingFlow.
pending_auth_flows: dict[str, PendingFlow] = {}


async def cleanup_expired(ttl: float = _TTL_SECONDS) -> list[str]:
    """Удалить все flows старше TTL + aclose их httpx клиентов.

    Вызывается лениво при каждом новом flow. Возвращает список flow_id,
    которые были очищены — для отладки.

    Ошибки от `aclose()` подавляются: cleanup — best-effort (clients могли
    быть уже закрыты из другого пути, например после успешного `finish`).
    """
    now = monotonic()
    expired_ids = [fid for fid, flow in pending_auth_flows.items() if now - flow.created_at > ttl]
    for fid in expired_ids:
        flow = pending_auth_flows.pop(fid)
        with contextlib.suppress(Exception):
            await flow.client.aclose()
    if expired_ids:
        _LOGGER.debug("Cleaned %d expired OAuth flows: %s", len(expired_ids), expired_ids)
    return expired_ids
