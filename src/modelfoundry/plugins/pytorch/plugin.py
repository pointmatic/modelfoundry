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
from modelfoundry.pipeline.progress import ProgressReporter
from modelfoundry.pipeline.seeding import derive_seed
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
    enable_deterministic_algorithms,
)
from modelfoundry.plugins.pytorch.losses import LOSS_OPERATIONS
from modelfoundry.plugins.pytorch.optimizers import OPTIMIZER_OPERATIONS
from modelfoundry.plugins.pytorch.schedules import SCHEDULE_OPERATIONS
from modelfoundry.plugins.pytorch.visualization_specs import VISUALIZATION_OPERATIONS
from modelfoundry.recipe.models import (
    EvaluationSpec,
    InferenceSpec,
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


class PyTorchPlugin:
    """The `pytorch` plugin. Vocabulary + execution land in Stories C.c-C.p."""

    name: str = "pytorch"
    version: str = __version__
    extension_keys: tuple[str, ...] = ()  # F3 (Story I.d): consumes no extension keys yet

    def __init__(self) -> None:
        # C.c architecture + C.d losses/optimizers/schedules + C.q.2 visualization
        # specs (the matplotlib-free OperationSpec registry — the renderers stay a
        # lazy import in `visualizations.py`). (Lazy augmentations, C.g, are realized
        # from the bound DataRefinery policy — not a ModelFoundry recipe op — so they
        # are not registered here.)
        self.operations: dict[str, OperationSpec] = {
            **ARCHITECTURE_OPERATIONS,
            **LOSS_OPERATIONS,
            **OPTIMIZER_OPERATIONS,
            **SCHEDULE_OPERATIONS,
            **VISUALIZATION_OPERATIONS,
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

    def prepare_for_build(self, seed: int) -> None:
        """Enable deterministic mode and seed weight-init RNG before `build_model`.

        The runner calls this immediately before constructing the model that will
        be trained, so weight initialization is reproducible across runs (FR-25).
        Mirrors the per-trial `enable_deterministic_algorithms(...)` in
        `optimization.py`; without it, `build_model` draws from the process's
        entropy-seeded RNG and the same recipe yields different weights each run.
        """
        enable_deterministic_algorithms(derive_seed(seed, "weight_init"))

    def build_model(self, arch: dict[str, Any]) -> Any:
        return _build_model(arch)

    def run_optimization(
        self,
        opt: OptimizationSpec,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
        *,
        progress: ProgressReporter | None = None,
    ) -> OptimizationResult:
        # Lazy import keeps this module (loaded on every discovery) torch-free.
        from modelfoundry.plugins.pytorch.optimization import (
            run_optimization as _run_optimization,
        )

        return _run_optimization(opt, recipe, data, seed, temp_dir, progress=progress)

    def run_training(
        self,
        training: TrainingSpec,
        model: Any,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
        *,
        progress: ProgressReporter | None = None,
    ) -> TrainingResult:
        # Lazy import keeps this module (loaded on every discovery) torch-free.
        from modelfoundry.plugins.pytorch.trainer import run_training as _run_training

        return _run_training(training, model, recipe, data, seed, temp_dir, progress=progress)

    def run_evaluation(
        self,
        evaluation: EvaluationSpec,
        model: Any,
        data: DataRefineryInstance,
        temp_dir: Path,
        *,
        inference: InferenceSpec | None = None,
        seed: int = 0,
    ) -> EvaluationResult:
        # Lazy import keeps this module (loaded on every discovery) torch-free.
        from modelfoundry.plugins.pytorch.evaluation import (
            run_evaluation as _run_evaluation,
        )

        return _run_evaluation(evaluation, model, data, temp_dir, inference=inference, seed=seed)

    def render_visualization(
        self,
        viz: VisualizationSpec,
        instance_artifacts: InstanceArtifacts,
    ) -> bytes | None:
        # Lazy import keeps this module (loaded on every discovery) matplotlib-free.
        from modelfoundry.plugins.pytorch.visualizations import (
            render_visualization as _render,
        )

        return _render(viz, instance_artifacts)

    def save_model(self, model: Any, path: Path) -> None:
        from modelfoundry.plugins.pytorch import persistence

        persistence.save_model(model, path)

    def write_model_summary(self, model: Any, data: DataRefineryInstance, model_dir: Path) -> Any:
        """Write `model/summary.txt` + `model/summary.json` (FR-27, Story C.q).

        The orchestrator calls this (duck-typed) after persistence; the input
        shape is derived from the bound instance's record schema. Lazy import
        keeps this module torch-free at discovery.
        """
        from modelfoundry.plugins.pytorch import summary

        return summary.write_summary(model, summary.derive_input_size(data), model_dir)

    def summarize_model(self, model: Any, data: DataRefineryInstance) -> dict[str, Any]:
        """Return the FR-27 `ModelSummary` (as a dict) for a built model, in-memory.

        The in-memory sibling of `write_model_summary` — no files written. Adds a
        top-level `output_shape` (the network's output, i.e. the root module's
        output size) for callers that just want the final logits shape. Powers
        `ModelFoundry.summary()` (Story H.a.2) for pre-materialize architecture
        inspection. Lazy import keeps this module torch-free at discovery.
        """
        from modelfoundry.plugins.pytorch import summary

        model_summary, _ = summary.summarize(model, summary.derive_input_size(data))
        result: dict[str, Any] = model_summary.model_dump()
        output_shape = next(
            (
                layer["output_shape"]
                for layer in result["layers"]
                if layer["depth"] == 0 and layer["output_shape"]
            ),
            None,
        )
        if output_shape is not None:
            result["output_shape"] = output_shape
        return result

    def load_model(self, path: Path) -> Any:
        from modelfoundry.plugins.pytorch import persistence

        return persistence.load_model(path)

    def predict(self, model: Any, X: Any) -> numpy.ndarray | pandas.Series:
        from modelfoundry.plugins.pytorch import persistence

        return persistence.predict(model, X)

    def predict_proba(self, model: Any, X: Any) -> numpy.ndarray | pandas.DataFrame:
        from modelfoundry.plugins.pytorch import persistence

        return persistence.predict_proba(model, X)


# The singleton registered via the `modelfoundry.plugins` entry point. The
# annotation gives a static structural-conformance check against the Protocol.
plugin: Plugin = PyTorchPlugin()
