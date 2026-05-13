"""DeviceCategoryDto — категория устройства.

JSON schema: элемент массива ``full_categories`` в DeviceDto.

Пример с одной категорией (моторизованный кран)::

    {
      "id": "valve",
      "name": "Моторизованный кран",
      "slug": "valve",
      "default_name": "Моторизованный кран",
      "image_set_type": "cat_valve_l",
      "sort_weight": 0,
      "meta": null,
      "images": {},
      "names": {},
      "default_names": {}
    }

LED-ленты с двойной природой (RGB + tunable white) приходят как массив
из двух элементов: ``[{slug: "led_strip", ...}, {slug: "light", ...}]``.
Первый элемент — основная категория устройства.

`slug` — стабильный машинный идентификатор категории, который Sber
сам кладёт в ответ. Использовать его как primary источник категории
надёжнее, чем эвристически парсить `image_set_type`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class DeviceCategoryDto:
    """Категория устройства (field key: ``full_categories`` array element)."""

    id: str | None = None
    name: str | None = None
    slug: str | None = None
    default_name: str | None = None
    image_set_type: str | None = None
    sort_weight: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["DeviceCategoryDto"]
