"""ListenerRegistry — in-memory хранилище listener-specs.

Lifecycle: построен в ``async_setup_entry`` из YAML конфига. Заменяется
при reload integration'а. last_fired_at — in-memory только, обнуляется
при reload.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from .matcher import EventMeta, match_listener
from .spec import ListenerSpec

_LOGGER = logging.getLogger(__name__)


class ListenerRegistry:
    """Container для listener-specs с filter-matching и last_fired tracking."""

    def __init__(self, specs: Iterable[ListenerSpec] = ()) -> None:
        self._specs: list[ListenerSpec] = list(specs)
        _LOGGER.debug("ListenerRegistry initialized with %d spec(s)", len(self._specs))

    def list(self) -> list[ListenerSpec]:
        """Все specs в порядке, как пришли. Не копия — caller'ам нужно не мутировать."""
        return self._specs

    def find_matching(self, event: EventMeta) -> list[ListenerSpec]:
        """Все listeners (enabled=True), которые matches event."""
        return [s for s in self._specs if match_listener(s, event)]

    def mark_fired(self, spec: ListenerSpec, when: str) -> None:
        """Обновить last_fired_at на ISO-8601 timestamp."""
        spec.last_fired_at = when

    def replace(self, new_specs: Iterable[ListenerSpec]) -> None:
        """Заменить все specs (config reload). last_fired_at новых specs = None."""
        old_count = len(self._specs)
        self._specs = list(new_specs)
        _LOGGER.debug(
            "ListenerRegistry replaced: %d → %d spec(s)",
            old_count,
            len(self._specs),
        )
