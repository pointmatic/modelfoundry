# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `validate` CLI command (Story D.b, FR-2)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("typer")

import datarefinery as dr
import yaml
from rich.console import Console
from typer.testing import CliRunner

from modelfoundry.cli.app import app
from modelfoundry.cli.commands.validate_cmd import render_validation
from modelfoundry.recipe.validator import ValidationCheck, ValidationReport

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DR_RECIPE = "recipes/cifar10-base.yaml"
_DELIVERABLE = "recipes/cifar10_resnet20.yml"
_DATA_ROOT = "data"


@pytest.fixture(autouse=True)
def _repo_root_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    # The recipe's relative `Data.recipe` and DataRefinery's input hashing
    # resolve against the cwd; pin it to the repo root.
    monkeypatch.chdir(_REPO_ROOT)


def _require_dr1_instance() -> None:
    status = dr.resolve_instance(_DR_RECIPE, cache_root=_DATA_ROOT, seed=None, variant=None)
    if status.cache_status != "hit":
        pytest.skip(f"DR-1 CIFAR-10 instance not materialized under ./{_DATA_ROOT}")


def _report(*, all_pass: bool) -> ValidationReport:
    return ValidationReport(
        checks=[
            ValidationCheck(id=1, name="schema_version", passed=True),
            ValidationCheck(
                id=2,
                name="plugin",
                passed=all_pass,
                message=None if all_pass else "plugin 'pytorch' is not discoverable",
            ),
        ]
    )


def _render_to_str(report: ValidationReport) -> str:
    buf = io.StringIO()
    render_validation(report, Path("recipe.yml"), console=Console(file=buf, width=120))
    return buf.getvalue()


# --- render_validation: the rich table + summary ---


def test_render_passing_report_summarizes_pass() -> None:
    out = _render_to_str(_report(all_pass=True))
    assert "schema_version" in out
    assert "passed" in out.lower()


def test_render_failing_report_shows_failure_and_message() -> None:
    out = _render_to_str(_report(all_pass=False))
    assert "failed" in out.lower()
    assert "not discoverable" in out


# --- end-to-end CLI smoke (binds the real DR-1 instance; skips if absent) ---


def test_cli_validate_passing_recipe_exits_0() -> None:
    # Validating the pytorch deliverable needs the pytorch plugin discoverable (torch);
    # runs in smoke-pytorch, skips in the light testenv.
    pytest.importorskip("torch")
    _require_dr1_instance()
    result = CliRunner().invoke(app, ["validate", _DELIVERABLE])
    assert result.exit_code == 0, result.output
    assert "passed" in result.output.lower()


def test_cli_validate_failing_recipe_exits_1(tmp_path: Path) -> None:
    # Needs the pytorch plugin discoverable (torch) so check 12 — not a missing-plugin
    # check 2 — is the isolated failure; runs in smoke-pytorch, skips in the light testenv.
    pytest.importorskip("torch")
    _require_dr1_instance()
    # Same Data binding, but primary_metric 'ece' is a valid metric NOT listed in
    # Evaluation.metrics → FR-2 check 12 fails (binding + every other check pass).
    spec = yaml.safe_load((_REPO_ROOT / _DELIVERABLE).read_text(encoding="utf-8"))
    spec["Evaluation"]["primary_metric"] = "ece"
    bad = tmp_path / "bad.yml"
    bad.write_text(yaml.safe_dump(spec), encoding="utf-8")

    result = CliRunner().invoke(app, ["validate", str(bad)])
    assert result.exit_code == 1, result.output
    assert "failed" in result.output.lower()


def test_cli_validate_missing_recipe_arg_is_usage_error() -> None:
    result = CliRunner().invoke(app, ["validate"])
    assert result.exit_code == 2
