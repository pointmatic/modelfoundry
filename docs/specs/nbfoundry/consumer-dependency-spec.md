# dependency-spec.md — modelfoundry (as consumed by nbfoundry)

**Version:** 0.2 — Draft

This document defines what **nbfoundry requires from modelfoundry** — the contract between the two projects. modelfoundry does not yet exist as a library; this spec is **input** to modelfoundry's own planning chain (`plan_concept` → `plan_features` → `plan_tech_spec` → `plan_stories`), and a **contract** for that planning chain to keep — or negotiate, if a choice here turns out to be wrong.

This is the symmetric counterpart to [`docs/specs/learningfoundry/dependency-spec.md`](../learningfoundry/dependency-spec.md), which defines what learningfoundry requires from nbfoundry. The two specs together stake out the boundaries of the four-library family: **DataRefinery** owns data prep, **ModelFoundry** owns modeling mechanics, **NbFoundry** authors notebook-based exercises, **LearningFoundry** consumes those exercises.

ModelFoundry's design follows DataRefinery's shape closely on purpose. Both tools: compile a YAML **recipe** into a materialized **instance** via a deterministic, content-addressed, atomically-promoted pipeline; expose library and CLI as co-equal surfaces; honor recipe-as-truth (only execution-context flags like `--seed` override). Where DataRefinery's documents already pin a pattern (cache identity, atomic promotion, error model, plugin discovery, schema versioning), this spec points at [`docs/specs/datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) rather than re-stating it. ModelFoundry's design is **expected to mirror those choices** unless its own `plan_tech_spec` surfaces a reason to diverge.

---

## Role in nbfoundry

modelfoundry is the **modeling-mechanics abstraction**. It encapsulates model definition, training, hyperparameter search, and evaluation as framework-agnostic operations described declaratively in a YAML recipe, hiding the particulars of the underlying backend (scikit-learn, PyTorch, Keras 3, HuggingFace `transformers`/`peft`). nbfoundry's lifecycle templates (`model_experimentation`, `model_optimization`, `model_evaluation`) consume modelfoundry to drive the modeling cells inside scaffolded notebooks. The templates author calls like `mf.materialize()` against a `ModelFoundry` instance — **they never import `torch`, `tensorflow`, `keras`, or `optuna` directly.**

That separation is structural: the framework substrate (PyTorch+MPS, TF+Metal, the HuggingFace stack, Optuna) is exercised by nbfoundry's hardware-gated env-validation smokes (`tests/integration/test_e2e_*.py`) only; **production code paths in `src/nbfoundry/` and in lifecycle template notebook bodies route through modelfoundry**.

### Hypothesis driving the boundary

> ModelFoundry abstracts the underlying model particulars and focuses on the mechanics of model training, optimization, and evaluation in the abstract.

Under that hypothesis:

- **Framework substrate** (does PyTorch find MPS? does TF find the Metal device? is the HuggingFace stack importable?) is properties of the **env** nbfoundry ships. Substrate validation is nbfoundry's concern.
- **Modeling mechanics in the abstract** (define a model, train it, sweep hyperparameters, evaluate against a holdout) is framework-independent orchestration. ModelFoundry territory.
- **Data prep** (clean, normalize, split, sample, cache, persist fitted statistics) is DataRefinery's concern. ModelFoundry consumes a prepared DataRefinery instance and does no data prep itself.
- **Save / load** is a persistence machinery concern. Notebooks don't see it. ModelFoundry materializes a `ModelInstance` the same way DataRefinery materializes a data `Instance` — content-addressed, atomically promoted, cached by recipe hash.

### Integration Points

| nbfoundry surface | modelfoundry role |
|---|---|
| `model_experimentation` lifecycle template | Materialize a `ModelInstance` from a model recipe: trained model + per-epoch metrics + visualizations |
| `model_optimization` lifecycle template | Run an optimization stage inside `materialize()` — the resulting instance carries trial history and a model trained with best params |
| `model_evaluation` lifecycle template | Score a held-out split inside `materialize()` — the instance's evaluation report is a notebook-renderable artifact |
| [`_modelfoundry.py`](../../src/nbfoundry/_modelfoundry.py) (existing Protocol stub) | Runtime adapter; lazy-imports `modelfoundry` and raises a clear "modelfoundry required" error if absent |
| [`tests/unit/test_modelfoundry_adapter.py`](../../tests/unit/test_modelfoundry_adapter.py) | AST-scan invariant — the nbfoundry compiler core (`compiler.py`, `validator.py`, `schema.py`, `cli.py`) does not import `_modelfoundry`; modelfoundry is opt-in, never a hard runtime dependency for the compile/validate paths |

---

## Design Decisions

### DD-1: ModelFoundry takes a DataRefinery instance (coexist, not subsume)

The canonical notebook pattern is:

```python
from datarefinery import DataRefinery
from modelfoundry import ModelFoundry

data  = DataRefinery.from_recipe("data.yml").materialize()      # data prep is DataRefinery's job
model = ModelFoundry.from_recipe("model.yml", data=data).materialize()   # modeling is ModelFoundry's job

# Notebook cells read primitives off the materialized instance:
metrics_df = model.metrics               # pd.DataFrame indexed by epoch
print(model.evaluation["macro_f1"])      # plain float
display(model.confusion_matrix)          # np.ndarray
study_df = model.trials                  # pd.DataFrame (None if no optimization stage in recipe)
```

