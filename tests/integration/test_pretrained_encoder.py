# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end smoke for the pretrained-encoder path (Story H.j.1, R1.1/R1.3/R1.5).

Materializes an `Encoder` -> `Pooling` -> `Head` recipe over a synthetic
DataRefinery instance authored at the encoder's native 224x224 resolution, then
asserts the run produces a `ModelInstance` (criterion 1) and reproduces offline
across two fresh-cache materializes (criterion 2). Weights load from the OFFLINE
warm HF cache (no network).

Gated on `torch` + `transformers`: skips in `testenv` / `smoke-pytorch`, runs in
`smoke-huggingface`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from datarefinery_instances.builder import (  # type: ignore[import-not-found]
    build_dr_instance,
)

from modelfoundry.core.config import RuntimeConfig

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

_RECIPE = "tests/fixtures/recipes/pretrained_encoder_smoke.yml"
_IMG = 224  # the tiny-ViT's native input resolution
_CLASSES = ("c0", "c1", "c2")


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def _instance(root: Path) -> Any:
    return build_dr_instance(
        root,
        classes=_CLASSES,
        split_counts={"train": 12, "val": 6},
        image_size=_IMG,
        seed=7,
    )


def test_pretrained_encoder_materializes_end_to_end(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    data = _instance(tmp_path / "dr")
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    instance = ModelFoundry.from_recipe(_RECIPE, data=data, config=config).materialize()

    assert isinstance(instance, ModelInstance)
    # The encoder path trained + evaluated: val metrics are present and finite.
    val_acc = instance.evaluation["val"]["accuracy"]
    assert 0.0 <= val_acc <= 1.0
    # predictions.parquet covers the val split with one row per evaluated record.
    predictions = instance.predictions
    assert len(predictions) == 6
    assert predictions["split"].unique().tolist() == ["val"]


def test_pretrained_encoder_offline_run_reproduces(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry

    # Two fresh-cache materializes of the same (recipe, data, seed) → identical
    # offline result (R1.5 / criterion 2): frozen encoder + seeded head, cpu,
    # deterministic mode, num_workers=0.
    data_a = _instance(tmp_path / "dr_a")
    data_b = _instance(tmp_path / "dr_b")
    config_a = RuntimeConfig(cache_root=tmp_path / "cache_a")
    config_b = RuntimeConfig(cache_root=tmp_path / "cache_b")

    inst_a = ModelFoundry.from_recipe(_RECIPE, data=data_a, config=config_a).materialize()
    inst_b = ModelFoundry.from_recipe(_RECIPE, data=data_b, config=config_b).materialize()

    assert inst_a.evaluation["val"]["accuracy"] == inst_b.evaluation["val"]["accuracy"]
    assert inst_a.evaluation["val"]["macro_f1"] == inst_b.evaluation["val"]["macro_f1"]


def _check(report: object, check_id: int) -> object:
    [check] = [c for c in report.checks if c.id == check_id]  # type: ignore[attr-defined]
    return check


def test_input_contract_flags_resolution_mismatch(tmp_path: Path) -> None:
    # Story H.j.3: a CIFAR-32 instance against the ViT-224 encoder fails validate's
    # input-shape contract (check 21) with an actionable message — caught before
    # the expensive materialize, not as a deep forward-pass crash.
    from modelfoundry import ModelFoundry

    data = build_dr_instance(
        tmp_path / "dr32", classes=_CLASSES, split_counts={"train": 6, "val": 3}, image_size=32
    )
    report = ModelFoundry.from_recipe(_RECIPE, data=data).validate()
    check = _check(report, 21)
    assert not check.passed  # type: ignore[attr-defined]
    assert "224" in (check.message or "")  # type: ignore[attr-defined]


def test_input_contract_passes_at_native_resolution(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry

    data = _instance(tmp_path / "dr224")  # 224x224, the encoder's native size
    report = ModelFoundry.from_recipe(_RECIPE, data=data).validate()
    assert _check(report, 21).passed  # type: ignore[attr-defined]


_LORA_RECIPE = "tests/fixtures/recipes/pretrained_encoder_lora_smoke.yml"


def test_lora_instance_materializes_and_round_trips_from_disk(tmp_path: Path) -> None:
    # Story H.k / criterion 9: a persisted LoRA ModelInstance reloads from disk
    # alone (base re-fetched from the warm cache + adapter/head deltas) and
    # reproduces predictions with no external config object.
    import numpy as np

    from modelfoundry import ModelFoundry, ModelInstance

    data = _instance(tmp_path / "dr")
    config = RuntimeConfig(cache_root=tmp_path / "cache")
    instance = ModelFoundry.from_recipe(_LORA_RECIPE, data=data, config=config).materialize()
    assert isinstance(instance, ModelInstance)

    x = np.random.default_rng(0).random((3, _IMG, _IMG, 3), dtype=np.float32)
    preds = instance.predict(x)
    proba = instance.predict_proba(x)

    reloaded = ModelInstance.load(instance.path)
    assert np.array_equal(preds, reloaded.predict(x))
    assert np.allclose(proba, reloaded.predict_proba(x))


def test_frozen_encoder_instance_round_trips_from_disk(tmp_path: Path) -> None:
    # Story H.l / criterion 9: the non-LoRA frozen-encoder composite also persists
    # base-from-cache + head/pooling deltas and reproduces predictions from disk.
    import numpy as np

    from modelfoundry import ModelFoundry, ModelInstance

    data = _instance(tmp_path / "dr")
    config = RuntimeConfig(cache_root=tmp_path / "cache")
    instance = ModelFoundry.from_recipe(_RECIPE, data=data, config=config).materialize()

    x = np.random.default_rng(1).random((3, _IMG, _IMG, 3), dtype=np.float32)
    preds = instance.predict(x)
    reloaded = ModelInstance.load(instance.path)
    assert np.array_equal(preds, reloaded.predict(x))
    assert np.allclose(instance.predict_proba(x), reloaded.predict_proba(x))
