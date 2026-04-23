"""GatewayCodec — serialized-format приватного API `gateway.iot.sberdevices.ru`.

Конвенции:
- INTEGER → int (`220`).
- COLOR: type=`"COLOR"`, поле `color_value` со short keys `{h, s, v}`.
  Range определяется устройством (DeviceFeatureDto.ColorValues), для
  большинства ламп: `h 0..359`, `s/v 0..1000`.
- ENUM/BOOL/FLOAT/STRING — стандартно.
- State entry: `{"key": ..., "type": ..., "X_value": ...}` flat.
- Bundle: `{"reported_state": [<state>, ...]}` или `{"desired_state": [...]}`
  (в зависимости от direction).

Формат восстановлен из JSON-обмена с публичным endpoint'ом
`gateway.iot.sberdevices.ru`.
"""

from __future__ import annotations

from typing import Any, Final

from ..exceptions import CodecError
from ..values import HsvColor, SberState, SberStateBundle, SberValue, ValueType


class GatewayCodec:
    """Codec для приватного gateway API."""

    name: Final = "gateway"

    # ---- Value ----
    def encode_value(self, value: SberValue) -> dict[str, Any]:
        out: dict[str, Any] = {"type": value.type.value}
        if value.type is ValueType.BOOL:
            out["bool_value"] = bool(value.bool_value)
        elif value.type is ValueType.INTEGER:
            out["integer_value"] = int(value.integer_value or 0)
        elif value.type is ValueType.FLOAT:
            out["float_value"] = float(value.float_value or 0.0)
        elif value.type is ValueType.STRING:
            out["string_value"] = str(value.string_value or "")
        elif value.type is ValueType.ENUM:
            out["enum_value"] = str(value.enum_value or "")
        elif value.type is ValueType.COLOR:
            if value.color_value is None:
                raise CodecError(self.name, "encode", "COLOR value missing color_value")
            out["color_value"] = self.encode_color(value.color_value)
        elif value.type is ValueType.SCHEDULE:
            # SCHEDULE не упрощаем — отдаём как dict если есть.
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
        try:
            vt = ValueType(wire_type)
        except ValueError as err:
            raise CodecError(
                self.name, "decode", f"unknown API type: {wire_type!r}", payload=raw
            ) from err

        if vt is ValueType.BOOL:
            return SberValue.of_bool(bool(raw.get("bool_value")))
        if vt is ValueType.INTEGER:
            v = raw.get("integer_value")
            return SberValue.of_int(int(v) if v is not None else 0)
        if vt is ValueType.FLOAT:
            v = raw.get("float_value")
            return SberValue.of_float(float(v) if v is not None else 0.0)
        if vt is ValueType.STRING:
            return SberValue.of_string(str(raw.get("string_value") or ""))
        if vt is ValueType.ENUM:
            return SberValue.of_enum(str(raw.get("enum_value") or ""))
        if vt is ValueType.COLOR:
            cv = raw.get("color_value")
            if not isinstance(cv, dict):
                raise CodecError(self.name, "decode", "COLOR missing color_value dict", payload=raw)
            return SberValue.of_color(self.decode_color(cv))
        if vt is ValueType.SCHEDULE:
            # Для simplicity возвращаем без полного декодирования
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

    # ---- Color ----
    def encode_color(self, color: HsvColor) -> dict[str, Any]:
        # format: {h, s, v} (short keys per Gson @SerializedName).
        return {"h": color.hue, "s": color.saturation, "v": color.brightness}

    def decode_color(self, raw: dict[str, Any]) -> HsvColor:
        # Принимаем оба формата: canonical short {h, s, v} + legacy long
        # {hue, saturation, brightness} на случай старых моков/данных.
        return HsvColor(
            hue=int(raw.get("h", raw.get("hue", 0))),
            saturation=int(raw.get("s", raw.get("saturation", 0))),
            brightness=int(raw.get("v", raw.get("brightness", 0))),
        )

    # ---- State ----
    def encode_state(self, state: SberState) -> dict[str, Any]:
        return {"key": state.key, **self.encode_value(state.value)}

    def decode_state(self, raw: dict[str, Any]) -> SberState:
        key = raw.get("key")
        if not key:
            raise CodecError(self.name, "decode", "state missing 'key'", payload=raw)
        return SberState(key=str(key), value=self.decode_value(raw))

    # ---- Bundle ----
    def encode_bundle(
        self, bundle: SberStateBundle, *, direction: str = "desired"
    ) -> dict[str, Any]:
        """Encode bundle for either `desired_state` (commands) or `reported_state` (read).

        Args:
            direction: `"desired"` или `"reported"`.
        """
        key = "desired_state" if direction == "desired" else "reported_state"
        out: dict[str, Any] = {key: [self.encode_state(s) for s in bundle.states]}
        if bundle.device_id is not None:
            out["device_id"] = bundle.device_id
        return out

    def decode_bundle(self, raw: dict[str, Any]) -> SberStateBundle:
        # Принимаем либо reported_state, либо desired_state.
        states_list = raw.get("reported_state") or raw.get("desired_state") or []
        states = tuple(self.decode_state(s) for s in states_list)
        return SberStateBundle(device_id=raw.get("device_id"), states=states)
