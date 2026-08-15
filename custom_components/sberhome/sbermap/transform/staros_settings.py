"""Маппинг server-driven настроек колонок Сбера → HA-сущности.

Отдельный слой от gateway-устройств: у настроек колонок нет `reported_state`
и attribute-ключей, вместо этого сервер отдаёт дерево узлов (server-driven UI),
каждый со своим `type` (TOGGLE / RADIO_BUTTONS / SLIDER / …). Поэтому здесь
свой dataclass `StarosSettingEntity`, а не общий `HaEntityData`.

Гибридный режим sbermap: HA imports разрешены (используем `Platform`,
`EntityCategory`, `STATE_ON`/`STATE_OFF` для type safety).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory, Platform

if TYPE_CHECKING:
    from ...aiosber.dto.settings import SettingNodeDto, SettingScreenDto

# --- Классификация wire-типов узлов ---------------------------------------
# Тумблеры → switch.
_TOGGLE_TYPES: frozenset[str] = frozenset({"TOGGLE", "UI_TOGGLE_SWITCHER"})
# Выбор из вариантов → select.
_SELECT_TYPES: frozenset[str] = frozenset({"RADIO_BUTTONS", "SELECT"})
# Слайдеры/громкость → number.
_SLIDER_TYPES: frozenset[str] = frozenset({"SLIDER", "SLIDER_V2", "STARCAST_VOLUME"})
# Эквалайзер — особый узел: раскрывается в набор сущностей, а запись собирает
# весь объект целиком (см. _make_equalizer + coordinator.async_set_staros_setting).
_EQUALIZER_TYPE = "EQUALIZER"
# Декоративные/контейнерные узлы: сами сущностей не дают, но их дети — могут.
_DECOR_TYPES: frozenset[str] = frozenset(
    {
        "SECTION_HEADER",
        "HEADER_TEXT",
        "SETTINGS_SECTION_GROUP",
        "CARD",
        "LANDING_CARD",
        "LANDING_CARD_V2",
        "START_WEBVIEW_CARD",
        "WEBSOCKET_STATE_CARD",
        "COPY",
        "OPEN_BETA_CARD",
    }
)

# Дефолтный шаг слайдера, когда сервер его не прислал.
_DEFAULT_STEP = 1.0

# Метка ручного режима (полосы выставлены пользователем, не пресетом).
EQ_PRESET_MANUAL = "Своя настройка"

# Встроенные пресеты эквалайзера — точные имена и значения из приложения Сбера
# (полосы 300/500/1400/3900/6500 Гц, дБ). Сервер список пресетов в дереве
# настроек не отдаёт, поэтому держим их у себя. При выборе пресета его полосы
# выставляются в number-сущности (см. coordinator). ВАЖНО: значения должны
# точно совпадать с приложением — иначе оно считает пресет «своей настройкой».
_BUILTIN_EQ_PRESETS: dict[str, tuple[float, ...]] = {
    "Ровный": (0.0, 0.0, 0.0, 0.0, 0.0),
    "Эмбиент": (0.0, -2.5, -2.5, -2.5, -1.0),
    "Басы": (3.5, 1.5, 0.0, 0.0, 0.0),
    "Голос": (-0.5, 1.0, 4.0, 2.5, -0.5),
}


# Продукты колонок, поддерживающих аудио-эквалайзер. Сервер узел `equalizer`
# в дереве настроек отдаёт не для всех прошивок (у ряда моделей его там нет),
# хотя запись эквалайзера поддерживается (id узла фиксирован — `equalizer`).
# Для таких колонок узел синтезируется с известной структурой.
EQ_SUPPORTED_PRODUCT_PREFIXES: tuple[str, ...] = ("sberboom",)

# Известная структура аудио-эквалайзера колонок SberBoom (частоты полос — как
# в приложении Сбера: 300/500/1400/3900/6500 Гц).
_EQ_FREQUENCIES: tuple[int, ...] = (300, 500, 1400, 3900, 6500)
_EQ_MIN_MAX_STEP: tuple[float, float, float] = (-4.0, 4.0, 0.5)
_EQ_DEFAULT_BANDS: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0)


def product_supports_equalizer(product: str | None) -> bool:
    """Поддерживает ли продукт колонки аудио-эквалайзер (для синтеза узла)."""
    p = (product or "").lower()
    return p.startswith(EQ_SUPPORTED_PRODUCT_PREFIXES)


class _SyntheticEqNode:
    """Лёгкий узел эквалайзера с известной структурой (для синтеза).

    Дублирует ровно те поля `SettingNodeDto`, что читает `_make_equalizer`.
    """

    __slots__ = (
        "active_preset",
        "disabled",
        "enabled",
        "frequencies",
        "id",
        "min_max_step",
        "presets",
        "title",
        "user_bands",
    )

    def __init__(self, enabled: bool, bands: list[float], active_preset: str | None) -> None:
        self.id = "equalizer"
        self.title = "Эквалайзер"
        self.disabled = None
        self.enabled = enabled
        self.presets = []
        self.active_preset = active_preset
        self.frequencies = list(_EQ_FREQUENCIES)
        self.min_max_step = list(_EQ_MIN_MAX_STEP)
        self.user_bands = bands


def build_synthetic_equalizer(
    product: str,
    serial: str,
    *,
    enabled: bool = True,
    bands: list[float] | None = None,
    active_preset: str | None = "user",
) -> list[StarosSettingEntity]:
    """Синтезировать набор сущностей эквалайзера с известной структурой.

    Используется, когда сервер не вернул узел `equalizer` в дереве настроек,
    но колонка его поддерживает. Текущие полосы (`bands`) переносятся с прошлого
    опроса (optimistic), по умолчанию — flat.
    """
    node = _SyntheticEqNode(
        enabled=enabled,
        bands=list(bands) if bands is not None else list(_EQ_DEFAULT_BANDS),
        active_preset=active_preset,
    )
    return _make_equalizer(node, product, serial)


def builtin_equalizer_preset_names() -> tuple[str, ...]:
    """Имена встроенных пресетов эквалайзера (для опций select)."""
    return tuple(_BUILTIN_EQ_PRESETS)


def equalizer_preset_bands(name: str | None) -> tuple[float, ...] | None:
    """Полосы встроенного пресета по имени, либо None (ручной/неизвестный)."""
    if name is None:
        return None
    return _BUILTIN_EQ_PRESETS.get(name)


@dataclass(slots=True, frozen=True)
class StarosSettingEntity:
    """Описание одной HA-сущности настройки колонки.

    Args:
        platform: HA-platform (SWITCH / SELECT / NUMBER).
        unique_id: уникальный ID для HA entity registry.
        name: display name.
        node_id: id узла настройки на стороне сервера (для записи).
        node_type: wire-тип узла (для записи `set_setting`).
        product: продукт колонки (для записи).
        serial: серийный номер колонки (для записи + привязки к устройству).
        state: текущее значение (STATE_ON/STATE_OFF, str-option или число).
        options: варианты для SELECT (значения).
        option_titles: value → человекочитаемый заголовок варианта.
        min_value/max_value/step/unit: диапазон для NUMBER.
        entity_category: HA EntityCategory (обычно CONFIG).
        enabled_by_default: включена ли сущность по умолчанию.
    """

    platform: Platform
    unique_id: str
    name: str
    node_id: str
    node_type: str
    product: str
    serial: str
    state: Any
    options: tuple[str, ...] = ()
    option_titles: dict[str, str] = field(default_factory=dict)
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    unit: str | None = None
    entity_category: Any | None = None
    enabled_by_default: bool = True
    # Эквалайзер: один узел раскрывается в набор сущностей (enabled/preset/полосы).
    # `eq_group` — id узла эквалайзера (общий для набора, для реконструкции записи),
    # `eq_role` ∈ {"enabled","preset","band"}, `eq_band_index` — индекс полосы.
    eq_group: str | None = None
    eq_role: str | None = None
    eq_band_index: int | None = None
    eq_frequency: int | None = None  # частота полосы, Гц (для UI-подписи)


def map_settings_screen_to_entities(
    screen: SettingScreenDto, product: str, serial: str
) -> list[StarosSettingEntity]:
    """Обойти дерево настроек и собрать список HA-сущностей.

    Рекурсия идёт и по `screen.settings`, и по `node.children` (раскрытые
    подэкраны CARD). Декоративные узлы сущностей не дают, но их дети
    обходятся.
    """
    result: list[StarosSettingEntity] = []
    # Один и тот же node_id может встретиться и на корневом экране, и в
    # раскрытом подэкране CARD — тогда unique_id совпал бы, и HA отбросил бы
    # второй дубль. Дедуплицируем по node_id при обходе.
    seen_ids: set[str] = set()

    def _add(entity: StarosSettingEntity | None) -> None:
        if entity is not None and entity.node_id not in seen_ids:
            seen_ids.add(entity.node_id)
            result.append(entity)

    def walk(node: SettingNodeDto) -> None:
        # Эквалайзер — один узел, но раскрывается в несколько сущностей.
        if node.type == _EQUALIZER_TYPE:
            for ent in _make_equalizer(node, product, serial):
                _add(ent)
        else:
            _add(_node_to_entity(node, product, serial))
        for child in node.children:
            walk(child)

    for node in screen.settings:
        walk(node)
    return result


def build_staros_value(node_type: str, value: Any) -> Any:
    """Привести HA-значение к типу, который ждёт сервер настроек.

    SWITCH → bool, SELECT → str, NUMBER → int (если целое) иначе float.
    Неизвестный тип — passthrough (сущность-фолбэк уже даёт корректный тип).
    """
    if node_type in _TOGGLE_TYPES:
        return bool(value)
    if node_type in _SELECT_TYPES:
        return str(value)
    if node_type in _SLIDER_TYPES:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return value
        return int(num) if num.is_integer() else num
    return value


# --- Internal --------------------------------------------------------------
def _node_to_entity(node: SettingNodeDto, product: str, serial: str) -> StarosSettingEntity | None:
    """Один узел → сущность (или None, если узел не управляемый)."""
    node_id = node.id
    node_type = node.type
    if not node_id or not node_type:
        return None

    unique_id = f"staros_{serial}_{node_id}"
    name = node.title or node_id
    enabled_by_default = node.disabled is not True

    common = {
        "unique_id": unique_id,
        "name": name,
        "node_id": node_id,
        "node_type": node_type,
        "product": product,
        "serial": serial,
        "entity_category": EntityCategory.CONFIG,
        "enabled_by_default": enabled_by_default,
    }

    if node_type in _TOGGLE_TYPES:
        return StarosSettingEntity(
            platform=Platform.SWITCH,
            state=STATE_ON if node.current_value else STATE_OFF,
            **common,
        )
    if node_type in _SELECT_TYPES:
        return _make_select(node, common)
    if node_type in _SLIDER_TYPES:
        return _make_number(node, common)
    if node_type in _DECOR_TYPES:
        return None

    # Фолбэк для неизвестных типов — по форме данных узла.
    current = node.current_value
    if isinstance(current, bool) and not node.options:
        return StarosSettingEntity(
            platform=Platform.SWITCH,
            state=STATE_ON if current else STATE_OFF,
            **common,
        )
    if node.options:
        return _make_select(node, common)
    if node.minimum is not None or node.maximum is not None:
        return _make_number(node, common)
    return None


def _make_select(node: SettingNodeDto, common: dict[str, Any]) -> StarosSettingEntity:
    options = tuple(str(o.value) for o in node.options)
    option_titles = {str(o.value): o.title for o in node.options if o.title is not None}
    current = node.current_value
    state = str(current) if current is not None else None
    return StarosSettingEntity(
        platform=Platform.SELECT,
        state=state,
        options=options,
        option_titles=option_titles,
        **common,
    )


def _make_number(node: SettingNodeDto, common: dict[str, Any]) -> StarosSettingEntity:
    minimum = node.minimum
    maximum = node.maximum
    step = node.step
    # Часть слайдеров отдаёт диапазон массивом `minMaxStep=[min, max, step]`
    # вместо отдельных полей min/max/step. Подхватываем недостающие границы,
    # иначе HA подставит дефолтные 0..100 и исказит реальный диапазон.
    mms = node.min_max_step
    if minimum is None and len(mms) >= 1:
        minimum = mms[0]
    if maximum is None and len(mms) >= 2:
        maximum = mms[1]
    if step is None and len(mms) >= 3:
        step = mms[2]
    return StarosSettingEntity(
        platform=Platform.NUMBER,
        state=node.current_value,
        min_value=minimum,
        max_value=maximum,
        step=step if step is not None else _DEFAULT_STEP,
        unit=node.unit,
        **common,
    )


def _match_preset(active_preset: str | None, bands: list[float], options: list[str]) -> str:
    """Имя пресета, соответствующего фактическим полосам.

    Приоритет: серверный ``activePreset`` (если это валидная опция и не «user»)
    → встроенный пресет, чьи значения совпали с полосами → «Вручную».
    """
    if active_preset and active_preset in options and active_preset != "user":
        return active_preset
    band_tuple = tuple(round(b, 2) for b in bands)
    for name in options:
        preset = equalizer_preset_bands(name)
        if preset is not None and tuple(round(b, 2) for b in preset) == band_tuple:
            return name
    return EQ_PRESET_MANUAL


def _make_equalizer(node: SettingNodeDto, product: str, serial: str) -> list[StarosSettingEntity]:
    """Узел EQUALIZER → набор сущностей: enabled(switch) + preset(select) + полосы(number).

    Все сущности набора помечены общим ``eq_group`` (= id узла эквалайзера).
    Запись любой из них собирает весь объект эквалайзера заново из текущих
    состояний набора (см. coordinator.async_set_staros_setting).
    """
    eqid = node.id
    if not eqid:
        return []
    title = node.title or "Эквалайзер"
    base: dict[str, Any] = {
        "node_type": _EQUALIZER_TYPE,
        "product": product,
        "serial": serial,
        "entity_category": EntityCategory.CONFIG,
        "enabled_by_default": node.disabled is not True,
        "eq_group": eqid,
    }
    ents: list[StarosSettingEntity] = [
        StarosSettingEntity(
            platform=Platform.SWITCH,
            unique_id=f"staros_{serial}_{eqid}_enabled",
            name=title,
            node_id=f"{eqid}__enabled",
            state=STATE_ON if node.enabled else STATE_OFF,
            eq_role="enabled",
            **base,
        )
    ]
    # Опции пресетов: серверные (если пришли) + встроенные, без дублей, плюс
    # «Вручную» — режим, когда полосы выставлены руками (не совпали ни с одним
    # пресетом). Селект строим всегда: встроенные пресеты есть на любой прошивке.
    preset_names: list[str] = list(node.presets)
    for name in builtin_equalizer_preset_names():
        if name not in preset_names:
            preset_names.append(name)
    if EQ_PRESET_MANUAL not in preset_names:
        preset_names.append(EQ_PRESET_MANUAL)
    # Текущий пресет: тот, чьи полосы совпали с фактическими; иначе — «Вручную».
    current_preset = _match_preset(node.active_preset, node.user_bands, preset_names)
    ents.append(
        StarosSettingEntity(
            platform=Platform.SELECT,
            unique_id=f"staros_{serial}_{eqid}_preset",
            name=f"{title} — пресет",
            node_id=f"{eqid}__preset",
            state=current_preset,
            options=tuple(preset_names),
            eq_role="preset",
            **base,
        )
    )
    mms = node.min_max_step
    mn = mms[0] if len(mms) >= 1 else None
    mx = mms[1] if len(mms) >= 2 else None
    st = mms[2] if len(mms) >= 3 else _DEFAULT_STEP
    for i, band in enumerate(node.user_bands):
        freq = node.frequencies[i] if i < len(node.frequencies) else None
        band_name = f"{title} {freq} Гц" if freq is not None else f"{title} полоса {i + 1}"
        ents.append(
            StarosSettingEntity(
                platform=Platform.NUMBER,
                unique_id=f"staros_{serial}_{eqid}_band_{i}",
                name=band_name,
                node_id=f"{eqid}__band_{i}",
                state=band,
                min_value=mn,
                max_value=mx,
                step=st,
                eq_role="band",
                eq_band_index=i,
                eq_frequency=freq,
                **base,
            )
        )
    return ents


__all__ = [
    "EQ_PRESET_MANUAL",
    "StarosSettingEntity",
    "build_staros_value",
    "build_synthetic_equalizer",
    "builtin_equalizer_preset_names",
    "equalizer_preset_bands",
    "map_settings_screen_to_entities",
    "product_supports_equalizer",
]
