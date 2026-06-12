# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch Optuna optimization (FR-11, Story C.i).

`run_optimization` builds a deterministic Optuna `Study` over the recipe's
`Optimization.search_space`, runs short per-trial trainings (capped by
`max_epochs_per_trial`), and returns the best hyperparameters for the
auto-composition merge-back (`recipe.search_space.apply_params`) the orchestrator
applies before the final Training stage.

**Determinism (see `project-essentials.md` § Determinism contract).** The sampler
is seeded from `derive_seed(master_seed, "optuna_sampler")` and `n_jobs` is locked
to `1` — parallel trials would make trial ordering (and thus best-params
selection) non-deterministic. Each trial seeds its own training from
`derive_seed(master_seed, "trial", <trial-number>)`, so a study reruns
byte-for-byte.

This module imports `torch` (via the trainer) at materialize time, not during
plugin discovery; the plugin delegates here through a lazy import.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modelfoundry.core.errors import OptimizationError
from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.pipeline.seeding import derive_seed
from modelfoundry.plugins.pytorch.architecture import build_model
from modelfoundry.plugins.pytorch.determinism import enable_deterministic_algorithms
from modelfoundry.plugins.pytorch.trainer import run_training
from modelfoundry.recipe.models import ModelRecipe, OptimizationSpec
from modelfoundry.recipe.search_space import apply_params, baseline_params, suggest_params

_U32 = (1 << 32) - 1

# Trial-objective metric name -> the trainer's per-epoch history key.
_METRIC_KEY: dict[str, str] = {
    "accuracy": "val_accuracy",
    "loss": "val_loss",
    "val_accuracy": "val_accuracy",
    "val_loss": "val_loss",
}


@dataclass(frozen=True)
class OptimizationResult:
    """Outcome of the Optuna study — feeds the auto-composition merge-back (C.o)."""

    best_params: dict[str, Any]
    best_value: float
    objective_metric: str
    direction: str
    n_trials: int
    study_db: Path
    trials_parquet: Path
    best_params_path: Path


def run_optimization(
    opt: OptimizationSpec,
    recipe: ModelRecipe,
    data: DataRefineryInstance,
    seed: int,
    temp_dir: Path,
) -> OptimizationResult:
    """Run the Optuna study and persist `trials.parquet` + `best-params.json`."""
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    opt_dir = temp_dir / "optimization"
    opt_dir.mkdir(parents=True, exist_ok=True)
    study_db = opt_dir / "study.db"

    metric_key, direction = _resolve_objective(opt, recipe)
    # Optuna / NumPy samplers want a 32-bit seed; mask the 64-bit derived value.
    sampler = _build_sampler(opt, derive_seed(seed, "optuna_sampler") & _U32)
    pruner = optuna.pruners.MedianPruner() if opt.pruner == "median" else optuna.pruners.NopPruner()

    study = optuna.create_study(
        storage=f"sqlite:///{study_db}",
        study_name="modelfoundry",
        sampler=sampler,
        pruner=pruner,
        direction=direction,
    )
    if opt.baseline_trial == "enqueue_recipe_defaults":
        study.enqueue_trial(baseline_params(recipe), skip_if_exists=True)

    objective = _make_objective(opt, recipe, data, seed, metric_key, direction, opt_dir)
    study.optimize(objective, n_trials=opt.n_trials, n_jobs=1)

    trials_parquet = opt_dir / "trials.parquet"
    study.trials_dataframe().to_parquet(trials_parquet, index=False)
    best_params_path = opt_dir / "best-params.json"
    best_params_path.write_text(
        json.dumps(study.best_params, indent=2, sort_keys=True), encoding="utf-8"
    )

    return OptimizationResult(
        best_params=dict(study.best_params),
        best_value=float(study.best_value),
        objective_metric=metric_key,
        direction=direction,
        n_trials=len(study.trials),
        study_db=study_db,
        trials_parquet=trials_parquet,
        best_params_path=best_params_path,
    )


def _resolve_objective(opt: OptimizationSpec, recipe: ModelRecipe) -> tuple[str, str]:
    """The `(history_key, direction)` driving the study.

    Optimization trials score against the trainer's per-epoch val metrics
    (`val_accuracy` / `val_loss`); the richer evaluation vocabulary lands at the
    Evaluation stage (C.j). `loss`-like metrics minimize, the rest maximize.
    """
    name = opt.objective_metric or recipe.Evaluation.primary_metric
    key = _METRIC_KEY.get(name)
    if key is None:
        raise OptimizationError(
            f"objective metric {name!r} is not available during optimization; "
            f"supported: {sorted(_METRIC_KEY)}",
            stage="run_optimization",
            detail={"metric": name},
        )
    return key, ("minimize" if "loss" in key else "maximize")


def _build_sampler(opt: OptimizationSpec, sampler_seed: int) -> Any:
    import optuna

    if opt.sampler == "tpe":
        return optuna.samplers.TPESampler(seed=sampler_seed)
    if opt.sampler == "random":
        return optuna.samplers.RandomSampler(seed=sampler_seed)
    # grid: enumerate the categorical-only space (raises on continuous distributions).
    from modelfoundry.recipe.search_space import categorical_grid

    return optuna.samplers.GridSampler(categorical_grid(opt.search_space), seed=sampler_seed)


def _make_objective(
    opt: OptimizationSpec,
    recipe: ModelRecipe,
    data: DataRefineryInstance,
    seed: int,
    metric_key: str,
    direction: str,
    opt_dir: Path,
) -> Any:
    import optuna

    def objective(trial: Any) -> float:
        params = suggest_params(trial, opt.search_space)
        trial_recipe = apply_params(recipe, params)
        training = trial_recipe.Training
        if opt.max_epochs_per_trial is not None:
            training = training.model_copy(
                update={"max_epochs": min(training.max_epochs, opt.max_epochs_per_trial)}
            )

        trial_seed = derive_seed(seed, "trial", trial.number.to_bytes(4, "big", signed=False))
        enable_deterministic_algorithms(derive_seed(trial_seed, "weight_init"))
        model = build_model(trial_recipe.Architecture)

        def report(epoch: int, record: dict[str, float]) -> None:
            if metric_key in record:
                trial.report(record[metric_key], epoch)
                if trial.should_prune():
                    raise optuna.TrialPruned()

        result = run_training(
            training,
            model,
            trial_recipe,
            data,
            trial_seed,
            opt_dir / "trials" / str(trial.number),
            epoch_callback=report,
        )
        values = [rec[metric_key] for rec in result.history if metric_key in rec]
        if not values:
            raise OptimizationError(
                f"trial produced no {metric_key!r} values to optimize",
                stage="run_optimization",
                detail={"metric": metric_key},
            )
        return max(values) if direction == "maximize" else min(values)

    return objective
