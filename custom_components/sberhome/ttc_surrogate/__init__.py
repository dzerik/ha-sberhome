"""TTC (text-to-command) surrogate — HA-side feature для ВЫПОЛНЕНИЯ произвольной
текстовой команды ассистенту через Sber-колонку (run-time edit сценария-болванки
с ``HEAD_DIALOG_COMMAND``).

🧪 EXPERIMENTAL. Аналог TTS-суррогата, но колонка ВЫПОЛНЯЕТ команду
(«Расскажи анекдот»), а не просто озвучивает текст.
"""

from .marker import (
    MARKER_PREFIX,
    build_marker,
    build_surrogate_name,
    match_surrogate,
    parse_marker,
)
from .service import SBER_SPEAKER_CATEGORY, TtcSurrogateService

__all__ = [
    "MARKER_PREFIX",
    "SBER_SPEAKER_CATEGORY",
    "TtcSurrogateService",
    "build_marker",
    "build_surrogate_name",
    "match_surrogate",
    "parse_marker",
]
