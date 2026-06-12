# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch plugin scaffold + `health_check` (Story C.b).

The plugin shell: it registers `name = "pytorch"`, an `operations` map (the
architecture vocabulary from C.c, extended by later stories), `build_model`
(delegated to `architecture.build_model`), and a working `health_check`. The
remaining execution methods are stubs raising `NotImplementedError` pointing at
their owning Story (C.h-C.p).

**Import-safe without the `[pytorch]` extra.** This module ships in ModelFoundry's
own entry-point table, so it is loaded by `discover_plugins()` on *every* install
— including sklearn-only ones. It therefore performs **no top-level `torch`
import**; torch is imported lazily inside `health_check`, and `health_check`
reports `available=False` (rather than raising) when the extra is absent.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

import numpy
import pandas  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict

from modelfoundry._version import __version__
from modelfoundry.plugins.base import (
    DataRefineryInstance,
    EvaluationResult,
    InstanceArtifacts,
    OperationSpec,
    OptimizationResult,
    Plugin,
    TrainingResult,
)
from modelfoundry.plugins.pytorch.architecture import (
    ARCHITECTURE_OPERATIONS,
)
from modelfoundry.plugins.pytorch.architecture import (
    build_model as _build_model,
)
from modelfoundry.plugins.pytorch.determinism import (
    deterministic_mode_supported,
    documented_hard_error_ops,
)
from modelfoundry.plugins.pytorch.losses import LOSS_OPERATIONS
from modelfoundry.plugins.pytorch.optimizers import OPTIMIZER_OPERATIONS
from modelfoundry.plugins.pytorch.schedules import SCHEDULE_OPERATIONS
from modelfoundry.recipe.models import (
    EvaluationSpec,
    ModelRecipe,
    OptimizationSpec,
    TrainingSpec,
    VisualizationSpec,
)


class PyTorchHealthReport(BaseModel):
    """Result of `PyTorchPlugin.health_check` — the backend's self-report.

    `accelerators` uses the `Training.device` vocabulary (`cpu` / `cuda` / `mps`),
    so the recipe validator's check 20 (B.n) can read it directly to confirm a
    requested device is actually available.
    """

    model_config = ConfigDict(extra="forbid")

    plugin: str
    available: bool
    torch_version: str | None
    torchvision_version: str | None
    torchmetrics_version: str | None
    accelerators: tuple[str, ...]
    deterministic_algorithms_available: bool
    documented_hard_error_ops: tuple[str, ...]


def _safe_dist_version(distribution: str) -> str | None:
    """Installed version of `distribution`, or `None` when it is not installed."""
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _detect_accelerators() -> tuple[str, ...]:
    """Accelerators torch reports on this machine, in `Training.device` terms.

    Always includes `cpu` when torch is importable; appends `cuda` / `mps` when
    the respective backend is available. Returns `()` when torch is absent.
    """
    try:
        import torch  # type: ignore[import-not-found, unused-ignore]
    except ImportError:
        return ()
    accelerators = ["cpu"]
    if torch.cuda.is_available():
        accelerators.append("cuda")
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        accelerators.append("mps")
    return tuple(accelerators)


def _not_implemented(method: str, story: str) -> NotImplementedError:
    return NotImplementedError(
        f"PyTorchPlugin.{method} is not implemented yet (lands in Story {story})"
    )


class PyTorchPlugin:
    """The `pytorch` plugin. Vocabulary + execution land in Stories C.c-C.p."""

    name: str = "pytorch"
    version: str = __version__

    def __init__(self) -> None:
        # C.c architecture + C.d losses/optimizers/schedules; the
        # visualization/evaluation stories extend this map further. (Lazy
        # augmentations, C.g, are realized from the bound DataRefinery policy —
        # not a ModelFoundry recipe op — so they are not registered here.)
        self.operations: dict[str, OperationSpec] = {
            **ARCHITECTURE_OPERATIONS,
            **LOSS_OPERATIONS,
            **OPTIMIZER_OPERATIONS,
            **SCHEDULE_OPERATIONS,
        }

    def health_check(self) -> PyTorchHealthReport:
        torch_version = _safe_dist_version("torch")
        available = torch_version is not None
        return PyTorchHealthReport(
            plugin=self.name,
            available=available,
            torch_version=torch_version,
            torchvision_version=_safe_dist_version("torchvision"),
            torchmetrics_version=_safe_dist_version("torchmetrics"),
            accelerators=_detect_accelerators() if available else (),
            # Sourced from the C.e determinism module (the production toggle).
            deterministic_algorithms_available=deterministic_mode_supported(),
            documented_hard_error_ops=documented_hard_error_ops,
        )

    def build_model(self, arch: dict[str, Any]) -> Any:
        return _build_model(arch)

    def run_optimization(
        self,
        opt: OptimizationSpec,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
    ) -> OptimizationResult:
        raise _not_implemented("run_optimization", "C.i")

    def run_training(
        self,
        training: TrainingSpec,
        model: Any,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
    ) -> TrainingResult:
        # Lazy import keeps this module (loaded on every discovery) torch-free.
        from modelfoundry.plugins.pytorch.trainer import run_training as _run_training

        return _run_training(training, model, recipe, data, seed, temp_dir)

    def run_evaluation(
        self,
        evaluation: EvaluationSpec,
        model: Any,
        data: DataRefineryInstance,
        temp_dir: Path,
    ) -> EvaluationResult:
        raise _not_implemented("run_evaluation", "C.j")

    def render_visualization(
        self,
        viz: VisualizationSpec,
        instance_artifacts: InstanceArtifacts,
    ) -> bytes | None:
        raise _not_implemented("render_visualization", "C.k")

    def save_model(self, model: Any, path: Path) -> None:
        raise _not_implemented("save_model", "C.l")

    def load_model(self, path: Path) -> Any:
        raise _not_implemented("load_model", "C.l")

    def predict(self, model: Any, X: Any) -> numpy.ndarray | pandas.Series:
        raise _not_implemented("predict", "C.l")

    def predict_proba(self, model: Any, X: Any) -> numpy.ndarray | pandas.DataFrame:
        raise _not_implemented("predict_proba", "C.l")


# The singleton registered via the `modelfoundry.plugins` entry point. The
# annotation gives a static structural-conformance check against the Protocol.
plugin: Plugin = PyTorchPlugin()
