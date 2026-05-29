# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the ModelFoundry exception hierarchy."""

from __future__ import annotations

from pathlib import Path

import pytest

from modelfoundry import ModelfoundryError as TopLevelModelfoundryError
from modelfoundry.core.errors import (
    CacheError,
    DataBindingError,
    ExpectationError,
    InspectionError,
    InstanceError,
    MaterializeError,
    ModelArtifactExistsError,
    ModelfoundryError,
    OptimizationError,
    PluginError,
    RecipeError,
    ValidationError,
)

SUBCLASSES = [
    RecipeError,
    ValidationError,
    PluginError,
    DataBindingError,
    MaterializeError,
    ModelArtifactExistsError,
    OptimizationError,
    ExpectationError,
    CacheError,
    InspectionError,
    InstanceError,
]


@pytest.mark.parametrize("exc_cls", SUBCLASSES)
def test_every_subclass_is_a_modelfoundry_error(exc_cls: type[ModelfoundryError]) -> None:
    assert issubclass(exc_cls, ModelfoundryError)
    assert isinstance(exc_cls("boom"), ModelfoundryError)


def test_top_level_reexport_is_same_class() -> None:
    assert TopLevelModelfoundryError is ModelfoundryError


def test_can_catch_subclass_as_base() -> None:
    with pytest.raises(ModelfoundryError):
        raise RecipeError("bad recipe")


def test_context_fields_default_to_none() -> None:
    err = PluginError("missing plugin")
    assert err.message == "missing plugin"
    assert err.recipe_path is None
    assert err.stage is None
    assert err.detail is None
    assert str(err) == "missing plugin"


def test_context_fields_are_carried() -> None:
    err = MaterializeError(
        "training failed",
        recipe_path=Path("/r/recipe.yml"),
        stage="training",
        detail={"epoch": 3, "loss": 0.42},
    )
    assert err.recipe_path == Path("/r/recipe.yml")
    assert err.stage == "training"
    assert err.detail == {"epoch": 3, "loss": 0.42}


def test_detail_round_trips_through_repr() -> None:
    detail = {"check": "schema_version", "supported": [1], "got": 99}
    err = ValidationError("unsupported schema", stage="validate", detail=detail)
    text = repr(err)
    assert "ValidationError(" in text
    assert "stage='validate'" in text
    assert repr(detail) in text


def test_repr_omits_unset_optional_fields() -> None:
    text = repr(CacheError("cache miss"))
    assert text == "CacheError(message='cache miss')"
