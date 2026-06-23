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
    # Raw mel values preserved verbatim — no /255, no premature normalize (I.n's job).
    raw = np.load(instance.path / str(ds._records[0]["feature_path"]))
    assert torch.equal(tensor, torch.from_numpy(raw).unsqueeze(0))


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
