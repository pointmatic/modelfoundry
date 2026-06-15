# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch training loop (FR-10, Story C.h).

`run_training` drives the deterministic per-epoch loop that ties the C.c-C.g
pieces together: it enables deterministic-algorithm mode (C.e), builds the
train/val `DataLoader`s (C.f) with the spawn-safe seeded `worker_init_fn`
(B.j / C.a.1) and the lazy augmentation policy (C.g), fits + persists class weights
(C.d) when the loss is class-weighted, constructs the optimizer + schedule (C.d),
runs the epochs, writes `training/history.parquet` and periodic checkpoints
(B.k), tracks the early-stopping monitor, and promotes the best-monitor-value
weights to `model/weights/`.

This module imports `torch` at the top — like `data.py`, it is loaded by the
trainer at materialize time, not during plugin discovery, so the
import-safe-without-`[pytorch]` rule does not apply. The plugin delegates to it
through a lazy import to keep `plugin.py` import-safe.

**Determinism.** Weight-init reproducibility is the model-construction caller's
job (the orchestrator seeds before `build_model`); this loop re-enables
deterministic mode and seeds the training-time RNG from the `"dropout"` scope, so
dropout / any in-loop stochasticity reproduces independently of how many RNG
draws model construction consumed. Shuffle order is owned by the dataloader's
seeded generator. See `project-essentials.md` § Determinism contract.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch import nn
from torch.utils.data import DataLoader

from modelfoundry.core.errors import PluginError
from modelfoundry.pipeline.checkpoint import Checkpoint
from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.pipeline.progress import ProgressReporter
from modelfoundry.pipeline.seeding import derive_seed
from modelfoundry.plugins.pytorch.augmentations import AugmentationOp, compose_augmentations
from modelfoundry.plugins.pytorch.data import DataRefineryDataset, build_dataloader
from modelfoundry.plugins.pytorch.determinism import enable_deterministic_algorithms
from modelfoundry.plugins.pytorch.losses import build_loss, derive_class_weights
from modelfoundry.plugins.pytorch.optimizers import build_optimizer
from modelfoundry.plugins.pytorch.schedules import build_schedule
from modelfoundry.recipe.canonical import recipe_hash
from modelfoundry.recipe.models import ModelRecipe, TrainingSpec

_CLASS_WEIGHTED_LOSS = "cross_entropy_class_weighted"
_PLATEAU_SCHEDULE = "reduce_on_plateau"


@dataclass(frozen=True)
class TrainingResult:
    """Outcome of a training run — what the orchestrator (C.o) records in the manifest."""

    epochs_run: int
    best_epoch: int
    best_metric_value: float
    monitor: str
    mode: str
    history: list[dict[str, float]]
    weights_path: Path
    best_checkpoint_path: Path
    class_weights_path: Path | None


