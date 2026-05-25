#!/usr/bin/env python3
"""Bump the project version in both pyproject.toml and manifest.json.

Single source of truth: версия дублируется в `pyproject.toml` (`version`) и
`custom_components/sberhome/manifest.json` (`version`). Этот скрипт держит
их синхронно.

Usage:
    scripts/bump_version.py patch          # 5.9.0    → 5.9.1
    scripts/bump_version.py minor          # 5.9.0    → 5.10.0
    scripts/bump_version.py major          # 5.9.0    → 6.0.0
    scripts/bump_version.py beta           # 5.9.0    → 5.9.1b1
                                           # 5.9.1b1  → 5.9.1b2
    scripts/bump_version.py release        # 5.9.0b3  → 5.9.0  (drop beta tag)
    scripts/bump_version.py 5.10.2[b1]     # explicit version

Flags:
    --dry-run    Печатает план, файлы не трогает.
    --print      Только напечатать текущую версию.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
MANIFEST = ROOT / "custom_components" / "sberhome" / "manifest.json"

# X.Y.Z [a|b|rc N]  — PEP 440 subset, достаточный для этого проекта.
VERSION_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:(?P<pre_kind>a|b|rc)(?P<pre_num>\d+))?$"
)


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    pre_kind: str | None = None  # "a" | "b" | "rc" | None
    pre_num: int | None = None

    @classmethod
    def parse(cls, raw: str) -> Version:
        m = VERSION_RE.match(raw.strip())
        if not m:
            raise ValueError(f"Invalid version: {raw!r}")
        return cls(
            major=int(m["major"]),
            minor=int(m["minor"]),
            patch=int(m["patch"]),
            pre_kind=m["pre_kind"],
            pre_num=int(m["pre_num"]) if m["pre_num"] else None,
        )

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_kind is not None:
            s += f"{self.pre_kind}{self.pre_num}"
        return s

    @property
    def is_prerelease(self) -> bool:
        return self.pre_kind is not None


# ---------------------------------------------------------------------------
# read / write
# ---------------------------------------------------------------------------


def read_pyproject_version() -> str:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if not m:
        raise RuntimeError(f"version not found in {PYPROJECT}")
    return m.group(1)


def write_pyproject_version(new: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'(?m)^(version\s*=\s*)"[^"]+"',
        lambda m: f'{m.group(1)}"{new}"',
        text,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"failed to update version in {PYPROJECT}")
    PYPROJECT.write_text(new_text, encoding="utf-8")


def read_manifest_version() -> str:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if "version" not in data:
        raise RuntimeError(f"version key not found in {MANIFEST}")
    return data["version"]


def write_manifest_version(new: str) -> None:
    """Replace the version value while preserving file formatting verbatim."""
    text = MANIFEST.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'("version"\s*:\s*)"[^"]+"',
        lambda m: f'{m.group(1)}"{new}"',
        text,
        count=1,
    )
    if n != 1:
        raise RuntimeError(f"failed to update version in {MANIFEST}")
    MANIFEST.write_text(new_text, encoding="utf-8")


# ---------------------------------------------------------------------------
# bump rules
# ---------------------------------------------------------------------------


def bump(current: Version, action: str) -> Version:
    if action == "major":
        return Version(current.major + 1, 0, 0)
    if action == "minor":
        return Version(current.major, current.minor + 1, 0)
    if action == "patch":
        # 5.9.1b1 → patch = drop beta, keep 5.9.1 (finalise this patch)
        if current.is_prerelease:
            return Version(current.major, current.minor, current.patch)
        return Version(current.major, current.minor, current.patch + 1)
    if action == "beta":
        if current.is_prerelease and current.pre_kind == "b":
            return Version(
                current.major, current.minor, current.patch, "b", (current.pre_num or 0) + 1
            )
        # stable → start a new beta series for the next patch
        return Version(current.major, current.minor, current.patch + 1, "b", 1)
    if action == "release":
        if not current.is_prerelease:
            raise SystemExit(f"already a stable release: {current}")
        return Version(current.major, current.minor, current.patch)
    raise ValueError(f"unknown action: {action}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


KEYWORDS = {"major", "minor", "patch", "beta", "release"}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Bump project version in pyproject.toml and manifest.json (kept in sync).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "action",
        nargs="?",
        help="major | minor | patch | beta | release | <explicit version like 5.10.2 or 5.10.2b1>",
    )
    p.add_argument("--dry-run", action="store_true", help="show plan, don't touch files")
    p.add_argument("--print", action="store_true", help="print current version and exit")
    args = p.parse_args()

    py_v = read_pyproject_version()
    mf_v = read_manifest_version()

    if py_v != mf_v:
        print(
            f"⚠  versions out of sync: pyproject={py_v} manifest={mf_v}\n"
            f"   resolve by running with an explicit version.",
            file=sys.stderr,
        )
        if not args.action:
            return 1

    current = Version.parse(py_v)

    if args.print:
        print(current)
        return 0

    if not args.action:
        p.error("action is required (or pass --print)")

    if args.action in KEYWORDS:
        new = bump(current, args.action)
    else:
        try:
            new = Version.parse(args.action)
        except ValueError as e:
            p.error(str(e))

    if str(new) == str(current):
        print(f"= {current} (no change)")
        return 0

    print(f"  pyproject.toml   {py_v}  →  {new}")
    print(f"  manifest.json    {mf_v}  →  {new}")

    if args.dry_run:
        print("(dry-run — files not modified)")
        return 0

    write_pyproject_version(str(new))
    write_manifest_version(str(new))
    print(f"✓ bumped to {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
