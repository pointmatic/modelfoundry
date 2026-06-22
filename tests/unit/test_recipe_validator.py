# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `recipe.validator.validate` — one test per FR-2 check.

Story E.b expands the B.m skeleton so **every** FR-2 check (1..20) exercises
both its pass and fail paths and asserts on the resulting `ValidationCheck`
`detail` / `message` (the "offending path" lives inside `detail`). Three layers:

1. `test_check_passes_on_good_recipe[N]` — parametrized pass path for 1..20.
2. Per-check fail-path tests, asserting on `detail`/`message`. Checks 9 / 10 / 15
   are pydantic-`Literal`-enforced, so their genuine fail path is construction
   time — exercised by asserting `ModelRecipe.model_validate` raises.
3. Fixture verification — loads each `tests/fixtures/recipes/invalid/*.yml`
   (authored in E.a) and asserts it trips *exactly* its documented check. This
   is what surfaced the check-13 gap: `invalid_baseline_model_id.yml` carries a
   non-empty-but-malformed id, which the validator does not yet reject (FR-2
   specifies a name-format check; the impl only rejects empty/whitespace). That
   test is `xfail(strict=True)` so it flips to a hard failure the moment check 13
   is tightened.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from modelfoundry.core.errors import RecipeError
from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.plugins.base import OperationSpec, Plugin
from modelfoundry.recipe.loader import load_recipe
from modelfoundry.recipe.models import ModelRecipe
from modelfoundry.recipe.validator import validate

INVALID_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "recipes" / "invalid"


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

    def prepare_for_build(self, seed: int) -> None:
        return None

    def build_model(self, arch: dict[str, Any]) -> Any:
        return None

    def run_optimization(self, *a: Any, **k: Any) -> Any:
        return None

    def run_training(self, *a: Any, **k: Any) -> Any:
        return None

    def run_evaluation(self, *a: Any, **k: Any) -> Any:
        return None

    def render_visualization(self, *a: Any, **k: Any) -> bytes | None:
        return None

    def save_model(self, model: Any, path: Path) -> None:
        return None

    def load_model(self, path: Path) -> Any:
        return None

    def predict(self, model: Any, X: Any) -> Any:
        return None

    def predict_proba(self, model: Any, X: Any) -> Any:
        return None


class _FixturePlugin(_Plugin):
    """Plugin tuned to the on-disk `invalid_*.yml` fixtures.

    The fixtures use the real pytorch op names (`cross_entropy`, `adamw`) and
    declare `device: cpu`, so this plugin registers `cross_entropy` and reports
    only `{cpu, mps}` accelerators — that way `invalid_device.yml` (which asks
    for `cuda`) is the *only* fixture that trips check 20.
    """

    def __init__(self) -> None:
        super().__init__()
        self.operations["cross_entropy"] = OperationSpec(
            op_name="cross_entropy", param_model=_LossParams, applies_to="loss"
        )

    def health_check(self) -> Any:
        return {"accelerators": ["cpu", "mps"]}


# Sanity: both synthetics satisfy the runtime Protocol.
assert isinstance(_Plugin(), Plugin)
assert isinstance(_FixturePlugin(), Plugin)


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
        "OutputExpectations": [{"metric": "accuracy", "split": "val", "op": "gte", "value": 0.5}],
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


def _check(report: Any, check_id: int) -> Any:
    [check] = [c for c in report.checks if c.id == check_id]
    return check


def _detail_text(check: Any) -> str:
    """Flatten message + detail into one string for substring assertions."""
    return f"{check.message or ''} {check.detail or ''}"


# --- Per-check PASS path (one parametrized test covering 1..20) ---


def test_predictive_entropy_is_a_selectable_metric() -> None:
    # Story H.o (R2.5): the MC predictive-uncertainty metric joins the
    # recipe-selectable evaluation vocabulary (check 11).
    report = validate(
        _recipe({"Evaluation": {"metrics": ["macro_f1", "accuracy", "predictive_entropy"]}}),
        _instance(),
        _Plugin(),
    )
    assert not _failures_for(report, 11)


@pytest.mark.parametrize("check_id", list(range(1, 22)))
def test_check_passes_on_good_recipe(check_id: int) -> None:
    report = validate(_recipe(), _instance(), _Plugin())
    check = _check(report, check_id)
    assert check.passed, check.message


def test_happy_path_all_21_pass() -> None:
    report = validate(_recipe(), _instance(), _Plugin())
    assert report.passed, [c.message for c in report.failures]
    assert [c.id for c in report.checks] == list(range(1, 22))


# --- Check 21: architecture input-shape / normalization-scale contract ---


