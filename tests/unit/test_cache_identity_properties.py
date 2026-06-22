# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-4 cache-identity property tests (Hypothesis) — Story E.c / TR-2.

The B.c (`test_canonical.py`) and B.d (`test_cache_identity.py`) suites pin the
contract on hand-written examples. This module generalizes those examples over
generated recipes so the invariants hold across the input space:

- **Cosmetic edits preserve canonical bytes.** Reordering keys, injecting
  comments, and adding whitespace/blank lines to the recipe YAML never change
  the canonical bytes (and hence the hash) — identity is a property of the
  *parsed* recipe, not its textual layout.
- **Semantic edits perturb canonical bytes.** Mutating a value, adding or
  removing an op param, or switching to a variant changes the hash.
- **The ModelFoundry seed perturbs the `CacheKey`** without bleeding into the
  bound data instance hash.
- **Loose coupling.** Changing the bound DataRefinery instance triple perturbs
  `data_instance_hash16` but never the consuming recipe's `recipe_hash16` (see
  `project-essentials.md` § Loose-coupled DataRefinery binding).
"""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any

import yaml
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from modelfoundry.cache.identity import DataInstanceTriple, cache_key
from modelfoundry.recipe.canonical import canonical_bytes, recipe_hash
from modelfoundry.recipe.models import ModelRecipe
from modelfoundry.recipe.variants import apply_variant

_MASK64 = (1 << 64) - 1

_LOSS_OPS = ["cross_entropy", "cross_entropy_class_weighted", "focal"]
_OPT_OPS = ["adamw", "sgd", "rmsprop"]
_METRICS = ["accuracy", "macro_f1", "ece", "per_class_f1", "per_class_precision"]


# --- strategies ---


@st.composite
def inference_blocks(draw: st.DrawFn) -> dict[str, Any] | None:
    """A valid `Inference` block, or `None` for the absent (single-pass) case."""
    choice = draw(st.sampled_from(["absent", "point", "mc_dropout"]))
    if choice == "absent":
        return None
    if choice == "point":
        return {"mode": "point"}
    return {"mode": "mc_dropout", "mc_samples": draw(st.integers(2, 100))}


@st.composite
def recipe_dicts(draw: st.DrawFn) -> dict[str, Any]:
    """A dict that always constructs a valid `ModelRecipe` (schema_version 1)."""
    metrics = draw(st.lists(st.sampled_from(_METRICS), min_size=1, max_size=5, unique=True))
    splits = draw(
        st.lists(st.sampled_from(["train", "val", "test"]), min_size=1, max_size=3, unique=True)
    )
    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": draw(st.sampled_from(["pytorch", "sklearn"])),
        "seed": draw(st.integers(min_value=0, max_value=2**31 - 1)),
        "Data": {"recipe": "../data/r.yml"},
        "Architecture": {"op": "simple_cnn", "num_classes": draw(st.integers(2, 200))},
        "Loss": {"op": draw(st.sampled_from(_LOSS_OPS))},
        "Optimizer": {
            "op": draw(st.sampled_from(_OPT_OPS)),
            "learning_rate": draw(
                st.floats(min_value=1e-6, max_value=1.0, allow_nan=False, allow_infinity=False)
            ),
        },
        "Training": {
            "max_epochs": draw(st.integers(1, 200)),
            "batch_size": draw(st.integers(1, 2048)),
        },
        "Evaluation": {
            "splits": splits,
            "primary_metric": draw(st.sampled_from(metrics)),
            "metrics": metrics,
        },
    }
    inference = draw(inference_blocks())
    if inference is not None:
        recipe["Inference"] = inference
    return recipe


@st.composite
def data_triples(draw: st.DrawFn) -> DataInstanceTriple:
    """A DataRefinery `(recipe_hash, input_hash, seed)` triple.

    Only the first 16 hex of each hash participates in the reduction, so the
    remaining 48 hex are padded deterministically — the reduction must ignore
    them.
    """
    recipe_h = f"{draw(st.integers(0, _MASK64)):016x}" + "0" * 48
    input_h = f"{draw(st.integers(0, _MASK64)):016x}" + "0" * 48
    return (recipe_h, input_h, draw(st.integers(0, _MASK64)))


# --- helpers ---


def _recipe(d: dict[str, Any], variant: str | None = None) -> ModelRecipe:
    """Mirror `load_recipe`'s canonicalization path without touching disk."""
    return ModelRecipe.model_validate(apply_variant(deepcopy(d), variant))


