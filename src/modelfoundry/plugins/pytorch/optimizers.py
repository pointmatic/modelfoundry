# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch optimizer vocabulary (FR-OPT-1, Story C.d).

Registers `adamw`, `sgd`, and `adam`. The recipe's `learning_rate` maps to
torch's `lr`. Import-safe without `[pytorch]`: param models + `OPTIMIZER_OPERATIONS`
are pure pydantic; `torch` is imported lazily inside `build_optimizer`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import OperationSpec


class _OptimizerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdamWParams(_OptimizerParams):
    learning_rate: float
    weight_decay: float = 0.01
    betas: tuple[float, float] = (0.9, 0.999)


class SGDParams(_OptimizerParams):
    learning_rate: float
    momentum: float = 0.0
    weight_decay: float = 0.0
    nesterov: bool = False


class AdamParams(_OptimizerParams):
    learning_rate: float
    betas: tuple[float, float] = (0.9, 0.999)


_OPTIMIZER_PARAMS: dict[str, type[BaseModel]] = {
    "adamw": AdamWParams,
    "sgd": SGDParams,
    "adam": AdamParams,
}

#: Optimizer ops the PyTorch plugin contributes to `Plugin.operations`.
OPTIMIZER_OPERATIONS: dict[str, OperationSpec] = {
    name: OperationSpec(op_name=name, param_model=model, applies_to="optimizer")
    for name, model in _OPTIMIZER_PARAMS.items()
}


def _validate(op: str, params: dict[str, Any]) -> Any:
    spec = OPTIMIZER_OPERATIONS.get(op)
    if spec is None:
        raise PluginError(
            f"unknown optimizer op {op!r}; known: {sorted(OPTIMIZER_OPERATIONS)}",
            stage="build_optimizer",
        )
    try:
        return spec.param_model(**params)
    except ValidationError as exc:
        raise PluginError(
            f"invalid params for optimizer op {op!r}: {exc}",
            stage="build_optimizer",
            detail={"op": op},
        ) from exc


def build_optimizer(op: str, params: dict[str, Any], model_parameters: Iterable[Any]) -> Any:
    """Construct the `torch.optim` optimizer for `op` over `model_parameters`."""
    p = _validate(op, params or {})
    import torch

    if op == "adamw":
        return torch.optim.AdamW(
            model_parameters, lr=p.learning_rate, weight_decay=p.weight_decay, betas=p.betas
        )
    if op == "sgd":
        return torch.optim.SGD(
            model_parameters,
            lr=p.learning_rate,
            momentum=p.momentum,
            weight_decay=p.weight_decay,
            nesterov=p.nesterov,
        )
    if op == "adam":
        return torch.optim.Adam(model_parameters, lr=p.learning_rate, betas=p.betas)
    raise PluginError(f"optimizer op {op!r} is not constructible", stage="build_optimizer")
