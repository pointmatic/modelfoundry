# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Extras-gating (R1.4) absent-side contract for the pretrained-encoder path (Story H.l).

Runs in an env that has `torch` but NOT `transformers` (the `smoke-pytorch` env);
skips when `[huggingface]` IS installed (its present-side — materialize succeeds —
is covered by `test_pretrained_encoder.py` in `smoke-huggingface`). Locks the
"discoverable without the extra; gated at materialize time" rule: an encoder recipe
LOADS and VALIDATES against the in-tree vocabulary, but building/materializing it
raises a clear `ImportError` with the install pointer.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from datarefinery_instances.builder import (  # type: ignore[import-not-found]
    build_dr_instance,
)

from modelfoundry.core.config import RuntimeConfig

pytest.importorskip("torch")

if importlib.util.find_spec("transformers") is not None:
    pytest.skip(
        "transformers installed; the no-extras gating path is exercised only without it",
        allow_module_level=True,
    )

_RECIPE = "tests/fixtures/recipes/pretrained_encoder_smoke.yml"


def _instance(root: Path) -> Any:
    return build_dr_instance(
        root, classes=("c0", "c1", "c2"), split_counts={"train": 6, "val": 3}, image_size=224
    )


def test_encoder_recipe_loads_and_validates_without_the_extra(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry

    mf = ModelFoundry.from_recipe(_RECIPE, data=_instance(tmp_path / "dr"))  # load succeeds
    report = mf.validate()  # validate succeeds against the in-tree vocabulary
    assert report.passed, [c.message for c in report.failures]


def test_encoder_materialize_is_gated_without_the_extra(tmp_path: Path) -> None:
    from modelfoundry import ModelFoundry
    from modelfoundry.core.errors import MaterializeError

    config = RuntimeConfig(cache_root=tmp_path / "cache")
    mf = ModelFoundry.from_recipe(_RECIPE, data=_instance(tmp_path / "dr"), config=config)
    # materialize fails at the architecture stage; the runner wraps the gate's
    # ImportError in a MaterializeError, but the `[huggingface]` install pointer
    # is preserved in the message (R1.4).
    with pytest.raises(MaterializeError, match=r"\[huggingface\]"):
        mf.materialize()


def test_encoder_summary_is_gated_without_the_extra(tmp_path: Path) -> None:
    # The direct build path (summary) surfaces the gate's ImportError unwrapped.
    from modelfoundry import ModelFoundry

    mf = ModelFoundry.from_recipe(_RECIPE, data=_instance(tmp_path / "dr"))
    with pytest.raises(ImportError, match=r"\[huggingface\]"):
        mf.summary()
