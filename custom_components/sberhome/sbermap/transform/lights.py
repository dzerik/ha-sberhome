"""Light scaling helpers — HSV/brightness/color_temp ranges из DeviceDto attributes.

Light в Sber имеет несколько диапазонов, специфичных для конкретного устройства,
которые лежат в `device.attributes[].int_values.range` или `[].color_values`.
HA-сторона ожидает фиксированный 0..255 brightness и Kelvin для color_temp.

Этот модуль переносит ВСЮ логику scaling между Sber и HA из платформы в
sbermap (правило: ad-hoc логика не остаётся в платформах).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.util.color import brightness_to_value, value_to_brightness
from homeassistant.util.scaling import scale_ranged_value_to_int_range

from ...aiosber.dto import AttributeValueDto, ColorValue

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto


# HA reference ranges (canonical).
H_RANGE: tuple[int, int] = (0, 360)
S_RANGE: tuple[int, int] = (0, 100)

# ranges для ColorValue — per-device из DeviceFeatureDto.ColorValues.
# Key на field key: short {h, s, v} (см. GatewayCodec.encode_color). API value
# идёт в native range лампы: для dt_bulb_e27_m (Beken cb2l) это 0..1000
# для s/v, для других — 0..100. Раньше был hardcoded WIRE_*_RANGE = (0, 100)
# и API ключи {hue, saturation, brightness} — из-за длинных ключей backend
# декодировал в zeros и ничего не менял. После перехода на {h, s, v}
# работает native range из config.


@dataclass(slots=True, frozen=True)
class LightConfig:
    """Per-device light scaling config — извлекается один раз из DeviceDto.attributes.

    Используется как для read state (sber→ha), так и для build command (ha→sber).
    """

    brightness_range: tuple[int, int] = (1, 255)
    color_temp_range: tuple[int, int] = (0, 100)
    real_color_temp_range: tuple[int, int] = (2700, 6500)
    color_h_range: tuple[int, int] = (0, 360)
    color_s_range: tuple[int, int] = (0, 100)
    color_v_range: tuple[int, int] = (1, 100)
    has_brightness: bool = False
    has_color_temp: bool = False
    has_colour: bool = False
    light_modes: tuple[str, ...] = ()


def _real_color_temp_range_for(image_set_type: str | None) -> tuple[int, int]:
    """Per-device-type color_temp Kelvin range.

    LED-strip Sber поддерживает шире (2000..6500), обычный bulb — 2700..6500.
    """
    if image_set_type and "ledstrip" in image_set_type:
        return (2000, 6500)
    return (2700, 6500)


def _attr_key(attr: Any) -> str | None:
    """Get attr.key from dict OR DeviceFeatureDto."""
    if isinstance(attr, dict):
        return attr.get("key")
    return getattr(attr, "key", None)


def _attr_int_range(attributes: list[Any] | None, key: str) -> tuple[int, int] | None:
    """Найти `int_values.range` у атрибута с указанным key.

    Поддерживает оба формата: dict (legacy mock в тестах) и
    `DeviceFeatureDto` (парсированный DTO от реального API). Раньше
    ограничение `isinstance(attr, dict)` ломало lookup для всех реальных
    устройств — `has_brightness=False`, supported_color_modes → {ONOFF}.
    """
    if not attributes:
        return None
    for attr in attributes:
        if _attr_key(attr) != key:
            continue
        if isinstance(attr, dict):
            ranges = (attr.get("int_values") or {}).get("range")
            if ranges:
                return (int(ranges["min"]), int(ranges["max"]))
        else:
            int_values = getattr(attr, "int_values", None)
            ranges = getattr(int_values, "range", None) if int_values else None
            if ranges is not None:
                return (int(ranges.min), int(ranges.max))
    return None


def _attr_color_ranges(
    attributes: list[Any] | None,
) -> dict[str, tuple[int, int]] | None:
    if not attributes:
        return None
    for attr in attributes:
        if _attr_key(attr) != "light_colour":
            continue
        if isinstance(attr, dict):
            cv = attr.get("color_values") or {}
            try:
                return {
                    "h": (int(cv["h"]["min"]), int(cv["h"]["max"])),
                    "s": (int(cv["s"]["min"]), int(cv["s"]["max"])),
                    "v": (int(cv["v"]["min"]), int(cv["v"]["max"])),
                }
            except (KeyError, TypeError):
                return None
        else:
            cv = getattr(attr, "color_values", None)
            if cv is None:
                return None
            try:
                return {
                    "h": (int(cv.h.min), int(cv.h.max)),
                    "s": (int(cv.s.min), int(cv.s.max)),
                    "v": (int(cv.v.min), int(cv.v.max)),
                }
            except AttributeError:
                return None
    return None


def _attr_enum_options(attributes: list[Any] | None, key: str) -> tuple[str, ...]:
    if not attributes:
        return ()
    for attr in attributes:
        if _attr_key(attr) != key:
            continue
        if isinstance(attr, dict):
            values = (attr.get("enum_values") or {}).get("values") or []
            return tuple(values)
        ev = getattr(attr, "enum_values", None)
        values = getattr(ev, "values", None) if ev else None
        return tuple(values) if values else ()
    return ()


def light_config_from_dto(dto: DeviceDto) -> LightConfig:
    """Извлечь LightConfig из DeviceDto.attributes."""
    br_range = _attr_int_range(dto.attributes, "light_brightness")
    ct_range = _attr_int_range(dto.attributes, "light_colour_temp")
    color_ranges = _attr_color_ranges(dto.attributes)
    light_modes = _attr_enum_options(dto.attributes, "light_mode")
    return LightConfig(
        brightness_range=br_range or (1, 255),
        color_temp_range=ct_range or (0, 100),
        real_color_temp_range=_real_color_temp_range_for(dto.image_set_type),
        color_h_range=color_ranges["h"] if color_ranges else (0, 360),
        color_s_range=color_ranges["s"] if color_ranges else (0, 100),
        color_v_range=color_ranges["v"] if color_ranges else (1, 100),
        has_brightness=br_range is not None,
        has_color_temp=ct_range is not None,
        has_colour=color_ranges is not None,
        light_modes=light_modes,
    )


def _desired_value(dto: DeviceDto, key: str) -> Any:
    """Берём значение из desired_state через type-aware диспатч.

    Делегирует к `AttributeValueDto.value` property, которое строго
    уважает `av.type`. Это критично для устройств типа `dt_bulb_e27_m`,
    где API-payload заполняет все value-поля дефолтами (bool_value: false,
    integer_value: "0"), и наивный "первое не-None" возвращал
    `bool_value=False` для COLOR атрибута → crash в scale_ranged_value.
    """
    for av in dto.desired_state:
        if av.key == key:
            return av.value
    return None


def light_state_from_dto(dto: DeviceDto, config: LightConfig) -> dict[str, Any]:
    """Полный read-only view light state из DeviceDto, с применённым scaling.

    Возвращает dict: is_on, brightness (0..255), hs_color, color_temp_kelvin,
    light_mode ("colour"|"white"), color_value (raw {h,s,v} dict если есть).
    """
    is_on = _desired_value(dto, "on_off")
    light_mode = _desired_value(dto, "light_mode")
    brightness_raw = _desired_value(dto, "light_brightness")
    color_obj = _desired_value(dto, "light_colour")

    brightness: int | None = None
    if light_mode == "colour" and color_obj is not None and int(color_obj.brightness) > 0:
        # В colour-mode brightness хранится в V компоненте color_value.
        # Range — per-device из config.color_v_range (для cb2l это 0..1000,
        # для других ламп 0..100).
        # ВАЖНО: `color_obj.brightness > 0` — Sber API для некоторых ламп
        # (Beken cb2l) возвращает reported `color_value: {0,0,0}` даже
        # когда лампа реально светит (баг Sber backend). В этом случае
        # fallback на общий light_brightness — он у lamp обновляется
        # корректно.
        brightness = value_to_brightness(config.color_v_range, int(color_obj.brightness))
    elif brightness_raw is not None:
        brightness = value_to_brightness(config.brightness_range, int(brightness_raw))

    hs_color: tuple[float, float] | None = None
    if color_obj is not None:
        hs_color = (
            scale_ranged_value_to_int_range(config.color_h_range, H_RANGE, int(color_obj.hue)),
            scale_ranged_value_to_int_range(
                config.color_s_range, S_RANGE, int(color_obj.saturation)
            ),
        )

    color_temp_kelvin: int | None = None
    color_temp_raw = _desired_value(dto, "light_colour_temp")
    if color_temp_raw is not None and config.has_color_temp:
        color_temp_kelvin = scale_ranged_value_to_int_range(
            config.color_temp_range, config.real_color_temp_range, int(color_temp_raw)
        )

    return {
        "is_on": bool(is_on) if is_on is not None else None,
        "brightness": brightness,
        "hs_color": hs_color,
        "color_temp_kelvin": color_temp_kelvin,
        "light_mode": light_mode,
    }


def build_light_command(
    config: LightConfig,
    device_id: str,
    *,
    is_on: bool,
    brightness: int | None = None,
    hs_color: tuple[float, float] | None = None,
    color_temp_kelvin: int | None = None,
    white: int | None = None,
    current_state: dict | None = None,
) -> list[AttributeValueDto]:
    """Build list[AttributeValueDto] для команды light, с per-device scaling.

    Args:
        current_state: опциональное текущее состояние (output
            `light_state_from_dto`). Используется для context-aware
            brightness-only commands: в colour mode brightness идёт через
            `light_colour.v` (сохраняя текущие h/s), в white — через
            отдельный `light_brightness`.
    """
    attrs: list[AttributeValueDto] = [AttributeValueDto.of_bool("on_off", is_on)]

    def _brightness_attr(ha_val: int) -> AttributeValueDto:
        return AttributeValueDto.of_int(
            "light_brightness",
            math.ceil(brightness_to_value(config.brightness_range, ha_val)),
        )

    if hs_color is not None:
        h, s = hs_color
        # Если brightness не указана в команде — сохраняем текущую.
        # Раньше безусловно шло `brightness or 255` → любое изменение цвета
        # сбрасывало лампу на 100% яркости.
        if brightness is not None:
            v_brightness = brightness
        elif current_state and current_state.get("brightness") is not None:
            v_brightness = current_state["brightness"]
        else:
            v_brightness = 255
        # light_mode шлём только если лампа ещё НЕ в colour mode. Для
        # некоторых прошивок (Beken cb2l) повторный light_mode сбрасывает
        # color_value в нули.
        current_mode = (current_state or {}).get("light_mode")
        if current_mode != "colour":
            attrs.append(AttributeValueDto.of_enum("light_mode", "colour"))
        attrs.append(
            AttributeValueDto.of_color(
                "light_colour",
                ColorValue(
                    hue=scale_ranged_value_to_int_range(H_RANGE, config.color_h_range, h),
                    saturation=scale_ranged_value_to_int_range(S_RANGE, config.color_s_range, s),
                    brightness=math.ceil(brightness_to_value(config.color_v_range, v_brightness)),
                ),
            )
        )
        if brightness is not None:
            attrs.append(_brightness_attr(brightness))
    elif color_temp_kelvin is not None:
        sber_temp = scale_ranged_value_to_int_range(
            config.real_color_temp_range, config.color_temp_range, color_temp_kelvin
        )
        attrs.append(AttributeValueDto.of_enum("light_mode", "white"))
        attrs.append(AttributeValueDto.of_int("light_colour_temp", max(0, sber_temp)))
        if brightness is not None:
            attrs.append(_brightness_attr(brightness))
    elif white is not None:
        attrs.append(AttributeValueDto.of_enum("light_mode", "white"))
        attrs.append(_brightness_attr(white))
    elif brightness is not None:
        # Brightness-only: context-aware по current mode.
        # - white mode: `light_brightness` применяется напрямую.
        # - colour mode: Sber игнорирует `light_brightness`, brightness
        #   хранится в `light_colour.v`. Сохраняем текущие h/s из DTO,
        #   обновляя только v компонент.
        current_mode = (current_state or {}).get("light_mode")
        if current_mode == "colour":
            hs = (current_state or {}).get("hs_color") or (0.0, 0.0)
            h, s = hs
            attrs.append(AttributeValueDto.of_enum("light_mode", "colour"))
            attrs.append(
                AttributeValueDto.of_color(
                    "light_colour",
                    ColorValue(
                        hue=scale_ranged_value_to_int_range(H_RANGE, config.color_h_range, h),
                        saturation=scale_ranged_value_to_int_range(
                            S_RANGE, config.color_s_range, s
                        ),
                        brightness=math.ceil(brightness_to_value(config.color_v_range, brightness)),
                    ),
                )
            )
        else:
            # white (или неизвестный) — шлём light_brightness.
            attrs.append(_brightness_attr(brightness))
    return attrs


__all__ = [
    "H_RANGE",
    "LightConfig",
    "S_RANGE",
    "build_light_command",
    "light_config_from_dto",
    "light_state_from_dto",
]
