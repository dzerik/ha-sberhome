"""Tests for Feature-Descriptor mapper (3.0.0+)."""

from __future__ import annotations

import json
from pathlib import Path

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory, Platform

from custom_components.sberhome.aiosber.dto import DeviceDto
from custom_components.sberhome.sbermap.transform.mapper import (
    build_command,
    map_device_to_entities,
)

_AURA_DUMP = Path(__file__).resolve().parents[3] / "docs" / "aura2.0.json"


def _dto(image_set_type: str, reported: list[dict] | None = None, **kw) -> DeviceDto:
    data = {
        "id": "test-id",
        "name": "Test",
        "image_set_type": image_set_type,
        "reported_state": reported or [],
        **kw,
    }
    return DeviceDto.from_dict(data)


# =============================================================================
# Primary entity creation
# =============================================================================


class TestPrimaryEntities:
    def test_light_creates_light(self):
        dto = _dto("bulb_sber", [{"key": "on_off", "bool_value": True}])
        ents = map_device_to_entities(dto)
        platforms = {e.platform for e in ents}
        assert Platform.LIGHT in platforms

    def test_socket_creates_switch(self):
        dto = _dto("cat_socket", [{"key": "on_off", "bool_value": True}])
        ents = map_device_to_entities(dto)
        primary = next(e for e in ents if e.unique_id == "test-id")
        assert primary.platform is Platform.SWITCH

    def test_hvac_ac_creates_climate(self):
        dto = _dto(
            "hvac_ac",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "hvac_work_mode", "enum_value": "cool"},
            ],
        )
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.CLIMATE for e in ents)

    def test_curtain_creates_cover(self):
        dto = _dto(
            "cat_curtain",
            [
                {"key": "open_state", "enum_value": "open"},
                {"key": "open_percentage", "integer_value": 50},
            ],
        )
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.COVER for e in ents)

    def test_vacuum_creates_vacuum(self):
        dto = _dto(
            "cat_vacuum_cleaner",
            [
                {"key": "vacuum_cleaner_status", "enum_value": "idle"},
            ],
        )
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.VACUUM for e in ents)

    def test_hub_creates_binary_sensor(self):
        dto = _dto("cat_hub", [{"key": "online", "bool_value": True}])
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.BINARY_SENSOR for e in ents)

    def test_unknown_category_returns_empty(self):
        dto = _dto("completely_unknown_xyz", [])
        assert map_device_to_entities(dto) == []


# =============================================================================
# Extra entity auto-discovery
# =============================================================================


