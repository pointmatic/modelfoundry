# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""OutputExpectations contract tests — TR-11 (Story E.h).

B.l's `test_expectations.py` covers the `evaluate_expectations` evaluator in
isolation (per-op pass/fail, missing metric/split, ordering). This module covers
the surrounding TR-11 *contract*: the runner's gate that turns failing outcomes
into the abort, the requirement that **every** failure surfaces (not just the
first), and the fact that a dangling expectation is caught earlier — at validate
time (FR-2 check 14) — than at materialize time.

Plugin-agnostic and torch-free: it drives `evaluate_expectations`, the runner's
`_gate_expectations` helper, and the validator's `_check_14_…` directly. The
materialize → `FAILED` marker integration lives in
`tests/integration/test_failing_expectations.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modelfoundry.core.errors import ExpectationError
from modelfoundry.pipeline.expectations import evaluate_expectations
from modelfoundry.pipeline.runner import _gate_expectations
from modelfoundry.recipe.models import (
    DataSpec,
    EvaluationSpec,
    ExpectationSpec,
    LossSpec,
    ModelRecipe,
    OptimizerSpec,
    TrainingSpec,
)
from modelfoundry.recipe.validator import _check_14_expectations_reference_evaluated

# Observed accuracy is 0.85 on `val`; each op below is exercised both ways.
_METRICS: dict[str, dict[str, object]] = {"val": {"accuracy": 0.85}}

_PASSING: list[tuple[str, object]] = [
    ("gte", 0.5),
    ("lte", 0.99),
    ("eq", 0.85),
    ("within", [0.8, 0.9]),
]
_FAILING: list[tuple[str, object]] = [
    ("gte", 0.99),
    ("lte", 0.5),
    ("eq", 0.5),
    ("within", [0.9, 1.0]),
]


def _spec(
    op: str, value: object, *, metric: str = "accuracy", split: str = "val"
) -> ExpectationSpec:
    return ExpectationSpec(metric=metric, split=split, op=op, value=value)


# --- each op, both ways, through the runner gate ---


@pytest.mark.parametrize(("op", "value"), _FAILING)
def test_failing_op_trips_the_gate(op: str, value: object) -> None:
    outcomes = evaluate_expectations([_spec(op, value)], _METRICS)
    assert [o.passed for o in outcomes] == [False]
    with pytest.raises(ExpectationError):
        _gate_expectations(outcomes)


@pytest.mark.parametrize(("op", "value"), _PASSING)
def test_passing_op_leaves_the_gate_silent(op: str, value: object) -> None:
    outcomes = evaluate_expectations([_spec(op, value)], _METRICS)
    assert [o.passed for o in outcomes] == [True]
    _gate_expectations(outcomes)  # does not raise


# --- every failure surfaces, not just the first ---


def test_all_failures_surface_in_gate_error() -> None:
    specs = [
        _spec("gte", 0.99),  # fails (0.85 < 0.99)
        _spec("lte", 0.99),  # passes
        _spec("eq", 0.5),  # fails (0.85 != 0.5)
    ]
    outcomes = evaluate_expectations(specs, _METRICS)
    assert [o.passed for o in outcomes] == [False, True, False]

    with pytest.raises(ExpectationError) as exc_info:
        _gate_expectations(outcomes)

    # Both failures are named — the abort does not short-circuit on the first.
    failed = exc_info.value.detail["failed"]  # type: ignore[index]
    assert len(failed) == 2
    message = str(exc_info.value)
    assert "accuracy@val gte 0.99" in message
    assert "accuracy@val eq 0.5" in message


def test_gate_silent_when_every_expectation_passes() -> None:
    outcomes = evaluate_expectations([_spec("gte", 0.5), _spec("lte", 0.99)], _METRICS)
    _gate_expectations(outcomes)  # no raise


# --- a dangling expectation is caught at validate time, not deferred to materialize ---


def _recipe_with_expectation(expectation_metric: str) -> ModelRecipe:
    """A minimal valid recipe whose only declared metric is `accuracy`."""
    return ModelRecipe(
        schema_version=1,
        plugin="pytorch",
        seed=7,
        Data=DataSpec(recipe=Path("dr_recipe.yml")),
        Architecture={"num_classes": 3, "layers": [{"op": "Flatten"}]},
        Loss=LossSpec(op="cross_entropy"),
        Optimizer=OptimizerSpec(op="adamw", learning_rate=0.01),
        Training=TrainingSpec(
            max_epochs=1, batch_size=2, device="cpu", precision="fp32", checkpoint_cadence=1
        ),
        Evaluation=EvaluationSpec(
            splits=["val"], primary_metric="accuracy", metrics=["accuracy"], calibration_bins=10
        ),
        OutputExpectations=[
            ExpectationSpec(metric=expectation_metric, split="val", op="gte", value=0.5)
        ],
    )


def test_expectation_on_unproduced_metric_fails_validation() -> None:
    # `macro_f1` is not in Evaluation.metrics — check 14 flags it before any
    # training runs (the early, cheap gate; E.b covers it via the full validator).
    check = _check_14_expectations_reference_evaluated(_recipe_with_expectation("macro_f1"))
    assert check.id == 14
    assert check.passed is False
    assert "macro_f1" in (check.message or "")


def test_expectation_on_produced_metric_passes_validation() -> None:
    check = _check_14_expectations_reference_evaluated(_recipe_with_expectation("accuracy"))
    assert check.passed is True


def test_unproduced_metric_would_also_fail_at_materialize() -> None:
    # The same dangling reference is *also* caught at materialize (absent from the
    # evaluation dict → a failed outcome), confirming validate is the earlier of
    # two gates rather than the only one.
    [outcome] = evaluate_expectations([_spec("gte", 0.5, metric="macro_f1")], _METRICS)
    assert outcome.passed is False
    assert outcome.observed is None
    assert outcome.detail is not None and "macro_f1" in outcome.detail
