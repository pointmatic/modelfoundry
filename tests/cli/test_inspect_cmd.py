# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `inspect` CLI command (Story D.g, FR-17).

`inspect` renders a single named view of a materialized instance on demand
(exploration mode, no persistence): PNG views (`training_curves`, …) are written
to a temp file and the path printed; the text `view_manifest` view renders a
`rich` table. The fixture instance is hand-built (manifest + recipe, no real
training); PNG rendering degrades to a placeholder image when artifacts are
absent, so the PNG path needs only matplotlib, not torch.
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
from modelfoundry.cli.commands.inspect_cmd import run
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import InspectionError
from modelfoundry.core.instance import ModelInstance
from modelfoundry.core.manifest import Manifest


def _build_fixture_instance(tmp_path: Path, *, plugin: str = "pytorch") -> Path:
    inst = tmp_path / "instance"
    inst.mkdir(parents=True)

    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": plugin,
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {"num_classes": 3, "layers": [{"op": "Flatten"}]},
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {"max_epochs": 1, "batch_size": 4},
        "Evaluation": {"splits": ["val"], "primary_metric": "accuracy", "metrics": ["accuracy"]},
        "Visualizations": [],
        "OutputExpectations": [],
    }
    (inst / "recipe.yml").write_text(yaml.safe_dump(recipe), encoding="utf-8")

    Manifest(
        plugin=plugin,
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
    return inst


# --- ModelInstance.inspect: the on-demand single-view path ---


def test_inspect_manifest_view_returns_manifest(tmp_path: Path) -> None:
    inst = _build_fixture_instance(tmp_path, plugin="sklearn")
    result = ModelInstance.load(inst).inspect(view="view_manifest")
    assert isinstance(result, Manifest)
    assert result.plugin == "sklearn"


def test_inspect_unknown_view_raises_inspection_error(tmp_path: Path) -> None:
    inst = _build_fixture_instance(tmp_path, plugin="pytorch")
    with pytest.raises(InspectionError):
        ModelInstance.load(inst).inspect(view="bogus_view")


def test_inspect_png_view_returns_bytes(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    inst = _build_fixture_instance(tmp_path, plugin="pytorch")
    result = ModelInstance.load(inst).inspect(view="training_curves")
    assert isinstance(result, bytes)
    assert result[:8] == b"\x89PNG\r\n\x1a\n"  # PNG signature


# --- run(): dispatch + rendering ---


def test_run_manifest_view_renders_table(tmp_path: Path) -> None:
    inst = _build_fixture_instance(tmp_path, plugin="sklearn")
    buf = io.StringIO()
    rc = run(inst, RuntimeConfig(), view="view_manifest", console=Console(file=buf, width=200))
    assert rc == 0
    out = buf.getvalue()
    assert "sklearn" in out
    assert "7" in out  # seed


def test_run_png_view_writes_tempfile(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    inst = _build_fixture_instance(tmp_path, plugin="pytorch")
    buf = io.StringIO()
    rc = run(inst, RuntimeConfig(), view="training_curves", console=Console(file=buf, width=200))
    assert rc == 0
    out = buf.getvalue()
    assert ".png" in out
    # The printed path exists and is a non-empty PNG.
    png_path = Path(out.split("→")[-1].strip())
    assert png_path.is_file() and png_path.stat().st_size > 0


def test_run_on_non_instance_path_raises_instance_error(tmp_path: Path) -> None:
    from modelfoundry.core.errors import InstanceError

    with pytest.raises(InstanceError):
        run(tmp_path, RuntimeConfig(), view="view_manifest", console=Console(file=io.StringIO()))


# --- CLI wiring ---


def test_cli_inspect_manifest_exits_0(tmp_path: Path) -> None:
    inst = _build_fixture_instance(tmp_path, plugin="sklearn")
    result = CliRunner().invoke(app, ["inspect", str(inst), "--view", "view_manifest"])
    assert result.exit_code == 0, result.output
    assert "sklearn" in result.output


def test_cli_inspect_unknown_view_exits_nonzero(tmp_path: Path) -> None:
    inst = _build_fixture_instance(tmp_path, plugin="pytorch")
    result = CliRunner().invoke(app, ["inspect", str(inst), "--view", "bogus_view"])
    assert result.exit_code != 0


def test_cli_inspect_missing_arg_is_usage_error() -> None:
    result = CliRunner().invoke(app, ["inspect"])
    assert result.exit_code == 2
