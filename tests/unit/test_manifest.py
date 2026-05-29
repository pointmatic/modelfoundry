# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `core.manifest`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from modelfoundry.core.manifest import (
    ExpectationOutcome,
    Manifest,
    ManifestWarning,
    OptimizationManifest,
)


def _representative_manifest() -> Manifest:
    return Manifest(
        plugin="pytorch",
        plugin_version="1",
        recipe_hash="a" * 64,
        data_instance_hash="b" * 16,
        bound_data_instance=Path("/some/dr_cache/instances/aa/bb/7"),
        seed=42,
        variant="big_batch",
        created_at=datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC),
        elapsed_seconds=123.456,
        warnings=[ManifestWarning(stage="training", message="early-stop triggered")],
        epoch_history=10,
        optimization=OptimizationManifest(
            sampler="tpe",
            pruner="median",
            n_trials=20,
            best_trial_number=7,
            best_value=0.87,
        ),
        evaluation={"val": {"accuracy": 0.85, "macro_f1": 0.83}},
        output_expectations=[
            ExpectationOutcome(
                metric="accuracy",
                split="val",
                op="gte",
                expected=0.8,
                observed=0.85,
                passed=True,
            )
        ],
    )


def test_round_trip(tmp_path: Path) -> None:
    original = _representative_manifest()
    path = tmp_path / "manifest.json"
    original.write(path)
    loaded = Manifest.load(path)
    assert loaded == original


def test_pretty_printed_and_sorted(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    _representative_manifest().write(path)
    text = path.read_text()
    assert "\n  " in text  # indented
    # Top-level keys are sorted (so the file is `byte_identity_guaranteed` first).
    first_key_line = next(ln for ln in text.splitlines() if ln.startswith('  "'))
    assert first_key_line.startswith('  "bound_data_instance"')


def test_write_is_byte_stable(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _representative_manifest().write(a)
    _representative_manifest().write(b)
    assert a.read_bytes() == b.read_bytes()


def test_created_at_is_iso_utc(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    _representative_manifest().write(path)
    text = path.read_text()
    assert '"created_at": "2026-05-28T12:00:00Z"' in text or (
        '"created_at": "2026-05-28T12:00:00+00:00"' in text
    )


def test_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        Manifest(  # type: ignore[call-arg]
            plugin="pytorch",
            plugin_version="1",
            # recipe_hash missing
            data_instance_hash="b" * 16,
            bound_data_instance=Path("/x"),
            seed=42,
            variant=None,
            created_at=datetime(2026, 5, 28, tzinfo=UTC),
            elapsed_seconds=1.0,
            epoch_history=0,
            evaluation={},
            output_expectations=[],
        )


def test_byte_identity_false_requires_metric_tolerance() -> None:
    base = dict(
        plugin="pytorch",
        plugin_version="1",
        recipe_hash="a" * 64,
        data_instance_hash="b" * 16,
        bound_data_instance=Path("/x"),
        seed=42,
        variant=None,
        created_at=datetime(2026, 5, 28, tzinfo=UTC),
        elapsed_seconds=1.0,
        epoch_history=0,
        evaluation={},
        output_expectations=[],
    )
    with pytest.raises(ValidationError, match="metric_tolerance"):
        Manifest(**base, byte_identity_guaranteed=False)
    # Providing the tolerance makes it valid.
    Manifest(**base, byte_identity_guaranteed=False, metric_tolerance=0.01)


def test_amp_amp_pattern_works() -> None:
    # The documented AMP pattern: identity off + tolerance set.
    m = Manifest(
        plugin="pytorch",
        plugin_version="1",
        recipe_hash="a" * 64,
        data_instance_hash="b" * 16,
        bound_data_instance=Path("/x"),
        seed=42,
        variant=None,
        created_at=datetime(2026, 5, 28, tzinfo=UTC),
        elapsed_seconds=1.0,
        epoch_history=0,
        evaluation={},
        output_expectations=[],
        byte_identity_guaranteed=False,
        metric_tolerance=0.005,
    )
    assert m.byte_identity_guaranteed is False
    assert m.metric_tolerance == 0.005


def test_expectation_outcome_within_op_accepts_tuple() -> None:
    eo = ExpectationOutcome(
        metric="ece",
        split="val",
        op="within",
        expected=(0.0, 0.1),
        observed=0.05,
        passed=True,
    )
    assert eo.expected == (0.0, 0.1)


def test_extra_keys_rejected() -> None:
    with pytest.raises(ValidationError):
        ManifestWarning(stage="x", message="m", bogus=1)  # type: ignore[call-arg]
