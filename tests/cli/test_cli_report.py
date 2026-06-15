# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry report` (Story E.j)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


def test_report_rerenders_instance(
    cli_env: SimpleNamespace, shared_opts: list[str], materialized: Any
) -> None:
    result = CliRunner().invoke(app, [*shared_opts, "report", str(materialized.path)])
    assert result.exit_code == 0
    assert "report rendered" in result.stdout
    assert (materialized.path / "report" / "report.md").is_file()
