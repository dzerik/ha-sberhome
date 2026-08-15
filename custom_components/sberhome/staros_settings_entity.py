"""Базовый класс HA-сущностей настроек умных колонок Сбера.

Настройки колонок живут в отдельном канале от gateway-устройств: у них нет
`reported_state`, состояние берётся из `coordinator.staros_settings_entities`
(ключ — serial колонки). Общая логика (lookup текущего дескриптора,
device_info привязки к колонке, availability, запись значения) вынесена сюда,
конкретные платформы (switch/select/number) наследуются.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SPEAKER_MERGE_DOMAIN
from .coordinator import SberHomeCoordinator
from .sbermap import StarosSettingEntity


class SberStarosSettingBase(CoordinatorEntity[SberHomeCoordinator]):
    """Общая база сущности-настройки колонки.

    Значение всегда читается из координатора (не хранится своё), поэтому
    optimistic-обновления и polling автоматически отражаются в UI.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        spec: StarosSettingEntity,
    ) -> None:
        super().__init__(coordinator)
        self._serial = spec.serial
        self._product = spec.product
        self._node_id = spec.node_id
        self._node_type = spec.node_type
        self._attr_unique_id = spec.unique_id
        self._attr_name = spec.name
        self._attr_entity_category = spec.entity_category
        self._attr_entity_registry_enabled_default = spec.enabled_by_default
        # Привязка к устройству-колонке (identifiers по serial), чтобы настройки
        # группировались с самим устройством в HA. Плюс общий с sboom_ha
        # identifier — HA сольёт медиа (sboom_ha) и настройки (sberhome) в одну
        # карточку устройства.
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, self._serial),
                (SPEAKER_MERGE_DOMAIN, self._serial),
            }
        )

    def _current(self) -> StarosSettingEntity | None:
        """Актуальный дескриптор из координатора (или None, если исчез)."""
        for ent in self.coordinator.staros_settings_entities.get(self._serial, []):
            if ent.node_id == self._node_id:
                return ent
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Служебные атрибуты набора эквалайзера.

        Фронтенд (панель/карточка sboom) находит сущности эквалайзера по
        `eq_group`/`eq_role` вместо хрупкого матчинга по имени. Для не-эквалайзер
        настроек атрибутов нет.
        """
        spec = self._current()
        if spec is None or spec.eq_group is None:
            return None
        attrs: dict[str, Any] = {"eq_group": spec.eq_group, "eq_role": spec.eq_role}
        if spec.eq_band_index is not None:
            attrs["eq_band_index"] = spec.eq_band_index
        if spec.eq_frequency is not None:
            attrs["eq_frequency"] = spec.eq_frequency
        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._current() is not None

    async def _async_write(self, value: Any) -> None:
        await self.coordinator.async_set_staros_setting(
            self._serial,
            self._product,
            self._node_id,
            self._node_type,
            value,
        )
