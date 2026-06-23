# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `pipeline.data_binding.resolve_data_instance`.

Since the binding bugfix, resolution delegates to DataRefinery's blessed
`resolve_instance` (vendor-dep-spec § "Resolving a materialized instance"), which
hashes the recipe's declared inputs — so a hand-built instance at a faked
`input_hash` can no longer be resolved. These tests therefore **materialize tiny
real instances** via `datarefinery.materialize` (a few 8x8 PNGs per class) so the
recipe + input hashes match what the resolver recomputes.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import datarefinery as dr
import pytest
from datarefinery.core.config import RuntimeConfig as DRRuntimeConfig
from PIL import Image

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import DataBindingError
from modelfoundry.pipeline import data_binding
from modelfoundry.pipeline.data_binding import (
    DataRefineryInstance,
    resolve_data_instance,
)
from modelfoundry.recipe.models import DataSpec

_CLASSES = ("c0", "c1", "c2")
_PER_CLASS = 5  # 5/class x 3 classes = 15 records -> stratified 0.6/0.2/0.2 fills every split


def _recipe_yaml(src: Path, labels_csv: Path, *, with_variants: bool) -> str:
    # Mirror the CIFAR recipe's working label path: image_flat + a label_from CSV
    # with kind: direct, which stamps `label` into each JSONL record (the derived
    # parent_directory_name mode does not stamp it, so instance_num_classes can't
    # read it).
    base = textwrap.dedent(
        f"""
        schema_version: 1
        plugin: image_classification
        seed: 11
        Input:
          sources:
            - name: imgs
              type: image_flat
              path: {src}
              label_from:
                path: {labels_csv}
                join: by_id
                id_field: id
                label_field: label
        Output:
          record_schema:
            image: {{dtype: uint8, shape: [8, 8, 3]}}
            label: {{dtype: str}}
            path:  {{dtype: str}}
        Labels:
          field: label
          source:
            kind: direct
        Splits:
          ratios: {{train: 0.6, val: 0.2, test: 0.2}}
          seed: 11
          stratify_by: label
        """
    ).strip()
    if with_variants:
        # A `variants:` block is exactly what regressed resolution: DataRefinery
        # clears variants for the default instance hash, so a consumer that hashed
        # the recipe *with* variants computed the wrong key. resolve_instance gets
        # this right — this fixture is the regression guard.
        base += textwrap.dedent(
            """

            variants:
              no_augment:
                Augmentations: []
              alt:
                Splits:
                  ratios: {train: 0.8, val: 0.1, test: 0.1}
                  seed: 11
                  stratify_by: label
            """
        )
    return base + "\n"


def _write_source(tmp_path: Path) -> tuple[Path, Path]:
    """Write a flat ImageFolder (`<n>.png`) + an id→label CSV; return (src, labels_csv)."""
    src = tmp_path / "src"
    src.mkdir()
    rows = ["id,label"]
    n = 0
    for c, cls in enumerate(_CLASSES):
        for i in range(_PER_CLASS):
            n += 1
            Image.new("RGB", (8, 8), (40 * c, 30 * i, 60)).save(src / f"{n}.png")
            rows.append(f"{n},{cls}")
    labels_csv = tmp_path / "labels.csv"
    labels_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return src, labels_csv


def _materialize(
    tmp_path: Path, *, with_variants: bool = False, seed: int = 11
) -> tuple[Path, Path, Path]:
    """Materialize a tiny real DR instance; return (recipe_yaml, cache_root, instance_dir)."""
    src, labels_csv = _write_source(tmp_path)
    recipe_yaml = tmp_path / "dr_recipe.yml"
    recipe_yaml.write_text(
        _recipe_yaml(src, labels_csv, with_variants=with_variants), encoding="utf-8"
    )
    cache_root = tmp_path / "dr_cache"
    instance = dr.materialize(recipe_yaml, config=DRRuntimeConfig(cache_root=cache_root), seed=seed)
    return recipe_yaml, cache_root, Path(instance.path).resolve()


def _config(cache_root: Path) -> RuntimeConfig:
    return RuntimeConfig(data_cache_root=cache_root)


# --- happy path ---


def test_resolution_returns_wrapper(tmp_path: Path) -> None:
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path)
    inst = resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))
    assert isinstance(inst, DataRefineryInstance)
    assert inst.path == instance_dir
    assert set(inst.splits) == {"train", "val", "test"}
    assert inst.label_schema["field"] == "label"
    assert "label" in inst.record_schema and "image" in inst.record_schema


def test_cross_validation_helpers(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _materialize(tmp_path)
    inst = resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))
    assert inst.instance_provides_splits(["train", "val"]) is True
    assert inst.instance_provides_splits(["train", "missing"]) is False
    assert inst.instance_schema_version() == 3  # v1 source migrates to v3 on load (DR v0.23)
    assert inst.instance_num_classes() == len(_CLASSES)


def test_variants_recipe_binds(tmp_path: Path) -> None:
    """Regression: a recipe with a `variants:` block must resolve (the original bug).

    DataRefinery clears variants for the default instance's cache key; the old
    hand-rolled hash kept them, so the bucket scan missed. resolve_instance gets it
    right.
    """
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path, with_variants=True)
    inst = resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))
    assert inst.path == instance_dir
    assert set(inst.splits) == {"train", "val", "test"}


# --- failure modes (vendor-dep-spec § Failure modes) ---


