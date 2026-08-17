"""IntentEncoder — IntentSpec ↔ Sber `ScenarioDto` (wire JSON).

Single source of truth для:
- **decode**: парсим Sber-сценарий из живого ответа REST API в IntentSpec.
  Известные actions через `registry`, незнакомые — `IntentAction(unknown=True)`.
  Все Sber-специфичные поля (image, meta, account_id, requires, …) уезжают
  в `IntentSpec.raw_extras`.
- **encode**: собираем wire-JSON для POST/PUT. Тащим обратно `raw_extras`,
  чтобы не потерять незнакомые поля при обновлении.

Структура wire (восстановлена из live traffic):

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
from .spec import IntentAction, IntentSpec, IntentTrigger

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
        "description",
        "steps",
        "home_id",
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
    triggers: list[IntentTrigger] = []
    actions: list[IntentAction] = []
    is_ha_managed = True

    # Фразы, triggers и actions — agg по всем steps. На практике обычно 1 step.
    for step in steps:
        if not isinstance(step, dict):
            continue
        phrases.extend(_collect_phrases(step.get("condition")))
        triggers.extend(_collect_triggers(step.get("condition")))
        step_actions, step_is_ha = _decode_tasks(step.get("tasks") or [])
        actions.extend(step_actions)
        if not step_is_ha:
            is_ha_managed = False

    # Если actions пусты (пустой tasks[]) — это ha_event_only.
    if not actions:
        actions = [IntentAction(type="ha_event_only")]

    # Forward-compat: всё остальное — в raw_extras.
    raw_extras = {k: v for k, v in scenario.items() if k not in _KNOWN_TOP_FIELDS}

    home_id_raw = scenario.get("home_id")
    home_id = home_id_raw if isinstance(home_id_raw, str) and home_id_raw else None

    return IntentSpec(
        id=spec_id if spec_id else None,
        name=name,
        phrases=_dedup_keep_order(phrases),
        triggers=triggers,
        actions=actions,
        enabled=enabled,
        description=str(scenario.get("description") or ""),
        is_ha_managed=is_ha_managed,
        home_id=home_id,
        raw_extras=raw_extras,
    )


def _collect_phrases(condition: Any) -> list[str]:
    """Собрать phrases С ВЕРХНЕЙ OR-плоскости (симметрично `_collect_triggers`).

    Ходим ровно по тем же top-level children, что и `_collect_triggers`, и
    НЕ спускаемся во вложенные группы: их `_collect_triggers` захватывает
    целиком как unknown-триггер (`data['raw']`). Если бы мы рекурсивно
    вытягивали PHRASES из такой подгруппы в `IntentSpec.phrases`, то при
    encode фраза продублировалась бы (внутри raw-блока + отдельной top-level
    PHRASES), а `(PHRASES AND DEVICE)` превратилось бы в
    `(PHRASES AND DEVICE) OR PHRASES` — сценарий сработал бы на голую фразу
    в обход DEVICE-условия (нарушение round-trip).
    """
    if not isinstance(condition, dict):
        return []
    cond_type = str(condition.get("type") or "").upper()
    if cond_type == "PHRASES":
        data = condition.get("phrases_data") or {}
        return [str(p) for p in (data.get("phrases") or [])]
    nested = condition.get("nested_conditions_data") or {}
    children = nested.get("conditions")
    if children is None:
        return []
    out: list[str] = []
    for c in children:
        if isinstance(c, dict) and str(c.get("type") or "").upper() == "PHRASES":
            data = c.get("phrases_data") or {}
            out.extend(str(p) for p in (data.get("phrases") or []))
    return out


def _collect_triggers(condition: Any) -> list[IntentTrigger]:
    """Собрать триггеры с ВЕРХНЕЙ OR-плоскости условия.

    Ходим только по top-level `nested_conditions_data.conditions` (или по
    самому condition, если он одиночный без обёртки). Внутрь вложенных
    AND/CONDITIONS НЕ спускаемся — они уходят целиком в unknown-триггер
    с дословным `data['raw']` (round-trip lossless).

    PHRASES пропускаем — они живут в `IntentSpec.phrases`.
    """
    if not isinstance(condition, dict):
        return []
    nested = condition.get("nested_conditions_data") or {}
    children = nested.get("conditions")
    if children is None:
        children = [condition]  # плоский single-condition без обёртки
    out: list[IntentTrigger] = []
    for c in children:
        if not isinstance(c, dict):
            continue
        c_type = str(c.get("type") or "").upper()
        if c_type == "PHRASES":
            continue
        if c_type == "TIME":
            out.append(_decode_time_trigger(c))
        elif c_type == "DEVICE":
            out.append(_decode_device_trigger(c))
        else:
            out.append(IntentTrigger(type="unknown", data={"raw": c}, unknown=True))
    return out


def _decode_time_trigger(c: dict[str, Any]) -> IntentTrigger:
    """TIME-condition → IntentTrigger('time', {'rrule': ...})."""
    time_data = c.get("time_data") or {}
    return IntentTrigger(
        type="time",
        data={"rrule": str(time_data.get("rrule", ""))},
    )


def _decode_device_trigger(c: dict[str, Any]) -> IntentTrigger:
    """DEVICE-condition → IntentTrigger('device', {...}).

    Полный `state`-dict сохраняем дословно в `data['attribute']` —
    device-триггер lossless и не рискует неполным AttributeValue-скелетом
    при re-encode.
    """
    dd = c.get("device_data") or {}
    inner = dd.get("condition") or {}
    return IntentTrigger(
        type="device",
        data={
            "device_id": str(dd.get("device_id", "")),
            "categories_slugs": list(dd.get("categories_slugs") or []),
            "attribute": inner.get("state") or {},
            "operator": str(inner.get("condition", "EQUAL")),
            "delay_seconds": _parse_delay_seconds(inner.get("delay")),
            "parent_id": str(dd.get("parent_id", "")),
        },
    )


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
            before = list(remaining)
            decoded, leftover = reg.decode(remaining)
            if decoded is None:
                break
            # Захватываем start_delay забранного task'а → в data действия.
            consumed = [t for t in before if t not in leftover]
            if consumed:
                delay = _parse_delay_seconds(consumed[0].get("start_delay"))
                if delay:
                    decoded.data["delay_seconds"] = delay
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


def _parse_delay_seconds(value: Any) -> int:
    """Секунды задержки из int или строки вида '240s'. Невалид/0 → 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        raw = value.strip().rstrip("s")
        try:
            return max(0, int(float(raw)))
        except ValueError:
            return 0
    return 0


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
        encoded = reg.encode(action.data)
        # Пауза перед действием — общее поле `start_delay` на любом task.
        delay = _parse_delay_seconds(action.data.get("delay_seconds"))
        if delay:
            for task in encoded:
                task["start_delay"] = f"{delay}s"
        tasks.extend(encoded)

    # Условие — собираем triggers + phrases в каноничный CONDITIONS/nested
    # top-OR (Sber всё равно обернёт сам, но шлём правильно сразу).
    condition = _build_condition(spec.phrases, spec.triggers)

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

    # Description — критично для TTS surrogate (marker для discovery)
    # и для intents (HA-managed ownership marker через description).
    # Пустой description пропускаем — Sber default'ит к "".
    if spec.description:
        body["description"] = spec.description

    # Multi-home: если у IntentSpec задан home_id — пишем в body.
    # Это применимо как для create (Sber кладёт сценарий в нужный дом
    # вместо дефолтного), так и для update (preserves существующий
    # home_id, который decoder скопировал из scenario при load).
    if spec.home_id:
        body["home_id"] = spec.home_id

    # Тащим назад незнакомые top-level поля кроме тех что уже
    # принципиально установили выше.
    skip_keys = {"timezone", "image", "steps"}
    for k, v in spec.raw_extras.items():
        if k not in skip_keys and k not in body:
            body[k] = v

    return body


