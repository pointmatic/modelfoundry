# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `pipeline.data_binding.resolve_data_instance`.

Fixtures hand-build a DataRefinery instance directory using DR's own pydantic
models (Recipe + Manifest), bypassing `materialize` for speed and isolation.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from datarefinery.pipeline.manifest import Manifest as DRManifest
from datarefinery.recipe.canonical import to_canonical_bytes
from datarefinery.recipe.loader import load as dr_load_recipe

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import DataBindingError
from modelfoundry.pipeline.data_binding import (
    DataRefineryInstance,
    resolve_data_instance,
)
from modelfoundry.recipe.models import DataSpec

# A minimal DR recipe that loads via DR's own loader. Declares the canonical
# DataRefinery schema v2 (the only shape persisted as `recipe.json` since
# ml-datarefinery 0.19.0); a v1 source recipe migrates to byte-identical v2 on
# load, so binding sees `schema_version: 2` either way.
_DR_RECIPE_YAML = textwrap.dedent(
    """
    schema_version: 2
    plugin: image_classification
    seed: 11
    Input:
      sources:
        - name: train
          type: image_folder
          path: /fixture/images
    Output:
      record_schema:
        image: {dtype: uint8, shape: [8, 8, 3]}
        label: {dtype: str}
        path:  {dtype: str}
    Labels:
      field: label
      source:
        kind: derived
        derivation: parent_directory_name
    Splits:
      ratios: {train: 0.7, val: 0.15, test: 0.15}
      seed: 11
      stratify_by: label
    """
).strip()


def _make_records(classes: tuple[str, ...], per_class: int, split: str) -> list[dict[str, Any]]:
    return [
        {
            "record_id": f"{split}/{cls}/img_{i}",
            "label": cls,
            "path": f"/fixture/{cls}/{split}_{i}.png",
        }
        for cls in classes
        for i in range(per_class)
    ]


def _build_fixture(
    tmp_path: Path,
    *,
    classes: tuple[str, ...] = ("c0", "c1", "c2"),
    seed: int = 11,
    write_failed_marker: bool = False,
    manifest_partial: bool = False,
    include_aggressive_variant: bool = False,
    aggressive_sidecar_present: bool = True,
    extra_input_dir: bool = False,
) -> tuple[Path, Path, Path]:
    """Hand-build a DR instance + return (recipe_yaml_path, cache_root, instance_dir)."""
    recipe_yaml = tmp_path / "dr_recipe.yml"
    recipe_yaml.write_text(_DR_RECIPE_YAML, encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_yaml)
    recipe_hash = hashlib.sha256(to_canonical_bytes(dr_recipe)).hexdigest()
    input_hash = "0" * 64

    cache_root = tmp_path / "dr_cache"
    instance_dir = (
        cache_root / "instances" / recipe_hash[:16] / input_hash[:16] / str(seed)
    )
    instance_dir.mkdir(parents=True)
    (instance_dir / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")

    train_records = _make_records(classes, per_class=3, split="train")
    val_records = _make_records(classes, per_class=1, split="val")
    test_records = _make_records(classes, per_class=1, split="test")

    if include_aggressive_variant:
        sidecar_relative = "train/images/img_0__v000.png"
        variant: dict[str, Any] = {
            "record_id": "train/c0/img_0__v000",
            "source_record_id": "train/c0/img_0",
            "variant_index": 0,
            "label": "c0",
            "image_path": sidecar_relative,
            "flip_seed": 12345,
        }
        train_records.append(variant)
        if aggressive_sidecar_present:
            sidecar = instance_dir / "dataset" / sidecar_relative
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            sidecar.write_bytes(b"\x89PNG\r\n\x1a\n")  # not a real PNG, just a sentinel

    dataset_dir = instance_dir / "dataset"
    dataset_dir.mkdir(exist_ok=True)
    for split, recs in (("train", train_records), ("val", val_records), ("test", test_records)):
        (dataset_dir / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in recs), encoding="utf-8"
        )

    record_counts = {
        "train": len(train_records),
        "val": len(val_records),
        "test": len(test_records),
    }
    manifest = DRManifest(
        datarefinery_version="0.19.0",
        plugin="image_classification",
        plugin_version="1",
        recipe_hash=recipe_hash,
        input_hash=input_hash,
        seed=seed,
        created_at=datetime.now(UTC),
        elapsed_seconds=0.1,
        is_partial=manifest_partial,
        record_counts=record_counts,
        # `class_balance` is new in ml-datarefinery 0.18.0+; ModelFoundry binds
        # against `record_counts` and read-and-ignores this field for now
        # (Subphase C-1 §C10). Present here so every binding test exercises a
        # v0.19.0-shaped manifest.
        class_balance={
            split: dict.fromkeys(classes, total // len(classes))
            for split, total in record_counts.items()
        },
        warnings=[],
        sinks={},
        sinks_skipped={},
    )
    (instance_dir / "manifest.json").write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )

    if write_failed_marker:
        (instance_dir / "FAILED").write_text("{}", encoding="utf-8")

    if extra_input_dir:
        # Add a second input_hash dir with the same seed → ambiguous bind.
        other = cache_root / "instances" / recipe_hash[:16] / ("1" * 16) / str(seed)
        other.mkdir(parents=True)

    return recipe_yaml, cache_root, instance_dir


