"""Каждый feature-key без стандартного device_class должен иметь
человекочитаемое имя в переводах (иначе HA покажет snake_case-фолбэк).

Регрессия для локализации сущностей: entity.py ставит translation_key =
feature-key и НЕ ставит _attr_name, поэтому имя обязано прийти из
translations. Ключи с device_class локализуются HA сами — их не требуем.
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.sberhome.sbermap.transform.feature_specs import FEATURE_SPECS

_BASE = Path(__file__).parent.parent / "custom_components" / "sberhome"
_LANGS = ("ru", "en", "be", "kk", "uz")


def _needs_name_keys() -> list[tuple[str, str]]:
    """(platform, key) для feature'ов без стандартного device_class."""
    out: list[tuple[str, str]] = []
    for key, spec in FEATURE_SPECS.items():
        plat = getattr(spec.platform, "value", None)
        if plat is None:
            continue
        codec = spec.codec
        dc = None
        for attr in ("device_class", "_device_class"):
            v = getattr(codec, attr, None)
            if v is not None:
                dc = v
                break
        if dc is None:
            out.append((plat, key))
    return out


def _entity_names(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")).get("entity", {})


def test_strings_json_covers_all_needs_name_keys():
    ent = _entity_names(_BASE / "strings.json")
    missing = [
        f"{plat}.{key}"
        for plat, key in _needs_name_keys()
        if not (ent.get(plat, {}).get(key, {}).get("name"))
    ]
    assert not missing, f"strings.json entity names missing: {missing}"


def test_all_langs_cover_all_needs_name_keys():
    needs = _needs_name_keys()
    for lang in _LANGS:
        ent = _entity_names(_BASE / "translations" / f"{lang}.json")
        missing = [
            f"{plat}.{key}"
            for plat, key in needs
            if not (ent.get(plat, {}).get(key, {}).get("name"))
        ]
        assert not missing, f"{lang}.json entity names missing: {missing}"


def test_select_option_states_translated_all_langs():
    """select'ы с options → должны иметь state-переводы во всех языках."""
    selects = {
        key: list(spec.options)
        for key, spec in FEATURE_SPECS.items()
        if spec.options and getattr(spec.platform, "value", None) == "select"
    }
    for lang in _LANGS + ("en",):
        path = _BASE / ("strings.json" if lang == "en" else f"translations/{lang}.json")
        ent = _entity_names(path)
        for key, opts in selects.items():
            states = ent.get("select", {}).get(key, {}).get("state", {})
            missing = [o for o in opts if o not in states]
            assert not missing, f"{path.name}: select.{key} missing states {missing}"
