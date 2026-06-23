# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-14 overlay application.

`apply_overlays(recipe_dict, overlay_names)` deep-merges an **ordered sequence**
of named overlays from the recipe's `overlays.<name>` blocks onto the base
recipe, returning a new dict for final pydantic construction. Overlays apply
left-to-right with **last-writer-wins per section**. The returned dict always
has `overlays` cleared so cache identity reflects only the applied semantics —
editing or adding an unused overlay never invalidates cached instances that
select other overlays (cf. `project-essentials.md` § Cache identity is the
reproducibility contract).

Merge semantics: nested mappings merge recursively; any non-mapping value
(scalars, lists) replaces the base value wholesale. Mirrors DataRefinery's
`overlays` standard — the governed cross-tool-family contract (`overlays` widened
from a single `variant` in DataRefinery v0.23 / ModelFoundry Story I.j.2).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from modelfoundry.core.errors import RecipeError


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def apply_overlays(
    recipe_dict: dict[str, Any], overlay_names: Sequence[str] | None
) -> dict[str, Any]:
    """Return a new recipe dict with the named overlays applied and `overlays` cleared.

    `overlay_names` applies left-to-right (last-writer-wins per section); an empty
    sequence or `None` clears `overlays` without applying any overlay. An unknown
    overlay name raises `RecipeError` listing the declared overlays.
    """
    overlays = recipe_dict.get("overlays", {})
    if not isinstance(overlays, dict):
        raise RecipeError(f"recipe 'overlays' must be a mapping, got {type(overlays).__name__}")

    merged = dict(recipe_dict)
    for name in overlay_names or []:
        if name not in overlays:
            raise RecipeError(
                f"unknown overlay {name!r}; declared overlays: {sorted(overlays.keys())}",
                detail={"overlay": name, "available": sorted(overlays.keys())},
            )
        overlay = overlays[name]
        if not isinstance(overlay, dict):
            raise RecipeError(f"overlay {name!r} must be a mapping, got {type(overlay).__name__}")
        merged = _deep_merge(merged, overlay)

    merged["overlays"] = {}
    return merged
