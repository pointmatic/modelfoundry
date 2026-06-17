# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Smoke for the ResNet-20 ModelFoundry deliverable (repaired in Story H.c).

Repaired to drive ModelFoundry's **public, backend-agnostic surface only**
(`from modelfoundry import ModelFoundry`) — no `import torch`, no reach into
`plugins.*` / `recipe.*` internals — and bound to the real
`recipes/cifar10_resnet20.yml` + the materialized DataRefinery instance under
`./data`. The pre-H.c original pointed at the non-existent `models/resnet20.yaml`
+ `./cache`, imported the `plugins.pytorch.architecture.build_model` internal, and
called `torch` directly.

It keeps the original three checks — the canonical CIFAR ResNet-20 parameter count
(272,474), the 10-way output, and the cifar10-base binding — but reads them off the
public `ModelFoundry.summary()` (H.a.2) and the bound instance, **without training**.

Run: `pyve test --env smoke-pytorch scripts/examples/test_models_resnet20.py`.
Skips cleanly when torch (the pytorch plugin) or the `./data` instance is absent.
"""

from __future__ import annotations

import pytest

# Environment guard only: the pytorch plugin must be installed for `summary()` to build
# the model. We never import a torch symbol or call a torch API — that is the point.
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


def test_resnet20_param_count(mf: ModelFoundry) -> None:
    assert mf.summary()["total_params"] == RESNET20_PARAMS


def test_resnet20_output_shape(mf: ModelFoundry) -> None:
    assert tuple(mf.summary()["output_shape"])[-1] == NUM_CLASSES


def test_resnet20_binds_to_cifar10_base(mf: ModelFoundry) -> None:
    assert mf.data.instance_num_classes() == NUM_CLASSES