class TestAutoDiscovery:
    def test_battery_sensor_created(self):
        dto = _dto(
            "cat_socket",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "battery_percentage", "integer_value": 85},
            ],
        )
        ents = map_device_to_entities(dto)
        battery = next((e for e in ents if "battery_percentage" in e.unique_id), None)
        assert battery is not None
        assert battery.platform is Platform.SENSOR
        assert battery.state == 85

    def test_unknown_feature_skipped(self):
        dto = _dto(
            "cat_socket",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "completely_unknown_feature", "string_value": "x"},
            ],
        )
        ents = map_device_to_entities(dto)
        assert not any("completely_unknown" in e.unique_id for e in ents)

    def test_online_creates_connectivity(self):
        dto = _dto(
            "cat_socket",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "online", "bool_value": True},
            ],
        )
        ents = map_device_to_entities(dto)
        online = next((e for e in ents if "online" in e.unique_id), None)
        assert online is not None
        assert online.platform is Platform.BINARY_SENSOR

    def test_sensor_air_creates_all_air_quality_sensors(self):
        """sensor_air (2026-07): CO2/PM/TVOC/HCHO + temperature/humidity/battery.

        Все feature'ы должны маппиться в SENSOR entities с корректными
        device_class'ами (CO2, PM1/PM10/PM25, VOC) и юнитами (ppm, µg/m³,
        mg/m³). temp_unit_view создаётся как SELECT.
        """
        from homeassistant.components.sensor import SensorDeviceClass

        dto = _dto(
            "cat_sensor_air_m",
            [
                {"key": "online", "bool_value": True},
                {"key": "co2", "integer_value": 850},
                {"key": "pm1_0", "integer_value": 5},
                {"key": "pm2_5", "integer_value": 12},
                {"key": "pm10", "integer_value": 20},
                {"key": "hcho_float", "float_value": 0.045},
                {"key": "tvoc_float", "float_value": 0.35},
                {"key": "temperature", "integer_value": 235},  # 23.5°C
                {"key": "humidity", "integer_value": 55},
                {"key": "battery_percentage", "integer_value": 88},
                {"key": "temp_unit_view", "enum_value": "celsius"},
            ],
        )
        ents = map_device_to_entities(dto)
        by_key = {e.unique_id.rsplit("_", 1)[-1]: e for e in ents}

        # CO2
        co2 = next((e for e in ents if e.unique_id.endswith("_co2")), None)
        assert co2 is not None
        assert co2.platform is Platform.SENSOR
        assert co2.device_class == SensorDeviceClass.CO2
        assert co2.state == 850

        # PM sensors
        for key, dc in (
            ("pm1_0", SensorDeviceClass.PM1),
            ("pm2_5", SensorDeviceClass.PM25),
            ("pm10", SensorDeviceClass.PM10),
        ):
            e = next((x for x in ents if x.unique_id.endswith(f"_{key}")), None)
            assert e is not None, f"missing entity for {key}"
            assert e.platform is Platform.SENSOR
            assert e.device_class == dc

        # TVOC — mg/m³ + VOLATILE_ORGANIC_COMPOUNDS device_class
        tvoc = next((e for e in ents if e.unique_id.endswith("_tvoc_float")), None)
        assert tvoc is not None
        assert tvoc.device_class == SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS

        # HCHO — no device_class, just float
        hcho = next((e for e in ents if e.unique_id.endswith("_hcho_float")), None)
        assert hcho is not None
        assert hcho.platform is Platform.SENSOR
        assert hcho.device_class is None

        # Global features work too — temperature/humidity/battery
        assert any(e.unique_id.endswith("_temperature") for e in ents)
        assert any(e.unique_id.endswith("_humidity") for e in ents)
        assert any(e.unique_id.endswith("_battery_percentage") for e in ents)

        # temp_unit_view — SELECT
        tuv = next((e for e in ents if e.unique_id.endswith("_temp_unit_view")), None)
        assert tuv is not None
        assert tuv.platform is Platform.SELECT


# =============================================================================
# Category restrictions
# =============================================================================


class TestCategoryRestrictions:
    def test_child_lock_only_for_socket(self):
        dto_socket = _dto(
            "cat_socket",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "child_lock", "bool_value": False},
            ],
        )
        dto_light = _dto(
            "bulb_sber",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "child_lock", "bool_value": False},
            ],
        )
        socket_ents = map_device_to_entities(dto_socket)
        light_ents = map_device_to_entities(dto_light)
        assert any("child_lock" in e.unique_id for e in socket_ents)
        assert not any("child_lock" in e.unique_id for e in light_ents)

    def test_consumed_features_not_duplicated(self):
        """on_off consumed by SWITCH primary — no separate switch entity."""
        dto = _dto("cat_socket", [{"key": "on_off", "bool_value": True}])
        ents = map_device_to_entities(dto)
        switches = [e for e in ents if e.platform is Platform.SWITCH]
        assert len(switches) == 1  # only primary, no extra on_off


# =============================================================================
# Reverse mapper (build_command)
# =============================================================================


class TestBuildCommand:
    def test_bool_command(self):
        attrs = build_command("dev-1", on_off=True)
        assert len(attrs) == 1
        assert attrs[0].key == "on_off"
        assert attrs[0].bool_value is True

    def test_multi_feature_command(self):
        attrs = build_command("dev-1", on_off=True, light_brightness=200)
        keys = {a.key for a in attrs}
        assert keys == {"on_off", "light_brightness"}

    def test_none_values_skipped(self):
        attrs = build_command("dev-1", on_off=True, light_brightness=None)
        assert len(attrs) == 1

    def test_unknown_feature_passthrough(self):
        attrs = build_command("dev-1", unknown_feature=42)
        assert attrs[0].key == "unknown_feature"
        assert attrs[0].integer_value == 42

    def test_enum_command(self):
        attrs = build_command("dev-1", hvac_work_mode="cool")
        assert attrs[0].enum_value == "cool"


