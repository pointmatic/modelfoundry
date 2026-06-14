# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch visualization `OperationSpec` registry (Story C.q.2 — C.k repair).

The renderers themselves live in `plugins.pytorch.visualizations`, which imports
matplotlib at module top and is therefore loaded **lazily** (at materialize time)
— never at plugin discovery. This module holds only the pure-pydantic param
models + `OperationSpec` registry so `PyTorchPlugin.operations` can advertise the
visualization ops to the FR-2 recipe validator (check 3 `section_ops_registered`,
check 17 `op_params_match_spec`) **without** pulling matplotlib into every
`discover_plugins()` call. Keep this module matplotlib-free.

Each param model mirrors the params its renderer actually reads from
`VisualizationSpec.model_extra`:

* `training_curves` / `optimization_history` — no params.
* `confusion_matrix` / `calibration_curve` — optional `split` (via `_pick_split`).
* `predictions_grid` — optional `max_items` (default 16).

`extra="forbid"` so the validator rejects params an op would silently ignore.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from modelfoundry.plugins.base import OperationSpec


class _VizParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoVizParams(_VizParams):
    """For renderers that draw solely from the artifacts snapshot (no recipe params)."""


class SplitVizParams(_VizParams):
    """Renderers that pick a split via `visualizations._pick_split`."""

    split: str | None = None


class PredictionsGridParams(_VizParams):
    max_items: int = 16


_VISUALIZATION_PARAMS: dict[str, type[BaseModel]] = {
    "training_curves": NoVizParams,
    "optimization_history": NoVizParams,
    "confusion_matrix": SplitVizParams,
    "calibration_curve": SplitVizParams,
    "predictions_grid": PredictionsGridParams,
}

#: Visualization ops the PyTorch plugin contributes to `Plugin.operations`. Must
#: stay in sync with `plugins.pytorch.visualizations._RENDERERS`.
VISUALIZATION_OPERATIONS: dict[str, OperationSpec] = {
    name: OperationSpec(op_name=name, param_model=model, applies_to="visualization")
    for name, model in _VISUALIZATION_PARAMS.items()
}
