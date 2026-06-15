# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Materialize orchestrator (FR-3, Story C.o).

`MaterializeRunner.run()` sequences every stage of a materialization atomically
and returns the written `Manifest`. The stage order follows FR-3 step 4:

    Architecture → Optimization (if declared) → Training → Evaluation →
    OutputExpectations → Persistence → Report (+ reporting visualizations) →
    Manifest

All writes target a per-run temp directory (`cache.atomic.materialize_temp_dir`);
on clean exit the temp dir is promoted to its final instance path in one
`os.replace`. Any stage exception leaves a `FAILED` marker (naming the failing
stage + error class + message) and the final path untouched; non-ModelFoundry
exceptions are wrapped as `MaterializeError`, and a failing OutputExpectation as
`ExpectationError`. Each stage is timed and structurally logged; the timings flow
into the report and the total into `Manifest.elapsed_seconds`.

The runner is plugin-agnostic — it drives the `Plugin` Protocol and duck-types
the per-stage result objects, so the same orchestration serves the PyTorch and
sklearn plugins.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modelfoundry.cache.atomic import materialize_temp_dir, trash_existing
from modelfoundry.cache.identity import CacheKey, cache_key
from modelfoundry.cache.layout import CachePaths
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import ExpectationError, MaterializeError, ModelfoundryError
from modelfoundry.core.manifest import Manifest, ManifestWarning, OptimizationManifest
from modelfoundry.logging import get_logger
from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.pipeline.expectations import evaluate_expectations
from modelfoundry.pipeline.progress import StageObserver
from modelfoundry.plugins.base import InstanceArtifacts, Plugin
from modelfoundry.recipe.canonical import recipe_hash
from modelfoundry.recipe.models import ModelRecipe
from modelfoundry.recipe.search_space import apply_params
from modelfoundry.reporting.report import render_report
from modelfoundry.reporting.visualizations import render_reporting_visualizations


