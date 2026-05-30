# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-15 OutputExpectations evaluation.

`evaluate_expectations` evaluates each `ExpectationSpec` against the produced
`evaluation/metrics.json` shape (`dict[split][metric] -> number`) and returns a
list of `ExpectationOutcome`s — the same model the manifest carries under
`output_expectations`. This module never raises on a failing expectation; the
materialize runner (C.o) inspects the outcomes and writes the `FAILED` marker
if any `passed=False` is present. Recipe-time validation (FR-2 check 14) is
B.m's job; here we evaluate what's declared and report what's observed.
"""

from __future__ import annotations

from typing import Any

from modelfoundry.core.manifest import ExpectationOutcome
from modelfoundry.recipe.models import ExpectationSpec


def evaluate_expectations(
    expectations: list[ExpectationSpec],
    evaluation_metrics: dict[str, dict[str, Any]],
) -> list[ExpectationOutcome]:
    """Evaluate each expectation; return one outcome per spec, preserving order."""
    return [_evaluate_one(spec, evaluation_metrics) for spec in expectations]


def _evaluate_one(
    spec: ExpectationSpec, evaluation_metrics: dict[str, dict[str, Any]]
) -> ExpectationOutcome:
    if spec.split not in evaluation_metrics:
        return ExpectationOutcome(
            metric=spec.metric,
            split=spec.split,
            op=spec.op,
            expected=spec.value,
            observed=None,
            passed=False,
            detail=f"split {spec.split!r} not in evaluation_metrics",
        )
    split_metrics = evaluation_metrics[spec.split]
    if spec.metric not in split_metrics:
        return ExpectationOutcome(
            metric=spec.metric,
            split=spec.split,
            op=spec.op,
            expected=spec.value,
            observed=None,
            passed=False,
            detail=f"metric {spec.metric!r} not in evaluation_metrics[{spec.split!r}]",
        )

    observed_raw = split_metrics[spec.metric]
    try:
        observed = float(observed_raw)
    except (TypeError, ValueError):
        return ExpectationOutcome(
            metric=spec.metric,
            split=spec.split,
            op=spec.op,
            expected=spec.value,
            observed=None,
            passed=False,
            detail=f"observed value {observed_raw!r} is not numeric",
        )

    passed, detail = _compare(spec.op, observed, spec.value)
    return ExpectationOutcome(
        metric=spec.metric,
        split=spec.split,
        op=spec.op,
        expected=spec.value,
        observed=observed,
        passed=passed,
        detail=detail,
    )


def _compare(
    op: str, observed: float, expected: float | tuple[float, float]
) -> tuple[bool, str | None]:
    if op == "gte":
        assert isinstance(expected, (int, float))
        return observed >= expected, None
    if op == "lte":
        assert isinstance(expected, (int, float))
        return observed <= expected, None
    if op == "eq":
        assert isinstance(expected, (int, float))
        return observed == expected, None
    if op == "within":
        if not (isinstance(expected, tuple) and len(expected) == 2):
            return False, f"op 'within' requires a 2-element range, got {expected!r}"
        lo, hi = expected
        return lo <= observed <= hi, None
    return False, f"unknown op {op!r}"
