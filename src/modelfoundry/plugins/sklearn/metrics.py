# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Shared metric implementations (Stories C.j + C.m).

The cross-plugin metric vocabulary: `calibration_curve` (consumed by the PyTorch
evaluator since C.j so the reliability diagram is identical across plugins), plus
the C.m additions `accuracy` / `f1_score` / `confusion_matrix` (sklearn) and the
hand-rolled `expected_calibration_error`. The sklearn `MLPClassifier` baseline
(C.m) scores against these.

`calibration_curve` is the multiclass **confidence reliability** form: bin each
prediction by its max-probability (confidence), then report the mean confidence
and the observed accuracy within each bin — the curve a reliability diagram
plots, and the basis of expected-calibration-error.

The `calibration_curve` / `expected_calibration_error` paths are pure NumPy;
`accuracy` / `f1_score` / `confusion_matrix` import `sklearn.metrics` lazily
(scikit-learn is a base dependency).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt


def calibration_curve(
    confidences: npt.ArrayLike,
    correct: npt.ArrayLike,
    *,
    n_bins: int = 10,
) -> dict[str, list[float]]:
    """Per-bin confidence-reliability curve over equal-width confidence bins.

    `confidences[i]` is the model's max class probability for sample `i`;
    `correct[i]` is 1.0 if that prediction was right, else 0.0. Bins span
    `[0, 1]` in `n_bins` equal-width buckets; empty bins are dropped. Returns
    parallel lists `bin_lower` / `bin_upper` / `mean_confidence` /
    `accuracy` / `count` ordered by ascending confidence.
    """
    conf = np.asarray(confidences, dtype=np.float64).ravel()
    hit = np.asarray(correct, dtype=np.float64).ravel()
    if conf.shape != hit.shape:
        raise ValueError(f"confidences and correct must align: {conf.shape} vs {hit.shape}")
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # `digitize` with right=True puts confidence==1.0 in the last bin, not out of range.
    bin_idx = np.clip(np.digitize(conf, edges[1:-1], right=True), 0, n_bins - 1)

    out: dict[str, list[float]] = {
        "bin_lower": [],
        "bin_upper": [],
        "mean_confidence": [],
        "accuracy": [],
        "count": [],
    }
    for b in range(n_bins):
        mask = bin_idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        out["bin_lower"].append(float(edges[b]))
        out["bin_upper"].append(float(edges[b + 1]))
        out["mean_confidence"].append(float(conf[mask].mean()))
        out["accuracy"].append(float(hit[mask].mean()))
        out["count"].append(float(n))
    return out


def expected_calibration_error(
    confidences: npt.ArrayLike,
    correct: npt.ArrayLike,
    *,
    n_bins: int = 10,
) -> float:
    """Hand-rolled ECE: the count-weighted mean `|confidence - accuracy|` over bins."""
    curve = calibration_curve(confidences, correct, n_bins=n_bins)
    total = sum(curve["count"])
    if total == 0:
        return 0.0
    return (
        sum(
            count * abs(conf - acc)
            for count, conf, acc in zip(
                curve["count"], curve["mean_confidence"], curve["accuracy"], strict=True
            )
        )
        / total
    )


def accuracy(y_true: npt.ArrayLike, y_pred: npt.ArrayLike) -> float:
    """Overall accuracy (`sklearn.metrics.accuracy_score`)."""
    from sklearn.metrics import accuracy_score  # type: ignore[import-untyped]

    return float(accuracy_score(y_true, y_pred))


def f1_score(
    y_true: npt.ArrayLike,
    y_pred: npt.ArrayLike,
    *,
    labels: list[Any],
    average: str | None = "macro",
) -> Any:
    """F1 over `labels` (`sklearn.metrics.f1_score`); `average=None` → per-class list."""
    from sklearn.metrics import f1_score as _f1

    score = _f1(y_true, y_pred, labels=labels, average=average, zero_division=0)
    return float(score) if average is not None else [float(x) for x in score]


def precision_score(
    y_true: npt.ArrayLike, y_pred: npt.ArrayLike, *, labels: list[Any]
) -> list[float]:
    """Per-class precision over `labels` (`sklearn.metrics.precision_score`)."""
    from sklearn.metrics import precision_score as _p

    return [float(x) for x in _p(y_true, y_pred, labels=labels, average=None, zero_division=0)]


def recall_score(y_true: npt.ArrayLike, y_pred: npt.ArrayLike, *, labels: list[Any]) -> list[float]:
    """Per-class recall over `labels` (`sklearn.metrics.recall_score`)."""
    from sklearn.metrics import recall_score as _r

    return [float(x) for x in _r(y_true, y_pred, labels=labels, average=None, zero_division=0)]


def confusion_matrix(
    y_true: npt.ArrayLike, y_pred: npt.ArrayLike, *, labels: list[Any]
) -> np.ndarray:
    """Confusion matrix over `labels` (`sklearn.metrics.confusion_matrix`)."""
    from sklearn.metrics import confusion_matrix as _cm

    return np.asarray(_cm(y_true, y_pred, labels=labels), dtype=np.int64)


def score_split(
    requested: set[str],
    y_true: npt.ArrayLike,
    y_pred: npt.ArrayLike,
    proba: npt.ArrayLike,
    *,
    labels: list[Any],
    n_bins: int,
) -> dict[str, Any]:
    """The shared scalar/per-class scorer over one split's predictions.

    Computes only the requested scalar + per-class metrics (`accuracy` / `macro_f1`
    / `per_class_f1` / `per_class_precision` / `per_class_recall` / `ece`); the
    nested `confusion_matrix` / `calibration_curve` metrics are handled by callers
    that also persist their sidecars. Shared by the sklearn baseline plugin
    (Story C.m) and the FR-12 baseline comparison (Story I.t) so the two never drift.
    """
    proba = np.asarray(proba)
    out: dict[str, Any] = {}
    if "accuracy" in requested:
        out["accuracy"] = accuracy(y_true, y_pred)
    if "macro_f1" in requested:
        out["macro_f1"] = f1_score(y_true, y_pred, labels=labels, average="macro")
    if "per_class_f1" in requested:
        out["per_class_f1"] = f1_score(y_true, y_pred, labels=labels, average=None)
    if "per_class_precision" in requested:
        out["per_class_precision"] = precision_score(y_true, y_pred, labels=labels)
    if "per_class_recall" in requested:
        out["per_class_recall"] = recall_score(y_true, y_pred, labels=labels)
    if "ece" in requested:
        out["ece"] = expected_calibration_error(
            proba.max(axis=1),
            (np.asarray(y_pred) == np.asarray(y_true)).astype(float),
            n_bins=n_bins,
        )
    return out
