# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the `ModelFoundry` / `ModelInstance` library API (FR-22, C.p)."""

from __future__ import annotations

import hashlib
import json
import textwrap
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest
import yaml

torch = pytest.importorskip("torch")

import datarefinery as dr  # noqa: E402
import pyarrow as pa  # noqa: E402
from datarefinery.pipeline.manifest import Manifest as DRManifest  # noqa: E402
from datarefinery.recipe.canonical import to_canonical_bytes  # noqa: E402
from datarefinery.recipe.loader import load as dr_load_recipe  # noqa: E402
from PIL import Image  # noqa: E402

from modelfoundry.core.config import RuntimeConfig  # noqa: E402
from modelfoundry.pipeline.data_binding import DataRefineryInstance  # noqa: E402

_CLASSES = ("c0", "c1", "c2")
_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def _build_instance(tmp_path: Path) -> DataRefineryInstance:
    dr_yaml = textwrap.dedent(
        """
        schema_version: 2
        plugin: image_classification
        seed: 1
        Input: {sources: [{name: t, type: image_folder, path: /x}]}
        Output:
          record_schema: {image: {dtype: uint8, shape: [4, 4, 3]}, label: {dtype: str},
                          path: {dtype: str}}
        Labels: {field: label, source: {kind: derived, derivation: parent_directory_name}}
        Transformations:
          - {name: norm, op: normalize}
        Splits: {ratios: {train: 0.6, val: 0.2, test: 0.2}, seed: 1, stratify_by: label}
        """
    ).strip()
    recipe_path = tmp_path / "dr_recipe.yml"
    recipe_path.write_text(dr_yaml, encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_path)
    recipe_hash = hashlib.sha256(to_canonical_bytes(dr_recipe)).hexdigest()

    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")
    stats_dir = inst / "fitted_statistics" / "norm"
    stats_dir.mkdir(parents=True)
    pq.write_table(pa.table({"value": [0.5, 0.3, 0.1]}), stats_dir / "mean.parquet")  # type: ignore[no-untyped-call]
    pq.write_table(pa.table({"value": [0.25, 0.5, 0.2]}), stats_dir / "std.parquet")  # type: ignore[no-untyped-call]

    dataset_dir = inst / "dataset"
    dataset_dir.mkdir()
    images_dir = inst / "images"
    images_dir.mkdir()
    counts: dict[str, int] = {}
    for split, per_class in (("train", 6), ("val", 2), ("test", 2)):
        records = []
        for cls in _CLASSES:
            for i in range(per_class):
                png = images_dir / f"{split}_{cls}_{i}.png"
                Image.new("RGB", (4, 4), _COLORS[cls]).save(png)
                records.append(
                    {"record_id": f"{split}/{cls}/img_{i}", "label": cls, "path": str(png)}
                )
        (dataset_dir / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
        counts[split] = len(records)

    manifest = DRManifest(
        datarefinery_version="0.19.0",
        plugin="image_classification",
        plugin_version="1",
        recipe_hash=recipe_hash,
        input_hash="0" * 64,
        seed=1,
        created_at=datetime.now(UTC),
        elapsed_seconds=0.1,
        record_counts=counts,
        warnings=[],
        sinks={},
        sinks_skipped={},
    )
    (inst / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    loaded = dr.Instance.load(inst)
    return DataRefineryInstance(
        path=inst,
        manifest=loaded.manifest,
        recipe=loaded.recipe,
        splits=tuple(loaded.manifest.record_counts.keys()),
        label_schema=loaded.recipe.Labels.model_dump(),
        record_schema={k: v.model_dump() for k, v in loaded.recipe.Output.record_schema.items()},
        fitted_statistics=loaded.fitted_statistics,
    )


def _write_recipe(tmp_path: Path) -> Path:
    recipe = {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "num_classes": 3,
            "layers": [{"op": "Flatten"}, {"op": "Linear", "in_features": 48, "out_features": 3}],
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {
            "max_epochs": 1,
            "batch_size": 4,
            "device": "cpu",
            "precision": "fp32",
            "checkpoint_cadence": 1,
        },
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1", "confusion_matrix", "calibration_curve"],
            "calibration_bins": 10,
        },
        "Visualizations": [
            {"op": "training_curves", "mode": "reporting"},
            {"op": "confusion_matrix", "mode": "reporting"},
        ],
    }
    path = tmp_path / "recipe.yml"
    path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    return path


# --- tests ---


def test_materialize_via_library_api_and_accessors(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    data = _build_instance(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    mf = ModelFoundry.from_recipe(_write_recipe(tmp_path), data=data, config=config)
    instance = mf.materialize()

    assert isinstance(instance, ModelInstance)
    assert "val" in instance.metrics
    assert "val" in instance.evaluation
    assert "val" in instance.confusion_matrix
    assert instance.confusion_matrix["val"].shape == (3, 3)
    assert instance.calibration is not None
    assert instance.predictions is not None and len(instance.predictions) == 6
    assert instance.trials is None
    assert instance.best_params is None
    assert "training_curves" in instance.figures
    assert instance.figures["training_curves"].startswith(b"\x89PNG")


def test_load_round_trip_predict_matches(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    data = _build_instance(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    mf = ModelFoundry.from_recipe(_write_recipe(tmp_path), data=data, config=config)
    instance = mf.materialize()

    x = np.random.default_rng(0).random((4, 4, 4, 3), dtype=np.float32)
    preds = instance.predict(x)
    proba = instance.predict_proba(x)

    reloaded = ModelInstance.load(instance.path)
    assert np.array_equal(preds, reloaded.predict(x))
    assert np.allclose(proba, reloaded.predict_proba(x))


def test_verbs_status_report_check_clean(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry

    data = _build_instance(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    mf = ModelFoundry.from_recipe(_write_recipe(tmp_path), data=data, config=config)

    assert mf.status()["materialized"] is False
    check = mf.check()
    assert check["plugin"] == "pytorch"
    assert check["health"].available is True

    mf.materialize()
    status = mf.status()
    assert status["materialized"] is True
    assert status["manifest"].plugin == "pytorch"

    assert "# ModelFoundry Report" in mf.report()
    assert mf.inspect().manifest.plugin == "pytorch"

    trashed = mf.clean()
    assert trashed is not None
    assert mf.status()["materialized"] is False


def test_top_level_materialize_and_reexports(tmp_path: Path) -> None:
    import modelfoundry
    from modelfoundry import ModelFoundry, ModelfoundryError, ModelInstance, materialize

    assert all(
        name in modelfoundry.__all__
        for name in ("ModelFoundry", "ModelInstance", "materialize", "ModelfoundryError")
    )
    assert issubclass(ModelfoundryError, Exception)
    assert ModelFoundry is not None

    data = _build_instance(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    instance = materialize(_write_recipe(tmp_path), data=data, config=config)
    assert isinstance(instance, ModelInstance)
    assert "val" in instance.metrics
