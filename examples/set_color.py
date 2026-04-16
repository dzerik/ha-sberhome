#!/usr/bin/env python3
"""CLI пример: изменить цвет лампы.

Использует уже сохранённый companion-токен (для quick start без OAuth flow).
В реальном приложении токен брать из persistent storage.

Использование:

    python examples/set_color.py <companion_token> <device_id> <hue> <saturation> <brightness>

Пример:

    python examples/set_color.py "eyJ..." "abc-123" 240 100 80
"""

from __future__ import annotations

import asyncio
import sys

from aiosber import (
    AttributeValueDto,
    AttrKey,
    ColorValue,
    SberClient,
)


async def main(
    token: str, device_id: str, hue: int, saturation: int, brightness: int
) -> int:
    client = await SberClient.from_companion_token(token)
    try:
        color = ColorValue(hue=hue, saturation=saturation, brightness=brightness)
        await client.devices.set_state(
            device_id,
            [
                AttributeValueDto.of_bool(AttrKey.ON_OFF, True),
                AttributeValueDto.of_color(AttrKey.LIGHT_COLOUR, color),
            ],
        )
        print(f"✅ Цвет установлен: H={hue}° S={saturation}% B={brightness}%")
        return 0
    finally:
        await client.aclose()


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(2)
    sys.exit(
        asyncio.run(
            main(
                token=sys.argv[1],
                device_id=sys.argv[2],
                hue=int(sys.argv[3]),
                saturation=int(sys.argv[4]),
                brightness=int(sys.argv[5]),
            )
        )
    )