def run_training(
    training: TrainingSpec,
    model: nn.Module,
    recipe: ModelRecipe,
    data: DataRefineryInstance,
    seed: int,
    temp_dir: Path,
    *,
    epoch_callback: Callable[[int, dict[str, float]], None] | None = None,
    progress: ProgressReporter | None = None,
) -> TrainingResult:
    """Train `model` over the bound instance, writing artifacts under `temp_dir`.

    `epoch_callback(epoch, record)` runs after each epoch's metrics are produced
    (before checkpointing) — the Optuna optimization stage (C.i) uses it to report
    intermediate values and raise `optuna.TrialPruned` to prune a trial early.
    `progress`, when supplied, receives a per-epoch `on_epoch(epoch, record)` for
    user-facing rendering (Story D.e.1); it is independent of `epoch_callback`.
    """
    enable_deterministic_algorithms()
    torch.manual_seed(derive_seed(seed, "dropout"))

    device = _resolve_device(training.device)
    model = model.to(device)

    training_dir = temp_dir / "training"
    weights_dir = temp_dir / "model" / "weights"
    checkpoints_dir = temp_dir / "model" / "checkpoints"
    for directory in (training_dir, weights_dir, checkpoints_dir):
        directory.mkdir(parents=True, exist_ok=True)

    augmentations = compose_augmentations(_lazy_train_augmentations(data), master_seed=seed)
    train_ds = DataRefineryDataset(data, "train", augmentations=augmentations)
    train_loader = build_dataloader(train_ds, training, master_seed=seed)
    num_classes = len(train_ds.label_to_index)

    val_loader = _maybe_val_loader(data, training, seed)

    class_weights, class_weights_path = _fit_class_weights(
        recipe, train_ds, training_dir
    )
    loss_fn = build_loss(
        recipe.Loss.op,
        _op_params(recipe.Loss.model_dump(), drop=("op",)),
        class_weights=class_weights,
        num_classes=num_classes,
    ).to(device)

    optimizer = build_optimizer(
        recipe.Optimizer.op,
        _op_params(recipe.Optimizer.model_dump(), drop=("op", "schedule")),
        model.parameters(),
    )
    scheduler = _maybe_scheduler(recipe, optimizer)

    monitor, mode, patience = _resolve_monitor(training, has_val=val_loader is not None)
    recipe_hash16 = recipe_hash(recipe)[:16]

    history: list[dict[str, float]] = []
    best_value: float | None = None
    best_epoch = 0
    stale_epochs = 0

    for epoch in range(1, training.max_epochs + 1):
        learning_rate = float(optimizer.param_groups[0]["lr"])
        train_loss = _train_epoch(model, train_loader, loss_fn, optimizer, device)

        record: dict[str, float] = {
            "epoch": float(epoch),
            "train_loss": train_loss,
            "learning_rate": learning_rate,
        }
        if val_loader is not None:
            val_loss, val_accuracy = _eval_epoch(model, val_loader, loss_fn, device)
            record["val_loss"] = val_loss
            record["val_accuracy"] = val_accuracy
        history.append(record)

        if progress is not None:
            progress.on_epoch(epoch, record)
        if epoch_callback is not None:
            epoch_callback(epoch, record)

        _step_scheduler(scheduler, recipe, record, monitor)

        if epoch % training.checkpoint_cadence == 0:
            _write_checkpoint(
                checkpoints_dir / f"checkpoint-epoch-{epoch:04d}.pt",
                epoch,
                model,
                _monitored(record, monitor),
                recipe_hash16,
            )

        value = _monitored(record, monitor)
        if _is_better(value, best_value, mode):
            best_value, best_epoch, stale_epochs = value, epoch, 0
            _save_weights(model, weights_dir / "state_dict.pt")
            _write_checkpoint(
                checkpoints_dir / "checkpoint-best.pt", epoch, model, value, recipe_hash16
            )
        else:
            stale_epochs += 1
            if patience is not None and stale_epochs >= patience:
                break

    _write_history(history, training_dir / "history.parquet")

    assert best_value is not None  # max_epochs > 0, so the loop always ran once
    return TrainingResult(
        epochs_run=len(history),
        best_epoch=best_epoch,
        best_metric_value=best_value,
        monitor=monitor,
        mode=mode,
        history=history,
        weights_path=weights_dir / "state_dict.pt",
        best_checkpoint_path=checkpoints_dir / "checkpoint-best.pt",
        class_weights_path=class_weights_path,
    )


# --- epoch passes ---


def _train_epoch(
    model: nn.Module,
    loader: DataLoader[tuple[torch.Tensor, int]],
    loss_fn: nn.Module,
    optimizer: Any,
    device: torch.device,
) -> float:
    model.train()
    total, count = 0.0, 0
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        loss = loss_fn(model(images), labels)
        loss.backward()
        optimizer.step()
        total += float(loss.item()) * images.size(0)
        count += images.size(0)
    return total / max(count, 1)


def _eval_epoch(
    model: nn.Module,
    loader: DataLoader[tuple[torch.Tensor, int]],
    loss_fn: nn.Module,
    device: torch.device,
) -> tuple[float, float]:
    model.eval()
    total, count, correct = 0.0, 0, 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            logits = model(images)
            total += float(loss_fn(logits, labels).item()) * images.size(0)
            count += images.size(0)
            correct += int((logits.argmax(dim=1) == labels).sum().item())
    return total / max(count, 1), correct / max(count, 1)


# --- helpers ---


def _resolve_device(device: str) -> torch.device:
    """Map the recipe `Training.device` knob to a concrete `torch.device`.

    `"auto"` prefers CUDA, then MPS, then CPU; an explicit value is honored as-is
    (the recipe validator's check 20 already confirmed availability).
    """
    if device == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        mps = getattr(torch.backends, "mps", None)
        if mps is not None and mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(device)


def _op_params(dumped: dict[str, Any], *, drop: tuple[str, ...]) -> dict[str, Any]:
    """A plugin op's params: the section dump minus the structural keys in `drop`."""
    return {k: v for k, v in dumped.items() if k not in drop and v is not None}


def _lazy_train_augmentations(data: DataRefineryInstance) -> list[AugmentationOp]:
    """Lazy, train-split augmentation ops from the bound DataRefinery recipe.

    Aggressive ops are already baked into the materialized records (resolved via
    `image_path`), so only `materialization == "lazy"` ops that target `train`
    are realized on-the-fly here. The DataRefinery recipe may omit the section
    entirely, in which case there is nothing to compose.
    """
    ops: list[AugmentationOp] = []
    for op in getattr(data.recipe, "Augmentations", None) or []:
        materialization = getattr(op, "materialization", "lazy")
        splits = getattr(op, "splits", ["train"])
        if materialization == "lazy" and "train" in splits:
            ops.append(
                AugmentationOp(
                    name=op.name,
                    op=op.op,
                    params=dict(getattr(op, "params", {}) or {}),
                    seed=getattr(op, "seed", None),
                )
            )
    return ops


