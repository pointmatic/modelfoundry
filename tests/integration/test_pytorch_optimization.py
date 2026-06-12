# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the PyTorch Optuna optimization stage (FR-11, Story C.i).

Runs a small TPE study over a hand-built DataRefinery instance: baseline-trial
enqueue, deterministic reruns, `trials.parquet` / `best-params.json` persistence,
and the `apply_params` merge-back of `batch_size` + `patience`.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("optuna")

import datarefinery as dr  # noqa: E402
import pyarrow as pa  # noqa: E402
from datarefinery.pipeline.manifest import Manifest as DRManifest  # noqa: E402
from datarefinery.recipe.canonical import to_canonical_bytes  # noqa: E402
from datarefinery.recipe.loader import load as dr_load_recipe  # noqa: E402
from PIL import Image  # noqa: E402

from modelfoundry.pipeline.data_binding import DataRefineryInstance  # noqa: E402
from modelfoundry.plugins.pytorch.optimization import run_optimization  # noqa: E402
from modelfoundry.recipe.models import (  # noqa: E402
    DataSpec,
    EarlyStoppingSpec,
    EvaluationSpec,
    LossSpec,
    ModelRecipe,
    OptimizationSpec,
    OptimizerSpec,
    ScheduleSpec,
    SearchSpaceSpec,
    TrainingSpec,
)
from modelfoundry.recipe.search_space import apply_params  # noqa: E402

_CLASSES = ("c0", "c1", "c2")
_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}
_SEED = 11


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


def _recipe() -> ModelRecipe:
    return ModelRecipe(
        schema_version=1,
        plugin="pytorch",
        seed=_SEED,
        Data=DataSpec(recipe=Path("dr_recipe.yml")),
        Architecture={
            "num_classes": 3,
            "layers": [{"op": "Flatten"}, {"op": "Linear", "in_features": 48, "out_features": 3}],
        },
        Loss=LossSpec(op="cross_entropy"),
        Optimizer=OptimizerSpec(
            op="adamw",
            learning_rate=0.01,
            schedule=ScheduleSpec(op="reduce_on_plateau", monitor="val_loss"),
        ),
        Training=TrainingSpec(
            max_epochs=4,
            batch_size=2,
            num_workers=0,
            device="cpu",
            checkpoint_cadence=1,
            early_stopping=EarlyStoppingSpec(monitor="val_loss", mode="min", patience=2),
        ),
        Optimization=OptimizationSpec(
            sampler="tpe",
            pruner="none",
            n_trials=3,
            baseline_trial="enqueue_recipe_defaults",
            max_epochs_per_trial=2,
            search_space={
                "Optimizer.learning_rate": SearchSpaceSpec(log_uniform=[1e-4, 1e-2]),
                "Training.batch_size": SearchSpaceSpec(categorical=[2, 4]),
                "Training.early_stopping.patience": SearchSpaceSpec(int=[2, 4]),
            },
        ),
        Evaluation=EvaluationSpec(splits=["val"], primary_metric="accuracy", metrics=["accuracy"]),
    )


def _params_columns(trials_parquet: Path) -> dict[str, list[object]]:
    frame = pq.read_table(trials_parquet).to_pandas()  # type: ignore[no-untyped-call]
    param_cols = [c for c in frame.columns if c.startswith("params_")]
    return {c: frame[c].tolist() for c in param_cols}


# --- tests ---


def test_optimization_persists_artifacts_and_best_params(tmp_path: Path) -> None:
    recipe = _recipe()
    result = run_optimization(
        recipe.Optimization, recipe, _build_instance(tmp_path), _SEED, tmp_path  # type: ignore[arg-type]
    )

    opt_dir = tmp_path / "optimization"
    assert (opt_dir / "study.db").is_file()
    assert (opt_dir / "trials.parquet").is_file()
    assert (opt_dir / "best-params.json").is_file()

    assert result.n_trials == 3
    assert set(result.best_params) <= set(recipe.Optimization.search_space)  # type: ignore[union-attr]
    assert isinstance(result.best_value, float)
    assert result.direction == "maximize"  # accuracy
    assert json.loads((opt_dir / "best-params.json").read_text()) == result.best_params


def test_baseline_trial_uses_recipe_defaults(tmp_path: Path) -> None:
    recipe = _recipe()
    run_optimization(recipe.Optimization, recipe, _build_instance(tmp_path), _SEED, tmp_path)  # type: ignore[arg-type]

    cols = _params_columns(tmp_path / "optimization" / "trials.parquet")
    # Trial 0 is the enqueued baseline = the recipe defaults.
    assert cols["params_Training.batch_size"][0] == 2
    assert cols["params_Training.early_stopping.patience"][0] == 2
    assert cols["params_Optimizer.learning_rate"][0] == pytest.approx(0.01)


def test_study_is_deterministic_across_reruns(tmp_path: Path) -> None:
    recipe = _recipe()
    data = _build_instance(tmp_path)
    run_a = tmp_path / "a"
    run_b = tmp_path / "b"
    result_a = run_optimization(recipe.Optimization, recipe, data, _SEED, run_a)  # type: ignore[arg-type]
    result_b = run_optimization(recipe.Optimization, recipe, data, _SEED, run_b)  # type: ignore[arg-type]

    assert result_a.best_params == result_b.best_params
    assert result_a.best_value == pytest.approx(result_b.best_value)
    assert _params_columns(run_a / "optimization" / "trials.parquet") == _params_columns(
        run_b / "optimization" / "trials.parquet"
    )


def test_best_params_merge_back_takes_effect(tmp_path: Path) -> None:
    recipe = _recipe()
    result = run_optimization(
        recipe.Optimization, recipe, _build_instance(tmp_path), _SEED, tmp_path  # type: ignore[arg-type]
    )

    merged = apply_params(recipe, result.best_params)
    assert merged.Training.batch_size in {2, 4}
    assert merged.Training.early_stopping is not None
    assert merged.Training.early_stopping.patience in {2, 3, 4}
    assert 1e-4 <= merged.Optimizer.model_extra["learning_rate"] <= 1e-2  # type: ignore[index]
