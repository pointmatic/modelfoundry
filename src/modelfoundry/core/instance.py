# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`ModelInstance` — the notebook-shaped result object (FR-22, Story C.p).

A `ModelInstance` is a read-only handle to a materialized instance directory. Its
cached-property accessors lazily read the on-disk artifacts (metrics, confusion
matrix, calibration, predictions, trials, best params, figures), `predict` /
`predict_proba` delegate to the bound plugin, and `load(path)` reconstructs the
whole object from disk alone (FR-23) — the plugin is resolved from the manifest.

It is a frozen dataclass: the accessors cache into the instance `__dict__` (which
`functools.cached_property` writes directly, bypassing the frozen `__setattr__`),
so repeated reads are cheap while the handle stays immutable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, overload

import numpy as np

from modelfoundry.core.manifest import Manifest
from modelfoundry.plugins.base import InstanceArtifacts, Plugin
from modelfoundry.plugins.discovery import discover_plugins


@dataclass(frozen=True)
class ModelInstance:
    """A read-only view of a materialized ModelInstance directory."""

    path: Path
    manifest: Manifest
    plugin: Plugin

    @classmethod
    def load(cls, path: str | Path, *, plugin: Plugin | None = None) -> ModelInstance:
        """Reconstruct a `ModelInstance` from its dir; the plugin resolves from the manifest."""
        path = Path(path)
        manifest = Manifest.load(path / "manifest.json")
        if plugin is None:
            plugins = discover_plugins()
            if manifest.plugin not in plugins:
                from modelfoundry.core.errors import PluginError

                raise PluginError(
                    f"manifest names plugin {manifest.plugin!r} but it is not discoverable",
                    detail={"plugin": manifest.plugin},
                )
            plugin = plugins[manifest.plugin]
        return cls(path=path, manifest=manifest, plugin=plugin)

    # --- evaluation accessors ---

    @cached_property
    def evaluation(self) -> dict[str, dict[str, Any]]:
        """The full `{split: {metric: value}}` evaluation dict."""
        return _read_json(self.path / "evaluation" / "metrics.json") or {}

    @cached_property
    def metrics(self) -> dict[str, dict[str, Any]]:
        """Alias for `evaluation` — the per-split metric dict."""
        return self.evaluation

    @cached_property
    def confusion_matrix(self) -> dict[str, np.ndarray]:
        """Per-split confusion matrices from `evaluation/confusion_matrix.npz` (or `{}`)."""
        path = self.path / "evaluation" / "confusion_matrix.npz"
        if not path.is_file():
            return {}
        with np.load(path) as npz:
            return {key: npz[key] for key in npz.files}

    @cached_property
    def calibration(self) -> Any:
        """The calibration reliability curve DataFrame (or `None`)."""
        return _read_parquet(self.path / "evaluation" / "calibration.parquet")

    @cached_property
    def predictions(self) -> Any:
        """The per-record predictions DataFrame (or `None`)."""
        return _read_parquet(self.path / "evaluation" / "predictions.parquet")

    # --- optimization accessors ---

    @cached_property
    def trials(self) -> Any:
        """The Optuna trials DataFrame (or `None` when no optimization ran)."""
        return _read_parquet(self.path / "optimization" / "trials.parquet")

    @cached_property
    def best_params(self) -> dict[str, Any] | None:
        """The best hyperparameters from `optimization/best-params.json` (or `None`)."""
        path = self.path / "optimization" / "best-params.json"
        params: dict[str, Any] | None = _read_json(path)
        return params

    # --- model summary (FR-27, Story C.q) ---

    @cached_property
    def summary(self) -> dict[str, Any] | None:
        """The structured model summary from `model/summary.json` (or `None`).

        Shape: `{input_size, layers: [{type, depth, leaf, output_shape,
        param_count, trainable_params, mult_adds}], total_params,
        trainable_params, non_trainable_params, total_mult_adds}`.
        """
        payload: dict[str, Any] | None = _read_json(self.path / "model" / "summary.json")
        return payload

    @cached_property
    def summary_text(self) -> str | None:
        """The torchinfo text render from `model/summary.txt` (or `None`).

        Substrate-neutral: `print(mi.summary_text)` renders in any notebook host;
        the FR-17 `inspect --view model_summary` CLI surface (Story D.g) reads it.
        """
        path = self.path / "model" / "summary.txt"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    # --- figures ---

    @cached_property
    def figures(self) -> dict[str, bytes]:
        """Reporting visualization PNGs keyed by name (`{}` when none rendered)."""
        viz_dir = self.path / "report" / "visualizations"
        if not viz_dir.is_dir():
            return {}
        return {png.stem: png.read_bytes() for png in sorted(viz_dir.glob("*.png"))}

    # --- inference ---

    @cached_property
    def _model(self) -> Any:
        return self.plugin.load_model(self.path / "model")

    def predict(self, X: Any) -> Any:
        """Predicted labels for `X` (delegated to the plugin)."""
        return self.plugin.predict(self._model, X)

    def predict_proba(self, X: Any) -> Any:
        """Per-class probabilities for `X` (delegated to the plugin)."""
        return self.plugin.predict_proba(self._model, X)

    # --- inspection ---

    @overload
    def inspect(self, *, view: None = ...) -> InspectionView: ...
    @overload
    def inspect(self, *, view: str) -> bytes | Manifest: ...

    def inspect(self, *, view: str | None = None) -> InspectionView | bytes | Manifest:
        """Inspect the instance (FR-17, exploration mode — nothing is persisted).

        With no `view`, returns an `InspectionView` exposing the notebook-facing
        accessors (behavior 1). With `view="view_manifest"` (or `"manifest"`)
        returns the `Manifest`; any other `view` name is a plugin visualization op
        whose PNG bytes are returned (behavior 2). An unknown / unrenderable view
        raises `InspectionError`.
        """
        if view is None:
            return InspectionView(self)
        if view in ("view_manifest", "manifest"):
            return self.manifest
        return self._render_view(view)

    def _render_view(self, view: str, **params: Any) -> bytes:
        """Render a plugin visualization op `view` (with extra `params`) to PNG bytes."""
        from modelfoundry.core.errors import InspectionError, PluginError
        from modelfoundry.recipe.models import VisualizationSpec

        recipe = self._load_recipe()
        if recipe is None:
            raise InspectionError(
                f"cannot render view {view!r}: instance has no recipe.yml",
                detail={"view": view, "instance_dir": str(self.path)},
            )
        try:
            png = self.plugin.render_visualization(
                VisualizationSpec(op=view, mode="interactive", **params), self._artifacts(recipe)
            )
        except PluginError as exc:
            raise InspectionError(f"unknown view {view!r}", detail={"view": view}) from exc
        if png is None:
            raise InspectionError(
                f"view {view!r} produced nothing to render", detail={"view": view}
            )
        return png

    # --- report ---

    def render_report(self) -> str:
        """Re-render `report/` atomically and return the Markdown (falls back to the saved copy)."""
        recipe = self._load_recipe()
        if recipe is not None:
            from modelfoundry.reporting.visualizations import rerender_report

            rerender_report(self.path, self._artifacts(recipe), recipe, self.plugin)
        report_md = self.path / "report" / "report.md"
        return report_md.read_text(encoding="utf-8") if report_md.is_file() else ""

    def _load_recipe(self) -> Any:
        recipe_yml = self.path / "recipe.yml"
        if not recipe_yml.is_file():
            return None
        import yaml

        from modelfoundry.recipe.models import ModelRecipe

        return ModelRecipe(**yaml.safe_load(recipe_yml.read_text(encoding="utf-8")))

    def _artifacts(self, recipe: Any) -> InstanceArtifacts:
        return InstanceArtifacts(
            history=_read_parquet(self.path / "training" / "history.parquet"),
            evaluation=self.evaluation or None,
            predictions=self.predictions,
            trials=self.trials,
            recipe=recipe,
            manifest=self.manifest,
        )


