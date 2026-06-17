# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the full-dataset crossover runner (Story H.f.7).

The runner reuses `scale_crossover`'s machinery pointed at the full DR recipe;
these guard that wiring (the full recipe binds + exists). The materialize loop is
the experiment, run manually. Run:
`pyve test --env smoke-pytorch scripts/experiments/test_full_data_crossover.py`.
"""

from __future__ import annotations

from pathlib import Path

import full_data_crossover as fdc
import scale_crossover as sc

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_full_runner_binds_full_dr_recipe() -> None:
    point = sc.Point(
        "resnet20", "recipes/cifar10_cnn.yml", arch_type="resnet20", ceiling=40, accelerated=True
    )
    rec = sc.build_recipe(point, fdc._DR_FULL)
    assert rec["Data"]["recipe"] == "recipes/cifar10-base-full.yaml"
    assert rec["Training"]["device"] == "mps"


def test_full_dr_recipe_exists() -> None:
    assert (_REPO_ROOT / fdc._DR_FULL).is_file()
