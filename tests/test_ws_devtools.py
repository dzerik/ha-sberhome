"""Журнал сообщений DevTools: подписчики и смена ёмкости."""

from __future__ import annotations

from typing import Any

from custom_components.sberhome.ws_devtools import WsDevToolsRecorder


def test_failing_subscriber_does_not_break_logging_or_other_subscribers() -> None:
    recorder = WsDevToolsRecorder(maxlen=5)
    received: list[dict[str, Any]] = []

    def broken(_record: dict[str, Any]) -> None:
        raise RuntimeError("panel went away")

    recorder.subscribe(broken)
    unsubscribe = recorder.subscribe(received.append)

    record = recorder.record(topic="DEVICE_STATE", device_id="lamp", payload={"a": 1})

    assert received == [record]
    assert list(recorder.log) == [record]
    assert recorder.message_count == 1

    unsubscribe()
    unsubscribe()  # повторная отписка ничего не ломает
    recorder.record(topic="DEVICE_STATE", device_id="lamp", payload={"a": 2})
    assert received == [record]


def test_resize_to_same_capacity_keeps_buffer_object() -> None:
    """Та же ёмкость — буфер не пересоздаётся, и алиасы на него остаются живыми."""
    recorder = WsDevToolsRecorder(maxlen=3)
    log = recorder.log
    recorder.record(topic="t", device_id=None, payload=None)

    recorder.resize(3)
    assert recorder.log is log

    recorder.resize(1)
    assert recorder.log is not log
    assert len(recorder.log) == 1
