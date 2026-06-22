# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the PyTorch evaluation stage (FR-12 / FR-22, Story C.j).

Evaluates a (deterministically initialized) model over a hand-built DataRefinery
instance and cross-checks every torchmetrics value against sklearn computed from
the persisted `predictions.parquet` — sklearn is the golden reference.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torchmetrics")

import datarefinery as dr  # noqa: E402
import pyarrow as pa  # noqa: E402
import sklearn.metrics as skm  # type: ignore[import-untyped]  # noqa: E402
from datarefinery.pipeline.manifest import Manifest as DRManifest  # noqa: E402
from datarefinery.recipe.canonical import to_canonical_bytes  # noqa: E402
from datarefinery.recipe.loader import load as dr_load_recipe  # noqa: E402
from PIL import Image  # noqa: E402

from modelfoundry.pipeline.data_binding import DataRefineryInstance  # noqa: E402
from modelfoundry.pipeline.seeding import derive_seed  # noqa: E402
from modelfoundry.plugins.pytorch.architecture import build_model  # noqa: E402
from modelfoundry.plugins.pytorch.determinism import (  # noqa: E402
    enable_deterministic_algorithms,
)
from modelfoundry.plugins.pytorch.evaluation import run_evaluation  # noqa: E402
from modelfoundry.recipe.models import EvaluationSpec  # noqa: E402

_CLASSES = ("c0", "c1", "c2")
_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}
_ALL_METRICS = [
    "accuracy",
    "macro_f1",
    "per_class_f1",
    "per_class_precision",
    "per_class_recall",
    "confusion_matrix",
    "ece",
    "calibration_curve",
]


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


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
    for split, per_class in (("train", 4), ("val", 2), ("test", 2)):
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


def _model() -> Any:
    enable_deterministic_algorithms(derive_seed(7, "weight_init"))
    return build_model(
        {
            "num_classes": 3,
            "layers": [{"op": "Flatten"}, {"op": "Linear", "in_features": 48, "out_features": 3}],
        }
    )


def _eval_spec(metrics: list[str] | None = None, **kw: object) -> EvaluationSpec:
    return EvaluationSpec(
        splits=["val", "test"],
        primary_metric="accuracy",
        metrics=metrics if metrics is not None else _ALL_METRICS,
        calibration_bins=10,
        **kw,
    )


# --- tests ---


def test_metrics_match_sklearn_golden(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    result = run_evaluation(_eval_spec(), _model(), data, out)

    frame = pq.read_table(out / "evaluation" / "predictions.parquet").to_pandas()  # type: ignore[no-untyped-call]
    classes = list(_CLASSES)
    for split in ("val", "test"):
        sub = frame[frame["split"] == split]
        y_true = sub["true_label"].tolist()
        y_pred = sub["pred_label"].tolist()
        m = result.metrics[split]

        assert m["accuracy"] == pytest.approx(skm.accuracy_score(y_true, y_pred))
        assert m["macro_f1"] == pytest.approx(
            skm.f1_score(y_true, y_pred, labels=classes, average="macro", zero_division=0)
        )
        assert m["per_class_f1"] == pytest.approx(
            list(skm.f1_score(y_true, y_pred, labels=classes, average=None, zero_division=0))
        )
        assert m["per_class_precision"] == pytest.approx(
            list(skm.precision_score(y_true, y_pred, labels=classes, average=None, zero_division=0))
        )
        assert m["per_class_recall"] == pytest.approx(
            list(skm.recall_score(y_true, y_pred, labels=classes, average=None, zero_division=0))
        )
        assert (
            m["confusion_matrix"] == skm.confusion_matrix(y_true, y_pred, labels=classes).tolist()
        )
        assert 0.0 <= m["ece"] <= 1.0


def test_predictions_columns_and_row_count(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    run_evaluation(_eval_spec(), _model(), data, out)

    frame = pq.read_table(out / "evaluation" / "predictions.parquet").to_pandas()  # type: ignore[no-untyped-call]
    assert list(frame.columns) == [
        "split",
        "record_id",
        "true_label",
        "pred_label",
        "pred_proba_c0",
        "pred_proba_c1",
        "pred_proba_c2",
    ]
    assert len(frame) == 12  # val (6) + test (6)
    # Per-row probabilities sum to 1.0 (softmax).
    proba = frame[["pred_proba_c0", "pred_proba_c1", "pred_proba_c2"]].to_numpy()
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5)


def test_confusion_and_calibration_artifacts(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    result = run_evaluation(_eval_spec(), _model(), data, out)

    assert result.confusion_matrix_path is not None
    npz = np.load(result.confusion_matrix_path)
    assert set(npz.files) == {"val", "test"}
    assert npz["val"].shape == (3, 3)
    assert int(npz["val"].sum()) == 6  # val rows

    assert result.calibration_path is not None
    cal = pq.read_table(result.calibration_path).to_pandas()  # type: ignore[no-untyped-call]
    assert list(cal.columns) == [
        "split",
        "bin_lower",
        "bin_upper",
        "mean_confidence",
        "accuracy",
        "count",
    ]
    assert set(cal["split"]) <= {"val", "test"}


def test_metrics_json_shape_feeds_expectations(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    run_evaluation(_eval_spec(metrics=["accuracy", "macro_f1"]), _model(), data, out)

    payload = json.loads((out / "evaluation" / "metrics.json").read_text())
    assert set(payload) == {"val", "test"}
    assert set(payload["val"]) == {"accuracy", "macro_f1"}
    assert isinstance(payload["val"]["accuracy"], float)


def test_baseline_comparison_emits_warning(tmp_path: Path) -> None:
    from modelfoundry.recipe.models import ComparisonSpec

    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    spec = _eval_spec(
        metrics=["accuracy"], comparison=ComparisonSpec(baseline_model_id="sklearn-mlp")
    )
    result = run_evaluation(spec, _model(), data, out)
    assert any("sklearn-mlp" in w for w in result.warnings)
