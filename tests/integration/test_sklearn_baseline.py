# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the sklearn MLPClassifier baseline (FR-24, Story C.m).

Discovers both plugins, then drives the sklearn baseline end-to-end over a
hand-built DataRefinery instance: build -> train -> evaluate -> round-trip, plus
feature parity with the PyTorch C.f path.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

torch = pytest.importorskip("torch")  # the C.f feature path the baseline reuses

import datarefinery as dr  # noqa: E402
import pyarrow as pa  # noqa: E402
from datarefinery.pipeline.manifest import Manifest as DRManifest  # noqa: E402
from datarefinery.recipe.canonical import to_canonical_bytes  # noqa: E402
from datarefinery.recipe.loader import load as dr_load_recipe  # noqa: E402
from PIL import Image  # noqa: E402

from modelfoundry.pipeline.data_binding import DataRefineryInstance  # noqa: E402
from modelfoundry.plugins.discovery import discover_plugins  # noqa: E402
from modelfoundry.plugins.sklearn.data import feature_matrix  # noqa: E402
from modelfoundry.plugins.sklearn.plugin import SklearnPlugin  # noqa: E402
from modelfoundry.recipe.models import EvaluationSpec, TrainingSpec  # noqa: E402

_CLASSES = ("c0", "c1", "c2")
_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}
_ARCH = {"type": "mlp_classifier", "num_classes": 3, "hidden_layer_sizes": [16], "max_iter": 50}


def _recipe_yaml() -> str:
    return textwrap.dedent(
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


def _build_instance(tmp_path: Path) -> DataRefineryInstance:
    recipe_path = tmp_path / "dr_recipe.yml"
    recipe_path.write_text(_recipe_yaml(), encoding="utf-8")
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


def _training() -> TrainingSpec:
    return TrainingSpec(
        max_epochs=1, batch_size=4, device="cpu", precision="fp32", checkpoint_cadence=1
    )


def _evaluation() -> EvaluationSpec:
    return EvaluationSpec(
        splits=["val", "test"],
        primary_metric="accuracy",
        metrics=["accuracy", "macro_f1", "confusion_matrix", "ece", "calibration_curve"],
        calibration_bins=10,
    )


# --- tests ---


def test_discovery_finds_both_plugins() -> None:
    plugins = discover_plugins()
    assert {"pytorch", "sklearn"} <= set(plugins)
    report = plugins["sklearn"].health_check()
    assert report.plugin == "sklearn"
    assert report.available is True
    assert report.accelerators == ("cpu",)


def test_baseline_materializes_end_to_end(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    plugin = SklearnPlugin()
    out = tmp_path / "instance"

    model = plugin.build_model(_ARCH)
    train_result = plugin.run_training(_training(), model, None, data, 7, out)  # type: ignore[arg-type]
    assert train_result.classes == ["c0", "c1", "c2"]
    assert train_result.weights_path.is_file()
    assert train_result.history_path.is_file()

    eval_result = plugin.run_evaluation(_evaluation(), model, data, out)
    assert "accuracy" in eval_result.metrics["val"]
    assert 0.0 <= eval_result.metrics["val"]["accuracy"] <= 1.0
    assert eval_result.predictions_path.is_file()
    assert eval_result.confusion_matrix_path is not None


def test_round_trip_predict_matches(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    plugin = SklearnPlugin()
    out = tmp_path / "instance"
    model = plugin.build_model(_ARCH)
    plugin.run_training(_training(), model, None, data, 7, out)  # type: ignore[arg-type]

    x, _, _ = feature_matrix(data, "val")
    preds_before = plugin.predict(model, x)
    proba_before = plugin.predict_proba(model, x)

    loaded = plugin.load_model(out / "model")
    preds_after = plugin.predict(loaded, x)
    proba_after = plugin.predict_proba(loaded, x)

    assert np.array_equal(preds_before, preds_after)
    assert np.allclose(proba_before, proba_after)


def test_training_is_deterministic(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    plugin = SklearnPlugin()

    def train_and_predict(run: str) -> np.ndarray:
        model = plugin.build_model(_ARCH)
        plugin.run_training(_training(), model, None, data, 7, tmp_path / run)  # type: ignore[arg-type]
        x, _, _ = feature_matrix(data, "val")
        return plugin.predict_proba(model, x)

    assert np.allclose(train_and_predict("a"), train_and_predict("b"))


def test_feature_matrix_parity_with_pytorch_path(tmp_path: Path) -> None:
    # The baseline's features are exactly the C.f normalized tensors, flattened.
    from modelfoundry.plugins.pytorch.data import DataRefineryDataset

    data = _build_instance(tmp_path)
    x, y, classes = feature_matrix(data, "val")
    ds = DataRefineryDataset(data, "val")
    assert classes == ["c0", "c1", "c2"]
    for i in range(len(ds)):
        tensor, label = ds[i]
        assert np.allclose(x[i], tensor.reshape(-1).numpy())
        assert y[i] == label


def test_build_model_rejects_wrong_type() -> None:
    from modelfoundry.core.errors import PluginError

    with pytest.raises(PluginError, match="mlp_classifier"):
        SklearnPlugin().build_model({"type": "resnet20", "num_classes": 3})
