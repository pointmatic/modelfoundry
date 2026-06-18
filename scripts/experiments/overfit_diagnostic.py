# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Cheap overfit diagnostic — can ResNet-20 learn? (Story H.f.8, debug Step 2).

The H.f.4-H.f.7 arc left an unsettled question: ResNet-20 tops out at ~0.65 test
accuracy (vs the published ~91%), edged by the smaller `simple_cnn`. That is
either a training-REGIME limitation (under-training / small data / early stop)
or a residual-path BUG. A simple CNN matching a ResNet is *expected at low
budget* AND *what a broken residual path would look like* — the H.f data can't
tell them apart.

This is the highest-information-per-minute test that can: train `resnet20` and
`simple_cnn` on a TINY balanced subset (400 train images, no augmentation, no
early stopping, many epochs) and check whether each drives TRAIN accuracy ->
~100% / train_loss -> ~0. A net that *can* memorize 400 images has a correct
forward/backward path; its H.f underperformance is then a regime question. A net
that *cannot* (while the smaller CNN can) is a strong bug signal localized to the
residual path.

Run (from the repo root, with the tiny instance materialized under ./data):

    pyve env run smoke-pytorch -- python scripts/experiments/overfit_diagnostic.py
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = Path(__file__).resolve().parent
_DATA_ROOT = "data"
_DR_TINY = "recipes/cifar10-overfit-tiny.yaml"
_DEVICE = "mps"
_MAX_EPOCHS = 60
_SEED = 20260617

# Overfit thresholds: ln(10) ~= 2.303 is the 10-class chance floor for train_loss.
# A net that memorizes 400 images drops far below it and reaches ~100% train acc.
_TRAIN_LOSS_OVERFIT = 0.05
_TRAIN_ACC_OVERFIT = 0.98


@dataclass(frozen=True)
class Result:
    label: str
    train_acc: float
    test_acc: float
    train_loss_first: float
    train_loss_last: float
    train_loss_min: float
    epochs_run: int
    train_loss_curve: list[float]

    @property
    def overfits(self) -> bool:
        return self.train_loss_min < _TRAIN_LOSS_OVERFIT and self.train_acc >= _TRAIN_ACC_OVERFIT


def build_recipe(arch_type: str) -> dict[str, Any]:
    """A minimal, no-regularization recipe built to MAXIMIZE overfitting.

    No schedule, no early stopping, weight_decay 0, no augmentation (the DR
    instance has none) — so the only question is whether the architecture can
    fit the data at all. No `val` split in the instance => the trainer's
    best-weight monitor falls back to `train_loss`, so the promoted weights (and
    the train-split evaluation) reflect the most-overfit state.
    """
    return {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": _SEED,
        "Data": {"recipe": _DR_TINY},
        "Architecture": {"type": arch_type, "num_classes": 10, "in_channels": 3},
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.001, "weight_decay": 0.0},
        "Training": {
            "max_epochs": _MAX_EPOCHS,
            "batch_size": 64,
            "num_workers": 2,
            "device": _DEVICE,
        },
        "Evaluation": {
            "splits": ["train", "test"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1"],
        },
    }


def _materialize(arch_type: str) -> Result:
    import pandas as pd  # type: ignore[import-untyped]
    import yaml

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

    recipe = build_recipe(arch_type)
    tmp = Path(tempfile.mkdtemp())
    recipe_path = tmp / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp / "cache")
    instance = ModelFoundry.from_recipe(
        str(recipe_path), data=_DATA_ROOT, config=config
    ).materialize()

    history = pd.read_parquet(Path(instance.path) / "training" / "history.parquet")
    curve = [float(v) for v in history["train_loss"].tolist()]
    return Result(
        label=arch_type,
        train_acc=float(instance.evaluation["train"]["accuracy"]),
        test_acc=float(instance.evaluation["test"]["accuracy"]),
        train_loss_first=curve[0],
        train_loss_last=curve[-1],
        train_loss_min=min(curve),
        epochs_run=len(curve),
        train_loss_curve=curve,
    )


def render_table(results: list[Result]) -> str:
    lines = [
        "| model | train acc | test acc | train_loss first | train_loss last | "
        "train_loss min | epochs | overfits? |",
        "|---|---:|---:|---:|---:|---:|---:|:--:|",
    ]
    for r in results:
        lines.append(
            f"| {r.label} | {r.train_acc:.4f} | {r.test_acc:.4f} | {r.train_loss_first:.4f} | "
            f"{r.train_loss_last:.4f} | {r.train_loss_min:.4f} | {r.epochs_run} | "
            f"{'YES' if r.overfits else 'NO'} |"
        )
    return "\n".join(lines)


def _save_figure(results: list[Result], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for r in results:
        ax.plot(
            range(1, len(r.train_loss_curve) + 1), r.train_loss_curve, marker=".", label=r.label
        )
    ax.axhline(2.302585, color="#cccccc", linestyle="--", label="ln(10) chance floor")
    ax.set_xlabel("epoch")
    ax.set_ylabel("train_loss")
    ax.set_title("Overfit diagnostic — 400 CIFAR-10 images, no aug, MPS (H.f.8)")
    ax.set_yscale("log")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    logging.disable(logging.INFO)
    results = [_materialize("resnet20"), _materialize("simple_cnn")]
    for r in results:
        loss = f"{r.train_loss_first:.3f}->{r.train_loss_last:.3f} (min {r.train_loss_min:.3f})"
        print(
            f"{r.label:>11}  train_acc={r.train_acc:.4f}  test_acc={r.test_acc:.4f}  "
            f"loss {loss}  epochs={r.epochs_run}  overfits={r.overfits}",
            flush=True,
        )

    table = render_table(results)
    (_OUT_DIR / "overfit_diagnostic_results.md").write_text(table + "\n", encoding="utf-8")
    _save_figure(results, _OUT_DIR / "overfit_diagnostic.png")

    resnet = next(r for r in results if r.label == "resnet20")
    cnn = next(r for r in results if r.label == "simple_cnn")
    print("\n" + table)
    if resnet.overfits:
        verdict = "REGIME: resnet20 memorizes 400 images -> residual path learns"
    elif cnn.overfits:
        verdict = "BUG SIGNAL: simple_cnn overfits but resnet20 does NOT -> residual-path defect"
    else:
        verdict = "INCONCLUSIVE by eval-mode threshold; read the train_loss curve"
    print(f"\nVERDICT -> {verdict}")


if __name__ == "__main__":
    main()
