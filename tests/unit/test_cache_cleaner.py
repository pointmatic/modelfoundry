# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `cache.cleaner` selector logic (Story D.h, FR-20)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from modelfoundry.cache.cleaner import (
    CleanTarget,
    parse_duration,
    remove_targets,
    select_targets,
)
from modelfoundry.core.errors import CacheError
from modelfoundry.core.manifest import Manifest

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


def _instance(cache_root: Path, rh16: str, dh16: str, seed: int, created_at: datetime) -> Path:
    d = cache_root / "instances" / rh16 / dh16 / str(seed)
    d.mkdir(parents=True)
    Manifest(
        plugin="pytorch",
        plugin_version="0.4.0",
        recipe_hash=rh16 + "0" * 48,
        data_instance_hash=dh16 + "0" * 48,
        bound_data_instance=Path("/dr/x"),
        seed=seed,
        variant=None,
        created_at=created_at,
        elapsed_seconds=1.0,
        epoch_history=1,
        evaluation={"val": {"accuracy": 0.9}},
        output_expectations=[],
    ).write(d / "manifest.json")
    return d


def _temp(cache_root: Path, run_id: str, *, failed: bool, mtime: datetime) -> Path:
    d = cache_root / "instances" / ".tmp" / run_id
    d.mkdir(parents=True)
    if failed:
        (d / "FAILED").write_text("{}", encoding="utf-8")
    os.utime(d, (mtime.timestamp(), mtime.timestamp()))
    return d


def _trash(cache_root: Path, ts: str, *, mtime: datetime) -> Path:
    d = cache_root / ".trash" / ts
    d.mkdir(parents=True)
    os.utime(d, (mtime.timestamp(), mtime.timestamp()))
    return d


def _paths(targets: list[CleanTarget]) -> set[Path]:
    return {t.path for t in targets}


# --- parse_duration ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("60s", timedelta(seconds=60)),
        ("30m", timedelta(minutes=30)),
        ("24h", timedelta(hours=24)),
        ("7d", timedelta(days=7)),
        ("2w", timedelta(weeks=2)),
    ],
)
def test_parse_duration_units(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("bad", ["", "7", "d", "7y", "-3d", "abc"])
def test_parse_duration_invalid_raises(bad: str) -> None:
    with pytest.raises(CacheError):
        parse_duration(bad)


# --- select_targets ---


def test_recipe_hash_targets_the_recipe_tree(tmp_path: Path) -> None:
    _instance(tmp_path, "aaaa111122223333", "dddd", 0, _NOW)
    _instance(tmp_path, "bbbb444455556666", "dddd", 0, _NOW)
    targets = select_targets(tmp_path, recipe_hash="aaaa111122223333", now=_NOW)
    assert _paths(targets) == {tmp_path / "instances" / "aaaa111122223333"}
    assert targets[0].reason == "recipe-hash"


def test_recipe_hash_truncates_full_hash(tmp_path: Path) -> None:
    _instance(tmp_path, "aaaa111122223333", "dddd", 0, _NOW)
    targets = select_targets(tmp_path, recipe_hash="aaaa111122223333" + "f" * 48, now=_NOW)
    assert _paths(targets) == {tmp_path / "instances" / "aaaa111122223333"}


def test_older_than_targets_old_promoted_instances(tmp_path: Path) -> None:
    old = _instance(tmp_path, "aaaa", "d1", 0, _NOW - timedelta(days=30))
    _instance(tmp_path, "bbbb", "d2", 0, _NOW - timedelta(days=1))
    targets = select_targets(tmp_path, older_than=timedelta(days=7), now=_NOW)
    assert _paths(targets) == {old}
    assert targets[0].reason == "older-than"


def test_older_than_targets_old_trash(tmp_path: Path) -> None:
    old = _trash(tmp_path, "20260501T000000_0Z", mtime=_NOW - timedelta(days=30))
    _trash(tmp_path, "20260614T000000_0Z", mtime=_NOW - timedelta(days=1))
    targets = select_targets(tmp_path, older_than=timedelta(days=7), now=_NOW)
    assert old in _paths(targets)
    assert all(t.reason in ("older-than", "trash") for t in targets)


def test_failed_targets_failed_temp_dirs_only(tmp_path: Path) -> None:
    failed = _temp(tmp_path, "run-a", failed=True, mtime=_NOW)
    _temp(tmp_path, "run-b", failed=False, mtime=_NOW)
    targets = select_targets(tmp_path, failed=True, now=_NOW)
    assert _paths(targets) == {failed}
    assert targets[0].reason == "failed"


def test_orphans_targets_old_unmarked_temp_dirs(tmp_path: Path) -> None:
    orphan = _temp(tmp_path, "run-a", failed=False, mtime=_NOW - timedelta(days=30))
    _temp(tmp_path, "run-b", failed=False, mtime=_NOW - timedelta(hours=1))  # too recent
    _temp(tmp_path, "run-c", failed=True, mtime=_NOW - timedelta(days=30))  # failed, not orphan
    targets = select_targets(tmp_path, orphans=True, older_than=timedelta(days=7), now=_NOW)
    assert _paths(targets) == {orphan}
    assert targets[0].reason == "orphan"


def test_no_selectors_returns_nothing(tmp_path: Path) -> None:
    _instance(tmp_path, "aaaa", "d1", 0, _NOW - timedelta(days=99))
    assert select_targets(tmp_path, now=_NOW) == []


# --- remove_targets ---


def test_remove_targets_dry_run_removes_nothing(tmp_path: Path) -> None:
    d = _instance(tmp_path, "aaaa", "d1", 0, _NOW)
    result = remove_targets([CleanTarget(path=d, reason="older-than")], dry_run=True)
    assert d.exists()
    assert result.removed == []


def test_remove_targets_removes_directories(tmp_path: Path) -> None:
    d = _instance(tmp_path, "aaaa", "d1", 0, _NOW)
    result = remove_targets([CleanTarget(path=d, reason="older-than")])
    assert not d.exists()
    assert result.removed == [d]
    assert result.failed == []
