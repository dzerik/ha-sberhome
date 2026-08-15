"""Support for SberHome select entities — sbermap-driven (PR #7 + PR #9)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, StarosSettingEntity, build_select_command
from .staros_settings_entity import SberStarosSettingBase


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.SELECT:
                entities.append(SberSbermapSelect(coordinator, device_id, ent))
    # Настройки-выбор умных колонок Сбера.
    for specs in coordinator.staros_settings_entities.values():
        for spec in specs:
            if spec.platform is Platform.SELECT:
                entities.append(SberStarosSettingSelect(coordinator, spec))
    async_add_entities(entities)


class SberSbermapSelect(SberBaseEntity, SelectEntity):
    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        ha_entity: HaEntityData,
    ) -> None:
        dto = coordinator.devices.get(device_id)
        device_real_id = (dto.id if dto else None) or device_id
        prefix = f"{device_real_id}_"
        suffix = (
            ha_entity.unique_id[len(prefix) :] if ha_entity.unique_id.startswith(prefix) else ""
        )
        super().__init__(coordinator, device_id, suffix)
        self._ha_unique_id = ha_entity.unique_id
        self._state_key = ha_entity.state_attribute_key or ""
        options = list(ha_entity.options or ())
        # Fallback: если spec не дал options (Sber иногда отдаёт ENUM
        # без enum_values), берём их из кэша /devices/enums по
        # attribute_key. Кэш заполняется однократно при первом refresh.
        if not options and self._state_key:
            options = coordinator.enum_values_for(self._state_key)
        self._attr_options = options
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon

    @property
    def current_option(self) -> str | None:
        ent = self._entity_data(self._ha_unique_id)
        if ent is None:
            return None
        v = ent.state
        return v if v in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self._async_send_attrs(
            build_select_command(device_id=self._device_id, key=self._state_key, option=option)
        )


class SberStarosSettingSelect(SberStarosSettingBase, SelectEntity):
    """Настройка-выбор умной колонки Сбера.

    В выпадающем списке показываем человекочитаемые заголовки
    (`option_titles`), а на запись переводим выбранный заголовок обратно
    в wire-значение. Если для варианта заголовок не пришёл — используем
    само значение как отображаемое.
    """

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        spec: StarosSettingEntity,
    ) -> None:
        super().__init__(coordinator, spec)
        self._init_spec = spec

    def _spec(self) -> StarosSettingEntity:
        return self._current() or self._init_spec

    @staticmethod
    def _labels(spec: StarosSettingEntity) -> tuple[list[str], dict[str, str]]:
        """(отображаемые заголовки, заголовок → wire-значение)."""
        labels: list[str] = []
        label_to_value: dict[str, str] = {}
        for value in spec.options:
            label = spec.option_titles.get(value, value)
            labels.append(label)
            label_to_value[label] = value
        return labels, label_to_value

    @property
    def options(self) -> list[str]:
        labels, _ = self._labels(self._spec())
        return labels

    @property
    def current_option(self) -> str | None:
        spec = self._current()
        if spec is None or spec.state is None:
            return None
        labels, _ = self._labels(spec)
        label = spec.option_titles.get(spec.state, spec.state)
        return label if label in labels else None

    async def async_select_option(self, option: str) -> None:
        _, label_to_value = self._labels(self._spec())
        await self._async_write(label_to_value.get(option, option))
