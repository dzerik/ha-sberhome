"""YAML loader для intents — `sberhome.intents` секция в configuration.yaml.

Парсит блок::

    sberhome:
      intents:
        - slug: morning                     # optional, autogen from name
          name: "Доброе утро"
          phrases:
            - "доброе утро"
          enabled: true                     # optional, default true
          description: "Утренний сценарий"  # optional
          actions:
            - type: ha_event_only
            - type: tts
              phrase: "Доброе утро!"
              device_ids: ["speaker-1"]
            - type: device_command
              device_id: "light-1"
              attributes:
                - key: on_off
                  type: BOOL
                  bool_value: true

→ список :class:`IntentSpec` с заполненным ``raw_extras["yaml_slug"]``
(используется reconciler для построения marker'а).

Минимальный набор action-типов (v5.2.0):
- ``ha_event_only`` — только fire HA-event `sberhome_intent`.
- ``tts`` — Sber произносит phrase через колонки.
- ``device_command`` — отправляет команду устройству.

Расширения (regime_command, condition_branch, ...) — в следующих
релизах. До этого они доступны только через UI; YAML ругается с
понятной ошибкой при попытке использовать unknown type.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from .spec import IntentAction, IntentSpec

_LOGGER = logging.getLogger(__name__)

# Известные YAML-action-типы. UI-actions с unknown=True здесь не нужны
# (они только read-only proxy для существующих сценариев из Sber).
_KNOWN_YAML_ACTION_TYPES = frozenset({"ha_event_only", "tts", "device_command"})

# Slug: lowercase, цифры/буквы/_/-. Используется в description-маркере.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _validate_action(value: Any) -> dict[str, Any]:
    """Schema-валидация одного action из YAML."""
    if not isinstance(value, dict):
        raise vol.Invalid(f"action должен быть dict, получено {type(value).__name__}")
    type_ = value.get("type")
    if type_ not in _KNOWN_YAML_ACTION_TYPES:
        raise vol.Invalid(
            f"неизвестный action type {type_!r}. "
            f"Поддерживаемые в YAML: {sorted(_KNOWN_YAML_ACTION_TYPES)}"
        )
    return value


# Schema per action-type. Воспаламбда не работает с YAML, поэтому
# делаем отдельные schemas.
_TTS_SCHEMA = vol.Schema(
    {
        vol.Required("type"): "tts",
        vol.Required("phrase"): vol.All(str, vol.Length(min=1)),
        vol.Required("device_ids"): vol.All([str], vol.Length(min=1)),
    }
)

_DEVICE_COMMAND_ATTR_SCHEMA = vol.Schema(
    {
        vol.Required("key"): str,
        vol.Required("type"): vol.In(["BOOL", "INTEGER", "STRING", "ENUM", "COLOR", "FLOAT"]),
        vol.Optional("bool_value"): bool,
        vol.Optional("integer_value"): vol.Any(int, str),
        vol.Optional("string_value"): str,
        vol.Optional("enum_value"): str,
        vol.Optional("float_value"): vol.Any(int, float),
        vol.Optional("color_value"): dict,
    },
    extra=vol.ALLOW_EXTRA,
)

_DEVICE_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("type"): "device_command",
        vol.Required("device_id"): vol.All(str, vol.Length(min=1)),
        vol.Required("attributes"): vol.All([_DEVICE_COMMAND_ATTR_SCHEMA], vol.Length(min=1)),
    }
)

_HA_EVENT_SCHEMA = vol.Schema({vol.Required("type"): "ha_event_only"})


def _action_dispatcher(value: Any) -> dict[str, Any]:
    """Sub-schema-disptacher: per type → конкретный schema."""
    if not isinstance(value, dict):
        raise vol.Invalid("action должен быть dict")
    type_ = value.get("type")
    if type_ == "tts":
        return _TTS_SCHEMA(value)
    if type_ == "device_command":
        return _DEVICE_COMMAND_SCHEMA(value)
    if type_ == "ha_event_only":
        return _HA_EVENT_SCHEMA(value)
    raise vol.Invalid(f"неизвестный action type {type_!r}")


# Slug-validator (если задан) либо None (автогенерация из name).
_SLUG_SCHEMA = vol.All(str, vol.Match(_SLUG_RE))


_INTENT_SCHEMA = vol.Schema(
    {
        vol.Optional("slug"): _SLUG_SCHEMA,
        vol.Required("name"): vol.All(str, vol.Length(min=1)),
        vol.Required("phrases"): vol.All([str], vol.Length(min=1)),
        vol.Optional("enabled", default=True): bool,
        vol.Optional("description", default=""): str,
        vol.Required("actions"): vol.All([_action_dispatcher], vol.Length(min=1)),
    }
)

INTENTS_SCHEMA = vol.Schema([_INTENT_SCHEMA])


def _slugify(name: str) -> str:
    """Сгенерировать slug из name (Latin transliteration + lower).

    Базовая транслитерация Cyrillic → Latin, потом lowercase + замена
    всего non-alphanum на ``_``, ужатие повторяющихся ``_``.
    """
    cyr_to_lat = {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "yo",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
    s = name.lower()
    s = "".join(cyr_to_lat.get(c, c) for c in s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "intent"


def load_intents_from_config(raw: list[dict[str, Any]]) -> list[IntentSpec]:
    """Распарсить already-validated YAML-список в `IntentSpec`-ы.

    Args:
        raw: список dict'ов, уже прошедших ``INTENTS_SCHEMA``.

    Returns:
        Список IntentSpec с ``raw_extras["yaml_slug"]`` (стабильный
        machine handle для reconciler'а).

    Raises:
        ValueError: если в списке два intent'а с одинаковым slug.
    """
    seen_slugs: dict[str, str] = {}
    specs: list[IntentSpec] = []

    for entry in raw:
        name = entry["name"]
        slug = entry.get("slug") or _slugify(name)
        if slug in seen_slugs:
            raise ValueError(
                f"YAML: duplicate slug {slug!r}: "
                f"first used by {seen_slugs[slug]!r}, second by {name!r}. "
                f"Задайте уникальный явный slug в одном из intent-ов."
            )
        seen_slugs[slug] = name

        actions = [
            IntentAction(
                type=a["type"],
                data={k: v for k, v in a.items() if k != "type"},
            )
            for a in entry["actions"]
        ]

        spec = IntentSpec(
            id=None,  # будет заполнен после первого create
            name=name,
            phrases=list(entry["phrases"]),
            actions=actions,
            enabled=entry["enabled"],
            description=entry.get("description", ""),
            raw_extras={"yaml_slug": slug},
        )
        specs.append(spec)

    _LOGGER.debug(
        "YAML loader: parsed %d intent(s): %s",
        len(specs),
        [s.raw_extras.get("yaml_slug") for s in specs],
    )
    return specs


__all__ = [
    "INTENTS_SCHEMA",
    "load_intents_from_config",
]
