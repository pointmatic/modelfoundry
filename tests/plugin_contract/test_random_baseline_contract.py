# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""random/dummy baseline plugin contract test (Story H.f.2).

Pins the random chance-baseline plugin as a first-class ModelFoundry plugin, on
equal footing with `pytorch`/`sklearn`:

1. It is discoverable via the `modelfoundry.plugins` entry point.
2. It registers its op set — the `dummy_classifier` architecture op plus the
   recognized (no-param) Loss/Optimizer ops its recipe declares — each spec
   well-formed.
3. It satisfies the `Plugin` Protocol statically (`-> Plugin`) and at runtime
   (`isinstance`), and `health_check()` returns the `CheckReport` shape.
4. It materializes end-to-end through the plugin-agnostic `MaterializeRunner`
   (build -> train -> evaluate -> persist -> report).
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
from modelfoundry.plugins.discovery import discover_plugins
from modelfoundry.plugins.random.plugin import RandomPlugin

# The DummyClassifier is sklearn (a base dep), but the synthesized DataRefinery
# instance the end-to-end test binds against pulls in the torch-carrying builder
# stack (the baseline reuses the PyTorch feature path).
torch = pytest.importorskip("torch")

_NUM_CLASSES = 3


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    yield
    torch.use_deterministic_algorithms(False)


def _plugin() -> Plugin:
    """The random plugin, typed as `Plugin` so mypy verifies Protocol conformance."""
    return RandomPlugin()


def _random_recipe() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plugin": "random",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "type": "dummy_classifier",
            "num_classes": _NUM_CLASSES,
            "strategy": "stratified",
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "none"},
        "Training": {
            "max_epochs": 1,
            "batch_size": 8,
            "device": "cpu",
            "precision": "fp32",
            "checkpoint_cadence": 1,
        },
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1"],
            "calibration_bins": 10,
        },
    }


def test_random_is_discoverable_via_entry_point() -> None:
    plugins = discover_plugins()
    assert "random" in plugins
    assert isinstance(plugins["random"], Plugin)


def test_random_satisfies_plugin_protocol_at_runtime() -> None:
    assert isinstance(_plugin(), Plugin)


def test_random_registers_its_operation_set() -> None:
    ops = _plugin().operations
    # The dummy_classifier architecture op + the recognized Loss/Optimizer ops the
    # recipe declares (a chance baseline has no real loss/optimizer, but the schema
    # requires both blocks, so they are registered as no-ops for validator check 3).
    assert set(ops) == {"dummy_classifier", "cross_entropy", "none"}
    assert ops["dummy_classifier"].applies_to == "architecture"
    assert ops["cross_entropy"].applies_to == "loss"
    assert ops["none"].applies_to == "optimizer"
    for op_name, spec in ops.items():
        assert isinstance(spec, OperationSpec)
        assert spec.op_name == op_name
        assert issubclass(spec.param_model, BaseModel)


def test_random_health_check_returns_check_report_shape() -> None:
    report = _plugin().health_check()
    assert isinstance(report, CheckReport)
    assert report.plugin == "random"
    assert isinstance(report.available, bool)
    assert isinstance(report.accelerators, tuple)


def test_random_materializes_end_to_end(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry, ModelInstance

    data = build_dr_instance(tmp_path / "dr", split_counts={"train": 24, "val": 9}, image_size=8)
    recipe_path = tmp_path / "random.yml"
    recipe_path.write_text(yaml.safe_dump(_random_recipe()), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")

    instance = ModelFoundry.from_recipe(recipe_path, data=data, config=config).materialize()

    assert isinstance(instance, ModelInstance)
    accuracy = instance.evaluation["val"]["accuracy"]
    assert isinstance(accuracy, float)
    assert 0.0 <= accuracy <= 1.0
    # The fitted estimator + manifest were persisted into the promoted instance.
    assert (instance.path / "manifest.json").is_file()
    assert (instance.path / "model").exists()
