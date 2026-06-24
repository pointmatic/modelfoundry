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
from modelfoundry.plugins.pytorch.aggregation import ClipAggregate, aggregate_windows
from modelfoundry.plugins.pytorch.data import DataRefineryDataset
from modelfoundry.plugins.pytorch.stochastic import (
    enable_mc_dropout,
    mc_aggregate,
    mc_pass_seed,
    predictive_entropy,
)
from modelfoundry.plugins.sklearn.metrics import calibration_curve
from modelfoundry.recipe.models import EvaluationSpec, InferenceSpec, WindowAggregationSpec

_EVAL_BATCH_SIZE = 64
# Per-record predictive-uncertainty columns added to predictions.parquet on the
# MC-dropout path only (R2.3); absent on the default single-pass path.
_UNCERTAINTY_COLUMNS = ("predictive_entropy", "mc_variance")


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
    *,
    inference: InferenceSpec | None = None,
    window_aggregation: WindowAggregationSpec | None = None,
    seed: int = 0,
) -> EvaluationResult:
    """Evaluate `model` over `evaluation.splits`, writing artifacts under `temp_dir`.

    On the default single-pass path the probabilities are one `.eval()` forward
    pass. When `inference.mode == "mc_dropout"`, the deployed prediction is the
    mean over `inference.mc_samples` seeded active-dropout passes (R2.2) and
    per-record predictive uncertainty (`predictive_entropy`, `mc_variance`) is
    added to `predictions.parquet` (R2.3); `seed` is the recipe master seed that
    drives the per-pass dropout RNG (R2.4).

    When `window_aggregation` is set (FR-AUDIO-2 / R7, Story I.o.2), the bound
    instance's records are windows of a parent clip: per-window predictions are
    regrouped by `source_record_id` and combined per the declared policy, so the
    persisted metrics + predictions are **clip-level**. A window whose `record_id`
    does not decompose into its declared `source_record_id` + `window_index` is
    refused (`plugins.pytorch.aggregation.verify_window_integrity`).
    """
    eval_dir = temp_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    device = next(model.parameters()).device
    model.eval()

    mc = inference is not None and inference.mode == "mc_dropout"
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
        if mc:
            assert inference is not None and inference.mc_samples is not None  # mode == mc_dropout
            passes, targets = _infer_mc(
                model, dataset, device, n_samples=inference.mc_samples, master_seed=seed
            )
            agg = mc_aggregate(passes)
            probs = agg.mean
            uncertainty: dict[str, Any] | None = {
                "predictive_entropy": agg.predictive_entropy,
                "mc_variance": agg.mc_variance,
            }
        else:
            probs, targets = _infer(model, dataset, device)
            uncertainty = None

        if window_aggregation is not None:
            # Clip-level evaluation (R7): regroup window predictions by source_record_id
            # and combine per policy; metrics + predictions become clip-level.
            clip = _aggregate_to_clips(dataset, probs, window_aggregation)
            targets = _clip_targets(targets, clip)
            uncertainty = _clip_uncertainty(uncertainty, clip)
            probs = clip.probs
            record_ids: list[str] = clip.clip_ids
        else:
            record_ids = dataset.record_ids()
        preds = probs.argmax(dim=1)

        metrics[split] = _compute_metrics(
            requested, probs, targets, len(classes), evaluation.calibration_bins
        )
        prediction_rows.extend(
            _prediction_rows(split, record_ids, targets, probs, preds, classes, uncertainty)
        )

        if "confusion_matrix" in requested:
            cm = _confusion(preds, targets, len(classes))
            metrics[split]["confusion_matrix"] = cm.tolist()
            confusion[split] = cm
        if "calibration_curve" in requested:
            curve = _calibration(probs, targets, evaluation.calibration_bins)
            metrics[split]["calibration_curve"] = curve
            calibration_rows.extend(_calibration_rows(split, curve))

    if evaluation.comparison is not None:
        # FR-12 (Story I.t): resolve + fit-on-train the sklearn baseline and fold its
        # per-split metrics in under `baseline.<split>.<metric>`. A well-formed but
        # unresolvable id warns + omits the baseline (main metrics proceed).
        from modelfoundry.plugins.sklearn.baseline import BaselineUnresolvable, score_baseline

        try:
            metrics["baseline"] = score_baseline(
                evaluation.comparison.baseline_model_id, data, evaluation, seed
            )
        except BaselineUnresolvable as exc:
            warnings.append(str(exc))

    metrics_path = eval_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    predictions_path = eval_dir / "predictions.parquet"
    _write_predictions(prediction_rows, classes, predictions_path, with_uncertainty=mc)

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


