# Copyright (c) 2026 Michael Smith
# SPDX-License-Identifier: Apache-2.0
"""Chance-level baseline for the Module 3 CIFAR-10 subset.

Story D.a.34 follow-up: surface the random-guess benchmark used to
compare against the Scikit-learn MLP and ModelFoundry CNN runs. The test
is integration-tagged because it depends on the cached
``cifar10-base.yaml`` DataRefinery instance under ``./cache``.
"""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

from myapp.instances import load_instance, read_split

RECIPE_PATH = "recipes/cifar10-base.yaml"
MAX_RECORDS = 800
VAL_FRACTION = 0.2
RNG_SEED = 42


def _load_labels(split: str = "train", max_records: int = MAX_RECORDS) -> np.ndarray:
    """Load up to ``max_records`` labels from the cached CIFAR-10 instance."""

    instance_dir = load_instance(RECIPE_PATH)
    labels: list[str] = []
    for idx, record in enumerate(read_split(instance_dir, split)):
        labels.append(record["label"])
        if idx + 1 >= max_records:
            break
    if not labels:
        raise RuntimeError(f"no labels loaded from split={split!r}")
    return np.asarray(labels, dtype=object)


@pytest.mark.integration
def test_random_classifier_accuracy_hugs_chance_level() -> None:
    """Chance accuracy over 10 CIFAR-10 classes should sit in the ~10% band."""

    try:
        labels = _load_labels()
    except FileNotFoundError as exc:
        pytest.skip(f"cifar10-base instance not available under ./cache: {exc}")

    _, val_labels = train_test_split(
        labels,
        test_size=VAL_FRACTION,
        stratify=labels,
        random_state=RNG_SEED,
    )

    rng = np.random.default_rng(RNG_SEED)
    vocab = np.unique(labels)
    predictions = rng.choice(vocab, size=val_labels.shape[0])
    accuracy = accuracy_score(val_labels, predictions)

    assert 0.05 <= accuracy <= 0.35, (
        "Random classifier diverged too far from the expected ~10% chance-level accuracy: "
        f"{accuracy:.3f}"
    )