def _build_condition(
    phrases: list[str], triggers: list[IntentTrigger] | None = None
) -> dict[str, Any]:
    """Каноничная Sber-обёртка top-OR: триггеры → одна PHRASES-condition.

    Порядок conditions: сначала time/device/unknown-триггеры (в исходном
    порядке), затем — единая PHRASES-condition со всеми фразами. Sber на
    сервере оборачивает single-condition в CONDITIONS/nested, но
    воспринимает и плоский вариант. Шлём канонический.
    """
    conditions: list[dict[str, Any]] = []
    for trig in triggers or []:
        enc = _encode_trigger(trig)
        if enc is not None:
            conditions.append(enc)
    if phrases:
        conditions.append({"type": "PHRASES", "phrases_data": {"phrases": list(phrases)}})
    return {
        "type": "CONDITIONS",
        "nested_conditions_data": {"conditions": conditions, "relation": "OR"},
    }


def _encode_trigger(trig: IntentTrigger) -> dict[str, Any] | None:
    """IntentTrigger → Sber condition-dict (или None если пустой/невалидный)."""
    if trig.type == "unknown":
        raw = trig.data.get("raw")
        return raw if isinstance(raw, dict) else None
    if trig.type == "time":
        rrule = str(trig.data.get("rrule", "")).strip()
        if not rrule:
            return None
        return {"type": "TIME", "time_data": {"execute_at": None, "rrule": rrule}}
    if trig.type == "device":
        return _encode_device_trigger(trig)
    return None


def _encode_device_trigger(trig: IntentTrigger) -> dict[str, Any] | None:
    """IntentTrigger('device') → DEVICE-condition. Полный state дословно."""
    device_id = str(trig.data.get("device_id", "")).strip()
    if not device_id:
        return None
    parent_id = str(trig.data.get("parent_id", "")).strip()
    device_data: dict[str, Any] = {
        "device_id": device_id,
        "categories_slugs": list(trig.data.get("categories_slugs") or []),
        "condition": {
            "state": trig.data.get("attribute") or {},
            "condition": str(trig.data.get("operator", "EQUAL")),
            "delay": f"{_parse_delay_seconds(trig.data.get('delay_seconds'))}s",
        },
    }
    if parent_id:
        device_data["parent_id"] = parent_id
    return {"type": "DEVICE", "device_data": device_data}


__all__ = ["DEFAULT_IMAGE", "DEFAULT_TIMEZONE", "decode_scenario", "encode_scenario"]
