# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the 10x scale-crossover runner's pure helpers (Story H.f.6).

Covers the recipe builder (binds the 10x DR instance, accelerates the CNNs on
MPS + the dynamic regime, leaves the cpu-only baselines alone) and the table
renderer. The materialize loop is the experiment, run manually. Run:
`pyve test --env smoke-pytorch scripts/experiments/test_scale_crossover.py`.
"""

from __future__ import annotations

import scale_crossover as sc


def test_build_recipe_binds_10x_and_accelerates_cnn() -> None:
    rec = sc.build_recipe(
        sc.Point(
            "resnet20",
            "recipes/cifar10_cnn.yml",
            arch_type="resnet20",
            ceiling=40,
            accelerated=True,
        )
    )
    assert rec["Data"]["recipe"] == "recipes/cifar10-base-10x.yaml"
    assert rec["Architecture"]["type"] == "resnet20"
    assert rec["Training"]["device"] == "mps"
    assert rec["Optimizer"]["schedule"] == {"op": "cosine", "T_max": 40}
    assert rec["Training"]["early_stopping"]["monitor"] == "val_loss"
    assert "variants" not in rec


def test_build_recipe_baseline_stays_cpu() -> None:
    rec = sc.build_recipe(sc.Point("mlp", "recipes/cifar10_mlp.yml"))
    assert rec["Data"]["recipe"] == "recipes/cifar10-base-10x.yaml"
    assert rec["Training"]["device"] == "cpu"  # sklearn only supports cpu (validator check 20)
    assert "schedule" not in rec["Optimizer"]  # no dynamic regime on the baselines


def test_render_table() -> None:
    table = sc.render_table([("mlp", 0.45, 0), ("resnet20", 0.55, 31)])
    assert "| mlp | 0.4500 | — |" in table
    assert "| resnet20 | 0.5500 | 31 |" in table
