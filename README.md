# ModelFoundry

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

Compile a YAML recipe into a reproducible, framework-agnostic trained-model instance.

ModelFoundry consumes a materialized [DataRefinery](https://github.com/pointmatic/datarefinery) instance and compiles a single YAML **model recipe** into a content-addressed, atomically-promoted **ModelInstance**: the trained model, per-epoch metrics, hyperparameter-search trials, held-out evaluation, predictions, visualizations, and a manifest. The result object returns notebook-shaped primitives (`pandas.DataFrame` / `numpy.ndarray` / PNG `bytes`) and works identically inside Jupyter, Marimo, IPython, or a plain `.py` script — no framework imports in user code.

Reproducibility is a first-class concern: every stochastic source is seeded, the cache identity is computed from the recipe's **segmented** canonical form (independently-hashed `core` / `plugin` / `overlays` / `extensions` segments, so a plugin-surface change never invalidates another plugin's caches), and the same `(recipe, data, seed, overlays)` tuple materializes to a byte-identical `ModelInstance`.

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

## Swap the model — three baselines, one workflow

In ModelFoundry the **recipe is the model definition.** Changing the classification model — from a chance baseline, to a scikit-learn MLP, to a PyTorch CNN — is a declarative edit to two lines of YAML (`plugin` + `Architecture`). The Python you write to train and evaluate is *identical* across all of them:

```python
from modelfoundry import ModelFoundry

for recipe in ("recipes/cifar10_random.yml",   # chance floor — the `random` plugin
               "recipes/cifar10_mlp.yml",       # scikit-learn MLP baseline
               "recipes/cifar10_cnn.yml"):      # PyTorch simple_cnn
    mi = ModelFoundry.from_recipe(recipe, data="./data").materialize()
    print(recipe, mi.evaluation["test"]["accuracy"])
```

The three recipes share the same DataRefinery binding, `Training`, and `Evaluation` blocks — only the head changes (full annotated recipes live in [`recipes/`](recipes/)):

```yaml
# cifar10_random.yml — the chance floor
plugin: random
Architecture: {type: dummy_classifier, num_classes: 10, strategy: stratified}
Loss:      {op: cross_entropy}
Optimizer: {op: "none"}          # a chance baseline has no optimizer
# (omits Optimization + Visualizations — a fixed baseline has neither)
```

```yaml
# cifar10_mlp.yml — flattened-pixel scikit-learn MLP
plugin: sklearn
Architecture: {type: mlp_classifier, num_classes: 10, hidden_layer_sizes: [256, 128], max_iter: 50}
Loss:      {op: cross_entropy}
Optimizer: {op: adam, learning_rate: 0.001}   # drives the MLPClassifier solver
# (omits Optimization + Visualizations — the baseline plugin implements neither)
```

```yaml
# cifar10_cnn.yml — PyTorch simple_cnn
plugin: pytorch
Architecture: {type: simple_cnn, num_classes: 10, in_channels: 3}
Loss:      {op: cross_entropy}
Optimizer: {op: adamw, learning_rate: 0.001}
Training:  {max_epochs: 5, ...}   # a deliberately small base budget
```

> The `sklearn` and `random` baselines reuse the PyTorch feature path, so all three currently need the `[pytorch]` extra (`pip install ml-modelfoundry[pytorch]`).

### Capacity is latent until you scale the budget

Run all four and the result tells a bigger story than "use a CNN" (CPU, deterministic, on the 1,700-image CIFAR-10 subset):

| Model | recipe | test accuracy |
|---|---|---:|
| Random (chance) | `cifar10_random.yml` | 0.095 |
| **PyTorch CNN — 5 epochs** | `cifar10_cnn.yml` | **0.275** |
| scikit-learn MLP | `cifar10_mlp.yml` | 0.352 |
| **PyTorch CNN — 40 epochs** | `cifar10_cnn.yml --overlay well_trained` | **0.403** |

The more-expressive CNN **loses to the flattened-pixel MLP at a small training budget**, and only **overtakes it once the budget is scaled up** — the same capacity-vs-budget dynamic that separates a legacy model from a modern over-parameterized one. Scaling the budget is itself a one-line recipe change, expressed as an overlay:

