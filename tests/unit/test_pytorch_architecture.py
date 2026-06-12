# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `plugins.pytorch.architecture` (FR-7 / FR-ARCH-1, Story C.c)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import OperationSpec
from modelfoundry.plugins.pytorch.architecture import (
    ARCHITECTURE_OPERATIONS,
    build_model,
)

torch = pytest.importorskip("torch")


_EXPECTED_OPS = {
    # primitives
    "Conv2d", "BatchNorm2d", "ReLU", "MaxPool2d", "AvgPool2d",
    "AdaptiveAvgPool2d", "Linear", "Dropout", "Flatten",
    # composites
    "MLP", "ConvBlock", "ResidualBlock",
    # baselines
    "simple_cnn", "resnet8", "resnet20",
    # deferred pretrained-encoder path
    "Encoder", "LoRA", "Pooling", "Head",
}


def _module_inventory(model: Any) -> dict[str, int]:
    counts = Counter(type(m).__name__ for m in model.modules())
    return dict(counts)


# --- registry ---


def test_every_op_is_registered_as_operation_spec() -> None:
    assert set(ARCHITECTURE_OPERATIONS) == _EXPECTED_OPS
    for name, spec in ARCHITECTURE_OPERATIONS.items():
        assert isinstance(spec, OperationSpec)
        assert spec.op_name == name
        assert spec.applies_to == "architecture"


def test_huggingface_ops_declare_requires_extras() -> None:
    for name in ("Encoder", "LoRA", "Pooling", "Head"):
        assert ARCHITECTURE_OPERATIONS[name].requires_extras == ("huggingface",)
    # Core ops require nothing.
    assert ARCHITECTURE_OPERATIONS["Conv2d"].requires_extras == ()


# --- baseline architectures ---


@pytest.mark.parametrize("name", ["simple_cnn", "resnet8", "resnet20"])
def test_baseline_instantiates_and_forwards(name: str) -> None:
    model = build_model({"type": name, "num_classes": 10})
    out = model(torch.zeros(2, 3, 32, 32))
    assert tuple(out.shape) == (2, 10)


def test_resnet20_canonical_inventory_and_param_count() -> None:
    """Pin resnet20 so the canonical CIFAR ResNet-20 cannot silently drift.

    272,474 params with option-B projection shortcuts: a 3x3 stem conv + three
    stages of three BasicBlocks (16/32/64 ch) + two 1x1 downsampling shortcuts
    = 21 convs / 21 batchnorms, and a single Linear head.
    """
    model = build_model({"type": "resnet20", "num_classes": 10})
    param_count = sum(p.numel() for p in model.parameters())
    assert param_count == 272_474
    inv = _module_inventory(model)
    assert inv["Conv2d"] == 21
    assert inv["BatchNorm2d"] == 21
    assert inv["Linear"] == 1


def test_baseline_respects_num_classes_and_in_channels() -> None:
    model = build_model({"type": "resnet8", "num_classes": 4, "in_channels": 1})
    out = model(torch.zeros(2, 1, 32, 32))
    assert tuple(out.shape) == (2, 4)


# --- explicit layer composition ---


def test_explicit_layers_compose_in_order() -> None:
    model = build_model(
        {
            "num_classes": 10,
            "layers": [
                {"op": "Conv2d", "in_channels": 3, "out_channels": 8, "padding": 1},
                {"op": "BatchNorm2d", "num_features": 8},
                {"op": "ReLU"},
                {"op": "AdaptiveAvgPool2d", "output_size": 1},
                {"op": "Flatten"},
                {"op": "Linear", "in_features": 8, "out_features": 10},
            ],
        }
    )
    out = model(torch.zeros(2, 3, 32, 32))
    assert tuple(out.shape) == (2, 10)


def test_composite_ops_build() -> None:
    mlp = build_model(
        {
            "num_classes": 10,
            "layers": [
                {"op": "Flatten"},
                {"op": "MLP", "in_features": 3 * 8 * 8, "hidden_dims": [32, 16], "num_classes": 10},
            ],
        }
    )
    assert tuple(mlp(torch.zeros(2, 3, 8, 8)).shape) == (2, 10)


# --- error mapping ---


@pytest.mark.parametrize(
    "spec",
    [
        {"type": "resnet20"},  # missing num_classes
        {"num_classes": 0, "type": "resnet8"},  # non-positive
        {"num_classes": 10, "type": "does_not_exist"},  # unknown baseline
        {"num_classes": 10},  # neither type nor layers
        {"num_classes": 10, "type": "resnet8", "layers": []},  # both
        {"num_classes": 10, "layers": [{"op": "Conv2d", "bogus": 1}]},  # bad op params
        {"num_classes": 10, "layers": [{"op": "NotAnOp"}]},  # unknown op
        {"num_classes": 10, "layers": "not-a-list"},  # malformed layers
    ],
)
def test_bad_arch_raises_plugin_error(spec: dict[str, Any]) -> None:
    with pytest.raises(PluginError):
        build_model(spec)


def test_pretrained_encoder_without_extras_raises_importerror() -> None:
    # [huggingface] is not installed in the test env -> clear ImportError with pointer.
    import importlib.util

    if importlib.util.find_spec("transformers") is not None:
        pytest.skip("transformers installed; the ImportError-without-extras path is not exercised")
    with pytest.raises(ImportError, match=r"\[huggingface\]"):
        build_model({"num_classes": 10, "layers": [{"op": "Encoder", "id": "bert-base"}]})
