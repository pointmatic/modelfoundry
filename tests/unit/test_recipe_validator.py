# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.validator.validate` — one test per FR-2 check."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.plugins.base import OperationSpec, Plugin
from modelfoundry.recipe.models import ModelRecipe
from modelfoundry.recipe.validator import validate

# --- Synthetic plugin with the ops the GOOD_RECIPE references ---


class _LossParams(BaseModel):
    weight_source: str = "train"


class _OptimizerParams(BaseModel):
    learning_rate: float = 0.001


class _ScheduleParams(BaseModel):
    factor: float = 0.5
    patience: int = 2


class _VizParams(BaseModel):
    pass


class _Plugin:
    name = "pytorch"
    version = "1"

    def __init__(self) -> None:
        self.operations: dict[str, OperationSpec] = {
            "cross_entropy_class_weighted": OperationSpec(
                op_name="cross_entropy_class_weighted",
                param_model=_LossParams,
                applies_to="loss",
            ),
            "adamw": OperationSpec(
                op_name="adamw", param_model=_OptimizerParams, applies_to="optimizer"
            ),
            "reduce_on_plateau": OperationSpec(
                op_name="reduce_on_plateau",
                param_model=_ScheduleParams,
                applies_to="schedule",
            ),
            "training_curves": OperationSpec(
                op_name="training_curves",
                param_model=_VizParams,
                applies_to="visualization",
            ),
        }

    def health_check(self) -> Any:
        return {"accelerators": ["cpu", "mps", "cuda"]}
    def build_model(self, arch: dict[str, Any]) -> Any: return None
    def run_optimization(self, *a: Any, **k: Any) -> Any: return None
    def run_training(self, *a: Any, **k: Any) -> Any: return None
    def run_evaluation(self, *a: Any, **k: Any) -> Any: return None
    def render_visualization(self, *a: Any, **k: Any) -> bytes | None: return None
    def save_model(self, model: Any, path: Path) -> None: return None
    def load_model(self, path: Path) -> Any: return None
    def predict(self, model: Any, X: Any) -> Any: return None
    def predict_proba(self, model: Any, X: Any) -> Any: return None


# Sanity: the synthetic satisfies the runtime Protocol.
assert isinstance(_Plugin(), Plugin)


# --- Synthetic DataRefinery instance ---


def _instance(
    *,
    splits: tuple[str, ...] = ("train", "val", "test"),
    label_field: str | None = "label",
    num_classes: int = 3,
    schema_version: int = 1,
) -> DataRefineryInstance:
    from types import SimpleNamespace

    recipe_stub = SimpleNamespace(schema_version=schema_version)
    label_schema = {"field": label_field} if label_field else {}
    instance = DataRefineryInstance(
        path=Path("/fixture"),
        manifest=object(),
        recipe=recipe_stub,
        splits=splits,
        label_schema=label_schema,
        record_schema={},
    )
    # Override instance_num_classes with a fixed value (no jsonl on disk).
    object.__setattr__(instance, "instance_num_classes", lambda: num_classes)
    return instance


# --- Good recipe (every check passes) ---


def _good_recipe_dict() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "../data/r.yml"},
        "Architecture": {"op": "simple_cnn", "num_classes": 3},
        "Loss": {"op": "cross_entropy_class_weighted", "weight_source": "train"},
        "Optimizer": {
            "op": "adamw",
            "learning_rate": 0.001,
            "schedule": {"op": "reduce_on_plateau", "monitor": "val_loss"},
        },
        "Training": {
            "max_epochs": 3,
            "batch_size": 32,
            "early_stopping": {"monitor": "val_loss", "mode": "min", "patience": 2},
        },
        "Optimization": {
            "sampler": "tpe",
            "pruner": "median",
            "n_trials": 5,
            "n_jobs": 1,
            "baseline_trial": "enqueue_recipe_defaults",
            "search_space": {
                "Optimizer.learning_rate": {"log_uniform": [1e-5, 1e-2]},
                "Training.batch_size": {"categorical": [16, 32, 64]},
            },
        },
        "Evaluation": {
            "splits": ["val", "test"],
            "primary_metric": "macro_f1",
            "metrics": ["macro_f1", "accuracy", "ece"],
            "comparison": {"baseline_model_id": "hf://example/baseline"},
        },
        "Visualizations": [{"op": "training_curves", "mode": "reporting"}],
        "OutputExpectations": [
            {"metric": "accuracy", "split": "val", "op": "gte", "value": 0.5}
        ],
    }


