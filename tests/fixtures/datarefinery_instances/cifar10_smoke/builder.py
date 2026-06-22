# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Downsized CIFAR-10 smoke instance builder (Story E.l, TR-12 / AC-2).

Produces a CIFAR-10-*shaped* DataRefinery instance on disk — 10 classes, 32x32
RGB, ~500/100/100 train/val/test — in the vendor-dependency-spec layout
(`manifest.json`, `recipe.json`, `dataset/<split>.jsonl`, sidecar PNGs,
`fitted_statistics/`), returning the ModelFoundry-side `DataRefineryInstance`.

**Why synthetic, hand-built (the A.c fallback pattern), not a real
`dr.materialize`.** Two reasons: (1) the smoke must run offline on a free-tier CI
runner (PE-3), so it cannot download the real CIFAR-10 source; (2) a fresh
`dr.materialize` of a tiny instance stores labels via `record_id` / parent-dir
rather than a `label` column, so ModelFoundry's `instance_num_classes()` reads 0
— the hand-built layout writes explicit labels and binds cleanly. The real-DR
resolution path stays covered by `tests/integration/test_cifar10_resnet20.py`
(against the DR-1 instance, skip-if-absent). Mirrors
`datarefinery_instances/builder.py`, widened to CIFAR shape with a 10-colour
palette so each class is trivially separable and `simple_cnn` genuinely learns
(a meaningful `macro_f1` floor, not a degenerate fit).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 10 maximally-distinct RGB colours — one per CIFAR-10 class, so a tiny CNN learns
# the colour→class map in a few epochs (the smoke needs a real, non-degenerate fit).
_PALETTE: tuple[tuple[int, int, int], ...] = (
    (220, 20, 60),  # crimson
    (60, 180, 75),  # green
    (0, 130, 200),  # blue
    (245, 130, 48),  # orange
    (145, 30, 180),  # purple
    (70, 240, 240),  # cyan
    (240, 50, 230),  # magenta
    (170, 110, 40),  # brown
    (128, 128, 128),  # grey
    (0, 0, 0),  # black
)
CLASSES: tuple[str, ...] = tuple(f"c{i}" for i in range(10))
DEFAULT_SPLIT_COUNTS: dict[str, int] = {"train": 500, "val": 100, "test": 100}
_IMAGE_SIZE = 32


def build_cifar10_smoke_instance(
    root: str | Path,
    *,
    split_counts: dict[str, int] | None = None,
    seed: int = 20260613,
) -> Any:
    """Synthesize a downsized CIFAR-10-shaped instance under `root`; return its view."""
    import json
    import textwrap
    from datetime import UTC, datetime

    import datarefinery as dr
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datarefinery.pipeline.manifest import Manifest as DRManifest
    from datarefinery.recipe.loader import load as dr_load_recipe
    from datarefinery.recipe.segments import recipe_identity_hash
    from PIL import Image

    from modelfoundry.pipeline.data_binding import DataRefineryInstance

    split_counts = split_counts or dict(DEFAULT_SPLIT_COUNTS)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    dr_yaml = textwrap.dedent(
        f"""
        schema_version: 3
        plugin: image_classification
        seed: {seed}
        Input: {{sources: [{{name: t, type: image_folder, path: /x}}]}}
        Output:
          record_schema: {{image: {{dtype: uint8, shape: [{_IMAGE_SIZE}, {_IMAGE_SIZE}, 3]}},
                          label: {{dtype: str}}, path: {{dtype: str}}}}
        Labels: {{field: label, source: {{kind: derived, derivation: parent_directory_name}}}}
        Transformations:
          - {{name: norm, op: normalize}}
        Splits: {{ratios: {{train: 0.72, val: 0.14, test: 0.14}}, seed: {seed}, stratify_by: label}}
        """
    ).strip()
    recipe_path = root / "dr_recipe.yml"
    recipe_path.write_text(dr_yaml, encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_path)
    recipe_hash = recipe_identity_hash(dr_recipe)

    inst = root / "inst"
    inst.mkdir(exist_ok=True)
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")

    # Realistic 0-255-scale normalize stats (DataRefinery fits on raw pixels; the
    # PyTorch adapter applies them in 0-255 units, Story H.a). [0,1]-scale stats
    # would trip the validator's input-contract check (FR-2 check 21).
    stats_dir = inst / "fitted_statistics" / "norm"
    stats_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"value": [128.0, 128.0, 128.0]}), stats_dir / "mean.parquet")  # type: ignore[no-untyped-call]
    pq.write_table(pa.table({"value": [64.0, 64.0, 64.0]}), stats_dir / "std.parquet")  # type: ignore[no-untyped-call]

    dataset_dir = inst / "dataset"
    dataset_dir.mkdir(exist_ok=True)
    images_dir = inst / "images"
    images_dir.mkdir(exist_ok=True)

    counts: dict[str, int] = {}
    for split, count in split_counts.items():
        records = []
        for i in range(count):
            cls_idx = i % len(CLASSES)  # round-robin → balanced classes
            cls = CLASSES[cls_idx]
            png = images_dir / f"{split}_{i}.png"
            Image.new("RGB", (_IMAGE_SIZE, _IMAGE_SIZE), _PALETTE[cls_idx]).save(png)
            records.append({"record_id": f"{split}/{cls}/img_{i}", "label": cls, "path": str(png)})
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
        seed=seed,
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
