# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry status <recipe>` — the FR-16 lifecycle / cache summary (Story D.d).

Binds the recipe to its DataRefinery instance, resolves the ModelFoundry cache
key, and either renders the on-disk manifest as a `rich` summary table (cache
hit) or reports "not materialized" with the expected path (cache miss). `status`
is a read-only query — it always exits `0`; binding / plugin failures raise their
domain errors and are mapped to exit codes by `cli.app`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.manifest import Manifest


def run(recipe: Path, config: RuntimeConfig, *, console: Console | None = None) -> int:
    """Resolve `recipe`'s instance; render its status; always return `0`."""
    from modelfoundry.core.modelfoundry import ModelFoundry

    mf = ModelFoundry.from_recipe(recipe, data=config.data_cache_root, config=config)
    render_status(
        recipe,
        mf.status(),
        primary_metric=mf.recipe.Evaluation.primary_metric,
        console=console or Console(),
    )
    return 0


def render_status(
    recipe: Path,
    status: dict[str, Any],
    *,
    primary_metric: str,
    console: Console | None = None,
) -> None:
    """Render the resolved status: the manifest summary table, or a cache-miss notice."""
    console = console or Console()
    if not status["materialized"]:
        console.print(f"[yellow]✗ not materialized[/yellow] — {recipe}")
        console.print(f"  expected at: {status['instance_dir']}")
        return

    manifest: Manifest = status["manifest"]
    table = Table(
        title=f"Status — {recipe}", title_justify="left", header_style="bold", show_header=False
    )
    table.add_column("Field", style="bold", no_wrap=True)
    table.add_column("Value")

    rows: list[tuple[str, str]] = [
        ("plugin", f"{manifest.plugin} {manifest.plugin_version}"),
        ("schema version", str(manifest.schema_version)),
        ("recipe hash", manifest.recipe_hash),
        ("bound data instance", str(manifest.bound_data_instance)),
        ("seed", str(manifest.seed)),
        ("overlays", ", ".join(manifest.overlays) or "—"),
        ("cache", "[green]hit[/green]"),
        ("materialized at", manifest.created_at.isoformat()),
        ("elapsed", f"{manifest.elapsed_seconds:.2f}s"),
        ("primary metric", _primary_metric(manifest.evaluation, primary_metric)),
        ("expectations", _expectations(manifest)),
    ]
    if manifest.is_partial:
        rows.append(
            ("partial", f"[red]yes[/red] — failed at stage: {manifest.failed_stage or '?'}")
        )
    for field, value in rows:
        table.add_row(field, value)
    console.print(table)


def _primary_metric(evaluation: dict[str, dict[str, Any]], primary_metric: str) -> str:
    """`<name> = <value> (<split>)` for every split that recorded the primary metric."""
    parts = [
        f"{_fmt(metrics[primary_metric])} ({split})"
        for split, metrics in sorted(evaluation.items())
        if primary_metric in metrics
    ]
    if not parts:
        return f"{primary_metric} (not recorded)"
    return f"{primary_metric} = " + ", ".join(parts)


def _expectations(manifest: Manifest) -> str:
    """`<n> passed, <m> failed` over the manifest's `OutputExpectations` outcomes."""
    outcomes = manifest.output_expectations
    if not outcomes:
        return "none declared"
    passed = sum(1 for outcome in outcomes if outcome.passed)
    return f"{passed} passed, {len(outcomes) - passed} failed"


def _fmt(value: Any) -> str:
    """Compact rendering: 4-decimal floats, otherwise the value's `str`."""
    return f"{value:.4f}" if isinstance(value, float) else str(value)
