"""WsDevToolsRecorder — ring buffer WS/command сообщений для DevTools-панели.

Вынесено из ``coordinator.py`` (SOLID-аудит). Хранит последние N сообщений
(входящие WS push'и, исходящие команды, synthetic inject'ы) + live
subscribers для стриминга в панель.

Coordinator держит инстанс и делегирует `_record_ws_message`;
websocket_api/log.py читает `log` / `subscribers` напрямую.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from typing import Any

from .const import LOGGER


class WsDevToolsRecorder:
    """Ring buffer сообщений + notify подписчиков панели."""

    def __init__(self, maxlen: int = 100) -> None:
        self.log: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self.subscribers: list[Callable[[dict[str, Any]], None]] = []
        self.last_message_at: float | None = None
        self.message_count: int = 0

    def record(
        self,
        *,
        topic: str,
        device_id: str | None,
        payload: Any,
        direction: str = "in",
    ) -> dict[str, Any]:
        """Append запись в ring buffer + notify subscribers.

        Args:
            direction: "in" — входящее от Sber через WS, "out" — исходящая
                команда (HTTP PUT), "replay" — synthetic inject из DevTools.

        Returns:
            Записанный record (для доступа к ts вызывающей стороной).
        """
        record = {
            "ts": time.time(),
            "direction": direction,
            "topic": topic,
            "device_id": device_id,
            "payload": payload,
        }
        self.log.append(record)
        self.last_message_at = record["ts"]
        self.message_count += 1
        for sub in list(self.subscribers):
            try:
                sub(record)
            except Exception:  # noqa: BLE001 — подписчик не должен ломать pipeline
                LOGGER.debug("WS log subscriber failed", exc_info=True)
        return record

    def subscribe(self, callback_fn: Callable[[dict[str, Any]], None]) -> Callable[[], None]:
        """Подписаться на новые записи. Возвращает unsubscribe."""
        self.subscribers.append(callback_fn)

        def unsub() -> None:
            if callback_fn in self.subscribers:
                self.subscribers.remove(callback_fn)

        return unsub


__all__ = ["WsDevToolsRecorder"]
