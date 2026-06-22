# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.versioning` — the per-segment version scheme + seam (I.g).

The recipe carries a single umbrella `schema_version` (combination-function
version); per-segment versions + the migration registry live in code. The registry
is the seam only (empty pre-1.0); these tests exercise the routing mechanism so a
post-1.0 segment bump can register a migration without reworking the loader.
"""

from __future__ import annotations

from typing import Any

import pytest

from modelfoundry.recipe.loader import SUPPORTED_SCHEMA_VERSIONS
from modelfoundry.recipe.versioning import (
    MIGRATIONS,
    SEGMENT_VERSIONS,
    SUPPORTED_COMBINER_VERSIONS,
    MigrationError,
    migrate_segment,
)


def test_segment_versions_cover_the_four_segments() -> None:
    assert set(SEGMENT_VERSIONS) == {"core", "plugin", "overlays", "extensions"}
    assert all(v == 1 for v in SEGMENT_VERSIONS.values())


def test_umbrella_supported_set_is_v1() -> None:
    assert frozenset({1}) == SUPPORTED_COMBINER_VERSIONS


def test_loader_umbrella_alias_matches_combiner_versions() -> None:
    # The recipe's `schema_version` gate (validator check 1 / loader) IS the umbrella.
    assert SUPPORTED_SCHEMA_VERSIONS == SUPPORTED_COMBINER_VERSIONS


def test_migration_registry_is_empty_pre_1_0() -> None:
    # The seam only: no migrations are written pre-1.0 (OR-9 zero support window).
    assert MIGRATIONS == {}


def test_migrate_segment_same_version_is_noop() -> None:
    payload = {"op": "adamw", "learning_rate": 0.001}
    assert migrate_segment("plugin", payload, 1, 1) is payload


def test_migrate_segment_missing_migration_refuses_with_pointer() -> None:
    with pytest.raises(MigrationError, match="re-materialize"):
        migrate_segment("plugin", {"x": 1}, 1, 2)


def test_migrate_segment_downgrade_refused() -> None:
    with pytest.raises(MigrationError, match="downgrade"):
        migrate_segment("core", {"seed": 7}, 2, 1)


def test_migrate_segment_routes_through_registered_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Prove the seam works: register single-step migrations and confirm chaining.
    def v1_to_v2(p: dict[str, Any]) -> dict[str, Any]:
        return {**p, "added_in_v2": True}

    def v2_to_v3(p: dict[str, Any]) -> dict[str, Any]:
        return {**p, "added_in_v3": True}

    monkeypatch.setitem(MIGRATIONS, ("plugin", 1, 2), v1_to_v2)
    monkeypatch.setitem(MIGRATIONS, ("plugin", 2, 3), v2_to_v3)
    out = migrate_segment("plugin", {"op": "adamw"}, 1, 3)
    assert out == {"op": "adamw", "added_in_v2": True, "added_in_v3": True}
