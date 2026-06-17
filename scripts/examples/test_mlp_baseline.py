# Copyright (c) 2026 Michael Smith
# SPDX-License-Identifier: Apache-2.0
"""Integration test for the Scikit-learn MLP baseline (Module 3 exercise).

This mirrors the Marimo notebook cell that loads the cached CIFAR-10 base
instance, flattens images, and trains an ``MLPClassifier``. The goal is to
ensure the curriculum's baseline remains healthy when upstream libraries
change.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

from myapp.instances import load_instance, read_split

RECIPE_PATH = "recipes/cifar10-base.yaml"
MAX_RECORDS = 800
VAL_FRACTION = 0.2
RNG_SEED = 42


def _resolve_png(instance_dir: Path, split: str, record: dict[str, str]) -> Path:
    stem = Path(record["path"]).stem
    return (
        Path(instance_dir) / "exports" / "cifar-10" / split / record["label"] / f"{stem}.png"
    )


def _load_flattened(split: str = "train", max_records: int = MAX_RECORDS):
    instance_dir = load_instance(RECIPE_PATH)
    xs: list[np.ndarray] = []
    ys: list[str] = []
    for idx, record in enumerate(read_split(instance_dir, split)):
        png = _resolve_png(instance_dir, split, record)
        with Image.open(png) as img:
            array = np.asarray(img, dtype=np.float32) / 255.0
        xs.append(array.reshape(-1))
        ys.append(record["label"])
        if idx + 1 >= max_records:
            break
    return np.stack(xs), np.array(ys)


@pytest.mark.integration
def test_mlp_baseline_exceeds_random_accuracy() -> None:
    try:
        features, labels = _load_flattened()
    except FileNotFoundError as exc:
        pytest.skip(f"cifar10-base instance not available under ./cache: {exc}")

    X_train, X_val, y_train, y_val = train_test_split(
        features,
        labels,
        test_size=VAL_FRACTION,
        stratify=labels,
        random_state=RNG_SEED,
    )

    clf = MLPClassifier(
        hidden_layer_sizes=(512, 256),
        activation="relu",
        batch_size=128,
        max_iter=30,
        random_state=RNG_SEED,
        n_iter_no_change=5,
        learning_rate_init=1e-3,
    )
    clf.fit(X_train, y_train)

    accuracy = accuracy_score(y_val, clf.predict(X_val))
    assert accuracy >= 0.3, f"MLP baseline underperformed expectation: {accuracy:.3f}"