def _instance_with_normalize(means: list[float]) -> DataRefineryInstance:
    """A synthetic instance carrying a DR `normalize` op + fitted mean stats.

    Mirrors the DataRefineryInstance the binder produces (a `recipe` with a
    `Transformations` list and a `fitted_statistics` view exposing
    `get_vector(op, name)` -> a pyarrow-like table with a `value` column).
    """
    from types import SimpleNamespace

    class _Table:
        def __init__(self, values: list[float]) -> None:
            self._values = values

        def column(self, _name: str) -> Any:
            return SimpleNamespace(to_pylist=lambda: self._values)

    class _Fitted:
        def get_vector(self, _op: str, _name: str) -> Any:
            return _Table(means)

    recipe_stub = SimpleNamespace(
        schema_version=1,
        Transformations=[SimpleNamespace(op="normalize", name="norm")],
    )
    instance = DataRefineryInstance(
        path=Path("/fixture"),
        manifest=object(),
        recipe=recipe_stub,
        splits=("train", "val", "test"),
        label_schema={"field": "label"},
        record_schema={},
        fitted_statistics=_Fitted(),
    )
    object.__setattr__(instance, "instance_num_classes", lambda: 3)
    return instance


def test_check_21_flags_normalization_units_mismatch() -> None:
    # [0,1]-scale fitted means against the adapter's 0-255 decode contract — the
    # H.a normalization-units class, caught at validate time (transformers-free).
    report = validate(_recipe(), _instance_with_normalize([0.5, 0.45, 0.4]), _Plugin())
    failing = _check(report, 21)
    assert not failing.passed
    assert "0-255" in _detail_text(failing)


def test_check_21_passes_on_realistic_0_255_stats() -> None:
    report = validate(_recipe(), _instance_with_normalize([120.0, 115.0, 110.0]), _Plugin())
    assert _check(report, 21).passed


# --- Per-check FAIL path (inline overrides + detail/message assertions) ---


def test_check_1_unsupported_schema_version() -> None:
    # Bypass loader (it gates schema_version) and construct directly.
    data = _good_recipe_dict()
    data["schema_version"] = 99
    recipe = ModelRecipe.model_validate(data)
    failing = _check(validate(recipe, _instance(), _Plugin()), 1)
    assert not failing.passed
    assert "99" in (failing.message or "")


def test_check_2_plugin_mismatch() -> None:
    failing = _check(validate(_recipe({"plugin": "sklearn"}), _instance(), _Plugin()), 2)
    assert not failing.passed
    assert failing.detail == {"declared": "sklearn", "discovered": "pytorch"}


def test_check_3_unregistered_op() -> None:
    failing = _check(validate(_recipe({"Loss": {"op": "phantom_loss"}}), _instance(), _Plugin()), 3)
    assert not failing.passed
    assert "phantom_loss" in _detail_text(failing)


def test_check_4_missing_split() -> None:
    inst = _instance(splits=("train", "test"))  # no "val"
    failing = _check(validate(_recipe(), inst, _Plugin()), 4)
    assert not failing.passed
    assert "val" in _detail_text(failing)


def test_check_5_non_train_fit_source() -> None:
    failing = _check(
        validate(_recipe({"Loss": {"weight_source": "val"}}), _instance(), _Plugin()), 5
    )
    assert not failing.passed
    assert "weight_source" in _detail_text(failing)


@pytest.mark.parametrize("source", ["train", "train_inverse_frequency", "effective_number"])
def test_check_5_all_fit_on_train_sources_pass(source: str) -> None:
    # Story H.p (R3.3): all three train-fitted class-weight modes validate.
    report = validate(
        _recipe({"Loss": {"op": "cross_entropy_class_weighted", "weight_source": source}}),
        _instance(),
        _Plugin(),
    )
    assert not _failures_for(report, 5)


def test_check_6_unknown_early_stopping_monitor() -> None:
    failing = _check(
        validate(
            _recipe({"Training": {"early_stopping": {"monitor": "phantom_metric"}}}),
            _instance(),
            _Plugin(),
        ),
        6,
    )
    assert not failing.passed
    assert "phantom_metric" in _detail_text(failing)


def test_check_7_search_space_unknown_path() -> None:
    failing = _check(
        validate(
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
        ),
        7,
    )
    assert not failing.passed
    assert "Phantom.nonexistent" in _detail_text(failing)


def test_check_8_baseline_categorical_default_not_in_choices() -> None:
    # batch_size=32 with categorical choices [128, 256] → recipe default not a choice.
    failing = _check(
        validate(
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
        ),
        8,
    )
    assert not failing.passed
    assert "Training.batch_size" in _detail_text(failing)


