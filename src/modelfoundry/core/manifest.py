# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`manifest.json` — the per-ModelInstance metadata document.

Written by the materialize runner at promote time; read by `status`,
`inspect`, `ModelInstance.load`, and any downstream consumer. The model is
pretty-printed (indent=2, sorted keys) so diffs stay readable across runs while
the byte form remains stable for goldens. UTC ISO 8601 timestamps are produced
by pydantic's default datetime serialization.

The pre-production schema is `schema_version: int = 1`. Bumping it is a
ceremonious cache-invalidating change (see `project-essentials.md` § Cache
identity is the reproducibility contract).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class ManifestWarning(BaseModel):
    """A non-fatal issue observed during materialization."""

    model_config = ConfigDict(extra="forbid")

    stage: str | None = None
    message: str


class OptimizationManifest(BaseModel):
    """Summary of the Optimization stage (FR-11), if one ran."""

    model_config = ConfigDict(extra="forbid")

    sampler: str
    pruner: str
    n_trials: int
    best_trial_number: int | None = None
    best_value: float | None = None


class ExpectationOutcome(BaseModel):
    """Result of evaluating one `OutputExpectations` entry (FR-15)."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    split: str
    op: Literal["gte", "lte", "eq", "within"]
    expected: float | tuple[float, float]
    observed: float | None = None
    passed: bool
    detail: str | None = None


class Manifest(BaseModel):
    """The `manifest.json` document for one ModelInstance."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    plugin: str
    plugin_version: str
    recipe_hash: str
    data_instance_hash: str
    bound_data_instance: Path
    seed: int
    variant: str | None
    created_at: datetime
    elapsed_seconds: float
    warnings: list[ManifestWarning] = []
    is_partial: bool = False
    failed_stage: str | None = None
    epoch_history: int
    optimization: OptimizationManifest | None = None
    evaluation: dict[str, dict[str, Any]]
    output_expectations: list[ExpectationOutcome]
    byte_identity_guaranteed: bool = True
    metric_tolerance: float | None = None

    @model_validator(mode="after")
    def _tolerance_required_when_byte_identity_off(self) -> Manifest:
        if not self.byte_identity_guaranteed and self.metric_tolerance is None:
            raise ValueError(
                "byte_identity_guaranteed=False requires metric_tolerance to be set "
                "(e.g., when Training.precision='amp')"
            )
        return self

    def write(self, path: str | Path) -> None:
        """Write the manifest as sorted, indent=2 JSON at `path` (parents created)."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(mode="json")
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        path.write_text(text, encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Manifest:
        """Parse and validate the manifest at `path`."""
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
