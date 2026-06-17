# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""sklearn plugin contract test (Story E.i, tech-spec § Plugin contract tests).

The sklearn plugin began as a stub (CR-9) and was promoted to a working
`MLPClassifier` baseline in C.m. This pins its contract:

1. It registers its full `OperationSpec` set — the `mlp_classifier` architecture
   op — each spec well-formed.
2. It satisfies the `Plugin` Protocol statically (the `-> Plugin` return on
   `_plugin()`, enforced by the env `mypy src tests --strict` gate) and at runtime
   (`isinstance` against the `@runtime_checkable` Protocol), and `health_check()`
   returns the `CheckReport` shape.
3. It materializes a small `MLPClassifier` recipe end-to-end through the
   plugin-agnostic `MaterializeRunner` (build → train → evaluate → persist →
   report), proving the Protocol is not just shape-conformant but executable.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]
from pydantic import BaseModel

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.plugins.base import CheckReport, OperationSpec, Plugin
from modelfoundry.plugins.sklearn.plugin import SklearnPlugin

# sklearn is a base dependency, but the synthesized DataRefinery instance the
# end-to-end test binds against pulls in the (torch-carrying) builder stack.
torch = pytest.importorskip("torch")

_NUM_CLASSES = 3


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def _plugin() -> Plugin:
    """The sklearn plugin, typed as `Plugin` so mypy verifies Protocol conformance."""
    return SklearnPlugin()


def _mlp_recipe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plugin": "sklearn",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "type": "mlp_classifier",
            "num_classes": _NUM_CLASSES,
            "hidden_layer_sizes": [16],
            "max_iter": 50,
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {"max_epochs": 1, "batch_size": 8, "num_workers": 0, "device": "cpu"},
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1"],
        },
    }


def test_sklearn_satisfies_plugin_protocol_at_runtime() -> None:
    assert isinstance(_plugin(), Plugin)


def test_sklearn_registers_its_full_operation_set() -> None:
    ops = _plugin().operations
    # Story H.f.1: besides the `mlp_classifier` architecture op, the baseline now
    # registers the Loss/Optimizer ops its recipe declares so `validate()` passes;
    # the optimizer ops map onto MLPClassifier's `solver` + `learning_rate_init`.
    assert set(ops) == {"mlp_classifier", "cross_entropy", "adam", "sgd"}
    assert ops["mlp_classifier"].applies_to == "architecture"
    assert ops["cross_entropy"].applies_to == "loss"
    assert {ops["adam"].applies_to, ops["sgd"].applies_to} == {"optimizer"}
    for op_name, spec in ops.items():
        assert isinstance(spec, OperationSpec)
        assert spec.op_name == op_name
        assert issubclass(spec.param_model, BaseModel)


def test_sklearn_health_check_returns_check_report_shape() -> None:
    report = _plugin().health_check()
    assert isinstance(report, CheckReport)
    assert report.plugin == "sklearn"
    assert isinstance(report.available, bool)
    assert isinstance(report.accelerators, tuple)


def test_sklearn_materializes_mlp_classifier_end_to_end(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    data = build_dr_instance(tmp_path / "dr", split_counts={"train": 24, "val": 9}, image_size=8)
    recipe_path = tmp_path / "mlp.yml"
    recipe_path.write_text(yaml.safe_dump(_mlp_recipe()), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")

    instance = ModelFoundry.from_recipe(recipe_path, data=data, config=config).materialize()

    assert isinstance(instance, ModelInstance)
    accuracy = instance.evaluation["val"]["accuracy"]
    assert isinstance(accuracy, float)
    assert 0.0 <= accuracy <= 1.0
    # The trained estimator + manifest were persisted into the promoted instance.
    assert (instance.path / "manifest.json").is_file()
    assert (instance.path / "model").exists()
