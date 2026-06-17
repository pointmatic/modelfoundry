# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Full CIFAR-10 (50k) at the same split proportions (Story H.f.7).

H.f.6 showed `resnet20` crosses over at 10x data (17k train). This runs the same
comparison on the **full** balanced CIFAR-10 train set (50k → 28,330 train, same
0.567/0.1/0.333 split), CNNs on **MPS** + the dynamic regime — does the
high-capacity model's lead widen further with maximal data? Reuses the H.f.6
runner's machinery (`scale_crossover`) pointed at the full DR recipe.

Run (from the repo root, with the full instance materialized under ./data):

    pyve env run smoke-pytorch -- python scripts/experiments/full_data_crossover.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import scale_crossover as sc  # type: ignore[import-not-found]  # sibling experiment script

_OUT_DIR = Path(__file__).resolve().parent
_DR_FULL = "recipes/cifar10-base-full.yaml"
_TITLE = "Full data (28k) on MPS — does resnet20's lead widen? (CIFAR-10)"


def main() -> None:
    logging.disable(logging.INFO)
    rows: list[tuple[str, float, int]] = []
    for point in sc.LADDER:
        acc, epochs_run = sc._materialize(point, _DR_FULL)
        rows.append((point.label, acc, epochs_run))
        print(f"{point.label:>11}  test={acc:.4f}  epochs_run={epochs_run}", flush=True)

    table = sc.render_table(rows)
    (_OUT_DIR / "full_data_crossover_results.md").write_text(table + "\n", encoding="utf-8")
    sc._save_figure(rows, _OUT_DIR / "full_data_crossover.png", title=_TITLE)
    print("\n" + table)


if __name__ == "__main__":
    main()
