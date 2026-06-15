# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the PyTorch plugin's registration + health_check (C.b).

Unlike the synthetic-plugin unit tests in `test_plugin_discovery.py`, these
exercise the *real* `modelfoundry.plugins` entry point declared in
`pyproject.toml`, so the editable install must be present (the conda testenv).
"""

from __future__ import annotations

import pytest

from modelfoundry.plugins.base import Plugin
from modelfoundry.plugins.discovery import discover_plugins


def test_discovery_finds_pytorch_plugin() -> None:
    plugins = discover_plugins()
    assert "pytorch" in plugins
    pytorch = plugins["pytorch"]
    assert isinstance(pytorch, Plugin)
    assert pytorch.name == "pytorch"
    # C.c populated the architecture vocabulary; C.d/C.g extend it further.
    assert "resnet20" in pytorch.operations
    assert "Conv2d" in pytorch.operations


def test_health_check_reports_available_backend() -> None:
    # Integration env carries the [pytorch] extra (env-dependencies.md §5.1);
    # skip cleanly anywhere torch is genuinely absent.
    pytest.importorskip("torch")
    from modelfoundry.plugins.pytorch.plugin import PyTorchHealthReport

    report = discover_plugins()["pytorch"].health_check()
    # `health_check()` is typed to the structural `CheckReport` (FR-19/D.c); narrow
    # to the concrete report to read the pytorch-specific version/determinism fields.
    assert isinstance(report, PyTorchHealthReport)
    assert report.plugin == "pytorch"
    assert report.available is True
    assert report.torch_version is not None
    assert isinstance(report.accelerators, tuple)
    assert "cpu" in report.accelerators  # CPU is always present when torch loads
    assert report.deterministic_algorithms_available is True
    assert report.documented_hard_error_ops == ()  # no CPU op trips the guard (C.a/C.e)


def test_no_plugin_method_is_a_not_implemented_stub() -> None:
    # As of C.l every Protocol method is implemented (delegated to its module).
    # A genuine stub raised NotImplementedError on call; the implemented methods
    # instead fail with their own errors (e.g. PluginError) on bad input. Probing
    # each here would require real artifacts, so assert the stub helper is gone.
    import modelfoundry.plugins.pytorch.plugin as plugin_module

    assert not hasattr(plugin_module, "_not_implemented")
