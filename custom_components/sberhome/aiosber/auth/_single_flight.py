"""SingleFlightRefresh — общий single-flight для обновления токенов.

Все провайдеры токенов (`AuthManager`, `CsafrontAuthManager`,
`SberIdBearerAuth`) обновляют одноразовый refresh_token. Параллельные
запросы, получившие 401 или увидевшие истёкший токен, не должны
устраивать шторм обменов: успешный refresh выполняется один раз, а
неудачный — делится с задачами, которые ждали lock во время попытки.

ZERO HA imports.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from ..exceptions import InvalidGrant


class SingleFlightRefresh:
    """Сериализует refresh токенов и разделяет исход попытки с ожидавшими.

    Args:
        lock: lock провайдера токенов. Передаётся снаружи, потому что тот же
            lock защищает и загрузку токенов из store.
        refresh: корутина-функция, выполняющая сам обмен токенов.
    """

    def __init__(self, lock: asyncio.Lock, refresh: Callable[[], Awaitable[None]]) -> None:
        self._lock = lock
        self._refresh = refresh
        # Число завершённых попыток refresh и ошибка последней.
        self._attempts = 0
        self._last_error: Exception | None = None

    def reset(self) -> None:
        """Забыть ошибку последней попытки — появились новые учётные данные."""
        self._last_error = None

    async def run(self, *, skip: Callable[[], bool]) -> bool:
        """Выполнить refresh под lock, если он всё ещё нужен.

        Args:
            skip: проверка под lock; ``True`` — соседняя задача уже получила
                подходящий токен, refresh не нужен.

        Returns:
            ``True``, если попытка refresh выполнена; ``False``, если её
            отменила проверка ``skip``.

        Raises:
            InvalidGrant / AuthError / NetworkError: ошибка refresh — своя или
                соседней задачи, завершившей попытку, пока эта ждала lock.
        """
        seen_attempt = self._attempts
        async with self._lock:
            if skip():
                return False
            await self._run_locked(seen_attempt)
            return True

    async def _run_locked(self, seen_attempt: int) -> None:
        """Выполнить refresh под lock, разделяя неудачу с ждавшими.

        Args:
            seen_attempt: значение счётчика попыток до ожидания lock. Если за
                время ожидания соседняя задача уже пыталась обновить токен и
                упала — её ошибка пробрасывается без повторного обращения к
                Sber (иначе очередь из N запросов даёт N неудачных refresh).

        Raises:
            InvalidGrant / AuthError / NetworkError: ошибка refresh.
        """
        err = self._last_error
        # InvalidGrant — отказ окончательный (одноразовый refresh_token отозван):
        # повтор с теми же учётными данными гарантированно упадёт, а до reauth
        # каждый запрос бил бы в Sber. Прочие ошибки делятся только с теми, кто
        # ждал lock во время неудачной попытки.
        if err is not None and (seen_attempt != self._attempts or isinstance(err, InvalidGrant)):
            raise err
        self._last_error = None
        try:
            await self._refresh()
        except Exception as exc:
            self._last_error = exc
            raise
        finally:
            # Считаем ЗАВЕРШЁННЫЕ попытки: задачи, вставшие в очередь во время
            # этой, видят прежнее значение и узнают о её исходе.
            self._attempts += 1


__all__ = ["SingleFlightRefresh"]
