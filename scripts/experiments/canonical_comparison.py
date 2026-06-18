# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Best-results comparison at the canonical regime (Story H.f.9 high-vs-high).

Fills the apples-to-apples cells the canonical-benchmark scoreboard needs, all on
the SAME crop+flip full instance (`cifar10-base-full-cropflip.yaml`, 28,330 train)
under v0.10.2:

  - `random` + `sklearn mlp` — their baseline recipes (not trainer models; the
    training regime does not apply, so they are the regime-invariant floor),
    re-bound to the crop+flip instance for a same-instance comparison.
  - `simple_cnn` — the CANONICAL regime (SGD lr 0.1 + cosine over 160 epochs, no
    early stopping), via the canonical recipe with the architecture overridden.
    This is the "high-vs-high at the same regime" data point.

`resnet20` at the canonical regime is already measured (test 0.7764, val 0.7936;
see canonical_benchmark.md) — same recipe, same instance, v0.10.2 — so it is not
re-run here; it is added to the scoreboard from that run.

Run (from the repo root, crop+flip instance materialized under ./data):

    pyve env run smoke-pytorch -- python scripts/experiments/canonical_comparison.py
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_OUT = Path(__file__).resolve().parent
_DATA = "data"
_CROPFLIP = "recipes/cifar10-base-full-cropflip.yaml"
_CANONICAL = "recipes/cifar10_resnet20_canonical.yml"

#: resnet20 @ canonical regime — already materialized under v0.10.2 (canonical_benchmark.md).
_RESNET20_CANONICAL = ("resnet20", 0.7764, 160)


def _materialize(recipe: dict[str, Any]) -> tuple[float, int]:
    import pandas as pd  # type: ignore[import-untyped]
    import yaml

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

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


def _baseline(recipe_path: str) -> dict[str, Any]:
    """A baseline recipe (random / sklearn mlp) re-bound to the crop+flip instance."""
    import yaml

    recipe: dict[str, Any] = yaml.safe_load((_REPO / recipe_path).read_text(encoding="utf-8"))
    recipe.pop("variants", None)
    recipe["Data"] = {"recipe": _CROPFLIP}
    return recipe


def _canonical_cnn(arch_type: str) -> dict[str, Any]:
    """The canonical-regime recipe with the architecture overridden."""
    import yaml

    recipe: dict[str, Any] = yaml.safe_load((_REPO / _CANONICAL).read_text(encoding="utf-8"))
    recipe["Architecture"] = {"type": arch_type, "num_classes": 10, "in_channels": 3}
    return recipe


def render_table(rows: list[tuple[str, float, int]]) -> str:
    lines = ["| model | regime | test accuracy | epochs |", "|---|---|---:|---:|"]
    regime = {
        "random": "baseline (chance)",
        "sklearn_mlp": "baseline (sklearn, 50 iters)",
        "simple_cnn": "canonical (SGD 0.1, cosine 160)",
        "resnet20": "canonical (SGD 0.1, cosine 160)",
    }
    for label, acc, epochs in rows:
        run = "—" if epochs == 0 else str(epochs)
        lines.append(f"| {label} | {regime.get(label, '?')} | {acc:.4f} | {run} |")
    return "\n".join(lines)


def main() -> None:
    logging.disable(logging.INFO)
    rows: list[tuple[str, float, int]] = []
    rows.append(("random", *_materialize(_baseline("recipes/cifar10_random.yml"))))
    rows.append(("sklearn_mlp", *_materialize(_baseline("recipes/cifar10_mlp.yml"))))
    rows.append(("simple_cnn", *_materialize(_canonical_cnn("simple_cnn"))))
    rows.append(_RESNET20_CANONICAL)
    for label, acc, epochs in rows:
        print(f"{label:>12}  test={acc:.4f}  epochs={epochs}", flush=True)

    table = render_table(rows)
    (_OUT / "canonical_comparison_results.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table)


if __name__ == "__main__":
    main()
