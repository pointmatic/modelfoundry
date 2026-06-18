# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Honest ladder re-run AFTER the restore-best-weights fix (Story H.f.8, debug Step 4b).

H.f.8 found that early stopping never restored the best-monitor weights: the
runner evaluated + persisted the *final* epoch, which with early stopping is
`patience` epochs of non-improvement past the best. That silently shipped a
stale model and disproportionately penalized models that early-stop (resnet20).

The H.f.4-H.f.7 numbers were produced WITH that bug, so this re-runs the same
field — `random` + sklearn `mlp` (cpu) vs `simple_cnn` + `resnet20` (MPS, cosine
+ early-stopping) — across all three data scales (1,700 -> 10x -> full) with the
fix in place, and compares to the committed pre-fix numbers. `random` / `mlp`
use the dummy / sklearn baseline plugins (not the PyTorch trainer), so the fix
cannot move them — they are unchanged references and a harness sanity check.

Run (from the repo root, with the three instances materialized under ./data):

    pyve env run smoke-pytorch -- python scripts/experiments/postfix_ladder.py
"""

from __future__ import annotations

import logging
from pathlib import Path

import scale_crossover as sc  # type: ignore[import-not-found]  # sibling experiment script

_OUT_DIR = Path(__file__).resolve().parent

#: (scale label, DataRefinery recipe) — the three rungs of the data ladder.
SCALES: list[tuple[str, str]] = [
    ("1700", "recipes/cifar10-base.yaml"),
    ("10x", "recipes/cifar10-base-10x.yaml"),
    ("full", "recipes/cifar10-base-full.yaml"),
]

#: Committed PRE-FIX test accuracies (scale_crossover_results.md / full_data_crossover_results.md).
#: 1,700 had no clean 4-model run at this exact regime, so it is post-fix-only.
PREFIX: dict[tuple[str, str], float] = {
    ("10x", "random"): 0.0993,
    ("10x", "mlp"): 0.4512,
    ("10x", "simple_cnn"): 0.5441,
    ("10x", "resnet20"): 0.5936,
    ("full", "random"): 0.1012,
    ("full", "mlp"): 0.4653,
    ("full", "simple_cnn"): 0.6687,
    ("full", "resnet20"): 0.6458,
}


def render_comparison(rows: list[tuple[str, str, float, int]]) -> str:
    """Render `(scale, model, post_acc, epochs)` with the pre-fix delta where known."""
    lines = [
        "| scale | model | pre-fix acc | post-fix acc | Δ | post epochs |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for scale, model, acc, epochs in rows:
        pre = PREFIX.get((scale, model))
        pre_s = f"{pre:.4f}" if pre is not None else "—"
        delta_s = f"{acc - pre:+.4f}" if pre is not None else "—"
        run = "—" if epochs == 0 else str(epochs)
        lines.append(f"| {scale} | {model} | {pre_s} | {acc:.4f} | {delta_s} | {run} |")
    return "\n".join(lines)


def main() -> None:
    logging.disable(logging.INFO)
    rows: list[tuple[str, str, float, int]] = []
    for scale, dr_recipe in SCALES:
        for point in sc.LADDER:
            acc, epochs_run = sc._materialize(point, dr_recipe)
            rows.append((scale, point.label, acc, epochs_run))
            print(
                f"{scale:>5}  {point.label:>11}  test={acc:.4f}  epochs_run={epochs_run}",
                flush=True,
            )

    table = render_comparison(rows)
    (_OUT_DIR / "postfix_ladder_results.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table)


if __name__ == "__main__":
    main()
