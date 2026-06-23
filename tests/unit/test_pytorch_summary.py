# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `plugins.pytorch.summary` (FR-27, Story C.q)."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("torch")
pytest.importorskip("torchinfo")

from modelfoundry.core.instance import ModelInstance
from modelfoundry.core.manifest import Manifest
from modelfoundry.plugins.pytorch.architecture import build_model
from modelfoundry.plugins.pytorch.summary import (
    ModelSummary,
    derive_input_size,
    summarize,
    write_summary,
)

_RESNET20_PARAMS = 272_474
_INPUT = (1, 3, 32, 32)


def _resnet20() -> Any:
    return build_model({"type": "resnet20", "num_classes": 10})


def _leaf_inventory(summary: ModelSummary) -> dict[str, int]:
    return dict(Counter(layer.type for layer in summary.layers if layer.leaf))


def _minimal_manifest() -> Manifest:
    return Manifest(
        plugin="pytorch",
        plugin_version="0.0.0",
        recipe_hash="0" * 64,
        data_instance_hash="0" * 16,
        bound_data_instance=Path("/tmp/dr"),
        seed=0,
        overlays=[],
        created_at=datetime.now(UTC),
        elapsed_seconds=0.0,
        epoch_history=0,
        evaluation={},
        output_expectations=[],
    )


class _SchemaStub:
    """Minimal stand-in exposing only what `derive_input_size`'s schema path reads."""

    def __init__(self, record_schema: dict[str, object]) -> None:
        self.record_schema = record_schema


# --- structured summary ---


def test_resnet20_summary_pins_total_and_inventory() -> None:
    summary, _ = summarize(_resnet20(), _INPUT)

    assert summary.total_params == _RESNET20_PARAMS
    assert summary.trainable_params == _RESNET20_PARAMS
    assert summary.non_trainable_params == 0
    assert summary.total_mult_adds > 0
    assert summary.input_size == list(_INPUT)

    inventory = _leaf_inventory(summary)
    assert inventory["Conv2d"] == 21
    assert inventory["BatchNorm2d"] == 21
    assert inventory["Linear"] == 1
    assert inventory["AdaptiveAvgPool2d"] == 1
    assert inventory["Flatten"] == 1


def test_summary_text_reports_totals() -> None:
    _, text = summarize(_resnet20(), _INPUT)
    assert "Total params: 272,474" in text
    assert "Trainable params" in text


def test_layer_rows_carry_shape_and_counts() -> None:
    summary, _ = summarize(_resnet20(), _INPUT)
    # The root module's output is the 10-class logit vector for a batch of 1.
    assert summary.layers[0].output_shape == [1, 10]
    # Every leaf Linear/Conv has a positive parameter count and output shape.
    convs = [layer for layer in summary.layers if layer.type == "Conv2d"]
    assert convs and all(c.param_count > 0 and c.output_shape for c in convs)


# --- determinism ---


def test_summary_render_is_byte_deterministic(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    write_summary(_resnet20(), _INPUT, dir_a)
    write_summary(_resnet20(), _INPUT, dir_b)

    assert (dir_a / "summary.txt").read_bytes() == (dir_b / "summary.txt").read_bytes()
    assert (dir_a / "summary.json").read_bytes() == (dir_b / "summary.json").read_bytes()


# --- on-disk round-trip through the ModelInstance accessor ---


def test_summary_json_round_trips_through_accessor(tmp_path: Path) -> None:
    write_summary(_resnet20(), _INPUT, tmp_path / "model")

    instance = ModelInstance(path=tmp_path, manifest=_minimal_manifest(), plugin=None)  # type: ignore[arg-type]
    assert instance.summary is not None
    assert instance.summary["total_params"] == _RESNET20_PARAMS
    # The accessor payload reconstructs the structured model losslessly.
    assert ModelSummary(**instance.summary).total_params == _RESNET20_PARAMS

    assert instance.summary_text is not None
    assert "Total params: 272,474" in instance.summary_text


def test_summary_accessors_are_none_when_absent(tmp_path: Path) -> None:
    instance = ModelInstance(path=tmp_path, manifest=_minimal_manifest(), plugin=None)  # type: ignore[arg-type]
    assert instance.summary is None
    assert instance.summary_text is None


# --- input-size derivation ---


def test_derive_input_size_from_record_schema() -> None:
    stub = _SchemaStub(
        {"image": {"dtype": "uint8", "shape": [32, 32, 3]}, "label": {"dtype": "str"}}
    )
    assert derive_input_size(stub) == (1, 3, 32, 32)


def test_derive_input_size_prefers_image_field() -> None:
    # A non-image 3-element shape must not win over the image entry.
    stub = _SchemaStub({"bbox": {"shape": [4, 4, 4]}, "image": {"shape": [8, 16, 3]}})
    assert derive_input_size(stub) == (1, 3, 8, 16)


# --- in-memory plugin summary (H.a.2: ModelFoundry.summary() support) ---


def test_plugin_summarize_model_returns_dict_with_totals_and_output_shape() -> None:
    from modelfoundry.plugins.pytorch.plugin import PyTorchPlugin

    data = _SchemaStub({"image": {"dtype": "uint8", "shape": [32, 32, 3]}})
    result = PyTorchPlugin().summarize_model(_resnet20(), data)

    assert result["total_params"] == _RESNET20_PARAMS
    assert result["trainable_params"] == _RESNET20_PARAMS
    assert result["output_shape"][-1] == 10  # 10-way classification head
    assert isinstance(result["layers"], list) and result["layers"]
