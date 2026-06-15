# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry validate` (Story E.j)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


def test_validate_passes_for_minimal_recipe(
    cli_env: SimpleNamespace, shared_opts: list[str]
) -> None:
    result = CliRunner().invoke(app, [*shared_opts, "validate", str(cli_env.recipe)])
    assert result.exit_code == 0  # every FR-2 check passes
    assert "Validation" in result.stdout
    assert "schema_version" in result.stdout  # a rendered check row
    assert "pass" in result.stdout
