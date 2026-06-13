# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Markdown report rendering (FR-18, Story C.n).

`render_report(artifacts)` produces the human-readable `report/report.md` summary
of a ModelInstance: recipe + plugin, evaluation metrics, optimization summary,
OutputExpectations outcomes, and warnings. It reads from the `InstanceArtifacts`
snapshot (recipe + manifest + the evaluation dict), degrading gracefully when a
section's data is absent so the report renders for partial / minimal instances.

The headings are stable (`## Recipe`, `## Metrics`, `## Optimization`,
`## Expectations`, `## Warnings`) so downstream tooling and tests can anchor on
them.
"""

from __future__ import annotations

from typing import Any

from modelfoundry.plugins.base import InstanceArtifacts

# Metric values that are scalars (rendered in the metrics table); nested metrics
# like confusion_matrix / calibration_curve are summarized as artifacts, not cells.
_NON_SCALAR_METRICS = frozenset({"confusion_matrix", "calibration_curve"})


def render_report(artifacts: InstanceArtifacts) -> str:
    """Render the ModelInstance report as a Markdown string."""
    sections = [
        "# ModelFoundry Report",
        _recipe_section(artifacts),
        _metrics_section(artifacts),
        _optimization_section(artifacts),
        _expectations_section(artifacts),
        _warnings_section(artifacts),
    ]
    return "\n\n".join(sections) + "\n"


def _recipe_section(artifacts: InstanceArtifacts) -> str:
    lines = ["## Recipe"]
    manifest = artifacts.manifest
    recipe = artifacts.recipe
    plugin = _attr(manifest, "plugin") or _attr(recipe, "plugin") or "unknown"
    lines.append(f"- **Plugin:** {plugin}")
    if (seed := _attr(manifest, "seed", _attr(recipe, "seed"))) is not None:
        lines.append(f"- **Seed:** {seed}")
    if (variant := _attr(manifest, "variant")) is not None:
        lines.append(f"- **Variant:** {variant}")
    if recipe is not None:
        architecture = _attr(recipe, "Architecture")
        if isinstance(architecture, dict):
            kind = architecture.get("type") or f"{len(architecture.get('layers', []))} layers"
            lines.append(f"- **Architecture:** {kind}")
        if (loss := _attr(recipe, "Loss")) is not None:
            lines.append(f"- **Loss:** {_attr(loss, 'op')}")
        optimizer = _attr(recipe, "Optimizer")
        if optimizer is not None:
            lines.append(f"- **Optimizer:** {_attr(optimizer, 'op')}")
    if (elapsed := _attr(manifest, "elapsed_seconds")) is not None:
        lines.append(f"- **Elapsed:** {float(elapsed):.2f}s")
    return "\n".join(lines)


def _metrics_section(artifacts: InstanceArtifacts) -> str:
    evaluation = artifacts.evaluation or _attr(artifacts.manifest, "evaluation")
    lines = ["## Metrics"]
    if not evaluation:
        lines.append("_No evaluation metrics._")
        return "\n".join(lines)

    scalar_names = sorted(
        {
            name
            for split_metrics in evaluation.values()
            for name, value in split_metrics.items()
            if name not in _NON_SCALAR_METRICS and isinstance(value, int | float)
        }
    )
    if not scalar_names:
        lines.append("_No scalar metrics._")
        return "\n".join(lines)

    header = "| split | " + " | ".join(scalar_names) + " |"
    divider = "| --- | " + " | ".join("---" for _ in scalar_names) + " |"
    lines += [header, divider]
    for split in sorted(evaluation):
        cells = [_fmt(evaluation[split].get(name)) for name in scalar_names]
        lines.append(f"| {split} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _optimization_section(artifacts: InstanceArtifacts) -> str:
    lines = ["## Optimization"]
    opt = _attr(artifacts.manifest, "optimization")
    if opt is None:
        lines.append("_No optimization stage._")
        return "\n".join(lines)
    lines.append(f"- **Sampler:** {_attr(opt, 'sampler')} / **Pruner:** {_attr(opt, 'pruner')}")
    lines.append(f"- **Trials:** {_attr(opt, 'n_trials')}")
    if (best := _attr(opt, "best_trial_number")) is not None:
        lines.append(f"- **Best trial:** #{best} (value {_fmt(_attr(opt, 'best_value'))})")
    return "\n".join(lines)


def _expectations_section(artifacts: InstanceArtifacts) -> str:
    lines = ["## Expectations"]
    outcomes = _attr(artifacts.manifest, "output_expectations")
    if not outcomes:
        lines.append("_None declared._")
        return "\n".join(lines)
    lines += [
        "| metric | split | op | expected | observed | result |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for o in outcomes:
        mark = "✅" if _attr(o, "passed") else "❌"
        lines.append(
            f"| {_attr(o, 'metric')} | {_attr(o, 'split')} | {_attr(o, 'op')} | "
            f"{_fmt(_attr(o, 'expected'))} | {_fmt(_attr(o, 'observed'))} | {mark} |"
        )
    return "\n".join(lines)


def _warnings_section(artifacts: InstanceArtifacts) -> str:
    lines = ["## Warnings"]
    warnings = _attr(artifacts.manifest, "warnings") or []
    if not warnings:
        lines.append("_None._")
        return "\n".join(lines)
    for w in warnings:
        stage = _attr(w, "stage")
        prefix = f"[{stage}] " if stage else ""
        lines.append(f"- {prefix}{_attr(w, 'message', w)}")
    return "\n".join(lines)


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read `name` from a pydantic model / object (`getattr`) or a mapping."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, tuple | list):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    return str(value)
