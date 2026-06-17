# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Static-stopping vs dynamic-regime comparison (Story H.f.5).

H.f.4 measured a *static* regime (constant LR, no early stopping, evaluate the
final epoch) and found the sweep noisy / non-monotonic. This runner re-runs the
two PyTorch architectures under a *dynamic* regime — a cosine LR schedule
(`T_max` = the epoch ceiling) + early stopping on `val_loss` — and compares
against H.f.4's committed static numbers, reporting whether the regime stabilizes
and/or improves the sweep. It is a recipe-only change (the PyTorch plugin already
implements both); no plugin code. CPU, deterministic.

Run (from the repo root, with the DR-1 instance under ./data):

    pyve env run smoke-pytorch -- python scripts/experiments/regime_comparison.py
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from budget_crossover import EPOCHS  # type: ignore[import-not-found]  # sibling experiment script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = Path(__file__).resolve().parent
_DATA_ROOT = "data"
_CNN_RECIPE = "recipes/cifar10_cnn.yml"
_PATIENCE = 5
ARCHES: tuple[str, ...] = ("simple_cnn", "resnet20")

#: Static-stopping baseline (H.f.4 / budget_crossover_results.md — deterministic).
STATIC: dict[tuple[str, int], float] = {
    ("simple_cnn", 5): 0.275,
    ("simple_cnn", 10): 0.349,
    ("simple_cnn", 20): 0.274,
    ("simple_cnn", 40): 0.403,
    ("resnet20", 5): 0.292,
    ("resnet20", 10): 0.293,
    ("resnet20", 20): 0.351,
    ("resnet20", 40): 0.277,
}
#: Fixed references (no LR knob), from H.f.4.
MLP_REF = 0.352
RANDOM_REF = 0.095


def dynamic_recipe(arch: str, ceiling: int) -> dict[str, Any]:
    """The CNN recipe under the dynamic regime: cosine(T_max=ceiling) + early stopping."""
    import yaml

    recipe: dict[str, Any] = yaml.safe_load((_REPO_ROOT / _CNN_RECIPE).read_text(encoding="utf-8"))
    recipe.pop("variants", None)  # the runner owns the regime, not the recipe's variants
    if arch == "resnet20":
        recipe["Architecture"] = {"type": "resnet20", "num_classes": 10, "in_channels": 3}
    recipe["Optimizer"]["schedule"] = {"op": "cosine", "T_max": ceiling}
    recipe["Training"]["max_epochs"] = ceiling
    recipe["Training"]["early_stopping"] = {
        "monitor": "val_loss",
        "mode": "min",
        "patience": _PATIENCE,
    }
    return recipe


def render_table(rows: list[tuple[str, int, float, float, int]]) -> str:
    """Render `(arch, ceiling, static_acc, dynamic_acc, epochs_run)` as a Markdown table."""
    lines = [
        "| model | epoch ceiling | static | dynamic (cosine + early-stop) | epochs run |",
        "|---|---:|---:|---:|---:|",
    ]
    for arch, ceiling, static_acc, dynamic_acc, epochs_run in rows:
        lines.append(
            f"| {arch} | {ceiling} | {static_acc:.4f} | {dynamic_acc:.4f} | {epochs_run} |"
        )
    return "\n".join(lines)


def _materialize_dynamic(arch: str, ceiling: int) -> tuple[float, int]:
    import pandas as pd  # type: ignore[import-untyped]
    import yaml

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

    recipe = dynamic_recipe(arch, ceiling)
    tmp = Path(tempfile.mkdtemp())
    recipe_path = tmp / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp / "cache")
    instance = ModelFoundry.from_recipe(
        str(recipe_path), data=_DATA_ROOT, config=config
    ).materialize()
    acc = float(instance.evaluation["test"]["accuracy"])
    epochs_run = len(pd.read_parquet(Path(instance.path) / "training" / "history.parquet"))
    return acc, epochs_run


def _save_figure(rows: list[tuple[str, int, float, float, int]], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_arch: dict[str, list[tuple[int, float, float]]] = {}
    for arch, ceiling, static_acc, dynamic_acc, _ in rows:
        by_arch.setdefault(arch, []).append((ceiling, static_acc, dynamic_acc))

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for arch, pts in by_arch.items():
        pts.sort()
        xs = [c for c, _, _ in pts]
        ax.plot(
            xs,
            [s for _, s, _ in pts],
            marker="o",
            linestyle="--",
            alpha=0.6,
            label=f"{arch} static",
        )
        ax.plot(xs, [d for _, _, d in pts], marker="o", linestyle="-", label=f"{arch} dynamic")
    ax.axhline(MLP_REF, color="gray", linestyle=":", label=f"mlp {MLP_REF:.2f}")
    ax.axhline(RANDOM_REF, color="lightgray", linestyle=":", label=f"random {RANDOM_REF:.2f}")
    ax.set_xlabel("epoch ceiling")
    ax.set_ylabel("test accuracy")
    ax.set_title("Static stopping vs cosine + early stopping (CIFAR-10 1.7k subset, CPU)")
    ax.set_xticks(list(EPOCHS))
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    logging.disable(logging.INFO)
    rows: list[tuple[str, int, float, float, int]] = []
    for arch in ARCHES:
        for ceiling in EPOCHS:
            dynamic_acc, epochs_run = _materialize_dynamic(arch, ceiling)
            static_acc = STATIC[(arch, ceiling)]
            rows.append((arch, ceiling, static_acc, dynamic_acc, epochs_run))
            print(
                f"{arch:>11} ceiling={ceiling:>2}  static={static_acc:.4f}  "
                f"dynamic={dynamic_acc:.4f}  epochs_run={epochs_run}",
                flush=True,
            )

    table = render_table(rows)
    (_OUT_DIR / "regime_comparison_results.md").write_text(table + "\n", encoding="utf-8")
    _save_figure(rows, _OUT_DIR / "regime_comparison.png")
    print("\n" + table)


if __name__ == "__main__":
    main()
