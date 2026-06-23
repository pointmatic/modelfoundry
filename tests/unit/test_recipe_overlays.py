# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.overlays.apply_overlays` and loader integration.

Story I.j.2 widened the single `variant: str` to an ordered `overlays:
Sequence[str]` (last-writer-wins per section), adopting the DataRefinery family
`overlays` standard.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from modelfoundry.core.errors import RecipeError
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.overlays import apply_overlays

BASE = {
    "schema_version": 1,
    "plugin": "pytorch",
    "seed": 7,
    "Training": {"max_epochs": 3, "batch_size": 32},
    "overlays": {
        "big": {"Training": {"batch_size": 128}, "seed": 99},
        "wipe_viz": {"Visualizations": []},
        "huge": {"Training": {"batch_size": 512}},
    },
}


def test_empty_overlays_clears_catalog_only() -> None:
    selections: tuple[list[str] | None, ...] = (None, [])
    for selection in selections:
        out = apply_overlays(BASE, selection)
        assert out["overlays"] == {}
        assert out["seed"] == 7
        assert out["Training"] == {"max_epochs": 3, "batch_size": 32}
    # Input is not mutated.
    assert BASE["overlays"] != {}


def test_single_overlay_deep_merges_nested_section() -> None:
    out = apply_overlays(BASE, ["big"])
    # batch_size overridden, max_epochs preserved (deep merge, not wholesale).
    assert out["Training"] == {"max_epochs": 3, "batch_size": 128}
    assert out["seed"] == 99
    assert out["overlays"] == {}


def test_overlay_replaces_list_wholesale() -> None:
    base = {**BASE, "Visualizations": [{"op": "training_curves"}]}
    out = apply_overlays(base, ["wipe_viz"])
    assert out["Visualizations"] == []


def test_ordered_overlays_last_writer_wins() -> None:
    # `big` sets batch_size 128, then `huge` overrides to 512 (later wins);
    # `big`'s seed=99 survives because `huge` does not touch it.
    out = apply_overlays(BASE, ["big", "huge"])
    assert out["Training"] == {"max_epochs": 3, "batch_size": 512}
    assert out["seed"] == 99
    # Reversed order → `big` wins the contested key.
    assert apply_overlays(BASE, ["huge", "big"])["Training"]["batch_size"] == 128


def test_unknown_overlay_lists_available() -> None:
    with pytest.raises(RecipeError) as excinfo:
        apply_overlays(BASE, ["missing"])
    assert "unknown overlay 'missing'" in str(excinfo.value)
    assert excinfo.value.detail == {
        "overlay": "missing",
        "available": ["big", "huge", "wipe_viz"],
    }


def test_non_mapping_overlays_block_rejected() -> None:
    with pytest.raises(RecipeError, match="'overlays' must be a mapping"):
        apply_overlays({"overlays": ["not", "a", "map"]}, ["x"])


def test_non_mapping_overlay_rejected() -> None:
    with pytest.raises(RecipeError, match="overlay 'x' must be a mapping"):
        apply_overlays({"overlays": {"x": [1, 2]}}, ["x"])


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
    overlays:
      big_batch:
        Training: {batch_size: 256}
      huge_batch:
        Training: {batch_size: 1024}
    """
).strip()


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "recipe.yml"
    p.write_text(RECIPE, encoding="utf-8")
    return p


def test_loader_applies_selected_overlays(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path), overlays=["big_batch"])
    assert recipe.Training.batch_size == 256
    assert recipe.Training.max_epochs == 3  # untouched by overlay
    assert recipe.overlays == {}  # cleared for cache identity


def test_loader_applies_overlays_in_order(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path), overlays=["big_batch", "huge_batch"])
    assert recipe.Training.batch_size == 1024  # last writer wins


def test_loader_no_overlays_clears_catalog(tmp_path: Path) -> None:
    recipe = load_recipe(_write(tmp_path))
    assert recipe.Training.batch_size == 32
    assert recipe.overlays == {}


def test_loader_unknown_overlay_raises_with_path(tmp_path: Path) -> None:
    path = _write(tmp_path)
    with pytest.raises(RecipeError) as excinfo:
        load_recipe(path, overlays=["nope"])
    assert "unknown overlay 'nope'" in str(excinfo.value)
    assert excinfo.value.recipe_path == path


def test_overlays_change_recipe_shape(tmp_path: Path) -> None:
    plain = load_recipe(_write(tmp_path))
    varied = load_recipe(_write(tmp_path), overlays=["big_batch"])
    assert plain.model_dump() != varied.model_dump()
