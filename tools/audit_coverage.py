#!/usr/bin/env python3
"""Audit покрытия features в typed device wrappers.

Сравнивает атрибуты, которые мы выставили в `aiosber/dto/devices/*.py`,
с features из `docs/sber_full_spec.json` И с sealed-hierarchy из реверса
APK (research_docs/04-dataclasses.md §6.1).

Цель — найти gaps: какие фичи устройств у нас не оборачиваются typed-property.

Использование:

    python tools/audit_coverage.py

Выводит markdown-отчёт в stdout (можно перенаправить в файл).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "sber_full_spec.json"

sys.path.insert(0, str(REPO_ROOT))
from custom_components.sberhome.aiosber.dto.devices import (  # noqa: E402
    _CATEGORY_TO_CLASS,
    TypedDevice,
)

# ============================================================================
# Маппинг: feature key (snake_case как в spec) → имя property в TypedDevice.
# Если property называется иначе чем feature — указать здесь явно.
# ============================================================================
FEATURE_TO_PROPERTY: dict[str, str] = {
    # Базовые (из TypedDevice)
    "online": "online",
    "battery_percentage": "battery_percentage",
    "battery_low_power": "battery_low",
    "signal_strength": "signal_strength",
    # spec typo
    "battery_percentag": "battery_percentage",  # обрабатывается fallback'ом

    # Light
    "on_off": "is_on",
    "light_brightness": "brightness",
    "light_colour": "color",
    "light_colour_temp": "color_temp",
    "light_mode": "mode",
    "sleep_timer": "sleep_timer",

    # Electric
    "voltage": "voltage",
    "cur_voltage": "voltage",
    "current": "current_milliamps",
    "cur_current": "current_milliamps",
    "power": "power_watts",
    "cur_power": "power_watts",
    "child_lock": "child_lock",

    # Sensors
    "temperature": ("temperature", "current_temperature"),
    "humidity": "humidity",
    "air_pressure": "air_pressure",
    "temp_unit_view": "temp_unit",
    "sensor_sensitive": "sensitivity",
    "doorcontact_state": "is_open",
    "pir": "motion",
    "motion_state": "motion",
    "water_leak_state": "water_leak",
    "smoke_state": "smoke",
    "gas_leak_state": "gas_leak",
    "tamper_alarm": "tamper_alarm",
    "alarm_mute": ("alarm_muted", "is_muted"),

    # Covers
    "open_percentage": "position",
    "open_set": None,  # это команда, не state — не должна быть property
    "open_state": "state",
    "open_rate": "open_rate",
    "open_left_percentage": "left_position",
    "open_left_set": None,
    "open_left_state": None,
    "open_right_percentage": "right_position",
    "open_right_set": None,
    "open_right_state": None,
    "fault_alarm": "fault_alarm",  # ⚠ valve — есть в реверсе, у нас НЕТ

    # HVAC
    "hvac_temp_set": "target_temperature",
    "hvac_humidity_set": "target_humidity",
    "hvac_work_mode": "work_mode",
    "hvac_air_flow_power": ("fan_speed", "speed"),
    "hvac_air_flow_direction": "air_flow_direction",
    "hvac_night_mode": "night_mode",
    "hvac_ionization": "ionization",
    "hvac_aromatization": "aromatization",
    "hvac_decontaminate": "decontaminate",  # ⚠ AirPurifier — нет
    "hvac_thermostat_mode": "thermostat_mode",
    "hvac_heating_rate": "heating_rate",
    "hvac_replace_filter": "replace_filter_alarm",
    "hvac_replace_ionizator": "replace_ionizer_alarm",
    "hvac_water_level": "water_level",
    "hvac_water_percentage": "water_percentage",  # ⚠ Humidifier — нет
    "hvac_water_low_level": "water_low_alarm",

    # Kitchen
    "kitchen_water_temperature": "water_temperature",
    "kitchen_water_temperature_set": "target_water_temperature",
    "kitchen_water_level": "water_level",
    "kitchen_water_low_level": "water_low_alarm",

    # Vacuum
    "vacuum_cleaner_command": None,  # команда
    "vacuum_cleaner_status": "status",
    "vacuum_cleaner_program": "program",
    "vacuum_cleaner_cleaning_type": "cleaning_type",

    # TV
    "source": "source",
    "volume": None,  # legacy ENUM, у нас volume_int
    "volume_int": "volume",
    "mute": "muted",
    "channel": None,
    "channel_int": "channel",
    "number": None,
    "custom_key": None,  # команда (через service)
    "direction": None,  # команда (через service)

    # Scenario button
    "button_1_event": "button_event",  # method, не property
    "button_2_event": "button_event",
    "button_3_event": "button_event",
    "button_4_event": "button_event",
    "button_5_event": "button_event",
    "button_6_event": "button_event",
    "button_7_event": "button_event",
    "button_8_event": "button_event",
    "button_9_event": "button_event",
    "button_10_event": "button_event",

    # Intercom
    "incoming_call": "has_incoming_call",
    "reject_call": None,  # команда
    "unlock": None,  # команда
}


def has_property(cls: type, name: str | tuple[str, ...] | None) -> bool:
    """True если cls имеет указанное property (или метод).

    Если name — tuple, проверяется наличие хотя бы одного из вариантов.
    """
    if name is None:
        return True  # помечен как "не должно быть"
    candidates = (name,) if isinstance(name, str) else name
    return any(hasattr(cls, c) for c in candidates)


def audit_category(cat: str, cls: type[TypedDevice], cat_spec: dict) -> dict[str, Any]:
    """Audit одной категории. Возвращает dict со статистикой."""
    features = set(cat_spec.get("features", []))
    obligatory = set(cat_spec.get("obligatory", []))
    all_features = set(cat_spec.get("all_features", []))

    covered: list[str] = []
    missing: list[str] = []
    not_required: list[str] = []  # commands / set-only fields

    for f in sorted(features):
        prop = FEATURE_TO_PROPERTY.get(f, f)  # fallback — same name
        if prop is None:
            not_required.append(f)
            continue
        if has_property(cls, prop):
            covered.append(f)
        else:
            missing.append(f)

    # Specific extras в реверсе (НЕ в spec features, но есть в SmartDevice
    # subclass'ах APK — см. research_docs/04-dataclasses.md §6.1).
    extras_from_apk = REVERSE_EXTRAS.get(cat, [])
    apk_missing = [
        f for f in extras_from_apk
        if not has_property(cls, FEATURE_TO_PROPERTY.get(f, f))
    ]

    return {
        "category": cat,
        "class_name": cls.__name__,
        "spec_features": len(features),
        "covered": covered,
        "missing": missing,
        "not_required": not_required,
        "apk_extras_missing": apk_missing,
        "obligatory_covered": all(
            has_property(cls, FEATURE_TO_PROPERTY.get(f, f)) or FEATURE_TO_PROPERTY.get(f) is None
            for f in obligatory
        ),
        "all_features_total": len(all_features),
    }


# ============================================================================
# Дополнительные поля из реверса APK (research_docs/04-dataclasses.md §6.1).
# Эти поля живут в SmartDevice sealed subclass'ах (HvacRadiatorState, Thermostat,
# CurtainState, ScenarioButtonState, Intercom, ...) — но НЕ упомянуты в
# `sber_full_spec.json:features`.
# ============================================================================
REVERSE_EXTRAS: dict[str, list[str]] = {
    # CurtainState: openSet, reverseMode, openingTime, calibration, showSetup
    "curtain": ["reverse_mode", "opening_time", "calibration", "show_setup"],
    "window_blind": ["reverse_mode", "opening_time", "calibration"],
    "gate": ["reverse_mode", "opening_time", "calibration"],

    # Valve: fault_alarm
    "valve": ["fault_alarm"],

    # Thermostat (HvacRadiator/Boiler/Underfloor) — много config fields
    "hvac_radiator": [
        "min_temperature", "max_temperature", "show_setup", "adjust_floor_temp",
        "floor_type", "floor_sensor_type", "main_sensor", "device_condition",
        "open_window", "open_window_status", "anti_frost_temp",
        "heating_hysteresis", "temperature_correction",
    ],
    "hvac_boiler": [
        "device_condition", "schedule_status", "schedule",
        "heating_hysteresis", "anti_frost_temp",
    ],
    "hvac_underfloor_heating": [
        "device_condition", "floor_type", "floor_sensor_type",
        "main_sensor", "heating_hysteresis", "anti_frost_temp",
    ],

    # Socket: upper_current_threshold (config)
    "socket": ["upper_current_threshold"],

    # ScenarioButton: led_indicator + color_indicator + click_mode
    "scenario_button": [
        "click_mode", "is_double_click_enabled",
        "led_indicator_on", "led_indicator_off",
        "color_indicator_on", "color_indicator_off",
    ],

    # Intercom: virtualOpenState, unlockDuration
    "intercom": ["virtual_open_state", "unlock_duration"],

    # Camera (нет в spec, но есть в реверсе как CameraState)
    # Не категория spec, поэтому здесь не появится.
}


def render_report(audits: list[dict[str, Any]]) -> str:
    out: list[str] = []
    out.append("# Audit покрытия typed device wrappers")
    out.append("")
    out.append("AUTO-GENERATED `tools/audit_coverage.py`. Не редактировать вручную.")
    out.append("")
    out.append("## Сводка")
    out.append("")
    out.append("| Категория | Class | Spec features | Covered | Missing (spec) | Missing (APK reverse) |")
    out.append("|---|---|---|---|---|---|")

    total_spec = total_covered = total_missing_spec = total_missing_apk = 0
    for a in audits:
        spec = a["spec_features"]
        cov = len(a["covered"])
        miss = len(a["missing"])
        apk_miss = len(a["apk_extras_missing"])
        total_spec += spec
        total_covered += cov
        total_missing_spec += miss
        total_missing_apk += apk_miss
        out.append(
            f"| `{a['category']}` | `{a['class_name']}` | {spec} | {cov} | "
            f"{miss} {'❌' if miss else '✅'} | {apk_miss} {'⚠️' if apk_miss else '✅'} |"
        )
    out.append(
        f"| **TOTAL** |  | **{total_spec}** | **{total_covered}** | "
        f"**{total_missing_spec}** | **{total_missing_apk}** |"
    )
    out.append("")
    pct = 100.0 * total_covered / total_spec if total_spec else 0
    out.append(f"**Spec coverage: {pct:.1f}%** ({total_covered}/{total_spec})")
    out.append("")

    out.append("## Детально по категориям")
    out.append("")

    for a in audits:
        if not a["missing"] and not a["apk_extras_missing"]:
            continue  # 100% покрытие — пропускаем
        out.append(f"### `{a['category']}` → `{a['class_name']}`")
        out.append("")
        if a["missing"]:
            out.append("**❌ Не покрыто (spec features):**")
            for f in a["missing"]:
                out.append(f"- `{f}`")
            out.append("")
        if a["apk_extras_missing"]:
            out.append("**⚠️ Не покрыто (extra fields из реверса APK SmartDevice):**")
            for f in a["apk_extras_missing"]:
                out.append(f"- `{f}`")
            out.append("")

    out.append("## 100% покрыты")
    out.append("")
    full = [a for a in audits if not a["missing"] and not a["apk_extras_missing"]]
    out.append(", ".join(f"`{a['category']}`" for a in full) or "_(none)_")
    out.append("")

    return "\n".join(out)


def main() -> int:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    cats = spec["categories"]

    audits = []
    for cat in sorted(cats):
        if cat not in _CATEGORY_TO_CLASS:
            print(f"WARN: no typed class for {cat!r}", file=sys.stderr)
            continue
        cls = _CATEGORY_TO_CLASS[cat]
        audits.append(audit_category(cat, cls, cats[cat]))

    print(render_report(audits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