@dataclass(frozen=True)
class InspectionView:
    """Notebook-facing exploration accessors over a materialized instance (FR-17 behavior 1).

    Each accessor renders or returns one artifact on demand; accessors that depend
    on an unfilled stage (e.g. `view_trials()` with no Optimization stage, or any
    accessor on a partial instance whose artifact is absent) raise `InspectionError`
    with a clear message rather than returning empty data.
    """

    instance: ModelInstance

    def view_manifest(self) -> Manifest:
        """The instance `Manifest`."""
        return self.instance.manifest

    def view_training_curves(self) -> bytes:
        """The training-curves visualization (PNG bytes)."""
        return self.instance._render_view("training_curves")

    def view_confusion_matrix(self, split: str) -> bytes:
        """The confusion-matrix visualization for `split` (PNG bytes)."""
        self._require_eval_split(split)
        return self.instance._render_view("confusion_matrix", split=split)

    def view_calibration(self, split: str) -> bytes:
        """The calibration-curve visualization for `split` (PNG bytes)."""
        self._require_eval_split(split)
        return self.instance._render_view("calibration_curve", split=split)

    def view_predictions(self, split: str, n: int = 16) -> Any:
        """The first `n` per-record predictions for `split` (a DataFrame)."""
        from modelfoundry.core.errors import InspectionError

        predictions = self.instance.predictions
        if predictions is None:
            raise InspectionError(
                "no predictions: the evaluation stage did not run",
                detail={"instance_dir": str(self.instance.path)},
            )
        rows = predictions[predictions["split"] == split] if "split" in predictions else predictions
        if len(rows) == 0:
            raise InspectionError(
                f"no predictions for split {split!r}", detail={"split": split}
            )
        return rows.head(n)

    def view_trials(self) -> Any:
        """The Optuna trials DataFrame (raises if no Optimization stage ran)."""
        from modelfoundry.core.errors import InspectionError

        trials = self.instance.trials
        if trials is None:
            raise InspectionError(
                "no trials: the instance has no Optimization stage",
                detail={"instance_dir": str(self.instance.path)},
            )
        return trials

    def _require_eval_split(self, split: str) -> None:
        from modelfoundry.core.errors import InspectionError

        if split not in self.instance.evaluation:
            raise InspectionError(
                f"no evaluation for split {split!r}; available: {sorted(self.instance.evaluation)}",
                detail={"split": split},
            )


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_parquet(path: Path) -> Any:
    if not path.is_file():
        return None
    import pandas as pd  # type: ignore[import-untyped]

    return pd.read_parquet(path)