def _data_spec(recipe_yaml: Path) -> DataSpec:
    return DataSpec(recipe=recipe_yaml)


def _config(cache_root: Path) -> RuntimeConfig:
    return RuntimeConfig(data_cache_root=cache_root)


# --- happy path ---


def test_resolution_returns_wrapper(tmp_path: Path) -> None:
    recipe_yaml, cache_root, instance_dir = _build_fixture(tmp_path)
    inst = resolve_data_instance(_data_spec(recipe_yaml), _config(cache_root))
    assert isinstance(inst, DataRefineryInstance)
    assert inst.path == instance_dir
    assert set(inst.splits) == {"train", "val", "test"}
    assert inst.label_schema["field"] == "label"
    assert "label" in inst.record_schema and "image" in inst.record_schema


def test_cross_validation_helpers(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _build_fixture(tmp_path)
    inst = resolve_data_instance(_data_spec(recipe_yaml), _config(cache_root))
    assert inst.instance_provides_splits(["train", "val"]) is True
    assert inst.instance_provides_splits(["train", "missing"]) is False
    assert inst.instance_schema_version() == 2
    assert inst.instance_num_classes() == 3


# --- failure modes (vendor-dep-spec § Failure modes) ---


def test_missing_recipe_yaml_raises(tmp_path: Path) -> None:
    data_spec = DataSpec(recipe=tmp_path / "nope.yml")
    with pytest.raises(DataBindingError, match="recipe not found"):
        resolve_data_instance(data_spec, _config(tmp_path / "cache"))


def test_no_materialized_instance_raises(tmp_path: Path) -> None:
    recipe_yaml = tmp_path / "dr_recipe.yml"
    recipe_yaml.write_text(_DR_RECIPE_YAML, encoding="utf-8")
    with pytest.raises(DataBindingError, match="no materialized DataRefinery instance"):
        resolve_data_instance(_data_spec(recipe_yaml), _config(tmp_path / "empty_cache"))


def test_failed_marker_refused(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _build_fixture(tmp_path, write_failed_marker=True)
    with pytest.raises(DataBindingError, match="FAILED marker"):
        resolve_data_instance(_data_spec(recipe_yaml), _config(cache_root))


def test_manifest_is_partial_refused(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _build_fixture(tmp_path, manifest_partial=True)
    with pytest.raises(DataBindingError, match="partial"):
        resolve_data_instance(_data_spec(recipe_yaml), _config(cache_root))


def test_missing_aggressive_sidecar_refused(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _build_fixture(
        tmp_path,
        include_aggressive_variant=True,
        aggressive_sidecar_present=False,
    )
    with pytest.raises(DataBindingError, match="sidecar missing"):
        resolve_data_instance(_data_spec(recipe_yaml), _config(cache_root))


def test_aggressive_variant_with_sidecar_succeeds(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _build_fixture(
        tmp_path,
        include_aggressive_variant=True,
        aggressive_sidecar_present=True,
    )
    inst = resolve_data_instance(_data_spec(recipe_yaml), _config(cache_root))
    assert inst.splits  # resolution worked


def test_ambiguous_bind_refused(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _build_fixture(tmp_path, extra_input_dir=True)
    with pytest.raises(DataBindingError, match="ambiguous bind"):
        resolve_data_instance(_data_spec(recipe_yaml), _config(cache_root))


def test_schema_version_too_high_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patch the loader to return a recipe with schema_version=999.
    recipe_yaml = tmp_path / "dr_recipe.yml"
    recipe_yaml.write_text(_DR_RECIPE_YAML, encoding="utf-8")

    class _FakeRecipe:
        schema_version = 999
        seed = 11

    def _fake_load(path: Path) -> _FakeRecipe:
        return _FakeRecipe()

    monkeypatch.setattr(
        "modelfoundry.pipeline.data_binding._dr_loader.load", _fake_load
    )
    with pytest.raises(DataBindingError, match="higher than ModelFoundry's known max"):
        resolve_data_instance(_data_spec(recipe_yaml), _config(tmp_path / "c"))


def test_data_spec_seed_overrides_recipe_seed(tmp_path: Path) -> None:
    # Build with seed=11; resolve asking for seed=99 → not found.
    recipe_yaml, cache_root, _ = _build_fixture(tmp_path, seed=11)
    spec = DataSpec(recipe=recipe_yaml, seed=99)
    with pytest.raises(DataBindingError, match="with seed=99"):
        resolve_data_instance(spec, _config(cache_root))


def test_data_spec_cache_root_overrides_runtime(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _build_fixture(tmp_path)
    other = tmp_path / "other_cache"
    other.mkdir()
    spec = DataSpec(recipe=recipe_yaml, cache_root=cache_root)
    # runtime_config points at empty other_cache, but data_spec.cache_root wins.
    inst = resolve_data_instance(spec, _config(other))
    assert inst.path.is_relative_to(cache_root)
