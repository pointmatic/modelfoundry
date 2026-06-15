# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`ModelFoundry` — the library entry point (FR-22, Story C.p).

`ModelFoundry.from_recipe(...)` builds the shared construction state (recipe +
bound DataRefinery instance + plugin + runtime config + cache key); the verbs
`validate` / `materialize` / `status` / `inspect` / `report` / `clean` / `check`
are thin wrappers over it. The CLI (Phase D) drives the same class, so the
library and CLI stay co-equal.

The top-level `materialize(...)` is the one-call convenience: bind, materialize,
return the `ModelInstance`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from modelfoundry.cache.atomic import trash_existing
from modelfoundry.cache.identity import CacheKey, cache_key
from modelfoundry.cache.layout import CachePaths
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import InstanceError, PluginError
from modelfoundry.core.instance import ModelInstance
from modelfoundry.pipeline.data_binding import DataRefineryInstance, resolve_data_instance
from modelfoundry.pipeline.runner import MaterializeRunner
from modelfoundry.plugins.base import Plugin
from modelfoundry.plugins.discovery import discover_plugins
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.models import ModelRecipe


class ModelFoundry:
    """Shared construction state + the seven verbs over one recipe binding."""

    def __init__(
        self,
        recipe: ModelRecipe,
        data_instance: DataRefineryInstance,
        plugin: Plugin,
        config: RuntimeConfig,
        variant: str | None = None,
    ) -> None:
        self.recipe = recipe
        self.data = data_instance
        self.plugin = plugin
        self.config = config
        self.variant = variant
        self.key = self._cache_key()
        self.paths = CachePaths(config.cache_root, self.key)

    @classmethod
    def from_recipe(
        cls,
        recipe_path: str | Path,
        *,
        data: DataRefineryInstance | str | Path,
        config: RuntimeConfig | None = None,
        variant: str | None = None,
        seed: int | None = None,
    ) -> ModelFoundry:
        """Load `recipe_path`, bind `data`, discover the plugin, and return a `ModelFoundry`.

        `data` is either a pre-bound `DataRefineryInstance` or a path to the
        DataRefinery cache root (in which case the recipe's `Data:` block is
        resolved against it).
        """
        config = config or RuntimeConfig()
        recipe = load_recipe(recipe_path, variant=variant, seed=seed)

        if isinstance(data, DataRefineryInstance):
            data_instance = data
        else:
            config = config.model_copy(update={"data_cache_root": Path(data)})
            data_instance = resolve_data_instance(recipe.Data, config)

        plugins = discover_plugins(config.plugin_path)
        if recipe.plugin not in plugins:
            raise PluginError(
                f"recipe plugin {recipe.plugin!r} is not discoverable; known: {sorted(plugins)}",
                detail={"plugin": recipe.plugin},
            )
        return cls(recipe, data_instance, plugins[recipe.plugin], config, variant)

    # --- verbs ---

    def validate(self) -> Any:
        """Run the FR-2 static validator; return the `ValidationReport`."""
        from modelfoundry.recipe.validator import validate as validate_recipe

        return validate_recipe(self.recipe, self.data, self.plugin)

    def materialize(self) -> ModelInstance:
        """Materialize the recipe and return the resulting `ModelInstance`."""
        MaterializeRunner(
            recipe=self.recipe,
            data_instance=self.data,
            plugin=self.plugin,
            runtime_config=self.config,
            variant=self.variant,
        ).run()
        return ModelInstance.load(self.paths.instance_dir, plugin=self.plugin)

    def status(self) -> dict[str, Any]:
        """Whether the instance is materialized, plus its manifest when present."""
        from modelfoundry.core.manifest import Manifest

        instance_dir = self.paths.instance_dir
        materialized = (instance_dir / "manifest.json").is_file()
        return {
            "materialized": materialized,
            "instance_dir": str(instance_dir),
            "manifest": Manifest.load(instance_dir / "manifest.json") if materialized else None,
        }

    def inspect(self) -> ModelInstance:
        """Return the materialized `ModelInstance` (raises if not materialized)."""
        return self._require_instance()

    def report(self) -> str:
        """Render and return the instance report Markdown (raises if not materialized)."""
        return self._require_instance().render_report()

    def clean(self) -> Path | None:
        """Trash the materialized instance (move to `.trash/`); `None` if nothing to clean."""
        if not self.paths.instance_dir.exists():
            return None
        return trash_existing(self.config.cache_root, self.key)

    def check(self) -> dict[str, Any]:
        """Environment / plugin health summary for *this* recipe's bound plugin."""
        from modelfoundry._version import __version__

        return {
            "modelfoundry_version": __version__,
            "plugin": self.plugin.name,
            "health": self.plugin.health_check(),
        }

    @classmethod
    def check_environment(cls, config: RuntimeConfig | None = None) -> dict[str, Any]:
        """Recipe-free environment probe (FR-19, the `check` verb).

        Reports the Python version, the installed ModelFoundry version, and — for
        every discovered plugin (no recipe binding required) — the plugin's
        `health_check()` self-report. `ok` is `False` when any discovered plugin
        is unavailable (its extras are missing), so the CLI exits non-zero; a
        CPU-only machine is not itself an error (CPU is always functional).
        """
        import platform

        from modelfoundry._version import __version__

        config = config or RuntimeConfig()
        plugins = discover_plugins(config.plugin_path)
        reports = [plugins[name].health_check() for name in sorted(plugins)]
        return {
            "python_version": platform.python_version(),
            "modelfoundry_version": __version__,
            "plugins": reports,
            "ok": all(getattr(report, "available", False) for report in reports),
        }

    # --- internals ---

    def _require_instance(self) -> ModelInstance:
        if not (self.paths.instance_dir / "manifest.json").is_file():
            raise InstanceError(
                f"no materialized instance at {self.paths.instance_dir}; run materialize first",
                detail={"instance_dir": str(self.paths.instance_dir)},
            )
        return ModelInstance.load(self.paths.instance_dir, plugin=self.plugin)

    def _cache_key(self) -> CacheKey:
        dm = self.data.manifest
        triple = (str(dm.recipe_hash), str(dm.input_hash), int(dm.seed))
        return cache_key(self.recipe, triple, self.recipe.seed)


def materialize(
    recipe_path: str | Path,
    *,
    data: DataRefineryInstance | str | Path,
    config: RuntimeConfig | None = None,
    variant: str | None = None,
    seed: int | None = None,
) -> ModelInstance:
    """One-call materialize: bind `recipe_path` to `data` and return the `ModelInstance`."""
    return ModelFoundry.from_recipe(
        recipe_path, data=data, config=config, variant=variant, seed=seed
    ).materialize()
