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

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from modelfoundry.cache.atomic import trash_existing
from modelfoundry.cache.identity import CacheKey, cache_key
from modelfoundry.cache.layout import CachePaths
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import InstanceError, PluginError
from modelfoundry.core.instance import ModelInstance
from modelfoundry.pipeline.data_binding import DataRefineryInstance, resolve_data_instance
from modelfoundry.pipeline.progress import StageObserver
from modelfoundry.pipeline.runner import MaterializeRunner
from modelfoundry.plugins.base import Plugin
from modelfoundry.plugins.discovery import discover_plugins
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.models import ModelRecipe


class ModelFoundry:
    """The library entry point: construction state + the verbs over one recipe binding (FR-22).

    An instance holds everything a recipe needs to act on — the parsed
    `ModelRecipe`, the bound DataRefinery instance, the resolved `Plugin`, the
    `RuntimeConfig`, and the derived `CacheKey` / `CachePaths`. The verbs
    (`validate` / `materialize` / `status` / `inspect` / `report` / `clean` /
    `check`) are thin methods over that state, so the library and the CLI (which
    drives this same class) stay co-equal. Prefer `ModelFoundry.from_recipe(...)`
    over the raw constructor; it loads, binds, and discovers in one call.

    Attributes:
        recipe: The parsed, overlay-applied recipe.
        data: The bound, read-only DataRefinery instance (FR-6).
        plugin: The framework plugin named by `recipe.plugin`.
        config: The effective runtime configuration.
        overlays: The ordered selected overlay names (possibly empty).
        key: The `CacheKey` identifying this `(recipe, data, seed)` binding (FR-4).
        paths: The on-disk `CachePaths` for the instance directory.
    """

    def __init__(
        self,
        recipe: ModelRecipe,
        data_instance: DataRefineryInstance,
        plugin: Plugin,
        config: RuntimeConfig,
        overlays: Sequence[str] | None = None,
    ) -> None:
        """Construct from already-resolved parts; prefer `from_recipe` for the usual path."""
        self.recipe = recipe
        self.data = data_instance
        self.plugin = plugin
        self.config = config
        self.overlays = list(overlays) if overlays is not None else []
        self.key = self._cache_key()
        self.paths = CachePaths(config.cache_root, self.key)

    @classmethod
    def from_recipe(
        cls,
        recipe_path: str | Path,
        *,
        data: DataRefineryInstance | str | Path,
        config: RuntimeConfig | None = None,
        overlays: Sequence[str] | None = None,
        seed: int | None = None,
    ) -> ModelFoundry:
        """Load `recipe_path`, bind `data`, discover the plugin, and return a `ModelFoundry`.

        This is the primary constructor (FR-22): it parses and validates the
        recipe (FR-1), applies the selected overlays (FR-14), binds the upstream
        data instance (FR-6), and resolves the framework plugin (FR-24).

        Args:
            recipe_path: Path to the YAML recipe file.
            data: Either a pre-bound `DataRefineryInstance`, or a path to the
                DataRefinery cache root — in which case the recipe's `Data:`
                block is resolved against it.
            config: Runtime configuration; a default `RuntimeConfig()` is used
                when omitted. When `data` is a path it overrides
                `config.data_cache_root`.
            overlays: Ordered names of `overlays.<name>` blocks to apply (last-
                writer-wins per section); empty/`None` applies none.
            seed: Master seed override; falls back to the recipe's own seed.

        Returns:
            A `ModelFoundry` bound to the loaded recipe, data, and plugin.

        Raises:
            RecipeError: The recipe is missing, malformed, or its schema version
                is unsupported.
            DataBindingError: The DataRefinery instance cannot be resolved or is
                incompatible (FR-6).
            PluginError: The recipe's `plugin` is not discoverable.
        """
        config = config or RuntimeConfig()
        recipe = load_recipe(recipe_path, overlays=overlays, seed=seed)

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
        return cls(recipe, data_instance, plugins[recipe.plugin], config, overlays)

    # --- verbs ---

    def validate(self) -> Any:
        """Run the FR-2 static validator over the bound recipe.

        Returns:
            The `ValidationReport` listing every static check and its outcome;
            it never short-circuits, so all failures surface at once.
        """
        from modelfoundry.recipe.validator import validate as validate_recipe

        return validate_recipe(self.recipe, self.data, self.plugin)

    def summary(self) -> dict[str, Any]:
        """Inspect the recipe's architecture WITHOUT training it (FR-27 surface).

        Builds the model from the recipe via the plugin and returns its structured
        summary as a backend-agnostic dict — `total_params` / `trainable_params` /
        `non_trainable_params` / per-layer `layers` rows + a top-level `output_shape`
        (the network's final output, e.g. `[1, 10]`). No `materialize()`, no framework
        import in caller code (Story H.a.2). The probe input shape is derived from the
        bound data instance's record schema.

        Raises:
            PluginError: when the resolved plugin does not implement summarization
            (the sklearn stub, for example).
        """
        summarizer = getattr(self.plugin, "summarize_model", None)
        if summarizer is None:
            raise PluginError(
                f"plugin {self.recipe.plugin!r} does not support architecture summary "
                f"(no `summarize_model`)",
                stage="summary",
            )
        model = self.plugin.build_model(self.recipe.Architecture)
        result: dict[str, Any] = summarizer(model, self.data)
        return result

    def materialize(self, *, stage_observer: StageObserver | None = None) -> ModelInstance:
        """Materialize the recipe into a cached ModelInstance and return a handle to it (FR-3).

        Runs every stage (architecture → optimization → training → evaluation →
        expectations → persistence → report) atomically, promoting the result
        into the cache directory on success.

        Args:
            stage_observer: Optional rendering-agnostic progress hook (FR-3). The
                CLI attaches a `rich`-based observer; library callers may pass
                their own or omit it.

        Returns:
            A `ModelInstance` handle to the freshly materialized instance.

        Raises:
            ModelArtifactExistsError: An instance already exists at the cache
                path and overwrite was not requested (FR-5).
            ExpectationError: A declared OutputExpectation failed (FR-15).
            MaterializeError: Any stage failed; non-ModelFoundry exceptions are
                wrapped as this (FR-3).
        """
        MaterializeRunner(
            recipe=self.recipe,
            data_instance=self.data,
            plugin=self.plugin,
            runtime_config=self.config,
            overlays=self.overlays,
            stage_observer=stage_observer,
        ).run()
        return ModelInstance.load(self.paths.instance_dir, plugin=self.plugin)

    def status(self) -> dict[str, Any]:
        """Report whether this recipe's instance is materialized.

        Returns:
            A dict with `materialized` (bool), `instance_dir` (str), and
            `manifest` (the loaded `Manifest` when materialized, else `None`).
        """
        from modelfoundry.core.manifest import Manifest

        instance_dir = self.paths.instance_dir
        materialized = (instance_dir / "manifest.json").is_file()
        return {
            "materialized": materialized,
            "instance_dir": str(instance_dir),
            "manifest": Manifest.load(instance_dir / "manifest.json") if materialized else None,
        }

    def inspect(self) -> ModelInstance:
        """Return a handle to the already-materialized instance (FR-17).

        Returns:
            The `ModelInstance` for this binding.

        Raises:
            InstanceError: No materialized instance exists; run `materialize` first.
        """
        return self._require_instance()

    def report(self) -> str:
        """Re-render and return the instance report as Markdown (FR-12).

        Returns:
            The report Markdown text.

        Raises:
            InstanceError: No materialized instance exists; run `materialize` first.
        """
        return self._require_instance().render_report()

    def clean(self) -> Path | None:
        """Trash the materialized instance, moving it under `.trash/` (FR-20).

        Returns:
            The destination path inside `.trash/`, or `None` when there was
            nothing to clean.
        """
        if not self.paths.instance_dir.exists():
            return None
        return trash_existing(self.config.cache_root, self.key)

    def check(self) -> dict[str, Any]:
        """Summarize environment / plugin health for *this* recipe's bound plugin (FR-19).

        Returns:
            A dict with `modelfoundry_version`, `plugin` (name), and the
            plugin's `health` self-report.
        """
        from modelfoundry._version import __version__

        return {
            "modelfoundry_version": __version__,
            "plugin": self.plugin.name,
            "health": self.plugin.health_check(),
        }

    @classmethod
    def check_environment(cls, config: RuntimeConfig | None = None) -> dict[str, Any]:
        """Probe the environment without a recipe binding (FR-19, the `check` verb).

        Reports the Python version, the installed ModelFoundry version, and — for
        every discovered plugin (no recipe binding required) — the plugin's
        `health_check()` self-report. A CPU-only machine is not itself an error
        (CPU is always functional).

        Args:
            config: Runtime configuration used for plugin discovery; a default
                `RuntimeConfig()` is used when omitted.

        Returns:
            A dict with `python_version`, `modelfoundry_version`, `plugins` (the
            list of health reports), and `ok` — `False` when any discovered
            plugin is unavailable (its extras are missing), so the CLI exits
            non-zero.
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
    overlays: Sequence[str] | None = None,
    seed: int | None = None,
) -> ModelInstance:
    """Bind `recipe_path` to `data` and materialize it in one call (FR-22).

    A convenience wrapper over `ModelFoundry.from_recipe(...).materialize()`.

    Args:
        recipe_path: Path to the YAML recipe file.
        data: A pre-bound `DataRefineryInstance`, or a path to the DataRefinery
            cache root to resolve the recipe's `Data:` block against.
        config: Runtime configuration; defaults to `RuntimeConfig()` when omitted.
        overlays: Ordered names of `overlays.<name>` blocks to apply, or `None`.
        seed: Master seed override; falls back to the recipe's own seed.

    Returns:
        The materialized `ModelInstance`.

    Raises:
        RecipeError: The recipe is missing, malformed, or has an unsupported
            schema version.
        DataBindingError: The DataRefinery instance cannot be resolved (FR-6).
        PluginError: The recipe's `plugin` is not discoverable.
        ModelArtifactExistsError: An instance already exists and overwrite was
            not requested (FR-5).
        ExpectationError: A declared OutputExpectation failed (FR-15).
        MaterializeError: A materialization stage failed (FR-3).
    """
    return ModelFoundry.from_recipe(
        recipe_path, data=data, config=config, overlays=overlays, seed=seed
    ).materialize()
