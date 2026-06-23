# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the audio feature-array load branch in `plugins.pytorch.data` (Story I.m).

Exercises the additive feature-array path against the synthesized audio fixture
(Story I.l): per-record branch selection (`feature_path` ⇒ feature branch,
authoritative over a stray `path`), instance-root-relative resolution (Q1) from a
foreign CWD, the rank-2 assertion (Q4) and channel-dim unsqueeze, and the
bind-time resolvability gate extended to `feature_path`. The image path is
unchanged — its coverage stays in `test_pytorch_data_adapter.py`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("datarefinery")

from datarefinery_instances.audio_smoke.builder import (  # type: ignore[import-not-found]  # noqa: E402
    build_dr_audio_instance,
)

from modelfoundry.core.errors import DataBindingError  # noqa: E402
from modelfoundry.pipeline.data_binding import _verify_record_images_resolvable  # noqa: E402
from modelfoundry.plugins.pytorch.data import DataRefineryDataset  # noqa: E402

# --- load + shape (Q3/Q4) ---


def test_feature_branch_decodes_to_channel_first_2d(tmp_path: Path) -> None:
    instance = build_dr_audio_instance(tmp_path / "a", n_mels=64, n_frames=100)
    ds = DataRefineryDataset(instance, "train")
    tensor, label = ds[0]
    assert tensor.dtype == torch.float32
    assert tuple(tensor.shape) == (1, 64, 100)  # Q4 unsqueeze: (1, n_mels, n_frames)
    assert label >= 0  # class label resolved


def test_decode_features_preserves_raw_mel_before_normalization(tmp_path: Path) -> None:
    # `_decode_features` is the raw load layer — no /255, no normalize (audio_normalize
    # is applied later in `__getitem__`, Story I.n). It must return the .npy verbatim.
    instance = build_dr_audio_instance(tmp_path / "a", n_mels=64, n_frames=100)
    ds = DataRefineryDataset(instance, "train")
    decoded = ds._decode_features(ds._records[0])
    raw = np.load(instance.path / str(ds._records[0]["feature_path"]))
    assert torch.equal(decoded, torch.from_numpy(raw).unsqueeze(0))


# --- audio_normalize fit-on-train application (Story I.n) ---


def test_audio_normalize_applied_per_mel_bin(tmp_path: Path) -> None:
    # __getitem__ standardizes each mel bin with the train-fitted stats on axis 1 of
    # (1, n_mels, n_frames) — NOT the image CHW reshape. Byte-match a torch reference
    # computed with the same float64 promotion, per-mel-bin reshape, and zero-variance
    # guard (the fixture plants std == 0 at bin 3).
    instance = build_dr_audio_instance(tmp_path / "a", n_mels=64, n_frames=100, zero_variance_bin=3)
    ds = DataRefineryDataset(instance, "train")
    rec = ds._records[0]
    raw = np.load(instance.path / str(rec["feature_path"]))  # (64, 100) float32
    fs = instance.fitted_statistics
    mean = torch.tensor(
        fs.get_vector("audio_norm", "mean").column("value").to_pylist(), dtype=torch.float64
    ).view(1, -1, 1)
    std = torch.tensor(
        fs.get_vector("audio_norm", "std").column("value").to_pylist(), dtype=torch.float64
    )
    std_guarded = torch.where(std == 0.0, torch.ones_like(std), std).view(1, -1, 1)
    raw_t = torch.from_numpy(raw).unsqueeze(0)  # (1, 64, 100) float32
    expected = ((raw_t - mean) / std_guarded).to(torch.float32)
    out, _ = ds[0]
    assert out.dtype == torch.float32
    assert torch.equal(out, expected)
    # Zero-variance bin 3: std guarded to 1.0 -> finite, equals (raw - mean) on that bin.
    assert torch.isfinite(out).all()
    bin3 = (torch.from_numpy(raw[3]).double() - mean[0, 3, 0]).to(torch.float32)
    assert torch.equal(out[0, 3], bin3)


def test_audio_normalize_registered_fit_on_train() -> None:
    # The geometry guard must treat audio_normalize as non-baked (fit-on-train).
    from modelfoundry.plugins.pytorch.data import _FIT_ON_TRAIN_OPS

    assert "audio_normalize" in _FIT_ON_TRAIN_OPS


def test_audio_instance_binds_without_geometry_guard(tmp_path: Path) -> None:
    # The geometry guard keys off image `Transformations`; the audio recipe has none,
    # so binding must not false-trip on the feature path.
    instance = build_dr_audio_instance(tmp_path / "a")
    ds = DataRefineryDataset(instance, "train")  # constructs without raising
    assert len(ds) == 8


# --- resolution anchor (Q1) + foreign CWD parity with I.k ---


def test_feature_path_resolves_instance_relative_from_other_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = build_dr_audio_instance(tmp_path / "a")
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    monkeypatch.chdir(workdir)  # a CWD-relative resolve would FileNotFoundError
    ds = DataRefineryDataset(instance, "train")
    tensor, _ = ds[0]
    assert tensor.shape[0] == 1


# --- branch precedence (Q6) ---


def test_feature_path_authoritative_over_stray_path(tmp_path: Path) -> None:
    # The first record also carries a source `path` (a nonexistent .ogg). The feature
    # branch must win: an image decode of that `path` would raise instead.
    instance = build_dr_audio_instance(tmp_path / "a", stray_path_on_first=True)
    ds = DataRefineryDataset(instance, "train")
    assert "path" in ds._records[0]
    tensor, _ = ds[0]
    assert tuple(tensor.shape) == (1, 64, 100)


# --- rank guard (Q4) ---


def test_non_2d_feature_array_refused(tmp_path: Path) -> None:
    instance = build_dr_audio_instance(tmp_path / "a")
    ds = DataRefineryDataset(instance, "train")
    bad = instance.path / str(ds._records[0]["feature_path"])
    np.save(bad, np.zeros((1, 64, 100), dtype=np.float32))  # rank-3 — must be refused
    with pytest.raises(DataBindingError, match="ndim"):
        _ = ds[0]


# --- bind-time resolvability gate extended to feature_path ---


def test_bind_gate_passes_for_present_feature_arrays(tmp_path: Path) -> None:
    instance = build_dr_audio_instance(tmp_path / "a")
    _verify_record_images_resolvable(instance.path)  # all .npy present → no raise


def test_bind_gate_refuses_missing_feature_array(tmp_path: Path) -> None:
    instance = build_dr_audio_instance(tmp_path / "a")
    # Delete one referenced feature file; the gate must surface it before training.
    train_jsonl = instance.path / "dataset" / "train.jsonl"
    import json

    first = json.loads(train_jsonl.read_text(encoding="utf-8").splitlines()[0])
    (instance.path / str(first["feature_path"])).unlink()
    with pytest.raises(DataBindingError, match="feature array not resolvable"):
        _verify_record_images_resolvable(instance.path)
