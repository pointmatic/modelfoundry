# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch loss vocabulary (FR-LOSS-1, Story C.d).

Registers `cross_entropy`, `cross_entropy_class_weighted`, and `bce_with_logits`.
Class weights for the weighted variant are derived from the train-split label
distribution (`derive_class_weights`) — the trainer (C.h) fits them once at
training start and persists them to `training/class_weights.json`.

Import-safe without `[pytorch]`: param models + `LOSS_OPERATIONS` are pure
pydantic; `torch` is imported lazily inside `build_loss`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import OperationSpec


class _LossParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CrossEntropyParams(_LossParams):
    pass


class CrossEntropyClassWeightedParams(_LossParams):
    weight_source: Literal["train", "train_inverse_frequency", "effective_number"] = "train"
    beta: float = 0.999  # the `effective_number` (Cui et al. 2019) hyperparameter


class BCEWithLogitsParams(_LossParams):
    pass


_LOSS_PARAMS: dict[str, type[BaseModel]] = {
    "cross_entropy": CrossEntropyParams,
    "cross_entropy_class_weighted": CrossEntropyClassWeightedParams,
    "bce_with_logits": BCEWithLogitsParams,
}

#: Loss ops the PyTorch plugin contributes to `Plugin.operations`.
LOSS_OPERATIONS: dict[str, OperationSpec] = {
    name: OperationSpec(op_name=name, param_model=model, applies_to="loss")
    for name, model in _LOSS_PARAMS.items()
}


def derive_class_weights(
    weight_source: str, class_counts: Sequence[int], *, beta: float = 0.999
) -> list[float]:
    """Per-class loss weights from a train-split label distribution (mean-normalized to 1.0).

    * ``train`` — sklearn-style *balanced* weights, ``N / (K * n_c)``.
    * ``train_inverse_frequency`` — ``1 / n_c``.
    * ``effective_number`` — class-balanced ``(1 - beta) / (1 - beta**n_c)``.

    Each is normalized so the weights average to 1.0 (a balanced distribution
    yields all-ones). Fit-on-train discipline is enforced upstream by FR-2 check 5.
    """
    counts = [int(c) for c in class_counts]
    if not counts or sum(counts) == 0:
        raise PluginError(
            "cannot derive class weights from an empty label distribution", stage="build_loss"
        )
    if any(c < 0 for c in counts):
        raise PluginError("class counts must be non-negative", stage="build_loss")
    k = len(counts)
    n = sum(counts)

    if weight_source == "train":
        raw = [n / (k * c) if c > 0 else 0.0 for c in counts]
    elif weight_source == "train_inverse_frequency":
        raw = [1.0 / c if c > 0 else 0.0 for c in counts]
    elif weight_source == "effective_number":
        raw = [(1.0 - beta) / (1.0 - beta**c) if c > 0 else 0.0 for c in counts]
    else:
        raise PluginError(
            f"unknown weight_source {weight_source!r}; expected one of "
            f"{{train, train_inverse_frequency, effective_number}}",
            stage="build_loss",
        )

    total = sum(raw)
    if total == 0:
        raise PluginError("derived class weights are degenerate (all zero)", stage="build_loss")
    return [r * k / total for r in raw]


def _validate(op: str, params: dict[str, Any]) -> Any:
    spec = LOSS_OPERATIONS.get(op)
    if spec is None:
        raise PluginError(
            f"unknown loss op {op!r}; known: {sorted(LOSS_OPERATIONS)}", stage="build_loss"
        )
    try:
        return spec.param_model(**params)
    except ValidationError as exc:
        raise PluginError(
            f"invalid params for loss op {op!r}: {exc}", stage="build_loss", detail={"op": op}
        ) from exc


def build_loss(
    op: str,
    params: dict[str, Any] | None = None,
    *,
    class_weights: Sequence[float] | None = None,
    num_classes: int | None = None,
) -> Any:
    """Construct the `torch.nn` loss for `op`.

    `class_weights` (from `derive_class_weights`) is consumed by
    `cross_entropy_class_weighted`. `bce_with_logits` is refused when
    `num_classes > 2` (FR-LOSS-1 binary-only constraint).
    """
    _validate(op, params or {})
    import torch
    from torch import nn

    if op == "cross_entropy":
        return nn.CrossEntropyLoss()
    if op == "cross_entropy_class_weighted":
        weight = (
            torch.tensor(list(class_weights), dtype=torch.float32)
            if class_weights is not None
            else None
        )
        return nn.CrossEntropyLoss(weight=weight)
    if op == "bce_with_logits":
        if num_classes is not None and num_classes > 2:
            raise PluginError(
                f"bce_with_logits is binary-only but Architecture.num_classes={num_classes}; "
                f"use cross_entropy for multi-class recipes",
                stage="build_loss",
                detail={"num_classes": num_classes},
            )
        return nn.BCEWithLogitsLoss()
    raise PluginError(f"loss op {op!r} is not constructible", stage="build_loss")