# =============================================================================
# Desired state override: epoch-timestamp guard
# =============================================================================


class TestDesiredOverride:
    """Sber возвращает в desired_state junk для read-only фичей (temperature,
    humidity, battery) с last_sync=1970-01-01 + value=range_min. Без guard'а
    mapper перезаписывал reported этим junk'ом.
    """

    def test_epoch_desired_does_not_override_reported(self):
        """desired с last_sync=1970 НЕ должен переписывать reported."""
        dto = _dto(
            "cat_sensor_temp_humidity_m",
            reported=[
                {
                    "key": "temperature",
                    "type": "FLOAT",
                    "float_value": 23.9,
                    "last_sync": "2026-04-21T12:47:56.916Z",
                },
                {
                    "key": "humidity",
                    "type": "FLOAT",
                    "float_value": 38.0,
                    "last_sync": "2026-04-21T12:47:56.916Z",
                },
            ],
            desired_state=[
                {
                    "key": "temperature",
                    "type": "FLOAT",
                    "float_value": -40.0,  # junk = range.min
                    "last_sync": "1970-01-01T00:00:00Z",
                },
                {
                    "key": "humidity",
                    "type": "FLOAT",
                    "float_value": 0.0,  # junk
                    "last_sync": "1970-01-01T00:00:00Z",
                },
            ],
        )
        ents = {e.unique_id.split("_", 1)[-1]: e for e in map_device_to_entities(dto)}
        assert ents["temperature"].state == 23.9
        assert ents["humidity"].state == 38

    def test_null_desired_last_sync_does_not_override(self):
        """desired с last_sync=None тоже считается junk'ом."""
        dto = _dto(
            "cat_sensor_temp_humidity_m",
            reported=[
                {
                    "key": "temperature",
                    "type": "FLOAT",
                    "float_value": 20.5,
                    "last_sync": "2026-04-21T00:00:00Z",
                }
            ],
            desired_state=[
                {
                    "key": "temperature",
                    "type": "FLOAT",
                    "float_value": -40.0,
                    "last_sync": None,
                }
            ],
        )
        ents = {e.unique_id.split("_", 1)[-1]: e for e in map_device_to_entities(dto)}
        assert ents["temperature"].state == 20.5

    def test_fresh_desired_overrides_reported(self):
        """desired свежее reported → optimistic update работает (для ламп etc.)."""
        dto = _dto(
            "bulb_sber",
            reported=[
                {
                    "key": "on_off",
                    "type": "BOOL",
                    "bool_value": False,
                    "last_sync": "2026-04-21T10:00:00Z",
                }
            ],
            desired_state=[
                {
                    "key": "on_off",
                    "type": "BOOL",
                    "bool_value": True,
                    "last_sync": "2026-04-21T12:00:00Z",
                }
            ],
        )
        ents = {e.platform: e for e in map_device_to_entities(dto)}
        # primary light entity отражает desired (True → on)
        from homeassistant.const import STATE_ON

        assert ents[Platform.LIGHT].state == STATE_ON