def test_missing_recipe_yaml_raises(tmp_path: Path) -> None:
    data_spec = DataSpec(recipe=tmp_path / "nope.yml")
    with pytest.raises(DataBindingError, match="recipe not found"):
        resolve_data_instance(data_spec, _config(tmp_path / "cache"))


def test_no_materialized_instance_raises(tmp_path: Path) -> None:
    # Real source present, but the recipe was never materialized → resolver miss.
    src, labels_csv = _write_source(tmp_path)
    recipe_yaml = tmp_path / "dr_recipe.yml"
    recipe_yaml.write_text(_recipe_yaml(src, labels_csv, with_variants=False), encoding="utf-8")
    with pytest.raises(DataBindingError, match="no materialized DataRefinery instance"):
        resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(tmp_path / "empty_cache"))


def test_failed_marker_refused(tmp_path: Path) -> None:
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path)
    (instance_dir / "FAILED").write_text("{}", encoding="utf-8")
    with pytest.raises(DataBindingError, match="FAILED marker"):
        resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))


def test_manifest_is_partial_refused(tmp_path: Path) -> None:
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path)
    manifest_path = instance_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["is_partial"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(DataBindingError, match="partial"):
        resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))


def test_missing_aggressive_sidecar_refused(tmp_path: Path) -> None:
    # Hand-append an aggressive variant referencing a sidecar that doesn't exist.
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path)
    train_jsonl = instance_dir / "dataset" / "train.jsonl"
    variant = {
        "record_id": "imgs/c0/img_0__v000",
        "source_record_id": "imgs/c0/img_0",
        "variant_index": 0,
        "label": "c0",
        "image_path": "train/images/img_0__v000.png",  # sidecar intentionally absent
    }
    train_jsonl.write_text(train_jsonl.read_text() + "\n" + json.dumps(variant), encoding="utf-8")
    with pytest.raises(DataBindingError, match="sidecar missing"):
        resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))


def test_aggressive_variant_with_sidecar_succeeds(tmp_path: Path) -> None:
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path)
    train_jsonl = instance_dir / "dataset" / "train.jsonl"
    rel = "train/images/img_0__v000.png"
    variant = {
        "record_id": "imgs/c0/img_0__v000",
        "source_record_id": "imgs/c0/img_0",
        "variant_index": 0,
        "label": "c0",
        "image_path": rel,
    }
    train_jsonl.write_text(train_jsonl.read_text() + "\n" + json.dumps(variant), encoding="utf-8")
    sidecar = instance_dir / "dataset" / rel
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_bytes(b"\x89PNG\r\n\x1a\n")  # sentinel; existence is all that's checked
    inst = resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))
    assert inst.splits


def test_instance_relative_path_missing_refused(tmp_path: Path) -> None:
    # Gap 1 gate: a bare, INSTANCE-relative `path` (as DR's png_per_record sink writes)
    # whose file is absent must be refused at bind time — not silently pass `validate`
    # and die mid-training. Absolute source paths are unaffected (loader uses them as-is).
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path)
    train_jsonl = instance_dir / "dataset" / "train.jsonl"
    record = {"record_id": "imgs/c0/sink_0", "label": "c0", "path": "images/c0/sink_0.png"}
    train_jsonl.write_text(train_jsonl.read_text() + "\n" + json.dumps(record), encoding="utf-8")
    with pytest.raises(DataBindingError, match="not resolvable from instance"):
        resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))


def test_instance_relative_path_present_binds(tmp_path: Path) -> None:
    # The same instance-relative `path`, with the file present under the instance root,
    # binds cleanly — confirming the gate anchors to the instance, not the CWD.
    recipe_yaml, cache_root, instance_dir = _materialize(tmp_path)
    train_jsonl = instance_dir / "dataset" / "train.jsonl"
    rel = "images/c0/sink_0.png"
    record = {"record_id": "imgs/c0/sink_0", "label": "c0", "path": rel}
    train_jsonl.write_text(train_jsonl.read_text() + "\n" + json.dumps(record), encoding="utf-8")
    target = instance_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x89PNG\r\n\x1a\n")  # sentinel; the gate only checks existence
    inst = resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))
    assert inst.splits


def test_schema_version_too_high_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Materialize normally (instance recipe is v2), then shrink ModelFoundry's
    # tracked DR support set so the v2 instance reads as "too high".
    recipe_yaml, cache_root, _ = _materialize(tmp_path)
    monkeypatch.setattr(data_binding, "DR_SUPPORTED_SCHEMA_VERSIONS", frozenset({1}))
    with pytest.raises(DataBindingError, match="higher than ModelFoundry's known max"):
        resolve_data_instance(DataSpec(recipe=recipe_yaml), _config(cache_root))


def test_data_spec_seed_overrides_recipe_seed(tmp_path: Path) -> None:
    # Materialized at seed=11; resolving with seed=99 lands on a different (absent) key.
    recipe_yaml, cache_root, _ = _materialize(tmp_path, seed=11)
    spec = DataSpec(recipe=recipe_yaml, seed=99)
    with pytest.raises(DataBindingError, match="no materialized DataRefinery instance"):
        resolve_data_instance(spec, _config(cache_root))


def test_data_spec_cache_root_overrides_runtime(tmp_path: Path) -> None:
    recipe_yaml, cache_root, _ = _materialize(tmp_path)
    other = tmp_path / "other_cache"
    other.mkdir()
    # runtime_config points at the empty other_cache, but data_spec.cache_root wins.
    spec = DataSpec(recipe=recipe_yaml, cache_root=cache_root)
    inst = resolve_data_instance(spec, _config(other))
    assert inst.path.is_relative_to(cache_root)
