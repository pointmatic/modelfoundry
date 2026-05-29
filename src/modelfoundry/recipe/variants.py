# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-14 variant overlay.

`apply_variant(recipe_dict, variant_name)` deep-merges a named overlay from the
recipe's `variants.<name>` block onto the base recipe, returning a new dict for
final pydantic construction. The returned dict always has `variants` cleared so
cache identity reflects only the applied semantics — editing or adding an unused
variant never invalidates cached instances of other variants (cf.
`project-essentials.md` § Cache identity is the reproducibility contract).

Merge semantics: nested mappings merge recursively; any non-mapping value
(scalars, lists) replaces the base value wholesale.
"""

from __future__ import annotations

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


def apply_variant(recipe_dict: dict[str, Any], variant_name: str | None) -> dict[str, Any]:
    """Return a new recipe dict with the named overlay applied and `variants` cleared.

    `variant_name=None` clears `variants` without applying any overlay. An
    unknown variant name raises `RecipeError` listing the declared variants.
    """
    variants = recipe_dict.get("variants", {})
    if not isinstance(variants, dict):
        raise RecipeError(
            f"recipe 'variants' must be a mapping, got {type(variants).__name__}"
        )

    if variant_name is None:
        merged = dict(recipe_dict)
    else:
        if variant_name not in variants:
            raise RecipeError(
                f"unknown variant {variant_name!r}; declared variants: "
                f"{sorted(variants.keys())}",
                detail={"variant": variant_name, "available": sorted(variants.keys())},
            )
        overlay = variants[variant_name]
        if not isinstance(overlay, dict):
            raise RecipeError(
                f"variant {variant_name!r} overlay must be a mapping, "
                f"got {type(overlay).__name__}"
            )
        merged = _deep_merge(recipe_dict, overlay)

    merged["variants"] = {}
    return merged
