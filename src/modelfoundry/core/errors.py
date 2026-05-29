# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""ModelFoundry exception hierarchy.

A single catch-all base (`ModelfoundryError`) with one subclass per failure
domain, so downstream consumers can `except ModelfoundryError:` cleanly per the
consumer-dependency-spec BR-10. Every exception carries optional structured
context (`recipe_path`, `stage`, `detail`) for operator logs and CLI surfacing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ModelfoundryError(Exception):
    """Base for every ModelFoundry-raised error.

    `detail` round-trips through `repr` so logs and test assertions can recover
    the structured context.
    """

    def __init__(
        self,
        message: str,
        *,
        recipe_path: Path | None = None,
        stage: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.recipe_path = recipe_path
        self.stage = stage
        self.detail = detail

    def __repr__(self) -> str:
        parts = [f"message={self.message!r}"]
        if self.recipe_path is not None:
            parts.append(f"recipe_path={self.recipe_path!r}")
        if self.stage is not None:
            parts.append(f"stage={self.stage!r}")
        if self.detail is not None:
            parts.append(f"detail={self.detail!r}")
        return f"{type(self).__name__}({', '.join(parts)})"


class RecipeError(ModelfoundryError):
    """FR-1 recipe load / parse / schema-version failure."""


class ValidationError(ModelfoundryError):
    """FR-2 static validation check failure."""


class PluginError(ModelfoundryError):
    """Plugin discovery, duplicate names, or missing extras."""


class DataBindingError(ModelfoundryError):
    """FR-6 DataRefinery instance incompatibility."""


class MaterializeError(ModelfoundryError):
    """FR-3/FR-10/FR-11/FR-12 stage failure or atomic-promote failure."""


class ModelArtifactExistsError(ModelfoundryError):
    """FR-5 instance directory exists and `overwrite=False`."""


class OptimizationError(ModelfoundryError):
    """FR-11 study cannot be created, resumed, or completed."""


class ExpectationError(ModelfoundryError):
    """FR-15 OutputExpectations failure."""


class CacheError(ModelfoundryError):
    """FR-4/FR-5/FR-20 cache key, layout, or clean problem."""


class InspectionError(ModelfoundryError):
    """FR-17 requested inspection view unavailable."""


class InstanceError(ModelfoundryError):
    """FR-22 corrupt or partial instance read error."""
