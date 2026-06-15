# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch plugin contract test (Story E.i, tech-spec § Plugin contract tests).

Pins the substrate-neutral `Plugin` contract for the shipped PyTorch plugin:

1. **Exhaustive `OperationSpec` set** — every op the spec names is registered.
   The closed pre-production vocabularies (`Loss` / `Optimizer` / schedule /
   `Visualizations`, per `features.md` FR-LOSS-1 / FR-OPT-1 / the Visualizations
   block) must match *exactly*; the FR-ARCH-1 baseline architectures must each be
   present (the plugin registers additional building-block ops — `Conv2d`,
   `ResidualBlock`, … — beyond the spec's named set, so architecture is a subset
   check). Augmentations are deliberately *not* recipe ops (they're realized from
   the bound DataRefinery policy), so they are absent from the registry by design.
2. **Protocol conformance** — both statically (mypy verifies the `-> Plugin`
   return annotation on `_plugin()`; the env-level `mypy src tests --strict` gate
   enforces it, which also covers "`mypy --strict` clean on the plugin source")
   and at runtime via the `@runtime_checkable` `isinstance` check.
3. **`health_check()` shape** — returns the `CheckReport` structural surface the
   `check` verb depends on (FR-19).
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from modelfoundry.plugins.base import CheckReport, OperationSpec, Plugin
from modelfoundry.plugins.pytorch.plugin import PyTorchPlugin

# The op vocabulary named in features.md. The first four are closed pre-production
# sets (asserted by equality); the baseline architectures are asserted by subset.
_FEATURES_LOSS = {"cross_entropy", "cross_entropy_class_weighted", "bce_with_logits"}
_FEATURES_OPTIMIZER = {"adamw", "sgd", "adam"}
_FEATURES_SCHEDULE = {"reduce_on_plateau", "cosine", "linear_warmup"}
_FEATURES_VISUALIZATION = {
    "training_curves",
    "optimization_history",
    "confusion_matrix",
    "calibration_curve",
    "predictions_grid",
}
_FEATURES_BASELINE_ARCH = {"simple_cnn", "resnet8", "resnet20"}


def _plugin() -> Plugin:
    """The PyTorch plugin, typed as `Plugin` so mypy verifies Protocol conformance."""
    return PyTorchPlugin()


def test_pytorch_satisfies_plugin_protocol_at_runtime() -> None:
    assert isinstance(_plugin(), Plugin)


def test_every_operation_spec_is_well_formed() -> None:
    for name, spec in _plugin().operations.items():
        assert isinstance(spec, OperationSpec)
        assert spec.op_name == name  # the registry key is the op's own name
        assert issubclass(spec.param_model, BaseModel)


def test_pytorch_operation_set_is_exhaustive() -> None:
    by_stage: dict[str, set[str]] = defaultdict(set)
    for name, spec in _plugin().operations.items():
        by_stage[spec.applies_to].add(name)

    # Closed pre-production vocabularies — registered set IS the features.md set.
    assert by_stage["loss"] == _FEATURES_LOSS
    assert by_stage["optimizer"] == _FEATURES_OPTIMIZER
    assert by_stage["schedule"] == _FEATURES_SCHEDULE
    assert by_stage["visualization"] == _FEATURES_VISUALIZATION
    # Every features.md baseline architecture is registered (building blocks may exceed it).
    assert by_stage["architecture"] >= _FEATURES_BASELINE_ARCH


def test_pytorch_health_check_returns_check_report_shape() -> None:
    report = _plugin().health_check()
    assert isinstance(report, CheckReport)  # structural @runtime_checkable Protocol
    assert report.plugin == "pytorch"
    assert isinstance(report.available, bool)
    assert isinstance(report.accelerators, tuple)
