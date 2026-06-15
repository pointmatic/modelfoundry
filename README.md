# ModelFoundry

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

Compile a YAML recipe into a reproducible, framework-agnostic trained-model instance.

ModelFoundry consumes a materialized [DataRefinery](https://github.com/pointmatic/datarefinery) instance and compiles a single YAML **model recipe** into a content-addressed, atomically-promoted **ModelInstance**: the trained model, per-epoch metrics, hyperparameter-search trials, held-out evaluation, predictions, visualizations, and a manifest. The result object returns notebook-shaped primitives (`pandas.DataFrame` / `numpy.ndarray` / PNG `bytes`) and works identically inside Jupyter, Marimo, IPython, or a plain `.py` script — no framework imports in user code.

Reproducibility is a first-class concern: every stochastic source is seeded, the cache identity is computed from the recipe's normalized semantic form, and the same `(recipe, data, seed, variant)` tuple materializes to a byte-identical `ModelInstance`.

> **Status:** pre-production (`0.x.y` series). APIs, CLI surface, and cache layout may change between minor versions until the `1.0.0` production release. See [`docs/specs/`](docs/specs/) for the concept, feature, technical, and story specifications.

## Installation

```bash
pip install ml-modelfoundry[pytorch]
```

The import name and console script are both `modelfoundry`; the PyPI distribution is `ml-modelfoundry`. The pre-production release ships an end-to-end **PyTorch** plugin (image classification, CIFAR-10-scale) plus a scikit-learn `MLPClassifier` baseline; the base install (`pip install ml-modelfoundry`) carries everything except the framework — a recipe selects its backend via the `[pytorch]` extra.

## Quickstart — CIFAR-10

ModelFoundry never does data prep: splitting, cleaning, sampling, and feature engineering are DataRefinery's job. The quickstart assumes the two bundled recipes — `recipes/cifar10-base.yaml` (the DataRefinery dataset recipe) and `recipes/cifar10_resnet20.yml` (the ModelFoundry ResNet-20 recipe, bound to it).

```bash
# 1. Materialize the CIFAR-10 dataset with DataRefinery (one-time) → ./data
datarefinery materialize recipes/cifar10-base.yaml

# 2. Validate, then materialize the model with ModelFoundry → ./models
modelfoundry validate    recipes/cifar10_resnet20.yml
modelfoundry materialize recipes/cifar10_resnet20.yml
```

`materialize` runs the full pipeline — hyperparameter optimization → training → held-out evaluation → output-expectation checks → persistence → report — and atomically promotes the result into the content-addressed cache. Re-running the same recipe finds the existing instance; pass `--overwrite` to recompute.

Then consume the materialized instance — from a script, a notebook, or the CLI:

```python
from datarefinery import DataRefinery
from modelfoundry import ModelFoundry

data = DataRefinery.from_recipe("recipes/cifar10-base.yaml").materialize()
model = ModelFoundry.from_recipe("recipes/cifar10_resnet20.yml", data=data).materialize()

model.evaluation["test"]   # dict[str, value] — held-out metrics for the test split
model.metrics              # alias for .evaluation: {split: {metric: value}}
model.confusion_matrix     # dict[str, np.ndarray] — per-split confusion matrices
model.predictions          # pandas.DataFrame — per-record predictions + class probabilities
model.figures              # dict[str, bytes] — reporting-visualization PNGs, keyed by name
model.predict(X)           # np.ndarray — predicted labels for new inputs
```

## Library API

`ModelFoundry.from_recipe(...)` binds a recipe to a materialized DataRefinery instance; the verbs (`validate` / `materialize` / `status` / `inspect` / `report` / `clean` / `check`) are thin methods over that binding, co-equal with the CLI.

```python
from modelfoundry import ModelFoundry, ModelInstance

mf = ModelFoundry.from_recipe("model.yml", data=data)

report = mf.validate()              # FR-2 static checks; report.passed is a bool
instance = mf.materialize()         # train + optimize + evaluate; returns a ModelInstance

# A reloaded instance predicts identically (byte-stable round-trip):
reloaded = ModelInstance.load(instance.path)
```

`data` may be a pre-bound `DataRefineryInstance` (as above) or a path to the DataRefinery cache root, in which case the recipe's `Data:` block is resolved against it.

## CLI

```bash
modelfoundry check                              # environment + plugin health
modelfoundry validate    <recipe>               # static FR-2 recipe checks
modelfoundry materialize <recipe> [--overwrite] # train + optimize + evaluate
modelfoundry status      <recipe>               # is it materialized? show the manifest
modelfoundry report      <instance-dir>         # re-render the instance report
modelfoundry inspect     <instance-dir> --view training_curves
modelfoundry clean       --older-than 7d        # cache management
modelfoundry init        <recipe-out> --data <datarefinery-recipe>   # scaffold a recipe
```

Shared options apply to every verb: `--cache-root` / `--data-cache-root` (defaults `./models` and `./data`), `--log-level`, `--log-target` (JSON-lines operational logs), `--plugin-path`, and `-v` / `-q`.

## Notebook-substrate-neutral

The same surface works identically in a Jupyter cell, a Marimo cell, an IPython REPL, or a plain `.py` script — the `ModelInstance` returns plain `pandas` / `numpy` / PNG-`bytes` primitives, so user code imports no framework:

```python
from IPython.display import Image

mi = ModelFoundry.from_recipe("model.yml", data=data).materialize()
Image(mi.figures["training_curves"])   # render the reporting PNG
mi.predictions.head()                  # a DataFrame, renders natively in any host
```

## Choosing an accelerator

Hardware acceleration is **auto-detected** by default — the PyTorch plugin picks Metal (Apple Silicon) → CUDA → CPU in that order. To pin a specific device (e.g. for CPU-speed benchmarking on a GPU-equipped machine, or to debug a non-deterministic op), set `Training.device` in the recipe:

```yaml
Training:
  max_epochs: 10
  batch_size: 32
  device: cpu              # one of: auto (default) | cpu | cuda | mps
```

`device` participates in the recipe's canonical hash, so the same recipe run with `device: cpu` and `device: mps` materializes into two distinct `ModelInstance` cache entries — no silent cross-device collision. Use the `variants:` block to keep both side-by-side without maintaining two recipe files:

```yaml
variants:
  cpu_bench:
    Training: {device: cpu}
```

```bash
modelfoundry materialize model.yml --variant cpu_bench
```

## Documentation

- [`docs/specs/concept.md`](docs/specs/concept.md) — why the project exists
- [`docs/specs/features.md`](docs/specs/features.md) — what it does (CR / FR / UR / TR requirements)
- [`docs/specs/tech-spec.md`](docs/specs/tech-spec.md) — how it is built
- [`docs/specs/project-essentials.md`](docs/specs/project-essentials.md) — must-know invariants (cache identity, determinism, loose coupling)
- [`docs/specs/stories.md`](docs/specs/stories.md) — the implementation plan

## License

Apache-2.0. Copyright (c) 2026 Pointmatic.
