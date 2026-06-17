# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch lazy augmentation realizers (Story C.g).

Realizes a DataRefinery *lazy* `Augmentations` policy on-the-fly during training
via `torchvision.transforms.v2.functional`. DataRefinery captures lazy ops as a
manifest-bound `AugmentationPolicy` and leaves the materialized pixels unchanged
(vendor-dependency-spec § Materialization modes); ModelFoundry's framework
adapter (`data.py`) applies them at iteration time through the callable this
module composes.

The realizers target **visual semantics**, not byte-equivalence, with
DataRefinery's Pillow-based aggressive realizers — the two paths are different
code. That semantic equivalence is verified by the Hypothesis property tests in
Story E.g; this story lands the realizers + composer + their determinism.

Each realizer is a pure function of `(params, seed)`: it draws every random
decision from a local `torch.Generator` seeded from the supplied seed, so it
never perturbs the global RNG (preserving the determinism invariants in
`project-essentials.md` § Determinism contract is foundational) and reproduces
byte-for-byte given the same seed.

**Import-safe without `[pytorch]`:** the param models + `AUGMENTATION_PARAMS`
registry are pure pydantic at module top; `torch` / `torchvision` are imported
lazily inside `build_realizer`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from modelfoundry.core.errors import PluginError
from modelfoundry.pipeline.seeding import derive_seed

if TYPE_CHECKING:
    import torch

    Transform = Callable[[torch.Tensor], torch.Tensor]

# Generators want a non-negative 63-bit seed; mask the 64-bit `derive_seed` output.
_I64 = (1 << 63) - 1

# DataRefinery `padding_mode` vocabulary -> torchvision `F.pad` `padding_mode`.
_PAD_MODE: dict[str, str] = {
    "reflect": "reflect",
    "replicate": "edge",
    "zero": "constant",
    "constant": "constant",
}


# --- per-op param models (mirror the vendor-dependency-spec § Per-op param schemas) ---


class _AugmentationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HorizontalFlipParams(_AugmentationParams):
    p: float = Field(default=0.5, ge=0.0, le=1.0)


class RandomCropParams(_AugmentationParams):
    size: int | tuple[int, int]
    padding: int = Field(default=0, ge=0)
    padding_mode: Literal["reflect", "replicate", "zero", "constant"] = "reflect"


class ColorJitterParams(_AugmentationParams):
    brightness: float = Field(default=0.0, ge=0.0, le=1.0)
    contrast: float = Field(default=0.0, ge=0.0, le=1.0)
    saturation: float = Field(default=0.0, ge=0.0, le=1.0)
    hue: float = Field(default=0.0, ge=0.0, le=0.5)


class RandomErasingParams(_AugmentationParams):
    p: float = Field(default=0.5, ge=0.0, le=1.0)
    scale: tuple[float, float] = (0.02, 0.33)
    ratio: tuple[float, float] = (0.3, 3.3)


#: Augmentation op name -> param model. Used by `build_realizer` to validate the
#: bound DataRefinery `AugmentationOp.params` before realizing.
AUGMENTATION_PARAMS: dict[str, type[BaseModel]] = {
    "horizontal_flip": HorizontalFlipParams,
    "random_crop": RandomCropParams,
    "color_jitter": ColorJitterParams,
    "random_erasing": RandomErasingParams,
}


class AugmentationOp(BaseModel):
    """ModelFoundry's view of one DataRefinery lazy `AugmentationOp`.

    `extra="ignore"` so a full DataRefinery op dict (carrying `splits` /
    `materialization` / `expansion`, which the lazy realizer does not need) can be
    passed straight through. `name` is the op-instance id used to salt the
    per-op seed scope `"augmentation:<name>"`.
    """

    model_config = ConfigDict(extra="ignore")

    name: str
    op: str
    params: dict[str, Any] = {}
    seed: int | None = None


# --- realizers ---


def _validate(op: str, params: dict[str, Any]) -> BaseModel:
    model = AUGMENTATION_PARAMS.get(op)
    if model is None:
        raise PluginError(
            f"unknown augmentation op {op!r}; known: {sorted(AUGMENTATION_PARAMS)}",
            stage="build_augmentation",
        )
    try:
        return model(**params)
    except ValidationError as exc:
        raise PluginError(
            f"invalid params for augmentation op {op!r}: {exc}",
            stage="build_augmentation",
            detail={"op": op},
        ) from exc


