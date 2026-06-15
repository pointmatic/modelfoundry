# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `clean` CLI command (Story D.h, FR-20)."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("typer")

from rich.console import Console
from typer.testing import CliRunner

from modelfoundry.cli.app import app
from modelfoundry.cli.commands.clean_cmd import run
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.manifest import Manifest

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


def _instance(cache_root: Path, rh16: str, created_at: datetime) -> Path:
    d = cache_root / "instances" / rh16 / "dddd" / "0"
    d.mkdir(parents=True)
    Manifest(
        plugin="pytorch",
        plugin_version="0.4.0",
        recipe_hash=rh16 + "0" * 48,
        data_instance_hash="d" * 64,
        bound_data_instance=Path("/dr/x"),
        seed=0,
        variant=None,
        created_at=created_at,
        elapsed_seconds=1.0,
        epoch_history=1,
        evaluation={"val": {"accuracy": 0.9}},
        output_expectations=[],
    ).write(d / "manifest.json")
    return d


def _failed_temp(cache_root: Path, run_id: str) -> Path:
    d = cache_root / "instances" / ".tmp" / run_id
    d.mkdir(parents=True)
    (d / "FAILED").write_text("{}", encoding="utf-8")
    return d


def _config(cache_root: Path) -> RuntimeConfig:
    return RuntimeConfig(cache_root=cache_root)


# --- run(): selectors + exit codes ---


def test_run_recipe_hash_removes_tree(tmp_path: Path) -> None:
    inst = _instance(tmp_path, "aaaa111122223333", _NOW)
    rc = run(_config(tmp_path), recipe_hash="aaaa111122223333", console=Console(file=io.StringIO()))
    assert rc == 0
    assert not inst.exists()


def test_run_failed_removes_failed_temp(tmp_path: Path) -> None:
    failed = _failed_temp(tmp_path, "run-a")
    rc = run(_config(tmp_path), failed=True, console=Console(file=io.StringIO()))
    assert rc == 0
    assert not failed.exists()


def test_run_dry_run_keeps_everything(tmp_path: Path) -> None:
    failed = _failed_temp(tmp_path, "run-a")
    buf = io.StringIO()
    rc = run(_config(tmp_path), failed=True, dry_run=True, console=Console(file=buf, width=200))
    assert rc == 0
    assert failed.exists()  # dry-run removed nothing
    assert "would remove" in buf.getvalue().lower()


def test_run_no_matches_is_nothing_to_clean(tmp_path: Path) -> None:
    (tmp_path / "instances").mkdir()
    buf = io.StringIO()
    rc = run(_config(tmp_path), failed=True, console=Console(file=buf, width=200))
    assert rc == 0
    assert "nothing to clean" in buf.getvalue().lower()


def test_run_no_selector_raises(tmp_path: Path) -> None:
    from modelfoundry.core.errors import CacheError

    with pytest.raises(CacheError):
        run(_config(tmp_path), console=Console(file=io.StringIO()))


def test_run_orphans_without_older_than_raises(tmp_path: Path) -> None:
    from modelfoundry.core.errors import CacheError

    with pytest.raises(CacheError):
        run(_config(tmp_path), orphans=True, console=Console(file=io.StringIO()))


# --- CLI wiring ---


def test_cli_clean_dry_run_older_than(tmp_path: Path) -> None:
    _instance(tmp_path, "aaaa111122223333", _NOW - timedelta(days=99))
    result = CliRunner().invoke(
        app, ["--cache-root", str(tmp_path), "clean", "--dry-run", "--older-than", "7d"]
    )
    assert result.exit_code == 0, result.output
    assert "would remove" in result.output.lower()


def test_cli_clean_failed_exits_0(tmp_path: Path) -> None:
    _failed_temp(tmp_path, "run-a")
    result = CliRunner().invoke(app, ["--cache-root", str(tmp_path), "clean", "--failed"])
    assert result.exit_code == 0, result.output


def test_cli_clean_no_selector_errors(tmp_path: Path) -> None:
    # `CliRunner` surfaces the raised CacheError as a generic non-zero exit; the
    # CacheError→2 mapping itself is covered by `exit_code_for` in test_app.py.
    result = CliRunner().invoke(app, ["--cache-root", str(tmp_path), "clean"])
    assert result.exit_code != 0
