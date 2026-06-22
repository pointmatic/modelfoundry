# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.sections` — the discriminated-union surface resolver (Story I.c).

The op-bearing recipe sections (Loss / Optimizer / Optimizer.schedule /
Visualizations) form a discriminated union: op = discriminator, the plugin's
registered `OperationSpec.param_model` = variant. `resolve_sections` realizes the
union at validate time against the discovered plugin and never short-circuits.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from modelfoundry.plugins.base import OperationSpec
from modelfoundry.recipe.models import ModelRecipe
from modelfoundry.recipe.sections import (
    ResolvedSection,
    iter_op_sections,
    resolve_sections,
)


class _LossParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _OptimizerParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learning_rate: float = 0.001


class _SchedParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factor: float = 0.5


class _VizParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Plugin:
    name = "pytorch"
    version = "1"

    def __init__(self) -> None:
        self.operations: dict[str, OperationSpec] = {
            "cross_entropy": OperationSpec(
                op_name="cross_entropy", param_model=_LossParams, applies_to="loss"
            ),
            "adamw": OperationSpec(
                op_name="adamw", param_model=_OptimizerParams, applies_to="optimizer"
            ),
            "reduce_on_plateau": OperationSpec(
                op_name="reduce_on_plateau", param_model=_SchedParams, applies_to="schedule"
            ),
            "training_curves": OperationSpec(
                op_name="training_curves", param_model=_VizParams, applies_to="visualization"
            ),
        }


def _good_dict() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "../data/r.yml"},
        "Architecture": {"op": "simple_cnn", "num_classes": 3},
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {
            "op": "adamw",
            "learning_rate": 0.001,
            "schedule": {"op": "reduce_on_plateau", "monitor": "val_loss"},
        },
        "Training": {
            "max_epochs": 1,
            "batch_size": 1,
            "device": "cpu",
            "precision": "fp32",
            "checkpoint_cadence": 1,
        },
        "Evaluation": {
            "splits": ["test"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy"],
            "calibration_bins": 10,
        },
        "Visualizations": [{"op": "training_curves", "mode": "reporting"}],
    }


def _recipe(overrides: dict[str, Any] | None = None) -> ModelRecipe:
    data = _good_dict()
    for k, v in (overrides or {}).items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k] = {**data[k], **v}
        else:
            data[k] = v
    return ModelRecipe.model_validate(data)


def _by_label(sections: list[ResolvedSection], label: str) -> ResolvedSection:
    [section] = [s for s in sections if s.label == label]
    return section


# --- iter_op_sections enumerates the union surfaces ---


def test_iter_op_sections_yields_all_op_bearing_surfaces() -> None:
    labels = [label for label, *_ in iter_op_sections(_recipe())]
    assert labels == ["Loss", "Optimizer", "Optimizer.schedule", "Visualizations[0]"]


def test_iter_op_sections_carries_the_slot() -> None:
    by_label = {label: slot for label, _op, _params, slot in iter_op_sections(_recipe())}
    assert by_label == {
        "Loss": "loss",
        "Optimizer": "optimizer",
        "Optimizer.schedule": "schedule",
        "Visualizations[0]": "visualization",
    }


def test_iter_op_sections_omits_absent_schedule() -> None:
    labels = [label for label, *_ in iter_op_sections(_recipe({"Optimizer": {"schedule": None}}))]
    assert "Optimizer.schedule" not in labels


# --- resolve_sections: the discriminated-union resolution ---


def test_resolve_registered_op_yields_typed_variant() -> None:
    loss = _by_label(resolve_sections(_recipe(), _Plugin()), "Loss")
    assert loss.registered
    assert loss.registration_error is None
    assert isinstance(loss.variant, _LossParams)
    assert loss.param_error is None


def test_resolve_unregistered_op_is_a_registration_failure() -> None:
    loss = _by_label(resolve_sections(_recipe({"Loss": {"op": "phantom"}}), _Plugin()), "Loss")
    assert not loss.registered
    assert "phantom" in (loss.registration_error or "")
    assert loss.variant is None
    assert loss.param_error is None  # check 3 owns this, not check 17


def test_resolve_op_in_wrong_section_is_a_registration_failure() -> None:
    # `adamw` is a registered op, but for the `optimizer` slot — using it in Loss
    # must fail (the discriminator selects no valid variant for the loss slot).
    loss = _by_label(resolve_sections(_recipe({"Loss": {"op": "adamw"}}), _Plugin()), "Loss")
    assert not loss.registered
    assert "optimizer" in (loss.registration_error or "")
    assert "loss" in (loss.registration_error or "")


def test_resolve_invalid_params_is_a_param_failure() -> None:
    sections = resolve_sections(_recipe({"Optimizer": {"learning_rate": "fast"}}), _Plugin())
    opt = _by_label(sections, "Optimizer")
    assert opt.registered  # the op resolves to its slot ...
    assert opt.variant is None
    assert opt.param_error is not None  # ... but the params don't validate


def test_resolve_unknown_param_rejected_by_forbid_variant() -> None:
    sections = resolve_sections(_recipe({"Loss": {"op": "cross_entropy", "bogus": 1}}), _Plugin())
    loss = _by_label(sections, "Loss")
    assert loss.registered
    assert loss.param_error is not None  # extra="forbid" on the variant catches it


def test_resolve_never_short_circuits() -> None:
    # An unregistered Loss AND an invalid Optimizer param: BOTH are reported in one
    # pass (FR-2 comprehensive-report contract).
    sections = resolve_sections(
        _recipe({"Loss": {"op": "phantom"}, "Optimizer": {"learning_rate": "fast"}}),
        _Plugin(),
    )
    loss = _by_label(sections, "Loss")
    opt = _by_label(sections, "Optimizer")
    assert not loss.registered  # registration failure surfaced
    assert opt.registered and opt.param_error is not None  # param failure surfaced