class MaterializeRunner:
    """Orchestrates one materialization of `recipe` over a bound DataRefinery instance."""

    def __init__(
        self,
        *,
        recipe: ModelRecipe,
        data_instance: DataRefineryInstance,
        plugin: Plugin,
        runtime_config: RuntimeConfig,
        variant: str | None = None,
        stage_observer: StageObserver | None = None,
    ) -> None:
        self.recipe = recipe
        self.data = data_instance
        self.plugin = plugin
        self.config = runtime_config
        self.variant = variant if variant is not None else runtime_config.variant
        self.seed = recipe.seed
        self.observer = stage_observer
        self.logger = get_logger(
            "modelfoundry.runner", target=runtime_config.log_target, level=runtime_config.log_level
        )
        self.stage_timings: dict[str, float] = {}

    def run(self) -> Manifest:
        """Materialize the recipe, atomically promoting the instance; return its manifest."""
        key = self._cache_key()
        if self.config.overwrite and CachePaths(self.config.cache_root, key).instance_dir.exists():
            trash_existing(self.config.cache_root, key)

        started = time.monotonic()
        with materialize_temp_dir(self.config.cache_root, key) as temp_dir:
            manifest = self._materialize(temp_dir, key, started)
            manifest.write(temp_dir / "manifest.json")
        self.logger.info("materialize_complete", extra={"instance": str(key.recipe_hash16)})
        return manifest

    # --- orchestration ---

    def _materialize(self, temp_dir: Path, key: CacheKey, started: float) -> Manifest:
        recipe = self.recipe

        model = self._stage("architecture", lambda: self.plugin.build_model(recipe.Architecture))

        opt_manifest: OptimizationManifest | None = None
        opt_spec = recipe.Optimization
        if opt_spec is not None:
            base_recipe = recipe
            opt_result = self._stage(
                "optimization",
                lambda: self.plugin.run_optimization(
                    opt_spec, base_recipe, self.data, self.seed, temp_dir
                ),
            )
            recipe = apply_params(recipe, opt_result.best_params)
            # Rebuild the model from the merged recipe (best params may touch arch).
            model = self.plugin.build_model(recipe.Architecture)
            opt_manifest = OptimizationManifest(
                sampler=opt_spec.sampler,
                pruner=opt_spec.pruner,
                n_trials=int(opt_result.n_trials),
                best_value=_opt_float(opt_result.best_value),
            )

        training_result = self._stage(
            "training",
            lambda: self.plugin.run_training(
                recipe.Training, model, recipe, self.data, self.seed, temp_dir
            ),
        )

        eval_metrics: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        if recipe.Evaluation.splits:
            eval_result = self._stage(
                "evaluation",
                lambda: self.plugin.run_evaluation(
                    recipe.Evaluation, model, self.data, temp_dir
                ),
            )
            eval_metrics = dict(eval_result.metrics)
            warnings = list(getattr(eval_result, "warnings", []))
        else:
            self._skip_stage("evaluation")

        outcomes = evaluate_expectations(recipe.OutputExpectations, eval_metrics)
        self._stage("output_expectations", lambda: _gate_expectations(outcomes))

        self._stage("persistence", lambda: self.plugin.save_model(model, temp_dir / "model"))
        self._maybe_write_summary(temp_dir, model)
        _persist_recipe(temp_dir, recipe)

        manifest = Manifest(
            plugin=self.plugin.name,
            plugin_version=self.plugin.version,
            recipe_hash=recipe_hash(recipe),
            data_instance_hash=key.data_instance_hash16,
            bound_data_instance=Path(self.data.path),
            seed=self.seed,
            variant=self.variant,
            created_at=datetime.now(UTC),
            elapsed_seconds=time.monotonic() - started,
            warnings=[ManifestWarning(message=w) for w in warnings],
            epoch_history=_epochs(training_result),
            optimization=opt_manifest,
            evaluation=eval_metrics,
            output_expectations=outcomes,
            byte_identity_guaranteed=recipe.Training.precision != "amp",
            metric_tolerance=None,
        )

        artifacts = self._build_artifacts(temp_dir, recipe, manifest, eval_metrics, training_result)
        self._stage("report", lambda: self._write_report(temp_dir, recipe, artifacts))

        return manifest

    def _maybe_write_summary(self, temp_dir: Path, model: Any) -> None:
        """Write the model summary (FR-27) when the plugin supports it.

        Duck-typed and optional so the runner stays plugin-agnostic: the PyTorch
        plugin writes a torchinfo summary; plugins without `write_model_summary`
        (e.g. sklearn) skip the stage cleanly.
        """
        writer = getattr(self.plugin, "write_model_summary", None)
        if writer is None:
            self._skip_stage("model_summary")
            return
        self._stage("model_summary", lambda: writer(model, self.data, temp_dir / "model"))

    def _write_report(
        self, temp_dir: Path, recipe: ModelRecipe, artifacts: InstanceArtifacts
    ) -> None:
        report_dir = temp_dir / "report"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "report.md").write_text(render_report(artifacts), encoding="utf-8")
        render_reporting_visualizations(
            recipe, self.plugin, artifacts, report_dir / "visualizations"
        )

    def _build_artifacts(
        self,
        temp_dir: Path,
        recipe: ModelRecipe,
        manifest: Manifest,
        eval_metrics: dict[str, dict[str, Any]],
        training_result: Any,
    ) -> InstanceArtifacts:
        return InstanceArtifacts(
            history=_load_parquet(temp_dir / "training" / "history.parquet"),
            evaluation=eval_metrics or None,
            predictions=_load_parquet(temp_dir / "evaluation" / "predictions.parquet"),
            trials=_load_parquet(temp_dir / "optimization" / "trials.parquet"),
            class_names=getattr(training_result, "classes", None),
            recipe=recipe,
            manifest=manifest,
            stage_timings=dict(self.stage_timings),
        )

    def _cache_key(self) -> CacheKey:
        dm = self.data.manifest
        triple = (str(dm.recipe_hash), str(dm.input_hash), int(dm.seed))
        return cache_key(self.recipe, triple, self.seed)

    def _stage(self, name: str, fn: Any) -> Any:
        t0 = time.monotonic()
        self.logger.info("stage_start", extra={"stage": name})
        if self.observer is not None:
            self.observer.on_stage_start(name)
        try:
            result = fn()
        except ModelfoundryError as exc:
            # Already a domain error (carries its own stage where set); annotate + re-raise.
            if getattr(exc, "stage", None) is None:
                exc.stage = name
            raise
        except Exception as exc:
            raise MaterializeError(
                f"stage {name!r} failed: {exc}", stage=name, detail={"stage": name}
            ) from exc
        elapsed = time.monotonic() - t0
        self.stage_timings[name] = elapsed
        self.logger.info("stage_done", extra={"stage": name, "elapsed_seconds": elapsed})
        if self.observer is not None:
            self.observer.on_stage_done(name, elapsed)
        return result

    def _skip_stage(self, name: str) -> None:
        self.logger.info("stage_skipped", extra={"stage": name})
        if self.observer is not None:
            self.observer.on_stage_skipped(name)


# --- helpers ---


def _persist_recipe(temp_dir: Path, recipe: ModelRecipe) -> None:
    """Write the (post-merge) recipe into the instance so it is self-contained (FR-23)."""
    import yaml

    (temp_dir / "recipe.yml").write_text(
        yaml.safe_dump(recipe.model_dump(mode="json"), sort_keys=True), encoding="utf-8"
    )


def _gate_expectations(outcomes: list[Any]) -> None:
    failed = [o for o in outcomes if not o.passed]
    if failed:
        names = [f"{o.metric}@{o.split} {o.op} {o.expected}" for o in failed]
        raise ExpectationError(
            f"output expectations failed: {names}",
            stage="output_expectations",
            detail={"failed": names},
        )


def _epochs(training_result: Any) -> int:
    for attr in ("epochs_run", "n_iter"):
        value = getattr(training_result, attr, None)
        if value is not None:
            return int(value)
    return 0


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _load_parquet(path: Path) -> Any:
    if not path.is_file():
        return None
    import pandas as pd  # type: ignore[import-untyped]

    return pd.read_parquet(path)
