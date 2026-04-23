#!/usr/bin/env python3
"""CLI пример: авторизоваться через PKCE + получить список устройств.

Поток:
1. Сгенерировать PKCE параметры → URL для логина в Sber ID.
2. Открыть URL вручную в браузере, авторизоваться.
3. Скопировать redirect URL (companionapp://...?code=...) → вставить в скрипт.
4. Скрипт обменяет code на SberID токены, потом на companion токен.
5. Вызовет SberClient.devices.list() и распечатает таблицу.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from aiosber import SberClient
from aiosber.auth import (
    PkceParams,
    build_authorize_url,
    exchange_code_for_tokens,
    extract_code_from_redirect,
)


async def main() -> int:
    pkce = PkceParams.generate()
    auth_url = build_authorize_url(pkce)
    print("=" * 80)
    print("Откройте в браузере:")
    print(auth_url)
    print()
    print("После логина браузер покажет ошибку — это нормально. Скопируйте URL")
    print("из адресной строки (он начинается с companionapp://) и вставьте сюда:")
    print("=" * 80)
    redirect_url = input("Redirect URL: ").strip()

    try:
        code = extract_code_from_redirect(redirect_url, expected_state=pkce.state)
    except Exception as err:
        print(f"❌ Не удалось извлечь code: {err}", file=sys.stderr)
        return 1

    async with httpx.AsyncClient() as http:
        sberid = await exchange_code_for_tokens(http, code, pkce.verifier)
        print(f"✅ SberID токен получен (expires in {sberid.expires_in}s)")

    client = await SberClient.from_oauth_setup(sberid_tokens=sberid)
    try:
        devices = await client.devices.list()
        print(f"\n✅ Получено устройств: {len(devices)}\n")
        for d in devices:
            online = d.reported_value("online")
            print(
                f"  {d.id[:8]}…  {(d.name or '?'):<30}  "
                f"{(d.image_set_type or '?'):<25}  online={online}"
            )
    finally:
        await client.aclose()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
