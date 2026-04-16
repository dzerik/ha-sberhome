"""Codec Protocol — wire-format encoder/decoder для Sber API."""

from __future__ import annotations

from typing import Any, Protocol

from ..values import HsvColor, SberState, SberStateBundle, SberValue


class Codec(Protocol):
    """Bidirectional encoder/decoder для одного wire-формата (Gateway/C2C)."""

    name: str
    """`gateway` / `c2c` — для error messages и логов."""

    # ---- Value level ----
    def encode_value(self, value: SberValue) -> dict[str, Any]:
        """`SberValue` → wire dict (`{type, X_value}`)."""
        ...

    def decode_value(self, raw: dict[str, Any]) -> SberValue:
        """wire dict → `SberValue`. Raises CodecError на unknown type."""
        ...

    # ---- Color (специальный case — разные шкалы между протоколами) ----
    def encode_color(self, color: HsvColor) -> dict[str, Any]:
        """canonical HSV → wire color dict."""
        ...

    def decode_color(self, raw: dict[str, Any]) -> HsvColor:
        """wire color → canonical HSV."""
        ...

    # ---- State (key + value) ----
    def encode_state(self, state: SberState) -> dict[str, Any]:
        """`SberState` → wire dict (`{key, ...value}`)."""
        ...

    def decode_state(self, raw: dict[str, Any]) -> SberState:
        """wire dict → `SberState`."""
        ...

    # ---- Bundle (полный state набор для одного устройства) ----
    def encode_bundle(self, bundle: SberStateBundle) -> dict[str, Any]:
        """`SberStateBundle` → wire dict для PUT/POST в Sber API."""
        ...

    def decode_bundle(self, raw: dict[str, Any]) -> SberStateBundle:
        """wire dict → `SberStateBundle` (например из reported_state)."""
        ...
