# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch visualization renderers (FR-13, Story C.k).

Matplotlib (Agg, headless) renderers for the registered viz ops —
`training_curves`, `optimization_history`, `confusion_matrix`,
`calibration_curve`, `predictions_grid`. Each takes an `InstanceArtifacts`
snapshot and returns PNG bytes; the dispatcher `render_visualization(viz,
artifacts)` routes on `VisualizationSpec.op`.

**Determinism.** Output PNG bytes must be reproducible across runs (the
materialize byte-identity contract): the Agg backend is forced, no timestamp is
embedded, and the `Software` metadata tag is pinned to a constant so the bytes
don't drift with the matplotlib version. Renderers draw only from the snapshot —
no RNG, no wall-clock.

This module imports matplotlib at the top; it is loaded at materialize time
(the plugin delegates here lazily), not during plugin discovery.
"""

from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless; must precede pyplot import

import matplotlib.pyplot as plt
import numpy as np

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import InstanceArtifacts
from modelfoundry.recipe.models import VisualizationSpec

# Pin the PNG `Software` tag so bytes don't drift with the matplotlib version.
_PNG_METADATA = {"Software": "modelfoundry"}
_FIGSIZE = (6.0, 4.0)
_DPI = 100


def render_visualization(viz: VisualizationSpec, artifacts: InstanceArtifacts) -> bytes:
    """Render the `viz` op against `artifacts`, returning deterministic PNG bytes."""
    renderer = _RENDERERS.get(viz.op)
    if renderer is None:
        raise PluginError(
            f"unknown visualization op {viz.op!r}; known: {sorted(_RENDERERS)}",
            stage="render_visualization",
        )
    return renderer(viz, artifacts)


# --- renderers ---


def _training_curves(viz: VisualizationSpec, artifacts: InstanceArtifacts) -> bytes:
    history = artifacts.history
    if history is None or len(history) == 0:
        return _placeholder("training_curves: no training history")
    fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
    epochs = history["epoch"]
    ax.plot(epochs, history["train_loss"], label="train_loss", color="C0")
    if "val_loss" in history.columns:
        ax.plot(epochs, history["val_loss"], label="val_loss", color="C1")
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss")
    ax.set_title("Training curves")
    if "val_accuracy" in history.columns:
        ax2 = ax.twinx()
        ax2.plot(epochs, history["val_accuracy"], label="val_accuracy", color="C2")
        ax2.set_ylabel("accuracy")
    ax.legend(loc="upper right")
    return _to_png(fig)


def _optimization_history(viz: VisualizationSpec, artifacts: InstanceArtifacts) -> bytes:
    trials = artifacts.trials
    values = _completed_trial_values(trials)
    if not values:
        # No Optimization stage ran (or no completed trials): keep the manifest's
        # viz record consistent with an explicit placeholder.
        return _placeholder("optimization_history: no optimization stage")
    numbers = list(range(len(values)))
    running_best = np.minimum.accumulate(values).tolist()
    fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
    ax.plot(numbers, values, marker="o", linestyle="none", label="trial value", color="C0")
    ax.plot(numbers, running_best, label="running best", color="C1")
    ax.set_xlabel("trial")
    ax.set_ylabel("objective value")
    ax.set_title("Optimization history")
    ax.legend(loc="upper right")
    return _to_png(fig)


def _draw_confusion(
    ax: Any, fig: Any, matrix: Any, split: str, artifacts: InstanceArtifacts
) -> None:
    cm = np.asarray(matrix)
    classes = artifacts.class_names or [str(i) for i in range(cm.shape[0])]
    im = ax.imshow(cm, cmap="Blues")
    fig.colorbar(im, ax=ax)
    ax.set_xticks(range(len(classes)), labels=classes, rotation=45, ha="right")
    ax.set_yticks(range(len(classes)), labels=classes)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title(f"Confusion matrix ({split})")
    threshold = cm.max() / 2 if cm.size else 0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j,
                i,
                str(int(cm[i, j])),
                ha="center",
                va="center",
                color="white" if cm[i, j] > threshold else "black",
            )


def _confusion_matrix(viz: VisualizationSpec, artifacts: InstanceArtifacts) -> bytes:
    panels = [
        (s, _evaluation_value(artifacts, s, "confusion_matrix"))
        for s in _pick_splits(viz, artifacts)
    ]
    panels = [(s, m) for s, m in panels if m is not None]
    if not panels:
        return _placeholder("confusion_matrix: not available")
    # One panel per split. For a single split this is `subplots(1, 1, figsize=_FIGSIZE)`
    # — byte-identical to the legacy single-split figure (Story I.w byte-neutrality).
    fig, axes = plt.subplots(
        1, len(panels), figsize=(_FIGSIZE[0] * len(panels), _FIGSIZE[1]), dpi=_DPI
    )
    for ax, (split, matrix) in zip(np.atleast_1d(axes).ravel(), panels, strict=True):
        _draw_confusion(ax, fig, matrix, split, artifacts)
    return _to_png(fig)


def _calibration_curve(viz: VisualizationSpec, artifacts: InstanceArtifacts) -> bytes:
    curves = [
        (s, _evaluation_value(artifacts, s, "calibration_curve"))
        for s in _pick_splits(viz, artifacts)
    ]
    curves = [(s, c) for s, c in curves if c and c.get("mean_confidence")]
    if not curves:
        return _placeholder("calibration_curve: not available")
    fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
    ax.plot([0, 1], [0, 1], linestyle="--", color="grey", label="perfect")
    if len(curves) == 1:
        # Legacy single-split path, byte-identical to the pre-I.w figure.
        split, curve = curves[0]
        ax.plot(curve["mean_confidence"], curve["accuracy"], marker="o", color="C0", label="model")
        ax.set_title(f"Calibration ({split})")
    else:
        for split, curve in curves:
            ax.plot(curve["mean_confidence"], curve["accuracy"], marker="o", label=split)
        ax.set_title("Calibration")
    ax.set_xlabel("mean predicted confidence")
    ax.set_ylabel("observed accuracy")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="upper left")
    return _to_png(fig)


def _predictions_grid(viz: VisualizationSpec, artifacts: InstanceArtifacts) -> bytes:
    predictions = artifacts.predictions
    if predictions is None or len(predictions) == 0:
        return _placeholder("predictions_grid: no predictions")
    params = viz.model_extra or {}
    # `n` (FR-13) with the legacy `max_items` alias; both default to 16. A recipe
    # authoring only `max_items` takes the identical legacy code path below.
    n = int(params.get("n", params.get("max_items", 16)))
    splits = params.get("splits")
    per_class = bool(params.get("per_class", False))
    if splits and "split" in predictions.columns:
        predictions = predictions[predictions["split"].isin([str(s) for s in splits])]
    if per_class and "true_label" in predictions.columns:
        # Stable sort groups the grid by true class without disturbing within-class order.
        predictions = predictions.sort_values("true_label", kind="stable")
    rows = predictions.head(n)
    n = len(rows)
    cols = min(4, n)
    grid_rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(grid_rows, cols, figsize=(cols * 1.6, grid_rows * 1.6), dpi=_DPI)
    # Labels-only grid: the bound instance does not expose per-record images here.
    flat = np.atleast_1d(axes).ravel()
    for idx, ax in enumerate(flat):
        ax.set_xticks([])
        ax.set_yticks([])
        if idx >= n:
            ax.axis("off")
            continue
        record = rows.iloc[idx]
        true_label = record.get("true_label")
        pred_label = record.get("pred_label")
        correct = true_label == pred_label
        ax.text(
            0.5,
            0.5,
            f"true: {true_label}\npred: {pred_label}",
            ha="center",
            va="center",
            color="green" if correct else "red",
        )
        for spine in ax.spines.values():
            spine.set_edgecolor("green" if correct else "red")
    fig.suptitle("Predictions")
    return _to_png(fig)


_RENDERERS = {
    "training_curves": _training_curves,
    "optimization_history": _optimization_history,
    "confusion_matrix": _confusion_matrix,
    "calibration_curve": _calibration_curve,
    "predictions_grid": _predictions_grid,
}


# --- helpers ---


def _to_png(fig: Any) -> bytes:
    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", metadata=_PNG_METADATA)
    plt.close(fig)
    return buffer.getvalue()


def _placeholder(message: str) -> bytes:
    fig, ax = plt.subplots(figsize=_FIGSIZE, dpi=_DPI)
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", color="grey")
    return _to_png(fig)


def _pick_splits(viz: VisualizationSpec, artifacts: InstanceArtifacts) -> list[str]:
    """Resolve the split(s) a split-aware viz renders over (FR-13, Story I.w).

    Precedence: an authored `splits` list → an authored single `split` → the
    evaluated splits (`Evaluation.splits`, i.e. every evaluation key **except** the
    FR-12 `baseline` block) → `["val"]`. A legacy recipe authoring `split` (or
    nothing) yields exactly one split, preserving the pre-I.w single-split figure.
    """
    params = viz.model_extra or {}
    requested = params.get("splits")
    if requested:
        return [str(s) for s in requested]
    single = params.get("split")
    if single is not None:
        return [str(single)]
    if artifacts.evaluation:
        evaluated = [s for s in artifacts.evaluation if s != "baseline"]
        if evaluated:
            return evaluated
    return ["val"]


def _evaluation_value(artifacts: InstanceArtifacts, split: str, metric: str) -> Any:
    if not artifacts.evaluation:
        return None
    return artifacts.evaluation.get(split, {}).get(metric)


def _completed_trial_values(trials: Any) -> list[float]:
    if trials is None or len(trials) == 0 or "value" not in getattr(trials, "columns", []):
        return []
    series = trials["value"].dropna()
    return [float(v) for v in series.tolist()]
