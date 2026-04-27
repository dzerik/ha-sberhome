"""Voice intents subsystem — UI-managed Sber-сценарии в HA.

Public API:
- `IntentSpec`, `IntentAction`, `FieldSpec` — data classes для UI.
- `ActionRegistration`, `register_action`, `get_action`, `list_actions`,
  `schema_dict` — extensibility hub.
- `decode_scenario`, `encode_scenario` — IntentSpec ↔ Sber wire.
- `IntentService` — high-level CRUD над `coordinator.client.scenarios`.
"""

from __future__ import annotations

from .encoder import DEFAULT_IMAGE, DEFAULT_TIMEZONE, decode_scenario, encode_scenario
from .registry import (
    ActionRegistration,
    get_action,
    list_actions,
    register_action,
    schema_dict,
)
from .service import IntentService
from .spec import FieldSpec, FieldType, IntentAction, IntentSpec

__all__ = [
    "DEFAULT_IMAGE",
    "DEFAULT_TIMEZONE",
    "ActionRegistration",
    "FieldSpec",
    "FieldType",
    "IntentAction",
    "IntentService",
    "IntentSpec",
    "decode_scenario",
    "encode_scenario",
    "get_action",
    "list_actions",
    "register_action",
    "schema_dict",
]
