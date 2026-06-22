# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Pydantic v2 models for a ModelFoundry recipe.

`ModelRecipe` is the top-level, `frozen`, `extra="forbid"` model — every field
default participates in the canonical cache-identity bytes (see
`project-essentials.md` § Cache identity), so this module's defaults are part of
the reproducibility contract.

Plugin-specific sections (`Architecture`, and the op-bearing `Loss` /
`Optimizer` / `Optimizer.schedule` / `Visualizations` blocks) stay permissive
here: they carry an `op` name plus arbitrary params, and the owning plugin
attaches typed `OperationSpec.param_model` validation in Phase C (FR-2 checks 3
and 17). Framework-level sections are typed precisely per `tech-spec.md`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe: Path
    variant: str | None = None
    seed: int | None = None
    cache_root: Path | None = None


class LossSpec(BaseModel):
    # extra="allow": plugin attaches the loss op's typed params in Phase C.
    model_config = ConfigDict(extra="allow")

    op: str


class ScheduleSpec(BaseModel):
    # extra="allow": plugin attaches the schedule op's typed params in Phase C.
    model_config = ConfigDict(extra="allow")

    op: str
    monitor: str | None = None


class OptimizerSpec(BaseModel):
    # extra="allow": plugin attaches the optimizer op's typed params in Phase C.
    model_config = ConfigDict(extra="allow")

    op: str
    schedule: ScheduleSpec | None = None


class EarlyStoppingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monitor: str
    mode: Literal["min", "max"]
    patience: int = Field(gt=0)


class TrainingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_epochs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    num_workers: int = Field(ge=0, default=2)
    precision: Literal["fp32", "amp"] = "fp32"
    checkpoint_cadence: int = Field(gt=0, default=1)
    early_stopping: EarlyStoppingSpec | None = None
    # Applies to Training + Evaluation + inference (eval and predict inherit);
    # resolved by the plugin's health_check-reported availability at materialize
    # time. "auto" picks the best available accelerator. Validator check 20
    # rejects an explicit device the plugin reports unavailable.
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"


class InferenceSpec(BaseModel):
    """Recipe-declared stochastic-inference block (R2.1, Story H.m).

    `mode: point` (the default, and the shape applied when the block is absent)
    is single-pass inference with dropout inactive — the established
    `predict()` / `predict_proba()` point-estimate semantics, byte-unchanged.

    `mode: mc_dropout` requests **T** (`mc_samples`, author-declared, target
    20-50) stochastic forward passes with `Dropout` kept active, seeded
    deterministically per pass via `derive_seed(master_seed, "dropout", t)`. The
    aggregation of those passes into mean probabilities + a predictive-uncertainty
    estimate, and their persistence, land in Story H.n.

    Adding this block to `ModelRecipe` shifts the canonical bytes of every recipe
    that omits it (a default participates in the cache identity) — a
    cache-invalidating change handled pre-production per OR-9 (release-note +
    re-materialize, no `schema_version` bump). See `project-essentials.md` §
    Cache identity.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["point", "mc_dropout"] = "point"
    mc_samples: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_mc_samples(self) -> InferenceSpec:
        if self.mode == "mc_dropout" and self.mc_samples is None:
            raise ValueError(
                "Inference.mode='mc_dropout' requires `mc_samples` (T, the number of "
                "stochastic forward passes; the consumer targets 20-50)"
            )
        if self.mode == "point" and self.mc_samples is not None:
            raise ValueError("Inference.mc_samples is only valid when mode='mc_dropout'")
        return self


class SearchSpaceSpec(BaseModel):
    # extra="allow": a single hyperparameter's distribution spec, e.g.
    # {log_uniform: [1e-5, 1e-3]} or {categorical: [16, 32, 64]}. Semantic
    # validation (exactly one distribution, valid bounds) is FR-2 checks 7-9
    # in the Story B.m validator.
    model_config = ConfigDict(extra="allow")


class OptimizationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sampler: Literal["tpe", "random", "grid"] = "tpe"
    pruner: Literal["median", "none"] = "median"
    n_trials: int = Field(gt=0)
    n_jobs: Literal[1] = 1
    baseline_trial: Literal["enqueue_recipe_defaults"] | None = "enqueue_recipe_defaults"
    objective_metric: str | None = None
    max_epochs_per_trial: int | None = None
    search_space: dict[str, SearchSpaceSpec]


class ComparisonSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_model_id: str


class EvaluationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    splits: list[str]
    primary_metric: str
    metrics: list[str]
    comparison: ComparisonSpec | None = None
    calibration_bins: int = Field(gt=0, default=10)


class VisualizationSpec(BaseModel):
    # extra="allow": plugin attaches the viz op's typed params in Phase C.
    model_config = ConfigDict(extra="allow")

    op: str
    mode: Literal["reporting", "interactive"] = "reporting"


class ExpectationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    split: str
    op: Literal["gte", "lte", "eq", "within"]
    value: float | tuple[float, float]


class ModelRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    plugin: str
    seed: int
    Data: DataSpec
    Architecture: dict[str, Any]
    Loss: LossSpec
    Optimizer: OptimizerSpec
    Training: TrainingSpec
    Optimization: OptimizationSpec | None = None
    Inference: InferenceSpec | None = None
    Evaluation: EvaluationSpec
    Visualizations: list[VisualizationSpec] = []
    OutputExpectations: list[ExpectationSpec] = []
    variants: dict[str, dict[str, Any]] = {}
