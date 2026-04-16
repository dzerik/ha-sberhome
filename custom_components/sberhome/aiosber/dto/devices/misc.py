"""Прочее — `scenario_button`, `intercom`, `hub`."""

from __future__ import annotations

from ._base import TypedDevice


class ScenarioButtonDevice(TypedDevice):
    """Сценарный выключатель.

    Поддерживает до 10 кнопок (`button_1_event` .. `button_10_event`) +
    направленные нажатия (`button_left_event`, `button_top_left_event`, ...).

    События — discrete (click/double_click), не state. Для real-time трекинга
    использовать WebSocket DEVMAN_EVENT.
    """

    CATEGORIES = ("scenario_button",)

    def button_event(self, n: int) -> str | None:
        """Последнее событие кнопки N (1-10): `click` / `double_click` / None."""
        if not 1 <= n <= 10:
            raise ValueError(f"button index out of range: {n}")
        return self._reported_str(f"button_{n}_event")

    def directional_event(self, direction: str) -> str | None:
        """Направленное событие.

        direction: left/right/top_left/top_right/bottom_left/bottom_right.
        """
        valid = ("left", "right", "top_left", "top_right", "bottom_left", "bottom_right")
        if direction not in valid:
            raise ValueError(f"invalid direction: {direction!r}")
        return self._reported_str(f"button_{direction}_event")

    @property
    def battery_percentage(self) -> int | None:  # type: ignore[override]
        # spec обозначает поле как `battery_percentag` (typo in Sber spec) +
        # стандартное `battery_percentage`. Пробуем оба.
        v = self._reported_int("battery_percentage")
        if v is not None:
            return v
        return self._reported_int("battery_percentag")

    # ----- Config-fields (из wire-протокола ScenarioButtonState) -----
    @property
    def click_mode(self) -> str | None:
        """Режим распознавания нажатий (например `single`/`double`/`both`)."""
        return self._reported_str("click_mode")

    @property
    def is_double_click_enabled(self) -> bool | None:
        return self._reported_bool("is_double_click_enabled")

    @property
    def led_indicator_on(self) -> bool | None:
        """LED-индикатор горит при on-состоянии."""
        return self._reported_bool("led_indicator_on")

    @property
    def led_indicator_off(self) -> bool | None:
        return self._reported_bool("led_indicator_off")

    @property
    def color_indicator_on(self):
        """HSV-цвет LED-индикатора в on-состоянии."""
        attr = self._dto.reported("color_indicator_on")
        return attr.color_value if attr else None

    @property
    def color_indicator_off(self):
        attr = self._dto.reported("color_indicator_off")
        return attr.color_value if attr else None


class IntercomDevice(TypedDevice):
    """Домофон."""

    CATEGORIES = ("intercom",)

    @property
    def has_incoming_call(self) -> bool | None:
        return self._reported_bool("incoming_call")

    @property
    def is_muted(self) -> bool | None:
        return self._reported_bool("intercom_mute")

    @property
    def virtual_open_state(self) -> bool | None:
        """Виртуальное состояние «открыто» — отображается в UI после команды unlock."""
        return self._reported_bool("virtual_open_state")

    @property
    def unlock_duration(self) -> int | None:
        """Длительность открытия двери в секундах (config)."""
        return self._reported_int("unlock_duration")


class HubDevice(TypedDevice):
    """Zigbee/центральный хаб. Только `online` поле обычно."""

    CATEGORIES = ("hub",)
