# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for segmented recipe identity (Story I.b).

Covers the `join_stable` combiner (prefix-capable, length-framed, sparse), the
`recipe_segments` core/plugin/overlays partition (I.a Decision 2), and the
horizontal cross-plugin isolation scaffolding (F2).

The combiner byte format is the I.a spike deliverable and remains a cross-repo
coordination point with DataRefinery's `join_stable` (DataRefinery has not yet
implemented it — see docs/spikes/I.a-segmented-recipe-identity.md). The
core/plugin split matures in I.c (discriminated unions) + I.e (no-implicit-
defaults); this story lands the combiner + partition + isolation scaffolding.
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

from modelfoundry.recipe.canonical import (
    canonical_bytes,
    join_stable,
    recipe_hash,
    recipe_segments,
)
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.models import ModelRecipe

_PYTORCH = textwrap.dedent(
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
      device: cpu
      precision: fp32
      checkpoint_cadence: 1
    Evaluation:
      splits: [val, test]
      primary_metric: macro_f1
      metrics: [macro_f1, accuracy]
      calibration_bins: 10
    """
).strip()

_SKLEARN = textwrap.dedent(
    """
    schema_version: 1
    plugin: sklearn
    seed: 7
    Data:
      recipe: ../data/recipe.yml
    Architecture: {op: random_forest, n_estimators: 100}
    Loss: {op: gini}
    Optimizer: {op: none}
    Training:
      max_epochs: 1
      batch_size: 1
      device: cpu
      precision: fp32
      checkpoint_cadence: 1
    Evaluation:
      splits: [test]
      primary_metric: accuracy
      metrics: [accuracy]
      calibration_bins: 10
    """
).strip()


def _load(tmp_path: Path, text: str, name: str = "r.yml", **kw: object) -> ModelRecipe:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return load_recipe(p, **kw)  # type: ignore[arg-type]


# --- join_stable combiner properties (I.a Decision 1) ---


def test_join_stable_is_deterministic() -> None:
    segs = {"core": {"plugin": "pytorch", "seed": 7}, "plugin": {"Loss": {"op": "ce"}}}
    assert join_stable(segs) == join_stable(segs)


def test_join_stable_returns_32_byte_digest() -> None:
    assert len(join_stable({"core": {"x": 1}})) == 32


def test_join_stable_is_label_keyed() -> None:
    # the same payload under a different segment label produces a different digest
    assert join_stable({"core": {"x": 1}}) != join_stable({"plugin": {"x": 1}})


def test_join_stable_is_length_framed_no_boundary_collision() -> None:
    # without length-framing {"a":"bc"} and {"ab":"c"} could collide
    assert join_stable({"a": "bc"}) != join_stable({"ab": "c"})


def test_join_stable_is_segment_order_independent() -> None:
    a = {"core": {"a": 1}, "plugin": {"b": 2}}
    b = {"plugin": {"b": 2}, "core": {"a": 1}}
    assert join_stable(a) == join_stable(b)


def test_join_stable_omits_empty_segments_sparsely() -> None:
    base = {"core": {"plugin": "pytorch"}, "plugin": {"Loss": {"op": "ce"}}}
    # empty dict, empty list, and None are all sparse-omitted ⇒ identical to absent
    assert (
        join_stable(base)
        == join_stable({**base, "extensions": {}})
        == join_stable({**base, "extensions": []})
        == join_stable({**base, "extensions": None})
    )


def test_join_stable_nonempty_segment_enters_identity() -> None:
    base = {"core": {"plugin": "pytorch"}}
    assert join_stable({**base, "extensions": {"foo": 1}}) != join_stable(base)


# --- prefix-capability for the deferred vertical axis (I.a Decision 1) ---


def test_join_stable_prefix_capable_composes_to_32_bytes() -> None:
    core = join_stable({"core": {"seed": 7}})
    h_arch = join_stable({"architecture": {"op": "cnn"}}, upstream=core)
    h_train = join_stable({"training": {"epochs": 3}}, upstream=h_arch)
    assert len(h_train) == 32


def test_join_stable_upstream_change_ripples_down_the_chain() -> None:
    arch = {"architecture": {"op": "cnn"}}
    a = join_stable(arch, upstream=join_stable({"core": {"seed": 7}}))
    b = join_stable(arch, upstream=join_stable({"core": {"seed": 8}}))
    assert a != b


def test_join_stable_upstream_perturbs_result() -> None:
    segs = {"training": {"epochs": 3}}
    assert join_stable(segs) != join_stable(segs, upstream=join_stable({"core": {"seed": 7}}))


# --- recipe_segments partition + recipe_hash relationship (I.a Decision 2) ---


def test_recipe_segments_partitions_core_plugin_overlays_extensions(tmp_path: Path) -> None:
    segs = recipe_segments(_load(tmp_path, _PYTORCH))
    assert set(segs) == {"core", "plugin", "overlays", "extensions"}
    assert set(segs["core"]) == {"schema_version", "plugin", "seed", "Data"}
    assert "Training" in segs["plugin"]
    assert "Loss" in segs["plugin"]
    assert "schema_version" not in segs["plugin"]
    assert segs["overlays"] == {}  # the overlays catalog is cleared by the loader pre-hash
    assert segs["extensions"] == {}  # Story I.d: absent ⇒ empty ⇒ sparse-omitted


# --- extensions namespace (Story I.d) ---


def test_empty_extensions_does_not_change_hash(tmp_path: Path) -> None:
    # The I.d mechanism, empty for everyone, is a no-op: an absent / empty bag is
    # sparse-omitted, so the hash is byte-identical to the pre-extensions state.
    base = recipe_hash(_load(tmp_path, _PYTORCH))
    with_empty = recipe_hash(_load(tmp_path, _PYTORCH + "\nextensions: {}", name="ee.yml"))
    assert base == with_empty


def test_nonempty_extensions_perturbs_hash(tmp_path: Path) -> None:
    base = recipe_hash(_load(tmp_path, _PYTORCH))
    with_ext = recipe_hash(
        _load(tmp_path, _PYTORCH + "\nextensions: {my_lab: {alpha: 0.5}}", name="xe.yml")
    )
    assert base != with_ext


def test_extensions_accepts_arbitrary_nested_content(tmp_path: Path) -> None:
    r = _load(tmp_path, _PYTORCH + "\nextensions: {a: {b: [1, 2, 3]}, c: hello}", name="ne.yml")
    assert r.extensions == {"a": {"b": [1, 2, 3]}, "c": "hello"}


def test_training_spec_rejects_num_workers(tmp_path: Path) -> None:
    import pytest

    from modelfoundry.core.errors import RecipeError

    # Story I.e.1: num_workers is execution context (RuntimeConfig), no longer a
    # recipe field — TrainingSpec is extra="forbid", so authoring it is rejected.
    with pytest.raises(RecipeError):
        _load(tmp_path, _PYTORCH.replace("batch_size: 32", "batch_size: 32\n  num_workers: 4"))


def test_unknown_toplevel_key_still_forbidden(tmp_path: Path) -> None:
    import pytest

    from modelfoundry.core.errors import RecipeError

    # extensions is the ONLY relaxed island; ModelRecipe stays extra="forbid".
    with pytest.raises(RecipeError):
        _load(tmp_path, _PYTORCH + "\nbogus_top_level: 1", name="bt.yml")


def test_recipe_hash_equals_join_stable_over_segments(tmp_path: Path) -> None:
    r = _load(tmp_path, _PYTORCH)
    assert recipe_hash(r) == join_stable(recipe_segments(r)).hex()


def test_recipe_hash_is_sha256_of_canonical_bytes(tmp_path: Path) -> None:
    r = _load(tmp_path, _PYTORCH)
    assert recipe_hash(r) == hashlib.sha256(canonical_bytes(r)).hexdigest()


def test_recipe_hash_is_full_64_hex(tmp_path: Path) -> None:
    h = recipe_hash(_load(tmp_path, _PYTORCH))
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# --- horizontal cross-plugin isolation scaffolding (Story I.b task 3 / F2) ---


def test_core_change_moves_hash_but_plugin_segment_is_unchanged(tmp_path: Path) -> None:
    r = _load(tmp_path, _PYTORCH)
    r_seeded = _load(tmp_path, _PYTORCH, name="s.yml", seed=42)
    # the plugin segment is isolated from a core-only change ...
    assert recipe_segments(r)["plugin"] == recipe_segments(r_seeded)["plugin"]
    # ... yet the overall identity correctly moves (seed ∈ core)
    assert recipe_hash(r) != recipe_hash(r_seeded)


def test_plugin_change_moves_hash_but_core_segment_is_unchanged(tmp_path: Path) -> None:
    r = _load(tmp_path, _PYTORCH)
    changed = _PYTORCH.replace("max_epochs: 3", "max_epochs: 9")
    r_changed = _load(tmp_path, changed, name="c.yml")
    assert recipe_segments(r)["core"] == recipe_segments(r_changed)["core"]
    assert recipe_hash(r) != recipe_hash(r_changed)


def test_sklearn_surface_change_does_not_move_a_pytorch_recipe(tmp_path: Path) -> None:
    # The F2 guarantee's scaffolding (full strength arrives with I.c unions +
    # I.e no-implicit-defaults): a PyTorch recipe's hash is a function of its own
    # segments only, so a change to the sklearn surface leaves it byte-identical
    # while the sklearn recipe's own hash correctly moves.
    pytorch_before = recipe_hash(_load(tmp_path, _PYTORCH, name="pt.yml"))
    sklearn_before = recipe_hash(_load(tmp_path, _SKLEARN, name="sk.yml"))
    sklearn_after = recipe_hash(
        _load(tmp_path, _SKLEARN.replace("n_estimators: 100", "n_estimators: 200"), name="sk2.yml")
    )
    pytorch_after = recipe_hash(_load(tmp_path, _PYTORCH, name="pt2.yml"))
    assert pytorch_before == pytorch_after  # pytorch unmoved by the sklearn change
    assert sklearn_before != sklearn_after  # the change is scoped to sklearn


def test_cosmetic_reorder_preserves_identity(tmp_path: Path) -> None:
    reordered = textwrap.dedent(
        """
        plugin: pytorch
        seed:    7
        Training: {batch_size: 32, max_epochs: 3, device: cpu,
                   precision: fp32, checkpoint_cadence: 1}
        schema_version: 1
        Loss: {op: cross_entropy}
        Optimizer: {learning_rate: 0.001, op: adamw}
        Data: {recipe: ../data/recipe.yml}
        Architecture: {num_classes: 10, op: simple_cnn}
        Evaluation:
          metrics: [macro_f1, accuracy]
          primary_metric: macro_f1
          splits: [val, test]
          calibration_bins: 10
        """
    ).strip()
    assert canonical_bytes(_load(tmp_path, _PYTORCH)) == canonical_bytes(
        _load(tmp_path, reordered, name="reordered.yml")
    )
