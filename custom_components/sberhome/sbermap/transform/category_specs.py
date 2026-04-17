"""CategorySpec — спецификация primary entity для каждой Sber-категории.

Primary entity — composite: несколько features образуют одну HA entity
(e.g. LIGHT = on_off + brightness + colour + colour_temp + mode).

Consumed features не создают отдельных entities — они «съедены» primary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.cover import CoverDeviceClass, CoverState
from homeassistant.components.vacuum import VacuumActivity
from homeassistant.const import STATE_OFF, STATE_ON, Platform

from ._types import HaEntityData
from .feature_codecs import to_ha

# =============================================================================
# CategorySpec dataclass
# =============================================================================


@dataclass(slots=True, frozen=True)
class CategorySpec:
    """Спецификация primary entity для категории."""

    primary_platform: Platform
    consumed_features: frozenset[str] = field(default_factory=frozenset)
    # Primary entity device_class (для cover, binary_sensor)
    device_class: Any | None = None
    # Extra attributes keys to extract from reported_state
    attribute_keys: tuple[str, ...] = ()
    # For FAN/HUMIDIFIER — preset mode options
    options: tuple[str, ...] | None = None
    # For HUMIDIFIER — humidity range
    min_value: float | None = None
    max_value: float | None = None


def _on_off(value: Any) -> str:
    return STATE_ON if value else STATE_OFF


# =============================================================================
# Primary entity builders (category-specific logic)
# =============================================================================

# Vacuum status → HA VacuumActivity
_VACUUM_STATUS_MAP: dict[str, VacuumActivity] = {
    "cleaning": VacuumActivity.CLEANING,
    "running": VacuumActivity.CLEANING,
    "paused": VacuumActivity.PAUSED,
    "returning": VacuumActivity.RETURNING,
    "docked": VacuumActivity.DOCKED,
    "charging": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
    "error": VacuumActivity.ERROR,
}

# Sber open_state → HA CoverState
_OPEN_STATE_MAP: dict[str, str] = {
    "open": CoverState.OPEN,
    "opened": CoverState.OPEN,
    "close": CoverState.CLOSED,
    "closed": CoverState.CLOSED,
    "opening": CoverState.OPENING,
    "closing": CoverState.CLOSING,
}


def build_primary_entity(
    reported: dict[str, Any],
    spec: CategorySpec,
    device_id: str,
    name: str,
    category: str,
) -> HaEntityData | None:
    """Build primary HaEntityData from reported_state values + CategorySpec.

    ``reported`` = {key: raw_value} dict extracted from DeviceDto.reported_state.
    """
    platform = spec.primary_platform

    if platform is Platform.SWITCH:
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=_on_off(reported.get("on_off")),
            sber_category=category,
        )

    if platform is Platform.LIGHT:
        # Primary LIGHT entity — state only. Platform (light.py) handles
        # brightness/color via LightConfig + light_state_from_dto.
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=_on_off(reported.get("on_off")),
            sber_category=category,
        )

    if platform is Platform.CLIMATE:
        from homeassistant.components.climate import HVACMode

        is_on = bool(reported.get("on_off"))
        raw_mode = reported.get("hvac_work_mode")
        if not is_on:
            ha_state = HVACMode.OFF
        elif raw_mode:
            _sber_to_hvac: dict[str, Any] = {
                "cool": HVACMode.COOL,
                "heat": HVACMode.HEAT,
                "dry": HVACMode.DRY,
                "fan": HVACMode.FAN_ONLY,
                "fan_only": HVACMode.FAN_ONLY,
                "auto": HVACMode.AUTO,
            }
            ha_state = _sber_to_hvac.get(str(raw_mode), HVACMode.AUTO)
        else:
            ha_state = HVACMode.AUTO
        attrs: dict[str, Any] = {}
        target = reported.get("hvac_temp_set")
        if target is not None:
            attrs["temperature"] = int(target)
        current = reported.get("temperature")
        if current is not None:
            attrs["current_temperature"] = to_ha("temperature", current)
        fan = reported.get("hvac_air_flow_power")
        if fan is not None:
            attrs["fan_mode"] = fan
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=ha_state,
            attributes=attrs,
            sber_category=category,
        )

    if platform is Platform.COVER:
        pos = reported.get("open_percentage")
        raw_state = str(reported.get("open_state") or "closed")
        ha_state = _OPEN_STATE_MAP.get(raw_state, CoverState.CLOSED)
        attrs = {}
        if pos is not None:
            attrs["current_position"] = int(pos)
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=ha_state,
            attributes=attrs,
            sber_category=category,
            device_class=spec.device_class,
        )

    if platform is Platform.FAN:
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=_on_off(reported.get("on_off")),
            attributes={"preset_mode": reported.get("hvac_air_flow_power")},
            options=spec.options,
            sber_category=category,
        )

    if platform is Platform.HUMIDIFIER:
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=_on_off(reported.get("on_off")),
            attributes={
                "humidity": reported.get("hvac_humidity_set"),
                "current_humidity": reported.get("humidity"),
                "mode": reported.get("hvac_air_flow_power"),
            },
            options=spec.options,
            min_value=spec.min_value,
            max_value=spec.max_value,
            sber_category=category,
        )

    if platform is Platform.MEDIA_PLAYER:
        volume_raw = reported.get("volume_int")
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=STATE_ON if reported.get("on_off") else STATE_OFF,
            attributes={
                "source": reported.get("source"),
                "volume_level": float(volume_raw) / 100.0 if volume_raw is not None else None,
                "is_volume_muted": reported.get("mute"),
            },
            sber_category=category,
        )

    if platform is Platform.VACUUM:
        raw_status = reported.get("vacuum_cleaner_status")
        activity = (
            _VACUUM_STATUS_MAP.get(str(raw_status), VacuumActivity.IDLE) if raw_status else None
        )
        battery = reported.get("battery_percentage")
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=activity,
            attributes={"battery_level": int(battery) if battery is not None else None},
            sber_category=category,
        )

    if platform is Platform.BINARY_SENSOR:
        # Hub — primary is connectivity sensor
        state_key = next(iter(spec.consumed_features - {"on_off"}), "online")
        return HaEntityData(
            platform=platform,
            unique_id=device_id,
            name=name,
            state=_on_off(reported.get(state_key)),
            device_class=spec.device_class,
            state_attribute_key=state_key,
            sber_category=category,
        )

    return None


# =============================================================================
# CATEGORY_SPECS — declarative category → primary entity
# =============================================================================

_LIGHT_CONSUMED = frozenset(
    {
        "on_off",
        "light_brightness",
        "light_colour",
        "light_colour_temp",
        "light_mode",
    }
)
_CLIMATE_CONSUMED = frozenset(
    {
        "on_off",
        "hvac_temp_set",
        "hvac_work_mode",
        "hvac_air_flow_power",
    }
)
_COVER_CONSUMED = frozenset(
    {
        "open_set",
        "open_state",
        "open_percentage",
        "open_left_percentage",
        "open_right_percentage",
        "open_left_set",
        "open_right_set",
        "open_left_state",
        "open_right_state",
    }
)
_TV_CONSUMED = frozenset(
    {
        "on_off",
        "volume_int",
        "mute",
        "source",
        "channel_int",
        "direction",
        "custom_key",
        "number",
    }
)
_VACUUM_CONSUMED = frozenset(
    {
        "on_off",
        "vacuum_cleaner_status",
        "vacuum_cleaner_command",
        "battery_percentage",
    }
)
_FAN_CONSUMED = frozenset({"on_off", "hvac_air_flow_power"})
_HUMIDIFIER_CONSUMED = frozenset(
    {
        "on_off",
        "hvac_humidity_set",
        "humidity",
        "hvac_air_flow_power",
    }
)

CATEGORY_SPECS: dict[str, CategorySpec] = {
    # Lights
    "light": CategorySpec(Platform.LIGHT, _LIGHT_CONSUMED),
    "led_strip": CategorySpec(Platform.LIGHT, _LIGHT_CONSUMED),
    # Switches
    "socket": CategorySpec(Platform.SWITCH, frozenset({"on_off"})),
    "relay": CategorySpec(Platform.SWITCH, frozenset({"on_off"})),
    "kettle": CategorySpec(Platform.SWITCH, frozenset({"on_off"})),
    # Climate
    "hvac_ac": CategorySpec(Platform.CLIMATE, _CLIMATE_CONSUMED),
    "hvac_heater": CategorySpec(Platform.CLIMATE, _CLIMATE_CONSUMED),
    "hvac_radiator": CategorySpec(Platform.CLIMATE, _CLIMATE_CONSUMED),
    "hvac_boiler": CategorySpec(Platform.CLIMATE, _CLIMATE_CONSUMED),
    "hvac_underfloor_heating": CategorySpec(Platform.CLIMATE, _CLIMATE_CONSUMED),
    # Covers
    "curtain": CategorySpec(Platform.COVER, _COVER_CONSUMED, device_class=CoverDeviceClass.CURTAIN),
    "window_blind": CategorySpec(
        Platform.COVER, _COVER_CONSUMED, device_class=CoverDeviceClass.BLIND
    ),
    "gate": CategorySpec(Platform.COVER, _COVER_CONSUMED, device_class=CoverDeviceClass.GATE),
    "valve": CategorySpec(Platform.COVER, _COVER_CONSUMED),
    # Fan / Air purifier
    "hvac_fan": CategorySpec(
        Platform.FAN, _FAN_CONSUMED, options=("low", "medium", "high", "turbo")
    ),
    "hvac_air_purifier": CategorySpec(
        Platform.FAN, _FAN_CONSUMED, options=("auto", "low", "medium", "high", "turbo")
    ),
    # Humidifier
    "hvac_humidifier": CategorySpec(
        Platform.HUMIDIFIER,
        _HUMIDIFIER_CONSUMED,
        options=("auto", "low", "medium", "high", "turbo"),
        min_value=30,
        max_value=80,
    ),
    # Media
    "tv": CategorySpec(Platform.MEDIA_PLAYER, _TV_CONSUMED),
    # Vacuum
    "vacuum_cleaner": CategorySpec(Platform.VACUUM, _VACUUM_CONSUMED),
    # Binary sensor categories (primary = the detection sensor)
    "sensor_water_leak": CategorySpec(
        Platform.BINARY_SENSOR,
        frozenset({"water_leak_state"}),
        device_class=BinarySensorDeviceClass.MOISTURE,
    ),
    "sensor_door": CategorySpec(
        Platform.BINARY_SENSOR,
        frozenset({"doorcontact_state"}),
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    "sensor_pir": CategorySpec(
        Platform.BINARY_SENSOR,
        frozenset({"motion_state", "pir"}),
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    "sensor_smoke": CategorySpec(
        Platform.BINARY_SENSOR,
        frozenset({"smoke_state"}),
        device_class=BinarySensorDeviceClass.SMOKE,
    ),
    "sensor_gas": CategorySpec(
        Platform.BINARY_SENSOR,
        frozenset({"gas_leak_state"}),
        device_class=BinarySensorDeviceClass.GAS,
    ),
    # Hub — connectivity binary sensor
    "hub": CategorySpec(
        Platform.BINARY_SENSOR,
        frozenset({"online"}),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    # Sensor (temp/humidity) — no single primary, all sensors are extras
    "sensor_temp": CategorySpec(Platform.SENSOR, frozenset()),
    # Intercom — no single primary, all entities are extras
    "intercom": CategorySpec(Platform.BINARY_SENSOR, frozenset(), device_class=None),
    # Scenario button — only events, no primary
    "scenario_button": CategorySpec(Platform.EVENT, frozenset()),
}


# Re-exports for mapper
__all__ = [
    "CATEGORY_SPECS",
    "CategorySpec",
    "build_primary_entity",
]