def _canonical_from_yaml(text: str) -> bytes:
    data = yaml.safe_load(text)
    return canonical_bytes(ModelRecipe.model_validate(apply_variant(data, None)))


def _cosmetic_variant(d: dict[str, Any], order_seed: int) -> str:
    """Re-serialize `d` with shuffled top-level keys, comments, and whitespace."""
    keys = list(d.keys())
    random.Random(order_seed).shuffle(keys)
    dumped = yaml.safe_dump({k: d[k] for k in keys}, sort_keys=False, default_flow_style=False)
    out = ["# leading comment", ""]
    for line in dumped.split("\n"):
        if line and not line[0].isspace() and ":" in line:
            out.extend(["", "# a section comment"])  # comment+blank before each top-level key
        out.append(line + ("   " if line.strip() else ""))  # trailing whitespace (plain scalars)
    out.append("# trailing comment")
    return "\n".join(out)


def _reduced(triple: DataInstanceTriple) -> int:
    recipe_h, input_h, seed = triple
    return (int(recipe_h[:16], 16) ^ int(input_h[:16], 16) ^ (seed & _MASK64)) & _MASK64


# --- cosmetic edits preserve canonical bytes ---


@given(recipe_dicts(), st.integers())
def test_cosmetic_edits_preserve_canonical_bytes(d: dict[str, Any], order_seed: int) -> None:
    reference = _canonical_from_yaml(yaml.safe_dump(d, sort_keys=True))
    cosmetic = _canonical_from_yaml(_cosmetic_variant(d, order_seed))
    # Equal canonical bytes ⇒ equal hash (the hash is their SHA-256).
    assert reference == cosmetic


# --- semantic edits perturb canonical bytes ---


@given(recipe_dicts(), st.integers(1, 200))
def test_value_mutation_perturbs_hash(d: dict[str, Any], new_epochs: int) -> None:
    assume(new_epochs != d["Training"]["max_epochs"])
    mutated = deepcopy(d)
    mutated["Training"]["max_epochs"] = new_epochs
    assert recipe_hash(_recipe(d)) != recipe_hash(_recipe(mutated))


@given(recipe_dicts())
def test_adding_op_param_perturbs_hash(d: dict[str, Any]) -> None:
    added = deepcopy(d)
    added["Optimizer"]["weight_decay"] = 0.01  # extra="allow" → enters canonical bytes
    assert recipe_hash(_recipe(d)) != recipe_hash(_recipe(added))


@given(recipe_dicts())
def test_removing_op_param_perturbs_hash(d: dict[str, Any]) -> None:
    removed = deepcopy(d)
    del removed["Optimizer"]["learning_rate"]
    assert recipe_hash(_recipe(d)) != recipe_hash(_recipe(removed))


@given(recipe_dicts(), st.sampled_from(_LOSS_OPS))
def test_op_name_change_perturbs_hash(d: dict[str, Any], new_op: str) -> None:
    assume(new_op != d["Loss"]["op"])
    changed = deepcopy(d)
    changed["Loss"]["op"] = new_op
    assert recipe_hash(_recipe(d)) != recipe_hash(_recipe(changed))


@given(recipe_dicts(), st.integers(1, 2048))
def test_variant_switch_perturbs_hash(d: dict[str, Any], variant_batch: int) -> None:
    assume(variant_batch != d["Training"]["batch_size"])
    with_variant = deepcopy(d)
    with_variant["variants"] = {"v": {"Training": {"batch_size": variant_batch}}}
    plain = recipe_hash(_recipe(with_variant))
    varied = recipe_hash(_recipe(with_variant, variant="v"))
    assert plain != varied