def _recipe(overrides: dict[str, Any] | None = None) -> ModelRecipe:
    data = _good_recipe_dict()
    if overrides:
        _deep_apply(data, overrides)
    return ModelRecipe.model_validate(data)


def _deep_apply(target: dict[str, Any], overlay: dict[str, Any]) -> None:
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_apply(target[k], v)
        else:
            target[k] = v


def _failures_for(report: Any, check_id: int) -> list[Any]:
    return [c for c in report.failures if c.id == check_id]


# --- happy path ---


def test_happy_path_all_20_pass() -> None:
    report = validate(_recipe(), _instance(), _Plugin())
    assert report.passed, [c.message for c in report.failures]
    assert [c.id for c in report.checks] == list(range(1, 21))


def test_report_collects_all_failures_no_short_circuit() -> None:
    # Break checks 12 + 14 simultaneously: report carries both failures.
    report = validate(
        _recipe(
            {
                "Evaluation": {"primary_metric": "phantom"},
                "OutputExpectations": [
                    {"metric": "phantom", "split": "val", "op": "gte", "value": 0.5}
                ],
            }
        ),
        _instance(),
        _Plugin(),
    )
    failed_ids = {c.id for c in report.failures}
    assert 12 in failed_ids and 14 in failed_ids


# --- per-check failure tests ---


def test_check_1_unsupported_schema_version() -> None:
    # Bypass loader: construct ModelRecipe with schema_version=99 directly.
    data = _good_recipe_dict()
    data["schema_version"] = 99
    recipe = ModelRecipe.model_validate(data)
    report = validate(recipe, _instance(), _Plugin())
    assert _failures_for(report, 1)


def test_check_2_plugin_mismatch() -> None:
    report = validate(_recipe({"plugin": "sklearn"}), _instance(), _Plugin())
    assert _failures_for(report, 2)


def test_check_3_unregistered_op() -> None:
    report = validate(_recipe({"Loss": {"op": "phantom_loss"}}), _instance(), _Plugin())
    assert _failures_for(report, 3)


def test_check_4_missing_split() -> None:
    inst = _instance(splits=("train", "test"))  # no "val"
    report = validate(_recipe(), inst, _Plugin())
    assert _failures_for(report, 4)


def test_check_5_non_train_fit_source() -> None:
    report = validate(
        _recipe({"Loss": {"weight_source": "val"}}), _instance(), _Plugin()
    )
    assert _failures_for(report, 5)


def test_check_6_unknown_early_stopping_monitor() -> None:
    report = validate(
        _recipe({"Training": {"early_stopping": {"monitor": "phantom_metric"}}}),
        _instance(),
        _Plugin(),
    )
    assert _failures_for(report, 6)


def test_check_7_search_space_unknown_path() -> None:
    report = validate(
        _recipe(
            {
                "Optimization": {
                    "search_space": {
                        "Optimizer.learning_rate": {"log_uniform": [1e-5, 1e-2]},
                        "Phantom.nonexistent": {"log_uniform": [0, 1]},
                    }
                }
            }
        ),
        _instance(),
        _Plugin(),
    )
    assert _failures_for(report, 7)


def test_check_8_baseline_categorical_default_not_in_choices() -> None:
    # batch_size=32 with categorical choices [128, 256] → recipe default not a choice.
    report = validate(
        _recipe(
            {
                "Optimization": {
                    "search_space": {
                        "Optimizer.learning_rate": {"log_uniform": [1e-5, 1e-2]},
                        "Training.batch_size": {"categorical": [128, 256]},
                    }
                }
            }
        ),
        _instance(),
        _Plugin(),
    )
    assert _failures_for(report, 8)


def test_check_9_sampler_pruner_enforced_at_construction() -> None:
    # Pydantic Literal blocks construction; the validator's sanity check passes
    # any successfully constructed recipe — confirm happy path here.
    report = validate(_recipe(), _instance(), _Plugin())
    assert not _failures_for(report, 9)


def test_check_10_n_jobs_locked_to_one() -> None:
    # Pydantic Literal[1] blocks Optimization.n_jobs != 1; sanity passes.
    report = validate(_recipe(), _instance(), _Plugin())
    assert not _failures_for(report, 10)


def test_check_11_unknown_evaluation_metric() -> None:
    report = validate(
        _recipe({"Evaluation": {"metrics": ["macro_f1", "phantom_metric"]}}),
        _instance(),
        _Plugin(),
    )
    assert _failures_for(report, 11)


