"""Shared state for pending authorization flows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import SberAPI

# Shared storage for pending auth flows: flow_id -> SberAPI client
pending_auth_flows: dict[str, SberAPI] = {}
