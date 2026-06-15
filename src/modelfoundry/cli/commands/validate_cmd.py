# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry validate <recipe>` — the FR-2 static checks (Story D.b).

Binds the recipe to its DataRefinery instance (the validator cross-checks splits,
class count, and schema version against the bound instance — FR-2 checks 4 / 18 /
19), runs `ModelFoundry.validate()`, renders the `ValidationReport` as a `rich`
table, and returns `0` when every check passes, `1` otherwise. Binding / plugin
failures raise their domain errors and are mapped to exit codes by `cli.app`.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.recipe.validator import ValidationReport


def run(recipe: Path, config: RuntimeConfig, *, console: Console | None = None) -> int:
    """Validate `recipe`; render the report; return `0` (all pass) or `1` (any fail)."""
    from modelfoundry.core.modelfoundry import ModelFoundry

    mf = ModelFoundry.from_recipe(recipe, data=config.data_cache_root, config=config)
    report = mf.validate()
    render_validation(report, recipe, console=console or Console())
    return 0 if report.passed else 1


def render_validation(
    report: ValidationReport, recipe: Path, *, console: Console | None = None
) -> None:
    """Render `report` as a per-check `rich` table plus a pass/fail summary line."""
    console = console or Console()
    table = Table(title=f"Validation — {recipe}", title_justify="left", header_style="bold")
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Check")
    table.add_column("Result", no_wrap=True)
    table.add_column("Detail")
    for check in report.checks:
        result = "[green]✓ pass[/green]" if check.passed else "[red]✗ fail[/red]"
        table.add_row(str(check.id), check.name, result, check.message or "")
    console.print(table)

    total = len(report.checks)
    failures = report.failures
    if not failures:
        console.print(f"[green]✓ all {total} checks passed[/green]")
    else:
        console.print(f"[red]✗ {len(failures)} of {total} checks failed[/red]")
