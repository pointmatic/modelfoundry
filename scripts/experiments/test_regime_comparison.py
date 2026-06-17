# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the regime-comparison runner's pure helpers (Story H.f.5).

Covers the recipe builder (injects the cosine schedule + early stopping) and the
static-vs-dynamic table renderer. The materialize loop is the experiment, run
manually. Run:
`pyve test --env smoke-pytorch scripts/experiments/test_regime_comparison.py`.
"""

from __future__ import annotations

import regime_comparison as rc


def test_dynamic_recipe_injects_cosine_schedule_and_early_stopping() -> None:
    rec = rc.dynamic_recipe("simple_cnn", 20)
    assert rec["Optimizer"]["schedule"] == {"op": "cosine", "T_max": 20}
    assert rec["Training"]["early_stopping"]["monitor"] == "val_loss"
    assert rec["Training"]["early_stopping"]["mode"] == "min"
    assert rec["Training"]["max_epochs"] == 20
    assert "variants" not in rec  # the runner owns the regime, not the recipe's variants
    rec_resnet = rc.dynamic_recipe("resnet20", 40)
    assert rec_resnet["Architecture"]["type"] == "resnet20"
    assert rec_resnet["Optimizer"]["schedule"]["T_max"] == 40


def test_render_table_formats_static_vs_dynamic() -> None:
    table = rc.render_table([("simple_cnn", 40, 0.403, 0.4200, 27)])
    assert "static" in table.lower()
    assert "dynamic" in table.lower()
    assert "| simple_cnn | 40 | 0.4030 | 0.4200 | 27 |" in table
