"""IntentEncoder — IntentSpec ↔ Sber `ScenarioDto` (wire JSON).

Single source of truth для:
- **decode**: парсим Sber-сценарий из живого ответа REST API в IntentSpec.
  Известные actions через `registry`, незнакомые — `IntentAction(unknown=True)`.
  Все Sber-специфичные поля (image, meta, account_id, requires, …) уезжают
  в `IntentSpec.raw_extras`.
- **encode**: собираем wire-JSON для POST/PUT. Тащим обратно `raw_extras`,
  чтобы не потерять незнакомые поля при обновлении.

Структура wire (восстановлена live + декомпил):

```jsonc
{
  "name": "...", "timezone": "...", "is_active": true, "image": "...",
  "steps": [{
    "tasks": [{
      "type": "PRONOUNCE_COMMAND" | "DEVICE_COMMAND" | "TRIGGER_NOTIFY_COMMAND" | ...,
      "pronounce_data" | "device_command_data" | ...
    }],
    "condition": {
      "type": "CONDITIONS",
      "nested_conditions_data": {
        "conditions": [{
          "type": "PHRASES",
          "phrases_data": {"phrases": [...]}
        }, ...],
        "relation": "OR"
      }
    }
  }]
}
```

Phrases могут лежать как непосредственно в `condition.phrases_data.phrases`
(минимально — один phrase-condition без обёртки), так и через
`nested_conditions_data.conditions[].phrases_data.phrases`. Decoder
поддерживает оба варианта.
"""

from __future__ import annotations

from typing import Any

from .registry import get_action, list_actions
from .spec import IntentAction, IntentSpec

# Default timezone — берётся из config_entry если отличается. Sber отвергает
# create без timezone, поэтому ставим разумный дефолт.
DEFAULT_TIMEZONE = "Europe/Moscow"

# Sber отказывает в create без image. Используем дефолтный URL который наблюдаем
# у штатно созданных сценариев.
DEFAULT_IMAGE = (
    "https://img.iot.sberdevices.ru/p/q100/e7/a4/"
    "e715a4ce20e06797be5743f2f489e5441630170f214118d86297a6ac818d018a"
)

# Поля верхнего уровня которые мы парсим в IntentSpec — остальное в raw_extras.
_KNOWN_TOP_FIELDS = frozenset(
    {
        "id",
        "name",
        "is_active",
        "steps",
        # эти поля важны но не маппятся на UI напрямую — храним в raw_extras
        # для round-trip update'ов
    }
)


# ---------------------------------------------------------------------------
# Decode: ScenarioDto-as-dict → IntentSpec
# ---------------------------------------------------------------------------


def decode_scenario(scenario: dict[str, Any]) -> IntentSpec:
    """Sber wire JSON → IntentSpec.

    Все unknown поля сохраняются в spec.raw_extras для round-trip
    forward-compat. Phrases собираются плоским списком из всех условий
    типа PHRASES в дереве (включая nested).
    """
    spec_id = scenario.get("id")
    name = str(scenario.get("name") or "").strip()
    enabled = bool(scenario.get("is_active", True))

    steps = scenario.get("steps") or []
    phrases: list[str] = []
    actions: list[IntentAction] = []
    is_ha_managed = True

    # Фразы и actions — agg по всем steps. На практике обычно 1 step.
    for step in steps:
        if not isinstance(step, dict):
            continue
        phrases.extend(_collect_phrases(step.get("condition")))
        step_actions, step_is_ha = _decode_tasks(step.get("tasks") or [])
        actions.extend(step_actions)
        if not step_is_ha:
            is_ha_managed = False

    # Если actions пусты (пустой tasks[]) — это ha_event_only.
    if not actions:
        actions = [IntentAction(type="ha_event_only")]

    # Forward-compat: всё остальное — в raw_extras.
    raw_extras = {k: v for k, v in scenario.items() if k not in _KNOWN_TOP_FIELDS}

    return IntentSpec(
        id=spec_id if spec_id else None,
        name=name,
        phrases=_dedup_keep_order(phrases),
        actions=actions,
        enabled=enabled,
        is_ha_managed=is_ha_managed,
        raw_extras=raw_extras,
    )


def _collect_phrases(condition: Any) -> list[str]:
    """Рекурсивно собрать все строки phrases из условия."""
    if not isinstance(condition, dict):
        return []
    out: list[str] = []
    cond_type = str(condition.get("type") or "").upper()
    if cond_type == "PHRASES":
        data = condition.get("phrases_data") or {}
        out.extend(str(p) for p in (data.get("phrases") or []))
    nested = condition.get("nested_conditions_data") or {}
    for sub in nested.get("conditions") or []:
        out.extend(_collect_phrases(sub))
    return out


