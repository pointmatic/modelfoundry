# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch evaluation (FR-12 / FR-22, Story C.j).

`run_evaluation` runs inference over each declared `Evaluation.split`, computes
the pre-production metric vocabulary via `torchmetrics`, and persists the
notebook-shaped evaluation artifacts: `evaluation/metrics.json` (the
`{split: {metric: value}}` shape the OutputExpectations evaluator consumes),
`evaluation/confusion_matrix.npz`, `evaluation/calibration.parquet`, and
`evaluation/predictions.parquet`.

The metric vocabulary mirrors the validator's `EVALUATION_METRIC_VOCABULARY`:
`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`,
`accuracy`, `confusion_matrix`, `ece`, `calibration_curve`. The reliability
curve comes from the shared `plugins.sklearn.metrics.calibration_curve` (C.j
slice; C.m extends that module).

This module imports `torch` at the top — it is loaded at materialize time, not
during plugin discovery; the plugin delegates here through a lazy import.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.plugins.pytorch.data import DataRefineryDataset
from modelfoundry.plugins.sklearn.metrics import calibration_curve
from modelfoundry.recipe.models import EvaluationSpec

_EVAL_BATCH_SIZE = 64


@dataclass(frozen=True)
class EvaluationResult:
    """Outcome of the evaluation stage — recorded in the manifest by the orchestrator."""

    metrics: dict[str, dict[str, Any]]
    metrics_path: Path
    predictions_path: Path
    confusion_matrix_path: Path | None
    calibration_path: Path | None
    warnings: list[str] = field(default_factory=list)


def run_evaluation(
    evaluation: EvaluationSpec,
    model: nn.Module,
    data: DataRefineryInstance,
    temp_dir: Path,
) -> EvaluationResult:
    """Evaluate `model` over `evaluation.splits`, writing artifacts under `temp_dir`."""
    eval_dir = temp_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    device = next(model.parameters()).device
    model.eval()

    requested = set(evaluation.metrics)
    warnings: list[str] = []
    metrics: dict[str, dict[str, Any]] = {}
    prediction_rows: list[dict[str, Any]] = []
    confusion: dict[str, np.ndarray] = {}
    calibration_rows: list[dict[str, Any]] = []
    classes: list[str] = []

    for split in evaluation.splits:
        dataset = DataRefineryDataset(data, split)
        classes = _class_names(dataset)
        probs, targets = _infer(model, dataset, device)
        preds = probs.argmax(dim=1)

        metrics[split] = _compute_metrics(
            requested, probs, targets, len(classes), evaluation.calibration_bins
        )
        prediction_rows.extend(_prediction_rows(split, dataset, probs, preds, classes))

        if "confusion_matrix" in requested:
            cm = _confusion(preds, targets, len(classes))
            metrics[split]["confusion_matrix"] = cm.tolist()
            confusion[split] = cm
        if "calibration_curve" in requested:
            curve = _calibration(probs, targets, evaluation.calibration_bins)
            metrics[split]["calibration_curve"] = curve
            calibration_rows.extend(_calibration_rows(split, curve))

    if evaluation.comparison is not None:
        warnings.append(_baseline_comparison_warning(evaluation.comparison.baseline_model_id))

    metrics_path = eval_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    predictions_path = eval_dir / "predictions.parquet"
    _write_predictions(prediction_rows, classes, predictions_path)

    confusion_path = None
    if confusion:
        confusion_path = eval_dir / "confusion_matrix.npz"
        np.savez(confusion_path, **confusion)  # type: ignore[arg-type]

    calibration_path = None
    if calibration_rows:
        calibration_path = eval_dir / "calibration.parquet"
        _write_calibration(calibration_rows, calibration_path)

    return EvaluationResult(
        metrics=metrics,
        metrics_path=metrics_path,
        predictions_path=predictions_path,
        confusion_matrix_path=confusion_path,
        calibration_path=calibration_path,
        warnings=warnings,
    )


# --- inference ---


def _infer(
    model: nn.Module, dataset: DataRefineryDataset, device: torch.device
) -> tuple[torch.Tensor, torch.Tensor]:
    loader: DataLoader[tuple[torch.Tensor, int]] = DataLoader(
        dataset, batch_size=_EVAL_BATCH_SIZE, shuffle=False, num_workers=0
    )
    probs_chunks: list[torch.Tensor] = []
    target_chunks: list[torch.Tensor] = []
    with torch.no_grad():
        for images, labels in loader:
            logits = model(images.to(device))
            probs_chunks.append(torch.softmax(logits, dim=1).cpu())
            target_chunks.append(labels)
    return torch.cat(probs_chunks), torch.cat(target_chunks)


