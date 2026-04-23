"""Generic serialization helpers for DTO dataclasses.

DTO в Sber API — это плоские dataclass'ы с None по умолчанию для optional.
Здесь общая логика from_dict / to_dict, чтобы не повторять её в каждом классе.

Поддерживается:
- Optional[X] / Union[X, None]
- StrEnum / IntEnum / Enum (значение = `.value`)
- Вложенные dataclass'ы (рекурсивно)
- list[X], dict[str, X]

НЕ поддерживается:
- Union из нескольких не-None типов (избегаем — для Sber API это не нужно)
- Generic-параметры с TypeVar
"""

from __future__ import annotations

import dataclasses
import types
import typing
from enum import Enum
from typing import Any, get_args, get_origin, get_type_hints


def to_jsonable(value: Any) -> Any:
    """Преобразовать произвольное значение в JSON-совместимое.

    Enum → .value, dataclass → dict (рекурсивно с omit_none),
    list/dict — рекурсивно.

    Если у dataclass определён собственный `to_dict()` (напр. ColorValue
    переопределяет имена полей на short {h, s, v}) — вызываем его,
    а не generic `dataclass_to_dict`. Большинство DTO имеют тривиальный
    `to_dict = return dataclass_to_dict(self)`, так что разница
    проявляется только для перегруженных методов.
    """
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        to_dict_method = getattr(value, "to_dict", None)
        if callable(to_dict_method):
            return to_dict_method()
        return dataclass_to_dict(value)
    if isinstance(value, (list, tuple)):
        return [to_jsonable(x) for x in value]
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    return value


def dataclass_to_dict(obj: Any, *, omit_none: bool = True) -> dict[str, Any]:
    """Сериализовать dataclass в dict, исключая None-поля по умолчанию."""
    result: dict[str, Any] = {}
    for f in dataclasses.fields(obj):
        v = getattr(obj, f.name)
        if omit_none and v is None:
            continue
        result[f.name] = to_jsonable(v)
    return result


def _is_optional(tp: Any) -> tuple[bool, Any]:
    """Проверить, является ли тип Optional[X] / X | None. Вернуть (is_opt, inner)."""
    origin = get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1 and len(get_args(tp)) == 2:
            return True, args[0]
    return False, tp


def _convert(value: Any, tp: Any) -> Any:
    """Преобразовать сырое значение в типизированное по аннотации tp."""
    if value is None:
        return None

    is_opt, inner = _is_optional(tp)
    tp = inner

    origin = get_origin(tp)

    if origin is None:
        if isinstance(tp, type):
            if issubclass(tp, Enum):
                try:
                    return tp(value)
                except ValueError:
                    return None
            if dataclasses.is_dataclass(tp):
                # Resilient: если серилизованный формат сменился (e.g. dict → list для какого-то
                # nested поля) — не падаем, возвращаем None. Лучше потерять одно поле,
                # чем целый device при парсинге дерева устройств.
                if not isinstance(value, dict):
                    return None
                return from_dict(tp, value)
        return value

    if origin in (list, tuple):
        if not isinstance(value, (list, tuple)):
            return []
        (item_tp,) = get_args(tp) or (Any,)
        return [_convert(x, item_tp) for x in value]

    if origin is dict:
        if not isinstance(value, dict):
            return {}
        args = get_args(tp)
        val_tp = args[1] if len(args) >= 2 else Any
        return {k: _convert(v, val_tp) for k, v in value.items()}

    return value


def from_dict(cls: type, data: dict[str, Any] | None) -> Any:
    """Создать dataclass-объект из dict с учётом типов полей.

    Неизвестные поля игнорируются. Отсутствующие optional-поля → None
    (через дефолты dataclass'а). Resilient: если `data` не dict —
    возвращаем None, не падаем (API может быть нестандартным).
    """
    if data is None or not isinstance(data, dict):
        return None
    if not dataclasses.is_dataclass(cls):
        raise TypeError(f"{cls!r} is not a dataclass")

    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    field_names = {f.name for f in dataclasses.fields(cls)}
    for key, raw in data.items():
        if key not in field_names:
            continue
        try:
            kwargs[key] = _convert(raw, hints.get(key, Any))
        except (AttributeError, TypeError, ValueError):
            # Skip только это поле, не ломаем весь DTO.
            continue
    return cls(**kwargs)
