# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry check` (Story E.j)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


def test_check_reports_plugin_health_and_exits_zero() -> None:
    # `check` needs no recipe or data; both plugins are available in this env.
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
    assert "pytorch" in result.stdout
    assert "sklearn" in result.stdout
    assert "available" in result.stdout
