# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `check` CLI command (Story D.c, FR-19).

The environment check discovers every registered plugin and runs each one's
`health_check()` — no recipe, no DataRefinery binding. Plugin availability is
faked via a monkeypatched `discover_plugins` so the exit code is deterministic
regardless of whether the optional `[pytorch]` extra is installed in the env
running the suite.
"""

from __future__ import annotations

import io
import platform
from typing import Any

import pytest

pytest.importorskip("typer")

from rich.console import Console
from typer.testing import CliRunner

from modelfoundry._version import __version__
from modelfoundry.cli.app import app
from modelfoundry.cli.commands.check_cmd import render_check, run
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.modelfoundry import ModelFoundry
from modelfoundry.plugins.sklearn.plugin import SklearnHealthReport

# --- fakes: a plugin whose health_check reports a fixed availability ---


class _FakeReport:
    def __init__(self, plugin: str, available: bool) -> None:
        self.plugin = plugin
        self.available = available
        self.accelerators: tuple[str, ...] = ("cpu",)


class _FakePlugin:
    def __init__(self, name: str, available: bool) -> None:
        self.name = name
        self._available = available

    def health_check(self) -> _FakeReport:
        return _FakeReport(self.name, self._available)


def _patch_discovery(monkeypatch: pytest.MonkeyPatch, plugins: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "modelfoundry.core.modelfoundry.discover_plugins",
        lambda extra_paths=(): plugins,
    )


def _render_to_str(result: dict[str, Any]) -> str:
    buf = io.StringIO()
    render_check(result, console=Console(file=buf, width=120))
    return buf.getvalue()


def _result(*, ok: bool, available: bool) -> dict[str, Any]:
    return {
        "python_version": "3.12.13",
        "modelfoundry_version": "0.4.0",
        "plugins": [
            SklearnHealthReport(
                plugin="sklearn",
                available=available,
                sklearn_version="1.5.0" if available else None,
                numpy_version="2.0.0",
            )
        ],
        "ok": ok,
    }


# --- ModelFoundry.check_environment: the library entry point ---


def test_check_environment_reports_python_and_modelfoundry_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_discovery(monkeypatch, {})
    result = ModelFoundry.check_environment(RuntimeConfig())
    assert result["python_version"] == platform.python_version()
    assert result["modelfoundry_version"] == __version__


def test_check_environment_ok_when_every_plugin_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_discovery(
        monkeypatch, {"a": _FakePlugin("a", True), "b": _FakePlugin("b", True)}
    )
    result = ModelFoundry.check_environment(RuntimeConfig())
    assert result["ok"] is True
    assert [r.plugin for r in result["plugins"]] == ["a", "b"]


def test_check_environment_not_ok_when_any_plugin_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_discovery(
        monkeypatch, {"a": _FakePlugin("a", True), "b": _FakePlugin("b", False)}
    )
    result = ModelFoundry.check_environment(RuntimeConfig())
    assert result["ok"] is False


# --- render_check: the rich table + summary ---


def test_render_healthy_shows_plugin_versions_and_ok() -> None:
    out = _render_to_str(_result(ok=True, available=True))
    assert "sklearn" in out
    assert "3.12.13" in out
    assert "0.4.0" in out
    assert "healthy" in out.lower()


def test_render_unhealthy_flags_unavailable_plugin() -> None:
    out = _render_to_str(_result(ok=False, available=False))
    assert "sklearn" in out
    assert "unavailable" in out.lower() or "unhealthy" in out.lower()


# --- run(): exit-code contract ---


def test_run_returns_0_when_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_discovery(monkeypatch, {"a": _FakePlugin("a", True)})
    assert run(RuntimeConfig(), console=Console(file=io.StringIO())) == 0


def test_run_returns_1_when_any_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_discovery(monkeypatch, {"a": _FakePlugin("a", False)})
    assert run(RuntimeConfig(), console=Console(file=io.StringIO())) == 1


# --- end-to-end CLI smoke ---


def test_cli_check_all_healthy_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_discovery(monkeypatch, {"pytorch": _FakePlugin("pytorch", True)})
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0, result.output
    assert "pytorch" in result.output


def test_cli_check_unavailable_plugin_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_discovery(monkeypatch, {"pytorch": _FakePlugin("pytorch", False)})
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 1, result.output
    assert "pytorch" in result.output


def test_cli_check_runs_against_real_environment() -> None:
    # No monkeypatch: exercises real plugin discovery + health_check. The exact
    # exit code depends on whether the [pytorch] extra is installed, so only the
    # invariant header + a real plugin name are asserted.
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code in (0, 1), result.output
    assert __version__ in result.output
    assert "sklearn" in result.output
