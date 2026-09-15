"""Перевод ошибок облака Сбера в ошибки действий Home Assistant.

Действия сущностей (включить свет, нажать кнопку, записать настройку колонки)
вызываются из UI, автоматизаций и скриптов. HA показывает пользователю только
`HomeAssistantError` и его наследников, причём текст берётся из переводов
(`strings.json` → `exceptions`). Сырые исключения aiosber туда не годятся:
их текст на английском, содержит URL запросов и не локализуется, а
`ConfigEntryAuthFailed` в контексте действия не запускает повторный вход —
HA обрабатывает его только при настройке записи и опросе координатора.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .aiosber.exceptions import (
    ApiError,
    AuthError,
    NetworkError,
    RateLimitError,
    RequestUnauthorized,
    SberError,
)
from .const import DOMAIN, LOGGER
from .coordinator import SberHomeCoordinator

BAD_REQUEST_STATUSES = frozenset({400, 422})
"""HTTP-статусы, которыми облако отвергает саму команду как некорректную."""


async def _async_recheck_after_denied(
    coordinator: SberHomeCoordinator, *, refresh_scenarios: bool
) -> None:
    """Перепроверить данные аккаунта после отказа облака в доступе к объекту.

    Опрос устройств идёт через ``async_request_refresh``: его ошибки
    обрабатывает сам координатор (в том числе запускает повторный вход).
    Перечитка сценариев best-effort — её сбой только пишется в журнал,
    плановый опрос сценариев повторит попытку сам.

    Args:
        coordinator: Координатор записи, от имени которой шёл запрос.
        refresh_scenarios: Сразу перечитать сценарии и «я дома» в обход
            интервала их опроса.
    """
    await coordinator.async_request_refresh()
    if not refresh_scenarios:
        return
    try:
        await coordinator.async_refresh_scenarios()
    except Exception as err:  # noqa: BLE001 — фоновая перечитка, не действие пользователя
        LOGGER.debug("Scenario refresh after denied action failed: %s", err)


@asynccontextmanager
async def async_translate_cloud_errors(
    coordinator: SberHomeCoordinator,
    *,
    refresh_scenarios: bool = False,
) -> AsyncIterator[None]:
    """Выполнить обращение к облаку и перевести его ошибки для действия HA.

    Ошибка авторизации запускает повторный вход для записи координатора
    (HA сам не создаёт второй поток, если он уже открыт). Исключение —
    `RequestUnauthorized`: токен только что успешно обновлён, а облако всё
    равно отвергло именно этот запрос (так Sber отвечает на удалённый в
    приложении сценарий). Повторный вход тут не поможет, поэтому вместо него
    запрашивается внеочередной опрос устройств: если данные входа всё же не
    годятся, повторный вход запустит он. Удалённое устройство пропадает после
    этого опроса. Список сценариев и «я дома» этот опрос не перечитывает
    (они опрашиваются реже, раз в ``SCENARIO_POLL_INTERVAL_SEC``, а после
    сбоя — только вручную), поэтому для их действий ``refresh_scenarios=True``
    дополнительно сразу перечитывает и их: удалённый сценарий становится
    недоступен, а не отвечает той же ошибкой до следующего планового опроса.

    Текст исходной ошибки пишется только в журнал — в сообщение пользователю
    попадает переведённая фраза без URL, тел ответов и токенов.

    Args:
        coordinator: Координатор записи, от имени которой идёт запрос.
        refresh_scenarios: Действие адресовано сценарию или дому: при отказе
            в доступе сразу перечитать сценарии и «я дома».

    Yields:
        Ничего — используется как ``async with``.

    Raises:
        HomeAssistantError: Облако не приняло данные входа, отказало в доступе
            к объекту, недоступно, ограничило частоту запросов или вернуло
            ошибку.
        ServiceValidationError: Облако отвергло команду как некорректную
            (HTTP 400/422).
    """
    try:
        yield
    except RequestUnauthorized as err:
        LOGGER.warning("Cloud denied access to the requested object, re-polling: %s", err)
        coordinator.hass.async_create_task(
            _async_recheck_after_denied(coordinator, refresh_scenarios=refresh_scenarios),
            "sberhome refresh after denied action",
        )
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="access_denied"
        ) from err
    except AuthError as err:
        LOGGER.warning("Cloud rejected credentials during an action, starting reauth: %s", err)
        entry = coordinator.config_entry
        if entry is not None:
            entry.async_start_reauth(coordinator.hass)
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="auth_failed") from err
    except RateLimitError as err:
        LOGGER.warning("Action rate-limited by the cloud: %s", err)
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rate_limited") from err
    except ApiError as err:
        LOGGER.warning("Cloud returned an error for an action: %s", err)
        placeholders = {"status": str(err.status_code)}
        if err.status_code in BAD_REQUEST_STATUSES:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="command_rejected",
                translation_placeholders=placeholders,
            ) from err
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="api_error",
            translation_placeholders=placeholders,
        ) from err
    except NetworkError as err:
        LOGGER.warning("Cloud unreachable during an action: %s", err)
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="cloud_unreachable"
        ) from err
    except SberError as err:
        LOGGER.warning("Unexpected cloud response during an action: %s", err)
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="cloud_error") from err
