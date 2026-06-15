# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `materialize` CLI command (Story D.e, FR-3).

D.e ships the verb (--variant/--seed/--overwrite, final summary, exit codes), a
stage-level progress seam (`StageObserver` on the runner, rendered by the CLI's
`RichStageProgress`), and the reusable `suppress_fd_output` fd-level context
manager. The deep in-trainer per-epoch tables + per-trial Optuna bars are
deferred to Story D.e.1.

Most tests are torch-free: the observer, the fd-suppression utility, the summary
renderer, the runner seam, and `run()` delegation (monkeypatched `from_recipe`).
One end-to-end test does a real 3-epoch + 2-trial materialize on a synthesized
DataRefinery fixture and is skipped when torch is absent.
"""

from __future__ import annotations

import io
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("typer")

from rich.console import Console
from typer.testing import CliRunner

from modelfoundry.cli.app import app
from modelfoundry.cli.commands.materialize_cmd import RichStageProgress, render_summary, run
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.manifest import ExpectationOutcome, Manifest, OptimizationManifest
from modelfoundry.core.modelfoundry import ModelFoundry
from modelfoundry.pipeline.progress import suppress_fd_output


@pytest.fixture(autouse=True)
def _restore_determinism() -> Any:
    yield
    try:
        import torch

        torch.use_deterministic_algorithms(False)
    except ImportError:
        pass


class _ProgressRecorder:
    """A `ProgressReporter` (+ `StageObserver`) that records the events it receives."""

    def __init__(self) -> None:
        self.epochs: list[int] = []
        self.trials_started: list[int] = []
        self.trials_done: list[int] = []

    def on_stage_start(self, stage: str) -> None: ...
    def on_stage_done(self, stage: str, elapsed: float) -> None: ...
    def on_stage_skipped(self, stage: str) -> None: ...

    def on_epoch(self, epoch: int, record: dict[str, float]) -> None:
        self.epochs.append(epoch)

    def on_trial_start(self, trial: int) -> None:
        self.trials_started.append(trial)

    def on_trial_done(self, trial: int, value: float | None) -> None:
        self.trials_done.append(trial)


def _manifest(**overrides: Any) -> Manifest:
    base: dict[str, Any] = {
        "plugin": "pytorch",
        "plugin_version": "0.4.0",
        "recipe_hash": "a" * 64,
        "data_instance_hash": "b" * 64,
        "bound_data_instance": Path("/dr/cache/instances/abc/def/1"),
        "seed": 7,
        "variant": None,
        "created_at": datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC),
        "elapsed_seconds": 12.5,
        "epoch_history": 3,
        "evaluation": {"val": {"accuracy": 0.9123}},
        "output_expectations": [
            ExpectationOutcome(
                metric="accuracy", split="val", op="gte", expected=0.5,
                observed=0.9123, passed=True,
            )
        ],
    }
    base.update(overrides)
    return Manifest(**base)


# --- RichStageProgress: the stage-level observer ---


def _drain(observer: RichStageProgress, buf: io.StringIO) -> str:
    observer.on_stage_start("training")
    observer.on_stage_done("training", 1.25)
    observer.on_stage_skipped("evaluation")
    return buf.getvalue()


def test_stage_observer_renders_start_and_done() -> None:
    buf = io.StringIO()
    out = _drain(RichStageProgress(Console(file=buf, width=120)), buf)
    assert "training" in out
    assert "1.25" in out  # elapsed on the done event


def test_stage_observer_renders_skipped() -> None:
    buf = io.StringIO()
    out = _drain(RichStageProgress(Console(file=buf, width=120)), buf)
    assert "evaluation" in out
    assert "skip" in out.lower()


def test_stage_observer_renders_epoch_row() -> None:
    buf = io.StringIO()
    RichStageProgress(Console(file=buf, width=120)).on_epoch(
        2, {"epoch": 2.0, "train_loss": 0.4321, "val_accuracy": 0.75}
    )
    out = buf.getvalue()
    assert "epoch" in out.lower() and "2" in out
    assert "0.4321" in out


def test_stage_observer_renders_trial_events() -> None:
    buf = io.StringIO()
    progress = RichStageProgress(Console(file=buf, width=120))
    progress.on_trial_start(0)
    progress.on_trial_done(0, 0.9123)
    out = buf.getvalue()
    assert "trial" in out.lower() and "0" in out
    assert "0.9123" in out


# --- suppress_fd_output: fd-level os.dup2 redirect ---


def test_suppress_fd_output_silences_then_restores_fd1() -> None:
    with tempfile.TemporaryFile() as sink:
        saved = os.dup(1)
        os.dup2(sink.fileno(), 1)  # route fd 1 to our capture file
        try:
            with suppress_fd_output():
                os.write(1, b"SUPPRESSED")  # should land in /dev/null, not the sink
            os.write(1, b"RESTORED")  # fd 1 restored to the sink
        finally:
            os.dup2(saved, 1)
            os.close(saved)
        sink.seek(0)
        captured = sink.read()
    assert b"RESTORED" in captured
    assert b"SUPPRESSED" not in captured


# --- render_summary: the success panel ---


def _instance(manifest: Manifest, path: str = "/mf/cache/x/y/7") -> Any:
    return SimpleNamespace(path=Path(path), manifest=manifest)


def _render_summary_to_str(instance: Any, primary_metric: str = "accuracy") -> str:
    buf = io.StringIO()
    render_summary(
        instance, Path("recipe.yml"), primary_metric=primary_metric,
        console=Console(file=buf, width=200),
    )
    return buf.getvalue()


def test_render_summary_shows_path_plugin_metric_expectations() -> None:
    out = _render_summary_to_str(_instance(_manifest()))
    assert "/mf/cache/x/y/7" in out
    assert "pytorch" in out
    assert "accuracy" in out and "0.9123" in out
    assert "1 passed" in out


def test_render_summary_includes_optimization_when_present() -> None:
    manifest = _manifest(
        optimization=OptimizationManifest(
            sampler="tpe", pruner="none", n_trials=2, best_value=0.91
        )
    )
    out = _render_summary_to_str(_instance(manifest))
    assert "2" in out  # n_trials
    assert "tpe" in out


# --- run(): delegation, exit code, flag threading ---


def _fake_mf(instance: Any, captured: dict[str, Any]) -> SimpleNamespace:
    recipe = SimpleNamespace(Evaluation=SimpleNamespace(primary_metric="accuracy"))

    def _materialize(*, stage_observer: Any = None) -> Any:
        captured["observer"] = stage_observer
        return instance

    return SimpleNamespace(recipe=recipe, materialize=_materialize)


def _patch_from_recipe(monkeypatch: pytest.MonkeyPatch, mf: Any, captured: dict[str, Any]) -> None:
    def _fake(recipe: Any, *, data: Any = None, config: Any = None,
              variant: Any = None, seed: Any = None) -> Any:
        captured["config"] = config
        captured["variant"] = variant
        captured["seed"] = seed
        return mf

    monkeypatch.setattr(ModelFoundry, "from_recipe", _fake)


def test_run_returns_0_and_renders_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_from_recipe(monkeypatch, _fake_mf(_instance(_manifest()), captured), captured)
    buf = io.StringIO()
    rc = run(Path("r.yml"), RuntimeConfig(), progress=False, console=Console(file=buf))
    assert rc == 0
    assert "pytorch" in buf.getvalue()
    assert captured["observer"] is None  # progress=False → no observer attached


def test_run_attaches_observer_when_progress_true(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_from_recipe(monkeypatch, _fake_mf(_instance(_manifest()), captured), captured)
    run(Path("r.yml"), RuntimeConfig(), progress=True, console=Console(file=io.StringIO()))
    assert isinstance(captured["observer"], RichStageProgress)


def test_run_overwrite_threads_into_config(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_from_recipe(monkeypatch, _fake_mf(_instance(_manifest()), captured), captured)
    run(Path("r.yml"), RuntimeConfig(), overwrite=True, progress=False,
        console=Console(file=io.StringIO()))
    assert captured["config"].overwrite is True


def test_run_threads_variant_and_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_from_recipe(monkeypatch, _fake_mf(_instance(_manifest()), captured), captured)
    run(Path("r.yml"), RuntimeConfig(), variant="cpu_bench", seed=99, progress=False,
        console=Console(file=io.StringIO()))
    assert captured["variant"] == "cpu_bench"
    assert captured["seed"] == 99


# --- runner stage-observer seam ---


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def on_stage_start(self, stage: str) -> None:
        self.events.append(("start", stage))

    def on_stage_done(self, stage: str, elapsed: float) -> None:
        self.events.append(("done", stage))

    def on_stage_skipped(self, stage: str) -> None:
        self.events.append(("skipped", stage))


def test_runner_stage_invokes_observer_start_and_done() -> None:
    from modelfoundry.pipeline.runner import MaterializeRunner

    recorder = _Recorder()
    recipe: Any = SimpleNamespace(seed=0)
    data: Any = SimpleNamespace()
    plugin: Any = SimpleNamespace()
    runner = MaterializeRunner(
        recipe=recipe,
        data_instance=data,
        plugin=plugin,
        runtime_config=RuntimeConfig(),
        stage_observer=recorder,
    )
    assert runner._stage("training", lambda: 42) == 42
    assert recorder.events == [("start", "training"), ("done", "training")]


# --- CLI wiring ---


def test_cli_materialize_missing_recipe_arg_is_usage_error() -> None:
    result = CliRunner().invoke(app, ["materialize"])
    assert result.exit_code == 2


def test_cli_materialize_delegates_and_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_from_recipe(monkeypatch, _fake_mf(_instance(_manifest()), captured), captured)
    result = CliRunner().invoke(app, ["materialize", "r.yml", "--no-progress"])
    assert result.exit_code == 0, result.output
    assert "pytorch" in result.output


# --- end-to-end: real 3-epoch + 2-trial materialize (torch only) ---

_DR_CLASSES = ("c0", "c1", "c2")
_DR_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}


def _build_dr_instance(tmp_path: Path) -> Any:
    """A minimal synthesized DataRefinery instance (mirrors the integration fixtures)."""
    import hashlib
    import json
    import textwrap

    import datarefinery as dr
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datarefinery.pipeline.manifest import Manifest as DRManifest
    from datarefinery.recipe.canonical import to_canonical_bytes
    from datarefinery.recipe.loader import load as dr_load_recipe
    from PIL import Image

    from modelfoundry.pipeline.data_binding import DataRefineryInstance

    dr_yaml = textwrap.dedent(
        """
        schema_version: 2
        plugin: image_classification
        seed: 1
        Input: {sources: [{name: t, type: image_folder, path: /x}]}
        Output:
          record_schema: {image: {dtype: uint8, shape: [4, 4, 3]}, label: {dtype: str},
                          path: {dtype: str}}
        Labels: {field: label, source: {kind: derived, derivation: parent_directory_name}}
        Transformations:
          - {name: norm, op: normalize}
        Splits: {ratios: {train: 0.6, val: 0.2, test: 0.2}, seed: 1, stratify_by: label}
        """
    ).strip()
    recipe_path = tmp_path / "dr_recipe.yml"
    recipe_path.write_text(dr_yaml, encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_path)
    recipe_hash = hashlib.sha256(to_canonical_bytes(dr_recipe)).hexdigest()

    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")
    stats_dir = inst / "fitted_statistics" / "norm"
    stats_dir.mkdir(parents=True)
    pq.write_table(pa.table({"value": [0.5, 0.3, 0.1]}), stats_dir / "mean.parquet")  # type: ignore[no-untyped-call]
    pq.write_table(pa.table({"value": [0.25, 0.5, 0.2]}), stats_dir / "std.parquet")  # type: ignore[no-untyped-call]

    dataset_dir = inst / "dataset"
    dataset_dir.mkdir()
    images_dir = inst / "images"
    images_dir.mkdir()
    counts: dict[str, int] = {}
    for split, per_class in (("train", 6), ("val", 2), ("test", 2)):
        records = []
        for cls in _DR_CLASSES:
            for i in range(per_class):
                png = images_dir / f"{split}_{cls}_{i}.png"
                Image.new("RGB", (4, 4), _DR_COLORS[cls]).save(png)
                records.append(
                    {"record_id": f"{split}/{cls}/img_{i}", "label": cls, "path": str(png)}
                )
        (dataset_dir / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
        counts[split] = len(records)

    manifest = DRManifest(
        datarefinery_version="0.19.0", plugin="image_classification", plugin_version="1",
        recipe_hash=recipe_hash, input_hash="0" * 64, seed=1,
        created_at=datetime.now(UTC), elapsed_seconds=0.1, record_counts=counts,
        warnings=[], sinks={}, sinks_skipped={},
    )
    (inst / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    loaded = dr.Instance.load(inst)
    return DataRefineryInstance(
        path=inst, manifest=loaded.manifest, recipe=loaded.recipe,
        splits=tuple(loaded.manifest.record_counts.keys()),
        label_schema=loaded.recipe.Labels.model_dump(),
        record_schema={k: v.model_dump() for k, v in loaded.recipe.Output.record_schema.items()},
        fitted_statistics=loaded.fitted_statistics,
    )


def _write_model_recipe(tmp_path: Path, *, max_epochs: int, n_trials: int) -> Path:
    import yaml

    recipe = {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "num_classes": 3,
            "layers": [{"op": "Flatten"}, {"op": "Linear", "in_features": 48, "out_features": 3}],
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {"max_epochs": max_epochs, "batch_size": 4, "num_workers": 0, "device": "cpu"},
        "Evaluation": {
            "splits": ["val"], "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1", "confusion_matrix"],
        },
    }
    if n_trials > 0:
        recipe["Optimization"] = {
            "sampler": "tpe", "pruner": "none", "n_trials": n_trials,
            "max_epochs_per_trial": 1,
            "search_space": {"Optimizer.learning_rate": {"log_uniform": [1e-4, 1e-2]}},
        }
    path = tmp_path / "recipe.yml"
    path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    return path


def test_cli_materialize_end_to_end_creates_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("torch")

    data = _build_dr_instance(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache", data_cache_root=tmp_path)
    recipe_path = _write_model_recipe(tmp_path, max_epochs=3, n_trials=2)
    real = ModelFoundry.from_recipe(recipe_path, data=data, config=config)
    monkeypatch.setattr(ModelFoundry, "from_recipe", lambda *a, **k: real)

    buf = io.StringIO()
    rc = run(recipe_path, config, progress=True, console=Console(file=buf, width=200))

    assert rc == 0
    assert real.paths.instance_dir.exists()  # instance directory created + promoted
    out = buf.getvalue()
    assert "materialized" in out.lower()
    assert "training" in out  # stage progress streamed
    assert "epoch" in out.lower()  # D.e.1 per-epoch rows
    assert "trial" in out.lower()  # D.e.1 per-trial events


# --- D.e.1: per-epoch / per-trial progress reaches the plugins ---


def test_run_training_reports_each_epoch(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    from modelfoundry.plugins.discovery import discover_plugins
    from modelfoundry.plugins.pytorch.trainer import run_training
    from modelfoundry.recipe.loader import load_recipe

    data = _build_dr_instance(tmp_path)
    recipe = load_recipe(_write_model_recipe(tmp_path, max_epochs=3, n_trials=0))
    model = discover_plugins()["pytorch"].build_model(recipe.Architecture)

    recorder = _ProgressRecorder()
    run_training(recipe.Training, model, recipe, data, 7, tmp_path / "t", progress=recorder)
    assert recorder.epochs == [1, 2, 3]


def test_run_training_silent_without_progress(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    from modelfoundry.plugins.discovery import discover_plugins
    from modelfoundry.plugins.pytorch.trainer import run_training
    from modelfoundry.recipe.loader import load_recipe

    data = _build_dr_instance(tmp_path)
    recipe = load_recipe(_write_model_recipe(tmp_path, max_epochs=2, n_trials=0))
    model = discover_plugins()["pytorch"].build_model(recipe.Architecture)

    # No progress reporter → trainer runs to completion without raising.
    result = run_training(recipe.Training, model, recipe, data, 7, tmp_path / "t")
    assert result.epochs_run == 2


def test_run_optimization_reports_each_trial(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    from modelfoundry.plugins.pytorch.optimization import run_optimization
    from modelfoundry.recipe.loader import load_recipe

    data = _build_dr_instance(tmp_path)
    recipe = load_recipe(_write_model_recipe(tmp_path, max_epochs=1, n_trials=2))
    assert recipe.Optimization is not None

    recorder = _ProgressRecorder()
    run_optimization(recipe.Optimization, recipe, data, 7, tmp_path / "o", progress=recorder)
    assert recorder.trials_started == [0, 1]
    assert recorder.trials_done == [0, 1]
