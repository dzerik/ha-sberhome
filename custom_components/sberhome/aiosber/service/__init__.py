"""Service layer — высокоуровневые операции над Sber Smart Home.

Standalone: не зависит от HA. Можно использовать из CLI, ботов, тестов.
"""

from .device_service import DeviceService
from .group_service import GroupService
from .scenario_service import ScenarioService
from .state_cache import StateCache

__all__ = [
    "DeviceService",
    "GroupService",
    "ScenarioService",
    "StateCache",
]
