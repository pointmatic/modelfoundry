# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry materialize <recipe>` — train + optimize + evaluate (Story D.e, FR-3).

Binds the recipe, runs the materialize orchestrator, and prints a final `rich`
summary panel on success. `--overwrite` is threaded through `RuntimeConfig`
(the runner trashes the existing instance); `--variant` / `--seed` go to
`from_recipe`. Progress is rendered at *stage* granularity via `RichStageProgress`
(the runner's `StageObserver` seam). Per-epoch training tables and per-trial
Optuna progress bars are deferred to Story D.e.1.

Materialize failures (`ExpectationError`, `MaterializeError`, …) propagate to
`cli.app`, which maps them to non-zero exit codes; `run()` returns `0` on success.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.instance import ModelInstance


class RichStageProgress:
    """A `StageObserver` that streams one `rich` line per materialization stage."""

    def __init__(self, console: Console) -> None:
        self._console = console

    def on_stage_start(self, stage: str) -> None:
        self._console.print(f"[cyan]▶[/cyan] {stage} …")

    def on_stage_done(self, stage: str, elapsed: float) -> None:
        self._console.print(f"[green]✓[/green] {stage} ([dim]{elapsed:.2f}s[/dim])")

    def on_stage_skipped(self, stage: str) -> None:
        self._console.print(f"[dim]· {stage} (skipped)[/dim]")


def run(
    recipe: Path,
    config: RuntimeConfig,
    *,
    variant: str | None = None,
    seed: int | None = None,
    overwrite: bool = False,
    progress: bool = True,
    console: Console | None = None,
) -> int:
    """Materialize `recipe`; stream stage progress; render the summary; return `0`."""
    from modelfoundry.core.modelfoundry import ModelFoundry

    console = console or Console()
    if overwrite:
        config = config.model_copy(update={"overwrite": True})

    mf = ModelFoundry.from_recipe(
        recipe, data=config.data_cache_root, config=config, variant=variant, seed=seed
    )
    observer = RichStageProgress(console) if progress else None
    instance = mf.materialize(stage_observer=observer)
    render_summary(
        instance, recipe, primary_metric=mf.recipe.Evaluation.primary_metric, console=console
    )
    return 0


def render_summary(
    instance: ModelInstance,
    recipe: Path,
    *,
    primary_metric: str,
    console: Console | None = None,
) -> None:
    """Render the post-materialize success panel from the instance's manifest."""
    console = console or Console()
    manifest = instance.manifest

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold", no_wrap=True)
    table.add_column("Value")
    table.add_row("instance", str(instance.path))
    table.add_row("plugin", f"{manifest.plugin} {manifest.plugin_version}")
    table.add_row("recipe hash", manifest.recipe_hash)
    table.add_row("seed", str(manifest.seed))
    table.add_row("variant", manifest.variant or "—")
    table.add_row("elapsed", f"{manifest.elapsed_seconds:.2f}s")
    table.add_row("primary metric", _primary_metric(manifest.evaluation, primary_metric))
    table.add_row("expectations", _expectations(manifest))
    if manifest.optimization is not None:
        opt = manifest.optimization
        best = "—" if opt.best_value is None else f"{opt.best_value:.4f}"
        table.add_row(
            "optimization", f"{opt.sampler}/{opt.pruner}, {opt.n_trials} trials, best={best}"
        )

    console.print(
        Panel(table, title=f"[green]✓ materialized[/green] — {recipe}", title_align="left")
    )


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


def _expectations(manifest: Any) -> str:
    """`<n> passed, <m> failed` over the manifest's `OutputExpectations` outcomes."""
    outcomes = manifest.output_expectations
    if not outcomes:
        return "none declared"
    passed = sum(1 for outcome in outcomes if outcome.passed)
    return f"{passed} passed, {len(outcomes) - passed} failed"


def _fmt(value: Any) -> str:
    """Compact rendering: 4-decimal floats, otherwise the value's `str`."""
    return f"{value:.4f}" if isinstance(value, float) else str(value)
