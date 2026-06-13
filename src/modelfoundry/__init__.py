# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""ModelFoundry — compile a YAML recipe into a reproducible trained-model instance.

Public API re-exports are added as the package is built out (see docs/specs/stories.md).
The pre-production scaffold exposes only the version string.
"""

from modelfoundry._version import __version__
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
from modelfoundry.core.instance import ModelInstance
from modelfoundry.core.modelfoundry import ModelFoundry, materialize

__all__ = [
    "CacheError",
    "DataBindingError",
    "ExpectationError",
    "InspectionError",
    "InstanceError",
    "MaterializeError",
    "ModelArtifactExistsError",
    "ModelFoundry",
    "ModelInstance",
    "ModelfoundryError",
    "OptimizationError",
    "PluginError",
    "RecipeError",
    "ValidationError",
    "__version__",
    "materialize",
]
