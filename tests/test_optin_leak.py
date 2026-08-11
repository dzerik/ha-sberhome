"""Opt-in выбор устройств должен соблюдаться ВСЕМИ платформами (issue #45).

Пользователь выбирает в панели, какие устройства пробросить в Home Assistant.
Платформы, которые ходят в `coordinator.devices` вместо `enabled_devices`,
создают сущности для невыбранных устройств — и те протаскиваются в HA через
device registry, минуя выбор. Именно так у автора issue включение
диагностического «Firmware» на одной колонке протащило весь аккаунт.

Тест проверяет не отдельные платформы, а инвариант: ни одна платформа не
перечисляет устройства в обход фильтра.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.const import CONF_ENABLED_DEVICE_IDS

COMPONENT = pathlib.Path("custom_components/sberhome")

# Платформы создают сущности; всё остальное (диагностика, панель, WS-API)
# имеет право видеть весь кэш — панели надо показывать и невыбранное.
PLATFORM_FILES = [
    "binary_sensor.py", "button.py", "climate.py", "cover.py", "event.py",
    "fan.py", "humidifier.py", "light.py", "media_player.py", "number.py",
    "select.py", "sensor.py", "switch.py", "update.py", "vacuum.py",
]


def _iterates_all_devices(path: pathlib.Path) -> bool:
    """True, если модуль перечисляет `coordinator.devices` целиком.

    Точечный `coordinator.devices.get(device_id)` не считается: там device_id
    уже пришёл из отфильтрованного `coordinator.entities`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            src = ast.unparse(node.iter)
            if "coordinator.devices" in src and ".get(" not in src:
                return True
    return False


@pytest.mark.parametrize("filename", PLATFORM_FILES)
def test_platform_respects_the_device_picker(filename: str) -> None:
    path = COMPONENT / filename
    if not path.exists():
        pytest.skip(f"{filename} отсутствует")
    assert not _iterates_all_devices(path), (
        f"{filename} перечисляет coordinator.devices — это весь аккаунт, а не выбор "
        f"пользователя. Нужен coordinator.enabled_devices, иначе невыбранные "
        f"устройства протащатся в HA (issue #45)."
    )


class TestEnabledDevices:
    """Сам фильтр: что он отдаёт в трёх состояниях выбора."""

    @staticmethod
    def _coordinator(enabled: list[str] | None):
        from custom_components.sberhome.coordinator import SberHomeCoordinator

        coord = object.__new__(SberHomeCoordinator)
        coord.state_cache = type(
            "Cache", (), {"get_all_devices": lambda self: {
                "dev-1": DeviceDto(id="dev-1"),
                "dev-2": DeviceDto(id="dev-2"),
            }}
        )()
        options = {} if enabled is None else {CONF_ENABLED_DEVICE_IDS: enabled}
        coord.config_entry = type("Entry", (), {"options": options})()
        return coord

    def test_unset_means_everything(self):
        """Старые установки, где выбора не было: ломать их нельзя."""
        assert set(self._coordinator(None).enabled_devices) == {"dev-1", "dev-2"}

    def test_only_the_chosen_ones(self):
        assert set(self._coordinator(["dev-2"]).enabled_devices) == {"dev-2"}

    def test_empty_choice_means_nothing(self):
        """Явно выбранный ноль устройств — это ноль, а не «показать всё»."""
        assert self._coordinator([]).enabled_devices == {}
