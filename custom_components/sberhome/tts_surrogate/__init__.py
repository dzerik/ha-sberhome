"""TTS surrogate — HA-side feature для произнесения произвольного текста
через Sber колонки путём run-time edit'а Sber-сценария-болванки.

🧪 EXPERIMENTAL. См. CHANGELOG v5.6.0 и spec.

Wire-формат scenario'я не дублируется — `TtsSurrogateService._build_body`
конструирует :class:`IntentSpec` и пропускает через существующий
проверенный ``intents.encoder.encode_scenario``.
"""

from .marker import (
    MARKER_PREFIX,
    build_marker,
    build_surrogate_name,
    match_surrogate,
    parse_marker,
)
from .service import SBER_SPEAKER_CATEGORY, TtsSurrogateService

__all__ = [
    "MARKER_PREFIX",
    "SBER_SPEAKER_CATEGORY",
    "TtsSurrogateService",
    "build_marker",
    "build_surrogate_name",
    "match_surrogate",
    "parse_marker",
]
