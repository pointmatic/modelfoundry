# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Phase E capstone — downsized CIFAR-10 end-to-end smoke (Story E.l, TR-12 / AC-2).

Materializes the `cifar10_smoke.yml` recipe (a real Optuna study + a multi-epoch
`simple_cnn` fit + evaluation on val/test) over the synthesized, CPU-budget
CIFAR-10-shaped instance, then asserts every contract surface: the val `macro_f1`
clears the documented floor, all `OutputExpectations` pass, the persisted
`predictions.parquet` has the expected shape, and the FR-23 from-disk
`ModelInstance.load(path).predict(X)` round-trip is stable. The whole run fits a
free-tier CI runner's per-job CPU budget (PE-3) — ~5s locally.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from datarefinery_instances.cifar10_smoke.builder import (  # type: ignore[import-not-found]
    build_cifar10_smoke_instance,
)

from modelfoundry.core.config import RuntimeConfig

torch = pytest.importorskip("torch")

_RECIPE = "tests/fixtures/recipes/cifar10_smoke.yml"
# The OutputExpectations floor declared in the recipe; the observed val macro_f1
# on the trivially-separable 10-colour palette is ~1.0.
_MACRO_F1_FLOOR = 0.80
_NUM_CLASSES = 10
_EVAL_ROWS = 200  # 100 val + 100 test


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def test_cifar10_smoke_materializes_end_to_end(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    data = build_cifar10_smoke_instance(tmp_path / "dr")
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    instance = ModelFoundry.from_recipe(_RECIPE, data=data, config=config).materialize()
    assert isinstance(instance, ModelInstance)

    # 1) The model genuinely learned — val macro_f1 clears the documented floor.
    val_macro_f1 = instance.evaluation["val"]["macro_f1"]
    assert val_macro_f1 >= _MACRO_F1_FLOOR

    # 2) Every declared OutputExpectation passed (so the instance promoted, not FAILED).
    outcomes = instance.manifest.output_expectations
    assert outcomes and all(o.passed for o in outcomes)

    # 3) The Optuna study ran (2 trials) and its best params were persisted.
    assert instance.best_params is not None
    assert instance.trials is not None and len(instance.trials) == 2

    # 4) predictions.parquet has the expected rows + columns over both eval splits.
    predictions = instance.predictions
    assert len(predictions) == _EVAL_ROWS
    assert sorted(predictions["split"].unique().tolist()) == ["test", "val"]
    expected_columns = {"split", "record_id", "true_label", "pred_label"} | {
        f"pred_proba_c{i}" for i in range(_NUM_CLASSES)
    }
    assert expected_columns <= set(predictions.columns)

    # 5) FR-23 from-disk round-trip: a reloaded instance predicts identically.
    x = np.random.default_rng(0).random((4, 32, 32, 3), dtype=np.float32)
    preds = instance.predict(x)
    assert preds.shape == (4,)
    reloaded = ModelInstance.load(instance.path)
    assert np.array_equal(preds, reloaded.predict(x))
    assert np.allclose(instance.predict_proba(x), reloaded.predict_proba(x))
