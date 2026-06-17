# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Torch-free guard for the random baseline's op registration (Story H.f.2).

Mirrors `test_sklearn_plugin_ops.py`: the random plugin's contract + materialize
tests are torch-gated (the baseline reuses the PyTorch feature path), so this
torch-free guard runs under the **default** `pyve test` (testenv) and catches an
op-registration regression — including the recognized no-op `Loss`/`Optimizer`
ops a `dummy_classifier` recipe needs to pass `validate()`.
"""

from __future__ import annotations

from modelfoundry.plugins.base import OperationSpec
from modelfoundry.plugins.random.plugin import RandomPlugin


def test_random_registers_dummy_classifier_and_noop_ops() -> None:
    ops = RandomPlugin().operations
    assert set(ops) == {"dummy_classifier", "cross_entropy", "none"}
    assert ops["dummy_classifier"].applies_to == "architecture"
    assert ops["cross_entropy"].applies_to == "loss"
    assert ops["none"].applies_to == "optimizer"
    for op_name, spec in ops.items():
        assert isinstance(spec, OperationSpec)
        assert spec.op_name == op_name
