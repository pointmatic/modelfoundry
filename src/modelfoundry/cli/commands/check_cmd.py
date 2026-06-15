# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry check` — the FR-19 environment / plugin health probe (Story D.c).

Runs `ModelFoundry.check_environment()` (recipe-free: discover every plugin, run
each one's `health_check()`), renders the result as a `rich` table, and returns
`0` when the environment is healthy or `1` when any discovered plugin is
unavailable (its extras are not installed). A CPU-only machine is healthy — CPU
is always functional per QR-5 — so an empty accelerator set is informational,
not a failure.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table

from modelfoundry.core.config import RuntimeConfig


def run(config: RuntimeConfig, *, console: Console | None = None) -> int:
    """Probe the environment; render the report; return `0` (healthy) or `1`."""
    from modelfoundry.core.modelfoundry import ModelFoundry

    result = ModelFoundry.check_environment(config)
    render_check(result, console=console or Console())
    return 0 if result["ok"] else 1


def render_check(result: dict[str, Any], *, console: Console | None = None) -> None:
    """Render the environment probe as a header line, a per-plugin table, and a summary."""
    console = console or Console()
    console.print(
        f"Python {result['python_version']}  ·  "
        f"ModelFoundry {result['modelfoundry_version']}"
    )

    table = Table(title="Environment check", title_justify="left", header_style="bold")
    table.add_column("Plugin")
    table.add_column("Status", no_wrap=True)
    table.add_column("Accelerators")
    table.add_column("Versions")

    reports = result["plugins"]
    for report in reports:
        available = getattr(report, "available", False)
        status = "[green]✓ available[/green]" if available else "[red]✗ unavailable[/red]"
        accelerators = ", ".join(getattr(report, "accelerators", ())) or "—"
        table.add_row(
            getattr(report, "plugin", "?"), status, accelerators, _versions(report)
        )
    console.print(table)

    unavailable = [r for r in reports if not getattr(r, "available", False)]
    if not unavailable:
        console.print("[green]✓ environment healthy[/green]")
    else:
        names = ", ".join(getattr(r, "plugin", "?") for r in unavailable)
        console.print(
            f"[red]✗ environment unhealthy[/red]: {len(unavailable)} plugin(s) "
            f"unavailable ({names})"
        )


def _versions(report: Any) -> str:
    """Comma-joined `<dep>=<version>` pairs harvested from the report's `*_version` fields."""
    dump = report.model_dump() if hasattr(report, "model_dump") else {}
    pairs = [
        f"{key.removesuffix('_version')}={value}"
        for key, value in dump.items()
        if key.endswith("_version") and value is not None
    ]
    return ", ".join(pairs) or "—"
