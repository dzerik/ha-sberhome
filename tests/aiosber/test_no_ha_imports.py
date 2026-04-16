"""Compliance check: aiosber/ не должен импортировать HA.

Защищает архитектурное правило из CLAUDE.md: aiosber/ — standalone-ready
пакет, готовый к extract в свой PyPI-пакет одним поиск-заменой.
"""

from __future__ import annotations

import ast
import pathlib

FORBIDDEN_TOP_LEVEL = {"homeassistant", "voluptuous", "aiohttp"}

AIOSBER_ROOT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "custom_components"
    / "sberhome"
    / "aiosber"
)


def _iter_aiosber_files():
    return [p for p in AIOSBER_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def test_aiosber_root_exists():
    assert AIOSBER_ROOT.is_dir(), f"aiosber/ not found at {AIOSBER_ROOT}"


def test_no_ha_imports_in_aiosber():
    """Ни один файл aiosber/ не импортирует homeassistant/voluptuous/aiohttp."""
    violations = []
    for path in _iter_aiosber_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    continue  # relative imports — это аиосбер сам себя
                if node.module:
                    mods = [node.module.split(".")[0]]
            bad = set(mods) & FORBIDDEN_TOP_LEVEL
            if bad:
                violations.append(
                    f"{path.relative_to(AIOSBER_ROOT.parent)}:{node.lineno} imports {bad}"
                )

    assert not violations, "aiosber must be HA-free:\n" + "\n".join(violations)


def test_no_relative_imports_outside_aiosber():
    """Relative imports не должны выходить за пределы aiosber/.

    Проверяется через `level=N`: aiosber/X/Y.py с `from ... import` (level >= 3
    относительно aiosber/X/Y.py = sberhome) — запрещено.
    """
    violations = []
    for path in _iter_aiosber_files():
        # Глубина файла относительно aiosber/
        depth = len(path.relative_to(AIOSBER_ROOT).parents)  # aiosber/x.py = 1, aiosber/a/b.py = 2
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        # level=1 = подняться на 1; чтобы выйти из aiosber — нужно подняться на `depth`
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.level > 0
                and node.level > depth
            ):
                violations.append(
                    f"{path.relative_to(AIOSBER_ROOT.parent)}:{node.lineno} "
                    f"relative import escapes aiosber "
                    f"(level={node.level}, depth={depth})"
                )

    assert not violations, "aiosber must not reach outside via relative import:\n" + "\n".join(
        violations
    )
