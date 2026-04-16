"""Exception hierarchy for sbermap.

Полностью независимая иерархия (не наследуем от aiosber.SberError) —
sbermap должен оставаться standalone-ready пакетом.
"""

from __future__ import annotations


class SbermapError(Exception):
    """Base exception for sbermap."""


class CodecError(SbermapError):
    """Encoder/decoder failed.

    Attributes:
        codec: имя codec'а (gateway/c2c).
        kind: что не получилось (encode/decode/unknown_type/...).
        payload: исходные данные (для отладки).
    """

    def __init__(self, codec: str, kind: str, message: str, *, payload: object = None) -> None:
        self.codec = codec
        self.kind = kind
        self.payload = payload
        super().__init__(f"[{codec}/{kind}] {message}")


class MappingError(SbermapError):
    """HA-platform / Sber-category mapping не найден.

    Например: пытаемся найти HA-platform для неизвестной категории Sber.
    """

    def __init__(
        self,
        message: str,
        *,
        category: str | None = None,
        platform: str | None = None,
    ) -> None:
        self.category = category
        self.platform = platform
        super().__init__(message)


class SpecError(SbermapError):
    """Несовместимость со spec: feature без типа, неизвестная категория, etc."""