def test_check_9_invalid_sampler_rejected_at_construction() -> None:
    # sampler is a pydantic Literal; the fail path is at construction, not validate.
    data = _good_recipe_dict()
    data["Optimization"]["sampler"] = "genetic"
    with pytest.raises(PydanticValidationError):
        ModelRecipe.model_validate(data)


def test_check_10_n_jobs_rejected_at_construction() -> None:
    # n_jobs is Literal[1]; any other value is rejected at construction.
    data = _good_recipe_dict()
    data["Optimization"]["n_jobs"] = 4
    with pytest.raises(PydanticValidationError):
        ModelRecipe.model_validate(data)


def test_check_11_unknown_evaluation_metric() -> None:
    failing = _check(
        validate(
            _recipe({"Evaluation": {"metrics": ["macro_f1", "phantom_metric"]}}),
            _instance(),
            _Plugin(),
        ),
        11,
    )
    assert not failing.passed
    assert "phantom_metric" in _detail_text(failing)


def test_check_12_primary_metric_not_in_metrics() -> None:
    failing = _check(
        validate(
            _recipe({"Evaluation": {"primary_metric": "accuracy", "metrics": ["macro_f1"]}}),
            _instance(),
            _Plugin(),
        ),
        12,
    )
    assert not failing.passed
    assert "accuracy" in _detail_text(failing)


def test_check_13_baseline_model_id_must_be_non_empty() -> None:
    failing = _check(
        validate(
            _recipe({"Evaluation": {"comparison": {"baseline_model_id": "   "}}}),
            _instance(),
            _Plugin(),
        ),
        13,
    )
    assert not failing.passed
    assert "baseline_model_id" in _detail_text(failing)


def test_check_14_expectation_references_unproduced_metric() -> None:
    failing = _check(
        validate(
            _recipe(
                {
                    "OutputExpectations": [
                        {"metric": "phantom", "split": "val", "op": "gte", "value": 0.5}
                    ]
                }
            ),
            _instance(),
            _Plugin(),
        ),
        14,
    )
    assert not failing.passed
    assert "phantom" in _detail_text(failing)


def test_check_15_invalid_viz_mode_rejected_at_construction() -> None:
    # Visualizations[].mode is a pydantic Literal; rejected at construction.
    data = _good_recipe_dict()
    data["Visualizations"] = [{"op": "training_curves", "mode": "hologram"}]
    with pytest.raises(PydanticValidationError):
        ModelRecipe.model_validate(data)


def test_check_16_variant_references_undeclared_section() -> None:
    variants = {"big_batch": {"Phantom": {"x": 1}}}
    failing = _check(validate(_recipe(), _instance(), _Plugin(), variants_block=variants), 16)
    assert not failing.passed
    assert "Phantom" in _detail_text(failing)


def test_check_16_passes_when_variants_block_omitted() -> None:
    check_16 = _check(validate(_recipe(), _instance(), _Plugin()), 16)
    # Passes-with-skip-message rather than failing when variants_block is absent.
    assert check_16.passed and check_16.message is not None


def test_check_17_op_params_invalid_against_param_model() -> None:
    # learning_rate must be float; a non-numeric extra param fails the param_model.
    failing = _check(
        validate(
            _recipe({"Optimizer": {"learning_rate": "fast-please"}}),
            _instance(),
            _Plugin(),
        ),
        17,
    )
    assert not failing.passed
    assert "adamw" in _detail_text(failing)


def test_check_18_num_classes_mismatch() -> None:
    failing = _check(
        validate(
            _recipe({"Architecture": {"num_classes": 99}}),
            _instance(num_classes=3),
            _Plugin(),
        ),
        18,
    )
    assert not failing.passed
    assert "num_classes" in _detail_text(failing)


def test_check_18_label_field_missing() -> None:
    failing = _check(validate(_recipe(), _instance(label_field=None), _Plugin()), 18)
    assert not failing.passed
    assert "label_schema" in _detail_text(failing)


def test_check_19_dr_schema_version_too_high() -> None:
    failing = _check(validate(_recipe(), _instance(schema_version=99), _Plugin()), 19)
    assert not failing.passed
    assert "99" in _detail_text(failing)


def test_check_20_explicit_unavailable_device_fails() -> None:
    class _CpuOnlyPlugin(_Plugin):
        def health_check(self) -> Any:
            return {"accelerators": ["cpu"]}

    failing = _check(
        validate(_recipe({"Training": {"device": "cuda"}}), _instance(), _CpuOnlyPlugin()),
        20,
    )
    assert not failing.passed
    assert "cuda" in _detail_text(failing)


