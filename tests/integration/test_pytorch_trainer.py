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
from typing import Any

import numpy as np
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


def _overfit_recipe_yaml() -> str:
    # No Transformations -> the adapter scales to [0,1] (no fitted stats needed).
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
        Splits: {ratios: {train: 0.6, val: 0.2, test: 0.2}, seed: 1, stratify_by: label}
        """
    ).strip()


def _build_overfit_instance(tmp_path: Path) -> DataRefineryInstance:
    """A memorizable RANDOM-pixel instance that forces overfitting.

    Train images are unique noise the linear model can fit exactly while val is
    held-out noise, so the model overfits: `val_loss` bottoms out early then rises
    while training continues — i.e. best-`val_loss` epoch != final epoch. No
    normalize op, so the adapter scales to [0,1] and no fitted statistics are
    needed. This is the condition under which "keep final" vs "restore best
    (early)" produce different weights (the H.f.9 regression guard).
    """
    recipe_path = tmp_path / "dr_overfit.yml"
    recipe_path.write_text(_overfit_recipe_yaml(), encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_path)
    recipe_hash = hashlib.sha256(to_canonical_bytes(dr_recipe)).hexdigest()

    inst = tmp_path / "overfit_inst"
    inst.mkdir()
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")

    rng = np.random.default_rng(0)
    dataset_dir = inst / "dataset"
    dataset_dir.mkdir()
    images_dir = inst / "images"
    images_dir.mkdir()
    counts: dict[str, int] = {}
    for split, per_class in (("train", 8), ("val", 4), ("test", 4)):
        records = []
        for cls in _CLASSES:
            for i in range(per_class):
                px = rng.integers(0, 256, size=(4, 4, 3), dtype=np.uint8)
                png = images_dir / f"{split}_{cls}_{i}.png"
                Image.fromarray(px, "RGB").save(png)
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
    loss: str = "cross_entropy",
    max_epochs: int = 3,
    patience: int = 10,
    monitor: str = "val_loss",
    mode: str = "min",
    with_early_stopping: bool = True,
) -> ModelRecipe:
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
            device="cpu",
            checkpoint_cadence=1,
            early_stopping=(
                EarlyStoppingSpec(monitor=monitor, mode=mode, patience=patience)
                if with_early_stopping
                else None
            ),
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


def test_best_weights_are_restored_into_model_after_early_stop(tmp_path: Path) -> None:
    # restore_best_weights contract (H.f.8 regression guard). The runner evaluates
    # AND persists the in-memory model `run_training` returns; with early stopping
    # the final epoch is `patience` epochs of non-improvement past the best, so the
    # returned model MUST be the best-monitor checkpoint, not the stale final epoch.
    # The H.f.8 bug kept the final epoch — early stopping silently shipped a
    # `patience`-epochs-stale model (and `save_model` then overwrote the on-disk
    # best with it), which disproportionately penalized models that early-stop.
    #
    # Monitor val_accuracy/max on the trivially-separable fixture: accuracy plateaus
    # at its max within a couple epochs, early-stopping fires `patience` epochs
    # later, but the weights keep drifting — so best_epoch < final_epoch and the two
    # weight sets differ, which is the only case that distinguishes the two
    # behaviors.
    from modelfoundry.pipeline.checkpoint import Checkpoint

    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    recipe = _recipe(max_epochs=10, patience=2, monitor="val_accuracy", mode="max")

    enable_deterministic_algorithms(derive_seed(_SEED, "weight_init"))
    model = build_model(recipe.Architecture)
    result = run_training(recipe.Training, model, recipe, data, _SEED, out)

    # Early stopping fired strictly before the final epoch — the only configuration
    # under which "restore best" and "keep final" produce different weights.
    assert result.best_epoch < result.epochs_run, (
        result.best_epoch,
        result.epochs_run,
    )

    payload = torch.load(out / "model" / "checkpoints" / "checkpoint-best.pt", weights_only=False)
    best_weights = Checkpoint.model_validate(payload).weights

    model_state = model.state_dict()
    assert set(model_state) == set(best_weights)
    for key, best_tensor in best_weights.items():
        assert torch.equal(model_state[key].cpu(), best_tensor.cpu()), (
            f"{key} was not restored to the best-monitor checkpoint"
        )


def test_final_weights_kept_when_no_early_stopping(tmp_path: Path) -> None:
    # H.f.9 regression guard. With NO early stopping the recipe asked to train the
    # FULL schedule, so run_training must return the converged FINAL epoch — not an
    # early best-monitor (val_loss/min) epoch. The v0.10.1 fix restored best weights
    # unconditionally, so a no-early-stopping cosine run shipped the early min-val_loss
    # epoch (val_loss bottoms out early then rises under overfitting while val accuracy
    # keeps improving — the canonical 160-epoch ResNet-20 run reported 0.731 instead of
    # ~0.79). The v0.10.2 gate restores best weights ONLY when early stopping is set.
    import pandas as pd  # type: ignore[import-untyped]

    from modelfoundry.pipeline.checkpoint import Checkpoint

    data = _build_overfit_instance(tmp_path)
    out = tmp_path / "instance"
    recipe = _recipe(max_epochs=20, with_early_stopping=False)

    enable_deterministic_algorithms(derive_seed(_SEED, "weight_init"))
    model = build_model(recipe.Architecture)
    run_training(recipe.Training, model, recipe, data, _SEED, out)

    history = pd.read_parquet(out / "training" / "history.parquet")
    best_i = int(history["val_loss"].idxmin())
    final_i = len(history) - 1
    # The fixture must actually overfit (best-val_loss strictly before final) or the
    # guard is trivial — "keep final" and "restore best" would coincide.
    assert best_i < final_i, (best_i + 1, final_i + 1, history["val_loss"].tolist())

    def _weights(name: str) -> dict[str, Any]:
        payload = torch.load(out / "model" / "checkpoints" / name, weights_only=False)
        weights: dict[str, Any] = Checkpoint.model_validate(payload).weights
        return weights

    final_weights = _weights(f"checkpoint-epoch-{len(history):04d}.pt")
    best_weights = _weights("checkpoint-best.pt")
    model_state = model.state_dict()

    # Returned model is the FINAL epoch (kept), not the early best-monitor epoch.
    for key, final_tensor in final_weights.items():
        assert torch.equal(model_state[key].cpu(), final_tensor.cpu()), (
            f"{key}: returned model is not the converged final epoch"
        )
    # Non-trivial: final and best genuinely differ here.
    assert any(
        not torch.equal(final_weights[k].cpu(), best_weights[k].cpu()) for k in final_weights
    ), "final == best; the overfit fixture did not separate them"


def test_best_weights_track_the_monitor(tmp_path: Path) -> None:
    # The promoted best checkpoint's metric equals the best monitored value seen.
    from modelfoundry.pipeline.checkpoint import Checkpoint

    data = _build_instance(tmp_path)
    out = tmp_path / "instance"
    result = _train_once(_recipe(), data, out)

    # Checkpoints are persisted via torch.save (deterministic tensor bytes), so
    # read them back through torch.load + the Checkpoint schema.
    payload = torch.load(out / "model" / "checkpoints" / "checkpoint-best.pt", weights_only=False)
    best = Checkpoint.model_validate(payload)
    assert best.epoch == result.best_epoch  # type: ignore[attr-defined]
    assert best.metric_value == pytest.approx(result.best_metric_value)  # type: ignore[attr-defined]
