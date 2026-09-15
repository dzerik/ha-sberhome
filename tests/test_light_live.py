"""Лампы в настоящем Home Assistant: доступность, цветовой режим, пропавшие данные."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.components.light import DATA_COMPONENT, ColorMode
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.sberhome.const import CONF_ENABLED_DEVICE_UIDS

from .fake_cloud import FakeSberCloud, device

BRIGHTNESS = {"key": "light_brightness", "int_values": {"range": {"min": 1, "max": 900}}}
COLOUR_TEMP = {"key": "light_colour_temp", "int_values": {"range": {"min": 0, "max": 100}}}
COLOUR = {
    "key": "light_colour",
    "color_values": {
        "h": {"min": 0, "max": 360},
        "s": {"min": 0, "max": 100},
        "v": {"min": 1, "max": 100},
    },
}
ON = {"key": "on_off", "type": "BOOL", "bool_value": True}


def _modes(*values: str) -> dict[str, Any]:
    return {"key": "light_mode", "enum_values": {"values": list(values)}}


def _mode(value: str) -> dict[str, Any]:
    return {"key": "light_mode", "type": "ENUM", "enum_value": value}


async def _lamp(hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, **kwargs: Any):
    # Лампы читают desired_state — облако отдаёт его вместе с reported_state.
    kwargs.setdefault("desired_state", kwargs.get("reported", []))
    fake_cloud.devices = [device("lamp", **kwargs)]
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp"]})
    return entry, hass.data[DATA_COMPONENT].get_entity("light.lamp")


@pytest.mark.parametrize(
    ("attributes", "reported", "expected"),
    [
        ([_modes("white"), BRIGHTNESS], [ON, _mode("white")], {ColorMode.BRIGHTNESS}),
        ([BRIGHTNESS], [ON], {ColorMode.BRIGHTNESS}),
        (
            [_modes("white", "colour"), BRIGHTNESS, COLOUR_TEMP, COLOUR],
            [ON, _mode("music")],
            {ColorMode.HS, ColorMode.COLOR_TEMP},
        ),
    ],
    ids=["white-without-temperature", "no-light-mode", "unknown-mode"],
)
async def test_color_mode_is_always_one_of_supported(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    attributes: list[dict[str, Any]],
    reported: list[dict[str, Any]],
    expected: set[ColorMode],
) -> None:
    await _lamp(hass, setup_sberhome, fake_cloud, attributes=attributes, reported=reported)

    state = hass.states.get("light.lamp")

    assert state.state == "on"
    assert state.attributes["color_mode"] in expected


async def test_lamp_without_colour_or_temperature_reports_neither(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    _, white = await _lamp(
        hass,
        setup_sberhome,
        fake_cloud,
        attributes=[_modes("white"), BRIGHTNESS],
        reported=[
            ON,
            _mode("white"),
            {"key": "light_colour", "type": "COLOR", "color_value": {"h": 1, "s": 2, "v": 3}},
        ],
    )

    assert white.hs_color is None
    assert white.color_temp_kelvin is None
    assert white.effect is None


async def test_lamp_availability_follows_online_flag_and_cloud(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    entry, lamp = await _lamp(
        hass,
        setup_sberhome,
        fake_cloud,
        reported=[ON, {"key": "online", "type": "STRING", "string_value": "maybe"}],
    )
    # Флаг online не булев — не повод прятать лампу.
    assert hass.states.get("light.lamp").state == "on"

    fake_cloud.devices[0]["reported_state"] = [
        {"key": "online", "type": "BOOL", "bool_value": False}
    ]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("light.lamp").state == STATE_UNAVAILABLE

    fake_cloud.devices[0]["reported_state"] = []
    fake_cloud.down = True
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("light.lamp").state == STATE_UNAVAILABLE

    fake_cloud.down = False
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("light.lamp").state == "on"


async def test_lamp_removed_from_account_has_no_stale_state(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    entry, lamp = await _lamp(hass, setup_sberhome, fake_cloud, reported=[ON])

    fake_cloud.devices = []
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert lamp.available is False
    assert lamp.is_on is None
    assert lamp.brightness is None


async def test_indicator_without_colors_reports_nothing_and_sends_nothing(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    """Облако не отдало цвета индикатора — сущность недоступна и в облако не пишет."""
    await _lamp(hass, setup_sberhome, fake_cloud, reported=[ON])
    indicator = hass.data[DATA_COMPONENT].get_entity("light.sber_indicator_led_indicator")

    assert hass.states.get("light.sber_indicator_led_indicator").state == STATE_UNAVAILABLE
    assert (indicator.is_on, indicator.brightness, indicator.hs_color) == (None, None, None)
    await indicator.async_turn_on()
    await indicator.async_turn_off()
    assert fake_cloud.sent("PUT", "/devices/indicator/values") == []
