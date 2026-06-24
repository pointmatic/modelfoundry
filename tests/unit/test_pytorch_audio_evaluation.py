# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Clip-level window aggregation in the evaluation stage (Story I.o.2).

Exercises `plugins.pytorch.evaluation.run_evaluation` with a recipe-declared
`WindowAggregation` policy against the synthesized audio fixture (Story I.l):
when the policy is present, window-level predictions are regrouped by
`source_record_id` so the persisted `predictions.parquet` and `metrics.json` are
**clip-level** (one row per clip, not per window); when absent, evaluation stays
window-level (additive). The dangling-key fixture variant is refused.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("torch")
pytest.importorskip("datarefinery")

from datarefinery_instances.audio_smoke.builder import (  # type: ignore[import-not-found]
    build_dr_audio_instance,
)
from torch import Tensor, nn

from modelfoundry.core.errors import DataBindingError
from modelfoundry.plugins.pytorch.evaluation import run_evaluation
from modelfoundry.recipe.models import EvaluationSpec, WindowAggregationSpec


class _TinyAudio(nn.Module):
    """Smallest model that maps a (B, 1, n_mels, n_frames) feature to class logits."""

    def __init__(self, num_classes: int) -> None:
        super().__init__()
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(1, num_classes)

    def forward(self, x: Tensor) -> Tensor:
        out: Tensor = self.fc(self.pool(x).flatten(1))
        return out


def _eval_spec() -> EvaluationSpec:
    return EvaluationSpec(
        splits=["train"],
        primary_metric="accuracy",
        metrics=["accuracy", "macro_f1"],
        calibration_bins=10,
    )


def _read_predictions(temp_dir: Path) -> Any:
    import pandas as pd  # type: ignore[import-untyped]

    return pd.read_parquet(temp_dir / "evaluation" / "predictions.parquet")


def test_window_aggregation_produces_clip_level_predictions(tmp_path: Path) -> None:
    # 4 train clips x 2 windows = 8 window records -> 4 clip-level predictions.
    instance = build_dr_audio_instance(tmp_path / "a", windows_per_clip=2)
    model = _TinyAudio(num_classes=3)
    temp_dir = tmp_path / "out"
    temp_dir.mkdir()

    result = run_evaluation(
        _eval_spec(),
        model,
        instance,
        temp_dir,
        window_aggregation=WindowAggregationSpec(policy="mean"),
    )

    frame = _read_predictions(temp_dir)
    assert len(frame) == 4  # one row per clip, not 8 windows
    assert set(frame["record_id"]) == {f"c{c % 3}/clip_{c}" for c in range(4)}
    assert "accuracy" in result.metrics["train"]


def test_evaluation_stays_window_level_without_aggregation(tmp_path: Path) -> None:
    # Control: no WindowAggregation ⇒ the established per-window surface (8 rows).
    instance = build_dr_audio_instance(tmp_path / "a", windows_per_clip=2)
    model = _TinyAudio(num_classes=3)
    temp_dir = tmp_path / "out"
    temp_dir.mkdir()

    run_evaluation(_eval_spec(), model, instance, temp_dir)

    frame = _read_predictions(temp_dir)
    assert len(frame) == 8  # per-window


def test_dangling_source_record_id_refused_during_aggregation(tmp_path: Path) -> None:
    instance = build_dr_audio_instance(tmp_path / "a", dangling_source_record_id=True)
    model = _TinyAudio(num_classes=3)
    temp_dir = tmp_path / "out"
    temp_dir.mkdir()

    with pytest.raises(DataBindingError, match=r"source_record_id|dangling"):
        run_evaluation(
            _eval_spec(),
            model,
            instance,
            temp_dir,
            window_aggregation=WindowAggregationSpec(policy="mean"),
        )
