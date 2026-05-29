# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Story A.c integration spike — DataRefinery instance binding (THROWAWAY).

Validates the most uncertain integration boundary before production modules
land: can ModelFoundry read a *real* materialized DataRefinery instance's
manifest + JSONL records + sidecar PNGs per the vendor-dependency-spec, decode
an image record into a numpy array, and produce DataLoader-ready samples?

Run:  pyve run python scripts/spike_datarefinery_binding.py

This is a spike: it writes only to a self-cleaning temp dir, prints a findings
summary, and exits 0 on success. The deliverable is docs/spikes/
A.c-datarefinery-binding.md, not this script.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import datarefinery as dr
import numpy as np
from datarefinery.core.config import RuntimeConfig
from datarefinery.recipe.loader import SUPPORTED_SCHEMA_VERSIONS as DR_SCHEMA_VERSIONS
from datarefinery.scaffolder.init import scaffold_image_classification
from PIL import Image

SEED = 1234
N_CLASSES = 2
N_PER_CLASS = 8
IMG_HW = 8


def make_synthetic_imagefolder(root: Path) -> None:
    """Emit an ImageFolder tree (<root>/<class>/<file>.png) of tiny RGB PNGs."""
    rng = np.random.default_rng(SEED)
    for c in range(N_CLASSES):
        cls_dir = root / f"class_{c}"
        cls_dir.mkdir(parents=True, exist_ok=True)
        for i in range(N_PER_CLASS):
            arr = rng.integers(0, 256, size=(IMG_HW, IMG_HW, 3), dtype=np.uint8)
            Image.fromarray(arr, mode="RGB").save(cls_dir / f"img_{c}_{i:02d}.png")


