# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Reporting-mode visualization pipeline + atomic report re-render (FR-18, Story C.n).

`render_reporting_visualizations` drives every `Visualizations` op whose
`mode == "reporting"` through the bound plugin's `render_visualization`, writing
each returned PNG to `report/visualizations/<name>.png`. `rerender_report`
re-renders the whole `report/` directory (Markdown + visualizations) atomically:
it builds a sibling `report.tmp/`, then swaps it into place only on success, so a
failed re-render leaves the existing report untouched.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from modelfoundry.plugins.base import InstanceArtifacts
from modelfoundry.reporting.report import render_report

_REPORT = "report"
_REPORT_TMP = "report.tmp"
_REPORT_BAK = "report.bak"
_VISUALIZATIONS = "visualizations"


def render_reporting_visualizations(
    recipe: Any, plugin: Any, artifacts: InstanceArtifacts, viz_dir: Path
) -> list[Path]:
    """Render every `mode: reporting` visualization to `viz_dir`; return the paths.

    Each op's filename is its `name` extra when present, else its `op`. A renderer
    returning `None` (nothing to draw) is skipped.
    """
    written: list[Path] = []
    for viz in _reporting_ops(recipe):
        png = plugin.render_visualization(viz, artifacts)
        if png is None:
            continue
        viz_dir.mkdir(parents=True, exist_ok=True)
        filename = _viz_name(viz)
        path = viz_dir / f"{filename}.png"
        path.write_bytes(png)
        written.append(path)
    return written


def rerender_report(
    instance_dir: Path, artifacts: InstanceArtifacts, recipe: Any, plugin: Any
) -> Path:
    """Atomically re-render `instance_dir/report/`; preserve the old one on failure.

    Renders the Markdown + reporting visualizations into `report.tmp/`, then swaps
    it onto `report/` (the previous `report/` is moved aside and only deleted once
    the swap succeeds, so any failure restores it). Returns the report directory.
    """
    instance_dir = Path(instance_dir)
    report_dir = instance_dir / _REPORT
    tmp_dir = instance_dir / _REPORT_TMP
    backup_dir = instance_dir / _REPORT_BAK

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)

    # Build the new report fully in tmp before touching the live report/.
    (tmp_dir / "report.md").write_text(render_report(artifacts), encoding="utf-8")
    render_reporting_visualizations(recipe, plugin, artifacts, tmp_dir / _VISUALIZATIONS)

    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    had_existing = report_dir.exists()
    if had_existing:
        report_dir.rename(backup_dir)
    try:
        tmp_dir.rename(report_dir)
    except Exception:
        if had_existing and backup_dir.exists() and not report_dir.exists():
            backup_dir.rename(report_dir)  # restore the previous report
        raise
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    return report_dir


def _reporting_ops(recipe: Any) -> list[Any]:
    visualizations = getattr(recipe, "Visualizations", None) or []
    return [v for v in visualizations if getattr(v, "mode", "reporting") == "reporting"]


def _viz_name(viz: Any) -> str:
    extra = getattr(viz, "model_extra", None) or {}
    return str(extra.get("name") or viz.op)
