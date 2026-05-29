# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `cache.layout.CachePaths`."""

from __future__ import annotations

from pathlib import Path

import pytest

from modelfoundry.cache.identity import CacheKey
from modelfoundry.cache.layout import CachePaths

KEY = CacheKey(recipe_hash16="aaaa1111bbbb2222", data_instance_hash16="cccc3333dddd4444", seed=7)

# Every path-property name and its expected suffix relative to the instance dir
# (or the cache root for the scratch helpers).
INSTANCE_RELATIVE = {
    "recipe_yaml": "recipe.yml",
    "manifest_json": "manifest.json",
    "model_dir": "model",
    "weights_dir": "model/weights",
    "architecture_json": "model/architecture.json",
    "tokenizer_dir": "model/tokenizer",
    "checkpoints_dir": "model/checkpoints",
    "training_dir": "training",
    "training_history": "training/history.parquet",
    "optimization_dir": "optimization",
    "trials_parquet": "optimization/trials.parquet",
    "study_db": "optimization/study.db",
    "best_params_json": "optimization/best-params.json",
    "evaluation_dir": "evaluation",
    "metrics_json": "evaluation/metrics.json",
    "confusion_matrix_npz": "evaluation/confusion_matrix.npz",
    "calibration_parquet": "evaluation/calibration.parquet",
    "predictions_parquet": "evaluation/predictions.parquet",
    "report_dir": "report",
    "report_md": "report/report.md",
    "report_viz_dir": "report/visualizations",
}


@pytest.fixture
def paths(tmp_path: Path) -> CachePaths:
    return CachePaths(tmp_path / "models", KEY)


def test_instance_dir_layout(paths: CachePaths) -> None:
    assert paths.instance_dir == (
        paths.cache_root / "instances" / "aaaa1111bbbb2222" / "cccc3333dddd4444" / "7"
    )


@pytest.mark.parametrize("attr,suffix", INSTANCE_RELATIVE.items())
def test_instance_relative_paths(paths: CachePaths, attr: str, suffix: str) -> None:
    resolved = getattr(paths, attr)
    assert resolved == paths.instance_dir / suffix


@pytest.mark.parametrize("attr", [*INSTANCE_RELATIVE, "instance_dir", "instances_root"])
def test_all_paths_absolute_and_within_root(paths: CachePaths, attr: str) -> None:
    resolved = getattr(paths, attr)
    assert resolved.is_absolute()
    assert resolved.is_relative_to(paths.cache_root)


def test_tmp_dir(paths: CachePaths) -> None:
    tmp = paths.tmp_dir("run-123")
    assert tmp == paths.cache_root / "instances" / ".tmp" / "run-123"
    assert tmp.is_absolute()
    assert tmp.is_relative_to(paths.cache_root)


def test_trash_dir(paths: CachePaths) -> None:
    trash = paths.trash_dir("20260528T120000Z")
    assert trash == paths.cache_root / ".trash" / "20260528T120000Z"
    assert trash.is_absolute()
    assert trash.is_relative_to(paths.cache_root)


def test_relative_cache_root_is_resolved_absolute() -> None:
    paths = CachePaths("models", KEY)
    assert paths.cache_root.is_absolute()
    assert paths.instance_dir.is_absolute()


def test_no_helper_creates_directories(paths: CachePaths) -> None:
    # Pure path computation — touching a property must not create anything.
    _ = paths.instance_dir
    _ = paths.weights_dir
    _ = paths.tmp_dir("x")
    assert not paths.cache_root.exists()
