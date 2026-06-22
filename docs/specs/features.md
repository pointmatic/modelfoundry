# features.md -- ModelFoundry (Python 3.12.x)

This document defines **what** the `ModelFoundry` project does -- requirements, inputs, outputs, behavior -- without specifying **how** it is implemented. This is the source of truth for scope.

For a high-level concept (why), see [`concept.md`](concept.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For project-specific must-know facts that future LLMs need to avoid blunders, see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

For the upstream contract ModelFoundry consumes (DataRefinery as vendor), see [`datarefinery/vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md). For the downstream contract ModelFoundry honors when consumed indirectly through nbfoundry lifecycle templates, see [`nbfoundry/consumer-dependency-spec.md`](nbfoundry/consumer-dependency-spec.md).

---

## Project Goal

ModelFoundry compiles a single YAML **model recipe** — declaring `plugin`, `Data` binding (to a materialized DataRefinery instance), `Architecture`, `Loss`, `Optimizer`, `Training`, `Optimization`, `Evaluation`, `Visualizations`, `OutputExpectations`, and `variants` — into a materialized **ModelInstance**: the recipe itself, the trained model (weights + a round-trippable `architecture.json`), per-epoch training history, hyperparameter-search trial history, held-out evaluation metrics, persisted per-record predictions, reporting visualizations, and a manifest, atomically promoted into a content-addressed cache. A category-specific **plugin** contributes the operations relevant to its backend; the pre-production release ships a PyTorch plugin scoped to image classification at CIFAR-10 scale, with a sklearn stub plugin sketched against the same `OperationSpec` set to keep abstractions honest (Keras and HuggingFace plugins are close follow-ons but not pre-production deliverables). ModelFoundry never performs data prep — splitting, cleaning, sampling, tokenization, and feature engineering are DataRefinery's responsibility. ModelFoundry is exposed as co-equal Python library and CLI surfaces, stays notebook-substrate-neutral (works identically inside Jupyter, Marimo, IPython, nbfoundry, or a plain `.py` script), runs fully offline by default, and treats reproducibility as a first-class concern: every stochastic source is seeded, the cache identity is computed from the recipe's normalized semantic form, and the `ModelInstance` API returns notebook-shaped primitives (`pandas.DataFrame`, `numpy.ndarray`, PNG `bytes`).

### Core Requirements

- **CR-1: Production release distinction.** Production release marks a transition where pre-production requirements are relaxed. Production release is a declared event, not a version number; the pre-production release is squarely pre-production by declaration. The pre-production release ships CI/CD and PyPI publishing but explicitly does not include GitHub branch protection, post-prod stability guarantees, or post-prod cache migration tooling.
- **CR-2: Recipe-driven training, optimization, and evaluation.** A single YAML recipe declares the entire model build; the recipe is the only canonical artifact describing what `materialize()` does.
- **CR-3: Materialized ModelInstance.** Each successful `materialize()` run produces a ModelInstance composed of (recipe, trained model + `architecture.json`, training history, optimization trials, held-out evaluation metrics + predictions, reporting visualizations, manifest). All components are required for the instance to be considered complete.
- **CR-4: Schema-versioned recipes.** Each recipe declares a `schema_version` — the **umbrella** (combination-function) version (Phase I). ModelFoundry refuses to load a recipe whose umbrella version it does not recognize. Identity also tracks **per-segment versions** (`core` / `plugin` / `overlays` / `extensions`) in code (`recipe/versioning.py`), with a migration registry keyed by `(segment, from, to)` — **empty pre-1.0**. Pre-production, version 1 may be redefined as design evolves with no migration path; post-production, versions are immutable and documented migrations ship with the tool.
- **CR-5: Determinism.** Same `(recipe, data_instance, seed, variant)` tuple produces a byte-identical ModelInstance (excluding wall-clock fields), subject to the plugin-documented determinism caveats in QR-3.
- **CR-6: Semantic cache identity.** Cache identity is derived from the recipe's normalized semantic form (parsed, key-sorted, comments stripped) plus the bound DataRefinery instance hash plus seed. Cosmetic edits do not trigger rebuilds; semantic edits do.
- **CR-7: Atomic materialization.** Pipeline writes target a temp location and atomically promote on success. On failure the temp directory is left in place with a `FAILED` marker. Partial ModelInstances never appear in the cache.
- **CR-8: Coexist-with-DataRefinery boundary.** ModelFoundry consumes a materialized DataRefinery `Instance` and never performs data prep itself. The `Data:` recipe block is a binding, not a pipeline.
- **CR-9: Plugin model.** A plugin specializes ModelFoundry for a single backend and contributes the operations its `Architecture` / `Loss` / `Optimizer` / `Training` / `Optimization` / `Evaluation` / `Visualizations` sections expose. The pre-production release ships an end-to-end PyTorch plugin (image classification, CIFAR-10-scale baseline architectures) plus a sklearn stub plugin (recipe section list + `OperationSpec` outline only; no working ops).
- **CR-10: Co-equal surfaces.** Python library API and CLI cover the same capabilities; neither grows operations the other lacks.
- **CR-11: Notebook-substrate neutrality.** The `ModelInstance` API returns framework-agnostic primitives (`pandas.DataFrame`, `numpy.ndarray`, PNG `bytes`) and notebook-native `.predict()` / `.predict_proba()`. The same surface works identically inside Jupyter, Marimo, IPython, nbfoundry lifecycle templates, and plain `.py` scripts — no substrate-specific adapter, no `display()` shim, no kernel coupling.
- **CR-12: Variants.** A recipe may declare named variants overlaying any section. A new ModelInstance is materialized per variant; the variant overlay participates in cache identity. Recipe inheritance is out of scope for the pre-production release.
- **CR-13: Offline operability.** The deterministic training path (validate, materialize, report, inspect) works with no network access (modulo HuggingFace pretrained weights served from a warm local cache). LLM enhancement of `init` is strictly opt-in.
- **CR-14: Round-trippable architecture.** The trained model persists `model/architecture.json` alongside weights. `ModelInstance.load(path).predict(X)` rebuilds the model from disk alone without any external config object.
- **CR-15: Loose-coupled DataRefinery binding.** The bound DataRefinery instance's `recipe_hash` does NOT participate in the consuming ModelFoundry recipe's cache identity. Re-materializing upstream does NOT auto-invalidate downstream; the user re-materializes ModelFoundry explicitly. Tight coupling is a deferred upgrade tracked under FR-26 and requires a `schema_version` bump.
- **CR-16: CIFAR-10 end-to-end deliverable.** The pre-production release ships a runnable end-to-end CIFAR-10 image-classification fixture (DataRefinery image-classification recipe + ModelFoundry PyTorch recipe + a CI-runnable smoke that materializes the chain) as the most rigorous exercise of every contract surface.

### Operational Requirements

- **OR-1: CLI verbs.** Lifecycle and pipeline verbs are: `init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`. Each verb has a library equivalent.
- **OR-2: Rich-based CLI ergonomics.** Per-epoch tables, per-trial progress bars, cache hit/miss summary, color-aware output via `rich`. Output degrades cleanly in non-TTY contexts.
- **OR-3: Diagnostic failures.** Failed materialization preserves the temp directory with a clear marker naming the failing stage, error class, and message. Failed validation produces structured, actionable error messages naming the offending section and field.
- **OR-4: Logging channels.** Two strictly separated channels: `rich` user-facing output on stdout (epoch tables, trial progress, final summary) and stdlib `logging` operational output as JSON lines via `modelfoundry.logging.JsonFormatter` to a configurable `--log-target`. Library callers get a logger named `modelfoundry`; ModelFoundry never hijacks the root logger.
- **OR-5: Configuration precedence.** Recipe file → CLI flags → environment variables. The recipe is authoritative for model-build semantics; CLI flags and env vars only control execution context (cache root, log level, seed override for ad-hoc runs, plugin search path, variant selection).
- **OR-6: Cache management.** A predictable on-disk layout under a configurable root (default `./models/`); `clean` operates on cache entries by recipe hash, age, or `FAILED` marker.
- **OR-7: Plugin discovery.** Plugins are discovered via `pyproject.toml` entry points; a plugin search path may be extended via configuration for development.
- **OR-8: API and CLI surface stability.** Pre-production, the library API, CLI verb names, and flag names may change without migration shims; deprecation aliases are best-effort. Post-production, the public surface follows semver-style stability with documented deprecations.
- **OR-9: Cache layout stability.** Pre-production, a ModelFoundry upgrade may invalidate all existing cached ModelInstances; users re-materialize. Post-production, the cache layout is versioned and old instances remain readable, or `clean --upgrade` provides a documented migration path.
- **OR-10: Materialize concurrency.** Pre-production, `materialize` is serialized: running two materializations against the same cache root concurrently is unsupported. Post-production, a file-lock-based concurrency protocol coordinates concurrent runs.
- **OR-11: PyPI distribution.** Published to PyPI as `ml-modelfoundry`. The import name and console script are both `modelfoundry`; the install command (`pip install ml-modelfoundry`) is the only place users see the prefixed name. Matches the `ml-datarefinery` precedent.
- **OR-12: CI/CD.** A CI pipeline runs lint (`ruff`), type-check (`mypy --strict`), unit + integration tests (`pyve test`), and the CIFAR-10 smoke fixture on every PR. A release pipeline publishes to PyPI on tagged commits. GitHub branch protection is explicitly out of scope for the pre-production release.

### Quality Requirements

- **QR-1: Reproducibility guarantee.** A successful run is byte-identical when re-executed against the same `(recipe, data_instance, seed, variant)` tuple, subject to the plugin-declared determinism caveats below.
- **QR-2: Minimal runtime dependencies.** The pre-production base depends on `numpy`, `pandas`, `pyarrow`, `pyyaml`, `rich`, `matplotlib`, `scikit-learn` (for sklearn stub + metric implementations shared across plugins), `optuna`, and `pydantic`. Plugins declare their own deps via optional extras: `[pytorch]` (`torch`, `torchvision`, `torchmetrics`), `[sklearn]` (already in base), `[huggingface]` (`transformers`, `peft`, `evaluate`) — deferred, `[keras]` (`tensorflow`, `keras`) — deferred. Optional `[llm]` (`lmentry`) extra enables the `init` scaffolder's LLM-enhancement layer.
- **QR-3: Determinism caveats.** The reproducibility guarantee applies when the plugin enables deterministic-algorithm mode and serial trial execution. Specifically, the PyTorch plugin:
  - sets `torch.use_deterministic_algorithms(True)` and `CUBLAS_WORKSPACE_CONFIG=:4096:8` by default (trade-off: slower training; a few ops hard-error rather than silently fall back to non-deterministic kernels);
  - passes a deterministic `worker_init_fn` + `generator` to every `DataLoader` so worker count does not affect output bytes;
  - forbids `n_jobs > 1` in the `Optimization` stage (the pre-production release is `n_jobs=1` only) so trial order is deterministic;
  - disables mixed-precision (AMP) by default; recipes that enable AMP relax the byte-identity guarantee to **metric-equivalent within a documented tolerance** (CR-5 marks this as plugin-documented).
  Each plugin documents its backend-specific determinism caveats in its plugin docs.
- **QR-4: Cross-platform.** Pre-production, macOS (Apple Silicon) is the first-class platform; Linux is best-effort. Post-production, both are first-class. Native Windows is best-effort in any release (CI smoke only); Windows users are not left behind because WSL2 provides the full Linux path on the same hardware, and the project documents WSL2 as the recommended Windows experience.
- **QR-5: Hardware acceleration.** Metal (Apple Silicon) is the top-priority acceleration target. CUDA is supported as available. CPU always functional. `check` reports acceleration availability without requiring it. Recipes may declare `Training.device: Literal["auto", "cpu", "cuda", "mps"] = "auto"` — `"auto"` picks the best available accelerator; explicit values force the chosen device and are validated against the plugin's `health_check`-reported availability (FR-2 check 20). The field drives every model-execution stage (Training, the inner trainings of Optuna Optimization, Evaluation, `predict` / `predict_proba`); eval and inference inherit. Distinct `device` values produce distinct canonical recipe bytes, so a CPU-benchmark run and a GPU run materialize into separate `ModelInstance` cache entries by design.
- **QR-6: Type discipline.** `mypy --strict` clean across the package and plugin sources.
- **QR-7: Lint and format discipline.** `ruff` (lint and format) clean.
- **QR-8: Test coverage.** Coverage on core invariants (recipe loader, schema-version gate, cache identity computation, plugin interface, atomic promote/rollback, architecture round-trip, determinism contract) ≥ 95% in any release. Pre-production, the project-wide 85% line-coverage gate is relaxed; every FR must be exercised by at least a smoke test, but no overall percentage threshold applies. Post-production, overall line coverage ≥ 85%.

### Usability Requirements

- **UR-1: Direct Python consumer.** A practitioner can write `from modelfoundry import ModelFoundry; mf = ModelFoundry.from_recipe(path, data=di); mi = mf.materialize()` against a materialized DataRefinery instance and consume `mi.metrics`, `mi.evaluation`, `mi.confusion_matrix`, `mi.predictions`, `mi.figures` without touching any framework-specific library.
- **UR-2: Notebook-substrate-neutral consumer.** The same three-line surface above works identically inside a Jupyter cell, a Marimo cell, an IPython REPL, and a plain `.py` script. Notebook cells render the result accessors directly (e.g. `IPython.display.Image(mi.figures["training_curves"])`, `mi.predictions.head()`).
- **UR-3: nbfoundry indirect consumer.** nbfoundry's `model_experimentation`, `model_optimization`, and `model_evaluation` lifecycle templates consume ModelFoundry through the `ModelfoundryAdapter` Protocol declared in nbfoundry's consumer-dependency-spec. The pre-production release honors the full BR-1..BR-12 contract — tightening nbfoundry's permissive Protocol stub is a no-op for compiled notebook code.
- **UR-4: Recipe legibility.** Section names (`Architecture`, `Loss`, `Optimizer`, `Training`, `Optimization`, `Evaluation`, `Visualizations`, `OutputExpectations`, `variants`) describe intent without leaking framework or ML-jargon collisions. The recipe never names `torch`, `optuna`, `keras`, or other libraries.
- **UR-5: Discoverable installation.** End users install ModelFoundry via `pip install ml-modelfoundry[pytorch]` from a clean Python 3.12 venv with no extra configuration; the `[pytorch]` extra brings in the pre-production default plugin's deps. Sentence-zero installation works on the documented platforms (QR-4).
- **UR-6: CIFAR-10 quickstart.** A new user follows the documented CIFAR-10 quickstart and produces a trained `ModelInstance` end-to-end (DataRefinery → ModelFoundry) on Apple Silicon without manual workarounds.

### Non-goals

- **NG-1: No data prep, splitting, sampling, cleaning, tokenization, or feature engineering.** DataRefinery owns that surface; ModelFoundry's `Data:` block is a binding, not a pipeline.
- **NG-2: No notebook generation, no notebook lifecycle templates, no embeddable exercise compilation.** Owned by nbfoundry.
- **NG-3: No curriculum scaffolding, learner-facing UI, or grading.** Owned by learningfoundry.
- **NG-4: No production inference-serving infrastructure beyond `ModelInstance.predict()`.** Batch scoring at scale, drift detection, and serving harnesses belong to a future `modelmachine` / `datamachine`.
- **NG-5: No backends beyond PyTorch end-to-end + sklearn stub in the pre-production release.** Keras and HuggingFace plugins are close follow-on cycles, not pre-production deliverables.
- **NG-6: No regression-task support in the pre-production release.** The pre-production PyTorch plugin scopes to classification only; the regression-task surface is plugin-extensible but not a pre-production deliverable.
- **NG-7: No model architectures beyond CIFAR-10-scale image classification in the pre-production release.** The pre-production release ships baseline CNN primitives (and an optional pretrained-encoder + LoRA path) sufficient for CIFAR-10; larger-scale architectures, detection, segmentation, generative models are out of scope.
- **NG-8: No resume-from-stage during materialization.** Atomic temp-then-promote is the pre-production failure model (matches DataRefinery).
- **NG-9: No recipe inheritance or multi-file recipe composition.** Variants suffice for the pre-production release.
- **NG-10: No tight-coupled DataRefinery binding in the pre-production release.** Bound `data_instance.recipe_hash` participating in the consuming recipe's cache identity is a future `schema_version` bump.
- **NG-11: No hard LLM dependency.** ModelFoundry must work fully offline; LLM enhancement of `init` is optional.
- **NG-12: No notebook-substrate-specific integration.** No Marimo reactivity hooks, no Jupyter magics, no IPython display hijacking. ModelFoundry stays substrate-neutral; substrate-specific affordances are the consumer's concern.
- **NG-13: No distributed training, multi-node orchestration, or accelerator-pool management.** Single-host execution against the env's accelerator only.
- **NG-14: No GitHub branch protection or post-prod stability ceremony in the pre-production release.** The pre-production series is pre-production by declaration.
- **NG-15: No parallel Optuna trials in the pre-production release.** `n_jobs=1` only (see QR-3).
- **NG-16: No hard performance targets.** The pre-production release does not commit to throughput, latency, or memory targets; performance work happens reactively in response to observed problems on representative workloads.

---

## Inputs

**Model recipe** (single YAML file):

- `schema_version` (top-level, integer).
- `plugin` (top-level string — pre-production-supported: `pytorch`; sklearn stub registered but no working ops).
- `seed` (top-level integer; overridable by `--seed` for ad-hoc runs; participates in cache identity).
- `Data` block — binds the recipe to a materialized DataRefinery instance:
  ```yaml
  Data:
    recipe: <filesystem path to the DataRefinery recipe YAML>
    variant: <optional variant name selected at the DataRefinery side>
    seed: <optional DataRefinery seed override>
  ```
  The block resolves to a `DataRefineryInstance` by computing DataRefinery's canonical recipe hash + input hash + seed and locating the promoted instance under the DataRefinery cache root. The instance must already be materialized — eager binding (concept Open Question 1, locked).
- `Architecture` block — plugin-specific model definition. For `plugin: pytorch` in the pre-production release, the block describes a baseline CNN (Conv2d / BatchNorm2d / ReLU / MaxPool2d / Linear / Dropout primitives) sufficient for CIFAR-10; an optional pretrained-encoder + LoRA + classification-head path is supported but not the default demo shape.
- `Loss` block — `op: cross_entropy | cross_entropy_class_weighted | bce_with_logits | ...` plus op-specific params (e.g. `weight_source: train` for the class-weighted variant).
- `Optimizer` block — `op: adamw | sgd | adam | ...`, op-specific params, plus an optional `schedule:` sub-block (`reduce_on_plateau`, `cosine`, `linear_warmup`).
- `Training` block — execution policy: `max_epochs`, `batch_size`, `precision` (`fp32`/`amp`), `device` (`auto`/`cpu`/`cuda`/`mps`), `checkpoint_cadence` (epochs between checkpoint writes), optional `early_stopping` (`monitor`, `mode`, `patience`). **`num_workers` is NOT a recipe field** (Phase I / Option A): it is execution context — set via `--num-workers` / `MODELFOUNDRY_NUM_WORKERS`. Per **no-implicit-defaults** (Phase I), `precision` / `device` / `checkpoint_cadence` are author-required (the scaffolder emits them); only mode-selecting optionals (`early_stopping`) may be omitted.
- `Optimization` block — optional hyperparameter search: `sampler: tpe | random | grid`, `pruner: median | none`, `n_trials: int`, `baseline_trial: enqueue_recipe_defaults` (enqueues the recipe's hyperparameter values as trial 0), `search_space:` keyed by recipe-path strings (e.g. `Optimizer.learning_rate`) with sample-spec values (`{log_uniform: [1e-5, 1e-3]}`, `{categorical: [16, 32, 64]}`, etc.).
- `Evaluation` block — `splits: list[str]`, `primary_metric: str`, `metrics: list[str]` drawn from the pre-production vocabulary (`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `accuracy`, `confusion_matrix`, `ece`, `calibration_curve`), optional `comparison.baseline_model_id`.
- `Visualizations` block — list of ops, each with `name`, `op` (`training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid`), `mode` (`exploration` or `reporting`), optional `splits`.
- `OutputExpectations` block — list of post-materialization assertions (`{metric: val_macro_f1, op: gte, value: 0.55}`); failures abort with a `FAILED` marker.
- `variants` block — optional named overlays applied at materialize time; selection changes cache identity.
- `extensions` block (Phase I / F3) — the one sanctioned relaxed island: a declarative bag where `extra` is allowed only inside the namespace (the rest of the recipe stays `extra="forbid"`). Enters cache identity only when non-empty; plugins declare consumed keys via `Plugin.extension_keys` and the validator warns (non-fatally) on unclaimed keys (FR-2 check 22). **Declarative params only — never recipe-activated code.**

**DataRefinery instance reference** — resolved through the `Data:` block above. ModelFoundry queries the bound instance's splits, label schema, num-classes, and record schema via DataRefinery's library API.

**Seed** — recipe field; `--seed` CLI flag overrides for ad-hoc runs and changes cache identity (matches DataRefinery precedent).

**Configuration** (CLI flags / environment variables, in configuration precedence order above):

- `--cache-root` / `MODELFOUNDRY_CACHE_ROOT` — root directory for cache (default `./models/`).
- `--log-level` / `MODELFOUNDRY_LOG_LEVEL` — operational log level.
- `--log-target` / `MODELFOUNDRY_LOG_TARGET` — JSON-lines log sink (file path; default stderr).
- `--plugin-path` / `MODELFOUNDRY_PLUGIN_PATH` — extra plugin discovery paths (development).
- `--variant` — selects a named variant from the recipe at materialize time.
- `--seed` — ad-hoc seed override (changes cache identity).
- `--overwrite` / `--force` — re-materialize even on cache hit (writes a new instance under the same key only by removing the existing one first; the pre-production default is to refuse and error).

## Outputs

**Materialized ModelInstance** (atomic directory under the cache root, addressed by recipe hash + DataRefinery instance hash + seed):

```
models/instances/<recipe-hash16>/<data-instance-hash16>/<seed>/
├── recipe.yaml                   # the exact recipe used (canonicalized for cache key; original preserved)
├── manifest.json                 # full hashes, plugin, plugin version, schema version, timings
├── model/
│   ├── architecture.json         # plugin-agnostic architecture description (round-trip contract)
│   ├── summary.txt               # torchinfo text render of the model (FR-27); plugin-provided
│   ├── summary.json              # structured per-layer rows + network totals (FR-27)
│   ├── weights/                  # plugin-preferred format (state_dict / SavedModel / joblib / ...)
│   └── tokenizer/                # present only when the plugin needs one (HuggingFace plugin path)
├── training/
│   ├── history.parquet           # per-epoch metrics; ModelInstance.metrics reads this
│   └── checkpoints/              # per-epoch checkpoints; retention configurable
├── optimization/                 # present only when Optimization is declared
│   ├── trials.parquet            # study.trials_dataframe() shape
│   ├── study.db                  # backend's persistent study (today SQLite; opaque to consumers)
│   └── best-params.json          # winning hyperparameter dict
├── evaluation/
│   ├── metrics.json              # keyed by split → metric → value
│   ├── confusion_matrix.npz      # per-split int arrays (num_classes × num_classes)
│   ├── calibration.parquet       # present when calibration_curve in Evaluation.metrics
│   └── predictions.parquet       # per-split, per-record predictions (FR-22)
└── report/
    ├── report.md                 # human-readable summary
    └── visualizations/            # reporting-mode PNGs
```

**Console output** (CLI):

- Per-epoch progress tables (`rich`).
- Per-trial progress bars during Optimization; tuning-noise suppression for trials > 0 (file-descriptor-level redirect for backends that write directly to fd 1/2, not just `sys.stdout`).
- Structured tables for `status`, `inspect`, and `validate` results.
- Final summary: instance path, cache hit/miss, elapsed time, primary-metric value(s).

**Failure artifacts:**

- Temp directory at `<cache-root>/instances/.tmp/<run-id>/` left in place on failure with a `FAILED` marker file containing the failing stage, error class, and message.

---

## Functional Requirements

### FR-1: Recipe Loading and Schema Versioning

Load a YAML model recipe, validate its schema version, and produce an in-memory recipe object.

**Behavior:**
1. Parse the YAML file.
2. Read `schema_version` (the umbrella combination-function version); refuse to load if absent or unrecognized (gated by `SUPPORTED_SCHEMA_VERSIONS`, sourced from `recipe.versioning.SUPPORTED_COMBINER_VERSIONS`).
3. Route through any registered per-segment migration (`recipe.versioning.migrate_segment`, keyed by `(segment, from, to)`) — empty pre-1.0, so an actual version gap refuses-with-pointer ("re-materialize").
4. Resolve the declared `plugin` and verify it is discoverable on the configured plugin path.
5. Apply the `variants` overlay if `--variant` is set; canonicalize the merged form for the cache key.
6. Construct the recipe object with all declared sections.

**Edge Cases:**
- Missing `schema_version` -> hard error naming the missing field.
- Unrecognized `schema_version` higher than the highest supported version -> hard error listing supported versions (mirrors DataRefinery's vendor-dependency-spec schema-version coordination rule).
- Malformed YAML -> structured error pointing to the offending line.
- Unknown top-level keys -> hard error with `extra="forbid"` semantics (forward-compatible recipes are not valid; readers should fail loudly).
- Unknown `plugin` -> hard error naming the plugin and the configured plugin path.
- `--variant` references a name not declared in `variants` -> hard error listing available variants.

### FR-2: Recipe Validation (`validate`)

Verify a recipe's correctness without running the pipeline. Covers schema correctness and an enumerated set of static logical checks. Never short-circuits.

**Behavior:**
1. Run schema validation (FR-1).
2. Run the enumerated static logical checks below and report each result.
3. Exit with non-zero status on any failure; produce a structured table (CLI) or a `ValidationReport` object (library) listing each check, status, and offending location.

**Enumerated static logical checks (pre-production release):**

1. Recipe `schema_version` is recognized.
2. `plugin` is recognized and discoverable on the configured plugin path.
3. Every op-bearing section names an op the plugin registers **for that section** — an unknown op, or an op registered for a different section (`applies_to` mismatch, e.g. an optimizer op in `Loss`), fails (Story I.c discriminated-union resolution).
4. Every operation in `Architecture` / `Loss` / `Optimizer` / `Training` / `Optimization` / `Evaluation` / `Visualizations` declares the splits it applies to where applicable, and the splits exist in the bound DataRefinery instance.
5. Fit-on-train operations (e.g. `cross_entropy_class_weighted` with `weight_source`) declare `train` as the fit source. Class weights cannot be fit on `val` or `test`.
6. `Training.early_stopping.monitor` references a metric that `Evaluation.metrics` produces, or a built-in (`train_loss`, `val_loss`).
7. `Optimization.search_space` keys reference legitimate recipe paths (e.g. `Optimizer.learning_rate` exists in the schema after variant overlay).
8. `Optimization` categorical hyperparameter defaults are members of the declared choice set (validates `baseline_trial: enqueue_recipe_defaults`).
9. `Optimization.sampler` is one of `{tpe, random, grid}`; `Optimization.pruner` is one of `{median, none}`. (Plugins may register additional samplers/pruners; the pre-production release caps to this set.)
10. `Optimization.n_jobs` is absent or `1` (the pre-production release forbids parallel trials per QR-3).
11. `Evaluation.metrics` names are members of the pre-production vocabulary (`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `accuracy`, `confusion_matrix`, `ece`, `calibration_curve`) plus any plugin-registered additions.
12. `Evaluation.primary_metric` is a member of `Evaluation.metrics`.
13. `Evaluation.comparison.baseline_model_id` (when present) is resolvable by the plugin at materialize time (recipe-time check is a name-format check; resolution happens at materialize).
14. `OutputExpectations` reference metrics that `Evaluation.metrics` produces on the declared split.
15. `Visualizations` operations each declare an output mode (`exploration` or `reporting`).
16. `variants` reference only declared sections and override only declared keys.
17. Plugin-specific operation parameters validate against the plugin's declared `OperationSpec`.
18. `Data:` binding cross-check — the bound DataRefinery instance exposes every split referenced by the recipe (`Training` implicitly requires `train`; `Evaluation.splits` must be a subset of the instance's splits); the instance's label schema is compatible with `Architecture`'s declared `num_classes`; the instance's record schema is compatible with the plugin's expected input shape.
19. Schema-version coordination — if the bound DataRefinery instance's manifest declares a recipe `schema_version` higher than ModelFoundry's highest supported DataRefinery `SUPPORTED_SCHEMA_VERSIONS`, hard error per the vendor-dependency-spec coordination policy.
20. `Training.device` is `"auto"` or matches one of the plugin's `health_check`-reported available accelerators. Tolerant of plugins whose `health_check` does not yet expose an `accelerators` field (skip with a recorded message rather than fail).
21. Architecture-input compatibility — the bound instance's produced input satisfies the architecture's contract (encoder input shape/channels for a pretrained `Encoder`; normalization in 0-255 pixel units), per the data↔model interface guard.
22. `extensions:` keys are claimed by some installed plugin (`Plugin.extension_keys`) — **warn-only** (non-fatal): an unclaimed key is a heads-up, not a failure (Story I.d).

**Edge Cases:**
- Plugin not installed -> hard error pointing at the plugin name and discovery path.
- Multiple failures -> all are reported; `validate` does not short-circuit on the first.
- Unknown operation under a known plugin -> reported as a plugin-specific operation-schema failure (check 17).
- Bound DataRefinery instance does not exist on disk -> hard error naming the expected DataRefinery cache path.
- Optional-extras-gated op referenced in a recipe but extras not installed -> recipe-time checks still fire on the in-tree vocabulary; execution-time errors are deferred to materialization with a clear extras-install pointer.

### FR-3: End-to-End Materialization (`materialize`)

Execute the recipe end-to-end and produce a materialized ModelInstance.

**Behavior:**
1. Run `validate` (FR-2); fail fast on any failure.
2. Compute the cache identity (FR-4); on cache hit, return the existing ModelInstance unchanged (constant-time hit: compute key + `path.exists()` + load manifest).
3. On cache miss, create a temp directory under `<cache-root>/instances/.tmp/<run-id>/`.
4. Execute pipeline stages in the canonical order:
   1. **Architecture** — instantiate the model from plugin primitives.
   2. **Optimization** (if declared) — run the hyperparameter sweep; persist `optimization/trials.parquet`, `optimization/study.db`, `optimization/best-params.json`; merge best-trial hyperparameters into the recipe before Training (auto-composition, locked).
   3. **Training** — fit the model; persist `training/history.parquet` and per-epoch checkpoints under `training/checkpoints/`; promote the best-checkpoint weights into `model/weights/`.
   4. **Evaluation** — score every split listed in `Evaluation.splits`; persist `evaluation/metrics.json`, `evaluation/confusion_matrix.npz`, `evaluation/calibration.parquet` (when applicable), and `evaluation/predictions.parquet` (FR-22).
   5. **OutputExpectations** — evaluate every assertion; on any failure abort with a `FAILED` marker and a structured detail naming the failing expectation, the observed value, and the expected value.
   6. **Visualizations (`mode: reporting`)** — render and persist to `report/visualizations/`.
   7. Write `model/architecture.json` (FR-23).
   8. Render `report/report.md` (FR-8).
   9. Write `manifest.json` with full hashes, plugin, plugin version, schema version, and timings.
5. Atomically promote the temp directory to the final cache path (FR-5).
6. Print a summary (cache hit/miss, instance path, elapsed time, primary-metric value(s)).

**Edge Cases:**
- Cache hit on identical inputs -> no work performed; return existing instance path with `cache=hit` in the summary.
- Failure mid-stage -> temp directory left in place with `FAILED` marker; cache untouched (FR-5).
- Variant selected via `--variant` -> cache identity reflects the variant overlay; different variants of the same recipe produce different ModelInstances.
- Recipe declares no `Optimization` section -> stage 4.2 is skipped; the manifest records `optimization: null`.
- Recipe declares `Evaluation.splits: []` -> stage 4.4 is skipped; downstream visualizations / expectations referencing evaluation metrics fail at `validate` time (FR-2 checks 12, 14).
- `--overwrite` set -> existing instance directory is removed before re-materialization; cache hit is suppressed.

### FR-4: Semantic Cache Identity

Compute a stable identity for a (recipe, data_instance, seed) triple that is invariant to cosmetic edits.

**Behavior:**
1. Parse the recipe; apply variant overlay; strip comments. **Segmented identity (Phase I):** partition the recipe into `core` / `plugin` / `overlays` / `extensions` segments, canonicalize each segment's sub-document via `model_dump(mode="json")` + `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, and combine them with **`join_stable`** — a labeled, length-framed concatenation of per-segment SHA-256 digests (empty segments sparse-omitted; prefix-capable for the deferred vertical axis). The recipe stays flat on disk; segmentation lives only in the hashing. The `join_stable` byte format is the DataRefinery-coordinated family standard (governed shared contract).
2. `recipe_hash` = SHA-256 of the combiner pre-image (`canonical_bytes`); full digest, truncated to 16 hex chars for the directory component.
3. Resolve the bound DataRefinery instance and take its `manifest.recipe_hash ⊕ manifest.input_hash ⊕ manifest.seed` triple's truncated 16-hex digest as `data_instance_hash16`.
4. Combine recipe hash + data_instance_hash + seed into the cache key (`<recipe-hash16>/<data-instance-hash16>/<seed>`).

**Edge Cases:**
- Whitespace-only or comment-only edit -> identical hash; cache hit.
- Key reordering -> identical hash; cache hit.
- Semantic edit (changed value, added/removed operation, variant overlay change) -> different hash; cache miss.
- Bound DataRefinery instance re-materialized at a different seed or with a different recipe -> different `data_instance_hash16`; cache miss.
- **Loose-coupling rule (CR-15):** the bound DataRefinery instance's `recipe_hash` does NOT participate in this recipe's cache identity. Re-materializing upstream does NOT auto-invalidate downstream; the user re-materializes ModelFoundry when ready. Tight coupling is a deferred upgrade (FR-26) and requires a `schema_version` bump.
- **No implicit defaults (Phase I / FR-4a):** behavior-affecting fields carry no value-`default=` — the recipe authors them (the `init` scaffolder emits them), the interpreting code supplies none. This removes the old silent default-shift hazard (a default change no longer perturbs omitting recipes, because there are none). The remaining invalidation levers are the `join_stable` combiner, the segment partition, and authored values; a change to any is a versioning event with a documented CHANGELOG callout. Mode-selecting optionals (absence is meaningful) and the `Optimization.n_jobs=1` invariant are the sanctioned exceptions.

### FR-5: Atomic Temp-then-Promote Materialization

Guarantee the cache contains only complete, valid ModelInstances.

**Behavior:**
1. All pipeline writes target `<cache-root>/instances/.tmp/<run-id>/`.
2. On successful completion, the temp directory is renamed to its final cache path in a single filesystem operation (`os.replace`).
3. On failure, the temp directory is left in place with a `FAILED` marker file containing the failing stage, error class, and message; the final cache path is never touched.

**Edge Cases:**
- Process killed mid-run -> orphaned temp directory; `clean` removes orphans older than a configurable threshold.
- Filesystem rename across devices -> not supported; temp and cache must share a filesystem (documented requirement).
- Concurrent `materialize` calls for the same cache key -> pre-production: serialized externally by the user; running two against the same cache root is unsupported (OR-10). Post-production: file-lock-based protocol detects the temp directory and either waits or refuses (configurable; default refuse with clear error).
- `--overwrite` set and existing instance present -> existing instance is moved to a `.trash/<timestamp>/` sibling, then the new run promotes into the final path; `clean` removes the trashed directory.

### FR-6: DataRefinery Instance Binding (`Data` section)

Resolve the `Data:` block to a materialized `DataRefineryInstance` and cross-validate against the recipe.

**Behavior:**
1. Read `Data.recipe`, `Data.variant`, `Data.seed`.
2. Resolve the bound instance via DataRefinery's library API: compute the canonical DataRefinery recipe hash + input hash + seed, locate the promoted instance under DataRefinery's cache root (or a configured override), and load its manifest.
3. Cross-check (covered by FR-2 checks 18, 19): the instance exposes every split the ModelFoundry recipe references; the label schema is compatible with `Architecture.num_classes`; the record schema is compatible with the plugin's expected input shape; the instance's recipe `schema_version` is within ModelFoundry's known DataRefinery `SUPPORTED_SCHEMA_VERSIONS`.
4. Expose the resolved instance path in `manifest.bound_data_instance` so `inspect()` / `status()` can show the lineage.

**Edge Cases:**
- Bound DataRefinery instance does not exist on disk (never materialized, or `clean`-ed) -> hard error at `validate` time pointing at the expected DataRefinery cache path with the recipe-side fix ("re-materialize the DataRefinery recipe at the bound variant/seed").
- Bound instance is partial (was loaded from a `FAILED` temp directory) -> hard error refusing to consume.
- Bound instance's manifest is missing required fields (`plugin`, `plugin_version`, `recipe_hash`, `record_counts`, `seed`) -> hard error per vendor-dependency-spec § "Failure modes ModelFoundry SHOULD detect" (stale fitted statistics, missing required fields, schema-version mismatch, aggressive variant sidecar missing, plugin missing).
- Bound instance declares an aggressive `Augmentations` op whose sidecar PNG (`image_path`) is missing -> hard error refusing to consume per vendor-dependency-spec.
- Bound instance's plugin is not installed in ModelFoundry's environment -> hard error per vendor-dependency-spec.

### FR-7: Architecture stage (model definition)

Instantiate the model from plugin primitives.

**Behavior:**
1. Parse the `Architecture` block against the plugin's `OperationSpec` set.
2. Resolve every referenced op (e.g. `Conv2d`, `BatchNorm2d`, `Linear`, `MLP`, `Encoder`, `LoRA`) and compose them into a plugin-native model object.
3. Stamp the canonical Architecture block into `model/architecture.json` for round-trip (FR-23).

**Plugin-contributed ops (PyTorch, pre-production release, FR-ARCH-1 — CIFAR-10 baseline vocabulary):**

- **Primitives**: `Conv2d`, `BatchNorm2d`, `ReLU`, `MaxPool2d`, `AvgPool2d`, `AdaptiveAvgPool2d`, `Linear`, `Dropout`, `Flatten`.
- **Composite**: `MLP` (`hidden_dims: list[int]`, `dropout: float`, `activation: str`), `ConvBlock` (`out_channels`, `kernel_size`, `stride`, `padding`, `with_batchnorm: bool`, `with_pool: bool`), `ResidualBlock` (`channels`, `stride`).
- **Baseline architectures**: `simple_cnn` (a small reference CNN sized for CIFAR-10 — three ConvBlock stacks + classification head), `resnet8` (a ResNet variant sized for CIFAR-10), `resnet20` (the canonical CIFAR ResNet-20 — 3×3 stem → three stages of three `ResidualBlock`s at 16/32/64 channels with option-B projection shortcuts and strided-conv downsampling → global average pool → `Linear` head; 272,474 params at `num_classes=10`).
- **Optional pretrained-encoder path (deferred but contract-supported)**: `Encoder` (`source: huggingface`, `id: <hf model id>`, `frozen: bool`), `LoRA` (`rank`, `alpha`, `dropout`, `target_modules: list[str]`), `Pooling` (`type: attention | mean | max`, `hidden_dim`), classification `Head` (`type: mlp`, `hidden_dims`, `num_classes`, `id2label`).

**Edge Cases:**
- Architecture references an op the plugin does not register -> caught by FR-2 check 17 (plugin operation-schema failure).
- Architecture's `num_classes` mismatches the bound DataRefinery instance's label count -> caught by FR-2 check 18.
- Optional pretrained-encoder path declared without `[huggingface]` extras -> hard error at `materialize` time with extras-install pointer (recipe-time validation passes because the in-tree `OperationSpec` enumerates the parameter set).

### FR-8: Loss declaration

Declare the loss function.

**Behavior:**
1. Parse the `Loss` block against the plugin's registered loss ops.
2. Resolve op-specific parameters (e.g. `weight_source: train` for `cross_entropy_class_weighted` — class weights fitted on the train split's label distribution).
3. The Training stage uses the resolved loss object directly.

**PyTorch plugin loss ops (FR-LOSS-1, pre-production release):**

- `cross_entropy` — standard multi-class CE. No params.
- `cross_entropy_class_weighted` — multi-class CE with class weights derived from `weight_source` (one of `train`, `train_inverse_frequency`, `effective_number`). Weights are computed once at training start from the train split's label distribution and persisted under `training/class_weights.json` for audit.
- `bce_with_logits` — binary CE. Reserved for binary-classification recipes; recipe-time validation rejects this op when `Architecture.num_classes > 2`.

**Edge Cases:**
- `weight_source` references a split that is not `train` -> caught by FR-2 check 5 (fit-on-train discipline).
- `bce_with_logits` on a multi-class recipe -> caught by FR-2 check 17 (plugin operation-schema failure).

### FR-9: Optimizer & Schedule

Declare the optimizer and (optionally) the learning-rate schedule.

**Behavior:**
1. Parse the `Optimizer` block.
2. Resolve the optimizer op (`adamw`, `sgd`, `adam`) and its parameters (`learning_rate`, `weight_decay`, `momentum`, `betas`, ...).
3. If `schedule:` is set, resolve the schedule op (`reduce_on_plateau`, `cosine`, `linear_warmup`) and its parameters.
4. The Training stage drives the schedule per its declared `monitor` (if any).

**PyTorch plugin optimizer ops (FR-OPT-1, pre-production release):**

- `adamw` — `learning_rate: float`, `weight_decay: float = 0.01`, `betas: tuple[float, float] = (0.9, 0.999)`.
- `sgd` — `learning_rate: float`, `momentum: float = 0.0`, `weight_decay: float = 0.0`, `nesterov: bool = False`.
- `adam` — same as `adamw` minus weight decay (legacy; `adamw` is preferred).

**PyTorch plugin schedule ops (FR-OPT-2, pre-production release):**

- `reduce_on_plateau` — `monitor: str`, `mode: "min" | "max"`, `factor: float = 0.5`, `patience: int = 2`, `min_lr: float = 1e-6`.
- `cosine` — `T_max: int` (typically `Training.max_epochs`), `eta_min: float = 0.0`.
- `linear_warmup` — `warmup_steps: int`, `total_steps: int`, `min_lr: float = 0.0`.

**Edge Cases:**
- `schedule.monitor` references a metric not produced by `Evaluation.metrics` and not a built-in (`train_loss`, `val_loss`) -> caught by FR-2 check 6 (extended for schedule monitors).

### FR-10: Training stage

Run the training loop.

**Behavior:**
1. Build the `DataLoader` for `train` (and `val` for early-stopping monitor) from the bound DataRefinery instance. Pass `worker_init_fn` and `generator` seeded from the master seed (QR-3).
2. For `max_epochs` epochs:
   1. Iterate `train`; compute loss; backprop; optimizer step.
   2. (If `val` declared by early-stopping monitor) compute monitor metric on `val`.
   3. Drive the LR schedule (if any).
   4. Append the epoch's metrics to `training/history.parquet`.
   5. Write a checkpoint per `Training.checkpoint_cadence`.
   6. Apply `Training.early_stopping`: if the monitor has not improved within `patience` epochs (per `mode`), stop early.
3. Promote the best-monitor-value checkpoint into `model/weights/`.

**Edge Cases:**
- Early stopping monitor references an invalid metric -> caught by FR-2 check 6.
- Training diverges (loss becomes NaN) -> hard error with a clear "training diverged at epoch N" message; the partial `training/history.parquet` is preserved in the temp directory; `FAILED` marker written.
- `max_epochs: 0` -> rejected at recipe-load time (FR-1) as a value-range violation.
- All checkpoint cadence epochs are skipped (e.g. `checkpoint_cadence > max_epochs`) -> the final epoch is always checkpointed regardless, so `model/weights/` is never empty.

### FR-11: Optimization stage (hyperparameter search)

Run a hyperparameter sweep prior to Training.

**Behavior:**
1. Build an Optuna `Study` with the configured sampler (`TPESampler`, `RandomSampler`, `GridSampler`) seeded from the master seed.
2. Configure the pruner (`MedianPruner` or no pruner).
3. If `baseline_trial: enqueue_recipe_defaults` is set, enqueue the recipe's hyperparameter values as trial 0.
4. Run `n_trials` trials sequentially (`n_jobs=1`, locked per QR-3). Each trial:
   1. Sample hyperparameters from `search_space`.
   2. Apply them to a copy of the recipe (override the referenced recipe paths).
   3. Run a short Training loop sized for the trial (the recipe's `Training.max_epochs` capped by `Optimization.max_epochs_per_trial` if set, else the full `Training.max_epochs`).
   4. Report intermediate values per epoch to enable pruning.
   5. Return the trial's objective value (the recipe's `Optimization.objective_metric` or `Evaluation.primary_metric` evaluated on `val`).
5. Persist `optimization/trials.parquet` (study.trials_dataframe() shape), `optimization/study.db`, and `optimization/best-params.json`.
6. Merge the best-trial hyperparameter values into the recipe **before the Training stage runs** (auto-composition, locked per concept Open Question 2).

**Edge Cases:**
- `n_trials: 0` -> rejected at recipe-load time as a value-range violation.
- All trials fail or are pruned -> hard error; `optimization/trials.parquet` is preserved; Training does not run.
- `baseline_trial: enqueue_recipe_defaults` references a recipe path that is not in `search_space` -> caught by FR-2 check 8.
- A trial's intermediate value is NaN -> trial is marked failed; subsequent trials continue; if every trial fails, the stage fails per the previous bullet.
- `n_jobs > 1` set explicitly -> caught by FR-2 check 10.
- Pruner-resumed studies across `materialize()` runs are NOT supported in the pre-production release — each `materialize()` creates a fresh `optimization/study.db`.

### FR-12: Evaluation stage

Score every split listed in `Evaluation.splits` with the declared metric set and persist results.

**Behavior:**
1. For each split in `Evaluation.splits`:
   1. Build the `DataLoader` for the split from the bound DataRefinery instance.
   2. Run inference (no gradient); collect predictions and ground-truth labels.
   3. Compute each metric in `Evaluation.metrics` against (predictions, labels). Metric implementations live in the plugin.
   4. Stamp metric values into `evaluation/metrics.json` keyed as `{split: {metric: value}}`.
   5. Stamp the confusion matrix into `evaluation/confusion_matrix.npz` keyed by split.
   6. If `calibration_curve` is in `Evaluation.metrics`, stamp the calibration table into `evaluation/calibration.parquet`.
   7. Persist per-record predictions to `evaluation/predictions.parquet` (FR-22).
2. If `Evaluation.comparison.baseline_model_id` is set, the plugin resolves and scores the baseline on the same splits with the same metric set; baseline values flow into `evaluation/metrics.json` under a `baseline.<split>.<metric>` key.

**Pre-production evaluation metric vocabulary (cross-plugin contract):**

`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `accuracy`, `confusion_matrix`, `ece`, `calibration_curve`. Each plugin contributes its own implementation:

- **PyTorch plugin (pre-production release)**: `torchmetrics` (`MulticlassF1Score`, `MulticlassConfusionMatrix`, `CalibrationError`).
- **sklearn plugin (stub)**: `sklearn.metrics` (`f1_score(average='macro')`, `confusion_matrix`, `calibration_curve`); ECE hand-rolled.
- **Future Keras / HuggingFace plugins**: implementations TBD per their close-follow-on cycles.

Regression-task metrics are out of scope in the pre-production release (NG-6).

**Edge Cases:**
- `Evaluation.splits` references a split absent from the bound DataRefinery instance -> caught by FR-2 check 18.
- An evaluated split is unlabeled (per DataRefinery's `unlabeled_consistency` rule) -> hard error at `materialize` time: classification metrics require labels.
- Baseline-model resolution fails (e.g. HuggingFace model id not downloadable on this network) -> warning emitted; baseline metrics are omitted from `evaluation/metrics.json`; the report names the failure; main metrics proceed.
- `calibration_curve` evaluated on a split with fewer than `Evaluation.calibration_bins` samples -> reduce-bins fallback (the table has fewer rows than configured); a warning is recorded in the manifest.

### FR-13: Visualizations

Render standard or bespoke views over the materialized model and metrics.

**Behavior:**
1. Each visualization declares `name`, `op`, `mode` (`exploration` or `reporting`), and optional `splits` and op-specific params.
2. `exploration` visualizations are rendered on demand via `inspect()` or the library API; not persisted.
3. `reporting` visualizations are rendered during materialization and persisted to `report/visualizations/<name>.png`.
4. The op handle's `render(...)` receives the `ModelInstance` context (training history, evaluation metrics, predictions). Each plugin contributes its own implementations using `matplotlib`.

**Registered ops (cross-plugin, pre-production release):**

- `training_curves` — per-epoch train/val loss and the primary metric, plotted as a 1×2 figure. No params.
- `optimization_history` — Optuna trial-objective values vs trial number, with the best-so-far envelope. No params. Empty placeholder PNG when no `Optimization` stage ran.
- `confusion_matrix` — per-split confusion matrix as a labeled heatmap. Params: `splits: list[str]` (defaults to `Evaluation.splits`).
- `calibration_curve` — per-split reliability diagram with the ECE value annotated. Params: `splits: list[str]`.
- `predictions_grid` — sample of per-record predictions (true label, pred label, pred prob) with optional image thumbnails when the bound DataRefinery instance exposes per-record images. Params: `n: int = 16`, `splits: list[str]`, `per_class: bool = False`.

**Edge Cases:**
- Visualization without an output mode -> caught by FR-2 check 15.
- `reporting` visualization that fails -> hard error during materialization; the report is not partial.
- `optimization_history` rendered with no `Optimization` stage -> renders an empty-placeholder PNG (or skipped per recipe); the manifest records the placeholder.
- `predictions_grid` declared on a split where the DataRefinery instance does not expose per-record images -> renders without thumbnails (labels-only table).

### FR-14: Variants

Allow a recipe to declare named overlays selected at materialize time.

**Behavior:**
1. The `variants` block declares a mapping of `name -> partial recipe overlay`.
2. `--variant <name>` (CLI) or `variant=<name>` (library) selects an overlay.
3. The overlay is deep-merged onto the base recipe before canonicalization; the merged form is the cache-identity input.
4. Different variants produce different ModelInstances by construction.

**Edge Cases:**
- Variant references a section or key not declared in the base recipe -> caught by FR-2 check 16.
- Multiple variants selected (CLI passed twice) -> last-write-wins behavior is forbidden; the CLI rejects multiple `--variant` flags.

### FR-15: Output Expectations

Machine-check quality gates post-materialization.

**Behavior:**
1. Each entry in `OutputExpectations` is a structured assertion: `{metric: <name>, split: <split>, op: gte | lte | eq | within, value: <number> | [<lo>, <hi>]}`.
2. After Evaluation completes, every assertion is evaluated against the produced `evaluation/metrics.json`.
3. On any failure, materialization aborts with a `FAILED` marker; the marker names the failing assertion, the observed value, and the expected value.
4. Successful expectations are recorded in the report.

**Edge Cases:**
- Expectation references a metric absent from `Evaluation.metrics` -> caught by FR-2 check 14.
- Expectation references a split absent from `Evaluation.splits` -> caught by FR-2 check 14 (extended).
- `op: within` with `value` not a two-element list -> caught at recipe-load time as a shape violation.
- Multiple expectations all fail -> all are reported in the `FAILED` marker, not just the first.

### FR-16: Status (`status`)

Summarize a ModelInstance's lifecycle, configuration, and cache state.

**Behavior:**
1. Resolve a cache path (explicit, or computed from the recipe).
2. Load the manifest.
3. Return a `StatusReport` (library) / render a `rich` table (CLI) with: plugin, plugin version, schema version, recipe hash, bound data instance, seed, variant, cache hit/miss, materialize timestamp, elapsed seconds, primary metric, OutputExpectations status (passed/failed counts).

**Edge Cases:**
- Cache path does not exist -> report "not materialized" with the expected path.
- Manifest is missing required fields -> report "instance corrupt" with the offending field.
- `FAILED` marker present in a sibling temp directory -> report partial state (`is_partial=True`).

### FR-17: Inspection (`inspect`)

Render read-only views of a materialized ModelInstance.

**Behavior:**
1. `inspect()` returns an `InspectionView` object exposing convenience accessors: `view_training_curves()`, `view_confusion_matrix(split)`, `view_calibration(split)`, `view_predictions(split, n)`, `view_trials()`, `view_manifest()`.
2. `inspect(view="<name>")` renders a single named visualization (exploration mode) on demand without persisting.
3. CLI `modelfoundry inspect <instance-path> --view <name>` writes the rendered PNG to a temp file and prints the path.

**Edge Cases:**
- Requested view depends on an unfilled stage (e.g. `view_trials()` on an instance without an Optimization stage) -> raise `InspectionError` with a clear message.
- Instance is partial (`is_partial=True`) -> views that depend on missing stages raise `InspectionError`; views that exist render normally.

### FR-18: Report regeneration (`report` / `render_report`)

Re-render `report.md` and reporting-mode visualizations from an existing ModelInstance without re-training.

**Behavior:**
1. `modelfoundry report <instance-path>` (CLI) / `instance.render_report()` (library) reads the instance, re-runs the reporting-mode visualizations, and rewrites `report/`.
2. The `report.md` is regenerated with current report templates (so a ModelFoundry upgrade that improves report formatting can be re-applied to an existing instance without re-materialization).
3. Cache identity is not affected.

**Edge Cases:**
- Instance is partial -> error refusing to render a report over an incomplete instance.
- Reporting visualization fails during re-render -> hard error; the existing `report/` is preserved (not partially overwritten) by writing to a temp `report.tmp/` and atomically replacing on success.

### FR-19: Environment check (`check`)

Verify the environment is healthy without performing a training run.

**Behavior:**
1. Probe Python version, installed `ml-modelfoundry` version, and plugin discovery.
2. For each discovered plugin, run its `health_check()` callback: verify required deps are importable, report accelerator availability (Metal / CUDA / CPU only), and verify the deterministic-algorithm mode can be enabled.
3. Print a `rich` table summarizing the results.
4. Exit non-zero if any required dep is missing or any plugin's `health_check()` reports an unrecoverable error.

**Edge Cases:**
- Plugin extras not installed (e.g. `[pytorch]` extra missing) -> the plugin reports "extras not installed" with the install pointer; exit non-zero.
- Accelerator absent (CPU-only machine) -> reported as a warning, not an error; CPU is always functional per QR-5.

### FR-20: Cache management (`clean`)

Remove cached ModelInstances by recipe hash, age, or `FAILED` marker.

**Behavior:**
1. `modelfoundry clean --recipe-hash <hash>` removes every instance under that recipe hash directory.
2. `modelfoundry clean --older-than <duration>` removes promoted instances whose `manifest.created_at` is older than the threshold.
3. `modelfoundry clean --failed` removes every temp directory carrying a `FAILED` marker.
4. `modelfoundry clean --orphans --older-than <duration>` removes temp directories without a `FAILED` marker that are older than the threshold (presumed crashed runs).
5. `--dry-run` prints what would be removed without removing.

**Edge Cases:**
- No matches -> exit zero with "nothing to clean" message.
- Removal fails on a directory (permissions) -> exit non-zero; partially-cleaned state is reported.
- Trashed instances (`.trash/<timestamp>/` from FR-5 `--overwrite` runs) are subject to the same age threshold.

### FR-21: Initial scaffolder (`init`)

Bootstrap a starter model recipe from a bound DataRefinery instance.

**Behavior:**
1. `modelfoundry init <recipe-path> --data <datarefinery-recipe-path> [--plugin pytorch]` writes a starter YAML recipe to `<recipe-path>`.
2. The starter is **deterministic** by default — it reads the bound DataRefinery instance's manifest (label schema, num-classes, record schema) and picks a sensible baseline architecture, loss, optimizer, training policy, evaluation metrics, and OutputExpectations for that shape.
3. **Deferred** — optional `--llm-assist` (gated by a future `[llm]` extra) reserved for interpretive judgments (e.g. baseline-model recommendation, OutputExpectations threshold suggestions). The `[llm]` extra and `--llm-assist` flag are **not implemented in the pre-production series**; the deterministic path of step 2 covers all pre-production scaffolding needs. The hook is named here to forward-declare the contract evolution path; a future FR with its own extras and acceptance criteria will graduate it.
4. The scaffold stamps the Apache-2.0 / Pointmatic copyright header at the top of the recipe file as a YAML comment.

**Edge Cases:**
- `<recipe-path>` already exists -> abort with "path exists" unless `--force` is set.
- `--data` references a DataRefinery recipe whose instance is not materialized -> error pointing at the DataRefinery cache path and the fix.

### FR-22: ModelInstance — notebook-shaped accessors and per-record predictions persistence

Expose the materialized ModelInstance through a substrate-neutral, notebook-shaped API.

**Behavior:**
1. `ModelInstance` is a frozen dataclass exposing:
   - `path: pathlib.Path` — the instance directory (escape hatch).
   - `manifest: Manifest` — parsed `manifest.json` (the partial-instance flag lives on `manifest.is_partial`).
   - `plugin: Plugin` — the framework plugin, resolved from `manifest.plugin` at `load` time (FR-23). The canonicalized recipe is read on demand from `recipe.yml` rather than held as a field.
2. Notebook-shaped properties (computed lazily, cached after first access):
   - `evaluation -> dict[str, dict[str, float | dict[str, float]]]` — held-out metrics per split. Per-class metrics are nested dicts keyed by class label. `{}` when no Evaluation stage ran.
   - `metrics -> dict[str, dict[str, float | dict[str, float]]]` — alias for `evaluation`. (Per-epoch training history is persisted to `training/history.parquet` and surfaced in the report / via `inspect`, not through `metrics`.)
   - `confusion_matrix -> dict[str, np.ndarray]` — per-split int arrays of shape (num_classes, num_classes); rows = true label, cols = predicted. `{}` when absent.
   - `calibration -> pd.DataFrame | None` — the reliability table read from `evaluation/calibration.parquet` (columns `confidence_bin`, `expected_accuracy`, `observed_accuracy`, `support`, plus `split`); `None` when absent.
   - `predictions -> pd.DataFrame | None` — **persisted per-record predictions** read from `evaluation/predictions.parquet`, one row per record with columns `split`, `record_id`, `true_label`, `pred_label`, `pred_proba_<class>` (one column per class); `None` when absent.
   - `trials -> pd.DataFrame | None` — Optuna `study.trials_dataframe()` shape; `None` if no Optimization stage.
   - `best_params -> dict[str, Any] | None` — winning hyperparameter dict; `None` if no Optimization stage.
   - `figures -> dict[str, bytes]` — lazily-loaded reporting-mode visualizations as PNG `bytes` (ready for `IPython.display.Image(...)`); `{}` when none were rendered.
3. Notebook-shaped methods:
   - `predict(X) -> np.ndarray | pd.Series` — run inference on caller-supplied input; returns numpy/pandas, never framework-native objects.
   - `predict_proba(X) -> np.ndarray | pd.DataFrame` — class-probability output; `None` for regression recipes (deferred).
4. `ModelInstance.load(path: pathlib.Path) -> ModelInstance` — reload an instance from disk; round-trips by construction (FR-23).

**Per-record predictions persistence** (`evaluation/predictions.parquet`):

- Columns: `split` (string), `record_id` (string; sourced from the DataRefinery instance), `true_label` (any JSON-native), `pred_label` (any JSON-native), `pred_proba_<class>` (float per declared class).
- Sorted by `(split, record_id)` for byte-stable output.
- Persisted at Evaluation stage time (FR-12 step 1.7) — same predictions are used to compute `evaluation/metrics.json`, `evaluation/confusion_matrix.npz`, and `evaluation/calibration.parquet`. No re-inference required to re-score under a different metric.

**Edge Cases:**
- Accessor used on a partial instance where the stage did not run -> the cached-property accessors return an empty container or `None` (`evaluation` / `metrics` / `confusion_matrix` -> `{}`; `calibration` / `predictions` / `trials` / `best_params` -> `None`). The FR-17 `inspect()` / `InspectionView` accessors instead raise `InspectionError` naming the missing stage, so exploration code fails loudly rather than on empty data.
- `predict(X)` called when the bound DataRefinery instance's record schema is unavailable (instance has been `clean`-ed) -> raise `DataBindingError` with a clear "DataRefinery instance no longer resolvable" message. ModelFoundry persists `model/architecture.json` and weights but does not persist the bound data's preprocessing pipeline — that remains DataRefinery's responsibility per CR-8.
- Notebook substrate-neutral check: `IPython.display.Image(mi.figures["training_curves"])` renders the PNG bytes identically in a Jupyter cell, a Marimo cell, and an IPython REPL, while a plain `.py` script consumes the same accessors as data (e.g. `print(mi.metrics)`, `mi.predictions.head()`) — all using only the locked accessor types.

### FR-23: Round-trippable model persistence

Persist the trained model so `ModelInstance.load(path).predict(X)` rebuilds the model from disk alone without any external config object.

**Behavior:**
1. At the end of Training, the plugin serializes the canonical `Architecture` block (post-variant-overlay, post-Optimization merge) as JSON to `model/architecture.json`.
2. The plugin writes weights in its preferred format to `model/weights/`:
   - PyTorch plugin: `state_dict.pt`.
   - sklearn stub: `model.joblib`.
   - Future Keras: SavedModel directory.
   - Future HuggingFace: `model/` directory with `config.json` + `pytorch_model.bin`, plus `tokenizer/` per the BR-8 layout from the consumer-dependency-spec.
3. `ModelInstance.load(path)` reads `model/architecture.json`, instantiates the plugin-native model from its primitives, loads the weights, and returns a fully-functional `ModelInstance` whose `predict(X)` and `predict_proba(X)` methods are immediately callable.

**Round-trip contract:**

- The **full canonical Architecture block** is persisted — not a summary, not a name reference. The sentiment-poc regression precedent (checkpoints missing pooling hidden size, MLP widths, head shapes) MUST NOT recur.
- The manifest pins `plugin`, `plugin_version`, `schema_version`. A loader can refuse a checkpoint produced by an incompatible plugin version with a clear error rather than a silent reconstruction failure.

**Edge Cases:**
- `ModelInstance.load(path)` against a `model/architecture.json` produced by a different `plugin_version` than is currently installed -> hard error naming both versions with the upgrade-path message.
- `model/weights/` missing -> hard error: instance is corrupt.
- `model/architecture.json` references an op the current plugin no longer registers -> hard error per FR-2 check 17 semantics.

### FR-24: Plugin Model

A plugin specializes ModelFoundry for a single backend and contributes the operations its recipe sections expose.

**Behavior:**
1. Plugins are discovered via `pyproject.toml` entry points under a `modelfoundry.plugins` group; additional discovery paths can be set via `--plugin-path` / `MODELFOUNDRY_PLUGIN_PATH`.
2. Each plugin contributes:
   - An `OperationSpec` set for each section: `Architecture`, `Loss`, `Optimizer`, `Schedule`, `Training`, `Optimization`, `Evaluation`, `Visualizations`.
   - A Training-loop implementation honoring the recipe's `Training` block.
   - An Optimization-trial harness honoring the recipe's `Optimization` block (today an Optuna-backed implementation; the plugin Protocol does not name Optuna).
   - Metric implementations for the pre-production metric vocabulary (FR-12).
   - Visualization implementations for the pre-production viz vocabulary (FR-13).
   - A `health_check()` callback exercised by `check` (FR-19).
3. The plugin interface is **honest by construction**: at least one non-default plugin (the sklearn stub) registers against the same `OperationSpec` interface, so the abstractions are exercised even though the stub has no working training implementation.

**Pre-production plugins:**

- **`pytorch` (end-to-end)** — full implementation of CIFAR-10-scale image-classification training/optimization/evaluation. Depends on `torch`, `torchvision`, `torchmetrics` via the `[pytorch]` extra. Honors QR-3 determinism caveats.
- **`sklearn` (stub)** — registers `OperationSpec` for each section but contributes only the metric implementations (sklearn-based) shared across plugins. `materialize()` against a `plugin: sklearn` recipe raises `PluginError("plugin 'sklearn' has no working Training implementation in the pre-production release; use 'pytorch'")` with the pre-production redirect message.

**Edge Cases:**
- Two plugins register the same plugin name -> ModelFoundry raises `PluginError` at discovery time naming both packages.
- A plugin contributes an op that collides with a name used by another plugin -> not an error (plugin names namespace ops); a recipe selects its plugin first.

### FR-25: Reproducibility & Determinism Contract

Codify the determinism guarantee and the conditions under which it holds.

**Behavior:**
1. Every stochastic source is seeded from the recipe's master seed:
   - Model weight initialization.
   - DataLoader shuffling (worker_init_fn + generator pattern).
   - Dropout RNG (frame-stamped from master seed).
   - Augmentation realization (consumes DataRefinery's `<AugmentationOp.name>_seed` per-record stamps from the vendor-dependency-spec for aggressive-mode variants; the plugin's framework-side augmentation seed for lazy-mode augmentations declared in the DataRefinery recipe).
   - Optuna sampler (sampler seed derived from master seed; sample sequence is deterministic).
2. Same `(recipe, data_instance, seed, variant)` tuple produces a byte-identical `ModelInstance` directory excluding `manifest.created_at` and `manifest.elapsed_seconds`.
3. Determinism caveats per QR-3 apply: the plugin's deterministic-algorithm mode is on by default; `n_jobs=1` for Optimization; AMP off by default. Recipes that enable AMP relax to metric-equivalent within a documented tolerance.

**Edge Cases:**
- A recipe that enables AMP via `Training.precision: "amp"` -> the plugin records `manifest.byte_identity_guaranteed: false` and `manifest.metric_tolerance: <documented tolerance>`; determinism tests gate on metric tolerance, not byte identity.
- The plugin's `health_check()` reports that deterministic-algorithm mode cannot be enabled (e.g. unsupported on the installed backend) -> hard error at `materialize` time refusing to proceed; the user can opt out via a future `--allow-nondeterministic` flag (deferred).

### FR-26: Future — tight-coupled DataRefinery binding

Documented future upgrade: tight-couple ModelFoundry's cache identity to DataRefinery's so re-materializing upstream auto-invalidates downstream ModelInstances.

**Behavior (when implemented, post-production):**
1. The bound DataRefinery instance's `recipe_hash` participates in the consuming ModelFoundry recipe's cache identity.
2. Re-materializing DataRefinery at a new recipe shape produces a new `data_instance_hash16`; ModelFoundry re-materializes on next invocation.
3. The upgrade requires a ModelFoundry `schema_version` bump and a documented migration of existing cached ModelInstances.

**Status in the pre-production release:** **deferred**. CR-15 explicitly locks loose-coupling for the pre-production release. This FR exists to forward-declare the contract evolution path for future tools (`modelmetrics`, `modelmachine`) that may want tighter guarantees.

### FR-27: Model summary

Generate a human- and machine-readable summary of the materialized model as a reproducible, from-disk artifact.

**Behavior:**
1. At materialize time, after Persistence, the plugin generates a model summary and writes two artifacts under the instance's `model/` directory:
   - `model/summary.txt` — a text render of the model (the PyTorch plugin uses `torchinfo`): a per-layer table plus the network totals.
   - `model/summary.json` — the structured form: an ordered list of per-layer rows and the network totals.
2. Each per-layer row reports the layer **type**, the **output shape**, the **parameter count**, and the **mult-adds** (multiply-add operations). The network totals report **total parameters**, **trainable parameters**, **non-trainable parameters**, and **total mult-adds**.
3. The input shape fed to the summary is derived from the bound DataRefinery instance's record schema (e.g. `(N, 3, 32, 32)` for CIFAR-10).
4. Both artifacts are **byte-deterministic** for a fixed architecture + input size: the reported quantities are functions of the architecture, not of any probe input, and the artifacts carry no timestamp. Generating the summary does not mutate the persisted model (the probe runs in eval mode; the model's training flag is restored).
5. The summary is surfaced to consumers via `ModelInstance.summary` (the structured `summary.json`, FR-22) and `ModelInstance.summary_text` (the text render); the CLI exposes it as `inspect --view model_summary` (FR-17), which renders the text summary. Substrate-neutral — `print(mi.summary_text)` renders in any notebook host.

**Plugin model:** model-summary generation is an **optional** plugin capability. A plugin that exposes it (the `pytorch` plugin) gets the artifacts written automatically; a plugin that does not (the sklearn baseline, whose `MLPClassifier` has no torchinfo-style layer summary) skips the step cleanly without failing the materialization.

**Edge Cases:**
- Plugin does not provide a model summary -> the `model/summary.*` artifacts are absent; `ModelInstance.summary` / `summary_text` return `None`; not an error.
- The bound DataRefinery instance's record schema declares no usable image shape -> the plugin falls back to decoding one record through its dataset adapter to learn the true `(C, H, W)`.

---

## Configuration

**Configuration precedence (high to low):**
1. Recipe file (authoritative for model-build semantics).
2. CLI flags (execution context only).
3. Environment variables (defaults for execution context).
4. Built-in defaults.

**CLI flags / environment variables:**

| CLI flag | Env var | Default | Purpose |
|---|---|---|---|
| `--cache-root` | `MODELFOUNDRY_CACHE_ROOT` | `./models/` | Cache root directory |
| `--log-level` | `MODELFOUNDRY_LOG_LEVEL` | `INFO` | Operational log level |
| `--log-target` | `MODELFOUNDRY_LOG_TARGET` | `stderr` | JSON-lines log sink (file path or `stderr` / `stdout`) |
| `--plugin-path` | `MODELFOUNDRY_PLUGIN_PATH` | (empty) | Extra plugin discovery paths |
| `--variant` | (none) | (none) | Variant overlay name |
| `--seed` | (none) | (recipe) | Ad-hoc seed override; changes cache identity |
| `--overwrite` | (none) | `false` | Re-materialize even on cache hit |

**No `modelfoundry.toml` per-project config in the pre-production release** — the recipe is authoritative; CLI flags and env vars cover execution context. A project-config file may be added post-production if recurring patterns emerge.

---

## Testing Requirements

- **TR-1: Recipe loader unit tests.** Coverage on schema-version gating, plugin resolution, variant overlay merge, canonicalization byte-stability.
- **TR-2: Cache identity unit tests.** Cosmetic edits (whitespace, key reorder, comment changes) produce identical hashes; semantic edits (value change, op add/remove, variant switch) produce different hashes; seed change perturbs the hash; bound DataRefinery instance change perturbs the `data_instance_hash16` but does NOT perturb the consuming recipe's hash (CR-15 loose-coupling check).
- **TR-3: Validate unit tests.** Every static logical check (FR-2 checks 1..22) has a dedicated test that asserts both the rejection and the human-readable error message.
- **TR-4: Atomic promote integration tests.** Forced failure at every materialize stage leaves a `FAILED`-marked temp directory; the cache never sees partials; `--overwrite` correctly trashes the existing instance before promoting.
- **TR-5: Determinism integration tests.** Run a fixture recipe twice with the PyTorch plugin and assert byte-identical instance contents (excluding wall-clock fields). One worker, two workers, four workers — all three configurations produce identical bytes (mirrors DataRefinery's H.o spike pattern).
- **TR-6: Round-trip integration test.** `ModelInstance.load(path).predict(X)` succeeds without the caller supplying any external config object (sentiment-poc regression precedent — must not recur).
- **TR-7: Loose-coupling guarantee integration test.** Re-materialize DataRefinery upstream; assert the existing ModelFoundry cached instance is unchanged on disk and is still returned on the next `materialize()` call.
- **TR-8: Notebook-substrate-neutral smoke.** Same `ModelInstance` accessor calls return identical values when consumed from (a) a plain `.py` script, (b) a Jupyter cell via `nbclient`, (c) a Marimo cell via Marimo's headless runner. (Substrate-neutral by construction — the test is a sanity check, not a feature requirement.)
- **TR-9: PyTorch-plugin metric implementation tests.** Each pre-production metric (`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `accuracy`, `confusion_matrix`, `ece`, `calibration_curve`) is validated against a hand-computed golden value on a tiny fixture; per-class metrics produce per-class dicts.
- **TR-10: Optimization stage tests.** TPE, Random, and Grid samplers each produce deterministic trial sequences from a fixed seed; `baseline_trial: enqueue_recipe_defaults` correctly enqueues trial 0; best-params merge into the recipe before Training; `n_jobs > 1` rejected at validate time.
- **TR-11: OutputExpectations tests.** Passing and failing expectations both produce the expected outcomes (success / `FAILED` marker); multiple failing expectations all surface in the marker.
- **TR-12: CIFAR-10 fixture smoke (CR-16, the strongest AC).** End-to-end CI-runnable fixture: a small DataRefinery image-classification recipe materializes a downsized CIFAR-10 instance; a ModelFoundry recipe trains a `simple_cnn` over it with a 2-trial Optimization stage and a 3-epoch Training stage; the smoke asserts `ModelInstance.evaluation["val"]["macro_f1"]` is above a documented floor and the `OutputExpectations` pass. Designed to fit a free-tier CI runner.
- **TR-13: Environment isolation.** Tests run via `pyve test` against the dev `testenv` (torch tests in `smoke-pytorch`); the runtime root venv is not polluted with pytest / mypy / ruff.
- **TR-14: Type checking.** `mypy --strict` passes on the entire package.
- **TR-15: Coverage targets.** ≥ 95% line coverage on core invariants (TR-1, TR-2, TR-4, TR-6, TR-7 modules); FR-coverage smoke for every FR in any release; ≥ 85% overall line coverage post-production.
- **TR-16: Cross-platform smoke.** CI runs the CIFAR-10 smoke on macOS (Apple Silicon) minimum; Linux is a stretch target in the pre-production release, first-class post-production.

---

## Security and Compliance Notes

- **SC-1: License and copyright.** Apache-2.0; copyright Pointmatic. SPDX identifier `Apache-2.0` on all new source files (`#` for Python / YAML / shell, per the `project-essentials.md` file-header convention).
- **SC-2: Local-first, no network at validate / materialize time.** `validate` and `materialize` make zero network calls **except** for plugin-declared pretrained-weight downloads on first run; subsequent runs use the warm local cache. The PyTorch plugin's CIFAR-10 baseline recipes use no pretrained weights and run fully offline.
- **SC-3: No secrets.** ModelFoundry does not read, store, or transmit credentials. Plugin-side pretrained-weight downloads use the backend library's standard local-cache mechanism.
- **SC-4: Path-escape protection.** `Data.recipe` and `--plugin-path` references that traverse outside the cache root or the configured plugin search paths are rejected at validate time.
- **SC-5: No code execution at validate time.** `validate` reads recipes and the bound DataRefinery instance's manifest only; it does not execute user-supplied Python or instantiate the plugin's model object. (Materialize does execute the plugin's training code, but only on explicit user invocation.)
- **SC-6: No PII.** ModelFoundry does not collect, store, or transmit personally identifying information. Cached ModelInstances contain only model artifacts, metrics, and the user's own data references; user identity tracking is not a ModelFoundry concern.

---

## Performance Expectations

- **PE-1: No hard targets in the pre-production release.** The pre-production release does not commit to throughput, latency, or memory targets. Performance work happens reactively, in response to observed problems on representative workloads.
- **PE-2: Constant-time cache hit.** A repeated `materialize()` call on an unchanged recipe + unchanged DataRefinery instance + unchanged seed returns in constant time (compute cache key + `path.exists()` + load manifest). This is the only performance commitment the pre-production release makes.
- **PE-3: CIFAR-10 smoke fits CI.** The TR-12 fixture must complete within a free-tier CI runner's per-job budget on CPU.
- **PE-4: Optimization-trial output suppression.** Tuning-noise from trial > 0 is suppressed at file-descriptor level for backends that write directly to fd 1/2 (not just `sys.stdout`), per the sentiment-poc precedent. Trial 0 prints normally so the user can verify the recipe-defaults baseline trains correctly.

---

## Acceptance Criteria

The project is "done" for the pre-production release when **all** of the following hold:

1. **AC-1: Public API matches the consumer-dependency-spec.** `from modelfoundry import ModelFoundry, ModelInstance, ModelfoundryError, ...` works; the symbols match the BR-1..BR-12 / BR-7 / BR-10 signatures from `nbfoundry/consumer-dependency-spec.md` exactly.
2. **AC-2: CIFAR-10 end-to-end fixture.** The CR-16 / TR-12 fixture runs end-to-end on CI: DataRefinery materializes a downsized CIFAR-10 instance; ModelFoundry trains a `simple_cnn` over it (with a 2-trial Optimization stage and a 3-epoch Training stage); `ModelInstance.evaluation["val"]["macro_f1"]` exceeds a documented floor; `OutputExpectations` pass.
3. **AC-3: PyTorch plugin ships end-to-end.** All pre-production PyTorch-plugin Architecture / Loss / Optimizer / Schedule / Training / Optimization / Evaluation / Visualization ops are implemented and exercised by integration tests against the bound DataRefinery image-classification plugin.
4. **AC-4: sklearn plugin stub ships.** The sklearn plugin registers the full `OperationSpec` set and the shared metric implementations; `materialize()` against a `plugin: sklearn` recipe raises the pre-production redirect message; the stub validates the plugin interface is honest.
5. **AC-5: Round-trip guarantee.** `ModelInstance.load(path).predict(X)` succeeds from disk alone without any external config object (TR-6).
6. **AC-6: Determinism guarantee.** Same `(recipe, data_instance, seed, variant)` tuple produces byte-identical instance contents excluding wall-clock fields, under QR-3 plugin-declared caveats (TR-5).
7. **AC-7: Loose-coupling guarantee.** Re-materializing DataRefinery upstream does not invalidate or alter the cached ModelFoundry instance (TR-7).
8. **AC-8: CLI is usable.** `init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean` all run successfully against the CIFAR-10 fixture, with concise `rich` stdout output and structured JSON-lines operational logs on the configured `--log-target`.
9. **AC-9: Notebook-substrate-neutral.** The `ModelInstance` accessor surface returns identical values when consumed from Jupyter, Marimo, IPython, and a plain `.py` script (TR-8 sanity check).
10. **AC-10: Tests and types pass.** Unit + integration tests pass under `pyve test`; `mypy --strict` passes; coverage on core invariants ≥ 95%; every FR exercised by at least a smoke (TR-15).
11. **AC-11: License hygiene.** Every new source file carries the Apache-2.0 / Pointmatic SPDX header.
12. **AC-12: Local-first, no network at validate / materialize.** Validate and materialize make zero network calls on the CIFAR-10 fixture (the fixture uses no pretrained weights); other recipes that name pretrained weights download on first run only (SC-2).
13. **AC-13: PyPI published.** `ml-modelfoundry` and `ml-modelfoundry[pytorch]` install cleanly from PyPI on a fresh Python 3.12 venv; the import name and console script are `modelfoundry`.
14. **AC-14: CI/CD wired.** PR pipeline runs lint + types + tests + CIFAR-10 smoke; release pipeline publishes tagged commits to PyPI. (Branch protection explicitly NOT required for the pre-production release per CR-1.)
15. **AC-15: Cross-repo contract honored.** The vendor-dependency-spec from DataRefinery and the consumer-dependency-spec from nbfoundry are both honored verbatim — no documented surface is silently violated.
