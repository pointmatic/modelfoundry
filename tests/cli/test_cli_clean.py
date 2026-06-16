# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry clean` (Story E.j)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


def test_clean_dry_run_reports_without_removing(
    cli_env: SimpleNamespace, shared_opts: list[str], materialized: Any
) -> None:
    instance_dir = materialized.path
    result = CliRunner().invoke(app, [*shared_opts, "clean", "--older-than", "0s", "--dry-run"])
    assert result.exit_code == 0
    assert "would remove" in result.stdout
    assert "dry run" in result.stdout
    # Dry run removes nothing — the instance is still on disk.
    assert (instance_dir / "manifest.json").is_file()
