# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for reporting (FR-18, Story C.n)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from modelfoundry.core.manifest import (
    ExpectationOutcome,
    Manifest,
    ManifestWarning,
    OptimizationManifest,
)
from modelfoundry.plugins.base import InstanceArtifacts
from modelfoundry.recipe.models import (
    DataSpec,
    EvaluationSpec,
    LossSpec,
    ModelRecipe,
    OptimizerSpec,
    TrainingSpec,
    VisualizationSpec,
)
from modelfoundry.reporting.report import render_report
from modelfoundry.reporting.visualizations import (
    render_reporting_visualizations,
    rerender_report,
)

_PNG = b"\x89PNG\r\n\x1a\nstub"
_HEADINGS = [
    "# ModelFoundry Report",
    "## Recipe",
    "## Metrics",
    "## Optimization",
    "## Expectations",
    "## Warnings",
]


class _StubPlugin:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def render_visualization(self, viz: Any, artifacts: Any) -> bytes:
        self.calls.append(viz.op)
        if self.fail:
            raise RuntimeError("render boom")
        return _PNG


def _recipe(visualizations: list[VisualizationSpec] | None = None) -> ModelRecipe:
    return ModelRecipe(
        schema_version=1,
        plugin="pytorch",
        seed=7,
        Data=DataSpec(recipe=Path("dr.yml")),
        Architecture={"type": "resnet20", "num_classes": 10},
        Loss=LossSpec(op="cross_entropy"),
        Optimizer=OptimizerSpec(op="adamw", learning_rate=0.01),
        Training=TrainingSpec(
            max_epochs=1, batch_size=2, device="cpu", precision="fp32", checkpoint_cadence=1
        ),
        Evaluation=EvaluationSpec(
            splits=["val"], primary_metric="accuracy", metrics=["accuracy"], calibration_bins=10
        ),
        Visualizations=visualizations or [],
    )


def _manifest() -> Manifest:
    return Manifest(
        plugin="pytorch",
        plugin_version="0.3.1",
        recipe_hash="a" * 64,
        data_instance_hash="b" * 16,
        bound_data_instance=Path("/cache/instances/x"),
        seed=7,
        overlays=[],
        created_at=datetime(2026, 6, 12, tzinfo=UTC),
        elapsed_seconds=12.5,
        epoch_history=3,
        warnings=[ManifestWarning(stage="evaluation", message="baseline skipped")],
        optimization=OptimizationManifest(
            sampler="tpe", pruner="median", n_trials=3, best_trial_number=1, best_value=0.82
        ),
        evaluation={
            "val": {"accuracy": 0.8, "macro_f1": 0.75, "confusion_matrix": [[1, 0], [0, 1]]}
        },
        output_expectations=[
            ExpectationOutcome(
                metric="accuracy", split="val", op="gte", expected=0.7, observed=0.8, passed=True
            )
        ],
    )


def _artifacts(**kw: Any) -> InstanceArtifacts:
    base: dict[str, Any] = {
        "recipe": _recipe(),
        "manifest": _manifest(),
        "evaluation": _manifest().evaluation,
    }
    base.update(kw)
    return InstanceArtifacts(**base)


# --- render_report ---


def test_report_has_all_section_headings() -> None:
    md = render_report(_artifacts())
    for heading in _HEADINGS:
        assert heading in md


def test_report_renders_recipe_and_metrics() -> None:
    md = render_report(_artifacts())
    assert "**Plugin:** pytorch" in md
    assert "resnet20" in md
    assert "accuracy" in md and "macro_f1" in md
    assert "0.8000" in md  # accuracy formatted
    assert "confusion_matrix" not in md  # non-scalar excluded from the metrics table


def test_report_renders_optimization_expectations_warnings() -> None:
    md = render_report(_artifacts())
    assert "tpe" in md and "median" in md
    assert "✅" in md  # passing expectation
    assert "baseline skipped" in md


def test_report_degrades_with_empty_artifacts() -> None:
    md = render_report(InstanceArtifacts())
    for heading in _HEADINGS:
        assert heading in md
    assert "_No optimization stage._" in md
    assert "_None declared._" in md


# --- reporting visualizations ---


def test_dispatcher_routes_only_reporting_mode(tmp_path: Path) -> None:
    recipe = _recipe(
        [
            VisualizationSpec(op="training_curves", mode="reporting"),
            VisualizationSpec(op="confusion_matrix", mode="interactive"),
        ]
    )
    plugin = _StubPlugin()
    written = render_reporting_visualizations(recipe, plugin, _artifacts(), tmp_path / "viz")

    assert plugin.calls == ["training_curves"]  # interactive skipped
    assert len(written) == 1
    assert written[0].name == "training_curves.png"
    assert written[0].read_bytes() == _PNG


def test_viz_name_extra_overrides_filename(tmp_path: Path) -> None:
    recipe = _recipe(
        [
            VisualizationSpec.model_validate(
                {"op": "training_curves", "mode": "reporting", "name": "curves"}
            )
        ]
    )
    written = render_reporting_visualizations(recipe, _StubPlugin(), _artifacts(), tmp_path / "viz")
    assert written[0].name == "curves.png"


# --- atomic re-render ---


def test_rerender_replaces_report_atomically(tmp_path: Path) -> None:
    instance = tmp_path / "inst"
    report = instance / "report"
    report.mkdir(parents=True)
    (report / "report.md").write_text("OLD REPORT", encoding="utf-8")

    recipe = _recipe([VisualizationSpec(op="training_curves", mode="reporting")])
    rerender_report(instance, _artifacts(), recipe, _StubPlugin())

    assert "# ModelFoundry Report" in (report / "report.md").read_text()
    assert (report / "visualizations" / "training_curves.png").is_file()
    assert not (instance / "report.tmp").exists()
    assert not (instance / "report.bak").exists()


def test_rerender_preserves_old_report_on_failure(tmp_path: Path) -> None:
    instance = tmp_path / "inst"
    report = instance / "report"
    report.mkdir(parents=True)
    (report / "report.md").write_text("OLD REPORT", encoding="utf-8")

    recipe = _recipe([VisualizationSpec(op="training_curves", mode="reporting")])
    with pytest.raises(RuntimeError, match="render boom"):
        rerender_report(instance, _artifacts(), recipe, _StubPlugin(fail=True))

    # The live report is untouched (the swap never happened).
    assert (report / "report.md").read_text() == "OLD REPORT"
