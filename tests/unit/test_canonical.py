# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.canonical` — the cache-identity byte contract."""

from __future__ import annotations

import hashlib
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
      device: auto
      precision: fp32
      checkpoint_cadence: 1
    Evaluation:
      splits: [val, test]
      primary_metric: macro_f1
      metrics: [macro_f1, accuracy]
      calibration_bins: 10
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


# A representative recipe exercising the Subphase H-1 surface (the `Inference`
# MC-dropout block + the imbalance metric vocabulary + class-weighted loss). Its
# canonical hash is PINNED below: per `project-essentials.md` § Cache identity,
# changing this literal is the deliberate sign-off that a cache-invalidating
# recipe-schema change has landed. Do not update it casually.
_PINNED_RECIPE = textwrap.dedent(
    """
    schema_version: 1
    plugin: pytorch
    seed: 7
    Data:
      recipe: ../data/recipe.yml
    Architecture: {op: simple_cnn, num_classes: 10}
    Loss: {op: cross_entropy_class_weighted, weight_source: train}
    Optimizer: {op: adamw, learning_rate: 0.001}
    Training:
      max_epochs: 3
      batch_size: 32
      device: auto
      precision: fp32
      checkpoint_cadence: 1
    Inference:
      mode: mc_dropout
      mc_samples: 30
    Evaluation:
      splits: [val, test]
      primary_metric: macro_f1
      metrics: [macro_f1, per_class_f1, per_class_precision, per_class_recall, confusion_matrix]
      calibration_bins: 10
    """
).strip()

# Re-pinned at Story I.f — the single conscious sign-off for Phase I's one-time
# cache-invalidating change (segmented `join_stable` combiner [I.b] + discriminated-
# union surfaces [I.c] + `extensions` segment [I.d] + `num_workers` reclassification
# [I.e.1] + no-implicit-defaults [I.e.2/I.e.3]). Prior pin (flat total dump):
# 60cc771852d238bc0e2a1c8d44e983026e42420a46d388226b8dae45685f8b6e.
_PINNED_HASH = "eca50ba1ccc6718b8ec525b4a5c8415561509e3355c58935306a2d3f03e82bc8"


def test_pinned_canonical_hash_is_stable(tmp_path: Path) -> None:
    # Guards the segmented canonical bytes (project-essentials § Cache identity). A
    # failure here means the canonical form shifted — confirm the change is an
    # intended cache-invalidating event before re-pinning this literal.
    assert recipe_hash(_load(tmp_path, _PINNED_RECIPE, name="pinned.yml")) == _PINNED_HASH


def test_hash_is_full_64_hex(tmp_path: Path) -> None:
    h = recipe_hash(_load(tmp_path, BASE))
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_canonical_bytes_is_the_combiner_preimage(tmp_path: Path) -> None:
    # Phase I: canonical_bytes is no longer JSON text — it is the length-framed
    # concatenation of per-segment SHA-256 digests (the `join_stable` pre-image),
    # so `recipe_hash` is its sha256. The per-segment sort+compact canonicalization
    # is what makes cosmetic edits identity-preserving (asserted separately).
    raw = canonical_bytes(_load(tmp_path, BASE))
    assert isinstance(raw, bytes)
    assert recipe_hash(_load(tmp_path, BASE)) == hashlib.sha256(raw).hexdigest()


def test_cosmetic_edits_produce_identical_bytes(tmp_path: Path) -> None:
    # Reordered top-level keys + extra whitespace + reflowed inline mappings.
    reordered = textwrap.dedent(
        """
        plugin: pytorch

        seed:    7
        Training: {batch_size: 32, max_epochs: 3, device: auto,
                   precision: fp32, checkpoint_cadence: 1}
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
          calibration_bins: 10
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


def test_device_field_perturbs_canonical_bytes(tmp_path: Path) -> None:
    # `Training.device` is part of cache identity (Story I.e.3: now author-required,
    # no default): distinct ModelInstances per device, so "trained on auto" and
    # "trained on cpu" never collide on the same cache key.
    explicit_cpu = BASE.replace("device: auto", "device: cpu")
    assert explicit_cpu != BASE  # sanity: substitution actually happened
    auto_hash = recipe_hash(_load(tmp_path, BASE))
    cpu_hash = recipe_hash(_load(tmp_path, explicit_cpu, name="cpu.yml"))
    assert auto_hash != cpu_hash
