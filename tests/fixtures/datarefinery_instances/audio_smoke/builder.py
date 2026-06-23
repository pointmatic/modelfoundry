# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Synthesized DataRefinery *audio* feature-array instance builder (Story I.l).

`build_dr_audio_instance(root, ...)` materializes a DataRefinery-shaped audio
classification instance on disk that matches the **pinned vendor contract** for
the forward-declared `npy_per_record` feature-array seam (vendor-dependency-spec
§ "Audio feature-array persistence", pinned answers Q1-Q6), then returns the
ModelFoundry-side `DataRefineryInstance` view. The substrate every following
Subphase I-1 story (I.m-I.r) tests against — DataRefinery has not yet shipped the
`npy_per_record` sink, so MF builds its consumer half against this synthesized
fixture rather than a real `dr.materialize`.

Layout produced (mirrors `datarefinery_instances/builder.py`, widened to audio):

    <inst>/recipe.json
    <inst>/manifest.json                 # record_counts post-windowing; sink format npy_per_record
    <inst>/dataset/<split>.jsonl         # one line per *window* record
    <inst>/features/<split>/<rid>.npy    # (n_mels, n_frames) float32; rid may nest (Q5)
    <inst>/fitted_statistics/<op>/{mean,std}.parquet   # per-mel-bin, n_mels rows, axis-0

Contract points realized here:

- **Q1** `feature_path` is **instance-root-relative** (`<instance>/features/...`, a
  sibling of `dataset/`), NOT `dataset/`-relative.
- **Q3** the `.npy` array is `float32`; the `audio_normalize` `mean`/`std` parquet
  is `float64` (same promotion as image `normalize` stats).
- **Q4** the array is always rank-2 `(n_mels, n_frames)` (mono); the consumer owns
  the channel-dim unsqueeze.
- **Q5** window `record_id = <clip_id>__w{window_index:04d}` and `clip_id` carries a
  class subdir, so `feature_path` nests below `features/<split>/`.
- **Q6** an optional stray source `path` may ride a record; `feature_path` is the
  authoritative feature surface.

`datarefinery` / `numpy` / `pyarrow` are imported lazily so importing this module
is cheap and does not require the optional stacks until a build is requested.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 3 classes, 2 splits; clips-per-split (not record counts — records are windows).
DEFAULT_CLASSES: tuple[str, ...] = ("c0", "c1", "c2")
DEFAULT_SPLIT_CLIP_COUNTS: dict[str, int] = {"train": 4, "val": 2}
# The `audio_normalize` featurization step name == the fitted-statistics op id on disk.
AUDIO_NORM_OP_ID: str = "audio_norm"


