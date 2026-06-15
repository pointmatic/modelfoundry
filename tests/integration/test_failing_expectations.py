# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration test — a failing OutputExpectation aborts to a FAILED marker (TR-11, E.h).

Materializes the `pytorch_failing_expectations.yml` fixture — a recipe that loads
and validates cleanly but whose `accuracy >= 0.999` expectation is unsatisfiable
— against a synthesized DataRefinery instance. The runner must abort at the
`output_expectations` stage with `ExpectationError`, leave the final instance
directory unpromoted (the cache only ever holds complete instances, FR-5), and
write the atomic `FAILED` marker naming the failing stage and the unmet
expectation (`cache.atomic` + the runner's `_gate_expectations`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import ExpectationError

torch = pytest.importorskip("torch")

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "recipes"
    / "pytorch_failing_expectations.yml"
)


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def test_failing_expectations_materialize_writes_failed_marker(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry

    data = build_dr_instance(
        tmp_path / "dr", split_counts={"train": 16, "val": 8}, image_size=8
    )
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")
    mf = ModelFoundry.from_recipe(_FIXTURE, data=data, config=config)

    with pytest.raises(ExpectationError) as exc_info:
        mf.materialize()
    assert exc_info.value.stage == "output_expectations"

    # FR-5: the cache only ever holds complete instances — nothing was promoted.
    assert not (mf.paths.instance_dir / "manifest.json").exists()

    # The atomic FAILED marker is left under .tmp for diagnosis, naming the stage,
    # the error class, and the unmet expectation.
    markers = list(config.cache_root.rglob("FAILED"))
    assert len(markers) == 1
    payload = json.loads(markers[0].read_text())
    assert payload["stage"] == "output_expectations"
    assert payload["error_class"] == "ExpectationError"
    assert "accuracy@val gte 0.999" in payload["message"]
