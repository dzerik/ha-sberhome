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
        type="template",
        label="Фраза для озвучивания",
        required=True,
        help_text=(
            "Sber произнесёт через выбранные колонки. Поддерживаются "
            "Jinja2-шаблоны Home Assistant — значения подставятся "
            "перед каждым произнесением."
        ),
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
        type="attr_form",
        label="Что задать",
        help_text="Отметьте атрибуты и задайте значения — форма по возможностям устройства.",
        required=True,
    ),
)


def _encode_device_command(data: dict[str, Any]) -> list[dict[str, Any]]:
    device_id = str(data.get("device_id", "")).strip()
    attrs = data.get("attributes") or []
    if not device_id or not isinstance(attrs, list) or not attrs:
        return []
    # Sber ждёт desired_state как [{state: <AttributeValue>, relative, mode}],
    # а не голый список AttributeValue (проверено live). Оборачиваем каждый
    # атрибут в RANGE_SET (задать значение). Уже обёрнутые не трогаем.
    desired: list[dict[str, Any]] = []
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        if "state" in attr and ("mode" in attr or "relative" in attr):
            desired.append(attr)  # forward-compat: уже обёрнут — не трогаем
            continue
        # UI-only sentinel `_mode` определяет режим; в wire его НЕ пускаем.
        ui_mode = attr.get("_mode")
        state = {k: v for k, v in attr.items() if not k.startswith("_")}
        if ui_mode == "INVERT":
            desired.append({"state": state, "relative": True, "mode": "INVERT"})
        else:
            desired.append({"state": state, "relative": False, "mode": "RANGE_SET"})
    return [
        {
            "type": "DEVICE_COMMAND",
            "device_command_data": {
                "device_id": device_id,
                "desired_state": desired,
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
    # Разворачиваем {state, relative, mode} обратно в голый AttributeValue,
    # чтобы редактор/форма работали с плоским attr (encode обернёт снова).
    # Режим INVERT (переключить) помечаем UI-only sentinel'ом `_mode`,
    # чтобы round-trip не деградировал INVERT в RANGE_SET.
    attributes: list[Any] = []
    for item in dc.get("desired_state") or []:
        if isinstance(item, dict) and "state" in item:
            st = dict(item.get("state") or {})
            if item.get("mode") == "INVERT" or item.get("relative"):
                st["_mode"] = "INVERT"
            attributes.append(st)
        else:
            attributes.append(item)
    return (
        IntentAction(
            type="device_command",
            data={
                "device_id": str(dc.get("device_id", "")),
                "attributes": attributes,
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


# ---- speaker_text (голый HEAD_DIALOG_COMMAND) ----
# Колонка ВЫПОЛНЯЕТ текст как голосовую команду ассистенту («Расскажи анекдот»,
# «Какая погода»). Каноничная форма «сказать сейчас» — ГОЛЫЙ HEAD_DIALOG_COMMAND
# на верхнем уровне tasks[] (проверено живьём: приложение Sber использует именно
# её, и она корректно срабатывает по голосу). Обёртка REGIME_COMMAND — только
# для мультипериодных «по утрам/вечерам»; такие остаются unknown/read-only.
_SPEAKER_TEXT_FIELDS = (
    FieldSpec(
        key="device_id",
        type="device_picker",
        label="Колонка",
        required=True,
        device_category=("sber_speaker",),
    ),
    FieldSpec(
        key="text",
        type="text",
        label="Текст команды ассистенту",
        required=True,
        help_text="Колонка выполнит это как голосовую команду («Расскажи анекдот»).",
    ),
)


def _encode_speaker_text(data: dict[str, Any]) -> list[dict[str, Any]]:
    device_id = str(data.get("device_id", "")).strip()
    text = str(data.get("text", "")).strip()
    if not device_id or not text:
        return []
    return [
        {
            "type": "HEAD_DIALOG_COMMAND",
            "head_dialog_command_task_data": {
                "device_id": device_id,
                "text": text,
                "content_id": "",
                "cinema": "",
                "action_type": "",
                "content": "",
            },
        }
    ]


def _decode_speaker_text(
    tasks: list[dict[str, Any]],
) -> tuple[IntentAction | None, list[dict[str, Any]]]:
    leftover: list[dict[str, Any]] = []
    matched: IntentAction | None = None
    for t in tasks:
        # Голый top-level HEAD_DIALOG_COMMAND — наша каноничная форма.
        # REGIME_COMMAND (мультипериод) НЕ забираем → остаётся unknown.
        if matched is None and t.get("type") == "HEAD_DIALOG_COMMAND":
            hd = t.get("head_dialog_command_task_data") or {}
            matched = IntentAction(
                type="speaker_text",
                data={
                    "device_id": str(hd.get("device_id", "")),
                    "text": str(hd.get("text", "")),
                },
            )
            continue
        leftover.append(t)
    if matched is None:
        return None, tasks
    return matched, leftover


# ---- scenario_status (SCENARIO_SET_ACTIVE) ----
_SCENARIO_STATUS_FIELDS = (
    FieldSpec(
        key="scenario_id",
        type="scenario_picker",
        label="Сценарий",
        required=True,
        help_text="Какой сценарий включить/выключить.",
    ),
    FieldSpec(
        key="active",
        type="bool",
        label="Сделать активным",
        default=True,
    ),
)


def _encode_scenario_status(data: dict[str, Any]) -> list[dict[str, Any]]:
    scenario_id = str(data.get("scenario_id", "")).strip()
    if not scenario_id:
        return []
    return [
        {
            "type": "SCENARIO_SET_ACTIVE",
            "scenario_set_active_task_data": {
                "scenario_id": scenario_id,
                "active": bool(data.get("active", True)),
            },
        }
    ]


def _decode_scenario_status(
    tasks: list[dict[str, Any]],
) -> tuple[IntentAction | None, list[dict[str, Any]]]:
    leftover: list[dict[str, Any]] = []
    matched: IntentAction | None = None
    for t in tasks:
        if matched is None and t.get("type") == "SCENARIO_SET_ACTIVE":
            sd = t.get("scenario_set_active_task_data") or {}
            matched = IntentAction(
                type="scenario_status",
                data={
                    "scenario_id": str(sd.get("scenario_id", "")),
                    "active": bool(sd.get("active", True)),
                },
            )
            continue
        leftover.append(t)
    if matched is None:
        return None, tasks
    return matched, leftover


# ---- sms (SEND_SMS_COMMAND) ----
# Sber сам заполняет scenario_id/scenario_name/trigger_device_id при срабатывании.
# UI-полей нет; decode кладёт наблюдаемый task_data в data['_raw'] для lossless.
def _encode_sms(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("_raw")
    payload = (
        dict(raw)
        if isinstance(raw, dict)
        else {"scenario_id": "", "scenario_name": "", "trigger_device_id": ""}
    )
    return [{"type": "SEND_SMS_COMMAND", "send_sms_command_task_data": payload}]


def _decode_sms(
    tasks: list[dict[str, Any]],
) -> tuple[IntentAction | None, list[dict[str, Any]]]:
    leftover: list[dict[str, Any]] = []
    matched: IntentAction | None = None
    for t in tasks:
        if matched is None and t.get("type") == "SEND_SMS_COMMAND":
            matched = IntentAction(
                type="sms",
                data={"_raw": dict(t.get("send_sms_command_task_data") or {})},
            )
            continue
        leftover.append(t)
    if matched is None:
        return None, tasks
    return matched, leftover


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
        type="speaker_text",
        ui_label="Команда ассистенту текстом (на колонку)",
        ui_fields=_SPEAKER_TEXT_FIELDS,
        encode=_encode_speaker_text,
        decode=_decode_speaker_text,
    ),
    ActionRegistration(
        type="scenario_status",
        ui_label="Включить/выключить другой сценарий",
        ui_fields=_SCENARIO_STATUS_FIELDS,
        encode=_encode_scenario_status,
        decode=_decode_scenario_status,
    ),
    ActionRegistration(
        type="sms",
        ui_label="Отправить SMS-уведомление",
        ui_fields=(),
        encode=_encode_sms,
        decode=_decode_sms,
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
