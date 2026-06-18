# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""The rigorous (canonical) approach across dataset sizes — 3k / 30k / 50k (Story H.f.11).

The curriculum narrative: after a student trains `resnet20` at the 3k (1,700-train)
scale and sees a modest result, show "a more rigorous approach — hardware
acceleration + the full dataset" and watch it scale. This runs the IDENTICAL
canonical regime (SGD 0.1 + cosine over 160 epochs, no early stopping, crop+flip
only, MPS — `recipes/cifar10_resnet20_canonical.yml`) on the crop+flip instances at
each dataset size, so only the data differs:

  - 3k  → recipes/cifar10-base-cropflip.yaml      (300/class → 1,700 train)
  - 30k → recipes/cifar10-base-10x-cropflip.yaml  (3,000/class → 17,000 train)
  - 50k → recipes/cifar10-base-full-cropflip.yaml (5,000/class → 28,330 train) — carried
          from the canonical benchmark (already materialized under v0.10.2).

`random` / `sklearn mlp` are regime-invariant baselines (verified to the digit) and
are carried from the dynamic-regime ladder (postfix_ladder.md), not re-run here.

Run (crop+flip instances materialized under ./data, v0.10.2+):

    pyve env run smoke-pytorch -- python scripts/experiments/canonical_scale_ladder.py
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_OUT = Path(__file__).resolve().parent
_DATA = "data"
_CANONICAL = "recipes/cifar10_resnet20_canonical.yml"

#: (dataset label, crop+flip DR recipe) to run the canonical regime on. 50k is carried.
SCALES: list[tuple[str, str]] = [
    ("3k", "recipes/cifar10-base-cropflip.yaml"),
    ("30k", "recipes/cifar10-base-10x-cropflip.yaml"),
]
ARCHS = ["resnet20", "simple_cnn"]

#: 50k @ canonical regime — already materialized under v0.10.2 (canonical_benchmark.md).
_K50: dict[str, tuple[float, int]] = {"resnet20": (0.7764, 160), "simple_cnn": (0.7305, 160)}


def _materialize(arch: str, dr_recipe: str) -> tuple[float, int]:
    import pandas as pd  # type: ignore[import-untyped]
    import yaml

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

    recipe: dict[str, Any] = yaml.safe_load((_REPO / _CANONICAL).read_text(encoding="utf-8"))
    recipe["Data"] = {"recipe": dr_recipe}
    recipe["Architecture"] = {"type": arch, "num_classes": 10, "in_channels": 3}

    tmp = Path(tempfile.mkdtemp())
    recipe_path = tmp / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    instance = ModelFoundry.from_recipe(
        str(recipe_path), data=_DATA, config=RuntimeConfig(cache_root=tmp / "cache")
    ).materialize()
    acc = float(instance.evaluation["test"]["accuracy"])
    history = Path(instance.path) / "training" / "history.parquet"
    epochs = len(pd.read_parquet(history)) if history.exists() else 0
    return acc, epochs


def render_table(rows: list[tuple[str, str, float, int]]) -> str:
    lines = ["| dataset | model | test accuracy | epochs |", "|---|---|---:|---:|"]
    for dataset, model, acc, epochs in rows:
        lines.append(f"| {dataset} | {model} | {acc:.4f} | {epochs} |")
    return "\n".join(lines)


def main() -> None:
    logging.disable(logging.INFO)
    rows: list[tuple[str, str, float, int]] = []
    for label, dr_recipe in SCALES:
        for arch in ARCHS:
            acc, epochs = _materialize(arch, dr_recipe)
            rows.append((label, arch, acc, epochs))
            print(f"{label:>4}  {arch:>11}  test={acc:.4f}  epochs={epochs}", flush=True)
    for arch in ARCHS:
        acc, epochs = _K50[arch]
        rows.append(("50k", arch, acc, epochs))
        print(f"{'50k':>4}  {arch:>11}  test={acc:.4f}  epochs={epochs}  (carried)", flush=True)

    table = render_table(rows)
    (_OUT / "canonical_scale_ladder_results.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table)


if __name__ == "__main__":
    main()