# Realizers are **module-level classes**, not local closures (Story H.b). A closure
# captured by a `DataLoader` dataset cannot be pickled, so under the macOS `spawn`
# start method worker creation crashed with `Can't get local object
# 'build_realizer.<locals>.crop'`. A class instance holds only validated params + the
# masked seed (all picklable), so the composed policy survives the pickling spawn
# requires. `torch` / `torchvision` stay lazily imported inside `__call__`, preserving
# the import-safe-without-`[pytorch]` rule.


class _Realizer:
    """Base for a deterministic, picklable augmentation realizer.

    Subclasses implement `__call__(img) -> img`, drawing all randomness from a fresh
    `torch.Generator` seeded from `seed` — so the same `(op, params, seed)` always
    produces the same output.
    """

    def __init__(self, seed: int) -> None:
        self._seed = seed & _I64

    def _generator(self) -> torch.Generator:
        import torch

        return torch.Generator().manual_seed(self._seed)

    @staticmethod
    def _uniform(g: torch.Generator, low: float, high: float) -> float:
        import torch

        return float(torch.empty((), dtype=torch.float32).uniform_(low, high, generator=g))

    def __call__(self, img: torch.Tensor) -> torch.Tensor:  # pragma: no cover - abstract
        raise NotImplementedError


class _HorizontalFlip(_Realizer):
    def __init__(self, p: float, seed: int) -> None:
        super().__init__(seed)
        self._p = p

    def __call__(self, img: torch.Tensor) -> torch.Tensor:
        from torchvision.transforms.v2 import functional as F  # type: ignore[import-untyped]

        if self._uniform(self._generator(), 0.0, 1.0) < self._p:
            flipped: torch.Tensor = F.horizontal_flip(img)
            return flipped
        return img


class _RandomCrop(_Realizer):
    def __init__(self, th: int, tw: int, padding: int, pad_mode: str, seed: int) -> None:
        super().__init__(seed)
        self._th, self._tw, self._padding, self._pad_mode = th, tw, padding, pad_mode

    def __call__(self, img: torch.Tensor) -> torch.Tensor:
        import torch
        from torchvision.transforms.v2 import functional as F

        th, tw, padding = self._th, self._tw, self._padding
        if padding > 0:
            img = F.pad(img, [padding, padding, padding, padding], padding_mode=self._pad_mode)
        _, h, w = img.shape
        if h < th or w < tw:
            raise PluginError(
                f"random_crop size ({th}, {tw}) exceeds padded image ({h}, {w})",
                stage="build_augmentation",
                detail={"op": "random_crop"},
            )
        if h == th and w == tw:
            return img
        g = self._generator()
        i = int(torch.randint(0, h - th + 1, (), generator=g))
        j = int(torch.randint(0, w - tw + 1, (), generator=g))
        cropped: torch.Tensor = F.crop(img, i, j, th, tw)
        return cropped


class _ColorJitter(_Realizer):
    def __init__(self, b: float, c: float, s: float, hue: float, seed: int) -> None:
        super().__init__(seed)
        self._b, self._c, self._s, self._hue = b, c, s, hue

    def __call__(self, img: torch.Tensor) -> torch.Tensor:
        import torch
        from torchvision.transforms.v2 import functional as F

        b, c, s, hue = self._b, self._c, self._s, self._hue
        g = self._generator()
        # Randomized op order, matching torchvision ColorJitter's behavior.
        for which in torch.randperm(4, generator=g).tolist():
            if which == 0 and b > 0.0:
                img = F.adjust_brightness(img, 1.0 + self._uniform(g, -b, b))
            elif which == 1 and c > 0.0:
                img = F.adjust_contrast(img, 1.0 + self._uniform(g, -c, c))
            elif which == 2 and s > 0.0:
                img = F.adjust_saturation(img, 1.0 + self._uniform(g, -s, s))
            elif which == 3 and hue > 0.0:
                img = F.adjust_hue(img, self._uniform(g, -hue, hue))
        return img


