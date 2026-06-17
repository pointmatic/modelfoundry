# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""random/dummy chance-baseline plugin (FR-24, Story H.f.2).

A first-class, durable comparison floor — the chance-level model every real
implementation must beat — implemented as a fully-baked ModelFoundry plugin, not
a tutorial prop. It is backed by scikit-learn's `DummyClassifier` and **reuses
the sklearn baseline's machinery**: both are sklearn estimators with
`predict_proba`, so `RandomPlugin` subclasses `SklearnPlugin` and overrides only
the architecture it builds and the op set it registers. Training (a single
`.fit`), evaluation, persistence, the `predict` / `predict_proba` round-trip, and
determinism (the estimator's `random_state` is seeded from the master seed in
`run_training`) are all inherited and already contract-tested.

`run_optimization` + `render_visualization` raise `NotImplementedError` (a fixed
baseline has neither) — inherited from the sklearn baseline.

**Import-safe without heavy extras.** This module ships in the entry-point table
and is loaded by `discover_plugins()` on every install, so `sklearn` is imported
lazily inside `build_model`, never at module top.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from modelfoundry._version import __version__
from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import OperationSpec, Plugin
from modelfoundry.plugins.sklearn.plugin import SklearnPlugin


class DummyClassifierParams(BaseModel):
    """Params for the `dummy_classifier` baseline architecture op."""

    model_config = ConfigDict(extra="forbid")

    num_classes: int
    strategy: Literal["stratified", "uniform", "prior", "most_frequent"] = "stratified"


class _RecognizedNoOpParams(BaseModel):
    """Empty param model for the recognized (but unused) Loss/Optimizer ops.

    A chance baseline has no real loss or optimizer, but `ModelRecipe` requires a
    `Loss` and an `Optimizer` block. These ops are registered with no params so
    the recipe passes validator checks 3 + 17.
    """

    model_config = ConfigDict(extra="forbid")


#: The dummy_classifier architecture op.
ARCHITECTURE_OPERATIONS: dict[str, OperationSpec] = {
    "dummy_classifier": OperationSpec(
        op_name="dummy_classifier", param_model=DummyClassifierParams, applies_to="architecture"
    )
}

#: Recognized no-op Loss op (a chance baseline computes no loss).
LOSS_OPERATIONS: dict[str, OperationSpec] = {
    "cross_entropy": OperationSpec(
        op_name="cross_entropy", param_model=_RecognizedNoOpParams, applies_to="loss"
    )
}

#: Recognized no-op Optimizer op (a chance baseline is not optimized).
OPTIMIZER_OPERATIONS: dict[str, OperationSpec] = {
    "none": OperationSpec(op_name="none", param_model=_RecognizedNoOpParams, applies_to="optimizer")
}


class RandomPlugin(SklearnPlugin):
    """The `random` chance-baseline plugin (sklearn `DummyClassifier` backing).

    Subclasses the sklearn baseline to reuse its (estimator-agnostic) training,
    evaluation, and persistence path, overriding only `build_model` and the op
    set. `health_check`, `prepare_for_build`, `run_training`, `run_evaluation`,
    `save_model` / `load_model`, `predict` / `predict_proba`, and the
    `NotImplementedError` `run_optimization` / `render_visualization` are inherited.
    """

    name: str = "random"
    version: str = __version__

    def __init__(self) -> None:
        self.operations: dict[str, OperationSpec] = {
            **ARCHITECTURE_OPERATIONS,
            **LOSS_OPERATIONS,
            **OPTIMIZER_OPERATIONS,
        }

    def build_model(self, arch: dict[str, Any]) -> Any:
        params = _validate_architecture(arch)
        from sklearn.dummy import DummyClassifier  # type: ignore[import-untyped]

        # `random_state` is set from the master seed in `run_training` (inherited);
        # the strategy shapes the predicted-class distribution / probabilities.
        return DummyClassifier(strategy=params.strategy)


def _validate_architecture(arch: dict[str, Any]) -> DummyClassifierParams:
    if not isinstance(arch, dict):
        raise PluginError(
            f"Architecture must be a mapping, got {type(arch).__name__}", stage="build_model"
        )
    arch_type = arch.get("type")
    if arch_type != "dummy_classifier":
        raise PluginError(
            f"random plugin only builds 'dummy_classifier'; got type={arch_type!r}",
            stage="build_model",
        )
    try:
        return DummyClassifierParams(**{k: v for k, v in arch.items() if k != "type"})
    except ValidationError as exc:
        raise PluginError(
            f"invalid dummy_classifier params: {exc}", stage="build_model", detail={"arch": arch}
        ) from exc


# The singleton registered via the `modelfoundry.plugins` entry point.
plugin: Plugin = RandomPlugin()
