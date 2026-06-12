# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Shared metric implementations (Story C.j slice; extended by Story C.m).

The PyTorch evaluator (C.j) consumes `calibration_curve` from here so the
reliability diagram is computed identically across plugins. Story C.m adds the
rest of the shared sklearn-based vocabulary (`f1_score`, `confusion_matrix`,
hand-rolled ECE) and the working `MLPClassifier` baseline.

`calibration_curve` is the multiclass **confidence reliability** form: bin each
prediction by its max-probability (confidence), then report the mean confidence
and the observed accuracy within each bin — the curve a reliability diagram
plots, and the basis of expected-calibration-error.

Import-safe without `[pytorch]`: this module is pure NumPy.
"""

from __future__ import annotations

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
        raise ValueError(
            f"confidences and correct must align: {conf.shape} vs {hit.shape}"
        )
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
