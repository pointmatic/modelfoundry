# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Plugin discovery (FR-24).

`discover_plugins(extra_paths=())` returns a `name -> Plugin` map, sourced from:

1. Entry points under the `modelfoundry.plugins` group (declared in installed
   packages' `[project.entry-points."modelfoundry.plugins"]` tables).
2. Any directories in `extra_paths` (typically `RuntimeConfig.plugin_path`, which
   `A.e`'s `from_env` builds from `MODELFOUNDRY_PLUGIN_PATH`). Each top-level
   `*.py` file is imported and its module-level `plugin` attribute is registered
   if it implements the `Plugin` Protocol.

Duplicate plugin names and unresolvable entry points raise `PluginError`.
"""

from __future__ import annotations

import importlib.util
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import Plugin

ENTRY_POINT_GROUP = "modelfoundry.plugins"


def discover_plugins(extra_paths: tuple[Path, ...] = ()) -> dict[str, Plugin]:
    plugins: dict[str, Plugin] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        _ingest_entry_point(plugins, ep)
    for path in extra_paths:
        _ingest_path(plugins, Path(path))
    return plugins


def _ingest_entry_point(plugins: dict[str, Plugin], ep: EntryPoint) -> None:
    try:
        candidate = ep.load()
    except Exception as exc:
        raise PluginError(
            f"could not load plugin entry point {ep.name!r}: {exc}",
            detail={"entry_point": ep.name, "value": getattr(ep, "value", None)},
        ) from exc
    _register(plugins, candidate, source=f"entry point {ep.name!r}")


def _ingest_path(plugins: dict[str, Plugin], path: Path) -> None:
    if not path.is_dir():
        return
    for module_path in sorted(path.glob("*.py")):
        if module_path.name == "__init__.py":
            continue
        spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise PluginError(
                f"could not import plugin from {module_path}: {exc}",
                detail={"path": str(module_path)},
            ) from exc
        candidate = getattr(module, "plugin", None)
        if candidate is None:
            continue
        _register(plugins, candidate, source=str(module_path))


def _register(plugins: dict[str, Plugin], candidate: object, *, source: str) -> None:
    if not isinstance(candidate, Plugin):
        raise PluginError(
            f"{source} did not provide a Plugin (missing one or more required "
            f"attributes/methods)",
            detail={"source": source},
        )
    if candidate.name in plugins:
        raise PluginError(
            f"duplicate plugin name {candidate.name!r} (already registered; "
            f"second registration from {source})",
            detail={"name": candidate.name, "source": source},
        )
    plugins[candidate.name] = candidate
