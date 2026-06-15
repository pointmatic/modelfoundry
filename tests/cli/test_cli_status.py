# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry status` (Story E.j)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


def test_status_reports_materialized_instance(
    cli_env: SimpleNamespace, shared_opts: list[str], materialized: Any
) -> None:
    # `materialized` lands an instance at the recipe's cache key; status re-resolves
    # the same key (the stubbed resolver returns the same bound instance) and finds it.
    result = CliRunner().invoke(app, [*shared_opts, "status", str(cli_env.recipe)])
    assert result.exit_code == 0
    assert "Status" in result.stdout
    assert "pytorch" in result.stdout
    assert "recipe hash" in result.stdout
