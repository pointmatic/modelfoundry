# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""End-to-end audio MC-dropout acceptance gate (Story I.p, FR-AUDIO-1/2/3).

The subphase's acceptance test: a synthesized (Story I.l) audio feature-array
instance + a 1-channel spectrogram-CNN recipe declaring
`Inference: {mode: mc_dropout}` + `WindowAggregation: {policy: mean}` materializes
end-to-end, producing **clip-level** (regrouped by `source_record_id`, Story
I.o.2) predictions with per-clip `predictive_entropy` / `mc_variance` and `ece`
over the MC-aggregated means. It asserts the four determinism invariants hold on
the audio path exactly as the image path: the same `(recipe, data, seed)`
materializes **byte-identically**, and the instance **round-trips from disk**
(`ModelInstance.load(path).predict(...)` with no external config). A default
image MC-dropout materialize stays window-level (the additive guarantee).

Runs in the `smoke-pytorch` env: the synthesized `.npy` fixture needs no audio
decode stack (`librosa` / `soundfile`), only `torch` + `datarefinery`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

torch = pytest.importorskip("torch")
pytest.importorskip("datarefinery")

from datarefinery_instances.audio_smoke.builder import (  # type: ignore[import-not-found]  # noqa: E402
    build_dr_audio_instance,
)
from datarefinery_instances.builder import (  # type: ignore[import-not-found]  # noqa: E402
    build_dr_instance,
)

from modelfoundry.core.config import RuntimeConfig  # noqa: E402

_N_MELS = 16
_N_FRAMES = 32
_NUM_CLASSES = 3
_MC_SAMPLES = 8
_VAL_CLIPS = 2


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    # The PyTorch plugin flips on deterministic-algorithm mode during materialize;
    # restore the process default so other tests are unaffected.
    yield
    torch.use_deterministic_algorithms(False)


def _audio_recipe_dict(*, window_policy: str | None, mc_samples: int | None) -> dict[str, Any]:
    # A genuine 1-channel spectrogram CNN: Conv2d over the (1, n_mels, n_frames) mel
    # feature → global pool → Dropout (the MC-dropout variation source) → linear head.
    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "num_classes": _NUM_CLASSES,
            "layers": [
                {"op": "Conv2d", "in_channels": 1, "out_channels": 4, "padding": 1},
                {"op": "ReLU"},
                {"op": "AdaptiveAvgPool2d", "output_size": 1},
                {"op": "Flatten"},
                {"op": "Dropout", "p": 0.5},
                {"op": "Linear", "in_features": 4, "out_features": _NUM_CLASSES},
            ],
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {
            "max_epochs": 1,
            "batch_size": 4,
            "device": "cpu",
            "precision": "fp32",
            "checkpoint_cadence": 1,
        },
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1", "ece", "predictive_entropy"],
            "calibration_bins": 10,
        },
    }
    if mc_samples is not None:
        recipe["Inference"] = {"mode": "mc_dropout", "mc_samples": mc_samples}
    if window_policy is not None:
        recipe["WindowAggregation"] = {"policy": window_policy}
    return recipe


def _materialize(tmp_path: Path, data: Any, recipe: dict[str, Any], *, tag: str) -> Any:
    from modelfoundry import ModelFoundry

    recipe_path = tmp_path / f"recipe_{tag}.yml"
    recipe_path.write_text(yaml.safe_dump(recipe), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp_path / f"cache_{tag}")
    return ModelFoundry.from_recipe(recipe_path, data=data, config=config).materialize()


@pytest.fixture
def audio_data(tmp_path: Path) -> Any:
    return build_dr_audio_instance(tmp_path / "dr_audio", n_mels=_N_MELS, n_frames=_N_FRAMES)


