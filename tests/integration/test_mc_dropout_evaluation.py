# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""MC-dropout aggregation + persistence + accessor (Story H.n, R2.2 / R2.3).

A recipe declaring `Inference: {mode: mc_dropout, mc_samples: T}` materializes
with the MC-aggregated mean as the deployed prediction and per-record predictive
uncertainty persisted into `evaluation/predictions.parquet`; the `ModelInstance`
accessor reconstructs mean + uncertainty from disk alone (criterion 3 / 9). A
recipe without the block keeps the single-pass point-estimate path byte-for-byte
(criterion 5).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

from modelfoundry.core.config import RuntimeConfig

torch = pytest.importorskip("torch")

_IMAGE_SIZE = 4
_NUM_CLASSES = 3
_FEATURES = _IMAGE_SIZE * _IMAGE_SIZE * 3
_UNCERTAINTY_COLUMNS = ("predictive_entropy", "mc_variance")


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def _recipe_dict(*, mc_samples: int | None) -> dict[str, Any]:
    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "num_classes": _NUM_CLASSES,
            "layers": [
                {"op": "Flatten"},
                {"op": "Linear", "in_features": _FEATURES, "out_features": 16},
                {"op": "ReLU"},
                {"op": "Dropout", "p": 0.5},
                {"op": "Linear", "in_features": 16, "out_features": _NUM_CLASSES},
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
    if mc_samples is not None:
        recipe["Inference"] = {"mode": "mc_dropout", "mc_samples": mc_samples}
    return recipe


def _materialize(tmp_path: Path, data: Any, *, tag: str, mc_samples: int | None) -> Any:
    from modelfoundry import ModelFoundry

    recipe_path = tmp_path / f"recipe_{tag}.yml"
    recipe_path.write_text(yaml.safe_dump(_recipe_dict(mc_samples=mc_samples)), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp_path / f"cache_{tag}")
    return ModelFoundry.from_recipe(recipe_path, data=data, config=config).materialize()


@pytest.fixture
def data(tmp_path: Path) -> Any:
    return build_dr_instance(
        tmp_path / "dr", split_counts={"train": 16, "val": 8}, image_size=_IMAGE_SIZE
    )


def test_mc_dropout_persists_uncertainty_columns(tmp_path: Path, data: Any) -> None:
    instance = _materialize(tmp_path, data, tag="mc", mc_samples=16)
    preds = instance.predictions
    assert preds is not None
    for col in _UNCERTAINTY_COLUMNS:
        assert col in preds.columns
    # Uncertainty is non-negative and present for every evaluated record.
    assert (preds["predictive_entropy"] >= 0).all()
    assert (preds["mc_variance"] >= 0).all()
    assert preds["predictive_entropy"].notna().all()


def test_point_mode_persists_no_uncertainty_columns(tmp_path: Path, data: Any) -> None:
    instance = _materialize(tmp_path, data, tag="pt", mc_samples=None)
    preds = instance.predictions
    assert preds is not None
    for col in _UNCERTAINTY_COLUMNS:
        assert col not in preds.columns


def test_uncertainty_accessor_reconstructs_from_disk(tmp_path: Path, data: Any) -> None:
    from modelfoundry.core.instance import ModelInstance

    instance = _materialize(tmp_path, data, tag="mc", mc_samples=16)
    # Reload from disk alone — no external config object.
    reloaded = ModelInstance.load(instance.path)
    uncertainty = reloaded.uncertainty
    assert uncertainty is not None
    assert set(_UNCERTAINTY_COLUMNS).issubset(uncertainty.columns)
    assert len(uncertainty) == len(reloaded.predictions)


def test_point_mode_uncertainty_accessor_is_none(tmp_path: Path, data: Any) -> None:
    instance = _materialize(tmp_path, data, tag="pt", mc_samples=None)
    assert instance.uncertainty is None


def test_mc_dropout_predictions_are_deterministic(tmp_path: Path, data: Any) -> None:
    first = _materialize(tmp_path, data, tag="a", mc_samples=16).path
    second = _materialize(tmp_path, data, tag="b", mc_samples=16).path
    a = (first / "evaluation" / "predictions.parquet").read_bytes()
    b = (second / "evaluation" / "predictions.parquet").read_bytes()
    assert a == b
