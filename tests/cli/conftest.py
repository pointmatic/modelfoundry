# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the end-to-end CLI smoke tests (Story E.j).

Each `test_cli_<verb>.py` drives the real Typer app through `CliRunner` against a
synthesized DataRefinery instance + a minimal recipe, asserting the verb's exit
code, its `rich` output, and — where the verb logs — the JSON-lines operational
channel on `--log-target`.

The CLI only accepts a `--data-cache-root` *path* and always resolves the bound
instance through `resolve_data_instance` (which calls DataRefinery's blessed
`resolve_instance`, hashing real on-disk source inputs — see C.q.1). To keep
these smokes fast and host-independent, `cli_env` stubs that one seam to return
the synthesized fixture instance; the binding itself is covered by B.i / C.q.1.
Everything else — arg parsing, `RuntimeConfig` assembly, command dispatch,
rendering, exit-code mapping, logging — runs for real.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

# A minimal, fast pytorch recipe (one Flatten+Linear, one epoch) over the
# synthesized 3-class / 4x4 image instance.
_IMAGE_SIZE = 4
_NUM_CLASSES = 3
_MINIMAL_RECIPE: dict[str, Any] = {
    "schema_version": 1,
    "plugin": "pytorch",
    "seed": 7,
    "Data": {"recipe": "dr_recipe.yml"},
    "Architecture": {
        "num_classes": _NUM_CLASSES,
        "layers": [
            {"op": "Flatten"},
            {
                "op": "Linear",
                "in_features": _IMAGE_SIZE * _IMAGE_SIZE * 3,
                "out_features": _NUM_CLASSES,
            },
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
        "metrics": ["accuracy", "macro_f1"],
        "calibration_bins": 10,
    },
}


@pytest.fixture
def cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A wired CLI environment: synthesized instance, minimal recipe, stubbed resolver."""
    from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

    import modelfoundry.core.modelfoundry as mf_mod
    import modelfoundry.scaffolder.init as init_mod

    dr_instance = build_dr_instance(
        tmp_path / "dr", split_counts={"train": 16, "val": 8}, image_size=_IMAGE_SIZE
    )
    # The CLI always path-resolves the bound instance; inject the fixture instead.
    # Both `from_recipe` (every data-binding verb) and the `init` scaffolder import
    # `resolve_data_instance` into their own namespace, so stub both seams.
    for module in (mf_mod, init_mod):
        monkeypatch.setattr(module, "resolve_data_instance", lambda data_spec, config: dr_instance)

    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(_MINIMAL_RECIPE), encoding="utf-8")

    return SimpleNamespace(
        recipe=recipe_path,
        dr_instance=dr_instance,
        dr_recipe=tmp_path / "dr" / "dr_recipe.yml",  # written by build_dr_instance
        cache_root=tmp_path / "mf_cache",
        data_cache_root=tmp_path / "dr",
        log_target=tmp_path / "ops.jsonl",
    )


@pytest.fixture
def shared_opts(cli_env: SimpleNamespace) -> list[str]:
    """The global `--cache-root` / `--data-cache-root` / `--log-target` options."""
    return [
        "--cache-root",
        str(cli_env.cache_root),
        "--data-cache-root",
        str(cli_env.data_cache_root),
        "--log-target",
        str(cli_env.log_target),
    ]


@pytest.fixture
def materialized(cli_env: SimpleNamespace) -> Iterator[Any]:
    """A materialized `ModelInstance` for the read-only verbs (report / inspect / status)."""
    import torch

    from modelfoundry import ModelFoundry
    from modelfoundry.core.config import RuntimeConfig

    instance = ModelFoundry.from_recipe(
        cli_env.recipe,
        data=cli_env.dr_instance,
        config=RuntimeConfig(cache_root=cli_env.cache_root),
    ).materialize()
    yield instance
    # The PyTorch plugin flips on deterministic mode during materialize; restore it.
    torch.use_deterministic_algorithms(False)
