# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the budget-crossover runner's pure helpers (Story H.f.4).

Covers only the cheap, deterministic helpers — the ladder spec and the table
renderer. The materialize loop is the experiment itself (run manually via
`budget_crossover.main()`), not a test. Run:
`pyve test --env smoke-pytorch scripts/experiments/test_budget_crossover.py`.
"""

from __future__ import annotations

from pathlib import Path

import budget_crossover as bc

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ladder_points_reference_existing_recipes() -> None:
    ladder = bc.build_ladder()
    labels = {p.label for p in ladder}
    assert {"random", "mlp", "simple_cnn", "resnet20"} <= labels
    # simple_cnn and resnet20 both sweep the configured epoch budgets.
    cnn_epochs = sorted(p.epochs for p in ladder if p.label == "simple_cnn")
    resnet_epochs = sorted(p.epochs for p in ladder if p.label == "resnet20")
    assert cnn_epochs == sorted(bc.EPOCHS)
    assert resnet_epochs == sorted(bc.EPOCHS)
    # Every point binds a committed recipe.
    for p in ladder:
        assert (_REPO_ROOT / p.recipe).is_file(), p.recipe


def test_render_table_formats_results() -> None:
    table = bc.render_table([("random", None, 0.095), ("simple_cnn", 5, 0.2754)])
    assert "| model | epochs | test accuracy |" in table
    assert "| random | — | 0.0950 |" in table
    assert "| simple_cnn | 5 | 0.2754 |" in table
