"""Support for SberHome binary sensors (declarative via registry)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import (
    BINARY_ONLY_ONLINE_CATEGORIES,
    CATEGORY_BINARY_SENSORS,
    COMMON_BINARY_SENSORS,
    BinarySensorSpec,
    resolve_category,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from .utils import find_from_list


def _has_reported(device: dict, key: str) -> bool:
    if "reported_state" not in device:
        return False
    return find_from_list(device["reported_state"], key) is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericBinarySensor] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        primary = CATEGORY_BINARY_SENSORS.get(category, [])
        # Основной binary sensor создаётся всегда для этих категорий (spec.obligatory),
        # даже если reported_state ещё не пришёл.
        for spec in primary:
            entities.append(SberGenericBinarySensor(coordinator, device_id, spec))
        # Online-индикатор для устройств-шлюзов (hub, intercom).
        if category in BINARY_ONLY_ONLINE_CATEGORIES:
            entities.append(
                SberGenericBinarySensor(
                    coordinator,
                    device_id,
                    BinarySensorSpec(
                        "online",
                        "connectivity",
                        BinarySensorDeviceClass.CONNECTIVITY,
                        EntityCategory.DIAGNOSTIC,
                    ),
                )
            )
        # Общие диагностические — только если feature присутствует.
        for spec in COMMON_BINARY_SENSORS:
            if _has_reported(device, spec.key):
                entities.append(SberGenericBinarySensor(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericBinarySensor(SberBaseEntity, BinarySensorEntity):
    """Универсальный binary sensor через BinarySensorSpec."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: BinarySensorSpec,
    ) -> None:
        super().__init__(coordinator, device_id, spec.suffix)
        self._spec = spec
        self._attr_device_class = spec.device_class
        if spec.entity_category is not None:
            self._attr_entity_category = spec.entity_category
        if not spec.enabled_by_default:
            self._attr_entity_registry_enabled_default = False
        if spec.icon is not None:
            self._attr_icon = spec.icon

    @property
    def is_on(self) -> bool | None:
        state = self._get_reported_state(self._spec.key)
        if state and "bool_value" in state:
            return state["bool_value"]
        return None


# ---- Backwards-compat specialised classes ----


def _bspec(category: str | None, key: str) -> BinarySensorSpec:
    """Найти BinarySensorSpec по (категории, ключу).

    Если category=None — ищем только в COMMON_BINARY_SENSORS.
    """
    pool = COMMON_BINARY_SENSORS if category is None else (
        CATEGORY_BINARY_SENSORS.get(category, []) + COMMON_BINARY_SENSORS
    )
    for s in pool:
        if s.key == key:
            return s
    raise KeyError(f"No binary spec for {category}/{key}")


class SberWaterLeakSensor(SberGenericBinarySensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _bspec("sensor_water_leak", "water_leak_state"))


class SberDoorSensor(SberGenericBinarySensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _bspec("sensor_door", "doorcontact_state"))


class SberMotionSensor(SberGenericBinarySensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _bspec("sensor_pir", "motion_state"))


class SberBatteryLowSensor(SberGenericBinarySensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _bspec(None, "battery_low_power"))