class TestSberBoxTime:
    """SberBox Time — issue #43, по полному JSON от владельца устройства.

    Прибор рапортует четыре атрибута, но команды есть только у двух. Это и
    определяет, что чем становится: без команды поле можно только читать.
    """

    REPORTED = [
        {"key": "online", "bool_value": True},
        {"key": "gamepad", "bool_value": False},
        {"key": "staros_assistant_sounds_enabled", "bool_value": False},
        {"key": "staros_age_mode", "enum_value": "adult"},
    ]

    def _entities(self):
        return map_device_to_entities(_dto("dt_sberbox_time_m", self.REPORTED))

    def test_recognised_as_a_speaker(self):
        """Подстрока `dt_box` не покрывает `dt_sberbox_time_m`.

        Без отдельной записи в IMAGE_TYPE_MAP устройство не получало категории
        вовсе, а значит и ни одной сущности — ровно то, с чем пришёл владелец.
        """
        assert self._entities(), "устройство не дало ни одной сущности"

    def test_assistant_sounds_gateway_is_read_only(self):
        """Gateway-зеркало настройки — READ-ONLY (binary_sensor).

        Запись в gateway этого ключа сервер не применяет (значение
        «откатывается»); реальное управление идёт по каналу /v18. Поэтому
        gateway-представление экспонируем как датчик, а не переключатель.
        """
        ent = next(
            e for e in self._entities() if e.unique_id.endswith("staros_assistant_sounds_enabled")
        )
        assert ent.platform is Platform.BINARY_SENSOR

    def test_age_mode_gateway_is_read_only(self):
        """Gateway-зеркало возрастного режима — READ-ONLY (sensor).

        Управление возрастными ограничениями идёт через /v18-сущности
        («Ограничения для детей/всех»), а gateway-значение только отражает
        текущее состояние.
        """
        ent = next(e for e in self._entities() if e.unique_id.endswith("staros_age_mode"))
        assert ent.platform is Platform.SENSOR

    def test_gamepad_is_read_only(self):
        """Команды на gamepad прибор не объявляет.

        Сделать его переключателем значило бы обещать управление, которого нет:
        нажатие ушло бы в облако и молча ничего не изменило.
        """
        ent = next(e for e in self._entities() if e.unique_id.endswith("gamepad"))
        assert ent.platform is Platform.BINARY_SENSOR

    def test_commands_carry_the_value_and_nothing_else(self):
        """Проверяется содержимое, а не факт «что-то вернулось».

        build_command принимает пары «фича=значение» и молча превращает любой
        неизвестный kwarg в атрибут с таким именем. Утверждение вида
        `assert cmd` поэтому проходит даже на полностью неверном вызове.
        """
        age = build_command("dev-1", staros_age_mode="child")
        assert len(age) == 1
        assert age[0].key == "staros_age_mode"
        assert age[0].enum_value == "child"

        sounds = build_command("dev-1", staros_assistant_sounds_enabled=True)
        assert len(sounds) == 1
        assert sounds[0].key == "staros_assistant_sounds_enabled"
        assert sounds[0].bool_value is True


