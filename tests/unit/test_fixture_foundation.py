# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Verification of the E.a test-fixture foundation.

Confirms the shared `conftest` fixtures are wired, the synthesized DataRefinery
builder produces a 100-record / 3-class / 2-split instance, and every happy-path
sample recipe loads cleanly through `recipe.loader`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.recipe.loader import load_recipe

_RECIPES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "recipes"
_HAPPY_RECIPES = [
    "minimal_pytorch.yml",
    "pytorch_with_optimization.yml",
    "pytorch_with_variants.yml",
    "pytorch_failing_expectations.yml",
    "sklearn_stub.yml",
]


# --- conftest fixtures ---


def test_runtime_config_fixture_wires_both_cache_roots(runtime_config: RuntimeConfig) -> None:
    assert isinstance(runtime_config, RuntimeConfig)
    assert runtime_config.cache_root.name
    assert runtime_config.data_cache_root.name
    assert runtime_config.cache_root != runtime_config.data_cache_root


def test_tmp_cache_roots_are_distinct(tmp_cache_root: Path, tmp_data_cache_root: Path) -> None:
    assert tmp_cache_root != tmp_data_cache_root


# --- synthesized DataRefinery builder ---


def test_dr_instance_fixture_shape(dr_instance: object) -> None:
    pytest.importorskip("datarefinery")
    assert dr_instance.instance_num_classes() == 3  # type: ignore[attr-defined]
    assert set(dr_instance.splits) == {"train", "val"}  # type: ignore[attr-defined]


def test_builder_record_count(tmp_path: Path) -> None:
    pytest.importorskip("datarefinery")
    pytest.importorskip("PIL")
    from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

    instance = build_dr_instance(tmp_path / "dr")
    total = sum(instance.manifest.record_counts.values())
    assert total == 100


def test_builder_is_path_resolvable_layout(tmp_path: Path) -> None:
    pytest.importorskip("datarefinery")
    pytest.importorskip("PIL")
    from datarefinery_instances.builder import build_dr_instance

    instance = build_dr_instance(tmp_path / "dr")
    # The on-disk layout exists for path-resolution callers.
    assert (instance.path / "manifest.json").is_file()
    assert (instance.path / "dataset" / "train.jsonl").is_file()
    assert (instance.path / "recipe.json").is_file()


# --- sample recipes load through recipe.loader ---


@pytest.mark.parametrize("name", _HAPPY_RECIPES)
def test_happy_recipe_loads(name: str) -> None:
    recipe = load_recipe(_RECIPES_DIR / name)
    assert recipe.schema_version == 1


def test_invalid_recipes_directory_exists() -> None:
    invalid = sorted((_RECIPES_DIR / "invalid").glob("invalid_*.yml"))
    assert len(invalid) >= 8  # one per cleanly file-expressible validator rejection
