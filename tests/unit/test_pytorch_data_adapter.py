# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `plugins.pytorch.data` (Story C.f).

Hand-builds a DataRefinery instance directory (recipe.json + fitted_statistics
parquet + dataset JSONL + source PNGs + manifest) and binds it via a real
`datarefinery.Instance.load`, so the adapter is exercised against the actual
vendor on-disk contract.
"""

from __future__ import annotations

import hashlib
import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

torch = pytest.importorskip("torch")

import datarefinery as dr  # noqa: E402
from datarefinery.pipeline.manifest import Manifest as DRManifest  # noqa: E402
from datarefinery.recipe.canonical import to_canonical_bytes  # noqa: E402
from datarefinery.recipe.loader import load as dr_load_recipe  # noqa: E402
from PIL import Image  # noqa: E402

from modelfoundry.core.errors import DataBindingError  # noqa: E402
from modelfoundry.pipeline.data_binding import DataRefineryInstance  # noqa: E402
from modelfoundry.plugins.pytorch.data import (  # noqa: E402
    DataRefineryDataset,
    build_dataloader,
)
from modelfoundry.recipe.models import TrainingSpec  # noqa: E402

_CLASSES = ("c0", "c1", "c2")
_COLORS = {"c0": (200, 100, 50), "c1": (10, 150, 250), "c2": (60, 60, 60)}


def _recipe_yaml(extra_transform: str = "") -> str:
    return textwrap.dedent(
        f"""
        schema_version: 2
        plugin: image_classification
        seed: 1
        Input: {{sources: [{{name: t, type: image_folder, path: /x}}]}}
        Output:
          record_schema: {{image: {{dtype: uint8, shape: [4, 4, 3]}}, label: {{dtype: str}},
                           path: {{dtype: str}}}}
        Labels: {{field: label, source: {{kind: derived, derivation: parent_directory_name}}}}
        Transformations:
          - {{name: norm, op: normalize}}{extra_transform}
        Splits: {{ratios: {{train: 0.6, val: 0.2, test: 0.2}}, seed: 1, stratify_by: label}}
        """
    ).strip()


def _build_instance(
    tmp_path: Path,
    *,
    mean: tuple[float, float, float] = (0.5, 0.3, 0.1),
    std: tuple[float, float, float] = (0.25, 0.5, 0.2),
    extra_transform: str = "",
) -> Path:
    recipe_path = tmp_path / "dr_recipe.yml"
    recipe_path.write_text(_recipe_yaml(extra_transform), encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_path)
    recipe_hash = hashlib.sha256(to_canonical_bytes(dr_recipe)).hexdigest()

    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")

    stats_dir = inst / "fitted_statistics" / "norm"
    stats_dir.mkdir(parents=True)
    pq.write_table(pa.table({"value": list(mean)}), stats_dir / "mean.parquet")  # type: ignore[no-untyped-call]
    pq.write_table(pa.table({"value": list(std)}), stats_dir / "std.parquet")  # type: ignore[no-untyped-call]

    dataset_dir = inst / "dataset"
    dataset_dir.mkdir()
    images_dir = inst / "images"
    images_dir.mkdir()
    counts: dict[str, int] = {}
    for split, per_class in (("train", 3), ("val", 1), ("test", 1)):
        records = []
        for cls in _CLASSES:
            for i in range(per_class):
                png = images_dir / f"{split}_{cls}_{i}.png"
                Image.new("RGB", (4, 4), _COLORS[cls]).save(png)
                records.append(
                    {"record_id": f"{split}/{cls}/img_{i}", "label": cls, "path": str(png)}
                )
        (dataset_dir / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
        counts[split] = len(records)

    manifest = DRManifest(
        datarefinery_version="0.19.0",
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
    return inst


def _wrap(inst_dir: Path) -> DataRefineryInstance:
    loaded = dr.Instance.load(inst_dir)
    return DataRefineryInstance(
        path=inst_dir,
        manifest=loaded.manifest,
        recipe=loaded.recipe,
        splits=tuple(loaded.manifest.record_counts.keys()),
        label_schema=loaded.recipe.Labels.model_dump(),
        record_schema={k: v.model_dump() for k, v in loaded.recipe.Output.record_schema.items()},
        fitted_statistics=loaded.fitted_statistics,
    )


# --- tests ---


def test_len_matches_manifest(tmp_path: Path) -> None:
    ds = DataRefineryDataset(_wrap(_build_instance(tmp_path)), "train")
    assert len(ds) == 9  # 3 classes x 3 per class


def test_decode_produces_normalized_rgb_float32(tmp_path: Path) -> None:
    mean = (0.5, 0.3, 0.1)
    std = (0.25, 0.5, 0.2)
    ds = DataRefineryDataset(_wrap(_build_instance(tmp_path, mean=mean, std=std)), "train")
    image, label = ds[0]  # first record = c0, colour (200, 100, 50)
    assert image.dtype == torch.float32
    assert tuple(image.shape) == (3, 4, 4)
    assert label == 0  # c0 -> index 0
    raw = np.array(_COLORS["c0"], dtype=np.float32) / 255.0
    expected = (raw - np.array(mean)) / np.array(std)
    # Solid colour -> every spatial position equals the per-channel value; RGB-ordered.
    assert image[:, 0, 0].tolist() == pytest.approx(expected.tolist(), abs=1e-5)


def test_zero_variance_guard_substitutes_one(tmp_path: Path) -> None:
    # Channel 1 (G) has std == 0 -> divisor guarded to 1.0; no inf/nan.
    mean = (0.5, 0.3, 0.1)
    std = (0.25, 0.0, 0.2)
    ds = DataRefineryDataset(_wrap(_build_instance(tmp_path, mean=mean, std=std)), "train")
    image, _ = ds[0]
    assert torch.isfinite(image).all()
    raw_g = _COLORS["c0"][1] / 255.0
    assert image[1, 0, 0].item() == pytest.approx(raw_g - mean[1], abs=1e-5)  # divided by 1.0


def test_label_index_scans_all_splits_sorted(tmp_path: Path) -> None:
    ds = DataRefineryDataset(_wrap(_build_instance(tmp_path)), "val")
    assert ds.label_to_index == {"c0": 0, "c1": 1, "c2": 2}


def test_geometry_transform_without_baking_is_refused(tmp_path: Path) -> None:
    inst = _build_instance(
        tmp_path,
        extra_transform="\n          - {name: rs, op: resize, params: {width: 8, height: 8}}",
    )
    with pytest.raises(DataBindingError, match="pixel-altering"):
        DataRefineryDataset(_wrap(inst), "train")


def test_iteration_is_invariant_to_num_workers(tmp_path: Path) -> None:
    wrapped = _wrap(_build_instance(tmp_path))

    def collect(num_workers: int) -> tuple[Any, list[int]]:
        ds = DataRefineryDataset(wrapped, "train")
        spec = TrainingSpec(max_epochs=1, batch_size=2, num_workers=num_workers)
        images: list[Any] = []
        labels: list[int] = []
        for batch_images, batch_labels in build_dataloader(ds, spec, master_seed=7):
            images.append(batch_images)
            labels.extend(int(x) for x in batch_labels)
        return torch.cat(images), labels

    images_1, labels_1 = collect(1)
    images_2, labels_2 = collect(2)
    assert labels_1 == labels_2
    assert torch.equal(images_1, images_2)