def decode_record_to_chw(
    record: dict[str, Any], instance_dir: Path
) -> tuple[np.ndarray, str]:
    """Resolve a JSONL record's pixels per the vendor-dep-spec and return CHW float32.

    image_path (aggressive variant sidecar, relative to dataset/) wins over the
    source `path` field when both are present.
    """
    if "image_path" in record:
        img_file = instance_dir / "dataset" / record["image_path"]
        source = f"image_path={record['image_path']!r} (sidecar)"
    else:
        img_file = Path(record["path"])
        source = f"path={record['path']!r} (source filesystem)"
    arr = np.asarray(Image.open(img_file).convert("RGB"), dtype=np.float32) / 255.0
    chw = np.transpose(arr, (2, 0, 1))  # HWC -> CHW, the torch convention
    return chw, source


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="mf_spike_acdr_"))
    findings: list[str] = []
    try:
        # 1. Synthetic ImageFolder + scaffolded recipe -> real materialize.
        input_dir = work / "images"
        recipe_path = work / "recipe.yml"
        cache_root = work / "dr_cache"
        make_synthetic_imagefolder(input_dir)
        scaffold_image_classification(input_dir, recipe_path)
        findings.append(f"scaffolded recipe at {recipe_path.name} from {N_CLASSES}-class folder")

        config = RuntimeConfig(cache_root=cache_root)
        instance = dr.materialize(recipe_path, config=config, seed=SEED)
        instance_dir = Path(instance.path)
        findings.append(f"materialized real DataRefinery instance at {instance_dir}")
        findings.append(f"instance.is_partial = {instance.is_partial}")

        # 2. Bind via the library API (the Story B.i intended path).
        reloaded = dr.Instance.load(instance_dir)
        findings.append(
            f"Instance.load round-trip OK; manifest.recipe_hash="
            f"{reloaded.manifest.recipe_hash[:16]}..."
        )

        # 3. Read the raw manifest.json per the vendor-dep-spec file contract.
        manifest = json.loads((instance_dir / "manifest.json").read_text())
        for required in ("plugin", "plugin_version", "recipe_hash", "record_counts", "seed"):
            assert required in manifest, f"manifest missing required field {required!r}"
        findings.append(
            f"manifest plugin={manifest['plugin']!r} v={manifest['plugin_version']!r} "
            f"seed={manifest['seed']} record_counts={manifest['record_counts']}"
        )

        # 4. Schema-version coordination check (vendor-dep-spec § coordination policy).
        recipe_schema_version = reloaded.recipe.schema_version
        mf_known_max = max(DR_SCHEMA_VERSIONS)
        assert recipe_schema_version <= mf_known_max, (
            f"recipe schema_version {recipe_schema_version} exceeds known max {mf_known_max}"
        )
        findings.append(
            f"schema coordination OK: recipe sv={recipe_schema_version}, "
            f"DR SUPPORTED={sorted(DR_SCHEMA_VERSIONS)}"
        )

        # 5. Iterate train.jsonl, inspect record schema, decode one image.
        train_jsonl = instance_dir / "dataset" / "train.jsonl"
        records = [json.loads(line) for line in train_jsonl.read_text().splitlines() if line]
        assert records, "no train records"
        sample_keys = sorted(records[0].keys())
        findings.append(f"train.jsonl has {len(records)} records; record keys={sample_keys}")

        has_image_path = any("image_path" in r for r in records)
        seed_stamp_keys = sorted(
            {k for r in records for k in r if k.endswith("_seed")}
        )
        findings.append(
            f"aggressive sidecars present={has_image_path}; "
            f"per-record-seed stamps={seed_stamp_keys or 'none'}"
        )

        chw, decode_source = decode_record_to_chw(records[0], instance_dir)
        findings.append(f"decoded record 0 via {decode_source} -> CHW float32 {chw.shape}")
        assert chw.dtype == np.float32 and chw.ndim == 3

        # 6. Produce DataLoader-ready samples (Dataset.__getitem__ shape).
        #    torch is the [pytorch] extra (not installed in the base venv); the
        #    literal torch.utils.data.DataLoader wiring + determinism is C.a/C.f.
        def getitem(idx: int) -> tuple[np.ndarray, Any]:
            rec = records[idx]
            img, _ = decode_record_to_chw(rec, instance_dir)
            return img, rec.get("label")

        batch = [getitem(i) for i in range(min(4, len(records)))]
        stacked = np.stack([img for img, _ in batch])  # default-collate analogue
        labels = [lbl for _, lbl in batch]
        findings.append(
            f"DataLoader-ready batch: images {stacked.shape} float32, labels={labels}"
        )

        # 7. Aggressive-variant consumer resolution against a hand-rolled,
        #    spec-conformant fixture. Real DataRefinery v0.17.0 cannot
        #    materialize an aggressive instance from a scaffolded recipe
        #    (sidecar write fails on path-like record_ids — see outcome doc),
        #    so the consumer-side image_path branch is validated here against
        #    a fixture matching the vendor-dep-spec § Aggressive-mode variants.
        agg_dir = work / "agg_instance"
        sidecar = agg_dir / "dataset" / "train" / "images" / "img_001__v000.png"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(SEED)
        Image.fromarray(
            rng.integers(0, 256, (IMG_HW, IMG_HW, 3), dtype=np.uint8), "RGB"
        ).save(sidecar)
        agg_record = {
            "record_id": "img_001__v000",
            "label": "class_0",
            "source_record_id": "img_001",
            "variant_index": 0,
            "image_path": "train/images/img_001__v000.png",
            "flip_seed": 7700112233,
        }
        agg_chw, agg_source = decode_record_to_chw(agg_record, agg_dir)
        assert agg_chw.shape == (3, IMG_HW, IMG_HW)
        findings.append(f"aggressive consumer resolution OK: decoded via {agg_source}")
        # Missing-sidecar refusal (vendor-dep-spec § Failure modes).
        try:
            decode_record_to_chw(
                {**agg_record, "image_path": "train/images/does_not_exist.png"}, agg_dir
            )
            raise AssertionError("expected missing-sidecar decode to fail")
        except FileNotFoundError:
            findings.append("missing-sidecar refusal OK (FileNotFoundError as expected)")

        print("=== A.c DataRefinery binding spike — FINDINGS ===")
        for f in findings:
            print(f"  - {f}")
        print("=== spike OK ===")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
