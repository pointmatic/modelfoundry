# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `status` CLI command (Story D.d, FR-16).

`render_status` is a pure function over `(recipe_path, status_dict, primary_metric)`
so the manifest summary + the "not materialized" branch are exercised without any
DataRefinery binding or materialization. The end-to-end CLI smoke monkeypatches
`ModelFoundry.from_recipe` (binding requires real source inputs on-host, and a
full materialize is far too slow for a smoke) but still renders a *real* on-disk
`Manifest` fixture through the live command path. The real bind+status path is
covered by `tests/integration/test_modelfoundry_api.py::test_verbs_status_report_check_clean`.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("typer")

from rich.console import Console
from typer.testing import CliRunner

from modelfoundry.cli.app import app
from modelfoundry.cli.commands.status_cmd import render_status, run
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.manifest import ExpectationOutcome, Manifest
from modelfoundry.core.modelfoundry import ModelFoundry


def _manifest(**overrides: Any) -> Manifest:
    base: dict[str, Any] = {
        "plugin": "pytorch",
        "plugin_version": "0.4.0",
        "recipe_hash": "a" * 64,
        "data_instance_hash": "b" * 64,
        "bound_data_instance": Path("/dr/cache/instances/abc/def/1"),
        "seed": 7,
        "variant": None,
        "created_at": datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC),
        "elapsed_seconds": 12.5,
        "epoch_history": 3,
        "evaluation": {"val": {"accuracy": 0.9123, "macro_f1": 0.88}},
        "output_expectations": [
            ExpectationOutcome(
                metric="accuracy",
                split="val",
                op="gte",
                expected=0.5,
                observed=0.9123,
                passed=True,
            )
        ],
    }
    base.update(overrides)
    return Manifest(**base)


def _materialized(manifest: Manifest, instance_dir: str = "/mf/cache/.../1") -> dict[str, Any]:
    return {"materialized": True, "instance_dir": instance_dir, "manifest": manifest}


def _render_to_str(status: dict[str, Any], *, primary_metric: str = "accuracy") -> str:
    buf = io.StringIO()
    render_status(
        Path("recipe.yml"),
        status,
        primary_metric=primary_metric,
        console=Console(file=buf, width=200),
    )
    return buf.getvalue()


# --- render_status: the materialized summary table ---


def test_render_materialized_shows_manifest_summary() -> None:
    out = _render_to_str(_materialized(_manifest()))
    assert "pytorch" in out
    assert "0.4.0" in out
    assert "7" in out  # seed
    assert "12.5" in out  # elapsed seconds


def test_render_materialized_shows_primary_metric_name_and_value() -> None:
    out = _render_to_str(_materialized(_manifest()))
    assert "accuracy" in out
    assert "0.9123" in out
    assert "val" in out


def test_render_expectations_passed_and_failed_counts() -> None:
    manifest = _manifest(
        output_expectations=[
            ExpectationOutcome(
                metric="accuracy",
                split="val",
                op="gte",
                expected=0.5,
                observed=0.91,
                passed=True,
            ),
            ExpectationOutcome(
                metric="macro_f1",
                split="val",
                op="gte",
                expected=0.99,
                observed=0.88,
                passed=False,
            ),
        ]
    )
    out = _render_to_str(_materialized(manifest))
    assert "1 passed" in out
    assert "1 failed" in out


def test_render_variant_none_renders_placeholder() -> None:
    out = _render_to_str(_materialized(_manifest(variant=None)))
    # The variant row is present even when unset (rendered as a dash/none token).
    assert "variant" in out.lower()


def test_render_partial_instance_is_flagged() -> None:
    manifest = _manifest(is_partial=True, failed_stage="training")
    out = _render_to_str(_materialized(manifest))
    assert "partial" in out.lower()
    assert "training" in out


# --- render_status: the not-materialized branch ---


def test_render_not_materialized_reports_expected_path() -> None:
    status = {"materialized": False, "instance_dir": "/mf/cache/x/y/7", "manifest": None}
    out = _render_to_str(status)
    assert "not materialized" in out.lower()
    assert "/mf/cache/x/y/7" in out


# --- run(): delegates and returns 0 (status is informational) ---


def _patch_from_recipe(monkeypatch: pytest.MonkeyPatch, mf: Any) -> None:
    monkeypatch.setattr(ModelFoundry, "from_recipe", lambda *a, **k: mf)


def _fake_mf(status: dict[str, Any], primary_metric: str = "accuracy") -> SimpleNamespace:
    recipe = SimpleNamespace(Evaluation=SimpleNamespace(primary_metric=primary_metric))
    return SimpleNamespace(status=lambda: status, recipe=recipe)


def test_run_returns_0_when_materialized(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_from_recipe(monkeypatch, _fake_mf(_materialized(_manifest())))
    assert run(Path("recipe.yml"), RuntimeConfig(), console=Console(file=io.StringIO())) == 0


def test_run_returns_0_when_not_materialized(monkeypatch: pytest.MonkeyPatch) -> None:
    status = {"materialized": False, "instance_dir": "/x", "manifest": None}
    _patch_from_recipe(monkeypatch, _fake_mf(status))
    assert run(Path("recipe.yml"), RuntimeConfig(), console=Console(file=io.StringIO())) == 0


# --- end-to-end CLI smoke (renders a real on-disk Manifest fixture) ---


def test_cli_status_materialized_fixture_exits_0(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    instance_dir = tmp_path / "instance"
    _manifest().write(instance_dir / "manifest.json")
    loaded = Manifest.load(instance_dir / "manifest.json")
    _patch_from_recipe(monkeypatch, _fake_mf(_materialized(loaded, str(instance_dir))))

    result = CliRunner().invoke(app, ["status", "recipe.yml"])
    assert result.exit_code == 0, result.output
    assert "pytorch" in result.output
    assert "accuracy" in result.output


def test_cli_status_not_materialized_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    status = {"materialized": False, "instance_dir": "/mf/cache/x/y/7", "manifest": None}
    _patch_from_recipe(monkeypatch, _fake_mf(status))
    result = CliRunner().invoke(app, ["status", "recipe.yml"])
    assert result.exit_code == 0, result.output
    assert "not materialized" in result.output.lower()


def test_cli_status_missing_recipe_arg_is_usage_error() -> None:
    result = CliRunner().invoke(app, ["status"])
    assert result.exit_code == 2
