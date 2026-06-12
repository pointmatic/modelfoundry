# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PyTorch lazy augmentation realizers (Story C.g).

Determinism only: same `(op, params, seed)` -> byte-identical output, distinct
seeds diverge, and the policy composer threads per-op seeds reproducibly.
Semantic equivalence with DataRefinery's Pillow realizers is verified in E.g.
"""

from __future__ import annotations

from typing import Any

import pytest

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.pytorch.augmentations import (
    AUGMENTATION_PARAMS,
    AugmentationOp,
    build_realizer,
    compose_augmentations,
)

torch = pytest.importorskip("torch")


def _image(seed: int = 0) -> Any:
    """A deterministic normalized-looking CHW float image (3x16x16)."""
    g = torch.Generator().manual_seed(seed)
    return torch.rand(3, 16, 16, generator=g)


# --- registry ---


def test_registry_exposes_expected_ops() -> None:
    assert set(AUGMENTATION_PARAMS) == {
        "horizontal_flip",
        "random_crop",
        "color_jitter",
        "random_erasing",
    }


# --- per-op determinism ---


@pytest.mark.parametrize(
    ("op", "params"),
    [
        ("horizontal_flip", {"p": 1.0}),
        ("horizontal_flip", {"p": 0.5}),
        ("random_crop", {"size": 12, "padding": 2}),
        ("color_jitter", {"brightness": 0.4, "contrast": 0.4, "saturation": 0.4, "hue": 0.1}),
        ("random_erasing", {"p": 1.0}),
    ],
)
def test_realizer_is_deterministic_for_fixed_seed(op: str, params: dict[str, object]) -> None:
    img = _image()
    out_a = build_realizer(op, params, seed=1234)(img)
    out_b = build_realizer(op, params, seed=1234)(img)
    assert torch.equal(out_a, out_b)


@pytest.mark.parametrize(
    ("op", "params"),
    [
        ("random_crop", {"size": 12, "padding": 2}),
        ("color_jitter", {"brightness": 0.5, "hue": 0.2}),
        ("random_erasing", {"p": 1.0}),
    ],
)
def test_realizer_diverges_across_seeds(op: str, params: dict[str, object]) -> None:
    img = _image()
    out_a = build_realizer(op, params, seed=1)(img)
    out_b = build_realizer(op, params, seed=2)(img)
    assert not torch.equal(out_a, out_b)


def test_horizontal_flip_p1_actually_flips() -> None:
    img = _image()
    out = build_realizer("horizontal_flip", {"p": 1.0}, seed=0)(img)
    assert torch.equal(out, torch.flip(img, dims=[2]))


def test_horizontal_flip_p0_is_identity() -> None:
    img = _image()
    out = build_realizer("horizontal_flip", {"p": 0.0}, seed=0)(img)
    assert torch.equal(out, img)


def test_random_crop_output_shape() -> None:
    img = _image()
    out = build_realizer("random_crop", {"size": 16, "padding": 4}, seed=7)(img)
    assert out.shape == (3, 16, 16)


def test_random_erasing_p0_is_identity() -> None:
    img = _image()
    out = build_realizer("random_erasing", {"p": 0.0}, seed=0)(img)
    assert torch.equal(out, img)


# --- errors ---


def test_unknown_op_raises_plugin_error() -> None:
    with pytest.raises(PluginError, match="unknown augmentation op"):
        build_realizer("solarize", {}, seed=0)


def test_invalid_params_raise_plugin_error() -> None:
    with pytest.raises(PluginError, match="invalid params"):
        build_realizer("horizontal_flip", {"p": 1.5}, seed=0)


def test_random_crop_oversized_raises_plugin_error() -> None:
    img = _image()
    with pytest.raises(PluginError, match="exceeds padded image"):
        build_realizer("random_crop", {"size": 32}, seed=0)(img)


# --- composer ---


def test_compose_empty_policy_returns_none() -> None:
    assert compose_augmentations([], master_seed=99) is None


def test_compose_applies_ops_in_order_deterministically() -> None:
    img = _image()
    policy = [
        AugmentationOp(name="flip", op="horizontal_flip", params={"p": 1.0}),
        AugmentationOp(name="crop", op="random_crop", params={"size": 12, "padding": 2}),
    ]
    transform_a = compose_augmentations(policy, master_seed=42)
    transform_b = compose_augmentations(policy, master_seed=42)
    assert transform_a is not None and transform_b is not None
    assert torch.equal(transform_a(img), transform_b(img))
    assert transform_a(img).shape == (3, 12, 12)


def test_compose_master_seed_changes_output() -> None:
    img = _image()
    policy = [AugmentationOp(name="erase", op="random_erasing", params={"p": 1.0})]
    out_a = compose_augmentations(policy, master_seed=1)
    out_b = compose_augmentations(policy, master_seed=2)
    assert out_a is not None and out_b is not None
    assert not torch.equal(out_a(img), out_b(img))


def test_compose_per_op_seed_field_changes_output() -> None:
    img = _image()
    base = [AugmentationOp(name="erase", op="random_erasing", params={"p": 1.0})]
    salted = [AugmentationOp(name="erase", op="random_erasing", params={"p": 1.0}, seed=7)]
    out_base = compose_augmentations(base, master_seed=5)
    out_salted = compose_augmentations(salted, master_seed=5)
    assert out_base is not None and out_salted is not None
    assert not torch.equal(out_base(img), out_salted(img))


def test_augmentation_op_ignores_extra_datarefinery_fields() -> None:
    # A full DataRefinery op dict carries lazy-irrelevant fields; they're ignored.
    op = AugmentationOp.model_validate(
        {
            "name": "flip",
            "op": "horizontal_flip",
            "params": {"p": 0.5},
            "splits": ["train"],
            "materialization": "lazy",
            "expansion": 1,
        }
    )
    assert op.name == "flip" and op.op == "horizontal_flip"