def _infer_mc(
    model: nn.Module,
    dataset: DataRefineryDataset,
    device: torch.device,
    *,
    n_samples: int,
    master_seed: int,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Run `n_samples` seeded active-dropout passes over `dataset` (R2.1 / R2.4).

    Returns `(passes, targets)` where `passes` is `(T, N, C)` per-pass
    probabilities. Each pass seeds the global torch RNG from
    `mc_pass_seed(master_seed, t)` before iterating the (deterministically-ordered,
    `shuffle=False`) loader, so the whole T-pass sequence reproduces.
    """
    loader: DataLoader[tuple[torch.Tensor, int]] = DataLoader(
        dataset, batch_size=_EVAL_BATCH_SIZE, shuffle=False, num_workers=0
    )
    enable_mc_dropout(model)
    per_pass: list[torch.Tensor] = []
    targets: torch.Tensor | None = None
    for t in range(n_samples):
        torch.manual_seed(mc_pass_seed(master_seed, t))
        probs_chunks: list[torch.Tensor] = []
        target_chunks: list[torch.Tensor] = []
        with torch.no_grad():
            for images, labels in loader:
                logits = model(images.to(device))
                probs_chunks.append(torch.softmax(logits, dim=1).cpu())
                if t == 0:
                    target_chunks.append(labels)
        per_pass.append(torch.cat(probs_chunks))
        if t == 0:
            targets = torch.cat(target_chunks)
    assert targets is not None  # n_samples >= 1 (validated: mc_samples > 0)
    return torch.stack(per_pass), targets


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
    if "predictive_entropy" in requested:
        # R2.5: mean predictive entropy per split. `probs` is the MC-aggregated
        # mean on the stochastic path, so this reports the deployed predictor's
        # uncertainty and matches the per-record column persisted by H.n.
        out["predictive_entropy"] = float(predictive_entropy(probs).mean())
    return out


def _per_class(tensor: torch.Tensor) -> list[float]:
    return [float(x) for x in tensor.tolist()]


def _confusion(preds: torch.Tensor, targets: torch.Tensor, num_classes: int) -> np.ndarray:
    from torchmetrics.functional.classification import multiclass_confusion_matrix

    matrix = multiclass_confusion_matrix(preds, targets, num_classes=num_classes)
    return matrix.cpu().numpy().astype(np.int64)


def _calibration(probs: torch.Tensor, targets: torch.Tensor, n_bins: int) -> dict[str, list[float]]:
    confidences, predicted = probs.max(dim=1)
    correct = (predicted == targets).to(torch.float32)
    return calibration_curve(confidences.numpy(), correct.numpy(), n_bins=n_bins)


# --- predictions / persistence ---


def _class_names(dataset: DataRefineryDataset) -> list[str]:
    index_to_label = {idx: label for label, idx in dataset.label_to_index.items()}
    return [str(index_to_label[i]) for i in range(len(index_to_label))]


def _prediction_rows(
    split: str,
    record_ids: list[str],
    targets: torch.Tensor,
    probs: torch.Tensor,
    preds: torch.Tensor,
    classes: list[str],
    uncertainty: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-record (or per-clip) prediction rows.

    `record_ids` + `targets` align with `probs` row-for-row (window-level on the
    default path, clip-level after R7 aggregation).
    """
    rows: list[dict[str, Any]] = []
    for i, record_id in enumerate(record_ids):
        true_idx = int(targets[i])
        pred_idx = int(preds[i])
        row: dict[str, Any] = {
            "split": split,
            "record_id": record_id,
            "true_label": classes[true_idx] if true_idx >= 0 else None,
            "pred_label": classes[pred_idx],
        }
        for c, name in enumerate(classes):
            row[f"pred_proba_{name}"] = float(probs[i, c])
        if uncertainty is not None:
            for col, values in uncertainty.items():
                row[col] = float(values[i])
        rows.append(row)
    return rows


# --- clip-level window aggregation (R7) ---


def _aggregate_to_clips(
    dataset: DataRefineryDataset,
    probs: torch.Tensor,
    window_aggregation: WindowAggregationSpec,
) -> ClipAggregate:
    keys = dataset.window_keys()
    source_ids = [k[0] for k in keys]
    window_indices = [k[1] for k in keys]
    return aggregate_windows(
        probs, dataset.record_ids(), source_ids, window_indices, window_aggregation.policy
    )


def _clip_targets(targets: torch.Tensor, clip: ClipAggregate) -> torch.Tensor:
    # Every window of a clip shares one label (no straddling, R7), so the clip target
    # is its first window's target.
    return torch.tensor([int(targets[members[0]]) for members in clip.members])


def _clip_uncertainty(
    uncertainty: dict[str, Any] | None, clip: ClipAggregate
) -> dict[str, Any] | None:
    # Clip-level MC uncertainty: predictive entropy of the aggregated clip distribution
    # (the deployed clip prediction), and the mean MC variance across the clip's windows.
    if uncertainty is None:
        return None
    mc_variance = uncertainty["mc_variance"]
    return {
        "predictive_entropy": predictive_entropy(clip.probs),
        "mc_variance": torch.stack([mc_variance[members].mean() for members in clip.members]),
    }


def _write_predictions(
    rows: list[dict[str, Any]],
    classes: list[str],
    path: Path,
    *,
    with_uncertainty: bool = False,
) -> None:
    import pandas as pd  # type: ignore[import-untyped]

    columns = ["split", "record_id", "true_label", "pred_label"] + [
        f"pred_proba_{name}" for name in classes
    ]
    if with_uncertainty:
        columns += list(_UNCERTAINTY_COLUMNS)
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
