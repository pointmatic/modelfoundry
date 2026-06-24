# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end deliverable test — CIFAR-10 / ResNet-20 (Story C.r, FR-3 / FR-22).

Materializes the downsized fixture recipe (`tests/fixtures/recipes/
cifar10_resnet20.yml` — 2 Optuna trials of 1 epoch each + 2 final epochs) over
the **real** materialized DataRefinery DR-1 instance (1,700 / 300 / 1,000), and
asserts the full ModelInstance surface: the torchinfo summary pins ResNet-20's
272,474 params, the Optuna study persists `best-params.json` and the final
training applies them, val/test accuracy are computed, and the FR-23 from-disk
`load().predict()` round-trip is byte-stable.

This is the real-shape client deliverable test, distinct from E.l's downsized CI
smoke. It binds the real instance via DataRefinery's blessed `resolve_instance`
(vendor-dep-spec § "Resolving a materialized instance"), so it **skips** cleanly
on a host where the DR-1 instance has not been materialized under `./data`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

torch = pytest.importorskip("torch")

import datarefinery as dr  # noqa: E402

from modelfoundry.core.config import RuntimeConfig  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DELIVERABLE = "recipes/cifar10_resnet20.yml"
_FIXTURE = "tests/fixtures/recipes/cifar10_resnet20.yml"
_DR_RECIPE = "recipes/cifar10-base.yaml"
_DATA_ROOT = "data"
_RESNET20_PARAMS = 272_474


