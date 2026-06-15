# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `plugins.pytorch.determinism` (QR-3, Story C.e)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from modelfoundry.plugins.pytorch.determinism import (
    CUBLAS_WORKSPACE_CONFIG,
    deterministic_mode_supported,
    documented_hard_error_ops,
    enable_deterministic_algorithms,
)

torch = pytest.importorskip("torch")


@pytest.fixture
def restore_determinism() -> Iterator[None]:
    """Save/restore global torch deterministic state + the env var around a test."""
    was_enabled = torch.are_deterministic_algorithms_enabled()
    saved_cublas = os.environ.get("CUBLAS_WORKSPACE_CONFIG")
    try:
        yield
    finally:
        torch.use_deterministic_algorithms(was_enabled)
        if saved_cublas is None:
            os.environ.pop("CUBLAS_WORKSPACE_CONFIG", None)
        else:
            os.environ["CUBLAS_WORKSPACE_CONFIG"] = saved_cublas


def test_documented_hard_error_ops_matches_spike() -> None:
    # C.a found no CPU op trips the deterministic guard; the list stays empty.
    assert documented_hard_error_ops == ()


def test_deterministic_mode_supported() -> None:
    assert deterministic_mode_supported() is True


def test_enable_sets_env_and_mode(restore_determinism: None) -> None:
    os.environ.pop("CUBLAS_WORKSPACE_CONFIG", None)
    enable_deterministic_algorithms(seed=123)
    assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == CUBLAS_WORKSPACE_CONFIG
    assert torch.are_deterministic_algorithms_enabled() is True


def test_enable_is_idempotent(restore_determinism: None) -> None:
    enable_deterministic_algorithms(seed=1)
    enable_deterministic_algorithms(seed=1)  # must not raise
    assert torch.are_deterministic_algorithms_enabled() is True


def test_enable_does_not_override_existing_cublas(restore_determinism: None) -> None:
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":16:8"
    enable_deterministic_algorithms()
    assert os.environ["CUBLAS_WORKSPACE_CONFIG"] == ":16:8"  # setdefault left it alone


def test_seeding_is_reproducible(restore_determinism: None) -> None:
    enable_deterministic_algorithms(seed=7)
    first = torch.rand(8)
    enable_deterministic_algorithms(seed=7)
    second = torch.rand(8)
    assert torch.equal(first, second)


def test_prepare_for_build_makes_weight_init_reproducible(restore_determinism: None) -> None:
    # Regression guard (FR-25): the runner calls `prepare_for_build(seed)` before
    # building the to-be-trained model so weight init is reproducible. Without it,
    # `build_model` draws from the process's entropy-seeded RNG and two runs of the
    # same recipe produce different weights (the determinism bug E.e surfaced).
    from modelfoundry.plugins.pytorch.plugin import PyTorchPlugin

    plugin = PyTorchPlugin()
    arch = {
        "num_classes": 3,
        "layers": [{"op": "Flatten"}, {"op": "Linear", "in_features": 12, "out_features": 3}],
    }
    plugin.prepare_for_build(7)
    first = [p.detach().clone() for p in plugin.build_model(arch).parameters()]
    plugin.prepare_for_build(7)
    second = [p.detach().clone() for p in plugin.build_model(arch).parameters()]
    assert first and all(torch.equal(a, b) for a, b in zip(first, second, strict=True))