def build_dr_audio_instance(
    root: str | Path,
    *,
    classes: tuple[str, ...] = DEFAULT_CLASSES,
    split_clip_counts: dict[str, int] | None = None,
    windows_per_clip: int = 2,
    n_mels: int = 64,
    n_frames: int = 100,
    zero_variance_bin: int = 3,
    stray_path_on_first: bool = False,
    dangling_source_record_id: bool = False,
    seed: int = 7,
) -> Any:
    """Synthesize an audio feature-array DataRefinery instance under `root`; return its view."""
    import json
    import textwrap
    from datetime import UTC, datetime

    import datarefinery as dr
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    from datarefinery.pipeline.manifest import Manifest as DRManifest
    from datarefinery.pipeline.manifest import SinkManifestEntry
    from datarefinery.recipe.loader import load as dr_load_recipe
    from datarefinery.recipe.segments import recipe_identity_hash

    from modelfoundry.pipeline.data_binding import DataRefineryInstance

    split_clip_counts = split_clip_counts or dict(DEFAULT_SPLIT_CLIP_COUNTS)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    dr_yaml = textwrap.dedent(
        f"""
        schema_version: 3
        plugin: audio_classification
        seed: {seed}
        Input: {{sources: [{{name: t, type: audio_folder, path: /x}}]}}
        Output:
          record_schema: {{mel: {{dtype: float32, shape: [{n_mels}, {n_frames}]}},
                          label: {{dtype: str}}, feature_path: {{dtype: str}}}}
        Labels: {{field: label, source: {{kind: derived, derivation: parent_directory_name}}}}
        Featurizations:
          - {{name: mel, op: log_mel_spectrogram, inputs: [sample], output_field: mel}}
          - {{name: {AUDIO_NORM_OP_ID}, op: audio_normalize, inputs: [mel], output_field: feature}}
        Splits: {{ratios: {{train: 0.7, val: 0.3}}, seed: {seed}, stratify_by: label}}
        """
    ).strip()
    recipe_path = root / "dr_recipe.yml"
    recipe_path.write_text(dr_yaml, encoding="utf-8")
    dr_recipe = dr_load_recipe(recipe_path)
    recipe_hash = recipe_identity_hash(dr_recipe)

    inst = root / "inst"
    inst.mkdir(exist_ok=True)
    (inst / "recipe.json").write_text(dr_recipe.model_dump_json(), encoding="utf-8")

    # Per-mel-bin audio_normalize stats: n_mels rows, axis-0 (mel bins), single
    # `value` column — parity with image `normalize`. float64 (Q3). One zero-variance
    # bin exercises the consumer's std==0 → 1.0 guard.
    stats_dir = inst / "fitted_statistics" / AUDIO_NORM_OP_ID
    stats_dir.mkdir(parents=True, exist_ok=True)
    mean_vals = [float(i) for i in range(n_mels)]
    std_vals = [1.0] * n_mels
    if 0 <= zero_variance_bin < n_mels:
        std_vals[zero_variance_bin] = 0.0
    pq.write_table(pa.table({"value": mean_vals}), stats_dir / "mean.parquet")  # type: ignore[no-untyped-call]
    pq.write_table(pa.table({"value": std_vals}), stats_dir / "std.parquet")  # type: ignore[no-untyped-call]

    dataset_dir = inst / "dataset"
    dataset_dir.mkdir(exist_ok=True)
    features_dir = inst / "features"
    features_dir.mkdir(exist_ok=True)

    counts: dict[str, int] = {}
    files_written = 0
    bytes_total = 0
    first_record_emitted = False
    for split, clip_count in split_clip_counts.items():
        records: list[dict[str, Any]] = []
        for c in range(clip_count):
            cls = classes[c % len(classes)]  # round-robin → balanced classes
            clip_id = f"{cls}/clip_{c}"  # class subdir → nested feature_path (Q5)
            for w in range(windows_per_clip):
                record_id = f"{clip_id}__w{w:04d}"
                feature_path = (Path("features") / split / f"{record_id}.npy").as_posix()
                npy_file = inst / feature_path
                npy_file.parent.mkdir(parents=True, exist_ok=True)
                arr = rng.random((n_mels, n_frames), dtype=np.float64).astype(np.float32)
                np.save(npy_file, arr)  # Q3 float32 / Q4 rank-2 (n_mels, n_frames)
                files_written += 1
                bytes_total += npy_file.stat().st_size
                record: dict[str, Any] = {
                    "record_id": record_id,
                    "label": cls,
                    "feature_path": feature_path,  # Q1 instance-root-relative
                    "source_record_id": clip_id,
                    "window_index": w,
                }
                # Q6: one record also carries a source `path`; feature_path stays authoritative.
                if stray_path_on_first and not first_record_emitted:
                    record["path"] = f"audio/{clip_id}.ogg"
                first_record_emitted = True
                records.append(record)

        # I.o failure-mode substrate: one window whose source clip is not represented
        # by any record_id (a dangling parent reference). Train split only, deterministic.
        if dangling_source_record_id and split == "train":
            record_id = "__orphan__/clip_x__w0000"
            feature_path = (Path("features") / split / f"{record_id}.npy").as_posix()
            npy_file = inst / feature_path
            npy_file.parent.mkdir(parents=True, exist_ok=True)
            arr = rng.random((n_mels, n_frames), dtype=np.float64).astype(np.float32)
            np.save(npy_file, arr)
            files_written += 1
            bytes_total += npy_file.stat().st_size
            records.append(
                {
                    "record_id": record_id,
                    "label": classes[0],
                    "feature_path": feature_path,
                    "source_record_id": "__ghost_clip__",  # matches no record_id prefix
                    "window_index": 0,
                }
            )

        (dataset_dir / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
        counts[split] = len(records)  # post-windowing record count

    manifest = DRManifest(
        datarefinery_version="0.23.0",
        plugin="audio_classification",
        plugin_version="1",
        recipe_hash=recipe_hash,
        input_hash="0" * 64,
        seed=seed,
        created_at=datetime.now(UTC),
        elapsed_seconds=0.1,
        record_counts=counts,
        warnings=[],
        sinks={
            "features": SinkManifestEntry(
                stage="featurize",
                format="npy_per_record",
                files_written=files_written,
                bytes_total=bytes_total,
                path_template_resolved_root="features",
            )
        },
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
