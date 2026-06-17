# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""10x data scale-up on hardware acceleration — does resnet20 cross over? (Story H.f.6).

H.f.5 showed the canonical `resnet20` stays data-starved on the 1,700-image subset.
This runner re-runs the field on the **10x** DR instance (`cifar10-base-10x.yaml`,
17,000 train) with the CNNs on **MPS** (Apple-silicon hardware acceleration) under
the dynamic regime (cosine schedule + early stopping), to test whether `resnet20`
finally clears the sklearn MLP.

The sklearn / random baselines stay on cpu (they only support cpu; `device: mps`
would fail validator check 20). Each point is materialized through the public
surface into a temp cache.

Run (from the repo root, with the 10x instance materialized under ./data):

    pyve env run smoke-pytorch -- python scripts/experiments/scale_crossover.py
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
_DR_10X = "recipes/cifar10-base-10x.yaml"
_DEVICE = "mps"
_PATIENCE = 5


@dataclass(frozen=True)
class Point:
    """One model in the 10x comparison."""

    label: str
    base_recipe: str
    arch_type: str | None = None  # override Architecture.type (e.g. resnet20)
    ceiling: int | None = None  # epoch ceiling for the accelerated CNNs
    accelerated: bool = False  # device=mps + the dynamic cosine/early-stop regime


#: The decisive comparison: random + sklearn MLP (cpu) vs simple_cnn + resnet20
#: (MPS, dynamic regime) on the 10x data. Does resnet20 clear the MLP now?
LADDER: list[Point] = [
    Point("random", "recipes/cifar10_random.yml"),
    Point("mlp", "recipes/cifar10_mlp.yml"),
    Point("simple_cnn", "recipes/cifar10_cnn.yml", ceiling=40, accelerated=True),
    Point(
        "resnet20", "recipes/cifar10_cnn.yml", arch_type="resnet20", ceiling=40, accelerated=True
    ),
]


def build_recipe(point: Point, dr_recipe: str = _DR_10X) -> dict[str, Any]:
    """Build the materialize-ready recipe for `point`, bound to `dr_recipe`.

    Defaults to the 10x DR instance (H.f.6); H.f.7 reuses this with the full-dataset
    recipe.
    """
    import yaml

    recipe: dict[str, Any] = yaml.safe_load(
        (_REPO_ROOT / point.base_recipe).read_text(encoding="utf-8")
    )
    recipe.pop("variants", None)
    recipe["Data"] = {"recipe": dr_recipe}  # bind the chosen DR instance
    if point.arch_type is not None:
        recipe["Architecture"] = {"type": point.arch_type, "num_classes": 10, "in_channels": 3}
    if point.accelerated:
        recipe["Optimizer"]["schedule"] = {"op": "cosine", "T_max": point.ceiling}
        recipe["Training"]["max_epochs"] = point.ceiling
        recipe["Training"]["device"] = _DEVICE
        recipe["Training"]["early_stopping"] = {
            "monitor": "val_loss",
            "mode": "min",
            "patience": _PATIENCE,
        }
    return recipe


def render_table(rows: list[tuple[str, float, int]]) -> str:
    """Render `(label, test_accuracy, epochs_run)` as a Markdown table (run 0 → '—')."""
    lines = ["| model | test accuracy | epochs run |", "|---|---:|---:|"]
    for label, acc, epochs_run in rows:
        run = "—" if epochs_run == 0 else str(epochs_run)
        lines.append(f"| {label} | {acc:.4f} | {run} |")
    return "\n".join(lines)


def _materialize(point: Point, dr_recipe: str = _DR_10X) -> tuple[float, int]:
    import pandas as pd  # type: ignore[import-untyped]
    import yaml

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

    recipe = build_recipe(point, dr_recipe)
    tmp = Path(tempfile.mkdtemp())
    recipe_path = tmp / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp / "cache")
    instance = ModelFoundry.from_recipe(
        str(recipe_path), data=_DATA_ROOT, config=config
    ).materialize()
    acc = float(instance.evaluation["test"]["accuracy"])
    history = Path(instance.path) / "training" / "history.parquet"
    epochs_run = len(pd.read_parquet(history)) if history.exists() else 0
    return acc, epochs_run


def _save_figure(
    rows: list[tuple[str, float, int]],
    path: Path,
    title: str = "10x data (17k) on MPS — does resnet20 cross over? (CIFAR-10)",
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [label for label, _, _ in rows]
    accs = [acc for _, acc, _ in rows]
    mlp_acc = next((acc for label, acc, _ in rows if label == "mlp"), None)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, accs, color=["#bbbbbb", "#888888", "#1f77b4", "#ff7f0e"][: len(rows)])
    for bar, acc in zip(bars, accs, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2, acc + 0.005, f"{acc:.3f}", ha="center", fontsize=9
        )
    if mlp_acc is not None:
        ax.axhline(mlp_acc, color="#888888", linestyle="--", alpha=0.7, label="sklearn MLP")
        ax.legend()
    ax.set_ylabel("test accuracy")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    logging.disable(logging.INFO)
    rows: list[tuple[str, float, int]] = []
    for point in LADDER:
        acc, epochs_run = _materialize(point)
        rows.append((point.label, acc, epochs_run))
        print(f"{point.label:>11}  test={acc:.4f}  epochs_run={epochs_run}", flush=True)

    table = render_table(rows)
    (_OUT_DIR / "scale_crossover_results.md").write_text(table + "\n", encoding="utf-8")
    _save_figure(rows, _OUT_DIR / "scale_crossover.png")
    print("\n" + table)


if __name__ == "__main__":
    main()
