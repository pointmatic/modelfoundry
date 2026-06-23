# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Verification of the Subphase I-1 synthesized audio feature-array fixture (Story I.l).

Confirms the `audio_smoke` builder emits a DataRefinery-shaped *audio* instance
matching the pinned vendor contract (Q1-Q6): `features/<split>/<record_id>.npy`
feature arrays, window-record JSONL carrying `feature_path` / `source_record_id` /
`window_index`, per-mel-bin `audio_normalize` fitted statistics, and a manifest
whose sink format is `npy_per_record`. This is the test substrate every following
story (I.m-I.r) exercises; it has no `src/` counterpart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _build(tmp_path: Path, **kwargs: object) -> object:
    pytest.importorskip("datarefinery")
    pytest.importorskip("numpy")
    pytest.importorskip("pyarrow")
    from datarefinery_instances.audio_smoke.builder import (  # type: ignore[import-not-found]
        build_dr_audio_instance,
    )

    return build_dr_audio_instance(tmp_path / "dr_audio", **kwargs)


# --- conftest fixture wiring ---


def test_dr_audio_instance_fixture_shape(dr_audio_instance: object) -> None:
    pytest.importorskip("datarefinery")
    assert set(dr_audio_instance.splits) == {"train", "val"}  # type: ignore[attr-defined]
    assert dr_audio_instance.instance_num_classes() == 3  # type: ignore[attr-defined]


# --- instance loads + view shape ---


def test_audio_instance_loads_and_exposes_splits(tmp_path: Path) -> None:
    instance = _build(tmp_path)
    assert set(instance.splits) == {"train", "val"}  # type: ignore[attr-defined]
    # Labels are derived from clip class dirs, so the class count is enumerable.
    assert instance.instance_num_classes() == 3  # type: ignore[attr-defined]


def test_record_counts_are_post_windowing(tmp_path: Path) -> None:
    # 4 train clips + 2 val clips, 2 windows each → 8 train / 4 val window records.
    instance = _build(tmp_path)
    counts = instance.manifest.record_counts  # type: ignore[attr-defined]
    assert counts == {"train": 8, "val": 4}


# --- feature arrays on disk (Q3/Q4/Q5) ---


def test_feature_paths_resolve_instance_root_relative(tmp_path: Path) -> None:
    import numpy as np

    instance = _build(tmp_path, n_mels=64, n_frames=100)
    inst_root = Path(instance.path)  # type: ignore[attr-defined]
    for split in instance.splits:  # type: ignore[attr-defined]
        for record in _read_jsonl(inst_root / "dataset" / f"{split}.jsonl"):
            # Q1: feature_path is instance-root-relative (sibling of dataset/), not dataset/-rel.
            feat_file = inst_root / record["feature_path"]
            assert feat_file.is_file(), feat_file
            assert record["feature_path"].startswith("features/")
            arr = np.load(feat_file)
            assert arr.dtype == np.float32  # Q3
            assert arr.ndim == 2 and arr.shape == (64, 100)  # Q4


def test_window_record_ids_are_nested_and_well_formed(tmp_path: Path) -> None:
    # Q5: clip ids carry a class subdir, so feature_path nests below features/<split>/.
    instance = _build(tmp_path)
    inst_root = Path(instance.path)  # type: ignore[attr-defined]
    saw_nested = False
    for record in _read_jsonl(inst_root / "dataset" / "train.jsonl"):
        wi = record["window_index"]
        clip = record["source_record_id"]
        assert record["record_id"] == f"{clip}__w{wi:04d}"
        if "/" in record["feature_path"].removeprefix("features/train/"):
            saw_nested = True
    assert saw_nested  # at least one feature_path nests beyond features/<split>/


def test_stray_source_path_does_not_displace_feature_path(tmp_path: Path) -> None:
    # Q6: a record may also carry a source `path`; `feature_path` stays authoritative.
    instance = _build(tmp_path, stray_path_on_first=True)
    inst_root = Path(instance.path)  # type: ignore[attr-defined]
    records = _read_jsonl(inst_root / "dataset" / "train.jsonl")
    stray = [r for r in records if "path" in r]
    assert len(stray) == 1
    assert "feature_path" in stray[0] and stray[0]["feature_path"] != stray[0]["path"]


# --- audio_normalize fitted statistics (per-mel-bin, axis-0) ---


def test_audio_normalize_stats_are_per_mel_bin(tmp_path: Path) -> None:
    from datarefinery_instances.audio_smoke.builder import AUDIO_NORM_OP_ID

    instance = _build(tmp_path, n_mels=64)
    fs = instance.fitted_statistics  # type: ignore[attr-defined]
    mean = fs.get_vector(AUDIO_NORM_OP_ID, "mean")
    std = fs.get_vector(AUDIO_NORM_OP_ID, "std")
    assert mean.num_rows == 64 and std.num_rows == 64  # n_mels rows, axis-0
    # A zero-variance mel bin is present to exercise the consumer's std==0 → 1.0 guard.
    assert 0.0 in std.column("value").to_pylist()


# --- manifest + recipe ---


def test_manifest_reports_npy_per_record_sink(tmp_path: Path) -> None:
    instance = _build(tmp_path)
    sinks = instance.manifest.sinks  # type: ignore[attr-defined]
    assert any(entry.format == "npy_per_record" for entry in sinks.values())


def test_recipe_exposes_audio_normalize_featurization(tmp_path: Path) -> None:
    instance = _build(tmp_path)
    ops = [step.op for step in instance.recipe.Featurizations]  # type: ignore[attr-defined]
    assert "audio_normalize" in ops


# --- dangling source_record_id variant (substrate for the I.o failure-mode test) ---


def test_dangling_source_record_id_variant_emits_orphan_window(tmp_path: Path) -> None:
    instance = _build(tmp_path, dangling_source_record_id=True)
    inst_root = Path(instance.path)  # type: ignore[attr-defined]
    records = _read_jsonl(inst_root / "dataset" / "train.jsonl")
    # The orphan window names a source clip that no record_id is derived from.
    clip_prefixes = {r["record_id"].rsplit("__w", 1)[0] for r in records}
    orphans = [r for r in records if r["source_record_id"] not in clip_prefixes]
    assert len(orphans) == 1


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
