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
* `confusion_matrix` / `calibration_curve` — optional `split` (single, legacy) or
  `splits: list[str]` (FR-13; defaults to `Evaluation.splits`), via `_pick_splits`.
* `predictions_grid` — optional `n` (FR-13; legacy alias `max_items`, default 16),
  `splits: list[str]`, and `per_class: bool` (FR-13).

`extra="forbid"` so the validator rejects params an op would silently ignore.

**Byte-neutrality (Story I.w).** The new params are authored-only-when-used and the
`max_items` legacy alias is preserved, so a recipe authoring the old `max_items`/
`split` form validates and dumps verbatim — its canonical bytes are unchanged. The
renderers also keep the legacy single-split code paths byte-identical, so existing
instances' materialized PNG bytes are unchanged too.
"""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from modelfoundry.plugins.base import OperationSpec


class _VizParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoVizParams(_VizParams):
    """For renderers that draw solely from the artifacts snapshot (no recipe params)."""


class SplitVizParams(_VizParams):
    """Renderers that select split(s) via `visualizations._pick_splits`.

    `split` (single, legacy) and `splits` (FR-13 list) are both optional; when
    neither is authored the renderer defaults to `Evaluation.splits`.
    """

    split: str | None = None
    splits: list[str] | None = None


class PredictionsGridParams(_VizParams):
    # `n` is the canonical FR-13 name; `max_items` is the preserved legacy alias
    # (byte-neutral — the recipe stores whichever key the author wrote, via
    # VisualizationSpec.model_extra; this validation-only model accepts either).
    n: int = Field(default=16, validation_alias=AliasChoices("n", "max_items"))
    splits: list[str] | None = None
    per_class: bool = False


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
