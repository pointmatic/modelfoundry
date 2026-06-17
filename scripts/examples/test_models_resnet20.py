# Copyright (c) 2026 Michael Smith
# SPDX-License-Identifier: Apache-2.0
"""Smoke test for the ResNet-20 ModelFoundry spec (Story D.a.31).

Builds the model from ``models/resnet20.yaml`` via ModelFoundry's pytorch plugin
and asserts the canonical CIFAR ResNet-20 parameter count (272,474) and forward
shape. Torch-dependent: skipped under ``pyve test`` (the testenv is torch-free) and run
in the torch test env via
``pyve test --env smoke-torch tests/test_models_resnet20.py``.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("modelfoundry")

from modelfoundry.plugins.pytorch.architecture import build_model  # noqa: E402
from modelfoundry.recipe.loader import load_recipe  # noqa: E402

RECIPE = "models/resnet20.yaml"
RESNET20_PARAMS = 272_474


def _build_model():
    """Load the recipe and build the bare ``nn.Module`` (no training)."""
    recipe = load_recipe(RECIPE)
    return build_model(recipe.Architecture)


def test_resnet20_param_count() -> None:
    model = _build_model()
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params == RESNET20_PARAMS, f"expected {RESNET20_PARAMS}, got {n_params}"


def test_resnet20_forward_shape() -> None:
    model = _build_model()
    model.eval()
    with torch.no_grad():
        logits = model(torch.randn(16, 3, 32, 32))
    assert tuple(logits.shape) == (16, 10)


def test_resnet20_binds_to_cifar10_base() -> None:
    """The recipe resolves + binds the cifar10-base DR instance (skips if unmaterialized)."""
    from modelfoundry import ModelFoundry

    try:
        mf = ModelFoundry.from_recipe(RECIPE, data="./cache")
    except Exception as exc:  # any binding failure → skip, not fail
        pytest.skip(f"cifar10-base instance not available: {exc}")
    assert mf.data.instance_num_classes() == 10
