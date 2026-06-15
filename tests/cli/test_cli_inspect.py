# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry inspect` (Story E.j)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


def test_inspect_renders_manifest_view(
    cli_env: SimpleNamespace, shared_opts: list[str], materialized: Any
) -> None:
    result = CliRunner().invoke(
        app, [*shared_opts, "inspect", str(materialized.path), "--view", "view_manifest"]
    )
    assert result.exit_code == 0
    assert "Manifest" in result.stdout
    assert "pytorch" in result.stdout
