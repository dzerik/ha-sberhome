"""Compliance: CATEGORY_TO_HA_PLATFORMS ↔ реальные реестры генерации entities.

`spec/ha_mapping.py:CATEGORY_TO_HA_PLATFORMS` — ручная документация
«какие HA-платформы создаёт категория», используемая внешним проектом
MQTT-SberGate. Реальную генерацию делают `CATEGORY_SPECS` (primary)
+ `FEATURE_SPECS` (category-scoped extras) в transform/.

Автогенерировать таблицу нельзя — spec не может импортировать transform
(mapper.py уже импортирует spec → цикл). Поэтому: таблица остаётся
ручной, а этот тест ловит расхождение при любом изменении реестров.
SOLID/DRY-аудит нашёл уже случившийся дрейф (led_strip потерял SWITCH
от switch_led) — этот тест не даст ему повториться.
"""

from __future__ import annotations

from homeassistant.const import Platform

from custom_components.sberhome.sbermap.spec.ha_mapping import CATEGORY_TO_HA_PLATFORMS
from custom_components.sberhome.sbermap.transform.category_specs import CATEGORY_SPECS
from custom_components.sberhome.sbermap.transform.feature_specs import FEATURE_SPECS

# Платформы, добавляемые для категории ВНЕ sbermap-пайплайна.
# Каждая запись обязана иметь комментарий-обоснование.
ALLOWED_EXTRA: dict[str, set[Platform]] = {
    # LED-индикатор колонки создаётся отдельной entity в light.py через
    # IndicatorAPI (не через FEATURE_SPECS) — см. комментарий в
    # category_specs.py "sber_speaker".
    "sber_speaker": {Platform.LIGHT},
}


def _derived_platforms(category: str) -> set[Platform]:
    """Платформы, которые sbermap реально создаст для категории."""
    platforms: set[Platform] = set()
    spec = CATEGORY_SPECS.get(category)
    if spec is not None and spec.primary_platform is not None:
        platforms.add(spec.primary_platform)
    for fs in FEATURE_SPECS.values():
        if fs.platform is None:
            continue
        # Только category-scoped extras. Global features (battery,
        # signal_strength, online) применимы ко всем категориям и в
        # документационную таблицу не входят.
        if fs.categories is not None and category in fs.categories:
            platforms.add(fs.platform)
    return platforms


def test_table_covers_every_category_spec():
    """Каждая категория из CATEGORY_SPECS задокументирована в таблице."""
    missing = set(CATEGORY_SPECS) - set(CATEGORY_TO_HA_PLATFORMS)
    assert not missing, f"Категории без записи в CATEGORY_TO_HA_PLATFORMS: {missing}"


def test_table_has_no_stale_categories():
    """В таблице нет категорий, которых больше нет в CATEGORY_SPECS."""
    stale = set(CATEGORY_TO_HA_PLATFORMS) - set(CATEGORY_SPECS)
    assert not stale, f"Устаревшие категории в CATEGORY_TO_HA_PLATFORMS: {stale}"


def test_no_duplicate_platforms_in_tuples():
    """Кортежи не содержат дублей (был copy-paste `socket: (..SWITCH, ..SWITCH)`)."""
    for cat, platforms in CATEGORY_TO_HA_PLATFORMS.items():
        assert len(platforms) == len(set(platforms)), f"Дубли платформ у {cat}: {platforms}"


def test_table_matches_actual_registries():
    """Содержимое таблицы == derived из CATEGORY_SPECS+FEATURE_SPECS.

    При добавлении category-scoped FeatureSpec с новой платформой этот
    тест упадёт, требуя обновить документационную таблицу (и наоборот).
    """
    problems: list[str] = []
    for cat in sorted(CATEGORY_SPECS):
        documented = set(CATEGORY_TO_HA_PLATFORMS.get(cat, ()))
        expected = _derived_platforms(cat) | ALLOWED_EXTRA.get(cat, set())
        if documented != expected:
            extra = documented - expected
            missing = expected - documented
            problems.append(
                f"{cat}: documented={sorted(p.value for p in documented)} "
                f"expected={sorted(p.value for p in expected)} "
                f"(missing={sorted(p.value for p in missing)}, "
                f"extra={sorted(p.value for p in extra)})"
            )
    assert not problems, "CATEGORY_TO_HA_PLATFORMS разъехался с реестрами:\n" + "\n".join(problems)