def test_check_20_auto_passes_without_consulting_plugin() -> None:
    # device="auto" must not require the plugin to expose accelerators.
    class _NoAccelPlugin(_Plugin):
        def health_check(self) -> Any:
            return None

    assert _check(validate(_recipe(), _instance(), _NoAccelPlugin()), 20).passed


def test_check_20_explicit_available_device_passes() -> None:
    assert _check(
        validate(_recipe({"Training": {"device": "mps"}}), _instance(), _Plugin()), 20
    ).passed


def test_check_20_skips_when_plugin_doesnt_expose_accelerators() -> None:
    # An honest plugin that hasn't wired accelerators into health_check yet
    # should not fail the validation — emit a skip-with-message instead.
    class _UninformativePlugin(_Plugin):
        def health_check(self) -> Any:
            return {"torch_version": "2.5.0"}

    check_20 = _check(
        validate(_recipe({"Training": {"device": "cuda"}}), _instance(), _UninformativePlugin()),
        20,
    )
    assert check_20.passed and check_20.message is not None


# --- No short-circuit: every distinct failure is reported ---


def test_report_collects_all_failures_no_short_circuit() -> None:
    # Break checks 12 + 14 simultaneously: the report carries both, with detail.
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
    assert "phantom" in _detail_text(_check(report, 12))
    assert "phantom" in _detail_text(_check(report, 14))


# --- Fixture verification: each invalid_*.yml trips exactly its target check ---

# (filename, target check id, token that must appear in the failing check)
_FIXTURE_FAIL_CASES = [
    ("invalid_unknown_plugin.yml", 2, "tensorflow"),
    ("invalid_unknown_loss_op.yml", 3, "bogus_loss"),
    ("invalid_fit_on_train.yml", 5, "weight_source"),
    ("invalid_early_stopping_monitor.yml", 6, "bogus_metric"),
    ("invalid_search_space_path.yml", 7, "Bogus.nonexistent_path"),
    ("invalid_metric_vocabulary.yml", 11, "bogus_metric"),
    ("invalid_primary_metric.yml", 12, "ece"),
    ("invalid_expectations_split.yml", 14, "test"),
    ("invalid_num_classes.yml", 18, "num_classes"),
    ("invalid_device.yml", 20, "cuda"),
]


@pytest.mark.parametrize("filename, check_id, token", _FIXTURE_FAIL_CASES)
def test_invalid_fixture_trips_exactly_its_target_check(
    filename: str, check_id: int, token: str
) -> None:
    recipe = load_recipe(INVALID_DIR / filename)
    report = validate(recipe, _instance(), _FixturePlugin())
    # "Otherwise-valid recipe mutated to fail exactly one check" (E.a contract).
    assert {c.id for c in report.failures} == {check_id}, [
        (c.id, c.message) for c in report.failures
    ]
    assert token in _detail_text(_check(report, check_id))


def test_invalid_schema_version_fixture_rejected_by_loader() -> None:
    # check 1: the loader's schema-version gate rejects this before validate().
    with pytest.raises(RecipeError) as exc:
        load_recipe(INVALID_DIR / "invalid_schema_version.yml")
    assert "99" in str(exc.value)


def test_invalid_variants_fixture_trips_check_16() -> None:
    # check 16: the loader clears `variants`, so thread the raw block separately.
    path = INVALID_DIR / "invalid_variants_keys.yml"
    recipe = load_recipe(path)
    variants_block = yaml.safe_load(path.read_text(encoding="utf-8"))["variants"]
    report = validate(recipe, _instance(), _FixturePlugin(), variants_block=variants_block)
    assert {c.id for c in report.failures} == {16}, [(c.id, c.message) for c in report.failures]
    assert "NonexistentSection" in _detail_text(_check(report, 16))


@pytest.mark.xfail(
    reason=(
        "FR-2 check 13 (features.md:223) specifies a name-format check, but the "
        "validator only rejects empty/whitespace baseline_model_id. "
        "invalid_baseline_model_id.yml carries a non-empty malformed id, so check "
        "13 does not yet trip. Tighten check 13 (or repurpose the fixture) to flip "
        "this xfail to a pass."
    ),
    strict=True,
)
def test_invalid_baseline_model_id_fixture_should_trip_check_13() -> None:
    recipe = load_recipe(INVALID_DIR / "invalid_baseline_model_id.yml")
    report = validate(recipe, _instance(), _FixturePlugin())
    assert _failures_for(report, 13)


# --- ValidationReport API ---


def test_report_passed_property_aggregates() -> None:
    good = validate(_recipe(), _instance(), _Plugin())
    bad = validate(_recipe({"plugin": "sklearn"}), _instance(), _Plugin())
    assert good.passed is True
    assert bad.passed is False
    assert len(bad.failures) >= 1
