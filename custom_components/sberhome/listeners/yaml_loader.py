"""YAML loader для listeners — `sberhome.listeners` секция.

Парсит блок::

    sberhome:
      listeners:
        - slug: morning              # optional, autogen из name
          name: "Утренние сценарии"
          enabled: true              # optional, default true
          description: "..."         # optional
          filter:                    # required, минимум одно поле
            trigger_type: TIME       # string или list
            scenario_name: "..."     # optional
            scenario_id: "..."       # optional
            home: "Мой дом"           # optional (или home_id)
            home_id: "..."           # optional

→ список :class:`ListenerSpec` с filter.home_id содержащим либо UUID
(если в YAML был ``home_id``), либо имя дома (если был ``home``)
— фактический резолв `home` → UUID происходит в ``__init__.py``
после ``state_cache.refresh()``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol

from ..yaml_utils import slugify
from .spec import ListenerFilter, ListenerSpec

_LOGGER = logging.getLogger(__name__)

# Принятые значения из start_scenario_reason.type — см.
# coordinator._extract_trigger_type, ScenarioConditionTypeDto.
_VALID_TRIGGER_TYPES = frozenset(
    {
        "PHRASES",
        "TIME",
        "DEVICE",
        "GEO_TIME",
        "CONDITIONS",
        "CHECK_DEVICE",
        "CHECK_SCENARIO",
        "UNDEFINED_TYPE",
    }
)


def _validate_trigger_type(value: Any) -> list[str]:
    """trigger_type: string или list[str] → list[str], all из _VALID_TRIGGER_TYPES."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise vol.Invalid(
            f"trigger_type должен быть str или list[str], получено {type(value).__name__}"
        )
    for item in items:
        if not isinstance(item, str):
            raise vol.Invalid(f"trigger_type item должен быть str, получено {item!r}")
        if item not in _VALID_TRIGGER_TYPES:
            raise vol.Invalid(
                f"неизвестный trigger_type {item!r}. Поддерживаемые: {sorted(_VALID_TRIGGER_TYPES)}"
            )
    return items


def _validate_filter(value: Any) -> dict[str, Any]:
    """filter: dict, минимум одно поле — анти-паттерн пустой filter."""
    if not isinstance(value, dict):
        raise vol.Invalid("filter должен быть dict")
    if not value:
        raise vol.Invalid(
            "filter не может быть пустым — нужно задать хотя бы одно поле "
            "(trigger_type / scenario_name / scenario_id / home / home_id)"
        )
    return value


_FILTER_SCHEMA = vol.Schema(
    {
        vol.Optional("trigger_type"): _validate_trigger_type,
        vol.Optional("scenario_name"): vol.All(str, vol.Length(min=1)),
        vol.Optional("scenario_id"): vol.All(str, vol.Length(min=1)),
        vol.Optional("home"): vol.All(str, vol.Length(min=1)),
        vol.Optional("home_id"): vol.All(str, vol.Length(min=1)),
    }
)


# Slug: lowercase, цифры/буквы/_/-.
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_SLUG_SCHEMA = vol.All(str, vol.Match(_SLUG_RE))


_LISTENER_SCHEMA = vol.Schema(
    {
        vol.Optional("slug"): _SLUG_SCHEMA,
        vol.Required("name"): vol.All(str, vol.Length(min=1)),
        vol.Optional("enabled", default=True): bool,
        vol.Optional("description", default=""): str,
        vol.Required("filter"): vol.All(_validate_filter, _FILTER_SCHEMA),
    }
)


LISTENERS_SCHEMA = vol.Schema([_LISTENER_SCHEMA])


def load_listeners_from_config(
    raw: list[dict[str, Any]],
    *,
    reserved_slugs: set[str],
) -> list[ListenerSpec]:
    """Распарсить already-validated YAML-список в `ListenerSpec`-ы.

    Args:
        raw: список dict'ов, прошедших ``LISTENERS_SCHEMA``.
        reserved_slugs: slugs уже занятые intents (collision detection).
            Listener со slug из этого множества будет создан, но
            ``enabled=False``, с warning в лог.

    Returns:
        Список ``ListenerSpec``. Filter.home_id содержит либо UUID
        (если в YAML был ``home_id``), либо имя дома (если был ``home``)
        — фактический резолв происходит в ``__init__.py``.

    Raises:
        ValueError: если в самом ``raw`` дубликат slug между listeners.
    """
    seen_slugs: dict[str, str] = {}
    specs: list[ListenerSpec] = []

    for entry in raw:
        name = entry["name"]
        slug = entry.get("slug") or slugify(name)

        if slug in seen_slugs:
            raise ValueError(
                f"YAML listeners: duplicate slug {slug!r}: "
                f"first used by {seen_slugs[slug]!r}, second by {name!r}"
            )
        seen_slugs[slug] = name

        enabled = entry["enabled"]
        if slug in reserved_slugs:
            _LOGGER.warning(
                "YAML listener %r uses slug %r which is already reserved "
                "(probably by an intent). Listener disabled.",
                name,
                slug,
            )
            enabled = False

        f = entry["filter"]
        trigger_types: frozenset[str] | None = None
        if "trigger_type" in f:
            trigger_types = frozenset(f["trigger_type"])

        # home/home_id: храним сырое значение, резолв позже.
        home_id_raw = f.get("home_id") or f.get("home")

        filter_obj = ListenerFilter(
            trigger_types=trigger_types,
            scenario_name=f.get("scenario_name"),
            scenario_id=f.get("scenario_id"),
            home_id=home_id_raw,
        )

        specs.append(
            ListenerSpec(
                slug=slug,
                name=name,
                filter=filter_obj,
                enabled=enabled,
                description=entry.get("description", ""),
            )
        )

    _LOGGER.debug(
        "YAML loader: parsed %d listener(s): %s",
        len(specs),
        [s.slug for s in specs],
    )
    return specs
