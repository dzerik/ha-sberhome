"""Поддельное облако Сбера для тестов в настоящем Home Assistant.

Интеграция настраивается целиком — ``async_setup_entry``, координатор,
платформы, WebSocket API панели, — а подменяется только сетевой слой:
httpx-клиент записи получает ``httpx.MockTransport``, который отвечает как
шлюз умного дома. Так тесты проверяют поведение, видимое пользователю
(ответы команд панели, состояния сущностей, записи в реестре), без заглушек
внутри интеграции.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import httpx

GATEWAY_PREFIX = "/gateway/v1"
"""Путь шлюза в ``GATEWAY_BASE_URL``; маршруты ниже задаются без него."""

COMPANION_TOKENS = {"access_token": "companion", "expires_in": 86400 * 365}
"""Токен шлюза, не требующий обмена: срок действия — год от создания записи."""

SBERID_TOKEN = {"access_token": "sberid", "refresh_token": "rt", "expires_in": 3600}

HOME = {"id": "home-1", "name": "Дом", "group_type": "HOME"}
ROOM = {"id": "room-1", "name": "Кухня", "group_type": "ROOM", "parent_id": "home-1"}

Responder = Callable[[httpx.Request], httpx.Response]


def device(
    device_id: str,
    *,
    image_set_type: str = "bulb_sber",
    serial: str | None = None,
    name: str | None = None,
    reported: list[dict[str, Any]] | None = None,
    attributes: list[dict[str, Any]] | None = None,
    commands: list[dict[str, Any]] | None = None,
    group_ids: list[str] | None = None,
    manufacturer: str = "Sber",
    **extra: Any,
) -> dict[str, Any]:
    """Сырой ответ ``/devices`` для одного устройства."""
    payload: dict[str, Any] = {
        "id": device_id,
        "serial_number": serial if serial is not None else f"SN-{device_id}",
        "name": {"name": name or device_id},
        "image_set_type": image_set_type,
        "sw_version": "1.0.0",
        "device_info": {"manufacturer": manufacturer, "model": "M-1"},
        "group_ids": group_ids if group_ids is not None else [ROOM["id"]],
        "reported_state": reported if reported is not None else [],
        "desired_state": [],
        "attributes": attributes if attributes is not None else [],
    }
    if commands is not None:
        payload["commands"] = commands
    payload.update(extra)
    return payload


class FakeSberCloud:
    """Шлюз умного дома Сбера в памяти: дома, комнаты, устройства, сценарии.

    Маршруты по умолчанию покрывают полный опрос координатора. Любой ответ
    можно переопределить через :meth:`on`; неизвестный путь отвечает 404,
    как настоящий шлюз на неподдерживаемый эндпоинт.
    """

    def __init__(self) -> None:
        self.homes: list[dict[str, Any]] = [dict(HOME)]
        self.rooms: list[dict[str, Any]] = [dict(ROOM)]
        self.groups: list[dict[str, Any]] = []
        self.devices: list[dict[str, Any]] = []
        self.scenarios: list[dict[str, Any]] = []
        self.requests: list[httpx.Request] = []
        self.down = False
        self._overrides: dict[tuple[str, str], Responder] = {}

    def on(self, method: str, path: str, response: Any) -> None:
        """Переопределить ответ на ``method path`` (путь без префикса шлюза).

        Args:
            method: HTTP-метод.
            path: Путь без ``/gateway/v1``.
            response: ``httpx.Response``, JSON-совместимое тело (ответ 200),
                исключение (бросается транспортом) или функция от запроса.
        """

        def _responder(request: httpx.Request) -> httpx.Response:
            if callable(response) and not isinstance(response, type):
                return response(request)
            if isinstance(response, BaseException):
                raise response
            if isinstance(response, httpx.Response):
                return response
            return httpx.Response(200, json=response)

        self._overrides[(method.upper(), path)] = _responder

    def sent(self, method: str, path: str) -> list[httpx.Request]:
        """Запросы, отправленные интеграцией на ``method path``."""
        return [r for r in self.requests if r.method == method.upper() and _route(r) == path]

    @staticmethod
    def body(request: httpx.Request) -> Any:
        """JSON-тело отправленного запроса."""
        return json.loads(request.content)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            raise httpx.ConnectError("network is unreachable", request=request)
        path = _route(request)
        override = self._overrides.get((request.method, path))
        if override is not None:
            return override(request)
        return self._default(request, path)

    def _default(self, request: httpx.Request, path: str) -> httpx.Response:
        if request.method == "GET":
            query = parse_qs(request.url.query.decode())
            if path == "/device_groups":
                kind = (query.get("group_type") or [""])[0]
                items = {"HOME": self.homes, "ROOM": self.rooms, "GROUP": self.groups}
                return httpx.Response(200, json={"result": items.get(kind, [])})
            if path == "/devices":
                return httpx.Response(200, json={"result": self.devices})
            if path == "/devices/enums":
                return httpx.Response(200, json={"result": {}})
            if path.startswith("/devices/"):
                device_id = path.removeprefix("/devices/")
                for raw in self.devices:
                    if raw["id"] == device_id:
                        return httpx.Response(200, json={"result": raw})
            if path == "/scenario/v2/scenario":
                return httpx.Response(200, json={"scenarios": self.scenarios})
            if path == "/scenario/v2/home/variable/at_home":
                return httpx.Response(
                    200, json={"variable": {"name": "at_home", "value": {"bool_value": True}}}
                )
            if path == "/inventory/ota-upgrades":
                return httpx.Response(200, json={"result": {}})
        if request.method in {"PUT", "POST"} and path.startswith("/devices/"):
            return httpx.Response(200, json={"result": {}})
        return httpx.Response(404, json={"message": f"no route {request.method} {path}"})


def _route(request: httpx.Request) -> str:
    return request.url.path.removeprefix(GATEWAY_PREFIX)