def _decode_tasks(
    tasks: list[Any],
) -> tuple[list[IntentAction], bool]:
    """Список Sber-tasks → список IntentAction.

    Прогоняем все зарегистрированные decoder'ы по очереди (в порядке
    `list_actions()`). Каждый matching забирает «свои» tasks; leftover
    идёт следующим. То что не разобрано ни одним decoder'ом
    оборачивается в IntentAction(type="<sber_task_type>", unknown=True).

    Returns:
        (actions, is_ha_managed) — is_ha_managed=False если есть unknown.
    """
    remaining = [t for t in tasks if isinstance(t, dict)]
    out: list[IntentAction] = []
    is_ha = True

    # Не дёргаем ha_event_only здесь — он матчит "нет tasks", а у нас
    # tasks есть. Дёрнем только если remaining=[] на выходе.
    for reg in list_actions():
        if reg.type == "ha_event_only":
            continue
        # Один тип может встретиться несколько раз — крутим пока match.
        while True:
            decoded, leftover = reg.decode(remaining)
            if decoded is None:
                break
            out.append(decoded)
            remaining = leftover
            if not remaining:
                break
        if not remaining:
            break

    # Что осталось — unknown.
    for t in remaining:
        out.append(
            IntentAction(
                type=str(t.get("type") or "unknown"),
                data={"raw": t},
                unknown=True,
            )
        )
        is_ha = False

    return out, is_ha


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


# ---------------------------------------------------------------------------
# Encode: IntentSpec → Sber wire dict (POST/PUT body)
# ---------------------------------------------------------------------------


def encode_scenario(spec: IntentSpec) -> dict[str, Any]:
    """IntentSpec → wire JSON for POST /scenario/v2/scenario.

    Тащит обратно `raw_extras` чтобы не потерять незнакомые поля
    (image, meta, requires) при update.
    """
    # Tasks из всех action'ов нашего spec'а.
    tasks: list[dict[str, Any]] = []
    for action in spec.actions:
        if action.unknown:
            # Forward-compat: unknown action — это action который мы
            # декодили из Sber но не знали как разобрать. Восстанавливаем
            # из data.raw.
            raw = action.data.get("raw")
            if isinstance(raw, dict):
                tasks.append(raw)
            continue
        reg = get_action(action.type)
        if reg is None:
            # Незарегистрированный тип — skip (не должно быть после decode,
            # но защита от дёрганого UI).
            continue
        tasks.extend(reg.encode(action.data))

    # Условие — wraps нашу phrases-фразу в каноничный CONDITIONS/nested
    # вид (Sber всё равно обернёт сам, но шлём правильно сразу).
    condition = _build_condition(spec.phrases)

    # Базовая структура.
    body: dict[str, Any] = {
        "name": spec.name,
        "timezone": spec.raw_extras.get("timezone") or DEFAULT_TIMEZONE,
        "is_active": bool(spec.enabled),
        "image": spec.raw_extras.get("image") or DEFAULT_IMAGE,
        "steps": [
            {
                "tasks": tasks,
                "condition": condition,
            }
        ],
    }

    # Тащим назад незнакомые top-level поля кроме тех что уже
    # принципиально установили выше.
    skip_keys = {"timezone", "image", "steps"}
    for k, v in spec.raw_extras.items():
        if k not in skip_keys and k not in body:
            body[k] = v

    return body


def _build_condition(phrases: list[str]) -> dict[str, Any]:
    """Каноничная Sber-обёртка для phrase-trigger'а.

    Sber на сервере оборачивает single-condition в CONDITIONS/nested,
    но воспринимает и плоский вариант. Шлём канонический.
    """
    if not phrases:
        # Без фраз сценарий бесполезен, но Sber примет — wrap пустым.
        return {
            "type": "CONDITIONS",
            "nested_conditions_data": {"conditions": [], "relation": "OR"},
        }
    inner = {
        "type": "PHRASES",
        "phrases_data": {"phrases": list(phrases)},
    }
    return {
        "type": "CONDITIONS",
        "nested_conditions_data": {
            "conditions": [inner],
            "relation": "OR",
        },
    }


__all__ = ["DEFAULT_IMAGE", "DEFAULT_TIMEZONE", "decode_scenario", "encode_scenario"]