```yaml
overlays:
  well_trained:
    Training: {max_epochs: 40}
```

```bash
modelfoundry materialize recipes/cifar10_cnn.yml --overlay well_trained
```

Every run is content-addressed and reproducible, so each comparison is cached and byte-stable — re-running finds the existing instance instead of recomputing.

> **This is a teaching illustration, not a benchmark.** On the 1,700-image subset the per-epoch trajectory is noisy and non-monotonic — the minimal recipes use no LR schedule or early stopping, so a single run can dip or spike between budgets (a swept study even shows `resnet20` *degrading* past its peak). The endpoint contrast above is real and reproducible, but a *robust* capacity-vs-budget crossover needs more data and a proper training regime. See [`scripts/experiments/`](scripts/experiments/) for the full sweep and that finding.

## Advanced paths — transfer learning & predictive uncertainty

Two further example recipes exercise the same recipe-as-truth workflow on richer modeling paths.

### Probabilistic — MC-dropout predictive uncertainty

[`recipes/cifar10_mc_dropout.yml`](recipes/cifar10_mc_dropout.yml) declares a stochastic-inference block. `Dropout` is kept **active at inference** and the model runs **T seeded forward passes**; their mean is the deployed prediction, and the spread across passes is per-record predictive uncertainty:

```yaml
Inference:
  mode: mc_dropout      # omit the block (or use mode: point) for single-pass point estimates
  mc_samples: 30        # T — the consumer targets 20–50
```

Uncertainty is **persisted in the materialized instance** and reads back from disk with no external config:

```python
mi = ModelFoundry.from_recipe("recipes/cifar10_mc_dropout.yml", data="./data").materialize()

mi.uncertainty                            # per-record DataFrame: [split, record_id, predictive_entropy, mc_variance]
mi.metrics["test"]["predictive_entropy"]  # mean predictive entropy per split (the reportable metric)
mi.predictions                            # pred_label/pred_proba_* are the MC means; + the uncertainty columns
```

The per-record `predictive_entropy` / `mc_variance` columns live in `evaluation/predictions.parquet`, and `ece` / `calibration_curve` are computed over the MC-aggregated means, so calibration reflects the stochastic predictor actually deployed. The recipe also pairs MC-dropout with imbalance-aware evaluation (per-class precision/recall/F1) and a train-fitted class-weighted loss. Same single-pass behavior is unchanged for any recipe that does not declare the block.

### Advanced — pretrained encoder + LoRA (transfer learning)

[`recipes/advanced_encoder_lora.yml`](recipes/advanced_encoder_lora.yml) composes a frozen pretrained image encoder, parameter-efficiently fine-tuned with a LoRA adapter: `Encoder → LoRA → Pooling → Head`. This path needs the `huggingface` extra:

```bash
pip install ml-modelfoundry[huggingface,pytorch]
```

Without it the recipe still loads and validates, but `materialize()` raises a `MaterializeError` carrying the install pointer. Two more requirements: the bound DataRefinery instance must match the encoder's **native input contract** (e.g. `vit-tiny-patch16-224` pins 224×224×3 — a pretrained backbone does not adapt to the data the way `simple_cnn` does; `validate()` fails fast on a mismatch), and the base weights load from an **offline warm HF cache** (download once with network, then reruns are reproducible with no run-time network). Only the trainable head/pooling + LoRA adapter deltas are persisted; the frozen base is re-fetched from the warm cache on load, so the instance round-trips from disk.

#### Feeding the encoder its exact normalization

A frozen pretrained encoder also expects its **exact** pretrained input statistics — and ModelFoundry applies **no** HuggingFace image-processor preprocessing (the `Encoder` op feeds `pixel_values` straight through). You supply those statistics on the **data side**, with no `Encoder`-op preprocessing and no code change: prepare the input in the **DataRefinery recipe** with a `resize` (baked into the uint8 sink) followed by a `normalize` op carrying the encoder's **fixed** mean/std — DataRefinery persists author-supplied normalize stats as-is, and ModelFoundry applies them at load over the sinked pixels (a fit-on-train op that does *not* rewrite the uint8 bytes, so resize-persistence and normalization coexist).

