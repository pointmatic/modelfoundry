# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Torch-free guard for the sklearn baseline's op registration (Story H.f.1).

The sklearn baseline reuses the PyTorch feature path, so its *materialize* and
*contract* tests are gated on torch and run only under
`pyve test --env smoke-pytorch`. The op-registration fix itself, though, is
torch-free: the baseline now registers the `Loss`/`Optimizer` ops its recipes
declare so they pass `validate()`. This guard asserts that contract with no torch
stack, so a registration regression is caught by the **default** `pyve test`
(testenv), not only the heavy torch env.
"""

from __future__ import annotations

from modelfoundry.plugins.base import OperationSpec
from modelfoundry.plugins.sklearn.plugin import SklearnPlugin


def test_sklearn_registers_loss_and_optimizer_ops() -> None:
    ops = SklearnPlugin().operations
    # The architecture op plus the Loss/Optimizer ops the teaching recipe declares
    # (`cifar10_mlp.yml`): without these, validator check 3 rejects the recipe.
    assert set(ops) == {"mlp_classifier", "cross_entropy", "adam", "sgd"}
    assert ops["mlp_classifier"].applies_to == "architecture"
    assert ops["cross_entropy"].applies_to == "loss"
    assert {ops["adam"].applies_to, ops["sgd"].applies_to} == {"optimizer"}
    for op_name, spec in ops.items():
        assert isinstance(spec, OperationSpec)
        assert spec.op_name == op_name
