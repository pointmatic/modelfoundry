# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Search-space plumbing for Optuna optimization (FR-3 step 4.2-4.3, Story C.i).

`Optimization.search_space` maps **dotted recipe paths** (e.g.
`"Optimizer.learning_rate"`, `"Training.batch_size"`,
`"Training.early_stopping.patience"`) to a single-distribution `SearchSpaceSpec`
whose distribution lives in `model_extra` — one of `log_uniform` / `uniform` /
`int` (an inclusive `[lo, hi]` range) or `categorical` (a choice list). The
validator's check 7 guarantees every key is a real recipe path before we get
here.

This module is the bridge between those declarations and Optuna:

* `suggest_params(trial, search_space)` — draw one value per path from a trial.
* `baseline_params(recipe)` — the recipe's current values at those paths, for
  `study.enqueue_trial` (`baseline_trial: enqueue_recipe_defaults`).
* `apply_params(recipe, params)` — deep-set the chosen values back onto the
  recipe and rebuild the frozen `ModelRecipe` (auto-composition before the final
  Training stage).
"""

from __future__ import annotations

from typing import Any

from modelfoundry.core.errors import RecipeError
from modelfoundry.recipe.models import ModelRecipe, SearchSpaceSpec

_MISSING = object()
_DISTRIBUTIONS = ("log_uniform", "uniform", "int", "categorical")


def _distribution(path: str, spec: SearchSpaceSpec) -> tuple[str, Any]:
    """The `(kind, args)` of the single distribution declared on `spec`."""
    extra = spec.model_extra or {}
    declared = [k for k in _DISTRIBUTIONS if k in extra]
    if len(declared) != 1:
        raise RecipeError(
            f"search_space[{path!r}] must declare exactly one of {list(_DISTRIBUTIONS)}; "
            f"got {sorted(extra)}",
            detail={"path": path, "keys": sorted(extra)},
        )
    return declared[0], extra[declared[0]]


def suggest_params(trial: Any, search_space: dict[str, SearchSpaceSpec]) -> dict[str, Any]:
    """Draw one value per search-space path from an Optuna `trial`.

    Keys are the dotted recipe paths (also the Optuna parameter names), so the
    trial record self-documents which recipe knob each value targets.
    """
    params: dict[str, Any] = {}
    for path, spec in search_space.items():
        kind, args = _distribution(path, spec)
        if kind == "log_uniform":
            lo, hi = args
            params[path] = trial.suggest_float(path, float(lo), float(hi), log=True)
        elif kind == "uniform":
            lo, hi = args
            params[path] = trial.suggest_float(path, float(lo), float(hi))
        elif kind == "int":
            lo, hi = args
            params[path] = trial.suggest_int(path, int(lo), int(hi))
        else:  # categorical
            params[path] = trial.suggest_categorical(path, list(args))
    return params


def categorical_grid(search_space: dict[str, SearchSpaceSpec]) -> dict[str, list[Any]]:
    """The enumerable grid for `GridSampler` — every path must be `categorical`.

    Raises `RecipeError` when any path declares a continuous/int distribution,
    which the grid sampler cannot enumerate.
    """
    grid: dict[str, list[Any]] = {}
    for path, spec in search_space.items():
        kind, args = _distribution(path, spec)
        if kind != "categorical":
            raise RecipeError(
                f"grid sampler requires categorical distributions; search_space[{path!r}] "
                f"is {kind!r}",
                detail={"path": path, "kind": kind},
            )
        grid[path] = list(args)
    return grid


def baseline_params(recipe: ModelRecipe) -> dict[str, Any]:
    """The recipe's current values at each search-space path (for `enqueue_trial`)."""
    if recipe.Optimization is None:
        return {}
    dump = recipe.model_dump()
    params: dict[str, Any] = {}
    for path in recipe.Optimization.search_space:
        value = _get_path(dump, path)
        if value is _MISSING:
            raise RecipeError(
                f"search_space path {path!r} is absent from the recipe", detail={"path": path}
            )
        params[path] = value
    return params


def apply_params(recipe: ModelRecipe, params: dict[str, Any]) -> ModelRecipe:
    """Return a new `ModelRecipe` with `params` deep-set at their dotted paths."""
    dump = recipe.model_dump()
    for path, value in params.items():
        _set_path(dump, path, value)
    return ModelRecipe(**dump)


def _get_path(node: Any, dotted: str) -> Any:
    cursor: Any = node
    for part in dotted.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            return _MISSING
    return cursor


def _set_path(node: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cursor: Any = node
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor or not isinstance(cursor[part], dict):
            raise RecipeError(
                f"cannot set {dotted!r}: intermediate {part!r} is missing or not a mapping",
                detail={"path": dotted},
            )
        cursor = cursor[part]
    if not isinstance(cursor, dict) or parts[-1] not in cursor:
        raise RecipeError(
            f"cannot set {dotted!r}: leaf {parts[-1]!r} is absent from the recipe",
            detail={"path": dotted},
        )
    cursor[parts[-1]] = value
