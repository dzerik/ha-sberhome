"""Support for SberHome lights — sbermap-driven (PR #4 рефакторинга).

Вся scaling-логика (HSV ranges, color_temp Kelvin↔Sber, brightness 100..900)
живёт в `sbermap.transform.lights`. Платформа лишь оркеструет: читает state
через `light_state_from_dto`, пишет через `build_light_command` →
`_async_send_attrs`.
"""

from __future__ import annotations

import math
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ATTR_WHITE,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aiosber.dto import AttributeValueDto, AttrKey, IndicatorColor
from .const import DOMAIN, LOGGER
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import (
    LightConfig,
    build_light_command,
    light_config_from_dto,
    light_state_from_dto,
    resolve_device_category,
)

_LIGHT_CATEGORIES = {"light", "led_strip"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[LightEntity] = []
    for device_id, dto in coordinator.devices.items():
        category = resolve_device_category(dto)
        if category not in _LIGHT_CATEGORIES:
            continue
        entities.append(SberLightEntity(coordinator, device_id))
    # Sber-wide LED indicator (HSV) — глобальная настройка кольца на
    # колонках. Прикрепляется к virtual device "Sber Indicator". Пользователь
    # может сменить цвет/яркость для статуса "online" из HA UI.
    entities.append(SberIndicatorLight(coordinator))
    async_add_entities(entities)


class SberLightEntity(SberBaseEntity, LightEntity):
    """SberHome light — read/write через sbermap.transform.lights."""

    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        # Config и EFFECT-support извлекаются один раз — оба зависят от
        # device.attributes (capability spec), который меняется только при
        # полном refresh / re-pair устройства.
        self._config: LightConfig = self._compute_config()
        self._supports_effects: bool = self._detect_effect_support()

    def _compute_config(self) -> LightConfig:
        dto = self._device_dto
        return light_config_from_dto(dto) if dto is not None else LightConfig()

    def _detect_effect_support(self) -> bool:
        """Поддерживает ли firmware режим динамических сцен.

        Признак — атрибут `light_mode` в `device.attributes[]` содержит
        enum-value `"scene"`. Reflection-based: если firmware не умеет —
        feature не включится, dropdown в HA не появится.
        """
        dto = self._device_dto
        if dto is None or not dto.attributes:
            return False
        for attr in dto.attributes:
            if attr.key != "light_mode":
                continue
            ev = attr.enum_values
            values = ev.values if ev is not None else None
            if values and "scene" in values:
                return True
        return False

    def _state(self) -> dict[str, Any]:
        dto = self._device_dto
        if dto is None:
            return {}
        return light_state_from_dto(dto, self._config)

    @property
    def is_on(self) -> bool | None:
        return self._state().get("is_on")

    @property
    def brightness(self) -> int | None:
        return self._state().get("brightness")

    @property
    def hs_color(self) -> tuple[float, float] | None:
        if ColorMode.HS not in self.supported_color_modes:
            return None
        return self._state().get("hs_color")

    @property
    def color_temp_kelvin(self) -> int | None:
        if ColorMode.COLOR_TEMP not in self.supported_color_modes:
            return None
        return self._state().get("color_temp_kelvin")

    @property
    def min_color_temp_kelvin(self) -> int:
        return self._config.real_color_temp_range[0]

    @property
    def max_color_temp_kelvin(self) -> int:
        return self._config.real_color_temp_range[1]

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        modes: set[ColorMode] = set()
        cfg = self._config
        if cfg.has_colour and "colour" in cfg.light_modes:
            modes.add(ColorMode.HS)
        # COLOR_TEMP — цветовой режим белого света. BRIGHTNESS сюда НЕ
        # добавляем: HA запрещает его рядом с любым другим режимом, а
        # HS/COLOR_TEMP уже включают управление яркостью.
        if "white" in cfg.light_modes and cfg.has_color_temp:
            modes.add(ColorMode.COLOR_TEMP)
        # BRIGHTNESS — только самостоятельным режимом, когда цвета нет вовсе.
        if not modes and cfg.has_brightness:
            modes.add(ColorMode.BRIGHTNESS)
        return modes or {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        """Current color mode. Must be in `supported_color_modes` — HA 2025+
        валидирует жёстко и выбрасывает HomeAssistantError иначе.

        Раньше возвращался `ColorMode.BRIGHTNESS` безусловно при light_mode=white
        или `UNKNOWN` для неизвестных — оба варианта могут не быть в supported
        set (например когда у лампы нет яркости). Теперь выбираем из supported.
        """
        supported = self.supported_color_modes
        light_mode = self._state().get("light_mode")
        if light_mode == "white":
            if ColorMode.COLOR_TEMP in supported:
                return ColorMode.COLOR_TEMP
            if ColorMode.BRIGHTNESS in supported:
                return ColorMode.BRIGHTNESS
        elif light_mode == "colour":
            if ColorMode.HS in supported:
                return ColorMode.HS
        # Fallback для устройств только с ONOFF, для "music"-mode,
        # или когда light_mode отсутствует в state.
        if ColorMode.ONOFF in supported and len(supported) == 1:
            return ColorMode.ONOFF
        if ColorMode.BRIGHTNESS in supported:
            return ColorMode.BRIGHTNESS
        return next(iter(supported))

    @property
    def supported_features(self) -> LightEntityFeature:
        """LightEntityFeature flags. EFFECT включается только когда firmware
        умеет `light_mode=scene` (см. `_detect_effect_support`).

        НЕ путать с `supported_color_modes` — это разные оси: color modes
        описывают HS/COLOR_TEMP/BRIGHTNESS/ONOFF (как красить), features —
        EFFECT/FLASH/TRANSITION (что ещё умеет лампа поверх цвета).
        """
        if self._supports_effects:
            return LightEntityFeature.EFFECT
        return LightEntityFeature(0)

    @property
    def effect_list(self) -> list[str] | None:
        """Список сцен устройства из enum атрибута `light_scene`.

        Возвращает None если устройство не умеет scene-mode (тогда HA
        не показывает dropdown). Имена сцен — технические enum-значения
        Sber (`candle`, `arctic`, `sunset`, …).
        """
        if not self._supports_effects:
            return None
        return list(self._config.scene_options)

    @property
    def effect(self) -> str | None:
        """Текущая сцена или None.

        Если `light_mode == "scene"` и `light_scene` — известное значение
        из enum устройства, возвращаем его. Иначе None.
        """
        if not self._supports_effects:
            return None
        dto = self._device_dto
        if dto is None or dto.reported_value("light_mode") != "scene":
            return None
        scene = dto.reported_value("light_scene")
        return scene if scene in self._config.scene_options else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        # Effect short-circuit: если HA дал effect-name и устройство умеет
        # scene-mode — отправляем тройку (light_mode=scene, light_scene=<value>,
        # on_off=true). effect-name = enum-значение light_scene напрямую.
        # Неизвестное имя → warning + fall-through на обычный turn_on.
        if (effect_name := kwargs.get(ATTR_EFFECT)) and self._supports_effects:
            if effect_name not in self._config.scene_options:
                LOGGER.warning(
                    "Unknown effect %r for %s — fallback to plain on",
                    effect_name,
                    self._device_id,
                )
                # fall-through to plain on below
            else:
                # light_scene — ENUM-атрибут: Sber отвергает STRING-value
                # ("only enum_value should be set"), нужен of_enum.
                attrs = [
                    AttributeValueDto.of_enum(AttrKey.LIGHT_MODE, "scene"),
                    AttributeValueDto.of_enum(AttrKey.LIGHT_SCENE, effect_name),
                    AttributeValueDto.of_bool(AttrKey.ON_OFF, True),
                ]
                await self._async_send_attrs(attrs)
                return

        # Текущее состояние передаём в build_light_command, чтобы
        # brightness-only решения принимались context-aware (в colour
        # mode brightness идёт через light_colour.v, в white — через
        # light_brightness).
        bundle = build_light_command(
            self._config,
            self._device_id,
            is_on=True,
            brightness=kwargs.get(ATTR_BRIGHTNESS),
            hs_color=kwargs.get(ATTR_HS_COLOR),
            color_temp_kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            white=kwargs.get(ATTR_WHITE),
            current_state=self._state(),
        )
        await self._async_send_attrs(bundle)

    async def async_turn_off(self, **kwargs: Any) -> None:
        bundle = build_light_command(self._config, self._device_id, is_on=False)
        await self._async_send_attrs(bundle)


class SberIndicatorLight(CoordinatorEntity[SberHomeCoordinator], LightEntity):
    """Sber-wide LED indicator color (HSV).

    Источник данных: `IndicatorAPI.get()` через `coordinator.indicator_colors`.
    Sber хранит несколько цветов одновременно (`current_colors[]`) — для
    HA-light entity мы редактируем только первый, как «основной» цвет
    индикатора.

    Если IndicatorAPI отвалился (`coordinator._indicator_disabled`),
    entity остаётся в реестре, но `available=False` пока не пройдёт
    очередной успешный poll или manual refresh.
    """

    _attr_has_entity_name = True
    _attr_name = "LED indicator"
    _attr_unique_id = "sberhome_indicator_color"
    _attr_icon = "mdi:led-strip-variant"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}

    def __init__(self, coordinator: SberHomeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "indicator")},
            "name": "Sber Indicator",
            "manufacturer": "Sberdevices",
            "model": "LED Indicator",
            "entry_type": "service",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.indicator_colors is not None and bool(
            self.coordinator.indicator_colors.current_colors
        )

    def _primary_color(self) -> IndicatorColor | None:
        ic = self.coordinator.indicator_colors
        if ic is None or not ic.current_colors:
            return None
        return ic.current_colors[0]

    @property
    def is_on(self) -> bool | None:
        color = self._primary_color()
        if color is None:
            return None
        return color.brightness > 0

    @property
    def brightness(self) -> int | None:
        color = self._primary_color()
        if color is None:
            return None
        # Sber 0..100 → HA 0..255.
        return min(255, max(0, math.ceil(color.brightness * 255 / 100)))

    @property
    def hs_color(self) -> tuple[float, float] | None:
        color = self._primary_color()
        if color is None:
            return None
        return (float(color.hue), float(color.saturation))

    async def async_turn_on(self, **kwargs: Any) -> None:
        current = self._primary_color()
        if current is None:
            return
        hs = kwargs.get(ATTR_HS_COLOR)
        brightness_ha = kwargs.get(ATTR_BRIGHTNESS)
        new = IndicatorColor(
            id=current.id,
            hue=int(hs[0]) if hs else current.hue,
            saturation=int(hs[1]) if hs else current.saturation,
            brightness=(
                min(100, max(1, math.ceil(brightness_ha * 100 / 255)))
                if brightness_ha is not None
                else (current.brightness or 100)
            ),
        )
        await self.coordinator.async_set_indicator_color(new)

    async def async_turn_off(self, **kwargs: Any) -> None:
        current = self._primary_color()
        if current is None:
            return
        new = IndicatorColor(
            id=current.id,
            hue=current.hue,
            saturation=current.saturation,
            brightness=0,
        )
        await self.coordinator.async_set_indicator_color(new)
