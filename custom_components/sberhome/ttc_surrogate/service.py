"""TtcSurrogateService — text-to-command суррогат (аналог TTS).

🧪 EXPERIMENTAL. Колонка ВЫПОЛНЯЕТ текст как голосовую команду ассистенту
(«Расскажи анекдот», «Включи радио», «Поставь таймер на 5 минут») — в отличие
от TTS, который просто ОЗВУЧИВАЕТ текст.

Механизм тот же, что у TtsSurrogateService: lookup-or-create surrogate-сценарий
per home + edit-then-run (PUT команду → POST /run). Отличие — action
``speaker_text`` (голый ``HEAD_DIALOG_COMMAND``, каноничная форма, проверено
голосом), а не ``tts`` (PRONOUNCE_COMMAND). Wire-формат не дублируется —
идём через тот же ``intents.encoder.encode_scenario``.

HEAD_DIALOG_COMMAND адресный (один device_id на task), поэтому на несколько
колонок собираем несколько ``speaker_text``-actions.
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

# Guard-фраза (Sber требует non-empty conditions[] и русский STT-алфавит).
GUARD_PHRASE = "служебная фраза сурогата хатэтээсэ"


class TtcSurrogateService:
    """Манипуляции с TTC-surrogate-сценариями per home."""

    def __init__(self, coordinator: SberHomeCoordinator) -> None:
        self._coord = coordinator
        self._home_locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, home_id: str) -> asyncio.Lock:
        lock = self._home_locks.get(home_id)
        if lock is None:
            lock = asyncio.Lock()
            self._home_locks[home_id] = lock
        return lock

    async def get_surrogate_id(self, home_id: str) -> str:
        cached = self._coord.ttc_surrogates.get(home_id)
        if cached:
            return cached
        async with self._lock_for(home_id):
            return await self._get_or_create_surrogate_locked(home_id)

    async def _get_or_create_surrogate_locked(self, home_id: str) -> str:
        cached = self._coord.ttc_surrogates.get(home_id)
        if cached:
            return cached

        scenarios = await self._coord.client.scenarios.list()
        for s in scenarios:
            if match_surrogate(s, home_id) and s.id:
                self._coord.ttc_surrogates[home_id] = s.id
                _LOGGER.debug("TTC surrogate discovered for home %s: %s", home_id, s.id)
                return s.id

        speakers = self._all_speakers_in_home(home_id)
        if not speakers:
            home_name = self._home_name(home_id) or home_id
            raise HomeAssistantError(
                f"В доме «{home_name}» нет колонок Sber. TTC-суррогат создаётся "
                "с одной HEAD_DIALOG_COMMAND task, поэтому нужна хотя бы одна "
                "колонка. Добавьте SberBoom/Portal/Satellite в этот дом через "
                "приложение «Салют!»."
            )

        body = self._build_body(home_id, "Который час", speakers[:1])
        created = await self._coord.client.scenarios.create(body)
        new_id = created["id"]
        self._coord.ttc_surrogates[home_id] = new_id
        _LOGGER.info(
            "TTC surrogate created for home %s (%s): %s",
            home_id,
            self._home_name(home_id),
            new_id,
        )
        return new_id

    async def send(
        self,
        home_id: str,
        command: str,
        device_ids: list[str] | None,
    ) -> None:
        """Edit-then-run: PUT head_dialog text → POST /run. Одна колонка =
        одна HEAD_DIALOG task; несколько — несколько tasks.

        Concurrency сериализован per-home lock'ом (как в TTS).
        """
        command = self._render_template(command)
        if not device_ids:
            device_ids = self._all_speakers_in_home(home_id)
        if not device_ids:
            raise HomeAssistantError(f"TTC surrogate: No speakers found in home {home_id}")

        async with self._lock_for(home_id):
            scenario_id = await self._get_or_create_surrogate_locked(home_id)
            body = self._build_body(home_id, command, device_ids)

            try:
                await self._coord.client.scenarios.update(scenario_id, body)
            except (SberApiError, _AiosberAuthError) as err:
                if not self._is_scenario_gone(err):
                    raise
                _LOGGER.warning(
                    "TTC surrogate %s gone (%s) — invalidating cache, recreating",
                    scenario_id,
                    type(err).__name__,
                )
                self._coord.ttc_surrogates.pop(home_id, None)
                scenario_id = await self._get_or_create_surrogate_locked(home_id)
                await self._coord.client.scenarios.update(scenario_id, body)

            await self._coord.client.scenarios.run(scenario_id)

    @staticmethod
    def _is_scenario_gone(err: Exception) -> bool:
        if isinstance(err, _AiosberAuthError):
            return True
        status = getattr(err, "status_code", None) or getattr(err, "status", None)
        return status in (401, 403, 404)

    def _render_template(self, command: str) -> str:
        if not isinstance(command, str) or ("{{" not in command and "{%" not in command):
            return command
        try:
            rendered = Template(command, self._coord.hass).async_render(parse_result=False)
        except TemplateError as err:
            raise HomeAssistantError(
                f"TTC surrogate: не удалось отрендерить шаблон команды: {err}"
            ) from err
        return str(rendered)

    def _build_body(self, home_id: str, command: str, device_ids: list[str]) -> dict[str, Any]:
        """Body через ``encode_scenario``. По одному ``speaker_text``-action на
        колонку (HEAD_DIALOG адресный)."""
        home_name = self._home_name(home_id)
        spec = IntentSpec(
            id=None,
            name=build_surrogate_name(home_id, home_name),
            phrases=[GUARD_PHRASE],
            actions=[
                IntentAction(
                    type="speaker_text",
                    data={"device_id": device_id, "text": command},
                )
                for device_id in device_ids
            ],
            enabled=True,
            description=build_marker(home_id),
            home_id=home_id,
        )
        return encode_scenario(spec)

    def _all_speakers_in_home(self, home_id: str) -> list[str]:
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
