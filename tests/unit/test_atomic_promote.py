# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `cache.atomic` — temp-then-promote, FAILED marker, trashing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modelfoundry.cache.atomic import FAILED_MARKER, materialize_temp_dir, trash_existing
from modelfoundry.cache.identity import CacheKey
from modelfoundry.cache.layout import CachePaths
from modelfoundry.core.errors import (
    CacheError,
    MaterializeError,
    ModelArtifactExistsError,
)

KEY = CacheKey(recipe_hash16="aaaa1111bbbb2222", data_instance_hash16="cccc3333dddd4444", seed=7)


def test_clean_exit_promotes(tmp_path: Path) -> None:
    paths = CachePaths(tmp_path, KEY)
    with materialize_temp_dir(tmp_path, KEY) as temp:
        (temp / "manifest.json").write_text("{}", encoding="utf-8")
    # Temp dir is gone; final instance dir holds the contents.
    assert not temp.exists()
    assert paths.instance_dir.is_dir()
    assert (paths.instance_dir / "manifest.json").read_text() == "{}"


def test_exception_leaves_failed_marker_and_temp(tmp_path: Path) -> None:
    paths = CachePaths(tmp_path, KEY)
    captured: dict[str, Path] = {}
    with (
        pytest.raises(MaterializeError, match="boom"),
        materialize_temp_dir(tmp_path, KEY) as temp,
    ):
        captured["temp"] = temp
        (temp / "partial.txt").write_text("half", encoding="utf-8")
        raise MaterializeError("boom", stage="training")

    temp = captured["temp"]
    assert temp.is_dir()  # left intact for diagnosis
    assert not paths.instance_dir.exists()  # final path never touched
    marker = json.loads((temp / FAILED_MARKER).read_text())
    assert marker["stage"] == "training"
    assert marker["error_class"] == "MaterializeError"
    assert marker["message"] == "boom"
    assert "MaterializeError" in marker["traceback"]


def test_failed_marker_stage_none_for_plain_exception(tmp_path: Path) -> None:
    captured: dict[str, Path] = {}
    with (
        pytest.raises(ValueError),
        materialize_temp_dir(tmp_path, KEY) as temp,
    ):
        captured["temp"] = temp
        raise ValueError("plain")
    marker = json.loads((captured["temp"] / FAILED_MARKER).read_text())
    assert marker["stage"] is None
    assert marker["error_class"] == "ValueError"


def test_promote_refuses_when_instance_exists(tmp_path: Path) -> None:
    paths = CachePaths(tmp_path, KEY)
    # First materialize succeeds.
    with materialize_temp_dir(tmp_path, KEY) as temp:
        (temp / "a.txt").write_text("1", encoding="utf-8")
    # Second materialize for the same key fails cleanly at promote (OR-10).
    with (
        pytest.raises(ModelArtifactExistsError, match="already exists"),
        materialize_temp_dir(tmp_path, KEY) as temp,
    ):
        (temp / "b.txt").write_text("2", encoding="utf-8")
    # Original instance is untouched.
    assert (paths.instance_dir / "a.txt").read_text() == "1"
    assert not (paths.instance_dir / "b.txt").exists()


def test_cross_device_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_device_id(path: Path) -> int:
        # temp dir parent on device 1, final parent on device 2.
        return 1 if ".tmp" in str(path) else 2

    monkeypatch.setattr("modelfoundry.cache.atomic._device_id", fake_device_id)
    with (
        pytest.raises(MaterializeError, match="across filesystems"),
        materialize_temp_dir(tmp_path, KEY) as temp,
    ):
        (temp / "x").write_text("y", encoding="utf-8")


def test_trash_existing_moves_not_deletes(tmp_path: Path) -> None:
    paths = CachePaths(tmp_path, KEY)
    with materialize_temp_dir(tmp_path, KEY) as temp:
        (temp / "weights.pt").write_text("W", encoding="utf-8")

    dest = trash_existing(tmp_path, KEY)
    assert not paths.instance_dir.exists()  # moved out of the live path
    assert dest.is_dir()
    assert (dest / "weights.pt").read_text() == "W"
    assert dest.is_relative_to(paths.cache_root / ".trash")


def test_trash_existing_enables_reuse_of_key(tmp_path: Path) -> None:
    paths = CachePaths(tmp_path, KEY)
    with materialize_temp_dir(tmp_path, KEY) as temp:
        (temp / "old.txt").write_text("old", encoding="utf-8")
    trash_existing(tmp_path, KEY)
    # After trashing, the key's path is free again for a fresh promote.
    with materialize_temp_dir(tmp_path, KEY) as temp:
        (temp / "new.txt").write_text("new", encoding="utf-8")
    assert (paths.instance_dir / "new.txt").read_text() == "new"
    assert not (paths.instance_dir / "old.txt").exists()


def test_trash_existing_raises_when_absent(tmp_path: Path) -> None:
    with pytest.raises(CacheError, match="no instance to trash"):
        trash_existing(tmp_path, KEY)


def test_explicit_run_id_used(tmp_path: Path) -> None:
    paths = CachePaths(tmp_path, KEY)
    with (
        pytest.raises(ValueError),
        materialize_temp_dir(tmp_path, KEY, run_id="run-xyz") as temp,
    ):
        assert temp == paths.tmp_dir("run-xyz")
        raise ValueError("stop")
