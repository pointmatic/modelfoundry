# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Notebook-substrate-neutral Jupyter smoke — TR-8 (Story E.k).

Executes a real Jupyter notebook (via `nbclient` + an `ipykernel` kernel) whose
cell runs `ModelFoundry.from_recipe(...).materialize()` against a synthesized
DataRefinery fixture, then asserts the notebook-shaped `ModelInstance` accessors
render the expected types (`UR-2`: the three-line surface works identically in a
notebook cell). The cell renders a `display(...)`-style consumption of `.metrics`
/ `.evaluation` / `.figures` / `.predictions`.

Runs in `smoke-pytorch`: the nbclient kernel is a fresh subprocess that executes
a real materialize, so it needs the full torch + modelfoundry runtime closure
(plus the `[notebook-smokes]` extra), not the light testenv. The kernel does not
inherit pytest's `conftest` / `sys.path`, so the executed cell is self-contained
— it puts the fixtures dir on `sys.path` and rebuilds the deterministic DR
fixture itself. A failed in-cell assertion surfaces as an `nbclient`
`CellExecutionError`, failing the test.

Marimo headless + IPython REPL smokes are deferred per Q14.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("torch")
nbformat = pytest.importorskip("nbformat")
pytest.importorskip("nbclient")
pytest.importorskip("ipykernel")

from nbclient import NotebookClient  # noqa: E402

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

_RECIPE = """\
schema_version: 1
plugin: pytorch
seed: 7
Data: {recipe: dr_recipe.yml}
Architecture:
  num_classes: 3
  layers: [{op: Flatten}, {op: Linear, in_features: 48, out_features: 3}]
Loss: {op: cross_entropy}
Optimizer: {op: adamw, learning_rate: 0.01}
Training: {max_epochs: 1, batch_size: 4, num_workers: 0, device: cpu}
Evaluation: {splits: [val], primary_metric: accuracy, metrics: [accuracy, macro_f1]}
Visualizations:
  - {name: curves, op: training_curves, mode: reporting}
  - {name: cm, op: confusion_matrix, mode: reporting}
"""

# The notebook cell is self-contained (a fresh kernel inherits nothing from
# pytest). `__TOKEN__` placeholders are substituted with repr'd absolute paths so
# the dict literals below don't collide with str.format braces.
_CELL_TEMPLATE = '''\
import sys
sys.path.insert(0, __FIXTURES__)

import pandas as pd
from matplotlib.figure import Figure  # noqa: F401  (smoke: the notebook stack imports)
from datarefinery_instances.builder import build_dr_instance
from modelfoundry import ModelFoundry
from modelfoundry.core.config import RuntimeConfig

data = build_dr_instance(__DR_DIR__, split_counts={"train": 16, "val": 8}, image_size=4)
mf = ModelFoundry.from_recipe(
    __RECIPE__, data=data, config=RuntimeConfig(cache_root=__MF_CACHE__)
)
mi = mf.materialize()

# The notebook-shaped accessors (UR-1 / UR-2) render the expected primitive types.
assert isinstance(mi.metrics, dict) and mi.metrics, "metrics"
assert isinstance(mi.evaluation, dict) and "val" in mi.evaluation, "evaluation"
assert isinstance(mi.predictions, pd.DataFrame) and len(mi.predictions) > 0, "predictions"
assert isinstance(mi.figures, dict) and mi.figures, "figures"
assert all(isinstance(v, (bytes, bytearray)) for v in mi.figures.values()), "figure bytes"

# A notebook would `display(...)` these; here we just confirm they materialize.
print("FIGURES", sorted(mi.figures))
print("SMOKE_OK")
'''


def _cell_source(tmp_path: Path) -> str:
    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(_RECIPE, encoding="utf-8")
    return (
        _CELL_TEMPLATE.replace("__FIXTURES__", repr(str(_FIXTURES_DIR)))
        .replace("__DR_DIR__", repr(str(tmp_path / "dr")))
        .replace("__RECIPE__", repr(str(recipe_path)))
        .replace("__MF_CACHE__", repr(str(tmp_path / "mf_cache")))
    )


def test_materialize_in_jupyter_notebook_cell(tmp_path: Path) -> None:
    notebook = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell(_cell_source(tmp_path))]
    )
    # Raises CellExecutionError (failing the test) if any in-cell assertion trips.
    NotebookClient(notebook, timeout=300, kernel_name="python3").execute()

    outputs = [out for cell in notebook.cells for out in cell.get("outputs", [])]
    assert not [o for o in outputs if o.output_type == "error"]
    streams = "".join(o.get("text", "") for o in outputs if o.output_type == "stream")
    assert "SMOKE_OK" in streams
