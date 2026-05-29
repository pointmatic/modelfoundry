# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""On-disk ModelInstance directory layout.

`CachePaths` turns a `(cache_root, CacheKey)` pair into every path inside an
instance directory. The instance root is
`<cache-root>/instances/<recipe-hash16>/<data-instance-hash16>/<seed>/`. The
cache root is resolved to an absolute path in the constructor so every helper
returns an absolute path that never escapes the root.

This module owns path *shapes* only; it creates no directories and writes no
files. Atomic promotion (`cache.atomic`) and the materialize runner own I/O.
"""

from __future__ import annotations

from pathlib import Path

from modelfoundry.cache.identity import CacheKey

_INSTANCES = "instances"
_TMP = ".tmp"
_TRASH = ".trash"


class CachePaths:
    """Path helpers for one ModelInstance under a cache root."""

    def __init__(self, cache_root: str | Path, key: CacheKey) -> None:
        self.cache_root = Path(cache_root).resolve()
        self.key = key

    # --- instance root ---

    @property
    def instances_root(self) -> Path:
        return self.cache_root / _INSTANCES

    @property
    def instance_dir(self) -> Path:
        return (
            self.instances_root
            / self.key.recipe_hash16
            / self.key.data_instance_hash16
            / str(self.key.seed)
        )

    @property
    def recipe_yaml(self) -> Path:
        return self.instance_dir / "recipe.yml"

    @property
    def manifest_json(self) -> Path:
        return self.instance_dir / "manifest.json"

    # --- model ---

    @property
    def model_dir(self) -> Path:
        return self.instance_dir / "model"

    @property
    def weights_dir(self) -> Path:
        return self.model_dir / "weights"

    @property
    def architecture_json(self) -> Path:
        return self.model_dir / "architecture.json"

    @property
    def tokenizer_dir(self) -> Path:
        return self.model_dir / "tokenizer"

    @property
    def checkpoints_dir(self) -> Path:
        return self.model_dir / "checkpoints"

    # --- training ---

    @property
    def training_dir(self) -> Path:
        return self.instance_dir / "training"

    @property
    def training_history(self) -> Path:
        return self.training_dir / "history.parquet"

    # --- optimization ---

    @property
    def optimization_dir(self) -> Path:
        return self.instance_dir / "optimization"

    @property
    def trials_parquet(self) -> Path:
        return self.optimization_dir / "trials.parquet"

    @property
    def study_db(self) -> Path:
        return self.optimization_dir / "study.db"

    @property
    def best_params_json(self) -> Path:
        return self.optimization_dir / "best-params.json"

    # --- evaluation ---

    @property
    def evaluation_dir(self) -> Path:
        return self.instance_dir / "evaluation"

    @property
    def metrics_json(self) -> Path:
        return self.evaluation_dir / "metrics.json"

    @property
    def confusion_matrix_npz(self) -> Path:
        return self.evaluation_dir / "confusion_matrix.npz"

    @property
    def calibration_parquet(self) -> Path:
        return self.evaluation_dir / "calibration.parquet"

    @property
    def predictions_parquet(self) -> Path:
        return self.evaluation_dir / "predictions.parquet"

    # --- report ---

    @property
    def report_dir(self) -> Path:
        return self.instance_dir / "report"

    @property
    def report_md(self) -> Path:
        return self.report_dir / "report.md"

    @property
    def report_viz_dir(self) -> Path:
        return self.report_dir / "visualizations"

    # --- cache-root-level scratch areas ---

    def tmp_dir(self, run_id: str) -> Path:
        """`<cache-root>/instances/.tmp/<run-id>/` — the pre-promote staging dir."""
        return self.instances_root / _TMP / run_id

    def trash_dir(self, timestamp: str) -> Path:
        """`<cache-root>/.trash/<timestamp>/` — displaced instances on `--overwrite`."""
        return self.cache_root / _TRASH / timestamp
