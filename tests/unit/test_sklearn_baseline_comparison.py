# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-12 sklearn-estimator baseline comparison (Story I.t).

The grammar + class-resolution half is pure (no torch / no instance) and lives
here in the light env; the fit-on-train scoring half (`score_baseline` against a
bound DataRefinery instance) needs the torch-backed C.f feature path and is
`importorskip`-guarded below. Design pinned in
`phase-i-subphase-2-feature-code-reconciliation-plan.md` § 7 (D-I.s.1…4).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modelfoundry.plugins.sklearn.baseline import (
    ALLOWLIST,
    BaselineUnresolvable,
    parse_baseline_model_id,
    resolve_estimator_class,
)

# --- D-I.s.1: grammar (format check) ---


@pytest.mark.parametrize(
    "model_id",
    [
        "sklearn:RandomForestClassifier",
        "sklearn:LogisticRegression",
        "sklearn:DummyClassifier",
        "sklearn:SomethingNotInTheAllowlist",  # well-formed, unknown class
    ],
)
def test_parse_accepts_well_formed_ids(model_id: str) -> None:
    assert parse_baseline_model_id(model_id) == model_id.split(":", 1)[1]


@pytest.mark.parametrize(
    "model_id",
    [
        "not a valid id!!",
        "RandomForestClassifier",  # no sklearn: prefix
        "sklearn:",  # empty class name
        "sklearn:Bad-Name",  # hyphen not allowed
        "torch:Net",  # wrong prefix
        "sklearn:Foo:Bar",  # extra segment
        "",
    ],
)
def test_parse_rejects_malformed_ids(model_id: str) -> None:
    assert parse_baseline_model_id(model_id) is None


# --- D-I.s.1: allowlist resolution (semantic check) ---


def test_resolve_allowlisted_class_returns_estimator_type() -> None:
    cls = resolve_estimator_class("RandomForestClassifier")
    assert cls is not None and cls.__name__ == "RandomForestClassifier"


def test_resolve_unknown_class_returns_none() -> None:
    assert resolve_estimator_class("SomethingNotInTheAllowlist") is None


def test_allowlist_entries_all_importable_and_probabilistic() -> None:
    # Every allowlisted estimator must import and expose predict_proba so the full
    # Evaluation.metrics set (incl. ece / calibration_curve) scores uniformly.
    for name in ALLOWLIST:
        cls = resolve_estimator_class(name)
        assert cls is not None, name
        assert hasattr(cls, "predict_proba"), name


# --- score_baseline: fit-on-train (needs the torch-backed C.f feature path) ---

pytest.importorskip("torch")
pytest.importorskip("datarefinery")

from datarefinery_instances.builder import (  # type: ignore[import-not-found]  # noqa: E402
    build_dr_instance,
)

from modelfoundry.plugins.sklearn.baseline import score_baseline  # noqa: E402
from modelfoundry.recipe.models import EvaluationSpec  # noqa: E402


def _eval_spec() -> EvaluationSpec:
    return EvaluationSpec(
        splits=["train", "val"],
        primary_metric="accuracy",
        metrics=["accuracy", "macro_f1"],
        calibration_bins=10,
    )


def test_score_baseline_produces_per_split_metrics(tmp_path: Path) -> None:
    inst = build_dr_instance(tmp_path / "dr")
    out = score_baseline("sklearn:RandomForestClassifier", inst, _eval_spec(), seed=7)
    assert set(out) == {"train", "val"}
    for split in ("train", "val"):
        assert "accuracy" in out[split] and "macro_f1" in out[split]
        assert isinstance(out[split]["accuracy"], float)


def test_score_baseline_is_byte_identical_across_runs(tmp_path: Path) -> None:
    inst = build_dr_instance(tmp_path / "dr")
    spec = _eval_spec()
    a = score_baseline("sklearn:RandomForestClassifier", inst, spec, seed=7)
    b = score_baseline("sklearn:RandomForestClassifier", inst, spec, seed=7)
    assert a == b


def test_score_baseline_unknown_class_raises_unresolvable(tmp_path: Path) -> None:
    inst = build_dr_instance(tmp_path / "dr")
    with pytest.raises(BaselineUnresolvable):
        score_baseline("sklearn:NoSuchEstimator", inst, _eval_spec(), seed=7)
