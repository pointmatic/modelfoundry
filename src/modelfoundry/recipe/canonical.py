# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-4 canonical bytes — the recipe-side input to cache identity.

This is the cache reproducibility contract. See `project-essentials.md` §
"Cache identity is the reproducibility contract — invalidations are
ceremonious."

**Every pydantic field default in `recipe/models.py` contributes to the
canonical bytes.** A "no-op refactor" that changes a default, renames a field,
or reorders fields silently shifts the canonical hash for every recipe that
omits that field — invalidating every cached ModelInstance for every user.
Bumping `SUPPORTED_SCHEMA_VERSIONS` in `recipe/loader.py` is the deliberate
invalidation lever; do not invalidate the cache by accident.
"""

from __future__ import annotations

import hashlib
import json

from modelfoundry.recipe.models import ModelRecipe


def canonical_bytes(recipe: ModelRecipe) -> bytes:
    """Render `recipe` to canonical UTF-8 JSON bytes.

    1. `model_dump(mode="json")` → a JSON-safe dict.
    2. `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
       → a compact, key-ordered, deterministic textual form.
    3. UTF-8 encode.
    """
    payload = recipe.model_dump(mode="json")
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return text.encode("utf-8")


def recipe_hash(recipe: ModelRecipe) -> str:
    """Return the full 64-hex SHA-256 digest of the recipe's canonical bytes."""
    return hashlib.sha256(canonical_bytes(recipe)).hexdigest()
