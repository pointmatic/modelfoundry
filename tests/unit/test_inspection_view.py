# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `InspectionView` accessor object (Story D.g.1, FR-17 behavior 1).

`ModelInstance.inspect()` (no arg) returns an `InspectionView` exposing the six
notebook-facing accessors. Data accessors (`view_trials`, `view_predictions`,
`view_manifest`) are torch/matplotlib-free; PNG accessors (`view_training_curves`,
`view_confusion_matrix`, `view_calibration`) `importorskip("matplotlib")`. The
fixture instance is hand-built from artifact files — no real training.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from modelfoundry.core.errors import InspectionError
from modelfoundry.core.instance import InspectionView, ModelInstance
from modelfoundry.core.manifest import Manifest


def _build_instance(
    tmp_path: Path,
    *,
    with_eval: bool = True,
    with_predictions: bool = True,
    with_trials: bool = True,
) -> Path:
    import pandas as pd  # type: ignore[import-untyped]

    inst = tmp_path / "instance"
    inst.mkdir(parents=True)

    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {"num_classes": 2, "layers": [{"op": "Flatten"}]},
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {
            "max_epochs": 1,
            "batch_size": 4,
            "device": "cpu",
            "precision": "fp32",
            "checkpoint_cadence": 1,
        },
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy"],
            "calibration_bins": 10,
        },
        "Visualizations": [],
        "OutputExpectations": [],
    }
    (inst / "recipe.yml").write_text(yaml.safe_dump(recipe), encoding="utf-8")

    Manifest(
        plugin="pytorch",
        plugin_version="0.4.0",
        recipe_hash="a" * 64,
        data_instance_hash="b" * 64,
        bound_data_instance=Path("/dr/cache/instances/abc/def/1"),
        seed=7,
        variant=None,
        created_at=datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC),
        elapsed_seconds=1.5,
        epoch_history=1,
        evaluation={"val": {"accuracy": 0.9}},
        output_expectations=[],
    ).write(inst / "manifest.json")

    if with_eval:
        eval_dir = inst / "evaluation"
        eval_dir.mkdir()
        (eval_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "val": {
                        "accuracy": 0.9,
                        "confusion_matrix": [[4, 1], [0, 5]],
                        "calibration_curve": {
                            "mean_confidence": [0.6, 0.9],
                            "accuracy": [0.6, 0.9],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        if with_predictions:
            pd.DataFrame(
                [
                    {"split": "val", "record_id": i, "true_label": "a", "pred_label": "a"}
                    for i in range(5)
                ]
            ).to_parquet(eval_dir / "predictions.parquet", index=False)

    if with_trials:
        opt_dir = inst / "optimization"
        opt_dir.mkdir()
        pd.DataFrame(
            [
                {"number": 0, "value": 0.7, "state": "COMPLETE"},
                {"number": 1, "value": 0.8, "state": "COMPLETE"},
            ]
        ).to_parquet(opt_dir / "trials.parquet", index=False)

    return inst


# --- inspect() returns the view object ---


def test_inspect_no_arg_returns_inspection_view(tmp_path: Path) -> None:
    view = ModelInstance.load(_build_instance(tmp_path)).inspect()
    assert isinstance(view, InspectionView)


def _view(tmp_path: Path, **kw: bool) -> InspectionView:
    result = ModelInstance.load(_build_instance(tmp_path, **kw)).inspect()
    assert isinstance(result, InspectionView)
    return result


# --- data accessors (torch/matplotlib-free) ---


def test_view_manifest_returns_manifest(tmp_path: Path) -> None:
    assert isinstance(_view(tmp_path).view_manifest(), Manifest)


def test_view_trials_returns_dataframe(tmp_path: Path) -> None:
    trials = _view(tmp_path).view_trials()
    assert len(trials) == 2


def test_view_trials_raises_without_optimization(tmp_path: Path) -> None:
    with pytest.raises(InspectionError):
        _view(tmp_path, with_trials=False).view_trials()


def test_view_predictions_honors_n(tmp_path: Path) -> None:
    rows = _view(tmp_path).view_predictions("val", 2)
    assert len(rows) == 2


def test_view_predictions_raises_when_absent(tmp_path: Path) -> None:
    with pytest.raises(InspectionError):
        _view(tmp_path, with_predictions=False).view_predictions("val", 5)


def test_view_predictions_raises_for_unknown_split(tmp_path: Path) -> None:
    with pytest.raises(InspectionError):
        _view(tmp_path).view_predictions("test", 5)


# --- PNG accessors ---


def test_view_training_curves_returns_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    png = _view(tmp_path).view_training_curves()
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_view_confusion_matrix_returns_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    png = _view(tmp_path).view_confusion_matrix("val")
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_view_confusion_matrix_raises_for_missing_split(tmp_path: Path) -> None:
    with pytest.raises(InspectionError):
        _view(tmp_path).view_confusion_matrix("test")


def test_view_calibration_returns_png(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    png = _view(tmp_path).view_calibration("val")
    assert isinstance(png, bytes) and png[:8] == b"\x89PNG\r\n\x1a\n"
