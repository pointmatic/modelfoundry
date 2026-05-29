# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `RuntimeConfig` and its env/override precedence."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from modelfoundry.core.config import RuntimeConfig


def test_defaults() -> None:
    cfg = RuntimeConfig()
    assert cfg.cache_root == Path("./models")
    assert cfg.data_cache_root == Path("./data")
    assert cfg.log_level == "INFO"
    assert cfg.log_target == "stderr"
    assert cfg.plugin_path == ()
    assert cfg.variant is None
    assert cfg.seed is None
    assert cfg.overwrite is False


def test_from_env_empty_yields_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MODELFOUNDRY_CACHE_ROOT",
        "MODELFOUNDRY_DATA_CACHE_ROOT",
        "MODELFOUNDRY_LOG_LEVEL",
        "MODELFOUNDRY_LOG_TARGET",
        "MODELFOUNDRY_PLUGIN_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    assert RuntimeConfig.from_env() == RuntimeConfig()


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELFOUNDRY_CACHE_ROOT", "/tmp/mf-cache")
    monkeypatch.setenv("MODELFOUNDRY_DATA_CACHE_ROOT", "/tmp/dr-cache")
    monkeypatch.setenv("MODELFOUNDRY_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MODELFOUNDRY_LOG_TARGET", "/var/log/mf.jsonl")
    monkeypatch.setenv("MODELFOUNDRY_PLUGIN_PATH", "/a/plugins,/b/plugins")
    cfg = RuntimeConfig.from_env()
    assert cfg.cache_root == Path("/tmp/mf-cache")
    assert cfg.data_cache_root == Path("/tmp/dr-cache")
    assert cfg.log_level == "DEBUG"
    assert cfg.log_target == "/var/log/mf.jsonl"
    assert cfg.plugin_path == (Path("/a/plugins"), Path("/b/plugins"))


def test_explicit_overrides_win_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELFOUNDRY_CACHE_ROOT", "/tmp/env-cache")
    monkeypatch.setenv("MODELFOUNDRY_LOG_LEVEL", "DEBUG")
    cfg = RuntimeConfig.from_env(cache_root=Path("/explicit/cache"), seed=42)
    assert cfg.cache_root == Path("/explicit/cache")
    assert cfg.log_level == "DEBUG"  # env still applied where not overridden
    assert cfg.seed == 42


def test_custom_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MF_CACHE_ROOT", "/tmp/prefixed")
    cfg = RuntimeConfig.from_env(prefix="MF_")
    assert cfg.cache_root == Path("/tmp/prefixed")


def test_plugin_path_skips_empty_segments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELFOUNDRY_PLUGIN_PATH", "/a,,/b,")
    cfg = RuntimeConfig.from_env()
    assert cfg.plugin_path == (Path("/a"), Path("/b"))


def test_invalid_log_level_rejected() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(log_level="TRACE")


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig(bogus=1)  # type: ignore[call-arg]
