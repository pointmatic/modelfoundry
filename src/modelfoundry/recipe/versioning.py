# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""F5 per-segment recipe versioning + migration-registry seam (Story I.g).

Phase I replaces the single global `schema_version` *gate* with a two-level scheme
(I.a spike, Decision 5):

* **Umbrella version** — the recipe's `schema_version` versions only the
  **combination function** (`join_stable` shape in `recipe/canonical`). Bumping it
  is a whole-world event: the combiner changed for *everyone*, so every cached
  ModelInstance is stale regardless of which segment a recipe uses.
* **Per-segment versions** — `core` / `plugin` / `overlays` / `extensions`, tracked
  **here in code**, NOT authored in the recipe. Keeping them out of the recipe text
  is deliberate: a recipe-level version field would enter the canonical bytes and
  trigger a *second* Phase I invalidation right after the one-time re-pin. A
  per-segment bump scopes its migration to that segment's recipes.

The **migration registry** is keyed by `(segment, from_version, to_version)` and is
**empty pre-1.0** (OR-9: zero support window — users re-materialize). The seam
exists so a post-1.0 segment bump ships its migration here without reworking the
loader; recipe-level per-segment version fields are themselves a future schema
change, landed only when migrations become necessary.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: Supported umbrella (combination-function) versions, carried as the recipe's
#: `schema_version`. The loader gates on this; bumping it is the deliberate
#: cache-invalidation lever for a combiner change.
SUPPORTED_COMBINER_VERSIONS: frozenset[int] = frozenset({1})

#: Current per-segment versions (code-tracked). To evolve a segment, bump its entry
#: here and register a `(segment, from, to)` migration below.
SEGMENT_VERSIONS: dict[str, int] = {
    "core": 1,
    "plugin": 1,
    "overlays": 1,
    "extensions": 1,
}

#: A migration transforms one segment's sub-document from `from_version` to
#: `to_version`.
SegmentMigration = Callable[[dict[str, Any]], dict[str, Any]]

#: `(segment, from_version, to_version)` -> migration. **Empty pre-1.0** (the seam
#: only). Post-1.0, a segment bump registers its migration here.
MIGRATIONS: dict[tuple[str, int, int], SegmentMigration] = {}


class MigrationError(Exception):
    """No registered migration path for a `(segment, from, to)` request."""


def migrate_segment(
    segment: str, payload: dict[str, Any], from_version: int, to_version: int
) -> dict[str, Any]:
    """Route `payload` through the registered migration chain for `segment`.

    A no-op when `from_version == to_version`. Otherwise it walks single-step
    `(segment, v, v+1)` migrations from the registry; a missing step raises
    `MigrationError` with a pointer (pre-1.0 the registry is empty, so any actual
    version gap raises — the sanctioned "refuse, re-materialize" behavior).
    """
    if from_version == to_version:
        return payload
    if from_version > to_version:
        raise MigrationError(
            f"cannot downgrade segment {segment!r} from v{from_version} to v{to_version}"
        )
    current = payload
    for step in range(from_version, to_version):
        migration = MIGRATIONS.get((segment, step, step + 1))
        if migration is None:
            raise MigrationError(
                f"no migration for segment {segment!r} v{step} -> v{step + 1} "
                f"(pre-1.0 support window is zero; re-materialize the recipe)"
            )
        current = migration(current)
    return current
