"""Codec Protocol — serialized-format encoder/decoder для Sber API."""

from __future__ import annotations

from typing import Any, Protocol

from ..values import HsvColor, SberState, SberStateBundle, SberValue


class Codec(Protocol):
    """Bidirectional encoder/decoder для одного серилизованный формат (Gateway/C2C)."""

    name: str
    """`gateway` / `c2c` — для error messages и логов."""

    # ---- Value level ----
    def encode_value(self, value: SberValue) -> dict[str, Any]:
        """`SberValue` → API dict (`{type, X_value}`)."""
        ...

    def decode_value(self, raw: dict[str, Any]) -> SberValue:
        """API dict → `SberValue`. Raises CodecError на unknown type."""
        ...

    # ---- Color (специальный case — разные шкалы между протоколами) ----
    def encode_color(self, color: HsvColor) -> dict[str, Any]:
        """canonical HSV → API color dict."""
        ...

    def decode_color(self, raw: dict[str, Any]) -> HsvColor:
        """API color → canonical HSV."""
        ...

    # ---- State (key + value) ----
    def encode_state(self, state: SberState) -> dict[str, Any]:
        """`SberState` → API dict (`{key, ...value}`)."""
        ...

    def decode_state(self, raw: dict[str, Any]) -> SberState:
        """API dict → `SberState`."""
        ...

    # ---- Bundle (полный state набор для одного устройства) ----
    def encode_bundle(self, bundle: SberStateBundle) -> dict[str, Any]:
        """`SberStateBundle` → API dict для PUT/POST в Sber API."""
        ...

    def decode_bundle(self, raw: dict[str, Any]) -> SberStateBundle:
        """API dict → `SberStateBundle` (например из reported_state)."""
        ...
