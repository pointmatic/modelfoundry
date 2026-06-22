# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the materialize orchestrator (FR-3, Story C.o)."""

from __future__ import annotations

import hashlib
import json
import textwrap
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

torch = pytest.importorskip("torch")

import datarefinery as dr  # noqa: E402
import pyarrow as pa  # noqa: E402
from datarefinery.pipeline.manifest import Manifest as DRManifest  # noqa: E402
from datarefinery.recipe.canonical import to_canonical_bytes  # noqa: E402
from datarefinery.recipe.loader import load as dr_load_recipe  # noqa: E402
from PIL import Image  # noqa: E402

from modelfoundry.cache.identity import cache_key  # noqa: E402
from modelfoundry.cache.layout import CachePaths  # noqa: E402
from modelfoundry.core.config import RuntimeConfig  # noqa: E402
from modelfoundry.core.errors import ExpectationError  # noqa: E402
from modelfoundry.pipeline.data_binding import DataRefineryInstance  # noqa: E402
from modelfoundry.pipeline.runner import MaterializeRunner  # noqa: E402
from modelfoundry.plugins.discovery import discover_plugins  # noqa: E402
from modelfoundry.recipe.models import (  # noqa: E402
    DataSpec,
    EvaluationSpec,
    ExpectationSpec,
    LossSpec,
    ModelRecipe,
    OptimizationSpec,
    OptimizerSpec,
    SearchSpaceSpec,
    TrainingSpec,
    VisualizationSpec,
)

_CLASSES = ("c0", "c1", "c2")
_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}


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


def _recipe(
    *,
    optimization: OptimizationSpec | None = None,
    expectations: list[ExpectationSpec] | None = None,
    eval_splits: list[str] | None = None,
    visualizations: list[VisualizationSpec] | None = None,
) -> ModelRecipe:
    return ModelRecipe(
        schema_version=1,
        plugin="pytorch",
        seed=7,
        Data=DataSpec(recipe=Path("dr_recipe.yml")),
        Architecture={
            "num_classes": 3,
            "layers": [{"op": "Flatten"}, {"op": "Linear", "in_features": 48, "out_features": 3}],
        },
        Loss=LossSpec(op="cross_entropy"),
        Optimizer=OptimizerSpec(op="adamw", learning_rate=0.01),
        Training=TrainingSpec(
            max_epochs=1, batch_size=4, device="cpu", precision="fp32", checkpoint_cadence=1
        ),
        Optimization=optimization,
        Evaluation=EvaluationSpec(
            splits=["val"] if eval_splits is None else eval_splits,
            primary_metric="accuracy",
            metrics=["accuracy", "macro_f1", "confusion_matrix"],
            calibration_bins=10,
        ),
        Visualizations=visualizations or [],
        OutputExpectations=expectations or [],
    )


def _config(tmp_path: Path) -> RuntimeConfig:
    return RuntimeConfig(cache_root=tmp_path / "mf_cache", data_cache_root=tmp_path)


def _instance_dir(recipe: ModelRecipe, data: DataRefineryInstance, config: RuntimeConfig) -> Path:
    dm = data.manifest
    key = cache_key(recipe, (dm.recipe_hash, dm.input_hash, int(dm.seed)), recipe.seed)
    return CachePaths(config.cache_root, key).instance_dir


def _run(recipe: ModelRecipe, data: DataRefineryInstance, config: RuntimeConfig) -> Any:
    plugin = discover_plugins()["pytorch"]
    return MaterializeRunner(
        recipe=recipe, data_instance=data, plugin=plugin, runtime_config=config
    ).run()


# --- tests ---


def test_full_materialize_produces_complete_instance(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    config = _config(tmp_path)
    recipe = _recipe(
        visualizations=[
            VisualizationSpec(op="training_curves", mode="reporting"),
            VisualizationSpec(op="confusion_matrix", mode="reporting"),
        ],
    )
    manifest = _run(recipe, data, config)

    inst = _instance_dir(recipe, data, config)
    assert (inst / "manifest.json").is_file()
    assert (inst / "training" / "history.parquet").is_file()
    assert (inst / "model" / "architecture.json").is_file()
    assert (inst / "model" / "weights" / "state_dict.pt").is_file()
    assert (inst / "model" / "summary.txt").is_file()
    summary = json.loads((inst / "model" / "summary.json").read_text())
    assert summary["total_params"] > 0 and summary["input_size"] == [1, 3, 4, 4]
    assert (inst / "evaluation" / "metrics.json").is_file()
    assert (inst / "evaluation" / "predictions.parquet").is_file()
    assert (inst / "report" / "report.md").is_file()
    assert (inst / "report" / "visualizations" / "training_curves.png").is_file()

    assert manifest.plugin == "pytorch"
    assert "val" in manifest.evaluation
    assert manifest.elapsed_seconds > 0
    assert manifest.optimization is None
    assert "## Stages" in (inst / "report" / "report.md").read_text()


def test_materialize_with_optimization(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    config = _config(tmp_path)
    recipe = _recipe(
        optimization=OptimizationSpec(
            sampler="tpe",
            pruner="none",
            n_trials=2,
            baseline_trial="enqueue_recipe_defaults",
            max_epochs_per_trial=1,
            search_space={"Optimizer.learning_rate": SearchSpaceSpec(log_uniform=[1e-4, 1e-2])},
        ),
    )
    manifest = _run(recipe, data, config)

    inst = _instance_dir(recipe, data, config)
    assert manifest.optimization is not None
    assert manifest.optimization.sampler == "tpe"
    assert manifest.optimization.n_trials == 2
    assert (inst / "optimization" / "best-params.json").is_file()


def test_failed_expectation_aborts_without_promote(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    config = _config(tmp_path)
    recipe = _recipe(
        expectations=[ExpectationSpec(metric="accuracy", split="val", op="gte", value=1.5)],
    )
    with pytest.raises(ExpectationError, match="output expectations failed"):
        _run(recipe, data, config)

    # Not promoted; a FAILED marker is left under the temp area for diagnosis.
    assert not _instance_dir(recipe, data, config).exists()
    failed = list((config.cache_root / "instances" / ".tmp").glob("*/FAILED"))
    assert failed, "expected a FAILED marker in the temp dir"
    payload = json.loads(failed[0].read_text())
    assert payload["stage"] == "output_expectations"
    assert payload["error_class"] == "ExpectationError"


def test_evaluation_skipped_when_no_splits(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    config = _config(tmp_path)
    recipe = _recipe(eval_splits=[])
    manifest = _run(recipe, data, config)

    assert manifest.evaluation == {}
    inst = _instance_dir(recipe, data, config)
    assert (inst / "manifest.json").is_file()
    assert not (inst / "evaluation" / "metrics.json").exists()


def test_existing_instance_blocks_without_overwrite(tmp_path: Path) -> None:
    from modelfoundry.core.errors import ModelArtifactExistsError

    data = _build_instance(tmp_path)
    config = _config(tmp_path)
    recipe = _recipe()
    _run(recipe, data, config)

    with pytest.raises(ModelArtifactExistsError):
        _run(recipe, data, config)
