"""Compliance check: гибридные правила импортов в sbermap.

**Гибридная модель** (см. CLAUDE.md → "Архитектурная парадигма"):

| Подкаталог | HA imports | Зачем |
|---|---|---|
| `values/` | ❌ запрещены | pure dataclasses, переиспользуемы вне HA |
| `codecs/` | ❌ запрещены | serialized-format Sber-only, нет HA-логики |
| `spec/ha_mapping.py` | ✅ разрешён `Platform` | type-safe platform constants |
| `transform/` | ✅ разрешены HA-deps | основной выигрыш гибрида: STATE_*/HVACMode/etc. |
| `exceptions.py`, `__init__.py` | ❌ запрещены | re-exports, не должны тянуть HA через себя |

В `aiosber/` — стандартное правило: **полный запрет** HA imports (см.
`tests/aiosber/test_no_ha_imports.py`).
"""

from __future__ import annotations

import ast
import pathlib

# Эти топ-левел модули запрещены **везде** в sbermap:
ALWAYS_FORBIDDEN = {
    "voluptuous",
    "aiohttp",
    "httpx",
    "aiosber",  # sbermap полностью независим от aiosber
}

# `homeassistant` запрещён в standalone-частях, но разрешён в transform/ и
# spec/ha_mapping.py (см. таблицу выше).
HA_ALLOWED_DIRS = {"transform"}  # любой файл в sbermap/transform/
HA_ALLOWED_FILES = {"spec/ha_mapping.py"}

SBERMAP_ROOT = (
    pathlib.Path(__file__).resolve().parents[2] / "custom_components" / "sberhome" / "sbermap"
)


def _iter_files():
    return [p for p in SBERMAP_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def _ha_allowed_for(rel_path: pathlib.Path) -> bool:
    parts = rel_path.parts
    if parts and parts[0] in HA_ALLOWED_DIRS:
        return True
    return str(rel_path) in HA_ALLOWED_FILES


def test_sbermap_root_exists():
    assert SBERMAP_ROOT.is_dir()


def test_no_always_forbidden_imports():
    """voluptuous/aiohttp/httpx/aiosber запрещены везде."""
    violations = []
    for path in _iter_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                if node.module:
                    mods = [node.module.split(".")[0]]
            bad = set(mods) & ALWAYS_FORBIDDEN
            if bad:
                rel = path.relative_to(SBERMAP_ROOT.parent)
                violations.append(f"{rel}:{node.lineno} imports {bad}")
    assert not violations, "Forbidden imports:\n" + "\n".join(violations)


def test_homeassistant_only_in_allowed_paths():
    """`homeassistant.*` разрешён ТОЛЬКО в transform/ и spec/ha_mapping.py."""
    violations = []
    for path in _iter_files():
        rel = path.relative_to(SBERMAP_ROOT)
        if _ha_allowed_for(rel):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue
                if node.module:
                    mods = [node.module.split(".")[0]]
            if "homeassistant" in mods:
                violations.append(
                    f"{path.relative_to(SBERMAP_ROOT.parent)}:{node.lineno} "
                    f"imports homeassistant "
                    f"(not allowed outside transform/ + spec/ha_mapping.py)"
                )
    assert not violations, "homeassistant imports вне разрешённых путей:\n" + "\n".join(violations)
