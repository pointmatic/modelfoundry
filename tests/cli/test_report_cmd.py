# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `report` CLI command (Story D.f, FR-18).

`report` operates on a self-contained materialized instance directory — no
recipe, no DataRefinery binding. The fixture instance below declares no
`Visualizations`, so `rerender_report` never calls `plugin.render_visualization`
and the whole path stays torch-free (the markdown re-render is pure
pandas/string work).
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("typer")

import yaml
from rich.console import Console
from typer.testing import CliRunner

from modelfoundry.cli.app import app
from modelfoundry.cli.commands.report_cmd import run
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import InstanceError
from modelfoundry.core.manifest import Manifest


def _build_fixture_instance(tmp_path: Path) -> Path:
    """A minimal materialized instance: manifest + recipe + a stale report to re-render."""
    inst = tmp_path / "instance"
    inst.mkdir(parents=True)

    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": "sklearn",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {"type": "mlp_classifier", "hidden_layer_sizes": [8], "num_classes": 3},
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
        plugin="sklearn",
        plugin_version="0.4.0",
        recipe_hash="a" * 64,
        data_instance_hash="b" * 64,
        bound_data_instance=Path("/dr/cache/instances/abc/def/1"),
        seed=7,
        overlays=[],
        created_at=datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC),
        elapsed_seconds=1.5,
        epoch_history=1,
        evaluation={"val": {"accuracy": 0.9}},
        output_expectations=[],
    ).write(inst / "manifest.json")

    report_dir = inst / "report"
    report_dir.mkdir()
    (report_dir / "report.md").write_text("# stale report\n", encoding="utf-8")
    return inst


def test_run_rerenders_report_and_returns_0(tmp_path: Path) -> None:
    inst = _build_fixture_instance(tmp_path)
    buf = io.StringIO()
    rc = run(inst, RuntimeConfig(), console=Console(file=buf, width=200))
    assert rc == 0
    out = buf.getvalue()
    assert "report.md" in out
    report_md = inst / "report" / "report.md"
    assert report_md.is_file()
    # The stale placeholder was replaced by a freshly rendered report.
    assert report_md.read_text(encoding="utf-8") != "# stale report\n"


def test_run_does_not_wrap_the_report_path_in_a_narrow_terminal(tmp_path: Path) -> None:
    # rich's no-TTY fallback width is 80 cols (CI); a long instance path would
    # wrap and split `report.md` across lines, breaking copy-paste and the path
    # match. A narrow width makes the regression deterministic regardless of the
    # tmp_path length (Story G.d).
    inst = _build_fixture_instance(tmp_path)
    buf = io.StringIO()
    rc = run(inst, RuntimeConfig(), console=Console(file=buf, width=40))
    assert rc == 0
    report_md = inst / "report" / "report.md"
    assert str(report_md) in buf.getvalue(), "the report path was line-wrapped"


def test_run_on_non_instance_path_raises_instance_error(tmp_path: Path) -> None:
    with pytest.raises(InstanceError):
        run(tmp_path, RuntimeConfig(), console=Console(file=io.StringIO()))


def test_cli_report_exits_0_and_prints_path(tmp_path: Path) -> None:
    inst = _build_fixture_instance(tmp_path)
    result = CliRunner().invoke(app, ["report", str(inst)])
    assert result.exit_code == 0, result.output
    assert "report.md" in result.output


def test_cli_report_missing_instance_exits_1(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["report", str(tmp_path)])
    assert result.exit_code == 1, result.output


def test_cli_report_missing_arg_is_usage_error() -> None:
    result = CliRunner().invoke(app, ["report"])
    assert result.exit_code == 2