class TestAura:
    """СберБум 2.0 (Aura) — по выгрузке протокола устройства от владельца.

    Колонка на StarOS с двумя новыми gateway-атрибутами:
    - `motion_sensor` — встроенный радар присутствия, ENUM
      {no_motion, any_motion, sensor_disabled};
    - `motion_sensor_enabled` — включён ли радар (BOOL);
    - `call_status` — статус звонка, ENUM {idle, ringing, calling, talking, hold}.

    Проверяется, что каждый атрибут становится сущностью правильного вида и
    что ENUM корректно превращается в состояние (а не «залипает» в ON).
    """

    def _entities(self, reported):
        return map_device_to_entities(_dto("dt_aura_l", reported))

    def _one(self, reported, suffix):
        # endswith с ведущим "_" исключает ложные совпадения:
        # "_motion_sensor" НЕ ловит "..._motion_sensor_enabled".
        return next(e for e in self._entities(reported) if e.unique_id.endswith(suffix))

    def test_recognised_as_speaker(self):
        """`dt_aura_l` матчится подстрокой `dt_aura` → категория sber_speaker.

        Без записи в IMAGE_TYPE_MAP устройство не получило бы категории и ни
        одной сущности — ровно то, с чем пришёл владелец колонки.
        """
        assert self._entities([{"key": "motion_sensor", "type": "ENUM", "enum_value": "no_motion"}])

    def test_presence_any_motion_is_on(self):
        """any_motion → присутствие есть (occupancy, ON)."""
        ent = self._one(
            [{"key": "motion_sensor", "type": "ENUM", "enum_value": "any_motion"}],
            "_motion_sensor",
        )
        assert ent.platform is Platform.BINARY_SENSOR
        assert ent.device_class is BinarySensorDeviceClass.OCCUPANCY
        assert ent.state == STATE_ON

    def test_presence_no_motion_is_off(self):
        """no_motion → присутствия нет (OFF), а не ON от непустой enum-строки.

        Это и есть регрессия, ради которой введён EnumBoolCodec: обычный
        EnumCodec отдал бы строку "no_motion" → маппер сделал бы STATE_ON.
        """
        ent = self._one(
            [{"key": "motion_sensor", "type": "ENUM", "enum_value": "no_motion"}],
            "_motion_sensor",
        )
        assert ent.state == STATE_OFF

    def test_presence_sensor_disabled_is_off(self):
        """sensor_disabled (радар выключен) → присутствия нет (OFF)."""
        ent = self._one(
            [{"key": "motion_sensor", "type": "ENUM", "enum_value": "sensor_disabled"}],
            "_motion_sensor",
        )
        assert ent.state == STATE_OFF

    def test_presence_enabled_flag_is_readonly_diagnostic(self):
        """motion_sensor_enabled — read-only diagnostic binary_sensor, не switch.

        По прецеденту gateway-зеркал настроек колонки: запись в gateway сервер
        не применяет (значение «откатывается»), реальное управление радаром —
        через /v18-сущность. Поэтому флаг экспонируем как датчик, а не тумблер.
        """
        ent = self._one(
            [{"key": "motion_sensor_enabled", "type": "BOOL", "bool_value": True}],
            "_motion_sensor_enabled",
        )
        assert ent.platform is Platform.BINARY_SENSOR
        assert ent.entity_category is EntityCategory.DIAGNOSTIC
        assert ent.state == STATE_ON

    def test_presence_selector_does_not_catch_enabled_flag(self):
        """Селектор «_motion_sensor» не должен цеплять «_motion_sensor_enabled».

        Оба атрибута в одном дампе создают две разные сущности; выбор одной по
        суффиксу с ведущим подчёркиванием их не путает.
        """
        ents = self._entities(
            [
                {"key": "motion_sensor", "type": "ENUM", "enum_value": "any_motion"},
                {"key": "motion_sensor_enabled", "type": "BOOL", "bool_value": True},
            ]
        )
        presence = [e for e in ents if e.unique_id.endswith("_motion_sensor")]
        assert len(presence) == 1
        assert presence[0].device_class is BinarySensorDeviceClass.OCCUPANCY

    def test_call_status_is_plain_enum_sensor(self):
        """call_status — диагностический sensor с сырым enum-значением.

        Сознательно без device_class=ENUM: state = сырая строка "ringing"
        (device_class=ENUM потребовал бы прокидывания options в sensor.py и
        ругался бы warning'ом на значения вне списка, напр. "" при инициализации).
        """
        ent = self._one(
            [{"key": "call_status", "type": "ENUM", "enum_value": "ringing"}],
            "_call_status",
        )
        assert ent.platform is Platform.SENSOR
        assert ent.entity_category is EntityCategory.DIAGNOSTIC
        assert ent.device_class is None
        assert ent.state == "ringing"

    def test_full_dump_produces_three_new_entities(self):
        """Полный дамp владельца: reported перекрывает epoch-desired (junk).

        В дампе motion_sensor=no_motion, motion_sensor_enabled=true,
        call_status=idle; все desired-зеркала имеют last_sync=1970 → игнор.
        """
        dto = DeviceDto.from_dict(json.loads(_AURA_DUMP.read_text(encoding="utf-8")))
        ents = {
            e.state_attribute_key: e
            for e in map_device_to_entities(dto)
            if e.state_attribute_key in {"motion_sensor", "motion_sensor_enabled", "call_status"}
        }

        assert ents["motion_sensor"].platform is Platform.BINARY_SENSOR
        assert ents["motion_sensor"].device_class is BinarySensorDeviceClass.OCCUPANCY
        assert ents["motion_sensor"].state == STATE_OFF  # дамп = no_motion

        assert ents["motion_sensor_enabled"].platform is Platform.BINARY_SENSOR
        assert ents["motion_sensor_enabled"].entity_category is EntityCategory.DIAGNOSTIC
        assert ents["motion_sensor_enabled"].state == STATE_ON  # дамп = true

        assert ents["call_status"].platform is Platform.SENSOR
        assert ents["call_status"].state == "idle"  # дамп = idle


