# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry report <instance>` — re-render an instance's report (Story D.f, FR-18).

Operates on a self-contained materialized instance directory: it loads the
instance (the plugin resolves from the manifest, honoring `--plugin-path`),
atomically re-renders `report/` via `ModelInstance.render_report()`, and prints
the report path. A path with no `manifest.json` raises `InstanceError` (exit 1);
an instance naming an undiscoverable plugin raises `PluginError` (exit 2) — both
mapped by `cli.app`.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import InstanceError, PluginError


def run(instance_path: Path, config: RuntimeConfig, *, console: Console | None = None) -> int:
    """Re-render `instance_path`'s report; print the path; return `0`."""
    from modelfoundry.core.instance import ModelInstance
    from modelfoundry.core.manifest import Manifest
    from modelfoundry.plugins.discovery import discover_plugins

    console = console or Console()
    manifest_path = instance_path / "manifest.json"
    if not manifest_path.is_file():
        raise InstanceError(
            f"no materialized instance at {instance_path}; nothing to report",
            detail={"instance_dir": str(instance_path)},
        )

    manifest = Manifest.load(manifest_path)
    plugins = discover_plugins(config.plugin_path)
    if manifest.plugin not in plugins:
        raise PluginError(
            f"instance names plugin {manifest.plugin!r} but it is not discoverable",
            detail={"plugin": manifest.plugin},
        )

    instance = ModelInstance.load(instance_path, plugin=plugins[manifest.plugin])
    instance.render_report()
    report_path = instance.path / "report" / "report.md"
    console.print(f"[green]✓[/green] report rendered → {report_path}")
    return 0