# --- metrics ---


def _compute_metrics(
    requested: set[str],
    probs: torch.Tensor,
    targets: torch.Tensor,
    num_classes: int,
    n_bins: int,
) -> dict[str, Any]:
    from torchmetrics.functional.classification import (
        multiclass_accuracy,
        multiclass_calibration_error,
        multiclass_f1_score,
        multiclass_precision,
        multiclass_recall,
    )

    out: dict[str, Any] = {}
    if "accuracy" in requested:
        out["accuracy"] = float(
            multiclass_accuracy(probs, targets, num_classes=num_classes, average="micro")
        )
    if "macro_f1" in requested:
        out["macro_f1"] = float(
            multiclass_f1_score(probs, targets, num_classes=num_classes, average="macro")
        )
    if "per_class_f1" in requested:
        out["per_class_f1"] = _per_class(
            multiclass_f1_score(probs, targets, num_classes=num_classes, average=None)
        )
    if "per_class_precision" in requested:
        out["per_class_precision"] = _per_class(
            multiclass_precision(probs, targets, num_classes=num_classes, average=None)
        )
    if "per_class_recall" in requested:
        out["per_class_recall"] = _per_class(
            multiclass_recall(probs, targets, num_classes=num_classes, average=None)
        )
    if "ece" in requested:
        out["ece"] = float(
            multiclass_calibration_error(
                probs, targets, num_classes=num_classes, n_bins=n_bins, norm="l1"
            )
        )
    return out


def _per_class(tensor: torch.Tensor) -> list[float]:
    return [float(x) for x in tensor.tolist()]


def _confusion(preds: torch.Tensor, targets: torch.Tensor, num_classes: int) -> np.ndarray:
    from torchmetrics.functional.classification import multiclass_confusion_matrix

    matrix = multiclass_confusion_matrix(preds, targets, num_classes=num_classes)
    return matrix.cpu().numpy().astype(np.int64)


def _calibration(
    probs: torch.Tensor, targets: torch.Tensor, n_bins: int
) -> dict[str, list[float]]:
    confidences, predicted = probs.max(dim=1)
    correct = (predicted == targets).to(torch.float32)
    return calibration_curve(confidences.numpy(), correct.numpy(), n_bins=n_bins)


# --- predictions / persistence ---


def _class_names(dataset: DataRefineryDataset) -> list[str]:
    index_to_label = {idx: label for label, idx in dataset.label_to_index.items()}
    return [str(index_to_label[i]) for i in range(len(index_to_label))]


def _prediction_rows(
    split: str,
    dataset: DataRefineryDataset,
    probs: torch.Tensor,
    preds: torch.Tensor,
    classes: list[str],
) -> list[dict[str, Any]]:
    record_ids = dataset.record_ids()
    rows: list[dict[str, Any]] = []
    for i, record_id in enumerate(record_ids):
        true_idx = int(dataset[i][1])
        pred_idx = int(preds[i])
        row: dict[str, Any] = {
            "split": split,
            "record_id": record_id,
            "true_label": classes[true_idx] if true_idx >= 0 else None,
            "pred_label": classes[pred_idx],
        }
        for c, name in enumerate(classes):
            row[f"pred_proba_{name}"] = float(probs[i, c])
        rows.append(row)
    return rows


def _write_predictions(rows: list[dict[str, Any]], classes: list[str], path: Path) -> None:
    import pandas as pd  # type: ignore[import-untyped]

    columns = ["split", "record_id", "true_label", "pred_label"] + [
        f"pred_proba_{name}" for name in classes
    ]
    frame = pd.DataFrame(rows).reindex(columns=columns)
    frame.to_parquet(path, index=False)


def _calibration_rows(split: str, curve: dict[str, list[float]]) -> list[dict[str, Any]]:
    return [
        {
            "split": split,
            "bin_lower": curve["bin_lower"][i],
            "bin_upper": curve["bin_upper"][i],
            "mean_confidence": curve["mean_confidence"][i],
            "accuracy": curve["accuracy"][i],
            "count": int(curve["count"][i]),
        }
        for i in range(len(curve["count"]))
    ]


def _write_calibration(rows: list[dict[str, Any]], path: Path) -> None:
    import pandas as pd

    pd.DataFrame(rows).to_parquet(path, index=False)


def _baseline_comparison_warning(baseline_model_id: str) -> str:
    # FR-12 baseline resolution is deferred (the resolver lands with the C.m sklearn
    # baseline + C.p library API); pre-prod records a warning and continues.
    return (
        f"baseline comparison against {baseline_model_id!r} is not yet resolvable "
        f"(deferred to the C.m baseline resolver); skipped"
    )
