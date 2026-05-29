# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.loader.load_recipe` and the schema-version gate."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from modelfoundry.core.errors import RecipeError
from modelfoundry.recipe.loader import SUPPORTED_SCHEMA_VERSIONS, load_recipe
from modelfoundry.recipe.models import ModelRecipe

MINIMAL_RECIPE = textwrap.dedent(
    """
    schema_version: 1
    plugin: pytorch
    seed: 7
    Data:
      recipe: ../data/recipe.yml
    Architecture:
      op: simple_cnn
      num_classes: 10
    Loss:
      op: cross_entropy
    Optimizer:
      op: adamw
      learning_rate: 0.001
    Training:
      max_epochs: 3
      batch_size: 32
    Evaluation:
      splits: [val, test]
      primary_metric: macro_f1
      metrics: [macro_f1, accuracy]
    """
).strip()


def _write(tmp_path: Path, text: str, name: str = "recipe.yml") -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_minimal_recipe_round_trips(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path, MINIMAL_RECIPE))
    assert isinstance(recipe, ModelRecipe)
    assert recipe.schema_version == 1
    assert recipe.plugin == "pytorch"
    assert recipe.seed == 7
    assert recipe.Data.recipe == Path("../data/recipe.yml")
    assert recipe.Loss.op == "cross_entropy"
    assert recipe.Optimizer.op == "adamw"
    assert recipe.Training.max_epochs == 3
    assert recipe.Evaluation.primary_metric == "macro_f1"
    # Defaults applied.
    assert recipe.Optimization is None
    assert recipe.Visualizations == []
    assert recipe.Training.precision == "fp32"


def test_recipe_is_frozen(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path, MINIMAL_RECIPE))
    with pytest.raises(PydanticValidationError):  # frozen model rejects mutation
        recipe.seed = 999  # type: ignore[misc]


def test_op_params_preserved_via_extra_allow(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path, MINIMAL_RECIPE))
    # learning_rate is a plugin param carried through extra="allow".
    assert recipe.Optimizer.model_extra == {"learning_rate": 0.001}


def test_seed_override_applied(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path, MINIMAL_RECIPE), seed=12345)
    assert recipe.seed == 12345


def test_missing_schema_version_raises(tmp_path: Path) -> None:
    text = MINIMAL_RECIPE.replace("schema_version: 1\n", "")
    with pytest.raises(RecipeError, match="missing required key 'schema_version'"):
        load_recipe(_write(tmp_path, text))


def test_unrecognized_schema_version_lists_supported(tmp_path: Path) -> None:
    text = MINIMAL_RECIPE.replace("schema_version: 1", "schema_version: 99")
    with pytest.raises(RecipeError) as excinfo:
        load_recipe(_write(tmp_path, text))
    assert str(sorted(SUPPORTED_SCHEMA_VERSIONS)) in str(excinfo.value)
    assert excinfo.value.detail == {"got": 99, "supported": [1]}


def test_malformed_yaml_includes_location(tmp_path: Path) -> None:
    bad = "schema_version: 1\nplugin: [unterminated\n"
    with pytest.raises(RecipeError) as excinfo:
        load_recipe(_write(tmp_path, bad))
    msg = str(excinfo.value)
    assert "malformed YAML" in msg
    assert "line" in msg


def test_unknown_top_level_key_raises(tmp_path: Path) -> None:
    text = MINIMAL_RECIPE + "\nBogus: true\n"
    with pytest.raises(RecipeError, match="validation failed"):
        load_recipe(_write(tmp_path, text))


def test_non_mapping_top_level_raises(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match="must be a YAML mapping"):
        load_recipe(_write(tmp_path, "- just\n- a\n- list\n"))


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match="recipe not found"):
        load_recipe(tmp_path / "nope.yml")
