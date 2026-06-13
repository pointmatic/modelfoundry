# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PyTorch visualization renderers (FR-13, Story C.k).

Each renderer produces a nontrivial PNG that is byte-deterministic across reruns
(Agg backend, pinned metadata, no timestamps).
"""

from __future__ import annotations

import pandas as pd  # type: ignore[import-untyped]
import pytest

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import InstanceArtifacts
from modelfoundry.plugins.pytorch.visualizations import render_visualization
from modelfoundry.recipe.models import VisualizationSpec

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _artifacts() -> InstanceArtifacts:
    history = pd.DataFrame(
        {
            "epoch": [1.0, 2.0, 3.0],
            "train_loss": [1.2, 0.8, 0.5],
            "val_loss": [1.3, 0.9, 0.7],
            "val_accuracy": [0.4, 0.6, 0.75],
            "learning_rate": [0.01, 0.01, 0.005],
        }
    )
    predictions = pd.DataFrame(
        {
            "split": ["val"] * 4,
            "record_id": [f"r{i}" for i in range(4)],
            "true_label": ["c0", "c1", "c2", "c0"],
            "pred_label": ["c0", "c1", "c1", "c0"],
            "pred_proba_c0": [0.8, 0.1, 0.2, 0.7],
            "pred_proba_c1": [0.1, 0.8, 0.5, 0.2],
            "pred_proba_c2": [0.1, 0.1, 0.3, 0.1],
        }
    )
    trials = pd.DataFrame({"number": [0, 1, 2], "value": [0.5, float("nan"), 0.7]})
    evaluation = {
        "val": {
            "accuracy": 0.75,
            "confusion_matrix": [[2, 0, 0], [0, 1, 1], [0, 0, 2]],
            "calibration_curve": {
                "bin_lower": [0.0, 0.5],
                "bin_upper": [0.5, 1.0],
                "mean_confidence": [0.4, 0.85],
                "accuracy": [0.5, 0.9],
                "count": [2.0, 4.0],
            },
        }
    }
    return InstanceArtifacts(
        history=history,
        evaluation=evaluation,
        predictions=predictions,
        trials=trials,
        class_names=["c0", "c1", "c2"],
    )


_OPS = [
    "training_curves",
    "optimization_history",
    "confusion_matrix",
    "calibration_curve",
    "predictions_grid",
]


@pytest.mark.parametrize("op", _OPS)
def test_renderer_produces_nontrivial_png(op: str) -> None:
    png = render_visualization(VisualizationSpec(op=op), _artifacts())
    assert png.startswith(_PNG_MAGIC)
    assert len(png) > 1000


@pytest.mark.parametrize("op", _OPS)
def test_renderer_is_byte_deterministic(op: str) -> None:
    artifacts = _artifacts()
    a = render_visualization(VisualizationSpec(op=op), artifacts)
    b = render_visualization(VisualizationSpec(op=op), artifacts)
    assert a == b


def test_optimization_history_placeholder_without_trials() -> None:
    artifacts = InstanceArtifacts(trials=None)
    png = render_visualization(VisualizationSpec(op="optimization_history"), artifacts)
    assert png.startswith(_PNG_MAGIC)


def test_predictions_grid_is_labels_only_without_images() -> None:
    # No image column on the predictions frame -> labels-only grid still renders.
    png = render_visualization(VisualizationSpec(op="predictions_grid"), _artifacts())
    assert png.startswith(_PNG_MAGIC)


def test_confusion_matrix_split_param_is_honored() -> None:
    # `split` is an extra field on VisualizationSpec (extra="allow").
    viz = VisualizationSpec.model_validate({"op": "confusion_matrix", "split": "val"})
    png = render_visualization(viz, _artifacts())
    assert png.startswith(_PNG_MAGIC)


def test_unknown_op_raises_plugin_error() -> None:
    with pytest.raises(PluginError, match="unknown visualization op"):
        render_visualization(VisualizationSpec(op="roc_curve"), _artifacts())