# =============================================================================
# Нормализация типов и свежесть desired
# =============================================================================


class TestDeclaredTypeNormalization:
    """Задекларированный в attributes[] тип важнее `type` конкретного значения."""

    def _humidity(self, declared: str, value: dict) -> object:
        dto = _dto(
            "cat_sensor_temp_humidity",
            [{"key": "humidity", "last_sync": "2026-09-15T10:00:00Z", **value}],
            attributes=[{"key": "humidity", "type": declared}],
        )
        ent = next(e for e in map_device_to_entities(dto) if e.state_attribute_key == "humidity")
        return ent.state

    def test_float_declared_integer_only_value(self):
        assert self._humidity("FLOAT", {"type": "INTEGER", "integer_value": "41"}) == 41

    def test_float_declared_without_any_number(self):
        assert self._humidity("FLOAT", {"type": "INTEGER"}) is None

    def test_integer_declared_float_only_value(self):
        assert self._humidity("INTEGER", {"type": "FLOAT", "float_value": 40.7}) == 40

    def test_integer_declared_without_any_number(self):
        assert self._humidity("INTEGER", {"type": "FLOAT"}) is None


class TestDesiredWithoutReported:
    def test_fresh_desired_used_when_nothing_reported(self):
        dto = _dto(
            "cat_socket",
            [],
            desired_state=[
                {"type": "BOOL", "bool_value": True},  # запись без key игнорируется
                {
                    "key": "on_off",
                    "type": "BOOL",
                    "bool_value": True,
                    "last_sync": "2026-09-15T10:00:00Z",
                },
            ],
        )
        primary = next(e for e in map_device_to_entities(dto) if e.unique_id == "test-id")
        assert primary.state == "on"


class TestClimatePrimaryAttributes:
    def test_target_current_and_fan(self):
        dto = _dto(
            "hvac_ac",
            [
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "hvac_work_mode", "type": "ENUM", "enum_value": "heat"},
                {"key": "hvac_temp_set", "type": "INTEGER", "integer_value": "24"},
                {"key": "temperature", "type": "FLOAT", "float_value": 22.5},
                {"key": "hvac_air_flow_power", "type": "ENUM", "enum_value": "medium"},
            ],
        )
        climate = next(e for e in map_device_to_entities(dto) if e.platform is Platform.CLIMATE)
        assert climate.attributes == {
            "temperature": 24,
            "current_temperature": 22.5,
            "fan_mode": "medium",
        }


def test_primary_platform_without_builder_gives_no_primary():
    from custom_components.sberhome.sbermap.transform.category_specs import (
        CategorySpec,
        build_primary_entity,
    )

    spec = CategorySpec(Platform.SENSOR, frozenset({"temperature"}))
    assert build_primary_entity({"temperature": 21}, spec, "dev", "Датчик", "sensor_temp") is None


class TestBuildCommandValueTypes:
    def test_float_colour_and_fallback_string(self):
        from custom_components.sberhome.aiosber.dto import AttributeValueType, ColorValue

        colour = ColorValue(hue=120, saturation=100, brightness=50)
        attrs = build_command(
            "dev", custom_float=21.5, custom_colour=colour, custom_list=["a", "b"]
        )
        by_key = {a.key: a for a in attrs}
        assert by_key["custom_float"].type is AttributeValueType.FLOAT
        assert by_key["custom_float"].float_value == 21.5
        assert by_key["custom_colour"].color_value == colour
        assert by_key["custom_list"].type is AttributeValueType.STRING
        assert by_key["custom_list"].string_value == "['a', 'b']"
