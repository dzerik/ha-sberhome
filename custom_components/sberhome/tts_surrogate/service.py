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

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from ..exceptions import SberApiError
from ..intents.encoder import encode_scenario
from ..intents.spec import IntentAction, IntentSpec
from ..sbermap.spec.ha_mapping import resolve_category
from .marker import build_marker, match_surrogate

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

    async def get_surrogate_id(self, home_id: str) -> str:
        """Вернуть scenario_id surrogate для home_id, создавая при необходимости.

        Order:
        1. Hot cache (``coordinator.tts_surrogates[home_id]``).
        2. Discover via ``scenarios.list()`` + match by marker.
        3. Create new boilerplate scenario с placeholder фразой и
           реальными device_ids (Sber требует non-empty PRONOUNCE_COMMAND).
        """
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

        На 404 при PUT — инвалидируем cache, recreate, retry один раз.
        Concurrency не контролируется (accepted limitation).
        """
        if not device_ids:
            device_ids = self._all_speakers_in_home(home_id)
        if not device_ids:
            raise HomeAssistantError(f"TTS surrogate: No speakers found in home {home_id}")

        scenario_id = await self.get_surrogate_id(home_id)
        body = self._build_body(home_id, message, device_ids)

        try:
            await self._coord.client.scenarios.update(scenario_id, body)
        except SberApiError as err:
            status = getattr(err, "status_code", None) or getattr(err, "status", None)
            if status == 404:
                _LOGGER.warning(
                    "TTS surrogate %s returned 404 — invalidating cache, recreating",
                    scenario_id,
                )
                self._coord.tts_surrogates.pop(home_id, None)
                scenario_id = await self.get_surrogate_id(home_id)
                await self._coord.client.scenarios.update(scenario_id, body)
            else:
                raise

        await self._coord.client.scenarios.run(scenario_id)

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
            name=f"Sber TTS surrogate — {home_name}",
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
