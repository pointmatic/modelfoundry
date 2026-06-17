# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for PyTorch lazy augmentation realizers (Stories C.g + E.g).

C.g — determinism: same `(op, params, seed)` -> byte-identical output, distinct
seeds diverge, and the policy composer threads per-op seeds reproducibly.

E.g — visual-semantic equivalence with DataRefinery's Pillow/NumPy *aggressive*
realizers (TR-9). The two stacks are deliberately different code: ModelFoundry's
lazy realizer is torchvision-v2 on a CHW float tensor seeded from a
`torch.Generator`; DataRefinery's aggressive realizer is Pillow/NumPy on an HWC
uint8 array seeded from `numpy.random.default_rng`. **Byte-equivalence is not
asserted** (the story says so explicitly), and two facts make literal
"same output for the same seed" impossible on random *placement*:

1. The RNG backends are independent — the same integer seed yields different
   draw sequences, so crop locations / erase rectangles differ.
2. `random_erasing` even fills differently by design — ModelFoundry erases to 0,
   DataRefinery erases to the image mean.

So equivalence is asserted on the regimes where the *visual outcome* is
RNG-invariant: deterministic flip probabilities (`p ∈ {0, 1}`), output
dimensions, uniform-image content (where placement is immaterial), and
colour-space statistics — all within a documented uint8↔float tolerance. These
are property tests (Hypothesis generates the images).
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.pytorch.augmentations import (
    AUGMENTATION_PARAMS,
    AugmentationOp,
    build_realizer,
    compose_augmentations,
)

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")
# The E.g equivalence tests bind against DataRefinery's aggressive realizers; the
# C.g determinism tests above need only torch. In practice both run in the same
# (torch + datarefinery) env, so importorskip-ing here costs the C.g tests nothing.
pytest.importorskip("datarefinery")
pytest.importorskip("PIL")
from datarefinery.plugins.image_classification.augmentations.color_jitter import (  # noqa: E402
    realize_color_jitter,
)
from datarefinery.plugins.image_classification.augmentations.horizontal_flip import (  # noqa: E402
    realize_horizontal_flip,
)
from datarefinery.plugins.image_classification.augmentations.random_crop import (  # noqa: E402
    realize_random_crop,
)
from datarefinery.plugins.image_classification.augmentations.random_erasing import (  # noqa: E402
    realize_random_erasing,
)

# uint8 -> float32/255 is exact for matching integers, so flip/crop *content*
# matches to the float epsilon; this tolerance just guards the round-trip.
_DOC_TOL = 1e-6


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


# === E.g: cross-realizer visual-semantic equivalence (TR-9, Hypothesis) ===


def _chw_float(img: Any) -> Any:
    """HWC uint8 image -> CHW float32 in [0, 1] (the ModelFoundry realizer input)."""
    return torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1).to(torch.float32) / 255.0


def _mf_to_hwc(tensor: Any) -> Any:
    """ModelFoundry CHW-float output -> HWC float32 numpy (common comparison frame)."""
    return tensor.permute(1, 2, 0).numpy()


def _hwc_float(img_uint8: Any) -> Any:
    """DataRefinery HWC uint8 output -> HWC float32 numpy."""
    return img_uint8.astype(np.float32) / 255.0


def _dr_image(data: Any, *, lo: int = 8, hi: int = 16) -> Any:
    """Draw a random HWC uint8 RGB image."""
    h = data.draw(st.integers(lo, hi))
    w = data.draw(st.integers(lo, hi))
    return data.draw(arrays(np.uint8, (h, w, 3), elements=st.integers(0, 255)))


def _uniform_image(data: Any, *, lo: int = 8, hi: int = 16) -> tuple[Any, tuple[int, int, int]]:
    """Draw a spatially-uniform HWC uint8 image and its fill colour."""
    side = data.draw(st.integers(lo, hi))
    color = data.draw(st.tuples(st.integers(0, 255), st.integers(0, 255), st.integers(0, 255)))
    return np.full((side, side, 3), color, dtype=np.uint8), color


# --- horizontal_flip: the geometric outcome is RNG-invariant at p ∈ {0, 1} ---


@given(data=st.data())
@settings(max_examples=20, deadline=None)
def test_horizontal_flip_p1_matches_across_realizers(data: Any) -> None:
    img = _dr_image(data)
    dr_out = realize_horizontal_flip({"image": img}, seed=3, variant_index=0, params={"p": 1.0})[
        "image"
    ]
    mf_out = build_realizer("horizontal_flip", {"p": 1.0}, seed=3)(_chw_float(img))
    # Both flip the width axis (DataRefinery axis 1 of HWC; ModelFoundry axis 2 of CHW).
    assert np.array_equal(dr_out, img[:, ::-1, :])
    assert np.allclose(_mf_to_hwc(mf_out), _hwc_float(dr_out), atol=_DOC_TOL)


@given(data=st.data())
@settings(max_examples=20, deadline=None)
def test_horizontal_flip_p0_is_identity_across_realizers(data: Any) -> None:
    img = _dr_image(data)
    dr_out = realize_horizontal_flip({"image": img}, seed=3, variant_index=0, params={"p": 0.0})[
        "image"
    ]
    mf_out = build_realizer("horizontal_flip", {"p": 0.0}, seed=3)(_chw_float(img))
    assert np.array_equal(dr_out, img)
    assert torch.equal(mf_out, _chw_float(img))


# --- random_crop: output dimensions always match; content matches on uniform images ---


