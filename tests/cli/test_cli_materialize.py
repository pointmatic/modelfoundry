# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end CLI smoke — `modelfoundry materialize` (Story E.j).

The one verb that drives the orchestrator, so it is also where the JSON-lines
operational channel on `--log-target` is asserted.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

pytest.importorskip("torch")

from modelfoundry.cli.app import app


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    import torch

    yield
    torch.use_deterministic_algorithms(False)


def test_materialize_runs_and_writes_json_logs(
    cli_env: SimpleNamespace, shared_opts: list[str]
) -> None:
    result = CliRunner().invoke(
        app, [*shared_opts, "materialize", str(cli_env.recipe), "--no-progress"]
    )
    assert result.exit_code == 0
    assert "materialized" in result.stdout  # the rich success panel

    # A complete ModelInstance was promoted into the cache.
    assert next((cli_env.cache_root / "instances").rglob("manifest.json"), None) is not None

    # The operational channel on --log-target is valid JSON lines naming the stages.
    lines = [ln for ln in cli_env.log_target.read_text(encoding="utf-8").splitlines() if ln]
    records = [json.loads(ln) for ln in lines]
    assert records  # the runner logged
    assert all({"timestamp", "level", "message"} <= record.keys() for record in records)
    assert any(record["message"] == "materialize_complete" for record in records)
    assert {r.get("stage") for r in records} >= {"architecture", "training", "evaluation"}
