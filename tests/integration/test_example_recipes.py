# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the minimal teaching recipes (Story H.f.1).

The recipe-centric README tutorial (Story H.f.3) shows that swapping the
classification model is a declarative-YAML change with identical Python glue:
`recipes/cifar10_cnn.yml` (PyTorch `simple_cnn`) and `recipes/cifar10_mlp.yml`
(scikit-learn `mlp_classifier`) bind the SAME DataRefinery instance and differ
only by `plugin` + `Architecture` (the baseline omits Optimization/Visualizations).

These tests guard the recipes' correctness so the tutorial can embed them
verbatim without a docs-scraping test (the docs->code back-edge H.g unwinds).
Both bind the real DR-1 instance via DataRefinery's `resolve_instance`, so they
**skip** cleanly when `./data` is unmaterialized; torch is required because the
sklearn baseline reuses the PyTorch feature path.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

import datarefinery as dr  # noqa: E402

from modelfoundry.core.config import RuntimeConfig  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CNN_RECIPE = "recipes/cifar10_cnn.yml"
_MLP_RECIPE = "recipes/cifar10_mlp.yml"
_DR_RECIPE = "recipes/cifar10-base.yaml"
_DATA_ROOT = "data"


@pytest.fixture(autouse=True)
def _repo_root_cwd(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The recipes' relative `Data.recipe` and DataRefinery's input hashing both
    # resolve against the cwd, so pin it to the repo root.
    monkeypatch.chdir(_REPO_ROOT)
    yield
    torch.use_deterministic_algorithms(False)


def _require_dr1_instance() -> None:
    status = dr.resolve_instance(_DR_RECIPE, cache_root=_DATA_ROOT, seed=None, overlays=None)
    if status.cache_status != "hit":
        pytest.skip(
            f"DR-1 CIFAR-10 instance not materialized under ./{_DATA_ROOT} "
            f"(cache_status={status.cache_status})"
        )


def _foundry(recipe: str, config: RuntimeConfig | None = None):  # type: ignore[no-untyped-def]
    from modelfoundry import ModelFoundry

    _require_dr1_instance()
    if config is None:
        return ModelFoundry.from_recipe(recipe, data=_DATA_ROOT)
    return ModelFoundry.from_recipe(recipe, data=_DATA_ROOT, config=config)


def test_cnn_recipe_validates() -> None:
    # Regression guard: the PyTorch teaching recipe already validates.
    assert _foundry(_CNN_RECIPE).validate().passed is True


def test_mlp_recipe_validates() -> None:
    # The precise RED for H.f.1: before the fix the sklearn plugin registers no
    # Loss/Optimizer ops, so validator check 3 rejects `cross_entropy` / `adam`.
    assert _foundry(_MLP_RECIPE).validate().passed is True


def test_mlp_recipe_materializes_above_chance(tmp_path: Path) -> None:
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    instance = _foundry(_MLP_RECIPE, config).materialize()
    test_acc = instance.evaluation["test"]["accuracy"]
    assert test_acc >= 0.25, f"sklearn MLP baseline below expectation: {test_acc:.3f}"


# --- Story H.q: the probabilistic (MC-dropout) consumer example recipe ---

_MC_DROPOUT_RECIPE = "recipes/cifar10_mc_dropout.yml"


def test_mc_dropout_recipe_validates() -> None:
    # The Subphase-H-1 probabilistic example: MC-dropout inference + imbalance
    # metrics + class-weighted loss, bound to the same DR-1 CIFAR-10 instance.
    assert _foundry(_MC_DROPOUT_RECIPE).validate().passed is True


def test_mc_dropout_recipe_materializes_with_uncertainty(tmp_path: Path) -> None:
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    instance = _foundry(_MC_DROPOUT_RECIPE, config).materialize()
    # The MC path persists per-record uncertainty + the reportable metric.
    assert instance.uncertainty is not None
    assert "predictive_entropy" in instance.metrics["test"]


# --- Story H.q: the advanced (pretrained-encoder/LoRA) consumer example recipe ---

_ADVANCED_RECIPE = "recipes/advanced_encoder_lora.yml"


def test_advanced_encoder_lora_recipe_loads() -> None:
    # The advanced example needs a 224x224x3 DR instance + the `[huggingface]`
    # extra to materialize (proven in test_pretrained_encoder.py), so this guards
    # only that the committed recipe is structurally well-formed: the canonical
    # Encoder -> LoRA -> Pooling -> Head composition, single-pass inference.
    from modelfoundry.recipe.loader import load_recipe

    recipe = load_recipe(_ADVANCED_RECIPE)
    ops = [layer["op"] for layer in recipe.Architecture["layers"]]
    assert ops == ["Encoder", "LoRA", "Pooling", "Head"]
    assert recipe.Inference is None
