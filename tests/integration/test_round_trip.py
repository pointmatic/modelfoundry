# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Round-trip integration test — TR-6 / FR-23.

A materialized ModelInstance is **self-contained**: `ModelInstance.load(path)`
needs only the instance directory (no `RuntimeConfig`, no recipe handle, no live
DataRefinery instance) and its `predict` / `predict_proba` reproduce the
in-process model's outputs. We prove self-containment by deleting the upstream
DataRefinery instance before reloading and predicting.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

from modelfoundry.core.config import RuntimeConfig

torch = pytest.importorskip("torch")

_IMAGE_SIZE = 4
_NUM_CLASSES = 3


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def _write_recipe(path: Path) -> Path:
    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "num_classes": _NUM_CLASSES,
            "layers": [
                {"op": "Flatten"},
                {
                    "op": "Linear",
                    "in_features": _IMAGE_SIZE * _IMAGE_SIZE * 3,
                    "out_features": _NUM_CLASSES,
                },
            ],
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {"max_epochs": 1, "batch_size": 4, "num_workers": 0, "device": "cpu"},
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1"],
        },
    }
    path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    return path


def test_load_predict_is_self_contained_and_matches(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    dr_root = tmp_path / "dr"
    data = build_dr_instance(
        dr_root, split_counts={"train": 16, "val": 8}, image_size=_IMAGE_SIZE
    )
    config = RuntimeConfig(cache_root=tmp_path / "cache")
    instance = ModelFoundry.from_recipe(
        _write_recipe(tmp_path / "recipe.yml"), data=data, config=config
    ).materialize()

    rng = np.random.default_rng(0)
    x = rng.random((5, _IMAGE_SIZE, _IMAGE_SIZE, 3), dtype=np.float32)
    in_proc_pred = instance.predict(x)
    in_proc_proba = instance.predict_proba(x)

    # Self-containment (FR-23): delete the upstream DataRefinery instance, then
    # reload purely from the instance directory — no config, no recipe, no plugin
    # handle. `predict` loads the model from `<instance>/model`, never upstream.
    shutil.rmtree(dr_root)
    reloaded = ModelInstance.load(instance.path)

    assert np.array_equal(in_proc_pred, reloaded.predict(x))
    assert np.allclose(in_proc_proba, reloaded.predict_proba(x))
    # The reloaded instance serves its evaluation metrics from disk alone.
    assert "val" in reloaded.metrics