class _RandomErasing(_Realizer):
    def __init__(
        self, p: float, scale: tuple[float, float], ratio: tuple[float, float], seed: int
    ) -> None:
        super().__init__(seed)
        self._p, self._scale, self._ratio = p, scale, ratio

    def __call__(self, img: torch.Tensor) -> torch.Tensor:
        import torch
        from torchvision.transforms.v2 import functional as F

        prob, scale, ratio = self._p, self._scale, self._ratio
        g = self._generator()
        if self._uniform(g, 0.0, 1.0) >= prob:
            return img
        _, h, w = img.shape
        area = h * w
        log_ratio = (math.log(ratio[0]), math.log(ratio[1]))
        for _ in range(10):
            target_area = self._uniform(g, scale[0], scale[1]) * area
            aspect = math.exp(self._uniform(g, log_ratio[0], log_ratio[1]))
            eh = round(math.sqrt(target_area * aspect))
            ew = round(math.sqrt(target_area / aspect))
            if eh < h and ew < w:
                i = int(torch.randint(0, h - eh + 1, (), generator=g))
                j = int(torch.randint(0, w - ew + 1, (), generator=g))
                erased: torch.Tensor = F.erase(
                    img, i, j, eh, ew, v=torch.zeros((), dtype=img.dtype)
                )
                return erased
        return img


class _ComposedTransform:
    """Picklable left-to-right composition of realizers (replaces a local closure)."""

    def __init__(self, realizers: list[Transform]) -> None:
        self._realizers = realizers

    def __call__(self, img: torch.Tensor) -> torch.Tensor:
        for realize in self._realizers:
            img = realize(img)
        return img


def build_realizer(op: str, params: dict[str, Any] | None, seed: int) -> Transform:
    """Return a deterministic, picklable transform for augmentation op `op`.

    The returned callable maps a normalized CHW float tensor to an augmented one,
    drawing all randomness from a `torch.Generator` seeded from `seed` — so the
    same `(op, params, seed)` always produces the same output.
    """
    p = _validate(op, params or {})

    if op == "horizontal_flip":
        assert isinstance(p, HorizontalFlipParams)
        return _HorizontalFlip(p.p, seed)

    if op == "random_crop":
        assert isinstance(p, RandomCropParams)
        th, tw = (p.size, p.size) if isinstance(p.size, int) else p.size
        return _RandomCrop(th, tw, p.padding, _PAD_MODE[p.padding_mode], seed)

    if op == "color_jitter":
        assert isinstance(p, ColorJitterParams)
        return _ColorJitter(p.brightness, p.contrast, p.saturation, p.hue, seed)

    if op == "random_erasing":
        assert isinstance(p, RandomErasingParams)
        return _RandomErasing(p.p, p.scale, p.ratio, seed)

    raise PluginError(f"augmentation op {op!r} is not constructible", stage="build_augmentation")


def compose_augmentations(
    augmentations: list[AugmentationOp], master_seed: int
) -> Transform | None:
    """Compose a lazy `Augmentations` policy into a single transform callable.

    Each op's seed is derived deterministically as
    `derive_seed(master_seed, "augmentation:<name>", <op.seed bytes>)`, matching
    the documented `"augmentation:<op_id>"` seeding scope (`pipeline.seeding`). The
    returned callable applies the ops left-to-right; it is `None` when the policy
    is empty (the no-augmentation path `data.py` expects).

    The returned `_ComposedTransform` and its realizers are picklable (Story H.b), so
    a `DataLoader` carrying an augmented dataset survives the pickling that worker
    processes require under the macOS `spawn` start method.

    Per-record variety (a distinct draw per example, independent of `num_workers`)
    is the trainer's concern (Story C.h): it re-salts the seed with the record id
    via this same scope. Composed here with the policy-level seed, the transform is
    fixed per construction — which is exactly what the determinism guarantee needs.
    """
    realizers: list[Transform] = []
    for op in augmentations:
        salt = op.seed.to_bytes(8, "big", signed=False) if op.seed is not None else b""
        seed = derive_seed(master_seed, f"augmentation:{op.name}", salt)
        realizers.append(build_realizer(op.op, op.params, seed))

    if not realizers:
        return None

    return _ComposedTransform(realizers)
