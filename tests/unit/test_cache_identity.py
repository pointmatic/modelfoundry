# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `cache.identity` — the ModelInstance cache key + loose coupling."""

from __future__ import annotations

import textwrap
from pathlib import Path

from modelfoundry.cache.identity import cache_key
from modelfoundry.recipe.canonical import recipe_hash
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.models import ModelRecipe

RECIPE = textwrap.dedent(
    """
    schema_version: 1
    plugin: pytorch
    seed: 7
    Data:
      recipe: ../data/recipe.yml
    Architecture: {op: simple_cnn}
    Loss: {op: cross_entropy}
    Optimizer: {op: adamw}
    Training: {max_epochs: 3, batch_size: 32, device: cpu, precision: fp32, checkpoint_cadence: 1}
    Evaluation: {splits: [val], primary_metric: accuracy, metrics: [accuracy], calibration_bins: 10}
    """
).strip()

# Full 64-hex DataRefinery hashes + seed.
TRIPLE = (
    "a" * 64,
    "b" * 64,
    1234,
)


def _recipe(tmp_path: Path) -> ModelRecipe:
    p = tmp_path / "recipe.yml"
    p.write_text(RECIPE, encoding="utf-8")
    return load_recipe(p)


def test_recipe_hash16_is_first_16_of_full_hash(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    key = cache_key(recipe, TRIPLE, seed=99)
    assert key.recipe_hash16 == recipe_hash(recipe)[:16]
    assert len(key.recipe_hash16) == 16


def test_data_instance_hash16_is_16_hex(tmp_path: Path) -> None:
    key = cache_key(_recipe(tmp_path), TRIPLE, seed=99)
    assert len(key.data_instance_hash16) == 16
    assert all(c in "0123456789abcdef" for c in key.data_instance_hash16)


def test_same_inputs_yield_equal_keys(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    assert cache_key(recipe, TRIPLE, seed=99) == cache_key(recipe, TRIPLE, seed=99)


def test_cachekey_is_frozen_and_hashable(tmp_path: Path) -> None:
    key = cache_key(_recipe(tmp_path), TRIPLE, seed=99)
    assert isinstance(hash(key), int)
    assert {key: 1}[key] == 1


def test_different_modelfoundry_seed_changes_key(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    k1 = cache_key(recipe, TRIPLE, seed=1)
    k2 = cache_key(recipe, TRIPLE, seed=2)
    assert k1 != k2
    assert k1.seed == 1 and k2.seed == 2
    # The MF seed does not bleed into the data instance hash.
    assert k1.data_instance_hash16 == k2.data_instance_hash16


def test_different_dr_recipe_hash_changes_data_instance_hash(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    base = cache_key(recipe, TRIPLE, seed=99)
    other = cache_key(recipe, ("c" * 64, "b" * 64, 1234), seed=99)
    assert base.data_instance_hash16 != other.data_instance_hash16


def test_different_dr_input_hash_changes_data_instance_hash(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    base = cache_key(recipe, TRIPLE, seed=99)
    other = cache_key(recipe, ("a" * 64, "d" * 64, 1234), seed=99)
    assert base.data_instance_hash16 != other.data_instance_hash16


def test_different_dr_seed_changes_data_instance_hash(tmp_path: Path) -> None:
    recipe = _recipe(tmp_path)
    base = cache_key(recipe, TRIPLE, seed=99)
    other = cache_key(recipe, ("a" * 64, "b" * 64, 5678), seed=99)
    assert base.data_instance_hash16 != other.data_instance_hash16


def test_rematerialize_same_triple_is_noop(tmp_path: Path) -> None:
    # Re-running DataRefinery into the same cache directory (identical triple)
    # must not change ModelFoundry's cache identity (loose coupling).
    recipe = _recipe(tmp_path)
    before = cache_key(recipe, TRIPLE, seed=99)
    after = cache_key(recipe, ("a" * 64, "b" * 64, 1234), seed=99)
    assert before == after


def test_explicit_xor_value(tmp_path: Path) -> None:
    # Deterministic spot check of the XOR reduction.
    key = cache_key(_recipe(tmp_path), ("a" * 64, "b" * 64, 0), seed=0)
    expected = int("a" * 16, 16) ^ int("b" * 16, 16)
    assert key.data_instance_hash16 == f"{expected:016x}"
