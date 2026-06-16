# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Recipe loading + schema-version gate.

`load_recipe` reads a YAML recipe, gates on `schema_version`, applies execution-
context overrides (`variant`, `seed`), and constructs a `ModelRecipe`. Every
failure path raises `RecipeError` with file context so the CLI/library surface a
single error type per the consumer-dependency-spec.

The variant overlay is a placeholder here; Story B.b wires the real deep-merge
via `recipe.variants.apply_variant`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError as PydanticValidationError

from modelfoundry.core.errors import RecipeError
from modelfoundry.recipe.models import ModelRecipe
from modelfoundry.recipe.variants import apply_variant

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


def load_recipe(
    path: str | Path,
    *,
    variant: str | None = None,
    seed: int | None = None,
) -> ModelRecipe:
    """Load and validate the recipe at `path`.

    `seed` (when given) overrides the recipe's master seed (CLI `--seed`).
    `variant` selects a named overlay, deep-merged onto the base recipe before
    validation; an unknown variant name raises `RecipeError`.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RecipeError(f"recipe not found: {path}", recipe_path=path) from exc
    except OSError as exc:
        raise RecipeError(f"cannot read recipe {path}: {exc}", recipe_path=path) from exc

    data = _parse_yaml(text, path)
    if not isinstance(data, dict):
        raise RecipeError(
            f"recipe {path} must be a YAML mapping at the top level, got {type(data).__name__}",
            recipe_path=path,
        )

    _gate_schema_version(data, path)

    try:
        data = apply_variant(data, variant)
    except RecipeError as exc:
        exc.recipe_path = path
        raise
    if seed is not None:
        data = {**data, "seed": seed}

    try:
        return ModelRecipe.model_validate(data)
    except PydanticValidationError as exc:
        raise RecipeError(
            f"recipe validation failed for {path}: {exc}",
            recipe_path=path,
            detail={"errors": exc.errors()},
        ) from exc


def _parse_yaml(text: str, path: Path) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" (line {mark.line + 1}, column {mark.column + 1})" if mark else ""
        raise RecipeError(f"malformed YAML in {path}{location}: {exc}", recipe_path=path) from exc


def _gate_schema_version(data: dict[str, Any], path: Path) -> None:
    if "schema_version" not in data:
        raise RecipeError(
            f"recipe {path} is missing required key 'schema_version'",
            recipe_path=path,
        )
    version = data["schema_version"]
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        supported = sorted(SUPPORTED_SCHEMA_VERSIONS)
        raise RecipeError(
            f"recipe {path} declares schema_version {version!r}; "
            f"supported versions are {supported}",
            recipe_path=path,
            detail={"got": version, "supported": supported},
        )
