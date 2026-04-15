"""Support for SberHome sensors (declarative via registry)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import COMMON_SENSORS, CATEGORY_SENSORS, SensorSpec, resolve_category
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
    entities: list[SberGenericSensor] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        specs = list(CATEGORY_SENSORS.get(category, []))
        specs.extend(COMMON_SENSORS)
        for spec in specs:
            if _has_reported(device, spec.key):
                entities.append(SberGenericSensor(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericSensor(SberBaseEntity, SensorEntity):
    """Универсальный сенсор, конфигурируемый через SensorSpec."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: SensorSpec,
    ) -> None:
        super().__init__(coordinator, device_id, spec.suffix)
        self._spec = spec
        self._attr_device_class = spec.device_class
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_state_class = spec.state_class
        if spec.entity_category is not None:
            self._attr_entity_category = spec.entity_category
        if spec.precision is not None:
            self._attr_suggested_display_precision = spec.precision
        if not spec.enabled_by_default:
            self._attr_entity_registry_enabled_default = False
        if spec.icon is not None:
            self._attr_icon = spec.icon

    @property
    def native_value(self) -> float | int | None:
        state = self._get_reported_state(self._spec.key)
        if not state:
            return None
        raw: float | None = None
        if "float_value" in state:
            raw = float(state["float_value"])
        elif "integer_value" in state:
            raw = float(state["integer_value"])
        if raw is None:
            return None
        value = raw * self._spec.scale
        if self._spec.as_int:
            return int(value)
        return value


# ---- Backwards-compat specialised classes (preserve public API for tests) ----


def _spec(category: str, key: str) -> SensorSpec:
    for s in CATEGORY_SENSORS.get(category, []) + COMMON_SENSORS:
        if s.key == key:
            return s
    raise KeyError(f"No spec for {category}/{key}")


class SberTemperatureSensor(SberGenericSensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _spec("sensor_temp", "temperature"))


class SberHumiditySensor(SberGenericSensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _spec("sensor_temp", "humidity"))


class SberBatterySensor(SberGenericSensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _spec("sensor_temp", "battery_percentage"))


class SberSignalStrengthSensor(SberGenericSensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _spec("sensor_temp", "signal_strength"))


class SberVoltageSensor(SberGenericSensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _spec("socket", "cur_voltage"))


class SberCurrentSensor(SberGenericSensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _spec("socket", "cur_current"))


class SberPowerSensor(SberGenericSensor):
    def __init__(self, coordinator: SberHomeCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, _spec("socket", "cur_power"))
