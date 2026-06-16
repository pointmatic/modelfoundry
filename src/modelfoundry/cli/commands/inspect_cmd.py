# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`modelfoundry inspect <instance> --view <name>` — render one view (Story D.g, FR-17).

Loads a materialized instance (plugin resolved from the manifest, honoring
`--plugin-path`) and renders a single named view on demand via
`ModelInstance.inspect(view=...)`. PNG views are written to a temp file and the
path printed; the text `view_manifest` view renders a `rich` table. A path with
no `manifest.json` raises `InstanceError`; an unknown view raises
`InspectionError` — both mapped to exit codes by `cli.app`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from rich.console import Console
from rich.table import Table

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import InstanceError, PluginError
from modelfoundry.core.manifest import Manifest


def run(
    instance_path: Path, config: RuntimeConfig, *, view: str, console: Console | None = None
) -> int:
    """Render `view` of `instance_path`; print the PNG path or a `rich` table; return `0`."""
    from modelfoundry.core.instance import ModelInstance
    from modelfoundry.plugins.discovery import discover_plugins

    console = console or Console()
    manifest_path = instance_path / "manifest.json"
    if not manifest_path.is_file():
        raise InstanceError(
            f"no materialized instance at {instance_path}; nothing to inspect",
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
    result = instance.inspect(view=view)
    if isinstance(result, bytes):
        out_dir = Path(tempfile.mkdtemp(prefix="modelfoundry-inspect-"))
        png_path = out_dir / f"{view}.png"
        png_path.write_bytes(result)
        # soft_wrap: never line-wrap the path (rich's 80-col CI fallback splits it).
        console.print(f"[green]✓[/green] {view} → {png_path}", soft_wrap=True)
    else:
        render_manifest(result, console=console)
    return 0


def render_manifest(manifest: Manifest, *, console: Console | None = None) -> None:
    """Render a `Manifest` as a two-column `rich` field/value table."""
    console = console or Console()
    table = Table(title="Manifest", title_justify="left", header_style="bold")
    table.add_column("Field", no_wrap=True)
    table.add_column("Value")
    for field, value in manifest.model_dump(mode="json").items():
        table.add_row(field, _fmt(value))
    console.print(table)


def _fmt(value: object) -> str:
    if isinstance(value, list | dict):
        import json

        return json.dumps(value, ensure_ascii=False)
    return str(value)
