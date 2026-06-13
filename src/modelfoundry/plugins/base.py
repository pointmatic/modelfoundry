# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Plugin Protocol + `OperationSpec` (FR-24).

`Plugin` is a `runtime_checkable` Protocol abstracting Trainer / Evaluator /
Optimizer / Visualization / Persistence handles. Each concrete plugin (`pytorch`,
`sklearn`) implements it via the Protocol's structural typing — no `Plugin`
subclass required. `runtime_checkable` lets the discovery layer assert
`isinstance(candidate, Plugin)` before registering.

`OperationSpec` is the plugin-side schema for one operation. Plugins register
one per Architecture / Loss / Optimizer / Schedule / Training / Optimization /
Evaluation / Visualization op they expose; the recipe validator (FR-2 check 17)
validates the recipe's op params against `OperationSpec.param_model`.

Several Protocol return types are aliased to `Any` here as forward stubs
(`DataRefineryInstance` lands in B.i, `CheckReport` in the FR-19 / D.c CLI
check story, `OptimizationResult` / `TrainingResult` / `EvaluationResult` in
C.h-C.j, `InstanceArtifacts` in C.k/C.p). The owning stories tighten these.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

import numpy
import pandas  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from modelfoundry.recipe.models import (
    EvaluationSpec,
    ModelRecipe,
    OptimizationSpec,
    TrainingSpec,
    VisualizationSpec,
)

# Forward-declared types, refined in their owning stories.
type DataRefineryInstance = Any  # Story B.i
type CheckReport = Any  # FR-19 / Story D.c
type OptimizationResult = Any  # Story C.i
type TrainingResult = Any  # Story C.h
type EvaluationResult = Any  # Story C.j


@dataclass(frozen=True)
class InstanceArtifacts:
    """A read-only snapshot of a ModelInstance's data, fed to viz renderers (C.k).

    Every field is optional so a renderer can degrade gracefully (e.g.
    `optimization_history` renders a placeholder when `trials is None`). The
    `pandas`-typed fields are `Any` because pandas ships no type stubs. Story C.p
    constructs these from an on-disk instance and may extend the snapshot
    additively (figures, summary).
    """

    history: Any = None  # training/history.parquet as a DataFrame
    evaluation: dict[str, dict[str, Any]] | None = None  # evaluation/metrics.json
    predictions: Any = None  # evaluation/predictions.parquet as a DataFrame
    trials: Any = None  # optimization/trials.parquet as a DataFrame
    class_names: list[str] | None = None
    recipe: Any = None  # the ModelRecipe (for the report's recipe summary)
    manifest: Any = None  # the Manifest (plugin / optimization / expectations / warnings)
    stage_timings: dict[str, float] | None = None  # per-stage elapsed seconds (C.o)


class OperationSpec(BaseModel):
    """Plugin-side schema for one op. Consumed by FR-2 check 17."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    op_name: str
    param_model: type[BaseModel]
    applies_to: Literal[
        "architecture",
        "loss",
        "optimizer",
        "schedule",
        "training",
        "optimization",
        "evaluation",
        "visualization",
    ]
    requires_extras: tuple[str, ...] = ()


@runtime_checkable
class Plugin(Protocol):
    """The substrate-neutral plugin contract."""

    name: str
    version: str
    operations: dict[str, OperationSpec]

    def health_check(self) -> CheckReport: ...

    def build_model(self, arch: dict[str, Any]) -> Any: ...

    def run_optimization(
        self,
        opt: OptimizationSpec,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
    ) -> OptimizationResult: ...

    def run_training(
        self,
        training: TrainingSpec,
        model: Any,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
    ) -> TrainingResult: ...

    def run_evaluation(
        self,
        evaluation: EvaluationSpec,
        model: Any,
        data: DataRefineryInstance,
        temp_dir: Path,
    ) -> EvaluationResult: ...

    def render_visualization(
        self,
        viz: VisualizationSpec,
        instance_artifacts: InstanceArtifacts,
    ) -> bytes | None: ...

    def save_model(self, model: Any, path: Path) -> None: ...

    def load_model(self, path: Path) -> Any: ...

    def predict(self, model: Any, X: Any) -> numpy.ndarray | pandas.Series: ...

    def predict_proba(self, model: Any, X: Any) -> numpy.ndarray | pandas.DataFrame: ...
