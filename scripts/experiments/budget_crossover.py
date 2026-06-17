# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Capacity-vs-budget crossover experiment (Story H.f.4).

Materializes a ladder of (model x training-budget) points over the 1,700-image
CIFAR-10 DR-1 subset and emits a results table + an accuracy-vs-budget figure. It
demonstrates that the more-expressive CNN *underperforms* the flattened-pixel
scikit-learn MLP at a small training budget and *overtakes* it once the budget is
scaled — the capacity-vs-budget lesson (the legacy-model-vs-modern analogy). Each
point is a cached, deterministic `ModelInstance` (FR-25), so the whole study is
reproducible and byte-stable.

Run (from the repo root, with the DR-1 instance materialized under ./data):

    pyve env run smoke-pytorch -- python scripts/experiments/budget_crossover.py

The runner reuses the committed teaching recipes (`recipes/cifar10_{random,mlp,
cnn}.yml`); the `simple_cnn` / `resnet20` epoch points are derived by overriding
`Training.max_epochs` (and `Architecture.type` for `resnet20`) — each equivalent
to a recipe variant. CPU-only; no DataRefinery work (data prep is upstream).
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_DIR = Path(__file__).resolve().parent
_DATA_ROOT = "data"
#: The training-budget axis (epochs) swept for the trainable architectures.
EPOCHS: tuple[int, ...] = (5, 10, 20, 40)


@dataclass(frozen=True)
class LadderPoint:
    """One (model, budget) point in the study."""

    label: str
    recipe: str
    epochs: int | None  # None => a fixed reference (random / mlp)
    arch_type: str | None = None  # override Architecture.type (e.g. resnet20)


def build_ladder() -> list[LadderPoint]:
    """The ladder: two fixed references + two architectures swept over `EPOCHS`."""
    points: list[LadderPoint] = [
        LadderPoint("random", "recipes/cifar10_random.yml", None),
        LadderPoint("mlp", "recipes/cifar10_mlp.yml", None),
    ]
    points += [LadderPoint("simple_cnn", "recipes/cifar10_cnn.yml", e) for e in EPOCHS]
    points += [
        LadderPoint("resnet20", "recipes/cifar10_cnn.yml", e, arch_type="resnet20") for e in EPOCHS
    ]
    return points


def render_table(results: list[tuple[str, int | None, float]]) -> str:
    """Render `(label, epochs, test_accuracy)` rows as a Markdown table."""
    lines = ["| model | epochs | test accuracy |", "|---|---:|---:|"]
    for label, epochs, acc in results:
        ep = "—" if epochs is None else str(epochs)
        lines.append(f"| {label} | {ep} | {acc:.4f} |")
    return "\n".join(lines)


def _materialize_point(point: LadderPoint) -> float:
    """Materialize one ladder point through the public surface; return test accuracy."""
    import yaml

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

    recipe = yaml.safe_load((_REPO_ROOT / point.recipe).read_text(encoding="utf-8"))
    recipe.pop("variants", None)  # the runner owns the budget axis, not the recipe variants
    if point.arch_type is not None:
        recipe["Architecture"] = {"type": point.arch_type, "num_classes": 10, "in_channels": 3}
    if point.epochs is not None:
        recipe.setdefault("Training", {})
        recipe["Training"]["max_epochs"] = point.epochs

    tmp = Path(tempfile.mkdtemp())
    recipe_path = tmp / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp / "cache")
    instance = ModelFoundry.from_recipe(
        str(recipe_path), data=_DATA_ROOT, config=config
    ).materialize()
    return float(instance.evaluation["test"]["accuracy"])


def _save_figure(results: list[tuple[str, int | None, float]], path: Path) -> None:
    """Accuracy-vs-budget: a curve per swept architecture; fixed refs as h-lines."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    by_label: dict[str, list[tuple[int, float]]] = {}
    refs: dict[str, float] = {}
    for label, epochs, acc in results:
        if epochs is None:
            refs[label] = acc
        else:
            by_label.setdefault(label, []).append((epochs, acc))

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for label, pts in by_label.items():
        pts.sort()
        xs = [e for e, _ in pts]
        ys = [a for _, a in pts]
        ax.plot(xs, ys, marker="o", label=label)
    for label, acc in refs.items():
        ax.axhline(acc, linestyle="--", alpha=0.7, label=f"{label} (no epoch budget)")

    ax.set_xlabel("training budget (epochs)")
    ax.set_ylabel("test accuracy")
    ax.set_title("Test accuracy vs training budget — CIFAR-10 (1.7k subset, CPU, minimal recipes)")
    ax.set_xticks(list(EPOCHS))
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    logging.disable(logging.INFO)
    results: list[tuple[str, int | None, float]] = []
    for point in build_ladder():
        acc = _materialize_point(point)
        results.append((point.label, point.epochs, acc))
        print(f"{point.label:>11}  epochs={point.epochs!s:>4}  test_acc={acc:.4f}", flush=True)

    table = render_table(results)
    (_OUT_DIR / "budget_crossover_results.md").write_text(table + "\n", encoding="utf-8")
    _save_figure(results, _OUT_DIR / "budget_crossover.png")
    print("\n" + table)


if __name__ == "__main__":
    main()
