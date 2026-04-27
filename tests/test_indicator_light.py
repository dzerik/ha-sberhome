"""Tests для SberIndicatorLight (Sber-wide LED indicator setting)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto import IndicatorColor, IndicatorColors
from custom_components.sberhome.coordinator import INDICATOR_POLL_INTERVAL_SEC
from custom_components.sberhome.light import SberIndicatorLight


def _coord(*, current: list | None = None) -> MagicMock:
    coord = MagicMock()
    if current is None:
        coord.indicator_colors = None
    else:
        coord.indicator_colors = IndicatorColors(
            default_colors=[],
            current_colors=current,
        )
    coord.async_set_indicator_color = AsyncMock()
    return coord


class TestIndicatorLight:
    def test_unavailable_when_indicator_not_polled_yet(self):
        light = SberIndicatorLight(_coord(current=None))
        assert light.available is False

    def test_unavailable_when_no_current_colors(self):
        light = SberIndicatorLight(_coord(current=[]))
        assert light.available is False

    def test_available_with_current_color(self):
        light = SberIndicatorLight(
            _coord(current=[IndicatorColor(id="c1", hue=120, saturation=80, brightness=50)])
        )
        assert light.available is True

    def test_is_on_true_when_brightness_positive(self):
        light = SberIndicatorLight(
            _coord(current=[IndicatorColor(id="c1", hue=0, saturation=0, brightness=10)])
        )
        assert light.is_on is True

    def test_is_on_false_when_brightness_zero(self):
        light = SberIndicatorLight(
            _coord(current=[IndicatorColor(id="c1", hue=0, saturation=0, brightness=0)])
        )
        assert light.is_on is False

    def test_brightness_scaled_to_ha_range(self):
        light = SberIndicatorLight(
            _coord(current=[IndicatorColor(id="c1", hue=0, saturation=0, brightness=50)])
        )
        # 50/100 → 50/100*255 = 127.5 → ceil 128
        assert light.brightness == 128

    def test_hs_color_passed_through(self):
        light = SberIndicatorLight(
            _coord(current=[IndicatorColor(id="c1", hue=200, saturation=80, brightness=50)])
        )
        assert light.hs_color == (200.0, 80.0)

    @pytest.mark.asyncio
    async def test_turn_on_with_no_kwargs_keeps_color_lights_brightness_default(self):
        coord = _coord(current=[IndicatorColor(id="c1", hue=10, saturation=20, brightness=0)])
        light = SberIndicatorLight(coord)
        await light.async_turn_on()
        sent = coord.async_set_indicator_color.await_args[0][0]
        assert sent.id == "c1"
        assert sent.hue == 10
        assert sent.saturation == 20
        # brightness=0 → но default fallback на 100 (так делает .async_turn_on
        # когда brightness не передан и текущая=0).
        assert sent.brightness == 100

    @pytest.mark.asyncio
    async def test_turn_on_applies_brightness_and_hs(self):
        from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_HS_COLOR

        coord = _coord(current=[IndicatorColor(id="c1", hue=0, saturation=0, brightness=50)])
        light = SberIndicatorLight(coord)
        await light.async_turn_on(**{ATTR_BRIGHTNESS: 255, ATTR_HS_COLOR: (180, 50)})
        sent = coord.async_set_indicator_color.await_args[0][0]
        assert sent.hue == 180
        assert sent.saturation == 50
        assert sent.brightness == 100  # 255/255*100

    @pytest.mark.asyncio
    async def test_turn_off_zeros_brightness(self):
        coord = _coord(current=[IndicatorColor(id="c1", hue=10, saturation=20, brightness=80)])
        light = SberIndicatorLight(coord)
        await light.async_turn_off()
        sent = coord.async_set_indicator_color.await_args[0][0]
        assert sent.brightness == 0
        # Остальное сохранилось.
        assert sent.hue == 10
        assert sent.saturation == 20

    @pytest.mark.asyncio
    async def test_turn_on_silently_skips_when_no_color_to_modify(self):
        """Защита: если до первого poll'а попробовать turn_on, не должно
        кидать AttributeError."""
        coord = _coord(current=[])
        light = SberIndicatorLight(coord)
        await light.async_turn_on()
        coord.async_set_indicator_color.assert_not_awaited()


# ---------------------------------------------------------------------------
# Coordinator indicator polling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_poll_indicator_throttled():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._indicator_disabled = False
    coord._indicator_last_poll_at = time.time() - 60
    api = MagicMock()
    api.get = AsyncMock()
    coord._indicator_api = MagicMock(return_value=api)

    await SberHomeCoordinator._maybe_poll_indicator(coord)
    api.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_indicator_runs_after_interval():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._indicator_disabled = False
    coord._indicator_last_poll_at = time.time() - INDICATOR_POLL_INTERVAL_SEC - 1
    payload = IndicatorColors(current_colors=[IndicatorColor(id="c1", hue=120)])
    api = MagicMock()
    api.get = AsyncMock(return_value=payload)
    coord._indicator_api = MagicMock(return_value=api)
    coord.indicator_colors = None

    await SberHomeCoordinator._maybe_poll_indicator(coord)
    api.get.assert_awaited_once()
    assert coord.indicator_colors is payload


@pytest.mark.asyncio
async def test_async_set_indicator_color_optimistic_update():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord.data = {}
    coord.async_set_updated_data = MagicMock()
    coord.indicator_colors = IndicatorColors(
        default_colors=[],
        current_colors=[IndicatorColor(id="c1", hue=0, brightness=50)],
    )
    api = MagicMock()
    api.set = AsyncMock()
    coord._indicator_api = MagicMock(return_value=api)

    new = IndicatorColor(id="c1", hue=180, saturation=80, brightness=100)
    await SberHomeCoordinator.async_set_indicator_color(coord, new)

    api.set.assert_awaited_once_with(new)
    # Optimistic patch: same id заменён в current_colors.
    assert coord.indicator_colors.current_colors == [new]
    coord.async_set_updated_data.assert_called_once()
