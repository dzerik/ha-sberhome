"""Детектор конфликтующих интеграций для устройств Sber.

Две cloud-polling интеграции, обслуживающие один аккаунт Sber, могут
перехватывать WS-push'и и гонять optimistic updates — состояние в HA
становится неконсистентным. Детектор не отключает чужую интеграцию
(мы не можем и не должны) — только информирует пользователя через
HA Repairs и баннер в панели.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

# Известные сторонние интеграции для устройств Sber.
CONFLICTING_DOMAINS: tuple[str, ...] = ("sberdevices",)
ISSUE_ID = "conflicting_integration"


@callback
def detect_conflicts(hass: HomeAssistant) -> list[str]:
    """Вернуть домены конфликтующих интеграций с активными config entries."""
    return [d for d in CONFLICTING_DOMAINS if hass.config_entries.async_entries(d)]


@callback
def async_update_conflict_issue(hass: HomeAssistant) -> list[str]:
    """Создать/удалить repair issue по факту конфликта.

    Returns:
        Список обнаруженных конфликтующих доменов (пустой, если конфликта нет).
    """
    conflicts = detect_conflicts(hass)
    if conflicts:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_ID,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_ID,
            translation_placeholders={"domains": ", ".join(conflicts)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
    return conflicts