@given(data=st.data())
@settings(max_examples=25, deadline=None)
def test_random_crop_output_dimensions_match(data: Any) -> None:
    h = data.draw(st.integers(12, 18))
    w = data.draw(st.integers(12, 18))
    img = data.draw(arrays(np.uint8, (h, w, 3), elements=st.integers(0, 255)))
    size = data.draw(st.integers(4, min(h, w)))
    padding = data.draw(st.integers(0, 4))
    params: dict[str, object] = {"size": size, "padding": padding, "padding_mode": "reflect"}

    dr_out = realize_random_crop({"image": img}, seed=5, variant_index=0, params=params)["image"]
    mf_out = build_realizer("random_crop", params, seed=5)(_chw_float(img))
    assert dr_out.shape[:2] == (size, size)
    assert tuple(mf_out.shape) == (3, size, size)


@given(data=st.data())
@settings(max_examples=20, deadline=None)
def test_random_crop_uniform_content_matches(data: Any) -> None:
    img, color = _uniform_image(data, lo=10, hi=16)
    size = data.draw(st.integers(4, img.shape[0]))
    params: dict[str, object] = {"size": size, "padding": 0}

    dr_out = realize_random_crop({"image": img}, seed=9, variant_index=0, params=params)["image"]
    mf_out = build_realizer("random_crop", params, seed=9)(_chw_float(img))
    # A uniform image crops to the same constant colour regardless of crop location.
    expected = np.full((size, size, 3), color, dtype=np.uint8)
    assert np.array_equal(dr_out, expected)
    assert np.allclose(_mf_to_hwc(mf_out), _hwc_float(expected), atol=_DOC_TOL)


# --- color_jitter: identity at zero magnitude; preserves uniformity (colour-space stat) ---


@given(data=st.data())
@settings(max_examples=20, deadline=None)
def test_color_jitter_zero_magnitude_is_identity(data: Any) -> None:
    img = _dr_image(data)
    params = {"brightness": 0.0, "contrast": 0.0, "saturation": 0.0, "hue": 0.0}
    dr_out = realize_color_jitter({"image": img}, seed=2, variant_index=0, params=params)["image"]
    mf_out = build_realizer("color_jitter", params, seed=2)(_chw_float(img))
    assert np.array_equal(dr_out, img)
    assert torch.equal(mf_out, _chw_float(img))


@given(data=st.data())
@settings(max_examples=20, deadline=None)
def test_color_jitter_preserves_spatial_uniformity(data: Any) -> None:
    # The colour-space statistic that survives the RNG-stream divergence: a
    # spatially-uniform image stays uniform under jitter (every pixel transformed
    # identically), even though the two realizers pick different jitter magnitudes.
    img, _ = _uniform_image(data, lo=8, hi=14)
    params = {"brightness": 0.5, "contrast": 0.5, "saturation": 0.5}
    dr_out = realize_color_jitter({"image": img}, seed=4, variant_index=0, params=params)["image"]
    mf_out = build_realizer("color_jitter", params, seed=4)(_chw_float(img))

    assert float(dr_out.reshape(-1, 3).std(axis=0).max()) == pytest.approx(0.0, abs=1e-6)
    assert float(mf_out.reshape(3, -1).std(dim=1).max()) == pytest.approx(0.0, abs=1e-4)
    assert dr_out.shape == img.shape
    assert tuple(mf_out.shape) == (3, img.shape[0], img.shape[1])


# --- random_erasing: dimensions preserved both ways; identity at p=0 (fill differs by design) ---


@given(data=st.data())
@settings(max_examples=20, deadline=None)
def test_random_erasing_preserves_shape(data: Any) -> None:
    img = _dr_image(data, lo=10, hi=16)
    dr_out = realize_random_erasing({"image": img}, seed=8, variant_index=0, params={"p": 1.0})[
        "image"
    ]
    mf_out = build_realizer("random_erasing", {"p": 1.0}, seed=8)(_chw_float(img))
    assert dr_out.shape == img.shape
    assert tuple(mf_out.shape) == (3, img.shape[0], img.shape[1])


@given(data=st.data())
@settings(max_examples=20, deadline=None)
def test_random_erasing_p0_is_identity_across_realizers(data: Any) -> None:
    img = _dr_image(data, lo=10, hi=16)
    dr_out = realize_random_erasing({"image": img}, seed=8, variant_index=0, params={"p": 0.0})[
        "image"
    ]
    mf_out = build_realizer("random_erasing", {"p": 0.0}, seed=8)(_chw_float(img))
    assert np.array_equal(dr_out, img)
    assert torch.equal(mf_out, _chw_float(img))


# --- spawn-safety: composed policy + realizers must pickle (Story H.b) ---


def test_composed_transform_is_picklable_and_deterministic() -> None:
    """Composed policy + realizers must pickle for `spawn` DataLoader workers (H.b).

    Pre-H.b the composer and each realizer were local closures
    (`compose_augmentations.<locals>.apply`, `build_realizer.<locals>.crop`, ...),
    which `pickle` cannot serialize.
    """
    import pickle

    ops = [
        AugmentationOp(name="rc", op="random_crop", params={"size": 4, "padding": 1}),
        AugmentationOp(name="hf", op="horizontal_flip", params={"p": 1.0}),
        AugmentationOp(name="cj", op="color_jitter", params={"brightness": 0.2}),
    ]
    transform = compose_augmentations(ops, master_seed=7)
    assert transform is not None

    restored = pickle.loads(pickle.dumps(transform))  # pre-fix: unpicklable local closure

    img = torch.rand(3, 4, 4)
    assert torch.equal(transform(img), restored(img))  # pickling preserves determinism


def test_single_realizer_is_picklable() -> None:
    """Each `build_realizer` output must itself pickle (composition holds a list of them)."""
    import pickle

    realizer = build_realizer("random_crop", {"size": 4, "padding": 1}, seed=11)
    restored = pickle.loads(pickle.dumps(realizer))
    img = torch.rand(3, 4, 4)
    assert torch.equal(realizer(img), restored(img))