def _maybe_val_loader(
    data: DataRefineryInstance, training: TrainingSpec, seed: int
) -> DataLoader[tuple[torch.Tensor, int]] | None:
    if "val" not in data.splits:
        return None
    val_ds = DataRefineryDataset(data, "val")
    return build_dataloader(val_ds, training, master_seed=seed, shuffle=False)


def _fit_class_weights(
    recipe: ModelRecipe, train_ds: DataRefineryDataset, training_dir: Path
) -> tuple[list[float] | None, Path | None]:
    """Fit class weights on the train split and persist them, for the weighted loss."""
    if recipe.Loss.op != _CLASS_WEIGHTED_LOSS:
        return None, None
    params = _op_params(recipe.Loss.model_dump(), drop=("op",))
    weight_source = str(params.get("weight_source", "train"))
    beta = float(params.get("beta", 0.999))
    counts = train_ds.class_counts()
    weights = derive_class_weights(weight_source, counts, beta=beta)

    path = training_dir / "class_weights.json"
    index_to_label = {idx: label for label, idx in train_ds.label_to_index.items()}
    path.write_text(
        json.dumps(
            {
                "weight_source": weight_source,
                "class_counts": counts,
                "class_weights": weights,
                "classes": [index_to_label[i] for i in range(len(weights))],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return weights, path


def _maybe_scheduler(recipe: ModelRecipe, optimizer: Any) -> Any | None:
    schedule = recipe.Optimizer.schedule
    if schedule is None:
        return None
    return build_schedule(
        schedule.op, _op_params(schedule.model_dump(), drop=("op", "monitor")), optimizer
    )


def _step_scheduler(
    scheduler: Any | None, recipe: ModelRecipe, record: dict[str, float], monitor: str
) -> None:
    if scheduler is None:
        return
    schedule = recipe.Optimizer.schedule
    if schedule is not None and schedule.op == _PLATEAU_SCHEDULE:
        watched = schedule.monitor or monitor
        scheduler.step(_monitored(record, watched))
    else:
        scheduler.step()


def _resolve_monitor(
    training: TrainingSpec, *, has_val: bool
) -> tuple[str, str, int | None]:
    """The metric/direction/patience driving best-weight promotion + early stopping.

    Uses `Training.early_stopping` when declared (validator check 6 guarantees its
    monitor is a produced metric); otherwise tracks `val_loss` (min) when a val
    split exists, falling back to `train_loss` (min). Patience is `None` when
    there is no early-stopping budget — best weights are still promoted.
    """
    if training.early_stopping is not None:
        es = training.early_stopping
        return es.monitor, es.mode, es.patience
    return ("val_loss", "min", None) if has_val else ("train_loss", "min", None)


def _monitored(record: dict[str, float], key: str) -> float:
    if key not in record:
        raise PluginError(
            f"monitored metric {key!r} is not produced this epoch; "
            f"available: {sorted(record)}",
            stage="run_training",
            detail={"monitor": key},
        )
    return record[key]


def _is_better(value: float, best: float | None, mode: str) -> bool:
    if best is None:
        return True
    return value < best if mode == "min" else value > best


def _save_weights(model: nn.Module, path: Path) -> None:
    torch.save(model.state_dict(), path)


def _write_checkpoint(
    path: Path,
    epoch: int,
    model: nn.Module,
    metric_value: float,
    recipe_hash16: str,
) -> None:
    # Persist via torch.save (not Checkpoint.save's pickle): raw-pickling torch
    # tensors is non-deterministic across equal-but-distinct tensors, while
    # torch.save is byte-stable — required for the FR-25 byte-identity contract.
    # Matches the stacking pattern documented in pipeline.checkpoint.
    checkpoint = Checkpoint(
        epoch=epoch,
        weights=model.state_dict(),
        metric_value=metric_value,
        recipe_hash16=recipe_hash16,
    )
    torch.save(checkpoint.model_dump(), path)


def _write_history(history: Iterable[dict[str, float]], path: Path) -> None:
    import pandas as pd  # type: ignore[import-untyped]

    columns = ["epoch", "train_loss", "val_loss", "val_accuracy", "learning_rate"]
    frame = pd.DataFrame(list(history))
    frame = frame.reindex(columns=[c for c in columns if c in frame.columns])
    frame.to_parquet(path, index=False)
