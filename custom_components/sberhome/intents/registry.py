"""Action registry для voice intents — extensibility hub.

Каждый action_type регистрируется здесь как `ActionRegistration`:
- `ui_label` / `ui_fields` — для UI-формы
- `encode(action_data, context)` → `list[ScenarioTaskDto-as-dict]` — Sber wire
- `decode(task_dicts)` → `(IntentAction, leftover_tasks)` — обратное.
  Encoder вызывает все зарегистрированные decoder'ы по очереди; первый
  matching берёт «свои» tasks, остальные передаются дальше. Незнакомые
  tasks остаются в `IntentSpec.raw_extras['steps'][i]['tasks']` и при
  update мерджатся обратно (forward-compat).

Добавление нового action type:
1. Написать encode/decode pair (~30 строк).
2. Зарегистрировать в `_DEFAULT_ACTIONS`.
3. UI получит новую option в форме автоматически.

Никаких других правок ни в backend, ни в frontend.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .spec import FieldSpec, IntentAction


@dataclass(slots=True, frozen=True)
class ActionRegistration:
    """One row in the action type registry.

    Attributes:
        type: discriminator string, e.g. ``"tts"``, ``"device_command"``.
            Должен быть стабильным — он сохраняется в IntentSpec и UI'е.
        ui_label: что показать в dropdown «Тип действия» в UI.
        ui_fields: список FieldSpec для динамической формы.
        encode: action_data → list[task-dict для Sber wire]. Один action
            может разворачиваться в несколько Sber-tasks (например TTS на
            два устройства = одна Sber-task с двумя device_ids в
            pronounce_data, encode возвращает [single_task]).
        decode: список Sber-tasks → (IntentAction | None, leftover).
            Возвращает (None, tasks) если ни один из tasks не наш.
            Иначе — берёт matching, возвращает leftover (потомительные
            decoder'ы получат то что осталось).
    """

    type: str
    ui_label: str
    ui_fields: tuple[FieldSpec, ...]
    encode: Callable[[dict[str, Any]], list[dict[str, Any]]]
    decode: Callable[
        [list[dict[str, Any]]],
        tuple[IntentAction | None, list[dict[str, Any]]],
    ]


# ---------------------------------------------------------------------------
# Built-in action implementations
# ---------------------------------------------------------------------------


# ---- ha_event_only ----
def _encode_ha_event_only(_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Sber-сценарий без actions — просто phrase trigger без дальнейшего
    выполнения чего-либо. HA event всё равно прилетит через scenario_widgets
    push (сценарий зарегистрирован → срабатывает → event log → HA bus).

    Sber требует хотя бы один step, но tasks может быть пустым. На прод
    проверено — POST с steps=[{tasks:[],condition:...}] принимается.
    """
    return []  # tasks=[] для этого action


def _decode_ha_event_only(
    tasks: list[dict[str, Any]],
) -> tuple[IntentAction | None, list[dict[str, Any]]]:
    """Если tasks пуст — это «голый» phrase-only сценарий."""
    if not tasks:
        return IntentAction(type="ha_event_only"), []
    return None, tasks


# ---- tts (PRONOUNCE_COMMAND) ----
_TTS_FIELDS = (
    FieldSpec(
        key="phrase",
        type="text",
        label="Фраза для озвучивания",
        required=True,
        help_text="Sber произнесёт через выбранные колонки",
    ),
    FieldSpec(
        key="device_ids",
        type="device_picker",
        label="Колонка",
        required=True,
        multiple=True,
        device_category=("sber_speaker",),
        help_text="Можно выбрать несколько; включая колонки не подключённые в HA",
    ),
)


def _encode_tts(data: dict[str, Any]) -> list[dict[str, Any]]:
    phrase = str(data.get("phrase", "")).strip()
    device_ids = [str(x) for x in (data.get("device_ids") or []) if str(x).strip()]
    if not phrase or not device_ids:
        return []  # invalid action — UI должен валидировать заранее
    return [
        {
            "type": "PRONOUNCE_COMMAND",
            "pronounce_data": {
                "device_ids": device_ids,
                "phrase": phrase,
            },
        }
    ]


def _decode_tts(
    tasks: list[dict[str, Any]],
) -> tuple[IntentAction | None, list[dict[str, Any]]]:
    leftover = []
    matched: dict[str, Any] | None = None
    for t in tasks:
        if matched is None and t.get("type") == "PRONOUNCE_COMMAND":
            matched = t
            continue
        leftover.append(t)
    if matched is None:
        return None, tasks
    pron = matched.get("pronounce_data") or {}
    return (
        IntentAction(
            type="tts",
            data={
                "phrase": str(pron.get("phrase", "")),
                "device_ids": list(pron.get("device_ids") or []),
            },
        ),
        leftover,
    )


# ---- device_command ----
_DEVICE_COMMAND_FIELDS = (
    FieldSpec(
        key="device_id",
        type="device_picker",
        label="Устройство",
        required=True,
    ),
    FieldSpec(
        key="attributes",
        type="multitext",
        label="Атрибуты JSON",
        help_text=(
            'Список AttributeValueDto (например [{"key":"on_off","type":"BOOL","bool_value":true}])'
        ),
        required=True,
    ),
)


def _encode_device_command(data: dict[str, Any]) -> list[dict[str, Any]]:
    device_id = str(data.get("device_id", "")).strip()
    attrs = data.get("attributes") or []
    if not device_id or not isinstance(attrs, list) or not attrs:
        return []
    return [
        {
            "type": "DEVICE_COMMAND",
            "device_command_data": {
                "device_id": device_id,
                "desired_state": attrs,
            },
        }
    ]


def _decode_device_command(
    tasks: list[dict[str, Any]],
) -> tuple[IntentAction | None, list[dict[str, Any]]]:
    leftover = []
    matched: dict[str, Any] | None = None
    for t in tasks:
        if matched is None and t.get("type") == "DEVICE_COMMAND":
            matched = t
            continue
        leftover.append(t)
    if matched is None:
        return None, tasks
    dc = matched.get("device_command_data") or {}
    return (
        IntentAction(
            type="device_command",
            data={
                "device_id": str(dc.get("device_id", "")),
                "attributes": list(dc.get("desired_state") or []),
            },
        ),
        leftover,
    )


# ---- trigger_notify (push notification в мобилку Sber) ----
def _encode_trigger_notify(_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Sber-сценарий шлёт push-нотификацию в мобилу. Payload пустой."""
    return [{"type": "TRIGGER_NOTIFY_COMMAND"}]


def _decode_trigger_notify(
    tasks: list[dict[str, Any]],
) -> tuple[IntentAction | None, list[dict[str, Any]]]:
    leftover = []
    matched = False
    for t in tasks:
        if not matched and t.get("type") == "TRIGGER_NOTIFY_COMMAND":
            matched = True
            continue
        leftover.append(t)
    if not matched:
        return None, tasks
    return IntentAction(type="trigger_notify", data={}), leftover


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_DEFAULT_ACTIONS: tuple[ActionRegistration, ...] = (
    # Order matters для decode: ha_event_only оставляем последним —
    # он матчит «нет tasks», пустой leftover.
    ActionRegistration(
        type="tts",
        ui_label="Произнести через колонку (Sber TTS)",
        ui_fields=_TTS_FIELDS,
        encode=_encode_tts,
        decode=_decode_tts,
    ),
    ActionRegistration(
        type="device_command",
        ui_label="Команда устройству",
        ui_fields=_DEVICE_COMMAND_FIELDS,
        encode=_encode_device_command,
        decode=_decode_device_command,
    ),
    ActionRegistration(
        type="trigger_notify",
        ui_label="Push-уведомление в Sber-приложение",
        ui_fields=(),
        encode=_encode_trigger_notify,
        decode=_decode_trigger_notify,
    ),
    ActionRegistration(
        type="ha_event_only",
        ui_label="Только HA event (без действий в Sber)",
        ui_fields=(),
        encode=_encode_ha_event_only,
        decode=_decode_ha_event_only,
    ),
)


_REGISTRY: dict[str, ActionRegistration] = {a.type: a for a in _DEFAULT_ACTIONS}


def get_action(action_type: str) -> ActionRegistration | None:
    """Получить регистрацию по типу или None."""
    return _REGISTRY.get(action_type)


def list_actions() -> list[ActionRegistration]:
    """Все зарегистрированные actions в стабильном порядке."""
    return list(_DEFAULT_ACTIONS)


def register_action(reg: ActionRegistration) -> None:
    """Добавить кастомный action_type. Используется в тестах и плагинах."""
    _REGISTRY[reg.type] = reg


def schema_dict() -> list[dict[str, Any]]:
    """Сериализованная schema для UI (через WS endpoint)."""
    return [
        {
            "type": a.type,
            "ui_label": a.ui_label,
            "fields": [f.to_dict() for f in a.ui_fields],
        }
        for a in _DEFAULT_ACTIONS
    ]


__all__ = [
    "ActionRegistration",
    "get_action",
    "list_actions",
    "register_action",
    "schema_dict",
]
