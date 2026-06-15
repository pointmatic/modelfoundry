# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Cache cleaning selectors (FR-20, Story D.h).

`select_targets` enumerates the directories a `clean` invocation would remove,
honoring four composable selectors; `remove_targets` deletes them (or, in
dry-run, reports them). Targets are de-duplicated so a parent (e.g. a whole
`--recipe-hash` tree) supersedes any of its descendants selected by another rule.

Cache layout (see `cache.layout`):

    <cache-root>/instances/<rh16>/<dh16>/<seed>/manifest.json   promoted instance
    <cache-root>/instances/.tmp/<run-id>/[FAILED]               in-flight / failed run
    <cache-root>/.trash/<timestamp>/...                         displaced by --overwrite

Age comes from `manifest.created_at` for promoted instances (per FR-20) and from
directory mtime for trash / orphan temp dirs, which carry no manifest.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from modelfoundry.core.errors import CacheError

_INSTANCES = "instances"
_TMP = ".tmp"
_TRASH = ".trash"
_FAILED_MARKER = "FAILED"

_DURATION = re.compile(r"^(\d+)([smhdw])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


@dataclass(frozen=True)
class CleanTarget:
    """One directory selected for removal, with the selector that chose it."""

    path: Path
    reason: str  # recipe-hash | older-than | trash | failed | orphan


@dataclass
class CleanResult:
    """Outcome of `remove_targets`: what was removed and what failed."""

    removed: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)


def parse_duration(text: str) -> timedelta:
    """Parse a `<int><unit>` duration (`s`/`m`/`h`/`d`/`w`) into a `timedelta`."""
    match = _DURATION.match(text.strip())
    if match is None:
        raise CacheError(
            f"invalid duration {text!r}; expected e.g. '7d', '24h', '30m', '60s', '2w'",
            detail={"duration": text},
        )
    return timedelta(seconds=int(match.group(1)) * _UNIT_SECONDS[match.group(2)])


def select_targets(
    cache_root: str | Path,
    *,
    recipe_hash: str | None = None,
    older_than: timedelta | None = None,
    failed: bool = False,
    orphans: bool = False,
    now: datetime | None = None,
) -> list[CleanTarget]:
    """Enumerate the directories the active selectors would remove (no I/O beyond stat/read)."""
    root = Path(cache_root).resolve()
    now = now or datetime.now(UTC)
    targets: list[CleanTarget] = []

    if recipe_hash is not None:
        rh16 = recipe_hash[:16]
        tree = root / _INSTANCES / rh16
        if tree.is_dir():
            targets.append(CleanTarget(path=tree, reason="recipe-hash"))

    if older_than is not None:
        cutoff = now - older_than
        targets.extend(_old_promoted(root, cutoff))
        targets.extend(_old_trash(root, cutoff))

    if failed:
        targets.extend(_failed_temp(root))

    if orphans and older_than is not None:
        targets.extend(_orphan_temp(root, now - older_than))

    return _prune_descendants(targets)


def remove_targets(targets: list[CleanTarget], *, dry_run: bool = False) -> CleanResult:
    """Delete each target's directory; in dry-run, remove nothing. Per-dir errors are collected."""
    result = CleanResult()
    if dry_run:
        return result
    for target in targets:
        try:
            shutil.rmtree(target.path)
            result.removed.append(target.path)
        except OSError as exc:
            result.failed.append((target.path, str(exc)))
    return result


# --- enumeration helpers ---


def _promoted_instances(root: Path) -> list[Path]:
    """Every `instances/<rh16>/<dh16>/<seed>/` dir carrying a `manifest.json`."""
    instances = root / _INSTANCES
    if not instances.is_dir():
        return []
    found: list[Path] = []
    for rh in instances.iterdir():
        if rh.name == _TMP or not rh.is_dir():
            continue
        for dh in rh.iterdir():
            if not dh.is_dir():
                continue
            for seed in dh.iterdir():
                if seed.is_dir() and (seed / "manifest.json").is_file():
                    found.append(seed)
    return found


def _old_promoted(root: Path, cutoff: datetime) -> list[CleanTarget]:
    from modelfoundry.core.manifest import Manifest

    targets: list[CleanTarget] = []
    for inst in _promoted_instances(root):
        created_at = Manifest.load(inst / "manifest.json").created_at
        if created_at < cutoff:
            targets.append(CleanTarget(path=inst, reason="older-than"))
    return targets


def _old_trash(root: Path, cutoff: datetime) -> list[CleanTarget]:
    trash = root / _TRASH
    if not trash.is_dir():
        return []
    return [
        CleanTarget(path=d, reason="trash")
        for d in trash.iterdir()
        if d.is_dir() and _mtime(d) < cutoff
    ]


def _temp_dirs(root: Path) -> list[Path]:
    tmp = root / _INSTANCES / _TMP
    return [d for d in tmp.iterdir() if d.is_dir()] if tmp.is_dir() else []


def _failed_temp(root: Path) -> list[CleanTarget]:
    return [
        CleanTarget(path=d, reason="failed")
        for d in _temp_dirs(root)
        if (d / _FAILED_MARKER).is_file()
    ]


def _orphan_temp(root: Path, cutoff: datetime) -> list[CleanTarget]:
    return [
        CleanTarget(path=d, reason="orphan")
        for d in _temp_dirs(root)
        if not (d / _FAILED_MARKER).is_file() and _mtime(d) < cutoff
    ]


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _prune_descendants(targets: list[CleanTarget]) -> list[CleanTarget]:
    """Drop any target whose path lies inside another selected target (and exact dups)."""
    kept: list[CleanTarget] = []
    seen: set[Path] = set()
    selected = {t.path for t in targets}
    for target in targets:
        if target.path in seen:
            continue
        if any(parent in selected for parent in target.path.parents):
            continue
        seen.add(target.path)
        kept.append(target)
    return kept
