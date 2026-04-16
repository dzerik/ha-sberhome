"""HA → Sber transform.

Превращает HA-state + attributes в `SberStateBundle`, готовый к encode'у через
Codec (Gateway/C2C). Используется `MQTT-SberGate` интеграцией для публикации
HA-сущностей как виртуальных устройств в облаке Sber.

Гибридный режим: использует `Platform`/`STATE_ON`/`STATE_OFF` enum'ы для
type safety. Brightness scaling — стандартный HA helper (через
`brightness_ha_to_sber` из sber_to_ha.py).

Этот модуль НЕ создаёт SberDevice descriptor (это вне scope sbermap — каждый
проект сам решает как формировать descriptors). Только маппит state.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_ON, Platform

from ..exceptions import MappingError
from ..values import HsvColor, SberState, SberStateBundle, SberValue
from .sber_to_ha import brightness_ha_to_sber


def ha_light_to_sber(
    *,
    device_id: str,
    is_on: bool,
    brightness: int | None = None,
    hs_color: tuple[float, float] | None = None,
    color_temp: int | None = None,
) -> SberStateBundle:
    """HA light state → Sber bundle.

    Args:
        device_id: Sber device ID для bundle.
        is_on: state on/off.
        brightness: HA-brightness 0..255 (опционально).
        hs_color: `(hue 0-360, saturation 0-100)` (опционально).
        color_temp: HA color_temp (mireds).
    """
    states: list[SberState] = [SberState("on_off", SberValue.of_bool(is_on))]
    if brightness is not None:
        # Используем shared HA-helper-обёртку из sber_to_ha.
        states.append(
            SberState("light_brightness", SberValue.of_int(brightness_ha_to_sber(brightness)))
        )
    if hs_color is not None:
        h, s = hs_color
        # HA brightness используется как value-component если есть
        v = round((brightness or 255) * 100 / 255)
        states.append(
            SberState(
                "light_colour",
                SberValue.of_color(HsvColor(int(h), int(s), v)),
            )
        )
    if color_temp is not None:
        states.append(
            SberState("light_colour_temp", SberValue.of_int(int(color_temp)))
        )
    return SberStateBundle(device_id=device_id, states=tuple(states))


def ha_switch_to_sber(*, device_id: str, is_on: bool) -> SberStateBundle:
    """HA switch state → Sber bundle (просто on_off)."""
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("on_off", SberValue.of_bool(is_on)),),
    )


def ha_climate_to_sber(
    *,
    device_id: str,
    is_on: bool,
    target_temperature: float | None = None,
    hvac_mode: str | None = None,
    fan_mode: str | None = None,
) -> SberStateBundle:
    """HA climate state → Sber bundle для HVAC устройства."""
    states: list[SberState] = [SberState("on_off", SberValue.of_bool(is_on))]
    if target_temperature is not None:
        states.append(
            SberState("hvac_temp_set", SberValue.of_int(int(target_temperature)))
        )
    if hvac_mode is not None and hvac_mode != "off":
        states.append(SberState("hvac_work_mode", SberValue.of_enum(hvac_mode)))
    if fan_mode is not None:
        states.append(SberState("hvac_air_flow_power", SberValue.of_enum(fan_mode)))
    return SberStateBundle(device_id=device_id, states=tuple(states))


def ha_cover_to_sber(
    *,
    device_id: str,
    position: int | None,
    command: str | None = None,
) -> SberStateBundle:
    """HA cover state → Sber bundle.

    Args:
        position: 0-100 (current_position) — отправляем как target.
        command: 'open'/'close'/'stop' для разовых команд (если position нет).
    """
    states: list[SberState] = []
    if position is not None:
        states.append(SberState("open_set", SberValue.of_int(int(position))))
    elif command in ("open", "close", "stop"):
        states.append(SberState("open_set", SberValue.of_enum(command)))
    return SberStateBundle(device_id=device_id, states=tuple(states))


def ha_to_sber_generic(
    *,
    device_id: str,
    platform: Platform | str,
    state: Any,
    attributes: dict[str, Any] | None = None,
) -> SberStateBundle:
    """Универсальный entry-point для transform HA → Sber.

    Args:
        device_id: Sber device ID.
        platform: HA `Platform` enum или строковое имя.
        state: HA-state (`STATE_ON`/`STATE_OFF`/HVACMode/...).
        attributes: dict HA-attributes.

    Raises:
        MappingError: если platform не поддерживается.
    """
    attrs = attributes or {}
    state_str = str(state).lower()
    is_on = state_str == STATE_ON
    platform_str = platform.value if isinstance(platform, Platform) else str(platform)

    if platform_str == Platform.LIGHT:
        return ha_light_to_sber(
            device_id=device_id,
            is_on=is_on,
            brightness=attrs.get("brightness"),
            hs_color=attrs.get("hs_color"),
            color_temp=attrs.get("color_temp"),
        )
    if platform_str == Platform.SWITCH:
        return ha_switch_to_sber(device_id=device_id, is_on=is_on)
    if platform_str == Platform.CLIMATE:
        # Для climate state — это HVACMode (cool/heat/...), а не on/off.
        return ha_climate_to_sber(
            device_id=device_id,
            is_on=state_str != "off",
            target_temperature=attrs.get("temperature"),
            hvac_mode=state_str if state_str and state_str != "off" else None,
            fan_mode=attrs.get("fan_mode"),
        )
    if platform_str == Platform.COVER:
        pos = attrs.get("current_position")
        cmd: str | None = None
        if pos is None:
            cmd = "open" if state_str == "open" else "close" if state_str == "closed" else None
        return ha_cover_to_sber(device_id=device_id, position=pos, command=cmd)

    raise MappingError(
        f"No HA→Sber transform для platform {platform!r}",
        platform=platform_str,
    )


__all__ = [
    "ha_climate_to_sber",
    "ha_cover_to_sber",
    "ha_light_to_sber",
    "ha_switch_to_sber",
    "ha_to_sber_generic",
]