@given(recipe_dicts(), st.integers(1, 2048))
def test_unused_variant_does_not_perturb_hash(d: dict[str, Any], variant_batch: int) -> None:
    # A declared-but-unselected variant must not change the no-variant identity.
    with_variant = deepcopy(d)
    with_variant["variants"] = {"v": {"Training": {"batch_size": variant_batch}}}
    assert recipe_hash(_recipe(d)) == recipe_hash(_recipe(with_variant))


# --- the H.m `Inference` block participates in cache identity (Story H.p) ---


@given(recipe_dicts(), st.integers(2, 100))
def test_inference_block_presence_perturbs_hash(d: dict[str, Any], mc_samples: int) -> None:
    # Declaring MC-dropout inference is a semantic change — it perturbs the hash
    # vs an absent block (the cache-invalidating field flagged for Subphase H-1).
    absent = deepcopy(d)
    absent.pop("Inference", None)
    with_mc = deepcopy(absent)
    with_mc["Inference"] = {"mode": "mc_dropout", "mc_samples": mc_samples}
    assert recipe_hash(_recipe(absent)) != recipe_hash(_recipe(with_mc))


@given(recipe_dicts(), st.integers(2, 100), st.integers(2, 100))
def test_inference_mc_samples_change_perturbs_hash(d: dict[str, Any], t1: int, t2: int) -> None:
    assume(t1 != t2)
    a = deepcopy(d)
    a["Inference"] = {"mode": "mc_dropout", "mc_samples": t1}
    b = deepcopy(d)
    b["Inference"] = {"mode": "mc_dropout", "mc_samples": t2}
    assert recipe_hash(_recipe(a)) != recipe_hash(_recipe(b))


# --- ModelFoundry seed perturbs the CacheKey ---


@given(recipe_dicts(), data_triples(), st.integers(0, _MASK64), st.integers(0, _MASK64))
def test_mf_seed_change_perturbs_cache_key(
    d: dict[str, Any], triple: DataInstanceTriple, seed_a: int, seed_b: int
) -> None:
    assume(seed_a != seed_b)
    recipe = _recipe(d)
    key_a = cache_key(recipe, triple, seed_a)
    key_b = cache_key(recipe, triple, seed_b)
    assert key_a != key_b
    # The MF seed must not bleed into the bound-data hash.
    assert key_a.data_instance_hash16 == key_b.data_instance_hash16


# --- loose coupling: data triple perturbs data hash, never recipe hash ---


@given(recipe_dicts(), data_triples(), data_triples(), st.integers(0, _MASK64))
def test_recipe_hash16_invariant_to_bound_data_triple(
    d: dict[str, Any], t1: DataInstanceTriple, t2: DataInstanceTriple, mf_seed: int
) -> None:
    recipe = _recipe(d)
    key_1 = cache_key(recipe, t1, mf_seed)
    key_2 = cache_key(recipe, t2, mf_seed)
    assert key_1.recipe_hash16 == key_2.recipe_hash16 == recipe_hash(recipe)[:16]


@given(recipe_dicts(), data_triples(), data_triples(), st.integers(0, _MASK64))
def test_distinct_data_triples_perturb_data_instance_hash(
    d: dict[str, Any], t1: DataInstanceTriple, t2: DataInstanceTriple, mf_seed: int
) -> None:
    assume(_reduced(t1) != _reduced(t2))
    recipe = _recipe(d)
    h1 = cache_key(recipe, t1, mf_seed).data_instance_hash16
    h2 = cache_key(recipe, t2, mf_seed).data_instance_hash16
    assert h1 != h2


@given(recipe_dicts(), data_triples(), st.integers(0, _MASK64))
@settings(max_examples=50)
def test_data_instance_hash_ignores_tail_beyond_first_16_hex(
    d: dict[str, Any], triple: DataInstanceTriple, mf_seed: int
) -> None:
    # The reduction truncates each hash to its first 16 hex; perturbing the
    # ignored tail must not change the result.
    recipe = _recipe(d)
    recipe_h, input_h, dr_seed = triple
    tail_swapped = (recipe_h[:16] + "f" * 48, input_h[:16] + "e" * 48, dr_seed)
    assert (
        cache_key(recipe, triple, mf_seed).data_instance_hash16
        == cache_key(recipe, tail_swapped, mf_seed).data_instance_hash16
    )
