# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch LR-schedule vocabulary (FR-OPT-2, Story C.d).

Registers `reduce_on_plateau`, `cosine`, and `linear_warmup`. For
`reduce_on_plateau`, the watched metric comes from `ScheduleSpec.monitor` (the
trainer feeds its value to `scheduler.step(value)`); the op params carry only the
LR-adjustment knobs. Import-safe without `[pytorch]`: param models +
`SCHEDULE_OPERATIONS` are pure pydantic; `torch` is imported lazily inside
`build_schedule`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import OperationSpec


class _ScheduleParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReduceOnPlateauParams(_ScheduleParams):
    mode: Literal["min", "max"] = "min"
    factor: float = 0.5
    patience: int = 2
    min_lr: float = 1e-6


class CosineParams(_ScheduleParams):
    T_max: int
    eta_min: float = 0.0


class LinearWarmupParams(_ScheduleParams):
    warmup_steps: int
    total_steps: int
    min_lr: float = 0.0


_SCHEDULE_PARAMS: dict[str, type[BaseModel]] = {
    "reduce_on_plateau": ReduceOnPlateauParams,
    "cosine": CosineParams,
    "linear_warmup": LinearWarmupParams,
}

#: Schedule ops the PyTorch plugin contributes to `Plugin.operations`.
SCHEDULE_OPERATIONS: dict[str, OperationSpec] = {
    name: OperationSpec(op_name=name, param_model=model, applies_to="schedule")
    for name, model in _SCHEDULE_PARAMS.items()
}


def _validate(op: str, params: dict[str, Any]) -> Any:
    spec = SCHEDULE_OPERATIONS.get(op)
    if spec is None:
        raise PluginError(
            f"unknown schedule op {op!r}; known: {sorted(SCHEDULE_OPERATIONS)}",
            stage="build_schedule",
        )
    try:
        return spec.param_model(**params)
    except ValidationError as exc:
        raise PluginError(
            f"invalid params for schedule op {op!r}: {exc}",
            stage="build_schedule",
            detail={"op": op},
        ) from exc


def build_schedule(op: str, params: dict[str, Any], optimizer: Any) -> Any:
    """Construct the `torch.optim.lr_scheduler` for `op`, bound to `optimizer`."""
    p = _validate(op, params or {})
    from torch.optim import lr_scheduler

    if op == "reduce_on_plateau":
        return lr_scheduler.ReduceLROnPlateau(
            optimizer, mode=p.mode, factor=p.factor, patience=p.patience, min_lr=p.min_lr
        )
    if op == "cosine":
        return lr_scheduler.CosineAnnealingLR(optimizer, T_max=p.T_max, eta_min=p.eta_min)
    if op == "linear_warmup":
        base_lr = float(optimizer.param_groups[0]["lr"])
        min_mult = (float(p.min_lr) / base_lr) if base_lr > 0 else 0.0
        warmup, total = int(p.warmup_steps), int(p.total_steps)

        def lr_lambda(step: int) -> float:
            if warmup > 0 and step < warmup:
                return step / warmup
            if step >= total:
                return min_mult
            decay_span = max(1, total - warmup)
            return 1.0 + (min_mult - 1.0) * ((step - warmup) / decay_span)

        return lr_scheduler.LambdaLR(optimizer, lr_lambda=lr_lambda)
    raise PluginError(f"schedule op {op!r} is not constructible", stage="build_schedule")