def test_check_12_primary_metric_not_in_metrics() -> None:
    report = validate(
        _recipe(
            {"Evaluation": {"primary_metric": "accuracy", "metrics": ["macro_f1"]}}
        ),
        _instance(),
        _Plugin(),
    )
    assert _failures_for(report, 12)


def test_check_13_baseline_model_id_must_be_non_empty() -> None:
    report = validate(
        _recipe({"Evaluation": {"comparison": {"baseline_model_id": "   "}}}),
        _instance(),
        _Plugin(),
    )
    assert _failures_for(report, 13)


def test_check_14_expectation_references_unproduced_metric() -> None:
    report = validate(
        _recipe(
            {
                "OutputExpectations": [
                    {"metric": "phantom", "split": "val", "op": "gte", "value": 0.5}
                ]
            }
        ),
        _instance(),
        _Plugin(),
    )
    assert _failures_for(report, 14)


def test_check_15_mode_is_pydantic_enforced() -> None:
    # Pydantic Literal enforces; sanity passes on a successfully constructed recipe.
    report = validate(_recipe(), _instance(), _Plugin())
    assert not _failures_for(report, 15)


def test_check_16_variant_references_undeclared_section() -> None:
    variants = {"big_batch": {"Phantom": {"x": 1}}}
    report = validate(_recipe(), _instance(), _Plugin(), variants_block=variants)
    assert _failures_for(report, 16)


def test_check_16_passes_when_variants_block_omitted() -> None:
    report = validate(_recipe(), _instance(), _Plugin())
    # Check passes-with-skip-message rather than failing when variants_block is absent.
    [check_16] = [c for c in report.checks if c.id == 16]
    assert check_16.passed and check_16.message is not None


def test_check_17_op_params_invalid_against_param_model() -> None:
    # learning_rate must be float; pass a non-numeric extra param value.
    report = validate(
        _recipe({"Optimizer": {"learning_rate": "fast-please"}}), _instance(), _Plugin()
    )
    assert _failures_for(report, 17)


def test_check_18_num_classes_mismatch() -> None:
    report = validate(
        _recipe({"Architecture": {"num_classes": 99}}), _instance(num_classes=3), _Plugin()
    )
    assert _failures_for(report, 18)


def test_check_18_label_field_missing() -> None:
    report = validate(_recipe(), _instance(label_field=None), _Plugin())
    assert _failures_for(report, 18)


def test_check_19_dr_schema_version_too_high() -> None:
    report = validate(_recipe(), _instance(schema_version=99), _Plugin())
    assert _failures_for(report, 19)


# --- Check 20: Training.device availability ---


def test_check_20_auto_passes_without_consulting_plugin() -> None:
    # device="auto" must not require the plugin to expose accelerators.
    class _NoAccelPlugin(_Plugin):
        def health_check(self) -> Any:
            return None

    report = validate(_recipe(), _instance(), _NoAccelPlugin())
    [check_20] = [c for c in report.checks if c.id == 20]
    assert check_20.passed


def test_check_20_explicit_unavailable_device_fails() -> None:
    class _CpuOnlyPlugin(_Plugin):
        def health_check(self) -> Any:
            return {"accelerators": ["cpu"]}

    report = validate(_recipe({"Training": {"device": "cuda"}}), _instance(), _CpuOnlyPlugin())
    assert _failures_for(report, 20)


def test_check_20_explicit_available_device_passes() -> None:
    report = validate(_recipe({"Training": {"device": "mps"}}), _instance(), _Plugin())
    assert not _failures_for(report, 20)


def test_check_20_skips_when_plugin_doesnt_expose_accelerators() -> None:
    # An honest plugin that hasn't wired accelerators into health_check yet
    # should not fail the validation — emit a skip-with-message instead.
    class _UninformativePlugin(_Plugin):
        def health_check(self) -> Any:
            return {"torch_version": "2.5.0"}

    report = validate(
        _recipe({"Training": {"device": "cuda"}}), _instance(), _UninformativePlugin()
    )
    [check_20] = [c for c in report.checks if c.id == 20]
    assert check_20.passed and check_20.message is not None


# --- ValidationReport API ---


def test_report_passed_property_aggregates() -> None:
    good = validate(_recipe(), _instance(), _Plugin())
    bad = validate(_recipe({"plugin": "sklearn"}), _instance(), _Plugin())
    assert good.passed is True
    assert bad.passed is False
    assert len(bad.failures) >= 1
