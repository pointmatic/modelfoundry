# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""F2 discriminated-union plugin-surface resolution (Story I.c).

The recipe stays **flat on disk**, but a plugin's op-bearing sections — `Loss`,
`Optimizer`, `Optimizer.schedule`, and each `Visualizations[i]` — form a
**discriminated union**: the **op name is the discriminator** and the plugin's
registered `OperationSpec.param_model`s are the **variants** (e.g. `cross_entropy`
→ `CrossEntropyParams`). The union is realized *at validate time* against the
discovered plugin's `operations` registry.

This placement is deliberate (I.a spike, Decision 3): `recipe/models.py` stays
**plugin-agnostic** (it cannot import plugins without breaking runtime plugin
discovery), and identity in `recipe/canonical.py` stays **plugin-free** (it hashes
the authored fields; plugin param-defaults never enter the cache bytes). The
op→param-model registry *is* the discriminated union — this module is its
validation-side concretization, consumed by FR-2 checks 3 and 17.

`resolve_sections(recipe, plugin)` resolves every op-bearing section and **never
short-circuits**, so the validator surfaces every problem in one pass. Two
failure modes are distinguished so each check owns exactly one:

* **registration** (check 3) — the op is unknown, or registered for a *different*
  slot (`applies_to` mismatch, e.g. an optimizer op placed in `Loss`).
* **params** (check 17) — the op resolves to its slot but the authored params
  fail its `param_model` (including unknown params, via the variant's
  `extra="forbid"`).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from modelfoundry.plugins.base import Plugin
from modelfoundry.recipe.models import ModelRecipe


@dataclass(frozen=True)
class ResolvedSection:
    """One op-bearing section resolved against the plugin's discriminated union.

    `registered` is true only when the op is known **and** registered for this
    section's `slot`. `variant` is the typed param instance, present only when the
    section both registers and validates. `registration_error` / `param_error`
    are mutually exclusive and populated for the matching failure mode.
    """

    label: str
    op: str
    slot: str
    registered: bool
    registration_error: str | None
    variant: BaseModel | None
    param_error: str | None


def iter_op_sections(recipe: ModelRecipe) -> Iterator[tuple[str, str, dict[str, Any], str]]:
    """Yield `(label, op, authored_params, slot)` for every op-bearing section.

    `authored_params` is the section's `extra` bag (the op-specific params as
    written); `slot` is the `OperationSpec.applies_to` value the section occupies.

    Loss/Optimizer are optional (Story I.ab): a generative density model omits them,
    so an absent section yields nothing — checks 3 / 17 then simply skip it.
    """
    if recipe.Loss is not None:
        yield "Loss", recipe.Loss.op, dict(recipe.Loss.model_extra or {}), "loss"
    if recipe.Optimizer is not None:
        yield (
            "Optimizer",
            recipe.Optimizer.op,
            dict(recipe.Optimizer.model_extra or {}),
            "optimizer",
        )
        if recipe.Optimizer.schedule is not None:
            sched = recipe.Optimizer.schedule
            yield "Optimizer.schedule", sched.op, dict(sched.model_extra or {}), "schedule"
    for i, viz in enumerate(recipe.Visualizations):
        yield f"Visualizations[{i}]", viz.op, dict(viz.model_extra or {}), "visualization"


def resolve_sections(recipe: ModelRecipe, plugin: Plugin) -> list[ResolvedSection]:
    """Resolve every op-bearing section against `plugin`'s discriminated union.

    Never short-circuits: every section is resolved and returned, so the
    validator can report all registration + param problems in a single pass.
    """
    resolved: list[ResolvedSection] = []
    for label, op, params, slot in iter_op_sections(recipe):
        spec = plugin.operations.get(op)
        if spec is None:
            resolved.append(
                ResolvedSection(
                    label,
                    op,
                    slot,
                    registered=False,
                    registration_error=f"op {op!r} is not registered by plugin {plugin.name!r}",
                    variant=None,
                    param_error=None,
                )
            )
            continue
        if spec.applies_to != slot:
            resolved.append(
                ResolvedSection(
                    label,
                    op,
                    slot,
                    registered=False,
                    registration_error=(
                        f"op {op!r} is registered for {spec.applies_to!r}, not {slot!r}"
                    ),
                    variant=None,
                    param_error=None,
                )
            )
            continue
        try:
            variant = spec.param_model.model_validate(params)
        except ValidationError as exc:
            resolved.append(
                ResolvedSection(
                    label,
                    op,
                    slot,
                    registered=True,
                    registration_error=None,
                    variant=None,
                    param_error=str(exc),
                )
            )
            continue
        resolved.append(
            ResolvedSection(
                label,
                op,
                slot,
                registered=True,
                registration_error=None,
                variant=variant,
                param_error=None,
            )
        )
    return resolved
