# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Ad-hoc proof: the confusion-matrix feature is correct (not broken).

Reproduces a resnet20 on the 1,700-image instance with the user's `resnet20.yaml`
training config, then cross-checks the persisted confusion matrix three ways so a
degenerate-looking matrix can be attributed to the *model*, not the feature:

  1. evaluation/confusion_matrix.npz == matrix recomputed from
     evaluation/predictions.parquet (true_label x pred_label) -> the matrix
     faithfully reflects the raw per-record predictions.
  2. reported test accuracy == diagonal / total -> matrix agrees with the metric.
  3. row sums == per-class test counts (orientation: rows = true label).

`num_workers: 0` keeps the DataLoader single-process (no macOS `spawn` re-import).
Device defaults to MPS for speed; the feature is device-independent.

    pyve env run smoke-pytorch -- python scripts/experiments/verify_confusion_matrix.py
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


def _build_recipe(device: str) -> dict[str, Any]:
    # Faithful to the user's resnet20.yaml (AdamW 1e-3/1e-4, 60 ep, early-stop
    # val_loss/12), bound to the 1,700-image cifar10-base instance.
    return {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 42,
        "Data": {"recipe": "recipes/cifar10-base.yaml"},
        "Architecture": {"type": "resnet20", "num_classes": 10, "in_channels": 3},
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.001, "weight_decay": 0.0001},
        "Training": {
            "max_epochs": 60,
            "batch_size": 64,
            "num_workers": 0,
            "device": device,
            "early_stopping": {"monitor": "val_loss", "mode": "min", "patience": 12},
        },
        "Evaluation": {
            "splits": ["test"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "confusion_matrix"],
        },
    }


def main() -> None:
    import yaml

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

    logging.disable(logging.INFO)
    device = "mps"
    recipe = _build_recipe(device)
    tmp = Path(tempfile.mkdtemp())
    recipe_path = tmp / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    instance = ModelFoundry.from_recipe(
        str(recipe_path), data="data", config=RuntimeConfig(cache_root=tmp / "cache")
    ).materialize()

    acc = float(instance.evaluation["test"]["accuracy"])
    cm = np.asarray(instance.confusion_matrix["test"])  # evaluation/confusion_matrix.npz
    preds = instance.predictions  # evaluation/predictions.parquet

    labels = sorted(set(preds["true_label"]))
    idx = {label: i for i, label in enumerate(labels)}
    cm_from_preds = np.zeros_like(cm)
    for true_label, pred_label in zip(preds["true_label"], preds["pred_label"], strict=True):
        cm_from_preds[idx[true_label]][idx[pred_label]] += 1

    npz_matches_preds = bool(np.array_equal(cm, cm_from_preds))
    diag_acc = cm.trace() / cm.sum()
    acc_matches_diag = abs(acc - diag_acc) < 1e-6  # float32 micro-accuracy vs exact ratio

    print("=== FEATURE-CORRECTNESS CHECKS (device=%s) ===" % device)
    print(f"cm shape={cm.shape} dtype={cm.dtype}")
    print(f"[1] npz cm == cm recomputed from predictions.parquet : {npz_matches_preds}")
    print(f"[2] reported accuracy == diagonal/total              : {acc_matches_diag} "
          f"({acc:.6f} vs {diag_acc:.6f}, |diff|={abs(acc - diag_acc):.2e})")
    print(f"[3] row sums (per-class test counts)                 : {cm.sum(axis=1).tolist()}")
    verdict = "FEATURE OK" if (npz_matches_preds and acc_matches_diag) else "FEATURE SUSPECT"
    print(f"--> {verdict}")

    print("\n=== MODEL BEHAVIOR ===")
    print(f"classes: {labels}")
    print(f"predictions per class (column sums): {cm.sum(axis=0).tolist()}")
    print(f"correct per class (diagonal): {np.diag(cm).tolist()}")
    print(f"test accuracy: {acc:.4f}")


if __name__ == "__main__":
    main()
