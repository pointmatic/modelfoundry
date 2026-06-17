# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Scikit-learn MLP baseline over CIFAR-10 (rewritten in Story H.c).

Rewritten to source its data through ModelFoundry's **public** binding —
`ModelFoundry.from_recipe(...).data` — instead of a private curriculum package.
The flattened-pixel MLP is a weak reference a real model (the ResNet-20 deliverable)
must beat; ModelFoundry's first-class way to wire a baseline into a run is the
recipe's `Evaluation.comparison.baseline_model_id` (FR-12), but this standalone
smoke keeps the curriculum's external sklearn baseline.

Raw images are resolved via the documented `.path` escape hatch over DataRefinery's
`exports/` sidecar layout (ModelFoundry has no public per-record image API — that is
intentional; DataRefinery owns data).

Run: `pyve test --env smoke-pytorch scripts/examples/test_mlp_baseline.py`.
Skips cleanly when the `./data` instance is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier

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


def _resolve_png(instance_dir: Path, split: str, record: dict[str, str]) -> Path:
    # DataRefinery's `exports/<dataset>/<split>/<label>/<stem>.png` sidecar layout.
    stem = Path(record["path"]).stem
    return instance_dir / "exports" / "cifar-10" / split / record["label"] / f"{stem}.png"


def _load_flattened(
    mf: ModelFoundry, split: str = "train", max_records: int = MAX_RECORDS
) -> tuple[np.ndarray, np.ndarray]:
    instance_dir = mf.data.path  # ModelFoundry-bound DataRefinery instance directory
    label_field = mf.data.label_schema.get("field", "label")
    jsonl = instance_dir / "dataset" / f"{split}.jsonl"
    xs: list[np.ndarray] = []
    ys: list[str] = []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        record = json.loads(line)
        with Image.open(_resolve_png(instance_dir, split, record)) as img:
            array = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
        xs.append(array.reshape(-1))
        ys.append(record[label_field])
        if len(xs) >= max_records:
            break
    return np.stack(xs), np.array(ys)


def test_mlp_baseline_exceeds_random_accuracy(mf: ModelFoundry) -> None:
    features, labels = _load_flattened(mf)
    X_train, X_val, y_train, y_val = train_test_split(
        features, labels, test_size=VAL_FRACTION, stratify=labels, random_state=RNG_SEED
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
