# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.variants.apply_variant` and loader integration."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modelfoundry.core.errors import RecipeError
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.variants import apply_variant

BASE = {
    "schema_version": 1,
    "plugin": "pytorch",
    "seed": 7,
    "Training": {"max_epochs": 3, "batch_size": 32},
    "variants": {
        "big": {"Training": {"batch_size": 128}, "seed": 99},
        "wipe_viz": {"Visualizations": []},
    },
}


def test_none_variant_clears_variants_only() -> None:
    out = apply_variant(BASE, None)
    assert out["variants"] == {}
    assert out["seed"] == 7
    assert out["Training"] == {"max_epochs": 3, "batch_size": 32}
    # Input is not mutated.
    assert BASE["variants"] != {}


def test_overlay_deep_merges_nested_section() -> None:
    out = apply_variant(BASE, "big")
    # batch_size overridden, max_epochs preserved (deep merge, not wholesale).
    assert out["Training"] == {"max_epochs": 3, "batch_size": 128}
    assert out["seed"] == 99
    assert out["variants"] == {}


def test_overlay_replaces_list_wholesale() -> None:
    base = {**BASE, "Visualizations": [{"op": "training_curves"}]}
    out = apply_variant(base, "wipe_viz")
    assert out["Visualizations"] == []


def test_unknown_variant_lists_available() -> None:
    with pytest.raises(RecipeError) as excinfo:
        apply_variant(BASE, "missing")
    assert "unknown variant 'missing'" in str(excinfo.value)
    assert excinfo.value.detail == {
        "variant": "missing",
        "available": ["big", "wipe_viz"],
    }


def test_non_mapping_variants_block_rejected() -> None:
    with pytest.raises(RecipeError, match="'variants' must be a mapping"):
        apply_variant({"variants": ["not", "a", "map"]}, "x")


def test_non_mapping_overlay_rejected() -> None:
    with pytest.raises(RecipeError, match="overlay must be a mapping"):
        apply_variant({"variants": {"x": [1, 2]}}, "x")


# --- loader integration ---

RECIPE = textwrap.dedent(
    """
    schema_version: 1
    plugin: pytorch
    seed: 7
    Data:
      recipe: ../data/recipe.yml
    Architecture: {op: simple_cnn}
    Loss: {op: cross_entropy}
    Optimizer: {op: adamw, learning_rate: 0.001}
    Training:
      max_epochs: 3
      batch_size: 32
      device: cpu
      precision: fp32
      checkpoint_cadence: 1
    Evaluation:
      splits: [val]
      primary_metric: accuracy
      metrics: [accuracy]
      calibration_bins: 10
    variants:
      big_batch:
        Training: {batch_size: 256}
    """
).strip()


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "recipe.yml"
    p.write_text(RECIPE, encoding="utf-8")
    return p


def test_loader_applies_selected_variant(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path), variant="big_batch")
    assert recipe.Training.batch_size == 256
    assert recipe.Training.max_epochs == 3  # untouched by overlay
    assert recipe.variants == {}  # cleared for cache identity


def test_loader_no_variant_clears_variants(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    assert recipe.Training.batch_size == 32
    assert recipe.variants == {}


def test_loader_unknown_variant_raises_with_path(tmp_path: Path) -> None:
    path = _write(tmp_path)
    with pytest.raises(RecipeError) as excinfo:
        load_recipe(path, variant="nope")
    assert "unknown variant 'nope'" in str(excinfo.value)
    assert excinfo.value.recipe_path == path


def test_variant_changes_recipe_shape(tmp_path: Path) -> None:
    plain = load_recipe(_write(tmp_path))
    varied = load_recipe(_write(tmp_path), variant="big_batch")
    assert plain.model_dump() != varied.model_dump()
