# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `pipeline.expectations.evaluate_expectations`."""

from __future__ import annotations

from modelfoundry.pipeline.expectations import evaluate_expectations
from modelfoundry.recipe.models import ExpectationSpec

METRICS = {
    "val": {"accuracy": 0.85, "macro_f1": 0.83, "ece": 0.05},
    "test": {"accuracy": 0.81},
}


def _spec(metric: str, split: str, op: str, value: object) -> ExpectationSpec:
    return ExpectationSpec(metric=metric, split=split, op=op, value=value)


# --- gte ---


def test_gte_pass() -> None:
    [out] = evaluate_expectations([_spec("accuracy", "val", "gte", 0.8)], METRICS)
    assert out.passed is True
    assert out.observed == 0.85
    assert out.expected == 0.8


def test_gte_fail() -> None:
    [out] = evaluate_expectations([_spec("accuracy", "val", "gte", 0.9)], METRICS)
    assert out.passed is False
    assert out.observed == 0.85


# --- lte ---


def test_lte_pass() -> None:
    [out] = evaluate_expectations([_spec("ece", "val", "lte", 0.1)], METRICS)
    assert out.passed is True


def test_lte_fail() -> None:
    [out] = evaluate_expectations([_spec("accuracy", "val", "lte", 0.5)], METRICS)
    assert out.passed is False


# --- eq ---


def test_eq_pass() -> None:
    [out] = evaluate_expectations([_spec("accuracy", "val", "eq", 0.85)], METRICS)
    assert out.passed is True


def test_eq_fail() -> None:
    [out] = evaluate_expectations([_spec("accuracy", "val", "eq", 0.86)], METRICS)
    assert out.passed is False


# --- within (2-element list) ---


def test_within_pass_with_list_value() -> None:
    # Pydantic coerces the YAML-style list into the tuple field.
    [out] = evaluate_expectations(
        [_spec("ece", "val", "within", [0.0, 0.1])], METRICS
    )
    assert out.passed is True
    assert out.observed == 0.05


def test_within_fail_above_high() -> None:
    [out] = evaluate_expectations(
        [_spec("accuracy", "val", "within", [0.5, 0.8])], METRICS
    )
    assert out.passed is False  # 0.85 > 0.8


def test_within_fail_below_low() -> None:
    [out] = evaluate_expectations(
        [_spec("accuracy", "val", "within", [0.9, 1.0])], METRICS
    )
    assert out.passed is False  # 0.85 < 0.9


# --- missing inputs ---


def test_missing_metric_marked_failed_with_detail() -> None:
    [out] = evaluate_expectations(
        [_spec("recall", "val", "gte", 0.5)], METRICS
    )
    assert out.passed is False
    assert out.observed is None
    assert out.detail is not None and "metric 'recall'" in out.detail


def test_missing_split_marked_failed_with_detail() -> None:
    [out] = evaluate_expectations(
        [_spec("accuracy", "holdout", "gte", 0.5)], METRICS
    )
    assert out.passed is False
    assert out.observed is None
    assert out.detail is not None and "split 'holdout'" in out.detail


def test_non_numeric_observed_marked_failed() -> None:
    [out] = evaluate_expectations(
        [_spec("accuracy", "val", "gte", 0.5)],
        {"val": {"accuracy": "not-a-number"}},
    )
    assert out.passed is False
    assert out.observed is None
    assert out.detail is not None and "not numeric" in out.detail


# --- preserved order, multiple specs ---


def test_outcomes_preserve_input_order() -> None:
    specs = [
        _spec("accuracy", "val", "gte", 0.8),
        _spec("ece", "val", "lte", 0.1),
        _spec("accuracy", "test", "gte", 0.9),
    ]
    outcomes = evaluate_expectations(specs, METRICS)
    assert [o.metric for o in outcomes] == ["accuracy", "ece", "accuracy"]
    assert [o.passed for o in outcomes] == [True, True, False]
