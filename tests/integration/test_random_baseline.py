# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration test for the random chance-baseline plugin over real DR-1 (Story H.f.2).

Drives `recipes/cifar10_random.yml` through the public surface against the real
materialized DataRefinery DR-1 instance: it **validates**, it **materializes** to
an accuracy that hugs chance (`1/num_classes`), and it is **deterministic** (same
`(recipe, data, seed)` -> byte-identical predictions, FR-25). Skips cleanly when
`./data` is unmaterialized; torch is required (the baseline reuses the PyTorch
feature path).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

import datarefinery as dr  # noqa: E402

from modelfoundry.core.config import RuntimeConfig  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECIPE = "recipes/cifar10_random.yml"
_DR_RECIPE = "recipes/cifar10-base.yaml"
_DATA_ROOT = "data"


@pytest.fixture(autouse=True)
def _repo_root_cwd(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.chdir(_REPO_ROOT)
    yield
    torch.use_deterministic_algorithms(False)


def _require_dr1_instance() -> None:
    status = dr.resolve_instance(_DR_RECIPE, cache_root=_DATA_ROOT, seed=None, variant=None)
    if status.cache_status != "hit":
        pytest.skip(
            f"DR-1 CIFAR-10 instance not materialized under ./{_DATA_ROOT} "
            f"(cache_status={status.cache_status})"
        )


def _materialize(cache_root: Path):  # type: ignore[no-untyped-def]
    from modelfoundry import ModelFoundry

    _require_dr1_instance()
    config = RuntimeConfig(cache_root=cache_root)
    return ModelFoundry.from_recipe(_RECIPE, data=_DATA_ROOT, config=config).materialize()


def test_random_recipe_validates() -> None:
    from modelfoundry import ModelFoundry

    _require_dr1_instance()
    assert ModelFoundry.from_recipe(_RECIPE, data=_DATA_ROOT).validate().passed is True


def test_random_materializes_at_chance(tmp_path: Path) -> None:
    instance = _materialize(tmp_path / "mf_cache")
    test_acc = instance.evaluation["test"]["accuracy"]
    # A chance baseline over 10 balanced classes hugs ~0.1 — well below any real
    # model. Generous band guards flakiness while staying sub-model.
    assert 0.03 <= test_acc <= 0.20, f"random baseline not at chance: {test_acc:.3f}"


def test_random_is_deterministic(tmp_path: Path) -> None:
    first = _materialize(tmp_path / "a")
    second = _materialize(tmp_path / "b")
    # FR-25: same (recipe, data, seed) -> byte-identical predictions.
    assert first.predictions.equals(second.predictions)
