# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `plugins.base.Plugin` and `plugins.discovery.discover_plugins`."""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import OperationSpec, Plugin
from modelfoundry.plugins.discovery import discover_plugins


class _StubPlugin:
    """A synthetic in-process plugin that satisfies the `Plugin` Protocol."""

    def __init__(self, name: str = "synth", version: str = "1") -> None:
        self.name = name
        self.version = version
        self.operations: dict[str, OperationSpec] = {}

    def health_check(self) -> Any:
        return None

    def prepare_for_build(self, seed: int) -> None:
        return None

    def build_model(self, arch: dict[str, Any]) -> Any:
        return None

    def run_optimization(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def run_training(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def run_evaluation(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def render_visualization(self, *args: Any, **kwargs: Any) -> bytes | None:
        return None

    def save_model(self, model: Any, path: Path) -> None:
        return None

    def load_model(self, path: Path) -> Any:
        return None

    def predict(self, model: Any, X: Any) -> Any:
        return None

    def predict_proba(self, model: Any, X: Any) -> Any:
        return None


class _FakeEntryPoint:
    def __init__(self, name: str, loader: Callable[[], Any], value: str = "stub:plugin") -> None:
        self.name = name
        self._loader = loader
        self.value = value

    def load(self) -> Any:
        return self._loader()


@pytest.fixture
def patch_eps(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[_FakeEntryPoint]], None]:
    """Patch discovery's `entry_points` to return the given list when queried."""

    def _patch(fake_eps: list[_FakeEntryPoint]) -> None:
        def fake(*, group: str | None = None) -> list[_FakeEntryPoint]:
            assert group == "modelfoundry.plugins"
            return fake_eps

        monkeypatch.setattr("modelfoundry.plugins.discovery.entry_points", fake)

    return _patch


# --- Protocol isinstance ---


def test_stub_isinstance_plugin() -> None:
    assert isinstance(_StubPlugin(), Plugin)


def test_missing_attribute_is_not_a_plugin() -> None:
    class _Partial:
        name = "partial"
        version = "1"
        # missing: operations, every method.

    assert not isinstance(_Partial(), Plugin)


# --- OperationSpec ---


class _DummyParams(BaseModel):
    learning_rate: float = 0.001


def test_operation_spec_constructs() -> None:
    spec = OperationSpec(
        op_name="adamw",
        param_model=_DummyParams,
        applies_to="optimizer",
        requires_extras=("pytorch",),
    )
    assert spec.op_name == "adamw"
    assert spec.param_model is _DummyParams
    assert spec.requires_extras == ("pytorch",)


def test_operation_spec_rejects_bad_applies_to() -> None:
    with pytest.raises(ValidationError):
        OperationSpec(
            op_name="x",
            param_model=_DummyParams,
            applies_to="bogus",
        )


# --- discover_plugins via entry points ---


def test_discovery_finds_synthetic_plugin(
    patch_eps: Callable[[list[_FakeEntryPoint]], None],
) -> None:
    stub = _StubPlugin("alpha")
    patch_eps([_FakeEntryPoint("alpha", lambda: stub)])
    result = discover_plugins()
    assert set(result) == {"alpha"}
    assert result["alpha"] is stub


def test_discovery_empty_when_no_entry_points(
    patch_eps: Callable[[list[_FakeEntryPoint]], None],
) -> None:
    patch_eps([])
    assert discover_plugins() == {}


def test_duplicate_names_raise(
    patch_eps: Callable[[list[_FakeEntryPoint]], None],
) -> None:
    a, b = _StubPlugin("dup"), _StubPlugin("dup")
    patch_eps(
        [
            _FakeEntryPoint("first", lambda: a),
            _FakeEntryPoint("second", lambda: b),
        ]
    )
    with pytest.raises(PluginError, match="duplicate plugin name 'dup'"):
        discover_plugins()


def test_unresolvable_entry_point_raises(
    patch_eps: Callable[[list[_FakeEntryPoint]], None],
) -> None:
    def boom() -> Any:
        raise ImportError("missing module modelfoundry_phantom")

    patch_eps([_FakeEntryPoint("phantom", boom)])
    with pytest.raises(PluginError, match="could not load plugin entry point 'phantom'"):
        discover_plugins()


def test_entry_point_not_a_plugin_raises(
    patch_eps: Callable[[list[_FakeEntryPoint]], None],
) -> None:
    patch_eps([_FakeEntryPoint("notplug", lambda: "this is not a Plugin")])
    with pytest.raises(PluginError, match="did not provide a Plugin"):
        discover_plugins()


# --- extra_paths ---


_PLUGIN_FILE = textwrap.dedent(
    """
    from typing import Any

    class _Plug:
        name = "fromfile"
        version = "1"
        operations = {}
        def health_check(self): return None
        def prepare_for_build(self, seed): return None
        def build_model(self, arch): return None
        def run_optimization(self, *a, **k): return None
        def run_training(self, *a, **k): return None
        def run_evaluation(self, *a, **k): return None
        def render_visualization(self, *a, **k): return None
        def save_model(self, model, path): return None
        def load_model(self, path): return None
        def predict(self, model, X): return None
        def predict_proba(self, model, X): return None

    plugin = _Plug()
    """
).strip()


def test_extra_paths_discovers_plugin(
    tmp_path: Path, patch_eps: Callable[[list[_FakeEntryPoint]], None]
) -> None:
    patch_eps([])
    plugin_dir = tmp_path / "plugs"
    plugin_dir.mkdir()
    (plugin_dir / "myplug.py").write_text(_PLUGIN_FILE, encoding="utf-8")
    result = discover_plugins(extra_paths=(plugin_dir,))
    assert "fromfile" in result


def test_extra_paths_missing_directory_is_silent(
    tmp_path: Path, patch_eps: Callable[[list[_FakeEntryPoint]], None]
) -> None:
    patch_eps([])
    assert discover_plugins(extra_paths=(tmp_path / "nope",)) == {}
