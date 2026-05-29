# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.canonical` — the cache-identity byte contract."""

from __future__ import annotations

import textwrap
from pathlib import Path

from modelfoundry.recipe.canonical import canonical_bytes, recipe_hash
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.models import ModelRecipe

BASE = textwrap.dedent(
    """
    schema_version: 1
    plugin: pytorch
    seed: 7
    Data:
      recipe: ../data/recipe.yml
    Architecture: {op: simple_cnn, num_classes: 10}
    Loss: {op: cross_entropy}
    Optimizer: {op: adamw, learning_rate: 0.001}
    Training:
      max_epochs: 3
      batch_size: 32
    Evaluation:
      splits: [val, test]
      primary_metric: macro_f1
      metrics: [macro_f1, accuracy]
    variants:
      big_batch:
        Training: {batch_size: 256}
    """
).strip()


def _load(
    tmp_path: Path,
    text: str,
    name: str = "r.yml",
    *,
    variant: str | None = None,
    seed: int | None = None,
) -> ModelRecipe:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return load_recipe(p, variant=variant, seed=seed)


def test_hash_is_full_64_hex(tmp_path: Path) -> None:
    h = recipe_hash(_load(tmp_path, BASE))
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_canonical_bytes_are_sorted_and_compact(tmp_path: Path) -> None:
    raw = canonical_bytes(_load(tmp_path, BASE))
    text = raw.decode("utf-8")
    # Compact separators: no ", " or ": " spacing.
    assert ", " not in text
    assert ": " not in text
    # Top-level keys are sorted.
    assert text.startswith('{"Architecture"')


def test_cosmetic_edits_produce_identical_bytes(tmp_path: Path) -> None:
    # Reordered top-level keys + extra whitespace + reflowed inline mappings.
    reordered = textwrap.dedent(
        """
        plugin: pytorch

        seed:    7
        Training: {batch_size: 32, max_epochs: 3}
        schema_version: 1
        Loss:
          op: cross_entropy
        Optimizer:
          learning_rate: 0.001
          op: adamw
        Data: {recipe: ../data/recipe.yml}
        Architecture: {num_classes: 10, op: simple_cnn}
        Evaluation:
          metrics: [macro_f1, accuracy]
          primary_metric: macro_f1
          splits: [val, test]
        variants:
          big_batch: {Training: {batch_size: 256}}
        """
    ).strip()
    assert canonical_bytes(_load(tmp_path, BASE)) == canonical_bytes(
        _load(tmp_path, reordered, name="reordered.yml")
    )


def test_value_change_perturbs_bytes(tmp_path: Path) -> None:
    changed = BASE.replace("max_epochs: 3", "max_epochs: 5")
    assert recipe_hash(_load(tmp_path, BASE)) != recipe_hash(
        _load(tmp_path, changed, name="changed.yml")
    )


def test_adding_an_op_param_perturbs_bytes(tmp_path: Path) -> None:
    with_param = BASE.replace(
        "Optimizer: {op: adamw, learning_rate: 0.001}",
        "Optimizer: {op: adamw, learning_rate: 0.001, weight_decay: 0.01}",
    )
    assert recipe_hash(_load(tmp_path, BASE)) != recipe_hash(
        _load(tmp_path, with_param, name="param.yml")
    )


def test_variant_selection_perturbs_bytes(tmp_path: Path) -> None:
    plain = _load(tmp_path, BASE)
    varied = _load(tmp_path, BASE, name="varied.yml", variant="big_batch")
    assert recipe_hash(plain) != recipe_hash(varied)


def test_unused_variant_edit_does_not_perturb_applied_bytes(tmp_path: Path) -> None:
    # Editing an unused variant must not change the no-variant canonical bytes,
    # because the loader clears `variants` before canonicalization.
    edited = BASE.replace("batch_size: 256", "batch_size: 999")
    assert canonical_bytes(_load(tmp_path, BASE)) == canonical_bytes(
        _load(tmp_path, edited, name="edited.yml")
    )


def test_seed_override_perturbs_bytes(tmp_path: Path) -> None:
    assert recipe_hash(_load(tmp_path, BASE)) != recipe_hash(
        _load(tmp_path, BASE, name="seeded.yml", seed=42)
    )


def test_canonical_bytes_are_deterministic(tmp_path: Path) -> None:
    recipe = _load(tmp_path, BASE)
    assert canonical_bytes(recipe) == canonical_bytes(recipe)