```yaml
# DataRefinery recipe — give the encoder its exact input distribution
Transformations:
  - {op: resize, height: 224, width: 224}   # baked → uint8 PNG sink (matches the encoder's pinned size)
  - op: normalize                            # fixed stats, applied at load by ModelFoundry
    mean: [123.675, 116.28, 103.53]          # ImageNet mean, scaled to 0-255 (see caveat)
    std:  [58.395, 57.12, 57.375]            # ImageNet std,  scaled to 0-255
```

> ⚠ **Units caveat — the easy way to get this silently wrong.** ModelFoundry applies `(x − mean) / std` on **0-255 pixel units with NO `/255` rescale** (the deliberate data-side contract). HuggingFace image processors define `image_mean` / `image_std` in **`[0,1]` units** (applied *after* a `/255` rescale). So the stats written into the DataRefinery `normalize` op must be **scaled to 0-255**: `mean₂₅₅ = image_mean × 255`, `std₂₅₅ = image_std × 255`. ModelFoundry then computes `(x₂₅₅ − image_mean·255)/(image_std·255) = (x₂₅₅/255 − image_mean)/image_std` — exactly the encoder's expected rescale-then-normalize. Writing the raw `[0,1]` HF values directly is a silent mismatch (a mean ≈ 0.5 subtracted from 0-255 pixels).

| Encoder norm | HF `[0,1]` stats | DataRefinery `normalize` op (0-255 units) |
|---|---|---|
| ImageNet | mean `[.485, .456, .406]`, std `[.229, .224, .225]` | mean `[123.675, 116.28, 103.53]`, std `[58.395, 57.12, 57.375]` |
| ViT `[-1, 1]` | mean `[.5, .5, .5]`, std `[.5, .5, .5]` | mean `[127.5, 127.5, 127.5]`, std `[127.5, 127.5, 127.5]` |

The full derivation and evidence live in [`docs/specs/consumer-gap-solutions.md`](docs/specs/consumer-gap-solutions.md) § "Gap 2".

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

Shared options apply to every verb: `--cache-root` / `--data-cache-root` (defaults `./models` and `./data`), `--log-level`, `--log-target` (JSON-lines operational logs), `--plugin-path`, `--num-workers` (DataLoader workers; execution context, env `MODELFOUNDRY_NUM_WORKERS`), and `-v` / `-q`.

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
  precision: fp32          # author-required (no implicit defaults) — fp32 | amp
  checkpoint_cadence: 1    # author-required — epochs between checkpoint writes
  device: cpu              # author-required — auto | cpu | cuda | mps ("auto" picks the best)
```

> Phase I introduced **no implicit defaults**: behavior-affecting fields like `precision` / `checkpoint_cadence` / `device` are authored in the recipe, not supplied by code — `modelfoundry init` emits them for you. DataLoader `num_workers` moved the *other* way: it is now **execution context**, set via `--num-workers` or `MODELFOUNDRY_NUM_WORKERS` (not a recipe field), since it never affects the trained bytes.

`device` participates in the recipe's canonical hash, so the same recipe run with `device: cpu` and `device: mps` materializes into two distinct `ModelInstance` cache entries — no silent cross-device collision. Use the `overlays:` block to keep both side-by-side without maintaining two recipe files:

```yaml
overlays:
  cpu_bench:
    Training: {device: cpu}
```

```bash
modelfoundry materialize model.yml --overlay cpu_bench
```

## Documentation

- [`docs/specs/concept.md`](docs/specs/concept.md) — why the project exists
- [`docs/specs/features.md`](docs/specs/features.md) — what it does (CR / FR / UR / TR requirements)
- [`docs/specs/tech-spec.md`](docs/specs/tech-spec.md) — how it is built
- [`docs/specs/project-essentials.md`](docs/specs/project-essentials.md) — must-know invariants (cache identity, determinism, loose coupling)
- [`docs/specs/stories.md`](docs/specs/stories.md) — the implementation plan

## License

Apache-2.0. Copyright (c) 2026 Pointmatic.
