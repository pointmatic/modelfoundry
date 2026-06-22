# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Tests for the `init` deterministic scaffolder (Story D.i, FR-21).

`scaffold_recipe` resolves the bound DataRefinery instance and writes a baseline
ModelFoundry recipe shaped to the dataset (num_classes, in_channels, splits).
`resolve_data_instance` is monkeypatched to a synthesized DR instance so the
scaffold logic is exercised without DataRefinery path-resolution; the
materialize check binds the same instance object directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("typer")

import yaml
from typer.testing import CliRunner

from modelfoundry.cli.app import app
from modelfoundry.cli.commands.init_cmd import run
from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import RecipeError
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.scaffolder.init import scaffold_recipe

_DR_CLASSES = ("c0", "c1", "c2")
_DR_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}


def _build_dr_instance(tmp_path: Path) -> Any:
    """A synthesized DataRefinery instance (8x8 RGB, 3 classes, train/val/test)."""
    import json
    import textwrap

    import datarefinery as dr
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datarefinery.pipeline.manifest import Manifest as DRManifest
    from datarefinery.recipe.loader import load as dr_load_recipe
    from datarefinery.recipe.segments import recipe_identity_hash
    from PIL import Image

    from modelfoundry.pipeline.data_binding import DataRefineryInstance

    dr_yaml = textwrap.dedent(
        """
        schema_version: 3
        plugin: image_classification
        seed: 1
        Input: {sources: [{name: t, type: image_folder, path: /x}]}
        Output:
          record_schema: {image: {dtype: uint8, shape: [8, 8, 3]}, label: {dtype: str},
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
    recipe_hash = recipe_identity_hash(dr_recipe)

    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")
    stats_dir = inst / "fitted_statistics" / "norm"
    stats_dir.mkdir(parents=True)
    # Realistic 0-255-scale normalize stats (the adapter applies them in 0-255
    # pixel units, Story H.a) so the validator's input-contract check (FR-2
    # check 21) passes; [0,1]-scale stats would read as a units mismatch.
    pq.write_table(pa.table({"value": [120.0, 100.0, 80.0]}), stats_dir / "mean.parquet")  # type: ignore[no-untyped-call]
    pq.write_table(pa.table({"value": [60.0, 55.0, 50.0]}), stats_dir / "std.parquet")  # type: ignore[no-untyped-call]

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
                Image.new("RGB", (8, 8), _DR_COLORS[cls]).save(png)
                records.append(
                    {"record_id": f"{split}/{cls}/img_{i}", "label": cls, "path": str(png)}
                )
        (dataset_dir / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
        counts[split] = len(records)

    manifest = DRManifest(
        datarefinery_version="0.23.0",
        plugin="image_classification",
        plugin_version="1",
        recipe_hash=recipe_hash,
        input_hash="0" * 64,
        seed=1,
        created_at=datetime.now(UTC),
        elapsed_seconds=0.1,
        record_counts=counts,
        warnings=[],
        sinks={},
        sinks_skipped={},
    )
    (inst / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    loaded = dr.Instance.load(inst)
    return DataRefineryInstance(
        path=inst,
        manifest=loaded.manifest,
        recipe=loaded.recipe,
        splits=tuple(loaded.manifest.record_counts.keys()),
        label_schema=loaded.recipe.Labels.model_dump(),
        record_schema={k: v.model_dump() for k, v in loaded.recipe.Output.record_schema.items()},
        fitted_statistics=loaded.fitted_statistics,
    )


def _patch_resolve(monkeypatch: pytest.MonkeyPatch, instance: Any) -> None:
    monkeypatch.setattr(
        "modelfoundry.scaffolder.init.resolve_data_instance", lambda spec, config: instance
    )


def _scaffold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, plugin: str = "pytorch") -> Path:
    instance = _build_dr_instance(tmp_path)
    _patch_resolve(monkeypatch, instance)
    out = tmp_path / "recipe.yml"
    cfg = RuntimeConfig(data_cache_root=tmp_path)
    return scaffold_recipe(out, tmp_path / "dr_recipe.yml", plugin=plugin, config=cfg)


# --- scaffold content ---


def test_scaffold_writes_loadable_pytorch_recipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = _scaffold(tmp_path, monkeypatch)
    assert out.is_file()
    recipe = load_recipe(out)
    assert recipe.plugin == "pytorch"
    assert recipe.Architecture["type"] == "resnet20"
    assert recipe.Architecture["num_classes"] == 3  # from instance_num_classes
    assert recipe.Architecture["in_channels"] == 3  # from record_schema shape


def test_scaffold_stamps_copyright_header(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out = _scaffold(tmp_path, monkeypatch)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Copyright (c) 2026 Pointmatic")
    assert "SPDX-License-Identifier: Apache-2.0" in text


def test_scaffold_sets_early_stopping_when_val_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = load_recipe(_scaffold(tmp_path, monkeypatch))
    assert recipe.Training.early_stopping is not None
    assert recipe.Training.early_stopping.monitor == "val_loss"


def test_scaffold_eval_split_prefers_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recipe = load_recipe(_scaffold(tmp_path, monkeypatch))
    assert recipe.Evaluation.splits == ["test"]
    assert recipe.Evaluation.primary_metric == "accuracy"


def test_scaffold_surfaces_imbalance_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Story H.p (R3.1): imbalance-aware per-class metrics are first-class in the
    # scaffolded baseline, not accuracy alone.
    recipe = load_recipe(_scaffold(tmp_path, monkeypatch))
    for metric in (
        "macro_f1",
        "per_class_f1",
        "per_class_precision",
        "per_class_recall",
        "confusion_matrix",
    ):
        assert metric in recipe.Evaluation.metrics


def test_scaffold_sklearn_emits_mlp_classifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recipe = load_recipe(_scaffold(tmp_path, monkeypatch, plugin="sklearn"))
    assert recipe.plugin == "sklearn"
    assert recipe.Architecture["type"] == "mlp_classifier"


def test_scaffold_refuses_existing_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = _build_dr_instance(tmp_path)
    _patch_resolve(monkeypatch, instance)
    out = tmp_path / "recipe.yml"
    out.write_text("# pre-existing\n", encoding="utf-8")
    with pytest.raises(RecipeError):
        scaffold_recipe(out, tmp_path / "dr_recipe.yml", config=RuntimeConfig())
    # force overwrites
    scaffold_recipe(out, tmp_path / "dr_recipe.yml", force=True, config=RuntimeConfig())
    assert load_recipe(out).Architecture["type"] == "resnet20"


# --- validate + materialize the scaffolded recipe ---


def test_scaffolded_recipe_validates_clean(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from modelfoundry.core.modelfoundry import ModelFoundry

    instance = _build_dr_instance(tmp_path)
    _patch_resolve(monkeypatch, instance)
    out = scaffold_recipe(
        tmp_path / "recipe.yml", tmp_path / "dr_recipe.yml", config=RuntimeConfig()
    )
    cfg = RuntimeConfig(cache_root=tmp_path / "c")
    mf = ModelFoundry.from_recipe(out, data=instance, config=cfg)
    report = mf.validate()
    failures = [(c.id, c.name, c.message) for c in report.checks if not c.passed]
    assert report.passed, failures


def test_scaffolded_recipe_materializes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("torch")
    from modelfoundry.core.modelfoundry import ModelFoundry

    instance = _build_dr_instance(tmp_path)
    _patch_resolve(monkeypatch, instance)
    out = scaffold_recipe(
        tmp_path / "recipe.yml", tmp_path / "dr_recipe.yml", config=RuntimeConfig()
    )
    # Trim for a fast smoke: 1 epoch, drop expectations (a 1-epoch tiny model
    # won't reliably clear the better-than-chance baseline assertion).
    spec = yaml.safe_load(out.read_text(encoding="utf-8"))
    spec["Training"]["max_epochs"] = 1
    spec["Training"]["device"] = "cpu"
    spec.pop("OutputExpectations", None)
    out.write_text(yaml.safe_dump(spec), encoding="utf-8")

    cfg = RuntimeConfig(cache_root=tmp_path / "c")
    mf = ModelFoundry.from_recipe(out, data=instance, config=cfg)
    instance_obj = mf.materialize()
    assert (instance_obj.path / "manifest.json").is_file()


# --- CLI wiring ---


def test_cli_init_creates_recipe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _build_dr_instance(tmp_path)
    _patch_resolve(monkeypatch, instance)
    out = tmp_path / "recipe.yml"
    dr_recipe = str(tmp_path / "dr_recipe.yml")
    result = CliRunner().invoke(
        app, ["--data-cache-root", str(tmp_path), "init", str(out), "--data", dr_recipe]
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()


def test_cli_init_missing_data_is_usage_error(tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["init", str(tmp_path / "r.yml")])
    assert result.exit_code == 2


def test_run_returns_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _build_dr_instance(tmp_path)
    _patch_resolve(monkeypatch, instance)
    out = tmp_path / "recipe.yml"
    rc = run(out, tmp_path / "dr_recipe.yml", RuntimeConfig(data_cache_root=tmp_path))
    assert rc == 0
    assert out.is_file()
