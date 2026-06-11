# ModelFoundry

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

Compile a YAML recipe into a reproducible, framework-agnostic trained-model instance.

ModelFoundry consumes a materialized [DataRefinery](https://github.com/pointmatic/datarefinery) instance and compiles a single YAML **model recipe** into a content-addressed, atomically-promoted **ModelInstance**: the trained model, per-epoch metrics, hyperparameter-search trials, held-out evaluation, predictions, visualizations, and a manifest. The result object returns notebook-shaped primitives (`pandas.DataFrame` / `numpy.ndarray` / `matplotlib.figure.Figure`) and works identically inside Jupyter, Marimo, IPython, or a plain `.py` script — no framework imports in user code.

> **Status:** pre-production (`0.x.y` series). APIs, CLI surface, and cache layout may change between minor versions until the `1.0.0` production release. See [`docs/specs/`](docs/specs/) for the concept, feature, technical, and story specifications.

## Installation

```bash
pip install ml-modelfoundry[pytorch]
```

The import name and console script are both `modelfoundry`; the PyPI distribution is `ml-modelfoundry`.

## Usage

_Quickstart and the CIFAR-10 walkthrough land with the release README (Story F.a)._

Library:

```python
from datarefinery import DataRefinery
from modelfoundry import ModelFoundry

data = DataRefinery.from_recipe("data.yml").materialize()
model = ModelFoundry.from_recipe("model.yml", data=data).materialize()

model.metrics                 # pd.DataFrame indexed by epoch
model.evaluation["test"]      # dict of held-out metrics
model.confusion_matrix        # dict[str, np.ndarray]
```

CLI:

```bash
modelfoundry validate model.yml
modelfoundry materialize model.yml
```

### Choosing an accelerator

Hardware acceleration is **auto-detected** by default — the PyTorch plugin picks Metal (Apple Silicon) → CUDA → CPU in that order. To pin a specific device (e.g. for CPU-speed benchmarking on a GPU-equipped machine, or to debug a non-deterministic op), set `Training.device` in the recipe:

```yaml
Training:
  max_epochs: 10
  batch_size: 32
  device: cpu              # one of: auto (default) | cpu | cuda | mps
```

`device` participates in the recipe's canonical hash, so the same recipe run with `device: cpu` and `device: mps` materializes into two distinct `ModelInstance` cache entries — no silent cross-device collision. Use the existing `variants:` block to keep both side-by-side without maintaining two recipe files:

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
- [`docs/specs/features.md`](docs/specs/features.md) — what it does
- [`docs/specs/tech-spec.md`](docs/specs/tech-spec.md) — how it is built
- [`docs/specs/stories.md`](docs/specs/stories.md) — the implementation plan

## License

Apache-2.0. Copyright (c) 2026 Pointmatic.
