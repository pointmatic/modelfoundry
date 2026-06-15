# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch metric golden-value tests — TR-9 (Story E.g).

Each pre-production metric is validated against a *hand-computed* golden on one
tiny fixed `(probs, targets)` fixture, exercising the exact entry points the
evaluator uses (`evaluation._compute_metrics` / `_confusion` / `_calibration`).
This pins the metric vocabulary so a silent implementation shift (a different
torchmetrics default, an averaging change) is caught — which matters beyond
correctness: post-production a metric-value drift perturbs the materialized
output bytes and is a cache-invalidating event (`project-essentials.md` § Cache
identity is the reproducibility contract).

The fixture — 6 samples, 3 classes — and every golden are derived by hand in the
comments below; the confusion matrix, precision/recall/F1, accuracy, ECE, and
the reliability curve are all computed from first principles, not read back from
the implementation.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from modelfoundry.plugins.pytorch.evaluation import (  # noqa: E402
    _calibration,
    _compute_metrics,
    _confusion,
)

# Fixture — argmax(probs) gives the prediction, max(probs) the confidence:
#
#   i | target | pred | confidence | correct
#   0 |   0    |  0   |   0.92     |   ✓
#   1 |   0    |  1   |   0.63     |   ✗
#   2 |   1    |  1   |   0.81     |   ✓
#   3 |   1    |  1   |   0.74     |   ✓
#   4 |   2    |  2   |   0.66     |   ✓
#   5 |   2    |  0   |   0.55     |   ✗
_PROBS = torch.tensor(
    [
        [0.92, 0.05, 0.03],
        [0.30, 0.63, 0.07],
        [0.10, 0.81, 0.09],
        [0.16, 0.74, 0.10],
        [0.20, 0.14, 0.66],
        [0.55, 0.25, 0.20],
    ]
)
_TARGETS = torch.tensor([0, 0, 1, 1, 2, 2])
_NUM_CLASSES = 3
_N_BINS = 10


def _metric(name: str) -> object:
    return _compute_metrics({name}, _PROBS, _TARGETS, _NUM_CLASSES, _N_BINS)[name]


def test_accuracy_golden() -> None:
    # 4 of 6 predictions correct (i0, i2, i3, i4) → 4/6.
    assert _metric("accuracy") == pytest.approx(4 / 6)


def test_confusion_matrix_golden() -> None:
    # rows = true class, cols = predicted class.
    #   true 0: pred {0, 1}      → [1, 1, 0]
    #   true 1: pred {1, 1}      → [0, 2, 0]
    #   true 2: pred {2, 0}      → [1, 0, 1]
    preds = _PROBS.argmax(dim=1)
    assert _confusion(preds, _TARGETS, _NUM_CLASSES).tolist() == [[1, 1, 0], [0, 2, 0], [1, 0, 1]]


def test_per_class_precision_golden() -> None:
    # precision = TP / (TP + FP) over the predicted column:
    #   class 0: TP=1 (i0), FP=1 (i5) → 1/2
    #   class 1: TP=2 (i2,i3), FP=1 (i1) → 2/3
    #   class 2: TP=1 (i4), FP=0 → 1
    assert _metric("per_class_precision") == pytest.approx([0.5, 2 / 3, 1.0])


def test_per_class_recall_golden() -> None:
    # recall = TP / (TP + FN) over the true row:
    #   class 0: TP=1 (i0), FN=1 (i1) → 1/2
    #   class 1: TP=2 (i2,i3), FN=0 → 1
    #   class 2: TP=1 (i4), FN=1 (i5) → 1/2
    assert _metric("per_class_recall") == pytest.approx([0.5, 1.0, 0.5])


def test_per_class_f1_golden() -> None:
    # F1 = 2PR/(P+R) per class:
    #   class 0: 2·.5·.5/(1.0)            = 0.5
    #   class 1: 2·(2/3)·1/((2/3)+1)      = 0.8
    #   class 2: 2·1·.5/(1.5)             = 2/3
    assert _metric("per_class_f1") == pytest.approx([0.5, 0.8, 2 / 3])


def test_macro_f1_golden() -> None:
    # unweighted mean of the per-class F1s: (0.5 + 0.8 + 2/3) / 3.
    assert _metric("macro_f1") == pytest.approx((0.5 + 0.8 + 2 / 3) / 3)


def test_ece_golden() -> None:
    # ECE (l1) = count-weighted mean |confidence - accuracy| over confidence bins.
    # Confidence bins (width 0.1) over the fixture:
    #   [0.5,0.6): {0.55→✗}                  count 1, conf .55,  acc 0.0
    #   [0.6,0.7): {0.63→✗, 0.66→✓}          count 2, conf .645, acc 0.5
    #   [0.7,0.8): {0.74→✓}                  count 1, conf .74,  acc 1.0
    #   [0.8,0.9): {0.81→✓}                  count 1, conf .81,  acc 1.0
    #   [0.9,1.0): {0.92→✓}                  count 1, conf .92,  acc 1.0
    # ECE = (1·.55 + 2·.145 + 1·.26 + 1·.19 + 1·.08) / 6 = 1.37 / 6.
    assert _metric("ece") == pytest.approx(1.37 / 6, abs=1e-6)


def test_calibration_curve_golden() -> None:
    # The reliability curve underlying the ECE above (ascending confidence,
    # empty bins dropped). Bin edges are the equal-width 0.1 buckets.
    curve = _calibration(_PROBS, _TARGETS, _N_BINS)
    assert curve["bin_lower"] == pytest.approx([0.5, 0.6, 0.7, 0.8, 0.9])
    assert curve["bin_upper"] == pytest.approx([0.6, 0.7, 0.8, 0.9, 1.0])
    assert curve["mean_confidence"] == pytest.approx([0.55, 0.645, 0.74, 0.81, 0.92])
    assert curve["accuracy"] == pytest.approx([0.0, 0.5, 1.0, 1.0, 1.0])
    assert curve["count"] == pytest.approx([1, 2, 1, 1, 1])
