# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Real-DR audio feature-array end-to-end smoke (Story I.m.1, Subphase I-1).

Materializes an **actual** DataRefinery v0.24.0 audio instance — synthesized
sine-tone `.wav` clips → `audio_flat` decode → `window` generation →
`log_mel_spectrogram` + fit-on-train `audio_normalize` → an `npy_per_record` sink
that persists the raw `mel` and rewrites a per-record `feature_path` — then binds
it through ModelFoundry's loader and asserts the feature branch (Story I.m)
consumes DR's true output bytes. This is the cross-repo seam verified against the
real producer, not the synthesized I.l mimic.

**Skips cleanly** wherever `torch` / `datarefinery` / `librosa` / `soundfile` are
absent (DR's `audio_flat` source decodes via `librosa.load`), so the light env
and audio-less CI stay green; it runs in the smoke-pytorch env.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("datarefinery")
pytest.importorskip("librosa")
soundfile = pytest.importorskip("soundfile")

import datarefinery as dr  # noqa: E402
from datarefinery.core.config import RuntimeConfig as DRRuntimeConfig  # noqa: E402

from modelfoundry.core.config import RuntimeConfig  # noqa: E402
from modelfoundry.pipeline.data_binding import resolve_data_instance  # noqa: E402
from modelfoundry.plugins.pytorch.data import DataRefineryDataset  # noqa: E402
from modelfoundry.recipe.models import DataSpec  # noqa: E402

_CLASSES = ("c0", "c1", "c2")
_CLIPS_PER_CLASS = 4
_SR = 16_000
_N_MELS = 16
_FREQS = {"c0": 220.0, "c1": 440.0, "c2": 880.0}
_SEED = 11


def _write_audio_source(root: Path) -> tuple[Path, Path]:
    """Synthesize a flat dir of per-class sine-tone WAVs + an id→label CSV."""
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    rows = ["id,label"]
    n = 0
    t = np.linspace(0, 1.0, _SR, endpoint=False)
    for cls in _CLASSES:
        for _ in range(_CLIPS_PER_CLASS):
            n += 1
            wave = (0.5 * np.sin(2 * np.pi * _FREQS[cls] * t)).astype(np.float32)
            soundfile.write(src / f"{n}.wav", wave, _SR)
            rows.append(f"{n},{cls}")
    labels_csv = root / "labels.csv"
    labels_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return src, labels_csv


def _recipe_yaml(src: Path, labels_csv: Path) -> str:
    # Mirrors the pinned audio feature-array contract: audio_flat + by_id labels,
    # window generation on every split, log-mel + fit-on-train audio_normalize, and
    # an npy_per_record sink on the raw `mel` (pre-normalize, Q2) rewriting feature_path.
    return textwrap.dedent(
        f"""
        schema_version: 3
        plugin: audio_classification
        seed: {_SEED}
        Input:
          sources:
            - name: clips
              type: audio_flat
              path: {src}
              target_sample_rate: {_SR}
              label_from:
                path: {labels_csv}
                join: by_id
                id_field: id
                label_field: label
        Output:
          record_schema:
            label: {{dtype: str}}
        Labels:
          field: label
          source: {{kind: direct}}
        Generation:
          - name: win
            op: window
            seed: {_SEED}
            splits: [train, val, test]
            inputs: [sample_array]
            output_schema: {{sample_array: {{dtype: float32, shape: [4000]}}}}
            params: {{window_length_samples: 4000, hop_samples: 2000, remainder: drop}}
            replace_input_records: true
        Featurizations:
          - name: mel
            op: log_mel_spectrogram
            inputs: [sample_array]
            output_field: mel
            splits: [train, val, test]
            params: {{n_fft: 256, hop_length: 128, n_mels: {_N_MELS}, f_min: 0.0, power: 2.0}}
          - name: audio_norm
            op: audio_normalize
            inputs: [mel]
            output_field: feature
            fit_source: train
            splits: [train, val, test]
            params: {{}}
        Sinks:
          - name: features
            stage: post_Featurizations
            field: mel
            format: npy_per_record
            path_template: "features/{{split}}/{{record_id}}.npy"
        Splits: {{ratios: {{train: 0.5, val: 0.25, test: 0.25}}, seed: {_SEED}, stratify_by: label}}
        """
    ).strip()


@pytest.fixture(scope="module")
def real_audio_binding(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Materialize a real DR audio instance once; bind it through MF. Module-scoped."""
    root = tmp_path_factory.mktemp("audio_real_dr")
    src, labels_csv = _write_audio_source(root)
    recipe_yaml = root / "audio_recipe.yml"
    recipe_yaml.write_text(_recipe_yaml(src, labels_csv), encoding="utf-8")
    cache_root = root / "dr_cache"
    dr.materialize(recipe_yaml, config=DRRuntimeConfig(cache_root=cache_root), seed=_SEED)
    # Bind through MF's real consumer path (resolve + schema gate + bind-time
    # feature_path resolvability gate), not a hand-rolled wrap.
    instance = resolve_data_instance(
        DataSpec(recipe=recipe_yaml), RuntimeConfig(data_cache_root=cache_root)
    )
    return {"instance": instance, "recipe_yaml": recipe_yaml, "cache_root": cache_root}


def test_real_instance_binds_and_reports_npy_sink(real_audio_binding: dict[str, Any]) -> None:
    instance = real_audio_binding["instance"]
    assert instance.instance_num_classes() == 3
    assert set(instance.splits) == {"train", "val", "test"}
    assert any(e.format == "npy_per_record" for e in instance.manifest.sinks.values())


def test_real_feature_branch_decodes_channel_first(real_audio_binding: dict[str, Any]) -> None:
    inst = real_audio_binding["instance"]
    ds = DataRefineryDataset(inst, "train")
    tensor, label = ds[0]
    assert tensor.dtype == torch.float32
    assert tensor.ndim == 3 and tensor.shape[0] == 1  # (1, n_mels, n_frames)
    assert tensor.shape[1] == _N_MELS
    assert 0 <= label < 3
    # The raw load layer is verbatim against DR's .npy (no normalize at decode); the
    # per-mel-bin audio_normalize (I.n) is applied on top in __getitem__.
    raw = np.load(inst.path / str(ds._records[0]["feature_path"]))
    assert raw.ndim == 2
    decoded = ds._decode_features(ds._records[0])
    assert torch.equal(decoded, torch.from_numpy(np.ascontiguousarray(raw)).unsqueeze(0))


def test_real_audio_normalize_applied_at_getitem(real_audio_binding: dict[str, Any]) -> None:
    # End-to-end: ds[0] standardizes the real DR mel with the real fitted audio_normalize
    # stats (per-mel-bin). Output must be finite and differ from the raw decode.
    inst = real_audio_binding["instance"]
    ds = DataRefineryDataset(inst, "train")
    out, _ = ds[0]
    decoded = ds._decode_features(ds._records[0])
    assert torch.isfinite(out).all()
    assert not torch.equal(out, decoded)  # normalization changed the values


def test_real_feature_path_is_instance_relative_and_nested(
    real_audio_binding: dict[str, Any],
) -> None:
    inst = real_audio_binding["instance"]
    ds = DataRefineryDataset(inst, "train")
    rec = ds._records[0]
    fp = str(rec["feature_path"])
    # Q1: resolves under the instance root (a sibling of dataset/), not dataset/-relative.
    assert (inst.path / fp).is_file()
    assert fp.startswith("features/")
    assert not (inst.path / "dataset" / fp).is_file()
    # Q5: DR's record_id (and thus feature_path) nests below features/<split>/.
    assert "/" in fp.removeprefix("features/train/")


def test_real_feature_path_authoritative_over_source_path(
    real_audio_binding: dict[str, Any],
) -> None:
    # Q6: DR rides the decoded source `path` alongside `feature_path`; MF must consume
    # the feature, not attempt to decode the .wav as an image.
    ds = DataRefineryDataset(real_audio_binding["instance"], "train")
    rec = ds._records[0]
    assert "path" in rec and str(rec["path"]).endswith(".wav")
    tensor, _ = ds[0]
    assert tensor.shape[0] == 1  # feature branch won


def test_real_audio_normalize_stats_present(real_audio_binding: dict[str, Any]) -> None:
    fs = real_audio_binding["instance"].fitted_statistics
    mean = fs.get_vector("audio_norm", "mean")
    std = fs.get_vector("audio_norm", "std")
    assert mean.num_rows == _N_MELS and std.num_rows == _N_MELS  # per-mel-bin, axis-0


def test_real_record_counts_are_post_windowing(real_audio_binding: dict[str, Any]) -> None:
    # Each 1s clip fans into multiple windows; counts exceed the 12-clip source.
    counts = real_audio_binding["instance"].manifest.record_counts
    assert sum(counts.values()) > _CLIPS_PER_CLASS * len(_CLASSES)