@pytest.fixture(autouse=True)
def _repo_root_cwd_and_determinism(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Both the recipe's relative `Data.recipe` and DataRefinery's input hashing
    # resolve against the cwd, so pin it to the repo root regardless of where
    # pytest was invoked.
    monkeypatch.chdir(_REPO_ROOT)
    yield
    torch.use_deterministic_algorithms(False)


def _require_dr1_instance() -> None:
    status = dr.resolve_instance(_DR_RECIPE, cache_root=_DATA_ROOT, seed=None, overlays=None)
    if status.cache_status != "hit":
        pytest.skip(
            f"DR-1 CIFAR-10 instance not materialized under ./{_DATA_ROOT} "
            f"(cache_status={status.cache_status}); materialize it to run this deliverable test"
        )


def _dotted_get(node: Any, dotted: str) -> Any:
    cursor = node
    for part in dotted.split("."):
        cursor = cursor[part]
    return cursor


# --- the deliverable e2e ---


def test_cifar10_resnet20_materializes_end_to_end(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    _require_dr1_instance()
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    mf = ModelFoundry.from_recipe(_FIXTURE, data=_DATA_ROOT, config=config)
    instance = mf.materialize()

    assert isinstance(instance, ModelInstance)

    # 1) torchinfo summary pins the ResNet-20 totals (FR-27 / C.q).
    assert instance.summary is not None
    assert instance.summary["total_params"] == _RESNET20_PARAMS
    assert instance.summary_text is not None
    assert "Total params: 272,474" in instance.summary_text

    # 2) the Optuna study ran and persisted its best params (FR-3 / C.i).
    assert instance.best_params is not None
    assert set(instance.best_params) == {
        "Optimizer.learning_rate",
        "Optimizer.weight_decay",
        "Training.batch_size",
        "Training.early_stopping.patience",
    }
    assert instance.trials is not None and len(instance.trials) == 2
    assert (instance.path / "optimization" / "best-params.json").is_file()

    # 3) final training applied the best params — the persisted (post-merge) recipe
    #    carries each best value at its dotted search-space path (auto-composition).
    import yaml

    persisted = yaml.safe_load((instance.path / "recipe.yml").read_text(encoding="utf-8"))
    for path, value in instance.best_params.items():
        assert _dotted_get(persisted, path) == pytest.approx(value)

    # 4) val + test accuracy are computed over the real splits.
    for split in ("val", "test"):
        acc = instance.evaluation[split]["accuracy"]
        assert isinstance(acc, float)
        assert 0.0 <= acc <= 1.0

    # 4b) learning-floor guard (H.a): the model must actually learn from the training
    #     data. The normalization-units bug fed it near-constant inputs, pinning
    #     train_loss at the ln(10) ≈ 2.303 chance floor (test accuracy 0.10). A healthy
    #     run drops train_loss well below that within the fixture's epoch budget. This
    #     is the precise inverse of the bug signature; a test-accuracy floor is avoided
    #     because generalization on the 1,700-image subset is confounded by overfitting.
    import pandas as pd  # type: ignore[import-untyped]

    history = pd.read_parquet(instance.path / "training" / "history.parquet")
    assert history["train_loss"].min() < 2.2, history["train_loss"].tolist()

    # report figures rendered (now that C.q.2 registered the viz ops, these also validate).
    assert "training_curves" in instance.figures
    assert "confusion_matrix" in instance.figures

    # 5) FR-23 from-disk round-trip: a reloaded instance predicts identically.
    x = np.random.default_rng(0).random((4, 32, 32, 3), dtype=np.float32)
    preds = instance.predict(x)
    proba = instance.predict_proba(x)
    assert preds.shape == (4,)
    assert proba.shape == (4, 10)

    reloaded = ModelInstance.load(instance.path)
    assert np.array_equal(preds, reloaded.predict(x))
    assert np.allclose(proba, reloaded.predict_proba(x))


# --- the deliverable recipe itself is well-formed (fast; no training) ---


def test_summary_inspects_architecture_without_training() -> None:
    """`summary()` reports ResNet-20 structure without training (H.a.2).

    Param count + output shape from the public surface — no `materialize()`, no
    framework import in caller code.
    """
    from modelfoundry import ModelFoundry

    _require_dr1_instance()
    mf = ModelFoundry.from_recipe(_DELIVERABLE, data=_DATA_ROOT)
    summary = mf.summary()

    assert summary["total_params"] == _RESNET20_PARAMS
    assert summary["output_shape"][-1] == 10


def test_deliverable_recipe_validates_clean() -> None:
    # The full 20-check FR-2 validator passes for the deliverable and every
    # variant. Bind the DR-1 instance ONCE (the `Data:` block is variant-
    # independent) and reuse it, so the ~3,000-image input hash isn't repeated.
    from modelfoundry import ModelFoundry
    from modelfoundry.pipeline.data_binding import resolve_data_instance
    from modelfoundry.recipe.loader import load_recipe

    _require_dr1_instance()
    base = load_recipe(_DELIVERABLE)
    data = resolve_data_instance(base.Data, RuntimeConfig(data_cache_root=Path(_DATA_ROOT)))

    for overlay in (None, "cosine", "sgd_momentum", "cpu_budget"):
        overlays = [overlay] if overlay else None
        mf = ModelFoundry.from_recipe(_DELIVERABLE, data=data, overlays=overlays)
        report = mf.validate()
        assert report.passed, (overlay, [(c.id, c.name, c.message) for c in report.failures])


def test_deliverable_overlays_flip_optimizer_and_schedule() -> None:
    from modelfoundry.recipe.loader import load_recipe

    base = load_recipe(_DELIVERABLE)
    assert base.Optimizer is not None
    assert base.Optimizer.op == "adamw"
    assert base.Optimizer.schedule is not None and base.Optimizer.schedule.op == "reduce_on_plateau"

    sgd = load_recipe(_DELIVERABLE, overlays=["sgd_momentum"])
    assert sgd.Optimizer is not None
    assert sgd.Optimizer.op == "sgd"
    assert (sgd.Optimizer.model_extra or {})["momentum"] == pytest.approx(0.9)

    cosine = load_recipe(_DELIVERABLE, overlays=["cosine"])
    assert cosine.Optimizer is not None
    assert cosine.Optimizer.schedule is not None and cosine.Optimizer.schedule.op == "cosine"

    budget = load_recipe(_DELIVERABLE, overlays=["cpu_budget"])
    assert budget.Optimization is not None and budget.Optimization.n_trials == 8
    assert budget.Training.max_epochs == 15
