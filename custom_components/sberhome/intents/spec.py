"""IntentSpec & IntentAction — HA-side abstraction для voice intents.

Не зависит от Sber wire-формата. Encoder в `intents/encoder.py` отвечает
за конвертацию IntentSpec ↔ Sber `ScenarioDto`. Если Sber меняет shape
своих сценариев — мы меняем encoder, IntentSpec остаётся стабильным
для UI.

Forward-compat: незнакомые Sber-поля складываются в `raw_extras` и
мерджатся обратно при `update()`. Это значит:
- Sber добавит новое поле в ScenarioDto → не упадём.
- Пользователь создал сценарий с action типа который мы не знаем
  (`regime_command`, новый task type) → UI пометит как
  «complex / read-only», но `raw_extras` содержит весь оригинал
  — при сохранении ничего не потеряется.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class IntentAction:
    """Одно действие в intent'е.

    `type` — discriminator. Конкретный shape `data` определяется
    `intents.registry.ACTION_TYPES[type]`.

    Примеры:
        IntentAction(type="ha_event_only", data={})
        IntentAction(type="tts", data={"phrase": "...", "device_ids": [...]})
        IntentAction(type="device_command", data={
            "device_id": "...",
            "attributes": [{"key": "on_off", "type": "BOOL", "bool_value": True}],
        })

    `unknown` — флаг от encoder'а: action имеет тип не из registry
    (например native `regime_command`). UI показывает его read-only,
    save сохраняет через `raw_extras` сценария.
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    unknown: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": dict(self.data), "unknown": self.unknown}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> IntentAction:
        return cls(
            type=str(raw.get("type", "ha_event_only")),
            data=dict(raw.get("data") or {}),
            unknown=bool(raw.get("unknown", False)),
        )


@dataclass(slots=True)
class IntentSpec:
    """Voice intent — то что пользователь видит в UI вкладки «Voice Intents».

    Маппится 1:1 на Sber-сценарий, но HA-friendly: phrases собраны в
    плоский list независимо от вложенности conditions, actions
    разложены по нашему registry, незнакомые Sber-поля убраны в
    `raw_extras`.

    Lifecycle:
    - **id=None** — новый intent (UI Create New). При save POST'ится в
      Sber и intent.id заполнится id'ом созданного сценария.
    - **id="..."** — существующий. PUT обновляет, DELETE удаляет.

    `is_ha_managed` рассчитывается encoder'ом: True если ВСЕ actions
    имеют известные типы (нет `unknown=True`). False — есть незнакомое
    действие (UI покажет как read-only complex scenario).

    `last_fired_at` populated IntentService'ом из event-log на read,
    None если событий ещё не было.
    """

    id: str | None = None
    name: str = ""
    phrases: list[str] = field(default_factory=list)
    actions: list[IntentAction] = field(default_factory=list)
    enabled: bool = True
    description: str = ""
    last_fired_at: str | None = None
    is_ha_managed: bool = True
    raw_extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phrases": list(self.phrases),
            "actions": [a.to_dict() for a in self.actions],
            "enabled": self.enabled,
            "description": self.description,
            "last_fired_at": self.last_fired_at,
            "is_ha_managed": self.is_ha_managed,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> IntentSpec:
        return cls(
            id=raw.get("id"),
            name=str(raw.get("name", "")),
            phrases=[str(p) for p in (raw.get("phrases") or []) if str(p).strip()],
            actions=[IntentAction.from_dict(a) for a in (raw.get("actions") or [])],
            enabled=bool(raw.get("enabled", True)),
            description=str(raw.get("description", "")),
            last_fired_at=raw.get("last_fired_at"),
            is_ha_managed=bool(raw.get("is_ha_managed", True)),
            raw_extras=dict(raw.get("raw_extras") or {}),
        )


# ---------------------------------------------------------------------------
# UI form schema — schema-driven dynamic field rendering
# ---------------------------------------------------------------------------


# Allowed UI-field types. Frontend знает renderer для каждого:
#   text         — <input type="text">
#   multitext    — список строк (chips)
#   number       — <input type="number">
#   bool         — <ha-switch>
#   enum         — <select>
#   device_picker — picker устройств (опционально фильтр по category)
#   scenario_picker — picker сценариев (для cross-references)
FieldType = str


@dataclass(slots=True, frozen=True)
class FieldSpec:
    """Одно поле в форме action data.

    Используется UI'ем для динамической генерации формы. Добавили
    новое action_type с новым полем — никаких изменений в JS не
    нужно, если тип поля уже среди известных рендереров. Нужен
    новый тип (slider, color_picker и т.п.) — добавляется один
    рендерер на фронте, FieldSpec'ы могут его сразу использовать.
    """

    key: str
    type: FieldType
    label: str
    required: bool = False
    multiple: bool = False
    default: Any = None
    options: tuple[str, ...] | None = None  # для type=enum
    help_text: str = ""
    # Hint для device_picker — показывать только устройства этих категорий.
    # None = все категории. Пример: ("sber_speaker",) для TTS-action'а.
    device_category: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "key": self.key,
            "type": self.type,
            "label": self.label,
            "required": self.required,
            "multiple": self.multiple,
        }
        if self.default is not None:
            out["default"] = self.default
        if self.options is not None:
            out["options"] = list(self.options)
        if self.help_text:
            out["help_text"] = self.help_text
        if self.device_category is not None:
            out["device_category"] = list(self.device_category)
        return out


__all__ = ["FieldSpec", "FieldType", "IntentAction", "IntentSpec"]
