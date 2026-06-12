# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PyTorch losses / optimizers / schedules (FR-LOSS-1/OPT-1/OPT-2, C.d)."""

from __future__ import annotations

from typing import Any

import pytest

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.pytorch.losses import (
    LOSS_OPERATIONS,
    build_loss,
    derive_class_weights,
)
from modelfoundry.plugins.pytorch.optimizers import OPTIMIZER_OPERATIONS, build_optimizer
from modelfoundry.plugins.pytorch.schedules import SCHEDULE_OPERATIONS, build_schedule

torch = pytest.importorskip("torch")


# --- registries ---


def test_registries_expose_expected_ops() -> None:
    assert set(LOSS_OPERATIONS) == {
        "cross_entropy",
        "cross_entropy_class_weighted",
        "bce_with_logits",
    }
    assert set(OPTIMIZER_OPERATIONS) == {"adamw", "sgd", "adam"}
    assert set(SCHEDULE_OPERATIONS) == {"reduce_on_plateau", "cosine", "linear_warmup"}
    assert all(s.applies_to == "loss" for s in LOSS_OPERATIONS.values())
    assert all(s.applies_to == "optimizer" for s in OPTIMIZER_OPERATIONS.values())
    assert all(s.applies_to == "schedule" for s in SCHEDULE_OPERATIONS.values())


# --- losses ---


def test_cross_entropy_builds() -> None:
    assert isinstance(build_loss("cross_entropy"), torch.nn.CrossEntropyLoss)


def test_class_weighted_loss_carries_weight_tensor() -> None:
    loss = build_loss(
        "cross_entropy_class_weighted",
        {"weight_source": "train"},
        class_weights=[0.5, 1.5, 1.0],
    )
    assert isinstance(loss, torch.nn.CrossEntropyLoss)
    assert loss.weight is not None
    assert torch.allclose(loss.weight, torch.tensor([0.5, 1.5, 1.0]))


def test_bce_with_logits_binary_ok_multiclass_rejected() -> None:
    assert isinstance(build_loss("bce_with_logits", num_classes=2), torch.nn.BCEWithLogitsLoss)
    with pytest.raises(PluginError, match="binary-only"):
        build_loss("bce_with_logits", num_classes=3)


def test_unknown_loss_op_raises() -> None:
    with pytest.raises(PluginError, match="unknown loss op"):
        build_loss("focal")


# --- class-weight derivation ---


def test_balanced_distribution_yields_uniform_weights() -> None:
    for source in ("train", "train_inverse_frequency", "effective_number"):
        weights = derive_class_weights(source, [10, 10, 10])
        assert weights == pytest.approx([1.0, 1.0, 1.0])


@pytest.mark.parametrize("source", ["train", "train_inverse_frequency", "effective_number"])
def test_imbalanced_distribution_upweights_minority(source: str) -> None:
    # Majority class 0 (80), minorities 1 and 2 (10 each).
    weights = derive_class_weights(source, [80, 10, 10])
    assert weights[1] > weights[0]
    assert weights[2] > weights[0]
    # Mean-normalized to ~1.0.
    assert sum(weights) == pytest.approx(len(weights))


def test_class_weight_errors() -> None:
    with pytest.raises(PluginError, match="empty"):
        derive_class_weights("train", [])
    with pytest.raises(PluginError, match="unknown weight_source"):
        derive_class_weights("bogus", [1, 2, 3])


# --- optimizers ---


def _params() -> Any:
    return torch.nn.Linear(4, 2).parameters()


def test_adamw_builds_with_hyperparameters() -> None:
    opt = build_optimizer(
        "adamw", {"learning_rate": 0.002, "weight_decay": 0.05, "betas": [0.8, 0.95]}, _params()
    )
    assert isinstance(opt, torch.optim.AdamW)
    g = opt.param_groups[0]
    assert g["lr"] == pytest.approx(0.002)
    assert g["weight_decay"] == pytest.approx(0.05)
    assert tuple(g["betas"]) == (0.8, 0.95)


def test_sgd_builds_with_hyperparameters() -> None:
    opt = build_optimizer(
        "sgd", {"learning_rate": 0.1, "momentum": 0.9, "nesterov": True}, _params()
    )
    assert isinstance(opt, torch.optim.SGD)
    g = opt.param_groups[0]
    assert g["lr"] == pytest.approx(0.1)
    assert g["momentum"] == pytest.approx(0.9)
    assert g["nesterov"] is True


def test_adam_builds() -> None:
    opt = build_optimizer("adam", {"learning_rate": 0.001}, _params())
    assert isinstance(opt, torch.optim.Adam)
    assert opt.param_groups[0]["lr"] == pytest.approx(0.001)


def test_unknown_optimizer_op_raises() -> None:
    with pytest.raises(PluginError, match="unknown optimizer op"):
        build_optimizer("rmsprop", {"learning_rate": 0.1}, _params())


# --- schedules ---


def _optimizer() -> Any:
    return torch.optim.SGD(torch.nn.Linear(4, 2).parameters(), lr=0.1)


def test_reduce_on_plateau_builds() -> None:
    sched = build_schedule(
        "reduce_on_plateau", {"mode": "max", "factor": 0.3, "patience": 5}, _optimizer()
    )
    assert isinstance(sched, torch.optim.lr_scheduler.ReduceLROnPlateau)
    assert sched.factor == pytest.approx(0.3)
    assert sched.patience == 5
    assert sched.mode == "max"


def test_cosine_builds() -> None:
    sched = build_schedule("cosine", {"T_max": 50, "eta_min": 0.01}, _optimizer())
    assert isinstance(sched, torch.optim.lr_scheduler.CosineAnnealingLR)
    assert sched.T_max == 50
    assert sched.eta_min == pytest.approx(0.01)


def test_linear_warmup_builds_and_warms_up() -> None:
    optimizer = _optimizer()
    sched = build_schedule(
        "linear_warmup", {"warmup_steps": 2, "total_steps": 10}, optimizer
    )
    assert isinstance(sched, torch.optim.lr_scheduler.LambdaLR)
    lr_at_start = optimizer.param_groups[0]["lr"]
    optimizer.step()  # establish optimizer-before-scheduler ordering (no grads → no-op)
    sched.step()
    sched.step()
    lr_after_warmup = optimizer.param_groups[0]["lr"]
    assert lr_after_warmup > lr_at_start  # lr ramped up over the warmup window


def test_unknown_schedule_op_raises() -> None:
    with pytest.raises(PluginError, match="unknown schedule op"):
        build_schedule("onecycle", {}, _optimizer())
