# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry init <recipe> --data <dr-recipe>` — scaffold a baseline recipe (Story D.i, FR-21).

Resolves the bound DataRefinery instance and writes a dataset-shaped baseline
recipe via `scaffolder.init.scaffold_recipe`, then prints the path. A binding
failure raises `DataBindingError`; an existing target without `--force` raises
`RecipeError` — both mapped to exit codes by `cli.app`.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from modelfoundry.core.config import RuntimeConfig


def run(
    recipe_path: Path,
    datarefinery_recipe_path: Path,
    config: RuntimeConfig,
    *,
    plugin: str = "pytorch",
    force: bool = False,
    console: Console | None = None,
) -> int:
    """Scaffold a baseline recipe; print the path; return `0`."""
    from modelfoundry.scaffolder.init import scaffold_recipe

    console = console or Console()
    written = scaffold_recipe(
        recipe_path, datarefinery_recipe_path, plugin=plugin, force=force, config=config
    )
    console.print(f"[green]✓[/green] scaffolded {plugin} recipe → {written}")
    return 0
