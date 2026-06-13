# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for PyTorch persistence + from-disk round-trip (FR-23, C.l).

`save_model` then `load_model` (architecture.json + state_dict.pt only) must
rebuild a model that predicts identically — no external config object.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from PIL import Image  # noqa: E402

from modelfoundry.core.errors import PluginError  # noqa: E402
from modelfoundry.plugins.pytorch.architecture import build_model  # noqa: E402
from modelfoundry.plugins.pytorch.determinism import (  # noqa: E402
    enable_deterministic_algorithms,
)
from modelfoundry.plugins.pytorch.persistence import (  # noqa: E402
    load_model,
    predict,
    predict_proba,
    save_model,
)

_ARCH = {"type": "simple_cnn", "num_classes": 10, "in_channels": 3}


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def _model() -> Any:
    enable_deterministic_algorithms(123)
    return build_model(_ARCH)


def _batch(n: int = 4) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.random((n, 32, 32, 3), dtype=np.float32)


# --- tests ---


def test_round_trip_predicts_identically(tmp_path: Path) -> None:
    model = _model()
    x = _batch()
    proba_before = predict_proba(model, x)
    preds_before = predict(model, x)

    save_model(model, tmp_path)
    assert (tmp_path / "weights" / "state_dict.pt").is_file()
    assert (tmp_path / "architecture.json").is_file()
    assert (tmp_path / "checkpoints" / "checkpoint-best.pt").is_file()

    loaded = load_model(tmp_path)
    proba_after = predict_proba(loaded, x)
    preds_after = predict(loaded, x)

    assert np.allclose(proba_before, proba_after, atol=1e-6)
    assert np.array_equal(preds_before, preds_after)


def test_architecture_json_is_self_describing(tmp_path: Path) -> None:
    import json

    save_model(_model(), tmp_path)
    architecture = json.loads((tmp_path / "architecture.json").read_text())
    assert architecture == _ARCH  # the exact block the model was built from


def test_predict_proba_shape_and_normalization(tmp_path: Path) -> None:
    proba = predict_proba(_model(), _batch(n=5))
    assert proba.shape == (5, 10)
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5)


def test_predict_accepts_image_paths(tmp_path: Path) -> None:
    paths = []
    for i in range(3):
        p = tmp_path / f"img_{i}.png"
        Image.new("RGB", (32, 32), (i * 40, 100, 200)).save(p)
        paths.append(p)
    preds = predict(_model(), paths)
    assert preds.shape == (3,)


def test_predict_accepts_dataframe_path_column(tmp_path: Path) -> None:
    import pandas as pd  # type: ignore[import-untyped]

    paths = []
    for i in range(2):
        p = tmp_path / f"img_{i}.png"
        Image.new("RGB", (32, 32), (10, i * 50, 30)).save(p)
        paths.append(str(p))
    frame = pd.DataFrame({"path": paths})

    preds = predict(_model(), frame)
    assert isinstance(preds, pd.Series)
    assert len(preds) == 2

    proba = predict_proba(_model(), frame)
    assert isinstance(proba, pd.DataFrame)
    assert list(proba.columns) == [f"proba_{c}" for c in range(10)]


def test_unsupported_input_raises(tmp_path: Path) -> None:
    with pytest.raises(PluginError, match="unsupported predict input"):
        predict(_model(), 42)


def test_3d_ndarray_rejected(tmp_path: Path) -> None:
    with pytest.raises(PluginError, match="must be 4-D"):
        predict(_model(), np.zeros((32, 32, 3), dtype=np.float32))


def test_save_rejects_unattributed_model(tmp_path: Path) -> None:
    # A raw module not built by build_model has no `architecture_spec`.
    raw = torch.nn.Linear(4, 2)
    with pytest.raises(PluginError, match="architecture_spec"):
        save_model(raw, tmp_path)
