"""Правило идентичности устройства — одно на всю интеграцию.

Раньше правил было два: реестр устройств ключевался серийником, а список
выбранных устройств — облачным id. Облачный id меняется при переподключении,
серийник нет. Отсюда и брался симптом «устройство видно, сущностей нет».

Эти тесты держат два инварианта: uid совпадает с тем, что уходит в
DeviceInfo.identifiers, и один uid никогда не включает два устройства.
"""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.identity import (
    device_match_keys,
    device_uid,
    resolve_enabled_ids,
    to_uids,
)


def _dto(device_id: str, serial: str | None = None, last_sync: str | None = None) -> DeviceDto:
    payload: dict = {"id": device_id, "name": {"name": device_id}}
    if serial is not None:
        payload["serial_number"] = serial
    if last_sync is not None:
        payload["reported_state"] = [
            {"key": "online", "type": "BOOL", "bool_value": True, "last_sync": last_sync}
        ]
    return DeviceDto.from_dict(payload)


class TestUidRule:
    def test_serial_wins_over_cloud_id(self) -> None:
        assert device_uid(_dto("cloud-A", serial="SER-1"), "key") == "SER-1"

    def test_cloud_id_used_when_serial_missing(self) -> None:
        assert device_uid(_dto("cloud-A"), "key") == "cloud-A"

    def test_fallback_used_when_nothing_known(self) -> None:
        assert device_uid(None, "key") == "key"

    def test_matches_device_info_identifier(self) -> None:
        """Инвариант: uid равен строке, которую entity.py кладёт в identifiers.

        Правило продублировано в двух местах, и любое расхождение возвращает
        исходную ошибку. Здесь оно зафиксировано в виде теста.
        """
        for dto, key in ((_dto("A", serial="S"), "A"), (_dto("A"), "A")):
            expected = (dto.serial_number if dto else None) or (dto.id if dto else None) or key
            assert device_uid(dto, key) == expected


class TestResolve:
    def test_new_format_survives_cloud_id_rotation(self) -> None:
        """Ради этого всё и затевалось: переподключение не теряет выбор."""
        before = resolve_enabled_ids({"A": _dto("A", serial="S")}, ["S"])
        after = resolve_enabled_ids({"B": _dto("B", serial="S")}, ["S"])
        assert before == {"A"}
        assert after == {"B"}

    def test_legacy_cloud_ids_still_match(self) -> None:
        """Старый формат обязан работать до миграции и во время неё."""
        assert resolve_enabled_ids({"A": _dto("A", serial="S")}, ["A"]) == {"A"}

    def test_unset_selection_stays_unset(self) -> None:
        """None означает «показывать всё». Превратить его в set() — худшая из регрессий."""
        assert resolve_enabled_ids({"A": _dto("A")}, None) is None

    def test_empty_selection_selects_nothing(self) -> None:
        assert resolve_enabled_ids({"A": _dto("A")}, []) == set()

    def test_unknown_key_selects_nothing(self) -> None:
        assert resolve_enabled_ids({"A": _dto("A", serial="S")}, ["ghost"]) == set()

    def test_duplicate_serial_enables_only_one(self) -> None:
        """Два устройства с одним серийником — включаем ровно одно.

        Наивное «совпало по любому ключу» включило бы оба и протащило в Home
        Assistant невыбранное устройство, то есть вернуло бы issue #45.
        """
        devices = {
            "A": _dto("A", serial="S", last_sync="2026-01-01T00:00:00Z"),
            "B": _dto("B", serial="S", last_sync="2026-08-01T00:00:00Z"),
        }
        assert resolve_enabled_ids(devices, ["S"]) == {"B"}

    def test_duplicate_serial_prefers_explicitly_chosen(self) -> None:
        """Явно выбранный облачный id важнее свежести."""
        devices = {
            "A": _dto("A", serial="S", last_sync="2026-01-01T00:00:00Z"),
            "B": _dto("B", serial="S", last_sync="2026-08-01T00:00:00Z"),
        }
        assert resolve_enabled_ids(devices, ["A"]) == {"A"}

    def test_result_is_stable_across_calls(self) -> None:
        """Выбор не должен прыгать между опросами."""
        devices = {"A": _dto("A", serial="S"), "B": _dto("B", serial="S")}
        assert resolve_enabled_ids(devices, ["S"]) == resolve_enabled_ids(devices, ["S"])


class TestToUids:
    def test_cloud_ids_become_serials(self) -> None:
        assert to_uids({"A": _dto("A", serial="S")}, ["A"]) == ["S"]

    def test_unresolvable_values_are_carried_over(self) -> None:
        """Устройство может быть офлайн — выбрасывать его выбор нельзя."""
        assert to_uids({"A": _dto("A", serial="S")}, ["A", "offline-dev"]) == ["S", "offline-dev"]

    def test_ambiguous_serial_stored_as_cloud_id(self) -> None:
        """Коллизию серийников разводим облачным id, иначе включатся оба."""
        devices = {"A": _dto("A", serial="S"), "B": _dto("B", serial="S")}
        assert to_uids(devices, ["A"]) == ["A"]

    def test_conversion_is_idempotent(self) -> None:
        devices = {"A": _dto("A", serial="S")}
        once = to_uids(devices, ["A"])
        assert to_uids(devices, once) == once


class TestMatchKeys:
    def test_all_known_identifiers_returned(self) -> None:
        assert device_match_keys(_dto("A", serial="S"), "cache-key") == {"A", "S", "cache-key"}

    def test_missing_dto_falls_back_to_cache_key(self) -> None:
        assert device_match_keys(None, "cache-key") == {"cache-key"}
