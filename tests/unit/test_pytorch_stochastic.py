# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""MC-dropout stochastic-inference mechanism (Story H.m, R2.1 / R2.4).

Torch-gated (the mechanism imports `torch`); runs under `smoke-pytorch`. The
recipe-field contract is covered torch-free in `test_recipe_inference_spec.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

torch = pytest.importorskip("torch")

from torch import Tensor, nn  # noqa: E402

from modelfoundry.plugins.pytorch.architecture import build_model  # noqa: E402
from modelfoundry.plugins.pytorch.stochastic import (  # noqa: E402
    enable_mc_dropout,
    mc_forward_proba,
)

_N, _C, _H, _W = 4, 3, 4, 4
_NUM_CLASSES = 3


def _dropout_model() -> nn.Module:
    arch: dict[str, Any] = {
        "num_classes": _NUM_CLASSES,
        "layers": [
            {"op": "Flatten"},
            {"op": "Linear", "in_features": _C * _H * _W, "out_features": 16},
            {"op": "ReLU"},
            {"op": "Dropout", "p": 0.5},
            {"op": "Linear", "in_features": 16, "out_features": _NUM_CLASSES},
        ],
    }
    model: nn.Module = build_model(arch)
    return model


def _batch() -> Tensor:
    torch.manual_seed(0)
    batch: Tensor = torch.randn(_N, _C, _H, _W)
    return batch


def test_enable_mc_dropout_activates_only_dropout_modules() -> None:
    model = _dropout_model()
    enable_mc_dropout(model)
    dropouts = [m for m in model.modules() if isinstance(m, nn.Dropout)]
    assert dropouts, "fixture should contain a Dropout layer"
    assert all(m.training for m in dropouts)
    # Everything that is not a dropout module stays in eval mode.
    non_dropout = [m for m in model.modules() if not isinstance(m, nn.Dropout) and not m._modules]
    assert all(not m.training for m in non_dropout)


def test_mc_forward_proba_returns_stacked_per_pass_probabilities() -> None:
    model = _dropout_model()
    out = mc_forward_proba(model, _batch(), n_samples=8, master_seed=7)
    assert out.shape == (8, _N, _NUM_CLASSES)
    # Each pass is a probability distribution per record.
    sums = out.sum(dim=2)
    assert torch.allclose(sums, torch.ones_like(sums), atol=1e-5)


def test_passes_vary_because_dropout_is_active() -> None:
    model = _dropout_model()
    out = mc_forward_proba(model, _batch(), n_samples=12, master_seed=7)
    # Active dropout → the passes are not all identical.
    assert not torch.allclose(out[0], out[1])


def test_mc_forward_is_byte_identical_across_runs() -> None:
    model = _dropout_model()
    batch = _batch()
    first = mc_forward_proba(model, batch, n_samples=10, master_seed=7)
    second = mc_forward_proba(model, batch, n_samples=10, master_seed=7)
    assert first.numpy().tobytes() == second.numpy().tobytes()


def test_master_seed_changes_the_pass_sequence() -> None:
    model = _dropout_model()
    batch = _batch()
    a = mc_forward_proba(model, batch, n_samples=10, master_seed=7)
    b = mc_forward_proba(model, batch, n_samples=10, master_seed=8)
    assert a.numpy().tobytes() != b.numpy().tobytes()


def test_default_eval_pass_is_unchanged_dropout_inactive() -> None:
    # Criterion 5: the default single-pass path (plain eval()) leaves dropout
    # inactive, so repeated forward passes are identical point estimates.
    model = _dropout_model()
    model.eval()
    batch = _batch()
    with torch.no_grad():
        first = torch.softmax(model(batch), dim=1)
        second = torch.softmax(model(batch), dim=1)
    assert torch.equal(first, second)
