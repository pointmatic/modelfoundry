# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Synthesized DataRefinery instance builder for the test suite (Story E.a).

`build_dr_instance(root, ...)` materializes a minimal DataRefinery instance on
disk — mimicking the vendor-dependency-spec's layout (`manifest.json`,
`recipe.json`, `dataset/<split>.jsonl`, sidecar PNGs, `fitted_statistics/`) — and
returns the ModelFoundry-side `DataRefineryInstance` view. The default is a
100-record, 3-class, 2-split (train/val) image-classification instance with
deterministic byte-shape; splits, classes, record count, and image size are all
overridable. It serves both object-binding callers (pass the returned instance
to `ModelFoundry.from_recipe(data=...)`) and path-resolution callers (the
on-disk layout under `root` is complete).

`datarefinery` / `PIL` / `pyarrow` are imported lazily so importing this module
is cheap and does not require the optional stacks until a build is requested.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 3 classes, 2 splits, 100 records (70 train / 30 val), round-robin class assignment.
DEFAULT_CLASSES: tuple[str, ...] = ("c0", "c1", "c2")
DEFAULT_SPLIT_COUNTS: dict[str, int] = {"train": 70, "val": 30}
_COLORS = [(200, 100, 50), (10, 150, 250), (60, 60, 60), (240, 220, 40), (120, 30, 200)]


def build_dr_instance(
    root: str | Path,
    *,
    classes: tuple[str, ...] = DEFAULT_CLASSES,
    split_counts: dict[str, int] | None = None,
    image_size: int = 8,
    seed: int = 1,
) -> Any:
    """Synthesize a DataRefinery instance under `root`; return its `DataRefineryInstance` view."""
    import hashlib
    import json
    import textwrap
    from datetime import UTC, datetime

    import datarefinery as dr
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datarefinery.pipeline.manifest import Manifest as DRManifest
    from datarefinery.recipe.canonical import to_canonical_bytes
    from datarefinery.recipe.loader import load as dr_load_recipe
    from PIL import Image

    from modelfoundry.pipeline.data_binding import DataRefineryInstance

    split_counts = split_counts or dict(DEFAULT_SPLIT_COUNTS)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)

    dr_yaml = textwrap.dedent(
        f"""
        schema_version: 2
        plugin: image_classification
        seed: {seed}
        Input: {{sources: [{{name: t, type: image_folder, path: /x}}]}}
        Output:
          record_schema: {{image: {{dtype: uint8, shape: [{image_size}, {image_size}, 3]}},
                          label: {{dtype: str}}, path: {{dtype: str}}}}
        Labels: {{field: label, source: {{kind: derived, derivation: parent_directory_name}}}}
        Transformations:
          - {{name: norm, op: normalize}}
        Splits: {{ratios: {{train: 0.7, val: 0.3}}, seed: {seed}, stratify_by: label}}
        """
    ).strip()
    recipe_path = root / "dr_recipe.yml"
    recipe_path.write_text(dr_yaml, encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_path)
    recipe_hash = hashlib.sha256(to_canonical_bytes(dr_recipe)).hexdigest()

    inst = root / "inst"
    inst.mkdir(exist_ok=True)
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")

    # Per-channel normalize stats (length == channel count) so the C.f adapter binds.
    stats_dir = inst / "fitted_statistics" / "norm"
    stats_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"value": [0.5, 0.45, 0.4]}), stats_dir / "mean.parquet")  # type: ignore[no-untyped-call]
    pq.write_table(pa.table({"value": [0.25, 0.25, 0.25]}), stats_dir / "std.parquet")  # type: ignore[no-untyped-call]

    dataset_dir = inst / "dataset"
    dataset_dir.mkdir(exist_ok=True)
    images_dir = inst / "images"
    images_dir.mkdir(exist_ok=True)

    counts: dict[str, int] = {}
    for split, count in split_counts.items():
        records = []
        for i in range(count):
            cls = classes[i % len(classes)]  # round-robin → balanced classes
            color = _COLORS[classes.index(cls) % len(_COLORS)]
            png = images_dir / f"{split}_{i}.png"
            Image.new("RGB", (image_size, image_size), color).save(png)
            records.append({"record_id": f"{split}/{cls}/img_{i}", "label": cls, "path": str(png)})
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
