"""C2cCodec — serialized-format публичного C2C MQTT API.

Конвенции (см. https://developers.sber.ru/docs/ru/smarthome/c2c):
- INTEGER → **string** `"220"` (не int!).
- COLOUR (с u): type=`"COLOUR"`, поле `colour_value`, components
  `{h 0..360, s 0..1000, v 100..1000}` (десятые доли процента).
- BOOL/ENUM/FLOAT/STRING — стандартно.
- State entry: `{"key": ..., "value": {...}}` — value **вложенный** объект
  (в отличие от gateway flat).
- Bundle: `{"states": [<state>]}` для одного device.

Используется `MQTT-SberGate` интеграцией для публикации HA-устройств в Sber.
"""

from __future__ import annotations

from typing import Any, Final

from ..exceptions import CodecError
from ..values import HsvColor, SberState, SberStateBundle, SberValue, ValueType

_WIRE_TYPE_TO_VT: Final[dict[str, ValueType]] = {
    "BOOL": ValueType.BOOL,
    "INTEGER": ValueType.INTEGER,
    "FLOAT": ValueType.FLOAT,
    "STRING": ValueType.STRING,
    "ENUM": ValueType.ENUM,
    "COLOUR": ValueType.COLOR,  # British → canonical American
    "SCHEDULE": ValueType.SCHEDULE,
}

_VT_TO_WIRE_TYPE: Final[dict[ValueType, str]] = {
    ValueType.BOOL: "BOOL",
    ValueType.INTEGER: "INTEGER",
    ValueType.FLOAT: "FLOAT",
    ValueType.STRING: "STRING",
    ValueType.ENUM: "ENUM",
    ValueType.COLOR: "COLOUR",  # American → British на API
    ValueType.SCHEDULE: "SCHEDULE",
}


class C2cCodec:
    """Codec для публичного C2C MQTT protocol."""

    name: Final = "c2c"

    # ---- Value ----
    def encode_value(self, value: SberValue) -> dict[str, Any]:
        wire_type = _VT_TO_WIRE_TYPE[value.type]
        out: dict[str, Any] = {"type": wire_type}
        if value.type is ValueType.BOOL:
            out["bool_value"] = bool(value.bool_value)
        elif value.type is ValueType.INTEGER:
            # CRITICAL: C2C требует INTEGER as STRING.
            out["integer_value"] = str(value.integer_value or 0)
        elif value.type is ValueType.FLOAT:
            out["float_value"] = float(value.float_value or 0.0)
        elif value.type is ValueType.STRING:
            out["string_value"] = str(value.string_value or "")
        elif value.type is ValueType.ENUM:
            out["enum_value"] = str(value.enum_value or "")
        elif value.type is ValueType.COLOR:
            if value.color_value is None:
                raise CodecError(self.name, "encode", "COLOR value missing color_value")
            out["colour_value"] = self.encode_color(value.color_value)
        elif value.type is ValueType.SCHEDULE:
            sv = value.schedule_value
            out["schedule_value"] = (
                {
                    "days": [d.value for d in sv.days],
                    "events": [
                        {
                            "time": e.time,
                            "value_type": e.value_type,
                            "target_value": e.target_value,
                        }
                        for e in sv.events
                    ],
                }
                if sv is not None
                else None
            )
        return out

    def decode_value(self, raw: dict[str, Any]) -> SberValue:
        wire_type = raw.get("type")
        if wire_type is None:
            raise CodecError(self.name, "decode", "missing 'type'", payload=raw)
        vt = _WIRE_TYPE_TO_VT.get(wire_type)
        if vt is None:
            raise CodecError(self.name, "decode", f"unknown API type: {wire_type!r}", payload=raw)

        if vt is ValueType.BOOL:
            return SberValue.of_bool(bool(raw.get("bool_value")))
        if vt is ValueType.INTEGER:
            v = raw.get("integer_value")
            # На входе — string, парсим в int.
            return SberValue.of_int(int(v) if v is not None else 0)
        if vt is ValueType.FLOAT:
            return SberValue.of_float(float(raw.get("float_value") or 0.0))
        if vt is ValueType.STRING:
            return SberValue.of_string(str(raw.get("string_value") or ""))
        if vt is ValueType.ENUM:
            return SberValue.of_enum(str(raw.get("enum_value") or ""))
        if vt is ValueType.COLOR:
            cv = raw.get("colour_value")
            if not isinstance(cv, dict):
                raise CodecError(
                    self.name,
                    "decode",
                    "COLOUR missing colour_value dict",
                    payload=raw,
                )
            return SberValue.of_color(self.decode_color(cv))
        if vt is ValueType.SCHEDULE:
            from ..values import ScheduleEvent, ScheduleValue, Weekday

            sv_raw = raw.get("schedule_value") or {}
            days = tuple(Weekday(d) for d in sv_raw.get("days", []))
            events = tuple(
                ScheduleEvent(
                    time=e.get("time", ""),
                    value_type=e.get("value_type", "FLOAT"),
                    target_value=float(e.get("target_value", 0)),
                )
                for e in sv_raw.get("events", [])
            )
            return SberValue.of_schedule(ScheduleValue(days=days, events=events))
        raise CodecError(self.name, "decode", f"unhandled type {vt}", payload=raw)

    # ---- Color (масштабирование 0..100 ↔ 0..1000) ----
    def encode_color(self, color: HsvColor) -> dict[str, Any]:
        # Saturation/brightness в C2C — десятые доли процента (×10).
        # Brightness min = 100 per Sber spec VR-004 (если 0 — устройство rejected).
        return {
            "h": color.hue,
            "s": color.saturation * 10,
            "v": max(100, color.brightness * 10),  # min 100 per VR-004
        }

    def decode_color(self, raw: dict[str, Any]) -> HsvColor:
        return HsvColor(
            hue=int(raw.get("h", 0)),
            saturation=int(raw.get("s", 0)) // 10,
            brightness=int(raw.get("v", 100)) // 10,
        )

    # ---- State ----
    def encode_state(self, state: SberState) -> dict[str, Any]:
        # C2C: value вложенный, не flat (в отличие от gateway).
        return {"key": state.key, "value": self.encode_value(state.value)}

    def decode_state(self, raw: dict[str, Any]) -> SberState:
        key = raw.get("key")
        if not key:
            raise CodecError(self.name, "decode", "state missing 'key'", payload=raw)
        value_raw = raw.get("value")
        if not isinstance(value_raw, dict):
            raise CodecError(self.name, "decode", "state missing 'value' dict", payload=raw)
        return SberState(key=str(key), value=self.decode_value(value_raw))

    # ---- Bundle ----
    def encode_bundle(
        self, bundle: SberStateBundle, *, direction: str = "desired"
    ) -> dict[str, Any]:
        """Encode bundle для C2C MQTT publish.

        C2C использует `states: [...]` — direction (desired/reported)
        задаётся MQTT topic'ом, не payload'ом.
        """
        return {"states": [self.encode_state(s) for s in bundle.states]}

    def decode_bundle(self, raw: dict[str, Any]) -> SberStateBundle:
        states_list = raw.get("states") or []
        states = tuple(self.decode_state(s) for s in states_list)
        return SberStateBundle(device_id=raw.get("device_id"), states=states)