def _instance_fingerprint(instance_dir: Path) -> dict[str, str]:
    """SHA-256 every file under the instance dir, modulo wall-clock metadata."""
    fp: dict[str, str] = {}
    for path in sorted(instance_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(instance_dir).as_posix()
        if rel.endswith("report.md"):
            continue
        data = path.read_bytes()
        if rel == "manifest.json":
            manifest = json.loads(data)
            for wallclock in ("created_at", "elapsed_seconds"):
                manifest.pop(wallclock, None)
            data = json.dumps(manifest, sort_keys=True).encode("utf-8")
        fp[rel] = hashlib.sha256(data).hexdigest()
    return fp


# --- End-to-end run (clip-level MC-dropout) ---


def test_audio_mc_dropout_materializes_clip_level(tmp_path: Path, audio_data: Any) -> None:
    mi = _materialize(
        tmp_path,
        audio_data,
        _audio_recipe_dict(window_policy="mean", mc_samples=_MC_SAMPLES),
        tag="a",
    )

    predictions = mi.predictions
    # Clip-level (R7): val has _VAL_CLIPS clips x 2 windows; predictions regroup to clips.
    assert len(predictions) == _VAL_CLIPS
    assert set(predictions["record_id"]) == {
        f"c{c % _NUM_CLASSES}/clip_{c}" for c in range(_VAL_CLIPS)
    }
    # Per-clip predictive uncertainty persisted over the MC-aggregated means (R2.3).
    for column in ("predictive_entropy", "mc_variance"):
        assert column in predictions.columns
        assert predictions[column].notna().all()
    # The MC passes genuinely vary (active dropout) — not a degenerate single-pass.
    assert (predictions["mc_variance"] > 0).any()
    # ece + mean predictive_entropy are reported per split.
    assert "ece" in mi.metrics["val"]
    assert "predictive_entropy" in mi.metrics["val"]


# --- Reproducibility parity (byte-determinism + disk round-trip) ---


def test_audio_materialize_is_byte_deterministic(tmp_path: Path, audio_data: Any) -> None:
    recipe = _audio_recipe_dict(window_policy="mean", mc_samples=_MC_SAMPLES)
    first = _instance_fingerprint(Path(_materialize(tmp_path, audio_data, recipe, tag="a").path))
    second = _instance_fingerprint(Path(_materialize(tmp_path, audio_data, recipe, tag="b").path))
    assert first == second


def test_audio_instance_round_trips_from_disk(tmp_path: Path, audio_data: Any) -> None:
    from modelfoundry import ModelInstance

    mi = _materialize(
        tmp_path,
        audio_data,
        _audio_recipe_dict(window_policy="mean", mc_samples=_MC_SAMPLES),
        tag="a",
    )
    # A (N, n_mels, n_frames, 1) NHWC batch coerces to the (N, 1, n_mels, n_frames)
    # audio input shape — predict from new inputs needs no external config object.
    rng = np.random.default_rng(0)
    x = rng.random((4, _N_MELS, _N_FRAMES, 1), dtype=np.float32)

    reloaded = ModelInstance.load(mi.path)
    assert np.allclose(mi.predict_proba(x), reloaded.predict_proba(x), atol=1e-6)
    assert np.array_equal(mi.predict(x), reloaded.predict(x))


# --- Image path unaffected (additive guarantee) ---


def test_image_mc_dropout_stays_window_level(tmp_path: Path) -> None:
    # The same MC-dropout recipe shape over an image instance, with NO WindowAggregation,
    # keeps the established per-record (window-level) predictions surface — the audio
    # aggregation is opt-in and does not perturb the image path.
    image_size = 4
    data = build_dr_instance(
        tmp_path / "dr_image", split_counts={"train": 16, "val": 8}, image_size=image_size
    )
    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "num_classes": _NUM_CLASSES,
            "layers": [
                {"op": "Flatten"},
                {"op": "Linear", "in_features": image_size * image_size * 3, "out_features": 16},
                {"op": "ReLU"},
                {"op": "Dropout", "p": 0.5},
                {"op": "Linear", "in_features": 16, "out_features": _NUM_CLASSES},
            ],
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {
            "max_epochs": 1,
            "batch_size": 4,
            "device": "cpu",
            "precision": "fp32",
            "checkpoint_cadence": 1,
        },
        "Inference": {"mode": "mc_dropout", "mc_samples": _MC_SAMPLES},
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1", "predictive_entropy"],
            "calibration_bins": 10,
        },
    }
    mi = _materialize(tmp_path, data, recipe, tag="img")
    # 8 val records, no clip regrouping → 8 per-record predictions.
    assert len(mi.predictions) == 8
    assert "predictive_entropy" in mi.predictions.columns
