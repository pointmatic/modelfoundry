# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch model summary (FR-27, Story C.q).

Generates a `torchinfo`-backed model summary as a **materialize-time artifact**
so it is reproducible and readable from disk alone. Two files land under the
instance's `model/` directory:

* `model/summary.txt` — the `torchinfo` text render (per-layer table + totals).
* `model/summary.json` — the structured rows + network totals (a `ModelSummary`).

Both are **byte-deterministic** for a fixed architecture + input size: the
reported quantities (per-layer type / output shape / parameter count / mult-adds
and the network totals) are functions of the architecture, not of the (random)
probe input torchinfo feeds the forward pass, and the artifact carries no
timestamp. The probe runs in `eval` mode (BatchNorm running stats are not
perturbed) and the model's `training` flag is snapshotted and restored, so
writing the summary never mutates the persisted model.

This module imports `torch` / `torchinfo` at the top: like `data.py` /
`persistence.py` it is loaded at materialize time (the plugin delegates here
lazily via `write_model_summary`), not during plugin discovery, so the
import-safe-without-`[pytorch]` rule does not apply here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torchinfo
from pydantic import BaseModel, ConfigDict
from torch import nn

_SUMMARY_TXT = "summary.txt"
_SUMMARY_JSON = "summary.json"

# Display depth for the torchinfo traversal. 3 reaches the conv/batchnorm leaves
# inside the CIFAR ResidualBlocks, so the per-layer inventory is complete for the
# baseline architectures while keeping the table readable.
_DEPTH = 3


class LayerSummary(BaseModel):
    """One row of the model summary — a single module in the torchinfo traversal."""

    model_config = ConfigDict(extra="forbid")

    type: str  # the module class name, e.g. "Conv2d"
    depth: int  # nesting depth in the module tree (0 = the root module)
    leaf: bool  # True for a leaf module (no registered children)
    output_shape: list[int]  # the module's output size, including the batch dim
    param_count: int
    trainable_params: int
    mult_adds: int  # multiply-add operations (torchinfo MACs)


class ModelSummary(BaseModel):
    """Structured model summary written to `model/summary.json`."""

    model_config = ConfigDict(extra="forbid")

    input_size: list[int]  # (N, C, H, W) the summary was computed for
    layers: list[LayerSummary]
    total_params: int
    trainable_params: int
    non_trainable_params: int
    total_mult_adds: int


def summarize(
    model: nn.Module, input_size: tuple[int, ...]
) -> tuple[ModelSummary, str]:
    """Run torchinfo once; return the structured `ModelSummary` and the text render.

    The model is probed in `eval` mode and its `training` flag is restored
    afterward, so the call has no side effect on the model's state.
    """
    was_training = model.training
    try:
        stats = torchinfo.summary(
            model, input_size=tuple(input_size), depth=_DEPTH, verbose=0, mode="eval"
        )
    finally:
        model.train(was_training)

    layers = [
        LayerSummary(
            type=info.class_name,
            depth=int(info.depth),
            leaf=bool(info.is_leaf_layer),
            output_shape=[int(d) for d in (info.output_size or [])],
            param_count=int(info.num_params),
            trainable_params=int(info.trainable_params),
            mult_adds=int(info.macs),
        )
        for info in stats.summary_list
    ]
    summary = ModelSummary(
        input_size=[int(d) for d in input_size],
        layers=layers,
        total_params=int(stats.total_params),
        trainable_params=int(stats.trainable_params),
        non_trainable_params=int(stats.total_params - stats.trainable_params),
        total_mult_adds=int(stats.total_mult_adds),
    )
    return summary, str(stats)


def write_summary(
    model: nn.Module, input_size: tuple[int, ...], model_dir: str | Path
) -> ModelSummary:
    """Write `summary.txt` + `summary.json` under `model_dir`; return the summary.

    The JSON is canonicalized (`sort_keys`) so the artifact is byte-stable.
    """
    summary, text = summarize(model, input_size)
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / _SUMMARY_TXT).write_text(text + "\n", encoding="utf-8")
    (model_dir / _SUMMARY_JSON).write_text(
        json.dumps(summary.model_dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def derive_input_size(data_instance: Any) -> tuple[int, int, int, int]:
    """Derive the `(N, C, H, W)` probe shape from the bound DataRefinery instance.

    Primary path: read the image entry of the instance's record schema, whose
    `shape` is `[H, W, C]` (DataRefinery's HWC image convention), and reorder to
    `(1, C, H, W)`. Fallback: decode one record through the C.f dataset adapter —
    which yields exactly the `(C, H, W)` tensor the model is trained on — when the
    schema declares no usable image shape.
    """
    record_schema = getattr(data_instance, "record_schema", None) or {}
    hwc = _image_hwc_from_schema(record_schema)
    if hwc is not None:
        h, w, c = hwc
        return (1, c, h, w)
    return _input_size_from_sample(data_instance)


def _image_hwc_from_schema(
    record_schema: dict[str, Any],
) -> tuple[int, int, int] | None:
    # Prefer an explicit "image" field; otherwise the first 3-element shape.
    candidates: list[Any] = []
    if "image" in record_schema:
        candidates.append(record_schema["image"])
    candidates.extend(v for k, v in record_schema.items() if k != "image")
    for entry in candidates:
        shape = entry.get("shape") if isinstance(entry, dict) else None
        if isinstance(shape, list | tuple) and len(shape) == 3:
            return int(shape[0]), int(shape[1]), int(shape[2])
    return None


def _input_size_from_sample(data_instance: Any) -> tuple[int, int, int, int]:
    from modelfoundry.plugins.pytorch.data import DataRefineryDataset

    split = data_instance.splits[0]
    dataset = DataRefineryDataset(data_instance, split)
    image, _ = dataset[0]
    channels, height, width = (int(d) for d in image.shape)
    return (1, channels, height, width)
