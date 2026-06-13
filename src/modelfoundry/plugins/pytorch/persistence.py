# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch persistence + from-disk round-trip (FR-23, Story C.l).

`save_model` / `load_model` make a trained model reconstructible **from disk
alone** — no external config object. `save_model` writes `model/weights/state_dict.pt`,
the canonical `model/architecture.json` (the recipe `Architecture:` block the
model was built from), and `model/checkpoints/checkpoint-best.pt`; `load_model`
reads `architecture.json`, rebuilds the `nn.Module` via the C.c builder, and
loads the weights. See `project-essentials.md` § Cache identity for the
architecture-json round-trip discipline.

`predict` / `predict_proba` accept a `pandas.DataFrame` (record-schema with a
`path`/`image` column), a `list[Path]` of image paths, or a 4-D
`numpy.ndarray` of shape `(N, H, W, C)`.

This module imports `torch` at the top — it is loaded at materialize / inference
time, not during plugin discovery; the plugin delegates here lazily.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from torch import nn

from modelfoundry.core.errors import InstanceError, PluginError
from modelfoundry.pipeline.checkpoint import Checkpoint
from modelfoundry.plugins.pytorch.architecture import build_model

_STATE_DICT = "weights/state_dict.pt"
_ARCHITECTURE = "architecture.json"
_BEST_CHECKPOINT = "checkpoints/checkpoint-best.pt"


def save_model(model: nn.Module, model_dir: str | Path) -> None:
    """Persist `model` under `model_dir` for a from-disk round-trip.

    Writes `weights/state_dict.pt`, the canonical `architecture.json` (from the
    spec `build_model` attached to the module), and `checkpoints/checkpoint-best.pt`.
    """
    model_dir = Path(model_dir)
    architecture = getattr(model, "architecture_spec", None)
    if not isinstance(architecture, dict):
        raise PluginError(
            "cannot persist a model that was not built by `architecture.build_model` "
            "(no `architecture_spec`); architecture.json would be unrecoverable",
            stage="save_model",
        )

    (model_dir / "weights").mkdir(parents=True, exist_ok=True)
    (model_dir / "checkpoints").mkdir(parents=True, exist_ok=True)

    torch.save(model.state_dict(), model_dir / _STATE_DICT)
    (model_dir / _ARCHITECTURE).write_text(_canonical_json(architecture), encoding="utf-8")
    Checkpoint(
        epoch=-1,  # provenance: a re-persist outside the training loop has no epoch
        weights=model.state_dict(),
        metric_value=float("nan"),
        recipe_hash16="",
    ).save(model_dir / _BEST_CHECKPOINT)


def load_model(model_dir: str | Path) -> nn.Module:
    """Rebuild a model from `model_dir` alone — architecture.json + state_dict.pt."""
    model_dir = Path(model_dir)
    architecture_path = model_dir / _ARCHITECTURE
    weights_path = model_dir / _STATE_DICT
    if not architecture_path.is_file():
        raise InstanceError(
            f"missing {architecture_path}; cannot reconstruct the model architecture",
            detail={"path": str(architecture_path)},
        )
    if not weights_path.is_file():
        raise InstanceError(
            f"missing {weights_path}; no weights to load", detail={"path": str(weights_path)}
        )

    architecture = json.loads(architecture_path.read_text(encoding="utf-8"))
    model: nn.Module = build_model(architecture)
    state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def predict(model: nn.Module, X: Any) -> np.ndarray | Any:
    """Predicted class indices for `X` (a `pd.Series` when `X` is a DataFrame)."""
    proba = _forward_proba(model, X)
    indices = proba.argmax(axis=1)
    if _is_dataframe(X):
        import pandas as pd  # type: ignore[import-untyped]

        return pd.Series(indices, index=X.index, name="prediction")
    return indices


def predict_proba(model: nn.Module, X: Any) -> np.ndarray | Any:
    """Per-class probabilities for `X` (a `pd.DataFrame` when `X` is a DataFrame)."""
    proba = _forward_proba(model, X)
    if _is_dataframe(X):
        import pandas as pd

        columns = [f"proba_{c}" for c in range(proba.shape[1])]
        return pd.DataFrame(proba, index=X.index, columns=columns)
    return proba


# --- helpers ---


def _forward_proba(model: nn.Module, X: Any) -> np.ndarray:
    device = next(model.parameters()).device
    batch = _to_batch(X).to(device)
    model.eval()
    with torch.no_grad():
        logits = model(batch)
        proba = torch.softmax(logits, dim=1)
    return proba.cpu().numpy()


def _to_batch(X: Any) -> torch.Tensor:
    """Coerce supported inputs to a `(N, C, H, W)` float32 tensor."""
    if _is_dataframe(X):
        return _to_batch(_dataframe_to_arrays(X))
    if isinstance(X, np.ndarray):
        return _ndarray_to_batch(X)
    if isinstance(X, torch.Tensor):
        return _ndarray_to_batch(X.detach().cpu().numpy())
    if isinstance(X, Sequence) and not isinstance(X, str | bytes):
        return _paths_to_batch(list(X))
    raise PluginError(
        f"unsupported predict input of type {type(X).__name__}; expected a DataFrame, "
        f"a list of image paths, or a 4-D (N, H, W, C) ndarray",
        stage="predict",
    )


def _ndarray_to_batch(array: np.ndarray) -> torch.Tensor:
    if array.ndim != 4:
        raise PluginError(
            f"ndarray input must be 4-D (N, H, W, C); got shape {array.shape}", stage="predict"
        )
    floats = array.astype(np.float32)
    if np.issubdtype(array.dtype, np.integer):
        floats = floats / 255.0  # match the data adapter's uint8 -> [0, 1] decode
    tensor = torch.from_numpy(floats).permute(0, 3, 1, 2).contiguous()  # NHWC -> NCHW
    return tensor


def _paths_to_batch(paths: list[Any]) -> torch.Tensor:
    if not paths:
        raise PluginError("empty image-path list for predict", stage="predict")
    arrays = []
    for item in paths:
        with Image.open(Path(item)) as handle:
            arrays.append(np.asarray(handle.convert("RGB"), dtype=np.float32) / 255.0)
    return _ndarray_to_batch(np.stack(arrays))


def _dataframe_to_arrays(frame: Any) -> Any:
    if "path" in frame.columns:
        return list(frame["path"])
    if "image" in frame.columns:
        return np.stack([np.asarray(img, dtype=np.float32) for img in frame["image"]])
    raise PluginError(
        "DataFrame predict input needs a 'path' or 'image' column", stage="predict"
    )


def _is_dataframe(X: Any) -> bool:
    return type(X).__name__ == "DataFrame" and hasattr(X, "columns")


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
