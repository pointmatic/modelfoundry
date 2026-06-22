# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-4 / F1 canonical bytes — the recipe-side input to cache identity.

This is the cache reproducibility contract. See `project-essentials.md` §
"Cache identity is the reproducibility contract — invalidations are
ceremonious."

**Segmented identity (Phase I).** Identity is no longer a single total
`model_dump`. The recipe's fields are partitioned into independently-hashed
**segments** — `core` / `plugin` / `overlays` (per the I.a spike, Decision 2,
`docs/spikes/I.a-segmented-recipe-identity.md`) — and combined by `join_stable`:
a labeled, length-framed concatenation of per-segment SHA-256 digests. An empty
segment is **sparse-omitted** (contributes nothing), so introducing an
optional segment (e.g. `extensions`, Story I.d) for everyone-empty is a no-op.
The combiner is **prefix-capable** (`H(H_upstream ‖ segment)`) so the deferred
vertical stage-waterfall can layer on later without re-specifying it.

The recipe stays **flat on disk**; segmentation lives only here in the hashing.
The cross-plugin isolation guarantee (a sklearn-surface change must not move a
PyTorch recipe's hash) is delivered by **sparse hashing + no-implicit-defaults**
(matures in I.c/I.e); this module lands the combiner and the partition.

> The exact `join_stable` byte format is the I.a deliverable and a **cross-repo
> coordination point** with DataRefinery's `join_stable` (a governed shared
> family standard, spike §3). DataRefinery has not yet implemented it; when it
> does, confirm the two formats byte-for-byte and reconcile (pre-1.0, a divergence
> is a cheap re-materialize).

Because every authored field still participates, a change to a pydantic field
default, a field rename/reorder, or the combiner itself shifts the canonical
hash. Bumping `SUPPORTED_SCHEMA_VERSIONS` in `recipe/loader.py` is the deliberate
invalidation lever; do not invalidate the cache by accident.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from modelfoundry.recipe.models import ModelRecipe

# Segment partition (I.a Decision 2). The recipe is flat on disk; these group its
# fields into the independently-hashed segments. `overlays` carries the selected
# variant's resolved delta — but the loader merges and clears `variants` pre-hash
# (see `recipe.variants.apply_variant`), so it is empty (⇒ sparse) until overlays
# become first-class (deferred). The core/plugin boundary firms up in I.c/I.e.
_CORE_FIELDS: tuple[str, ...] = ("schema_version", "plugin", "seed", "Data")
_PLUGIN_FIELDS: tuple[str, ...] = (
    "Architecture",
    "Loss",
    "Optimizer",
    "Training",
    "Optimization",
    "Inference",
    "Evaluation",
    "Visualizations",
    "OutputExpectations",
)
_OVERLAY_FIELD = "variants"

# Framed-label for the optional upstream prefix digest (vertical axis). The
# leading NUL keeps it out of the namespace of any real segment label.
_UPSTREAM_LABEL = b"\x00upstream"


def recipe_segments(recipe: ModelRecipe) -> dict[str, Any]:
    """Partition `recipe` into its `core` / `plugin` / `overlays` segments.

    Each value is a JSON-safe sub-document (from `model_dump(mode="json")`).
    Empty segments are kept here (the combiner sparse-omits them) so callers can
    inspect the full partition.
    """
    dump = recipe.model_dump(mode="json")
    core = {k: dump[k] for k in _CORE_FIELDS if k in dump}
    plugin = {k: dump[k] for k in _PLUGIN_FIELDS if k in dump}
    overlays = dump.get(_OVERLAY_FIELD, {})
    return {"core": core, "plugin": plugin, "overlays": overlays}


def _segment_canonical(value: Any) -> bytes | None:
    """Canonical UTF-8 JSON bytes for one segment's sub-document.

    Returns `None` for a sparse (absent / `None` / empty-collection) segment so
    the combiner omits it. The sort + compact separators make the bytes
    insensitive to authoring order/whitespace within the segment.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)) and len(value) == 0:
        return None
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _frame(label: bytes, payload: bytes) -> bytes:
    """Length-prefix a (label, payload) pair so boundaries are unambiguous."""
    return len(label).to_bytes(4, "big") + label + len(payload).to_bytes(4, "big") + payload


def _combiner_preimage(segments: dict[str, Any], upstream: bytes | None) -> bytes:
    """The framed concatenation that `join_stable` hashes.

    Labels are sorted for order-independence; an optional `upstream` digest is
    framed first (prefix composition for the deferred vertical axis).
    """
    parts: list[bytes] = []
    if upstream is not None:
        parts.append(_frame(_UPSTREAM_LABEL, upstream))
    for label in sorted(segments):
        payload = _segment_canonical(segments[label])
        if payload is None:
            continue  # sparse: an empty/absent segment contributes nothing
        parts.append(_frame(label.encode("utf-8"), hashlib.sha256(payload).digest()))
    return b"".join(parts)


def join_stable(segments: dict[str, Any], *, upstream: bytes | None = None) -> bytes:
    """Combine per-segment digests into one stable 32-byte identity digest.

    `segments` maps a segment label to its JSON-safe sub-document; each is hashed
    independently and framed. `upstream`, when given, is a prior digest folded in
    as a prefix (`H(H_upstream ‖ segments)`) — unused by `canonical_bytes` today,
    kept for the deferred vertical stage-waterfall.
    """
    return hashlib.sha256(_combiner_preimage(segments, upstream)).digest()


def canonical_bytes(recipe: ModelRecipe) -> bytes:
    """The combiner pre-image for `recipe` — `sha256` of this is `recipe_hash`.

    No longer JSON text: it is the length-framed concatenation of the recipe's
    per-segment digests (`recipe_segments` → `join_stable`). Cosmetic edits
    within a segment leave it unchanged (each segment is canonicalized sorted +
    compact); a semantic edit in any segment changes it.
    """
    return _combiner_preimage(recipe_segments(recipe), None)


def recipe_hash(recipe: ModelRecipe) -> str:
    """Return the full 64-hex SHA-256 digest of the recipe's canonical bytes."""
    return hashlib.sha256(canonical_bytes(recipe)).hexdigest()
