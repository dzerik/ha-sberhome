"""TtsSurrogateService — lookup-or-create + edit-then-run flow.

🧪 EXPERIMENTAL. См. CHANGELOG v5.6.0. Каждый ``send()`` делает 2-3 API
request'а к облаку Sber (PUT scenario → POST /run, плюс GET для cache miss).
Не для частых уведомлений. Concurrency control НЕ делается — пользователь
явно принимает race condition при одновременных вызовах.

DRY: wire-формат не дублируется. ``_build_body`` конструирует
:class:`IntentSpec` и пропускает через существующий проверенный
``intents.encoder.encode_scenario`` — тот же путь, что использует
обычное создание voice-intent'а. Surrogate отличается только пустыми
``phrases`` (encoder делает empty condition → Sber не запустит голосом)
и description-marker'ом.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers.template import Template

from ..aiosber.exceptions import AuthError as _AiosberAuthError
from ..exceptions import SberApiError
from ..intents.encoder import encode_scenario
from ..intents.spec import IntentAction, IntentSpec
from ..sbermap.spec.ha_mapping import resolve_category
from .marker import build_marker, build_surrogate_name, match_surrogate

if TYPE_CHECKING:
    from ..coordinator import SberHomeCoordinator

_LOGGER = logging.getLogger(__name__)

SBER_SPEAKER_CATEGORY = "sber_speaker"

# Guard-фраза для surrogate-сценария. Sber требует non-empty `conditions[]`
# (HTTP 500 "bad nested condition") и принимает phrases только на русском
# (STT-фильтр). Эта фраза достаточно необычная чтобы пользователь не
# произнёс её случайно, но при желании сценарий можно вручную активировать
# голосом в Sber app для отладки.
GUARD_PHRASE = "служебная фраза сурогата хатэтээс"


class TtsSurrogateService:
    """Манипуляции с surrogate-сценариями per home."""

    def __init__(self, coordinator: SberHomeCoordinator) -> None:
        self._coord = coordinator
        # Per-home lock — guard against concurrent get_surrogate_id calls
        # creating duplicate scenarios. Single event loop, но без lock'а
        # два concurrent notify.async_send_message → 2× list+create →
        # 2 orphan surrogate-сценария в Sber.
        self._home_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, home_id: str) -> asyncio.Lock:
        lock = self._home_locks.get(home_id)
        if lock is None:
            lock = asyncio.Lock()
            self._home_locks[home_id] = lock
        return lock

    async def get_surrogate_id(self, home_id: str) -> str:
        """Вернуть scenario_id surrogate для home_id, создавая при необходимости.

        Order:
        1. Hot cache (``coordinator.tts_surrogates[home_id]``).
        2. Discover via ``scenarios.list()`` + match by marker.
        3. Create new boilerplate scenario с placeholder фразой и
           реальными device_ids (Sber требует non-empty PRONOUNCE_COMMAND).

        Lock'аем per-home чтобы concurrent calls не создавали дубль.
        """
        # Fast path без lock'а — typical case (cache hit).
        cached = self._coord.tts_surrogates.get(home_id)
        if cached:
            return cached

        async with self._lock_for(home_id):
            # Re-check cache after acquiring lock — pre-empted writer мог уже
            # заполнить cache пока мы ждали lock.
            cached = self._coord.tts_surrogates.get(home_id)
            if cached:
                return cached

            scenarios = await self._coord.client.scenarios.list()
            for s in scenarios:
                if match_surrogate(s, home_id) and s.id:
                    self._coord.tts_surrogates[home_id] = s.id
                    _LOGGER.debug("TTS surrogate discovered for home %s: %s", home_id, s.id)
                    return s.id

            speakers = self._all_speakers_in_home(home_id)
            if not speakers:
                home_name = self._home_name(home_id) or home_id
                raise HomeAssistantError(
                    f"В доме «{home_name}» нет колонок Sber. Surrogate-сценарий "
                    "создаётся с одной PRONOUNCE_COMMAND task (Sber требует "
                    "non-empty device_ids), поэтому нужна хотя бы одна колонка. "
                    "Добавьте SberBoom/Portal/Satellite в этот дом через приложение «Салют!»."
                )

            body = self._build_body(home_id, "Тестовая фраза", speakers)
            created = await self._coord.client.scenarios.create(body)
            new_id = created["id"]
            self._coord.tts_surrogates[home_id] = new_id
            _LOGGER.info(
                "TTS surrogate created for home %s (%s): %s",
                home_id,
                self._home_name(home_id),
                new_id,
            )
            return new_id

    async def send(
        self,
        home_id: str,
        message: str,
        device_ids: list[str] | None,
    ) -> None:
        """Edit-then-run: PUT pronounce_data → POST /run.

        Если ``message`` содержит Jinja-шаблон (``{{ … }}`` / ``{% … %}``),
        он рендерится на стороне HA непосредственно перед отправкой —
        Sber произнесёт уже подставленный текст. Контекст рендера — пустой
        (helpers.template без переменных), так что доступны только
        стандартные функции (``states()``, ``state_attr()``, ``now()`` и т.п.).

        На «scenario gone» (404 OR 401/403 после refresh) — инвалидируем
        cache, rediscover/recreate, retry один раз. Sber отдаёт 401 а не
        404 для удалённого/чужого scenario_id (наблюдалось в production:
        юзер вручную удалил surrogate в приложении «Салют!»).

        Concurrency не контролируется (accepted limitation).
        """
        message = self._render_template(message)
        if not device_ids:
            device_ids = self._all_speakers_in_home(home_id)
        if not device_ids:
            raise HomeAssistantError(f"TTS surrogate: No speakers found in home {home_id}")

        scenario_id = await self.get_surrogate_id(home_id)
        body = self._build_body(home_id, message, device_ids)

        try:
            await self._coord.client.scenarios.update(scenario_id, body)
        except (SberApiError, _AiosberAuthError) as err:
            if not self._is_scenario_gone(err):
                raise
            _LOGGER.warning(
                "TTS surrogate %s gone (%s) — invalidating cache, recreating",
                scenario_id,
                type(err).__name__,
            )
            self._coord.tts_surrogates.pop(home_id, None)
            scenario_id = await self.get_surrogate_id(home_id)
            await self._coord.client.scenarios.update(scenario_id, body)

        await self._coord.client.scenarios.run(scenario_id)

    @staticmethod
    def _is_scenario_gone(err: Exception) -> bool:
        """True если ошибка означает «scenario_id не существует у Sber».

        Sber-specific: для удалённого/чужого scenario_id Sber отдаёт
        - 404 (Not Found) — typical REST behavior
        - 401/403 после auth refresh-retry (`AuthError "Unauthorized
          after refresh"` в transport/http.py) — наблюдалось когда юзер
          вручную удалил surrogate в приложении «Салют!».
        Оба случая → invalidate cache + recreate.
        """
        if isinstance(err, _AiosberAuthError):
            return True
        status = getattr(err, "status_code", None) or getattr(err, "status", None)
        return status in (401, 403, 404)

    def _render_template(self, message: str) -> str:
        """Render Jinja-шаблон в ``message``, если он там есть.

        Plain-строки (без ``{{``/``{%``) пропускаются as-is — это покрывает
        и обычный путь ``notify.sber_tts_*`` (HA рендерит service-data до
        вызова entity), и прямые программные вызовы без шаблонов.

        TemplateError маппится в HomeAssistantError — пользователь увидит
        понятную ошибку, scenario не обновится.
        """
        if not isinstance(message, str) or ("{{" not in message and "{%" not in message):
            return message
        try:
            rendered = Template(message, self._coord.hass).async_render(parse_result=False)
        except TemplateError as err:
            raise HomeAssistantError(
                f"TTS surrogate: не удалось отрендерить шаблон фразы: {err}"
            ) from err
        return str(rendered)

    def _build_body(self, home_id: str, message: str, device_ids: list[str]) -> dict[str, Any]:
        """Body для POST/PUT — через существующий ``encode_scenario``.

        DRY: используется тот же encoder, что и для обычных voice intents.
        Отличия surrogate:
        - ``phrases`` содержит ОДНУ guard-фразу на русском (Sber STT
          фильтрует latin/прочие алфавиты). Sber отвергает создание сценария
          с пустым ``conditions: []`` ("bad nested condition"), поэтому
          даём ему техническую русскую фразу, которую реальный пользователь
          не произнесёт в обиходе: «служебная фраза сурогата хатэтээс».
          Discovery surrogate'а идёт через description-marker, не через phrase.
        - ``description`` содержит marker для discovery через ``scenarios.list()``.
        - Один TTS-action с реальными ``phrase`` + ``device_ids``.
        """
        home_name = self._home_name(home_id)
        spec = IntentSpec(
            id=None,
            name=build_surrogate_name(home_id, home_name),
            phrases=[GUARD_PHRASE],
            actions=[
                IntentAction(
                    type="tts",
                    data={"phrase": message, "device_ids": list(device_ids)},
                )
            ],
            enabled=True,
            description=build_marker(home_id),
            home_id=home_id,
        )
        return encode_scenario(spec)

    def _all_speakers_in_home(self, home_id: str) -> list[str]:
        """Все Sber-колонки, принадлежащие указанному дому."""
        cache = self._coord.state_cache
        result: list[str] = []
        for device_id, dto in cache.get_all_devices().items():
            if cache.device_home_id(device_id) != home_id:
                continue
            slug = None
            if dto.full_categories:
                first = dto.full_categories[0]
                slug = getattr(first, "slug", None)
            category = resolve_category(dto.image_set_type, slug=slug)
            if category == SBER_SPEAKER_CATEGORY:
                result.append(device_id)
        return result

    def _home_name(self, home_id: str) -> str:
        for home in self._coord.state_cache.get_homes():
            if home.id == home_id:
                return home.name or ""
        return ""
