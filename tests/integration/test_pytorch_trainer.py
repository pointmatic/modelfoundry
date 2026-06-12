# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the PyTorch trainer (FR-10, Story C.h).

Binds a hand-built DataRefinery instance via a real `datarefinery.Instance.load`,
constructs a tiny explicit-layer model, and runs `run_training` end-to-end:
history + checkpoints + best-weight promotion, and byte-identical reruns under a
fixed seed.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

torch = pytest.importorskip("torch")

import datarefinery as dr  # noqa: E402
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
from modelfoundry.plugins.pytorch.trainer import run_training  # noqa: E402
from modelfoundry.recipe.models import (  # noqa: E402
    DataSpec,
    EarlyStoppingSpec,
    EvaluationSpec,
    LossSpec,
    ModelRecipe,
    OptimizerSpec,
    ScheduleSpec,
    TrainingSpec,
)

_CLASSES = ("c0", "c1", "c2")
_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}
_SEED = 7


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    """Keep this test's global deterministic-mode toggle from leaking to others."""
    yield
    torch.use_deterministic_algorithms(False)


# --- fixture instance ---


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


def _recipe(*, loss: str = "cross_entropy", max_epochs: int = 3, patience: int = 10) -> ModelRecipe:
    return ModelRecipe(
        schema_version=1,
        plugin="pytorch",
        seed=_SEED,
        Data=DataSpec(recipe=Path("dr_recipe.yml")),
        Architecture={
            "num_classes": 3,
            "layers": [{"op": "Flatten"}, {"op": "Linear", "in_features": 48, "out_features": 3}],
        },
        Loss=LossSpec(op=loss),
        Optimizer=OptimizerSpec(
            op="adamw",
            learning_rate=0.01,
            schedule=ScheduleSpec(op="reduce_on_plateau", monitor="val_loss"),
        ),
        Training=TrainingSpec(
            max_epochs=max_epochs,
            batch_size=2,
            num_workers=0,
            device="cpu",
            checkpoint_cadence=1,
            early_stopping=EarlyStoppingSpec(monitor="val_loss", mode="min", patience=patience),
        ),
        Evaluation=EvaluationSpec(splits=["val"], primary_metric="accuracy", metrics=["accuracy"]),
    )


def _train_once(recipe: ModelRecipe, data: DataRefineryInstance, temp_dir: Path) -> object:
    # Seed weight init deterministically before constructing the model (the job the
    # orchestrator does before build_model); the trainer re-seeds the training RNG.
    enable_deterministic_algorithms(derive_seed(_SEED, "weight_init"))
    model = build_model(recipe.Architecture)
    return run_training(recipe.Training, model, recipe, data, _SEED, temp_dir)


# --- tests ---


def test_training_writes_history_checkpoints_and_best_weights(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    result = _train_once(_recipe(), data, out)

    # history.parquet — 3 rows, expected columns
    history_path = out / "training" / "history.parquet"
    assert history_path.is_file()
    frame = pq.read_table(history_path).to_pandas()  # type: ignore[no-untyped-call]
    assert list(frame.columns) == [
        "epoch",
        "train_loss",
        "val_loss",
        "val_accuracy",
        "learning_rate",
    ]
    assert len(frame) == 3
    assert frame["epoch"].tolist() == [1.0, 2.0, 3.0]

    # checkpoints per cadence (1) + best, plus promoted best weights
    checkpoints = out / "model" / "checkpoints"
    assert (checkpoints / "checkpoint-epoch-0001.pt").is_file()
    assert (checkpoints / "checkpoint-epoch-0003.pt").is_file()
    assert (checkpoints / "checkpoint-best.pt").is_file()
    assert (out / "model" / "weights" / "state_dict.pt").is_file()

    assert result.monitor == "val_loss"  # type: ignore[attr-defined]
    assert result.epochs_run == 3  # type: ignore[attr-defined]
    assert 1 <= result.best_epoch <= 3  # type: ignore[attr-defined]
    assert result.class_weights_path is None  # type: ignore[attr-defined]


def test_reruns_are_byte_identical(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    result_a = _train_once(_recipe(), data, tmp_path / "run_a")
    result_b = _train_once(_recipe(), data, tmp_path / "run_b")

    assert result_a.history == result_b.history  # type: ignore[attr-defined]

    weights_a = (tmp_path / "run_a" / "model" / "weights" / "state_dict.pt").read_bytes()
    weights_b = (tmp_path / "run_b" / "model" / "weights" / "state_dict.pt").read_bytes()
    assert weights_a == weights_b

    history_a = (tmp_path / "run_a" / "training" / "history.parquet").read_bytes()
    history_b = (tmp_path / "run_b" / "training" / "history.parquet").read_bytes()
    assert history_a == history_b


def test_class_weighted_loss_persists_weights(tmp_path: Path) -> None:
    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    result = _train_once(_recipe(loss="cross_entropy_class_weighted"), data, out)

    weights_path = out / "training" / "class_weights.json"
    assert weights_path.is_file()
    assert result.class_weights_path == weights_path  # type: ignore[attr-defined]
    payload = json.loads(weights_path.read_text())
    assert payload["classes"] == ["c0", "c1", "c2"]
    assert payload["class_counts"] == [4, 4, 4]  # balanced fixture
    assert len(payload["class_weights"]) == 3


def test_best_weights_track_the_monitor(tmp_path: Path) -> None:
    # The promoted best checkpoint's metric equals the best monitored value seen.
    from modelfoundry.pipeline.checkpoint import Checkpoint

    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    result = _train_once(_recipe(), data, out)

    best = Checkpoint.load(out / "model" / "checkpoints" / "checkpoint-best.pt")
    assert best.epoch == result.best_epoch  # type: ignore[attr-defined]
    assert best.metric_value == pytest.approx(result.best_metric_value)  # type: ignore[attr-defined]
