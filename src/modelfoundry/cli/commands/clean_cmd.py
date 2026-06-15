# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry clean` — remove cached ModelInstances by selector (Story D.h, FR-20).

Selectors compose: `--recipe-hash`, `--older-than`, `--failed`, `--orphans`
(the last requires `--older-than`). `--dry-run` reports what would be removed
without touching anything. No matches → exit 0 with a "nothing to clean"
message; a removal failure (e.g. permissions) → exit 2 with the partial state
reported, per FR-20.
"""

from __future__ import annotations

from rich.console import Console

from modelfoundry.cache.cleaner import parse_duration, remove_targets, select_targets
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import CacheError


def run(
    config: RuntimeConfig,
    *,
    recipe_hash: str | None = None,
    older_than: str | None = None,
    failed: bool = False,
    orphans: bool = False,
    dry_run: bool = False,
    console: Console | None = None,
) -> int:
    """Select + remove cache directories; return `0` (clean/dry-run) or `2` (removal failed)."""
    console = console or Console()

    if orphans and older_than is None:
        raise CacheError("--orphans requires --older-than (it ages out un-marked temp dirs)")
    if not (recipe_hash or older_than or failed or orphans):
        raise CacheError(
            "specify at least one selector: --recipe-hash / --older-than / --failed / --orphans"
        )

    duration = parse_duration(older_than) if older_than is not None else None
    targets = select_targets(
        config.cache_root,
        recipe_hash=recipe_hash,
        older_than=duration,
        failed=failed,
        orphans=orphans,
    )

    if not targets:
        console.print("nothing to clean")
        return 0

    if dry_run:
        for target in targets:
            console.print(
                f"[yellow]would remove[/yellow]: {target.path} ([dim]{target.reason}[/dim])"
            )
        console.print(f"[dim]{len(targets)} item(s) — dry run, nothing removed[/dim]")
        return 0

    result = remove_targets(targets)
    for path in result.removed:
        console.print(f"[green]removed[/green]: {path}")
    if result.failed:
        for path, error in result.failed:
            console.print(f"[red]failed[/red]: {path}: {error}")
        console.print(f"[red]✗ removed {len(result.removed)}, {len(result.failed)} failed[/red]")
        return 2
    console.print(f"[green]✓ removed {len(result.removed)} item(s)[/green]")
    return 0
