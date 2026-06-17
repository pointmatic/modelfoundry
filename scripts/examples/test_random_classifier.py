# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Chance-level baseline for the CIFAR-10 subset (rewritten in Story H.c).

Rewritten to source its data through ModelFoundry's **public** binding —
`ModelFoundry.from_recipe(...).data` — instead of a private curriculum package.
The bound `DataRefineryInstance` exposes the class inventory directly
(`instance_num_classes()`); raw labels are read via the documented `.path` escape
hatch over DataRefinery's `dataset/<split>.jsonl` vendor layout (ModelFoundry has
no public per-record data API — that is intentional; DataRefinery owns data).

The random-guess benchmark a real model must beat: for a balanced N-class problem
chance accuracy ≈ 1/N. This asserts the analytic chance level and measures an
empirical seeded random classifier to confirm it lands in the expected band.

Run: `pyve test --env smoke-pytorch scripts/examples/test_random_classifier.py`.
Skips cleanly when the `./data` instance is absent.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from modelfoundry import ModelFoundry

RECIPE = "recipes/cifar10_resnet20.yml"
DATA = "./data"
MAX_RECORDS = 800
VAL_FRACTION = 0.2
RNG_SEED = 42


@pytest.fixture(scope="module")
def mf() -> ModelFoundry:
    """Bind the recipe to its DataRefinery instance via the public entry point."""
    try:
        return ModelFoundry.from_recipe(RECIPE, data=DATA)
    except Exception as exc:  # DataBindingError / RecipeError -> skip, not fail
        pytest.skip(f"cifar10-base instance not available under {DATA}: {exc}")


def _load_labels(
    mf: ModelFoundry, split: str = "train", max_records: int = MAX_RECORDS
) -> np.ndarray:
    # `.path` is the binding escape hatch; `dataset/<split>.jsonl` is DataRefinery's
    # on-disk vendor contract (vendor-dependency-spec § instance tree).
    jsonl = mf.data.path / "dataset" / f"{split}.jsonl"
    label_field = mf.data.label_schema.get("field", "label")
    labels: list[str] = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if line:
            labels.append(json.loads(line)[label_field])
            if len(labels) >= max_records:
                break
    if not labels:
        raise RuntimeError(f"no labels loaded from split={split!r}")
    return np.asarray(labels, dtype=object)


def test_analytic_chance_level_is_one_over_num_classes(mf: ModelFoundry) -> None:
    n = mf.data.instance_num_classes()
    assert n == 10
    assert 1.0 / n == pytest.approx(0.10)


def test_random_classifier_accuracy_hugs_chance_level(mf: ModelFoundry) -> None:
    """A seeded random classifier over 10 CIFAR-10 classes should sit in the ~10% band."""
    labels = _load_labels(mf)
    _, val_labels = train_test_split(
        labels, test_size=VAL_FRACTION, stratify=labels, random_state=RNG_SEED
    )
    rng = np.random.default_rng(RNG_SEED)
    predictions = rng.choice(np.unique(labels), size=val_labels.shape[0])
    accuracy = accuracy_score(val_labels, predictions)
    assert 0.05 <= accuracy <= 0.35, (
        f"random classifier diverged from the expected ~10% chance level: {accuracy:.3f}"
    )
