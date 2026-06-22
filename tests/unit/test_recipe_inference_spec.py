# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the recipe-declared stochastic-inference block (Story H.m, R2.1).

Torch-free: exercises only the pydantic `InferenceSpec` / `ModelRecipe.Inference`
contract, so it runs in the default `testenv`. The MC-dropout mechanism itself
is covered (torch-gated) in `test_pytorch_stochastic.py`.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.models import InferenceSpec, ModelRecipe

_BASE = textwrap.dedent(
    """
    schema_version: 1
    plugin: pytorch
    seed: 7
    Data:
      recipe: ../data/recipe.yml
    Architecture:
      op: simple_cnn
      num_classes: 10
    Loss:
      op: cross_entropy
    Optimizer:
      op: adamw
      learning_rate: 0.001
    Training:
      max_epochs: 3
      batch_size: 32
      device: cpu
      precision: fp32
      checkpoint_cadence: 1
    Evaluation:
      splits: [val, test]
      primary_metric: macro_f1
      metrics: [macro_f1, accuracy]
      calibration_bins: 10
    """
).strip()


def _load(tmp_path: Path, text: str, name: str = "recipe.yml") -> ModelRecipe:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return load_recipe(p)


def test_inference_defaults_to_absent(tmp_path: Path) -> None:
    # A recipe that does not declare an inference block → single-pass point
    # estimates (criterion 5); the field is absent.
    recipe = _load(tmp_path, _BASE)
    assert recipe.Inference is None


def test_explicit_point_mode_has_no_mc_samples() -> None:
    # No-implicit-defaults (Story I.e.3): when the Inference block is present, `mode`
    # is author-required (block *absence* still means point — tested separately).
    spec = InferenceSpec(mode="point")
    assert spec.mode == "point"
    assert spec.mc_samples is None


def test_mc_dropout_requires_mc_samples() -> None:
    with pytest.raises(PydanticValidationError):
        InferenceSpec(mode="mc_dropout")


def test_point_mode_rejects_mc_samples() -> None:
    with pytest.raises(PydanticValidationError):
        InferenceSpec(mode="point", mc_samples=30)


def test_mc_samples_must_be_positive() -> None:
    with pytest.raises(PydanticValidationError):
        InferenceSpec(mode="mc_dropout", mc_samples=0)


def test_mc_dropout_block_round_trips(tmp_path: Path) -> None:
    text = _BASE + textwrap.dedent(
        """
        Inference:
          mode: mc_dropout
          mc_samples: 30
        """
    )
    recipe = _load(tmp_path, text)
    assert recipe.Inference is not None
    assert recipe.Inference.mode == "mc_dropout"
    assert recipe.Inference.mc_samples == 30


def test_unknown_inference_field_is_forbidden() -> None:
    with pytest.raises(PydanticValidationError):
        InferenceSpec(mode="mc_dropout", mc_samples=30, bogus=1)  # type: ignore[call-arg]
