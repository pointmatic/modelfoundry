# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry init` (Story E.j)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


def test_init_scaffolds_a_recipe_from_the_bound_instance(
    cli_env: SimpleNamespace, shared_opts: list[str]
) -> None:
    out = cli_env.recipe.parent / "scaffolded.yml"
    result = CliRunner().invoke(
        app, [*shared_opts, "init", str(out), "--data", str(cli_env.dr_recipe)]
    )
    assert result.exit_code == 0
    assert "scaffolded" in result.stdout
    assert out.is_file()

    # The scaffolded recipe is well-formed and sized from the bound instance (3 classes).
    recipe = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert recipe["plugin"] == "pytorch"
    assert recipe["Architecture"]["num_classes"] == 3
    assert "Evaluation" in recipe

    # No-implicit-defaults (Story I.e.2): the scaffolder emits every behavior-
    # affecting value explicitly, rather than relying on a code-supplied default.
    assert recipe["Training"]["precision"] == "fp32"
    assert recipe["Training"]["checkpoint_cadence"] == 1
    assert recipe["Training"]["device"] == "auto"
    assert recipe["Evaluation"]["calibration_bins"] == 10