DataRefinery and ModelFoundry **coexist** per the Phase F plan's Coexist-vs-Subsume decision (locked). ModelFoundry never performs cleaning, splitting, sampling, tokenization, or feature engineering — those are DataRefinery primitives. ModelFoundry receives an already-materialized DataRefinery `Instance` and, when needed, binds it to a framework-specific data representation (PyTorch `DataLoader`, `tf.data.Dataset`, sklearn `X/y` arrays) internally.

### DD-2: Declarative YAML recipe, mirroring DataRefinery's shape

A ModelFoundry instance is constructed from a YAML recipe with sections analogous to DataRefinery's `Input` / `Output` / `Splits` / `Transformations` / `OutputExpectations` / `variants` family. The recipe is the single source of truth for the model build; CLI flags only affect execution context (cache root, log level, workers, plugin path, seed). Section names should match DataRefinery's intent-naming convention (capitalized, role-naming, no ML-jargon collisions).

Proposed section set (modelfoundry's own `plan_features` / `plan_tech_spec` will lock the final names and shapes):

| Section | Role |
|---|---|
| `schema_version` | Recipe schema version; loader gates on supported versions (per [`datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) `recipe.loader`) |
| `plugin` | Backend plugin name (e.g. `pytorch`, `keras`, `sklearn`, `huggingface`) |
| `seed` | Default seed; `--seed` CLI flag overrides (changes cache identity) |
| `Data` | Reference to a DataRefinery instance — `{ recipe: ../data/recipe.yml, variant: ..., seed: ... }` resolves to a cached DataRefinery instance via `cache.sibling_stats`-style lookup (see "loose vs tight coupling" below) |
| `Architecture` | Model definition: encoder / adapters / heads / layers — plugin-specific shape per `OperationSpec` |
| `Loss` | Loss function declaration (`cross_entropy`, `cross_entropy_class_weighted`, `mse`, plugin-extensible) |
| `Optimizer` | Optimizer + schedule (`adamw`, `sgd`, `reduce_on_plateau`, etc.) |
| `Training` | Epochs, batch size, early stopping, checkpointing-cadence — execution policy, not model definition |
| `Optimization` | Hyperparameter search: sampler (`tpe`, `random`, `grid`), pruner (`median`, `none`), `n_trials`, search space. **Wraps Optuna**; recipe never names Optuna directly |
| `Evaluation` | Splits to evaluate on; metrics list; calibration; comparison-baseline reference |
| `Visualizations` | Training curves, confusion matrix, calibration plot, optimization-trial plots — `mode: exploration` (on-demand) or `mode: reporting` (persisted in instance's `report/`) |
| `OutputExpectations` | Post-materialization assertions: e.g. `val_macro_f1 >= 0.6` — failure aborts with FAILED marker, mirrors DataRefinery's FR-23 |
| `variants` | Named overlays for experiments (e.g. `lora_rank_4`, `frozen_encoder`); selected at materialize time; change cache identity per FR-14 analog |

Each operation declares which **stage** it belongs to and which **splits** it applies to (train-only loss class weighting, val-only early stopping monitor, test-only evaluation), so train/inference skew has no place to hide — same discipline as DataRefinery's per-operation `stages` / `splits` declarations.

Concrete recipe example (illustrative; final shape owned by modelfoundry's `plan_features`):

```yaml
schema_version: 1
plugin: pytorch
seed: 42

Data:
  recipe: ../data/tweet_eval.yml
  variant: stratified_70_10_20
  # Resolved against modelfoundry's cache-root; cache identity binds to the
  # DataRefinery instance's recipe_hash + input_hash + seed. See FR-ARCH-1
  # in datarefinery/tech-spec.md for loose-vs-tight coupling.

Architecture:
  encoder:
    source: huggingface
    id: microsoft/deberta-v3-base
    frozen: true
  adapters:
    type: lora
    rank: 8
    alpha: 32
    dropout: 0.1
    target_modules: [query_proj, value_proj]
  heads:
    pooling: { type: attention, hidden_dim: 128 }
    classifier:
      type: mlp
      hidden_dims: [256, 128]
      dropout: 0.2
      activation: gelu
    num_classes: 3
    id2label: { 0: NEGATIVE, 1: NEUTRAL, 2: POSITIVE }

Loss:
  op: cross_entropy_class_weighted
  weight_source: train   # fit-on-train discipline

Optimizer:
  op: adamw
  learning_rate: 2e-4
  weight_decay: 0.01
  schedule:
    op: reduce_on_plateau
    monitor: val_macro_f1
    mode: max
    factor: 0.5
    patience: 2
    min_lr: 1e-6

Training:
  max_epochs: 10
  batch_size: 32
  early_stopping:
    monitor: val_macro_f1
    mode: max
    patience: 3

Optimization:
  sampler: tpe
  pruner: median
  n_trials: 20
  baseline_trial: enqueue_recipe_defaults     # enqueue the recipe's hyperparameter values as trial 0
  search_space:
    Architecture.adapters.rank:        { categorical: [4, 8, 16] }
    Architecture.adapters.alpha:       { categorical: [16, 32, 64] }
    Architecture.heads.pooling.hidden_dim: { int: [64, 256] }
    Architecture.heads.classifier.hidden_dims[0]: { int: [128, 512] }
    Architecture.heads.classifier.hidden_dims[1]: { int: [64, 256] }
    Architecture.heads.classifier.dropout: { float: [0.1, 0.5] }
    Optimizer.learning_rate:           { log_uniform: [1e-5, 1e-3] }
    Training.batch_size:               { categorical: [16, 32, 64] }

Evaluation:
  splits: [val, test]
  primary_metric: macro_f1
  metrics:
    - macro_f1
    - per_class_f1
    - per_class_precision
    - per_class_recall
    - accuracy
    - confusion_matrix
    - ece
    - calibration_curve
  comparison:
    baseline_model_id: cardiffnlp/twitter-roberta-base-sentiment-latest

Visualizations:
  - name: training_curves
    op: training_curves
    mode: reporting
  - name: optimization_history
    op: optimization_history
    mode: reporting
  - name: confusion_matrix
    op: confusion_matrix
    splits: [test]
    mode: reporting
  - name: calibration
    op: calibration_curve
    splits: [test]
    mode: reporting

OutputExpectations:
  - { metric: val_macro_f1, op: gte, value: 0.55 }

variants:
  frozen_baseline:
    Architecture: { adapters: { type: none } }
  lora_rank_16:
    Architecture: { adapters: { rank: 16, alpha: 64 } }
```

A notebook cell that consumes this is **three lines** of modelfoundry, the rest is matplotlib/pandas/numpy operations on the materialized instance's properties — no framework imports.

### DD-3: Framework backend is selected by the recipe's `plugin` field; nbfoundry sees no framework

The `plugin` field picks the backend (`pytorch`, `keras`, `sklearn`, `huggingface`). ModelFoundry's plugin model mirrors DataRefinery's — see [`datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) `plugins.base` and `plugins.discovery`. Each plugin contributes:

- **Architecture ops** — model component primitives (`Conv2d`, `Dense`, `MLP`, `Encoder`, `LoRA`, etc.)
- **Loss ops** — `cross_entropy`, `mse`, `bce_with_logits`, `cross_entropy_class_weighted`, etc.
- **Optimizer ops** — `adamw`, `sgd`, `adam`, etc. — and `Schedule` ops (`reduce_on_plateau`, `cosine`, `linear_warmup`)
- **Training procedure** — the actual loop (framework-specific implementation, framework-agnostic interface)
- **Optimization procedure** — the sampler / pruner / objective harness (today an Optuna implementation; the Protocol does not name Optuna)
- **Evaluation primitives** — metric implementations
- **Visualization primitives** — training curves, confusion matrix, calibration plot, optimization trial plots

nbfoundry templates do not see plugin internals. They author recipes against operation names and consume materialized instances. The plugin choice is invisible to the notebook body except via the recipe.

### DD-4: nbfoundry depends on the modelfoundry **Protocol**, not the library

nbfoundry ships [`src/nbfoundry/_modelfoundry.py`](../../src/nbfoundry/_modelfoundry.py) — a `@runtime_checkable` Protocol with the canonical methods and a `get_adapter()` factory that lazy-imports `modelfoundry` (or raises a clear "modelfoundry required" error). The compiler core never imports `_modelfoundry`; only lifecycle templates and notebook bodies do.

This keeps modelfoundry an **optional** dependency for nbfoundry's CLI surface (`nbfoundry init`, `compile`, `compile-exercise`, `validate` all run without it) and a **required** dependency only when learners actually execute a model-stage notebook.

When modelfoundry is published, the current permissive Protocol (`*args, **kwargs: Any`) tightens to the explicit shape this spec defines (see BR-1 onward). The current stub is **deliberately permissive** so nbfoundry's compiler-core test (`tests/unit/test_modelfoundry_adapter.py`) compiles cleanly today; the tightening is a no-op for nbfoundry's compiled code, since lifecycle templates already author calls in the shape this spec describes.

### DD-5: Materialization, not training — notebooks don't see save/load

Notebooks invoke `model.materialize()` and get a `ModelInstance`. They do not call `train()`, `save()`, or `load()`. Persistence is transparent: ModelFoundry caches materialized instances under a content-addressed path (recipe hash + DataRefinery instance hash + seed); re-running an unchanged recipe over an unchanged DataRefinery instance returns the cached `ModelInstance` unchanged. Any semantic edit invalidates and rebuilds. The mechanism mirrors DataRefinery's exactly — see [`datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) `cache.identity` and `cache.atomic`.

The `ModelInstance`'s API surface is **notebook-shaped**: `.metrics` returns a `pd.DataFrame`, `.evaluation` returns a dict of metric→value, `.confusion_matrix` returns a `np.ndarray`, `.trials` returns a `pd.DataFrame` (Optuna `study.trials_dataframe()` shape), `.predict(X)` returns predictions in notebook-native form. The notebook never sees `torch.load`, `keras.models.load_model`, `joblib.load`, `state_dict`, `optimizer.zero_grad`, or any other framework artifact. If a notebook needs to inspect raw artifacts (advanced cases), `.path: Path` exposes the on-disk instance directory — but that's an escape hatch, not the primary API.

---

## Build-Time / Library Requirements (Python API)

### BR-1: Construction API — `ModelFoundry.from_recipe(...)`

Mirrors [`datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) `DataRefinery.from_recipe`. Construction loads + validates the recipe and the bound DataRefinery instance once; verbs are methods that share that state.

```python
class ModelFoundry:
    @classmethod
    def from_recipe(
        cls,
        recipe_path: pathlib.Path,
        *,
        data: DataRefineryInstance,        # required — see DD-1
        config: RuntimeConfig | None = None,
        variant: str | None = None,
        seed: int | None = None,
    ) -> "ModelFoundry":
        """
        Construct a ModelFoundry instance bound to a materialized
        DataRefinery instance and a model recipe.

        Args:
            recipe_path: Path to the model YAML recipe.
            data: A materialized DataRefinery instance. ModelFoundry never
                  performs data prep — it queries this instance's splits
                  and schema via the DataRefinery library API.
            config: RuntimeConfig (cache root, log level, workers, plugin
                  path). Defaults applied if absent.
            variant: Optional named variant from the recipe's `variants`
                  block (FR-14 analog). Applied before canonicalization
                  so cache identity reflects the variant.
            seed: Optional override of recipe.seed. Documented ad-hoc-run
                  case; changes cache identity (per DataRefinery's
                  precedent).

        Raises:
            ModelfoundryError: malformed recipe, unsupported schema
                  version, plugin not found, DataRefinery instance
                  schema incompatible with the recipe.
        """
```

The construction validates the recipe against modelfoundry's schema, gates `schema_version` against `SUPPORTED_SCHEMA_VERSIONS`, resolves the plugin, and verifies the bound DataRefinery instance exposes the splits and label schema the recipe references — failures raise `ModelfoundryError` with a human-readable message before any framework code runs.

Top-level convenience (mirrors DataRefinery's `materialize(...)`):

```python
def materialize(
    recipe_path: pathlib.Path,
    *,
    data: DataRefineryInstance,
    config: RuntimeConfig | None = None,
    variant: str | None = None,
    seed: int | None = None,
) -> ModelInstance:
    return ModelFoundry.from_recipe(
        recipe_path, data=data, config=config, variant=variant, seed=seed
    ).materialize()
```

### BR-2: Validation — `mf.validate() → ValidationReport`

Mirrors DataRefinery's FR-2. Runs an enumerated set of static logical checks against the recipe; never short-circuits. Surfaces problems before `materialize()` does expensive work.

```python
def validate(self) -> ValidationReport: ...
```

Expected check categories (modelfoundry's `plan_features` enumerates the full list):

- Schema-version-correctness, unknown-key handling.
- Plugin existence and operation-name resolution against the plugin's `OperationSpec` set.
- Per-operation `splits` declarations are consistent (no train-only metric on test; no test-only loss; etc.).
- `fit_on_train` discipline: anything fitted (class weights, loss scaling, normalization-on-features) fits on the train split only.
- `Optimization.search_space` keys reference legitimate recipe paths (`Architecture.adapters.rank` exists in the schema).
- `Optimization` categorical hyperparameter defaults are members of the declared choice set (validates the `baseline_trial: enqueue_recipe_defaults` pattern at recipe time).
- `OutputExpectations` reference metrics that `Evaluation.metrics` produces.
- Cross-checks against the bound DataRefinery instance: label schema, num-classes consistency, split presence.

### BR-3: Materialization — `mf.materialize() → ModelInstance`

The main verb. Runs every stage declared in the recipe, in canonical order, and promotes the result atomically into the cache. Stage execution policy is identical to DataRefinery's: writes target `<cache-root>/instances/.tmp/<run-id>/`, `os.replace` to final on success, `FAILED` marker on failure (see [`datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) `cache.atomic`).

```python
def materialize(self, *, overwrite: bool = False) -> ModelInstance:
    """
    Run the recipe end-to-end. Stages execute in the canonical order:

      1. Resolve Architecture: build the model from plugin primitives.
      2. (Optional) Run Optimization stage: hyperparameter search, persist
         trial history; the best-trial hyperparameters are merged into the
         recipe before Training.
      3. Run Training stage: fit the model, persist per-epoch metrics and
         best checkpoint.
      4. Run Evaluation stage: score every split listed in
         Evaluation.splits, persist metrics + confusion matrix +
         calibration.
      5. Evaluate OutputExpectations; abort with FAILED marker if any
         assertion fails.
      6. Render Visualizations declared `mode: reporting`.
      7. Write manifest.json and atomically promote.

    Returns:
        A loaded ModelInstance bound to the promoted directory.

    Raises:
        ModelArtifactExistsError: instance directory exists and
            overwrite=False.
        ModelfoundryError: training, optimization, evaluation, or
            expectation failure.
    """
```

Cache hits are constant-time: compute cache key + `pathlib.Path.exists()` + load `manifest.json`. The notebook never knows whether the run was a hit or a miss — it just receives a `ModelInstance`.

**Per-stage cancellation**: a recipe with no `Optimization` section skips stage 2; a recipe with `Evaluation.splits: []` skips stage 4. Each section is opt-out by omission.

### BR-4: Status — `mf.status() → StatusReport`

Mirrors DataRefinery's FR-19. Summarizes an instance's lifecycle, configuration, and cache state for a downstream consumer (the lifecycle-template notebook, a CLI script, a learner trying to understand what they're looking at). Notebook-friendly: returns a structured object the template renders as a `rich` table.

```python
def status(self) -> StatusReport: ...
```

### BR-5: Inspection — `mf.inspect(view=None) → InspectionView`

Mirrors DataRefinery's FR-20. Read-only views of a materialized instance — render a single visualization on demand, dump the manifest, show the training history table. **Exploration-mode visualizations live here**; reporting-mode visualizations are persisted by `materialize()`.

```python
def inspect(self, view: str | None = None) -> InspectionView: ...
```

### BR-6: Report regeneration — `instance.render_report() → None`

Re-render `report.md` and reporting visualizations from an existing instance without re-training. Mirrors DataRefinery's FR-15 and `Instance.render_report`. Notebook callers and CI re-rendering hooks both use this.

### BR-7: ModelInstance — notebook-shaped accessors

The `ModelInstance` is the only object lifecycle-template notebooks consume. Its surface returns **NumPy / Pandas / Matplotlib primitives**, never framework-native objects. Notebooks render these directly.

```python
@dataclasses.dataclass(frozen=True)
class ModelInstance:
    path: pathlib.Path                          # the instance directory
    manifest: Manifest                          # parsed manifest.json
    recipe: ModelRecipe                         # canonicalized recipe used
    is_partial: bool                            # True when loaded from a FAILED temp dir

    # --- Notebook-shaped properties (computed lazily; cached) ---

    @property
    def metrics(self) -> pandas.DataFrame:
        """Per-epoch training history. One row per epoch. Columns include
        'epoch', 'train_loss', 'val_loss', and each metric declared in
        Evaluation.metrics. None if Training was not part of the recipe."""

    @property
    def evaluation(self) -> dict[str, float | dict[str, float]]:
        """Held-out metrics per split. Shape:
            {
              "<split_name>": {
                "macro_f1": 0.68,
                "accuracy": 0.71,
                "per_class_f1": {"NEGATIVE": ..., "NEUTRAL": ..., "POSITIVE": ...},
                ...
              },
              ...
            }
        Keys match the Evaluation.metrics list verbatim."""

    @property
    def confusion_matrix(self) -> dict[str, numpy.ndarray]:
        """Per-split confusion matrices as int ndarrays of shape
        (num_classes, num_classes). Rows = true label, cols = predicted."""

    @property
    def calibration(self) -> dict[str, pandas.DataFrame] | None:
        """Per-split calibration tables (confidence_bin, expected_accuracy,
        observed_accuracy, support). None if calibration not in
        Evaluation.metrics."""

    @property
    def trials(self) -> pandas.DataFrame | None:
        """Optimization trial history. Shape matches Optuna's
        study.trials_dataframe(): trial_number, value, state (completed/
        pruned/failed), params.<each_hp>, datetime_start, datetime_complete,
        duration. None if Optimization was not part of the recipe."""

    @property
    def best_params(self) -> dict[str, Any] | None:
        """The winning hyperparameter dict from the Optimization stage.
        None if Optimization was not part of the recipe. Same dict
        emitted as best-params.json under the instance directory for
        downstream re-application."""

    @property
    def figures(self) -> dict[str, matplotlib.figure.Figure]:
        """Lazily-loaded matplotlib Figures from the reporting-mode
        Visualizations stage. Keys match Visualizations[].name. Notebooks
        display these directly:  display(model.figures["training_curves"])."""

    # --- Inference, also notebook-shaped ---

    def predict(self, X) -> numpy.ndarray | pandas.Series:
        """Run inference on new data using the trained model. Input shape
        follows DataRefinery's record-schema convention for the bound
        instance; output is framework-agnostic (numpy/pandas).
        Notebooks never see torch.Tensor / tf.Tensor."""

    def predict_proba(self, X) -> numpy.ndarray | pandas.DataFrame:
        """Class-probability output for classification recipes. None for
        regression recipes."""

    @classmethod
    def load(cls, path: pathlib.Path) -> "ModelInstance": ...
```

`Manifest` and `ModelRecipe` are stable pydantic schemas; their shapes are the versioned dependency surface. Adding optional fields is non-breaking; removing or renaming fields is a major version bump for modelfoundry that requires a matching update on nbfoundry's side (per DataRefinery's `schema_version` discipline).

### BR-8: Instance Layout

Mirrors [`datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) "Cache layout" section. The on-disk layout is the durable interface; downstream tools (a future `modelmachine`, a CI replay harness, a notebook re-render) bind against it.

```
<cache-root>/instances/<recipe-hash16>/<data-instance-hash16>/<seed>/
├── recipe.yaml                # exact recipe used (canonicalized for the cache key)
├── manifest.json              # full hashes, plugin, plugin version, schema version, timing
├── model/                     # framework-specific weights + architecture
│   ├── architecture.json      # plugin-agnostic architecture description (so load() can rebuild)
│   ├── weights/               # framework's preferred format (state_dict, SavedModel, joblib, …)
│   └── tokenizer/             # if applicable (huggingface plugin)
├── training/
│   ├── history.parquet        # per-epoch metrics; ModelInstance.metrics reads this
│   └── checkpoints/           # per-epoch checkpoints (configurable retention)
├── optimization/              # present only if recipe had an Optimization section
│   ├── trials.parquet         # Optuna study.trials_dataframe() shape
│   ├── study.db               # backend's persistent study (today SQLite; opaque to nbfoundry)
│   └── best-params.json       # winning hyperparameter dict
├── evaluation/
│   ├── metrics.json           # keyed by split → metric → value
│   ├── confusion_matrix.npz   # per-split int arrays
│   └── calibration.parquet    # if calibration_curve in Evaluation.metrics
└── report/
    ├── report.md              # human-readable summary
    └── visualizations/        # reporting-mode PNGs
```

**Architecture must round-trip.** A common failure mode in the sentiment-poc precedent was checkpoints that omitted hyperparameter dimensions (pooling hidden_dim, MLP widths), making the saved weights unloadable without the original training-config object. modelfoundry's persistence MUST write the **full Architecture block** of the canonical recipe into `model/architecture.json` so `ModelInstance.load()` can rebuild from disk alone, without the caller passing any config object. nbfoundry's templates assume this guarantee.

### BR-9: DataRefinery binding — loose-coupling default

Following DataRefinery's loose-coupling pattern for sibling-instance imports (see [`datarefinery/tech-spec.md`](../datarefinery/tech-spec.md) "Caching" / FR-ARCH-1), the consuming model recipe's cache identity does **not** mix in the bound DataRefinery instance's `recipe_hash`. Re-materializing upstream (DataRefinery) does not auto-invalidate downstream (ModelFoundry); the user re-materializes ModelFoundry explicitly.

The loose-coupling choice matches DataRefinery's reasoning: small-scale single-author workflows, failure mode (stale model after data re-prep) detectable by inspection. Tight coupling — upstream `recipe_hash` participates in the consuming recipe's cache identity — is a planned upgrade for multi-team and longitudinal workflows; it will be a `schema_version` bump.

ModelFoundry surfaces the resolved DataRefinery instance path in the manifest so `inspect()` / `status()` can show the lineage.

### BR-10: Error Contract

modelfoundry errors must be catchable as `modelfoundry.ModelfoundryError` (base) and carry:

- **message**: human-readable description.
- **recipe_path**: path to the recipe that failed (if applicable).
- **stage**: one of `"load"`, `"validate"`, `"architecture"`, `"optimization"`, `"training"`, `"evaluation"`, `"output_expectations"`, `"visualization"`, `"manifest"`, `"promote"`.
- **detail**: structured detail (the offending recipe key, the trial number, the epoch, the failing expectation).

The exception hierarchy mirrors DataRefinery's:

```
ModelfoundryError                    # base
├── RecipeError                      # load/parse/schema-version failures
├── ValidationError                  # validate() check failures
├── PluginError                      # plugin discovery, duplicate names, missing extras
├── DataBindingError                 # bound DataRefinery instance incompatible with recipe
├── MaterializeError                 # stage failures, atomic-promote failures
├── ModelArtifactExistsError         # instance directory exists; overwrite=False
├── OptimizationError                # optimization study cannot be created, resumed, or completed
├── ExpectationError                 # OutputExpectations failure
└── CacheError                       # cache key, layout, clean problems
```

CLI exit codes follow DataRefinery's mapping: `0` success, `1` user/recipe/contract error, `2` system/plugin error, `130` SIGINT.

### BR-11: Reproducibility

Every entry point seeds all sources of stochasticity (framework RNGs, data shuffling, weight initialization, dropout, Optuna sampler). Same `(recipe, data_instance, seed, variant)` tuple produces a byte-identical `ModelInstance` directory (excluding `manifest.created_at` and `manifest.elapsed_seconds`, which are timestamps).

The reproducibility contract mirrors DataRefinery's. Determinism tests re-run a fixture recipe twice and assert byte-identical instance contents.

### BR-12: Logging and Progress

Two output channels, strictly separated, matching DataRefinery's "Logging" section:

- **`rich` — user-facing output.** Per-epoch tables, per-trial progress bars, cache-hit/miss line, final "model materialized at …" message. Goes to stdout for a human reading the terminal.
- **stdlib `logging` — operational output.** Stage starts/ends, op-ids, warnings, error context, timing. Emitted as JSON lines via `modelfoundry.logging.JsonFormatter` to `--log-target`.

Library callers (lifecycle templates) get a logger named `modelfoundry`; modelfoundry never hijacks the root logger. Progress is opt-in via the `progress: bool` argument; suppressed inside Optuna trials > 0 (per the sentiment-poc precedent's tuning-noise suppression — file-descriptor-level redirect for backends that write directly to fd 1/2, not just `sys.stdout`).

---

## Stub Behavior (current `_modelfoundry.py`) and Migration to Real

nbfoundry ships [`src/nbfoundry/_modelfoundry.py`](../../src/nbfoundry/_modelfoundry.py):

```python
@runtime_checkable
class ModelfoundryAdapter(Protocol):
    def prepare_data(self, *args: Any, **kwargs: Any) -> Any: ...
    def train(self, *args: Any, **kwargs: Any) -> Any: ...
    def optimize(self, *args: Any, **kwargs: Any) -> Any: ...
    def evaluate(self, *args: Any, **kwargs: Any) -> Any: ...


def get_adapter() -> ModelfoundryAdapter:
    try:
        import modelfoundry
    except ImportError as e:
        raise RuntimeError(
            "modelfoundry is required for this feature but is not installed."
        ) from e
    return modelfoundry
```

Three things change when this spec is honored by a real modelfoundry release:

1. **The Protocol shape changes substantially.** `prepare_data` / `train` / `optimize` / `evaluate` as top-level methods **disappear** — under DD-5, those are stages of `materialize()`, not callable verbs. The tightened Protocol declares: `from_recipe`, `validate`, `materialize`, `status`, `inspect`, plus the `ModelInstance` result-object surface in BR-7.
2. **`get_adapter()` returns a *class*, not the module.** Callers instantiate it via `from_recipe(...)`. The current "return the module" sentinel is a placeholder that the permissive `*args, **kwargs` makes type-safe-enough today.
3. **The Protocol type-checks against modelfoundry's public surface under `mypy --strict`.** The current permissive shape compiles cleanly but provides no static guarantee; the tightened shape makes the dependency contract enforceable in CI.

Because the current Protocol is permissive and lifecycle templates **already** author calls in the shape this spec describes (no template body calls `mf.train(...)` directly today; they're stubbed out pending modelfoundry's existence), the tightening is a no-op for nbfoundry's compiled code. The migration is a single PR: update [`_modelfoundry.py`](../../src/nbfoundry/_modelfoundry.py), bump the `[modelfoundry]` extra in `pyproject.toml`, and remove the "stubbed pending modelfoundry" placeholder from the lifecycle templates.

---

## Package Distribution

| Concern | Value |
|---|---|
| **Python package** | `modelfoundry` on PyPI (not yet published). Following DataRefinery's `ml-datarefinery` precedent, the PyPI distribution name will likely be `ml-modelfoundry` if `modelfoundry` is taken; the import name and console script remain `modelfoundry`. modelfoundry's own `plan_tech_spec` confirms. |
| **nbfoundry dependency** | Optional. nbfoundry's CLI surface runs without it; lifecycle-template notebooks fail at runtime if a learner tries to execute a model cell without modelfoundry installed. Documented as `pip install nbfoundry[modelfoundry]` once the contract lands. |
| **Env-level availability** | The Phase F refresh of [`templates/environment.yml`](../../src/nbfoundry/templates/environment.yml) ships the full framework substrate (PyTorch+MPS, TF+Metal, the HuggingFace stack, Optuna) so modelfoundry — running inside the same env — has every backend available. Adding `modelfoundry` itself to the env is deferred until the package exists on PyPI. |
| **DataRefinery coupling** | modelfoundry depends on `ml-datarefinery`'s library API (the `Instance` shape and the `DataRefinery` class). nbfoundry sees DataRefinery only indirectly — via the instance the template author passes to ModelFoundry. |
| **Optional extras** | `[corruptions]`-style extras may apply for backend-specific runtime deps (e.g. accelerator-specific wheels); modelfoundry's `plan_tech_spec` decides the final extras list. nbfoundry does not see extras directly. |

---

## Versioning and Compatibility

- **Recipe `schema_version`** is the primary versioning surface — mirrors DataRefinery's discipline. Loader gates on `SUPPORTED_SCHEMA_VERSIONS`; unknown versions are rejected with a documented migration path. Pre-production, schema 1 may be redefined; post-production, each version is immutable with migrations between adjacent versions.
- **Manifest `schema_version`** is a separate counter for the manifest format itself.
- **`ModelInstance` API shape** (BR-7) is part of the dependency contract: adding optional properties is non-breaking, removing or renaming requires a major bump and a matching nbfoundry update.
- **DataRefinery binding shape** is loose-coupled in v1 (BR-9). Tightening to bind sibling `recipe_hash` into cache identity is a future `schema_version` bump.

---

## Testing Contract

| Test | Owner | What is tested |
|---|---|---|
| Compiler core does not import `_modelfoundry` | nbfoundry | AST-scan unit test ([existing](../../tests/unit/test_modelfoundry_adapter.py)) — guards the optional-dependency invariant |
| `get_adapter()` raises a clear error when modelfoundry is absent | nbfoundry | Existing test in the same file |
| `ModelfoundryAdapter` Protocol resolves at type-check time (mypy `--strict`) against the real modelfoundry package | nbfoundry | Future integration test once modelfoundry is published |
| `from_recipe` rejects a malformed recipe with `RecipeError` | modelfoundry | modelfoundry unit test |
| `validate` returns a non-short-circuiting report | modelfoundry | modelfoundry unit test |
| `materialize` reproducibility: same `(recipe, data_instance, seed, variant)` → byte-identical `ModelInstance` directory | modelfoundry | modelfoundry integration test |
| `materialize` atomic-promote: forced failure at every stage leaves a FAILED-marked temp directory; cache never sees partials | modelfoundry | modelfoundry integration test |
| `ModelInstance.metrics` returns a `pandas.DataFrame` whose columns include each metric in `Evaluation.metrics` | modelfoundry | modelfoundry integration test |
| `ModelInstance.trials` returns a DataFrame matching Optuna's `study.trials_dataframe()` shape; `None` when no Optimization stage | modelfoundry | modelfoundry integration test |
| `model/architecture.json` round-trips: `ModelInstance.load(path).predict(X)` succeeds without the original config object | modelfoundry | modelfoundry integration test (sentiment-poc regression precedent — must not recur) |
| Loose-coupling guarantee: re-materializing DataRefinery upstream does **not** invalidate the cached ModelFoundry instance | modelfoundry | modelfoundry integration test (FR-ARCH-1 analog) |
| nbfoundry's `model_experimentation` template scaffolds to a notebook that runs end-to-end against a mock modelfoundry adapter (no live modelfoundry install) | nbfoundry | Future hardware-gated smoke under `tests/integration/test_e2e_template_*.py` (Phase F template smokes F.h–F.j) |
| Lifecycle-template notebook bodies do not import `torch`, `tensorflow`, `keras`, `optuna`, or `peft` | nbfoundry | Future AST-scan over `src/nbfoundry/templates/**/notebook.py` |

---

## Open Questions (carried into modelfoundry's plan_concept)

1. **DataRefinery binding semantics.** Does `ModelFoundry.from_recipe(data=...)` take a `DataRefinery` (lazy: materializes on demand) or a `DataRefinery.Instance` (eager: must already be materialized)? Recommend the latter — strict materialization order between the two libraries, simpler to reason about — but modelfoundry's `plan_concept` should pick deliberately.
2. **Optimization-then-Training composition.** The recipe declares Optimization and Training. After Optimization picks best params, does Training run with those params automatically, or does the user re-materialize with an explicit variant? The sentiment-poc precedent (Story H.l) auto-applies `best_params` from `tuning-report.json` at train time. Recommend matching that behavior for `materialize()`'s default path.
3. **Per-backend smoke ownership.** nbfoundry's Phase F per-tool hardware smokes (F.c TF / F.d PyTorch / F.e Keras / F.f HuggingFace) exercise framework primitives directly to validate the **env**. The analog at modelfoundry's layer would be smokes that exercise each backend **through** modelfoundry — `materialize()` against a `plugin: pytorch` recipe, against `plugin: keras`, against `plugin: sklearn`, etc. Those smokes belong in modelfoundry's repo. nbfoundry's env-validation smokes stay valid as substrate checks even after modelfoundry lands.
4. **CLI verb inventory.** Mirrors DataRefinery's: `init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`. modelfoundry's `plan_features` confirms; nbfoundry does not consume modelfoundry's CLI directly, but a learner running a lifecycle-template notebook benefits from a familiar verb set.
5. **Plugin extras and accelerator wheels.** Backend plugins may need optional extras for accelerator-specific wheels (CUDA-only PyTorch index URL, Apple Silicon TF distribution, etc.). modelfoundry's `plan_tech_spec` decides the extras shape. nbfoundry's `templates/environment.yml` already pins these at the env layer, so modelfoundry should be able to assume the env is wired correctly — extras are for stand-alone modelfoundry users without nbfoundry's env.
6. **Notebook-primitive boundary.** This spec commits `ModelInstance.metrics` → `pd.DataFrame`, `.confusion_matrix` → `np.ndarray`, `.figures` → `matplotlib.figure.Figure`. modelfoundry's `plan_concept` may want to add `.predictions` → `np.ndarray` (for downstream tools like a future `modelmetrics` to consume), or to split `.predict()` into `.predict()` + `.predict_proba()` (matches sklearn convention). Worth pinning before publishing v1.
7. **`models/` cache root, or shared with DataRefinery under `data/`?** DataRefinery defaults to `./data/` as cache root; sentiment-poc precedent uses `./models/bespoke/`. Recommend modelfoundry default to `./models/` for clarity, with full override via `--cache-root` and `MODELFOUNDRY_CACHE_ROOT`. Final naming owned by modelfoundry's `plan_concept`.

---

*Document version: 0.2 — Draft*

---

This v0.2 is a substantial revision of v0.1. The shape changes that came out of conversation:

- **Notebooks invoke `materialize()`, not `train()` / `save()` / `load()`.** The `ModelInstance` is the contract surface. Persistence is transparent and content-addressed, matching DataRefinery exactly (DD-5, BR-7, BR-8).
- **Result objects return notebook primitives.** `pd.DataFrame` / `np.ndarray` / `matplotlib.Figure` rather than opaque dataclasses. Notebook cells render directly without unpacking (BR-7).
- **Recipe-as-truth follows DataRefinery's shape closely** (DD-2, with full section list and a concrete recipe.yaml example).
- **The whole BR-2..BR-5 of v0.1 (train/probe/optimize/evaluate as top-level methods) collapsed into stages of `materialize()`** (BR-3).
- **Stub-tightening migration described concretely** — the current `_modelfoundry.py` Protocol's permissive `*args, **kwargs` accommodates the change without breaking the compiler-core AST-scan test.
- **Open questions list refreshed** to reflect what modelfoundry's `plan_concept` should pin (DataRefinery binding semantics, optimization→training composition, per-backend smoke ownership, CLI verb names, plugin extras, notebook-primitive boundary, cache-root default).

Pointers where this spec defers to DataRefinery's already-written tech-spec rather than re-stating shared patterns: cache identity, atomic promote, schema versioning, plugin discovery, error hierarchy, logging channels, CLI exit codes. modelfoundry's own `plan_tech_spec` is free to diverge — but a divergence should be deliberate, not accidental.
