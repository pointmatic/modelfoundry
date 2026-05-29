# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-4 cache identity — the ModelInstance directory key.

The cache key has three components:

- `recipe_hash16` — first 16 hex of the canonical recipe hash (`recipe.canonical`).
- `data_instance_hash16` — the bound DataRefinery instance reduced to a single
  16-hex unit: XOR of the instance's `recipe_hash`, `input_hash` (each first-16
  hex → 64-bit), and the DataRefinery-side `seed`.
- `seed` — the ModelFoundry-side master seed (a separate component).

**Loose coupling (CR-15 / `project-essentials.md` § Loose-coupled DataRefinery
binding).** ModelFoundry treats the upstream instance as a single hashed unit:
its `recipe_hash` feeds `data_instance_hash16` but is *not* mixed into the
ModelFoundry recipe's own `recipe_hash16`. Re-materializing DataRefinery into
the *same* cache directory (same triple) is therefore a no-op for ModelFoundry's
cache identity — the user re-materializes ModelFoundry explicitly to pick up
upstream changes. Do not mix the upstream hash into `recipe_hash16`; that is the
deferred tight-coupling upgrade (FR-26), gated by a `schema_version` bump.
"""

from __future__ import annotations

from dataclasses import dataclass

from modelfoundry.recipe.canonical import recipe_hash
from modelfoundry.recipe.models import ModelRecipe

_HASH16_HEXLEN = 16
_MASK64 = (1 << 64) - 1

# (DataRefinery recipe_hash, input_hash, seed) — the bound instance's identity.
DataInstanceTriple = tuple[str, str, int]


@dataclass(frozen=True)
class CacheKey:
    recipe_hash16: str
    data_instance_hash16: str
    seed: int


def _xor_data_instance(triple: DataInstanceTriple) -> str:
    """Reduce the DataRefinery instance triple to a single 16-hex unit.

    Each hash contributes its first 16 hex (64 bits); the DataRefinery seed is
    XORed in as a full 64-bit operand so it participates in the result rather
    than being lost to truncation.
    """
    dr_recipe_hash, dr_input_hash, dr_seed = triple
    a = int(dr_recipe_hash[:_HASH16_HEXLEN], 16)
    b = int(dr_input_hash[:_HASH16_HEXLEN], 16)
    combined = (a ^ b ^ (dr_seed & _MASK64)) & _MASK64
    return f"{combined:016x}"


def cache_key(
    recipe: ModelRecipe,
    data_instance_triple: DataInstanceTriple,
    seed: int,
) -> CacheKey:
    """Compute the `CacheKey` for `recipe` bound to a DataRefinery instance.

    `data_instance_triple` is the bound instance's `(recipe_hash, input_hash,
    seed)`. The full recipe hash is recorded separately in `manifest.json`.
    """
    return CacheKey(
        recipe_hash16=recipe_hash(recipe)[:_HASH16_HEXLEN],
        data_instance_hash16=_xor_data_instance(data_instance_triple),
        seed=seed,
    )
