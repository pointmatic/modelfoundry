# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Canonical ModelFoundry smoke for the CIFAR-10 / ResNet-20 deliverable (Story H.a.1).

Idiomatic reimplementation of ``test_models_resnet20.py``. It drives ModelFoundry
through its **public, backend-agnostic surface only** — ``from modelfoundry import
ModelFoundry`` — with no ``import torch`` and no reach into ``modelfoundry.plugins.*``
or ``modelfoundry.recipe.*`` internals (the framework-lock-in CR-11 exists to prevent).
It binds the real ``recipes/cifar10_resnet20.yml`` to the materialized DataRefinery
instance under ``./data`` (the original pointed at the non-existent ``models/resnet20.yaml``
+ ``./cache``).

Every check uses the public surface, including ``ModelFoundry.summary()`` (Story H.a.2) —
the pre-materialize, backend-agnostic architecture summary that lets the param-count and
output-shape checks run *without training the model* and *without importing a framework*.
That method was added precisely to close the gap this script first specced as strict
``xfail``s: the original example had to import ``plugins.pytorch.architecture.build_model``
and call ``torch`` directly because no such public surface existed. ``summary()`` returns
the FR-27 ``ModelSummary`` shape (``total_params`` / ``trainable_params`` / per-layer rows)
plus a top-level ``output_shape``.

Run: ``pyve test --env smoke-pytorch scripts/examples/test_models_resnet20_fix.py``.
This file lives outside ``testpaths=["tests"]``, so its xfails never gate ``pyve test``.
Skips cleanly when torch (the pytorch plugin) or the ``./data`` instance is absent.
"""

from __future__ import annotations

import pytest

# Environment guard ONLY: the pytorch plugin must be installed for validate() and any
# architecture build. We deliberately never import a torch symbol or call a torch API —
# that backend-agnostic discipline is the whole point of the reimplementation.
pytest.importorskip("torch")

from modelfoundry import ModelFoundry

RECIPE = "recipes/cifar10_resnet20.yml"
DATA = "./data"
RESNET20_PARAMS = 272_474
NUM_CLASSES = 10


@pytest.fixture(scope="module")
def mf() -> ModelFoundry:
    """Canonical construction — bind the recipe to its DataRefinery instance.

    Uses the one public entry point; skips when the ./data instance isn't materialized.
    """
    try:
        return ModelFoundry.from_recipe(RECIPE, data=DATA)
    except Exception as exc:  # DataBindingError / RecipeError -> skip, not fail
        pytest.skip(f"cifar10-base instance not available under {DATA}: {exc}")


# --- green: canonical public surface that exists today ---


def test_recipe_validates(mf: ModelFoundry) -> None:
    """FR-2 static checks pass for the deliverable recipe (the public `validate`)."""
    report = mf.validate()
    assert report.passed, [(c.id, c.message) for c in report.failures]


def test_recipe_declares_resnet20(mf: ModelFoundry) -> None:
    """Recipe is public, framework-agnostic state — no plugin import needed to read it."""
    assert mf.recipe.plugin == "pytorch"
    assert mf.recipe.Architecture["type"] == "resnet20"
    assert mf.recipe.Architecture["num_classes"] == NUM_CLASSES


def test_binds_to_cifar10_base(mf: ModelFoundry) -> None:
    """The bound DataRefinery instance exposes the 10-class CIFAR-10 label schema."""
    assert mf.data.instance_num_classes() == NUM_CLASSES


# --- green: pre-materialize architecture summary via the public surface (H.a.2) ---


def test_param_count_via_public_summary(mf: ModelFoundry) -> None:
    """Canonical replacement for the original ``test_resnet20_param_count``.

    No torch, no plugin internals — `summary()` builds and inspects the model
    without training it.
    """
    summary = mf.summary()
    assert summary["total_params"] == RESNET20_PARAMS


def test_output_is_ten_way_via_public_summary(mf: ModelFoundry) -> None:
    """Canonical replacement for the original ``test_resnet20_forward_shape``.

    The head maps to NUM_CLASSES logits, read off the summary's network output shape.
    """
    summary = mf.summary()
    assert tuple(summary["output_shape"])[-1] == NUM_CLASSES
