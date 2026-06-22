# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""CLI scaffolding tests (Story D.a) — exit-code mapping, shared options, verbs."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("typer")  # base dep; runs in an env carrying the runtime closure

import click
import typer
from typer.testing import CliRunner

from modelfoundry.cli.app import (
    app,
    build_runtime_config,
    exit_code_for,
    invoke,
    main,
)
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import (
    CacheError,
    DataBindingError,
    ExpectationError,
    MaterializeError,
    ModelArtifactExistsError,
    OptimizationError,
    PluginError,
    RecipeError,
    ValidationError,
)

_VERBS = ["init", "validate", "check", "status", "materialize", "report", "inspect", "clean"]


# --- exit_code_for: the exception -> exit-code mapping ---


@pytest.mark.parametrize(
    "exc",
    [
        RecipeError("x"),
        ValidationError("x"),
        DataBindingError("x"),
        ExpectationError("x"),
        ModelArtifactExistsError("x"),
    ],
)
def test_user_contract_errors_map_to_1(exc: Exception) -> None:
    assert exit_code_for(exc) == 1


@pytest.mark.parametrize(
    "exc",
    [PluginError("x"), MaterializeError("x"), CacheError("x"), OptimizationError("x")],
)
def test_system_plugin_errors_map_to_2(exc: Exception) -> None:
    assert exit_code_for(exc) == 2


def test_keyboard_interrupt_maps_to_130() -> None:
    assert exit_code_for(KeyboardInterrupt()) == 130


def test_unexpected_exception_maps_to_2() -> None:
    assert exit_code_for(ValueError("boom")) == 2


# --- --help lists every scaffolded verb ---


def test_help_lists_all_eight_verbs() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for verb in _VERBS:
        assert verb in result.output, f"verb {verb!r} missing from --help"


@pytest.mark.parametrize("verb", _VERBS)
def test_each_verb_is_registered(verb: str) -> None:
    # A scaffolded verb exists (its own --help renders) even though it is a stub.
    result = CliRunner().invoke(app, [verb, "--help"])
    assert result.exit_code == 0


# --- invoke(): the central exit-code-mapping wrapper, end-to-end ---


def _app_raising(exc: BaseException) -> typer.Typer:
    raiser: typer.Typer = typer.Typer()

    @raiser.command()
    def boom() -> None:
        raise exc

    return raiser


def test_invoke_maps_raised_domain_errors() -> None:
    assert invoke(_app_raising(RecipeError("bad recipe")), []) == 1
    assert invoke(_app_raising(PluginError("no plugin")), []) == 2
    assert invoke(_app_raising(KeyboardInterrupt()), []) == 130
    assert invoke(_app_raising(ValueError("unexpected")), []) == 2


def test_invoke_help_is_zero() -> None:
    assert invoke(app, ["--help"]) == 0


def test_invoke_unknown_command_is_usage_error_2() -> None:
    assert invoke(app, ["no-such-command"]) == 2


# --- build_runtime_config: shared options -> RuntimeConfig (CLI > env > defaults) ---


def test_flags_override_env_and_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("MODELFOUNDRY_CACHE_ROOT", raising=False)
    cfg = build_runtime_config(
        cache_root=tmp_path / "c",
        data_cache_root=None,
        log_level=None,
        log_target=None,
        plugin_path=None,
        verbose=False,
        quiet=False,
    )
    assert cfg.cache_root == tmp_path / "c"
    assert cfg.data_cache_root == RuntimeConfig().data_cache_root  # unset -> default


def test_env_used_when_flag_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODELFOUNDRY_CACHE_ROOT", str(tmp_path / "envc"))
    cfg = build_runtime_config(
        cache_root=None,
        data_cache_root=None,
        log_level=None,
        log_target=None,
        plugin_path=None,
        verbose=False,
        quiet=False,
    )
    assert cfg.cache_root == tmp_path / "envc"


def test_num_workers_flag_flows_into_runtime_config(monkeypatch: pytest.MonkeyPatch) -> None:
    # Story I.e.1: --num-workers (execution context) wins over env and default.
    monkeypatch.setenv("MODELFOUNDRY_NUM_WORKERS", "2")
    cfg = build_runtime_config(
        cache_root=None,
        data_cache_root=None,
        log_level=None,
        log_target=None,
        plugin_path=None,
        verbose=False,
        quiet=False,
        num_workers=6,
    )
    assert cfg.num_workers == 6


def test_plugin_path_splits_on_comma() -> None:
    cfg = build_runtime_config(
        cache_root=None,
        data_cache_root=None,
        log_level=None,
        log_target=None,
        plugin_path="a/b,c/d",
        verbose=False,
        quiet=False,
    )
    assert cfg.plugin_path == (Path("a/b"), Path("c/d"))


def test_verbose_sets_debug_level() -> None:
    cfg = build_runtime_config(
        cache_root=None,
        data_cache_root=None,
        log_level=None,
        log_target=None,
        plugin_path=None,
        verbose=True,
        quiet=False,
    )
    assert cfg.log_level == "DEBUG"


def test_quiet_sets_warning_level() -> None:
    cfg = build_runtime_config(
        cache_root=None,
        data_cache_root=None,
        log_level=None,
        log_target=None,
        plugin_path=None,
        verbose=False,
        quiet=True,
    )
    assert cfg.log_level == "WARNING"


def test_explicit_log_level_wins_over_verbose() -> None:
    cfg = build_runtime_config(
        cache_root=None,
        data_cache_root=None,
        log_level="ERROR",
        log_target=None,
        plugin_path=None,
        verbose=True,
        quiet=False,
    )
    assert cfg.log_level == "ERROR"


def test_verbose_and_quiet_conflict_raises() -> None:
    with pytest.raises(click.exceptions.UsageError):
        build_runtime_config(
            cache_root=None,
            data_cache_root=None,
            log_level=None,
            log_target=None,
            plugin_path=None,
            verbose=True,
            quiet=True,
        )


# --- callback wires the config into the Typer context ---


def test_shared_flag_reaches_the_callback(tmp_path: Path) -> None:
    # `check` exits 0 only when every discovered plugin is available; the pytorch
    # plugin needs torch, so this runs in smoke-pytorch and skips in the light testenv.
    pytest.importorskip("torch")
    # Passing a shared flag parses cleanly and the verb stub still runs.
    result = CliRunner().invoke(app, ["--cache-root", str(tmp_path), "check"])
    assert result.exit_code == 0


# --- main() entry point ---


def test_main_help_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["modelfoundry", "--help"])
    assert main() == 0


def test_version_flag_prints_version_and_exits_zero() -> None:
    from modelfoundry._version import __version__

    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
