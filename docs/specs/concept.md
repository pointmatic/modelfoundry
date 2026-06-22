# concept.md — ModelFoundry

This document defines why the `ModelFoundry` project exists.
- **Problem space**: problem statement, why, pain points, target users, value criteria
- **Solution space**: solution statement, goals, scope, constraints
- **Value mapping**: Pain point to solution mapping

For requirements and behavior (what), see [`features.md`](features.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For project-specific must-know facts (workflow rules, hidden coupling, tool-wrapper conventions that the LLM would otherwise random-walk on), see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

For the upstream contract ModelFoundry consumes, see [`datarefinery/vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md) (DataRefinery as vendor). For the downstream contract ModelFoundry honors when consumed indirectly through nbfoundry lifecycle templates, see [`nbfoundry/consumer-dependency-spec.md`](nbfoundry/consumer-dependency-spec.md).

## Problem Space

### Problem Statement
Once data is prepared, an ML practitioner hits a second wall: writing and rewriting framework-specific scaffolding for model definition, training loops, hyperparameter search, and evaluation. Each backend (PyTorch, Keras, scikit-learn, HuggingFace `transformers`/`peft`) carries its own boilerplate, save/load idioms, and accelerator quirks. Hyperparameter-search frameworks (Optuna, Ray Tune) bring their own object models that leak into notebooks and applications. Evaluation metric implementations are re-derived per project, calibration and per-class breakdowns are skipped, and "did the model meet the bar?" remains a human judgement rather than a machine-checked gate. The result: notebook cells and Python applications import `torch` / `tensorflow` / `keras` / `optuna` directly, coupling every downstream consumer to a specific framework, and trained models ship as opaque checkpoints whose architecture metadata lives in the author's head.

**Why this problem exists:**
The problem persists because modeling mechanics sit at the intersection of forces that resist commoditization:

- **Framework-specific boilerplate is the path of least resistance.** A working PyTorch training loop, a working Keras `fit`, and a working sklearn `pipeline` look nothing alike; the abstractions that would unify them are non-trivial to design, and no community standard has emerged.
- **Reproducibility is harder for models than for data.** A trained model depends on weight initialization, data shuffling, dropout RNG, augmentation RNG (lazy-mode policies from DataRefinery), and the Optuna sampler's internal state. Missing any of them silently breaks determinism.
- **Hyperparameter search leaks.** Optuna's `Study` / `Trial` object model becomes part of users' code; switching samplers or moving search to a different harness means rewriting the modeling layer that surrounds it.
- **Save/load is fragile.** Checkpoints routinely omit the architecture dimensions (pooling hidden size, MLP widths, head shapes) needed to reconstruct the model from disk alone — `load()` requires the original training config, and that config is rarely persisted alongside the weights.
- **Evaluation discipline decays under deadline pressure.** Per-class F1, calibration, confusion matrices, and baseline comparisons are easy to skip; without a declarative recipe they are rarely re-added.
- **Modeling and data prep blur.** Notebooks that should consume a prepared dataset instead mix splitting, normalization, and tokenization into the modeling cells, undoing DataRefinery's fit-on-train discipline.
- **Two consumption shapes, one missing contract.** Direct Python applications and notebook-based exercises (via nbfoundry / learningfoundry) need the same modeling primitives, but no library provides a single result-object surface that satisfies both.

### Pain Points
- **framework_lock_in_user_code**: Notebook cells and Python applications import `torch`, `tensorflow`, `keras`, `optuna`, or `peft` directly, coupling every downstream consumer to a specific backend and making cross-framework reuse impossible.
- **training_loop_reinvention**: Epoch loops, batching, early-stopping, LR schedules, and checkpoint cadence are reassembled every project from framework-specific primitives, with subtle variations between authors.
- **brittle_save_load**: Saved checkpoints omit the architecture dimensions needed to rebuild the model; `load()` silently fails or requires the caller to hand-pass the original training config.
- **hyperparameter_search_coupling**: Optuna's `Study` / `Trial` object model bleeds into modeling code; sampler choice and trial-history persistence are non-portable.
- **non_repeatable_training**: Unseeded weight init, data shuffling, dropout, augmentation realization, and Optuna sampling produce different results across runs of "the same" recipe.
- **evaluation_ad_hockery**: Metric implementations are re-derived per project; per-class F1, calibration, and confusion matrices are routinely omitted because they require extra code.
- **train_eval_skew**: Feature shape and normalization at training time differ from evaluation/inference; train-only operations (class-weighted loss, fit-on-train statistics) leak across splits.
- **expectation_drift**: No machine-checked "did this model meet the bar?" gate; quality regressions surface as silent metric drops noticed weeks later.
- **ad_hoc_caching**: Re-train to be safe, or trust stale weights; no content-addressed cache and no atomic-promote discipline means partial / corrupt model directories accumulate.
- **notebook_unfriendly_outputs**: Training/evaluation returns framework-native objects (`torch.Tensor`, `keras.callbacks.History`, Optuna `Study`); notebook cells unpack them by hand before rendering.
- **comparison_baseline_gap**: No built-in pattern for scoring a candidate model against a published baseline (HF model id, sklearn estimator) on the same held-out split.
- **data_modeling_blur**: Notebooks intended to consume a prepared dataset instead re-do splitting / sampling / tokenization in the modeling cells, undoing DataRefinery's discipline and re-introducing leakage.
- **hand_off_contract_gap**: Downstream tools (`modelmetrics`, `modelmachine`, a future replay harness) need a stable on-disk and in-memory contract; today every project rolls its own directory layout.

### Target Users
- **Primary — Python developers and ML practitioners** building supervised-learning models (classification, regression) over structured, text, or image data prepared by DataRefinery, who want backend-agnostic modeling mechanics rather than per-framework scaffolding.
- **Primary — Jupyter notebook users** doing exploratory ML work who want the same backend-agnostic modeling primitives, content-addressed caching, and notebook-shaped result accessors (`pandas.DataFrame` / `numpy.ndarray` / PNG `bytes`) without committing to a particular notebook substrate. ModelFoundry's API is substrate-neutral — it works inside Jupyter, Marimo, IPython, or a plain `.py` script with no integration layer.
- **Primary (indirect) — notebook authors via nbfoundry**, whose lifecycle templates (`model_experimentation`, `model_optimization`, `model_evaluation`) consume ModelFoundry as their modeling-mechanics abstraction. The nbfoundry path is an opinionated authoring/embedding choice (pure-Python Marimo notebooks, compileable for learningfoundry embedding) layered on top of the same ModelFoundry contract Jupyter users see directly.
- **Primary (indirect) — learners via learningfoundry**, who execute compiled nbfoundry exercises that route their modeling work through ModelFoundry.
- **Secondary — deep-learning curriculum** (students and instructors) using DataRefinery-prepared image-classification datasets and expecting a reproducible end-to-end path from a prepared dataset to a trained model.
- **Secondary — ML researchers** running optimization sweeps who want trial history surfaced as a DataFrame and persisted in a cache without writing Optuna boilerplate.
- **Indirect beneficiaries — downstream tools** (a future `modelmetrics`, `modelmachine`, drift-detection harness, CI replay) that consume `ModelInstance` directories against a stable contract.
- **Negatively impacted by the status quo (helped indirectly)** — reviewers, collaborators, and future maintainers who today reverse-engineer training runs from undocumented notebooks and orphaned checkpoint files.

### Value Criteria
- **Time-from-prepared-data-to-trained-model**: elapsed time from a materialized DataRefinery instance to a materialized ModelInstance a downstream tool can consume.
- **Backend-agnosticism in user code**: zero `import torch` / `import tensorflow` / `import keras` / `import optuna` in notebook bodies and application modeling code; the recipe's `plugin` field is the only backend selector.
- **Reproducibility guarantee**: same `(recipe, data_instance, seed, variant)` tuple produces a byte-identical `ModelInstance` directory (excluding wall-clock fields).
- **Round-trip integrity**: `ModelInstance.load(path).predict(X)` succeeds without the caller supplying any external config object — the architecture round-trips from disk alone.
- **Notebook-readiness**: result accessors return `pandas.DataFrame` / `numpy.ndarray` / PNG `bytes`; cells render tables and arrays with `display(...)` directly and figures via `IPython.display.Image(...)`.
- **Hand-off contract stability**: on-disk layout (`recipe.yaml` / `manifest.json` / `model/` / `training/` / `optimization/` / `evaluation/` / `report/`) and in-memory `ModelInstance` shape evolve only via `schema_version` bumps.
- **Cache discipline**: cache identity is computed and content-addressed; partial / failed runs leave a `FAILED` temp directory and never appear under the promoted cache root.
- **Plugin-interface honesty**: at least one non-default backend stubbed against the same `OperationSpec` set, exercising the framework-agnostic abstractions.
- **Evaluation completeness**: per-class metrics, calibration, and a baseline comparison are first-class recipe entries, not optional follow-ups.
- **Machine-checked quality gates**: `OutputExpectations` failures abort materialization with a `FAILED` marker, mirroring DataRefinery's FR-23.
- **Offline operability**: the deterministic training path runs without network access (modulo any plugin-declared pretrained weights that the env pre-fetches); no required LLM calls.

## Solution Space
`modelfoundry` is a Python project to compile a YAML recipe into a reproducible, framework-agnostic trained-model instance.

### Solution Statement
ModelFoundry is a Python tool — usable as a library or a CLI — that compiles a single YAML **model recipe** into a materialized **ModelInstance**: the recipe itself, the trained model (weights + a round-trippable architecture description), per-epoch training metrics, hyperparameter-search trial history, held-out evaluation metrics, reporting visualizations, and a manifest, atomically promoted into a content-addressed cache. The recipe declares `Architecture` / `Loss` / `Optimizer` / `Training` / `Optimization` / `Evaluation` / `Visualizations` / `OutputExpectations` / `variants`, plus a `Data` reference that binds the recipe to a materialized DataRefinery instance — ModelFoundry never performs splitting, cleaning, sampling, tokenization, or feature engineering. A `plugin` field selects the backend (PyTorch first, with at least one additional backend stubbed against the same `OperationSpec` set); recipe authors and user code never import `torch` / `tensorflow` / `keras` / `optuna` / `peft`. ModelFoundry executes the recipe deterministically, seeds every stochastic source (weight init, data shuffling, dropout, augmentation realization, Optuna sampler), persists trial history as parquet, and caches the result by `recipe_hash ⊕ data_instance_hash ⊕ seed`. Re-running an unchanged recipe over an unchanged DataRefinery instance returns the cached instance unchanged; any semantic edit invalidates and rebuilds. The `ModelInstance` exposes notebook-shaped accessors (`pandas.DataFrame` / `numpy.ndarray` / PNG `bytes`) and notebook-native `.predict()` / `.predict_proba()` — substrate-neutral, equally consumable from a plain `.py` script, a Jupyter cell, a Marimo cell, or nbfoundry's lifecycle templates. The on-disk layout and `ModelInstance` shape are the stable contract downstream tools (a future `modelmetrics`, `modelmachine`, replay harness) bind against.

### Goals
Mapped to the value criteria above:

- **Compress time-from-prepared-data-to-trained-model** by replacing per-project framework scaffolding with a single recipe and a small set of CLI verbs (`init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`).
- **Decouple modeling from framework** so user code, notebook cells, and lifecycle templates never import `torch` / `tensorflow` / `keras` / `optuna` / `peft`; the recipe's `plugin` field is the only backend selector and the `ModelInstance` API returns framework-agnostic primitives.
- **Guarantee reproducibility** by seeding every source of stochasticity (weight init, data shuffling, dropout, augmentation realization per DataRefinery's per-record-seed contract, Optuna sampler) and content-addressing every artifact, so the same `(recipe, data_instance, seed, variant)` tuple yields a byte-identical `ModelInstance` directory.
- **Round-trip models from disk alone** by persisting a plugin-agnostic `model/architecture.json` alongside weights, so `ModelInstance.load(path).predict(X)` works without the caller supplying any external config object.
- **Absorb hyperparameter search into materialization** by making `Optimization` a stage of `materialize()` rather than a separate orchestration; surface trials as a `pandas.DataFrame` matching Optuna's `study.trials_dataframe()` shape, and never name Optuna in the recipe.
- **Make evaluation declarative and complete** by listing metrics in the recipe (with per-class F1, calibration, confusion matrices, and baseline comparison as first-class entries) and applying them per-split via explicit `splits` declarations — the same fit-on-train / apply-per-split discipline DataRefinery uses.
- **Machine-check quality** through `OutputExpectations` assertions evaluated post-materialization; failures abort with a `FAILED` marker, mirroring DataRefinery's FR-23.
- **Coexist with DataRefinery (not subsume)** by consuming a materialized DataRefinery `Instance` for data and binding loose-coupled by default — re-materializing upstream does not auto-invalidate downstream.
- **Stay notebook-substrate-neutral** by returning result accessors that any Python notebook substrate can render directly (Jupyter, Marimo, IPython, plain script). nbfoundry is an opinionated consumer, not the only path.
- **Provide a stable downstream contract** by versioning the on-disk layout and `ModelInstance` API shape via `schema_version`, so future tools (`modelmetrics`, `modelmachine`, CI replay) bind against a defined surface.
- **Validate plugin-interface honesty** by sketching at least one non-default backend as a stub so the framework-agnostic abstractions are exercised, not just asserted.
- **Make failures inspectable** through atomic temp-then-promote materialization, mirroring DataRefinery: partial instances never appear in the cache; failed runs leave a marked temp directory with a `FAILED` sentinel.
- **Stay operable offline** by keeping the deterministic training path free of network dependencies (modulo any plugin-declared pretrained weights that the env pre-fetches); no required LLM calls.

### Scope
**In scope (pre-production release):**

- Recipe-driven pipeline with sections analogous to DataRefinery's intent-naming convention: `schema_version`, `plugin`, `seed`, `Data`, `Architecture`, `Loss`, `Optimizer`, `Training`, `Optimization`, `Evaluation`, `Visualizations`, `OutputExpectations`, `variants`, `extensions` (a sanctioned declarative bag for bounded experimentation). Per-operation `splits` declarations make train-only behavior explicit. **No implicit defaults:** behavior-affecting values are authored in the recipe (the scaffolder emits them), not supplied by code; `num_workers` is execution context (`--num-workers`), not a recipe field.
- Schema-versioned YAML recipes; load-time refusal of unknown versions; documented migration path between versions (mirrors DataRefinery's `recipe.loader`).
- Materialized `ModelInstance` = recipe + trained model (weights + `architecture.json`) + training history + optimization trials + evaluation metrics + report + manifest.
- Cache identity from the **segmented** canonical recipe form (per-segment digests — `core` / `plugin` / `overlays` / `extensions` — combined by the labeled, length-framed `join_stable`, replacing the flat total `model_dump`) ⊕ bound DataRefinery instance hash ⊕ seed. Cosmetic edits do not trigger rebuilds; a plugin-surface change scopes to that plugin's recipes.
- Atomic temp-then-promote materialization with `FAILED` sentinel on partial runs; no partial instances in cache.
- Named **variants** within a recipe (overlays on any section); selected at materialize time; participate in cache identity.
- Plugin model with **PyTorch shipping end-to-end in the pre-production release**, mirroring the sentiment-poc precedent; at least one additional backend (sklearn likely first, Keras / HuggingFace optional) stubbed against the same `OperationSpec` set to keep abstractions honest.
- Optuna-backed `Optimization` stage; recipe never names Optuna; trial history persisted as parquet matching `study.trials_dataframe()` shape; `baseline_trial: enqueue_recipe_defaults` pattern supported.
- DataRefinery binding (DD-1): `Data:` block resolves to a materialized DataRefinery `Instance`; ModelFoundry queries splits and label schema via DataRefinery's library API and does no data prep.
- `ModelInstance` notebook-shaped accessors: `.evaluation` → `dict[str, dict]` (per-split metrics), `.metrics` → alias for `.evaluation`, `.confusion_matrix` → `dict[str, np.ndarray]`, `.calibration` → `pd.DataFrame | None`, `.predictions` → `pd.DataFrame | None`, `.trials` → `pd.DataFrame | None`, `.best_params` → `dict | None`, `.figures` → `dict[str, bytes]` (PNG bytes, ready for `IPython.display.Image`), `.predict()` / `.predict_proba()` returning numpy/pandas primitives, plus `.path` escape hatch. (Per-epoch training history is persisted to `training/history.parquet` and surfaced in the report, not via `.metrics`.)
- Round-trippable `model/architecture.json` — `ModelInstance.load(path).predict(X)` works without an external config object.
- `OutputExpectations` post-materialization assertions; failures abort with `FAILED` marker.
- `Visualizations` with `mode: exploration` (on-demand via `inspect()`) and `mode: reporting` (persisted in instance's `report/`).
- Python library API and CLI as co-equal surfaces; CLI verbs `init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`.
- `validate` runs an enumerated set of static logical checks (schema-version, plugin/op resolution, per-op splits consistency, `fit_on_train` discipline, search-space path resolution, expectations referencing produced metrics, DataRefinery binding cross-checks); never short-circuits.
- Deterministic `init` scaffolder; optional LLM enhancement layer via `lmentry` as an extra (mirrors DataRefinery).
- Loose-coupled DataRefinery binding (FR-ARCH-1 analog): bound instance hash does not participate in the consuming recipe's cache identity in the pre-production release; tight coupling deferred to a future schema-version bump.
- Forward-declared dependency contracts: ModelFoundry's `vendor-dependency-spec.md` (for `modelmetrics` / `modelmachine` / future tools) authored at the pre-production release, mirroring DataRefinery's vendor-dependency-spec discipline.
- Error contract: `ModelfoundryError` base with `RecipeError`, `ValidationError`, `PluginError`, `DataBindingError`, `MaterializeError`, `ModelArtifactExistsError`, `OptimizationError`, `ExpectationError`, `CacheError` hierarchy.
- `rich`-based CLI ergonomics (per-epoch tables, per-trial progress, cache hit/miss) + stdlib `logging` JSON-lines operational channel; Optuna trial output suppressed at fd-level for trials > 0.

**Out of scope (pre-production release):**

- Data prep, splits, cleaning, sampling, tokenization, feature engineering — owned by DataRefinery; ModelFoundry consumes a materialized instance.
- Notebook generation, lifecycle templates, embeddable exercise compilation — owned by nbfoundry.
- Curriculum scaffolding, learner-facing UI, grading — owned by learningfoundry.
- Inference-serving infrastructure beyond `ModelInstance.predict()` — production serving, drift detection, batch scoring at scale belong to a future `modelmachine` / `datamachine`.
- Resume-from-stage during materialization — atomic temp-then-promote is the pre-production failure model (matches DataRefinery).
- All backends day-1 — PyTorch ships end-to-end; additional backends are stubs validating the plugin interface.
- Recipe inheritance and multi-file recipe composition — `variants` suffice for the pre-production release.
- Tight-coupled DataRefinery binding (bound `recipe_hash` participating in cache identity) — deferred to a future schema-version bump.
- Hard LLM dependency — `init` LLM enhancement is opt-in via `lmentry`; the deterministic path runs offline.
- Marimo-specific reactivity, Jupyter-specific magics, or any other notebook-substrate-specific integration — ModelFoundry stays substrate-neutral; substrate-specific affordances are nbfoundry's (or the user's) concern.
- Distributed training, multi-node orchestration, accelerator pool management — single-host execution against the env's accelerator (CUDA / MPS / CPU per plugin support).

### Constraints
**Technical (inherited project conventions):**

- Python 3.12.x pinned (`.tool-versions`); environments managed by `pyve` with a venv multi-env layout (`root` + `testenv` + lazy `smoke-pytorch` / `typecheck`, with `smoke-tensorflow` / `smoke-huggingface` placeholders); see [`env-dependencies.md`](env-dependencies.md).
- `pyproject.toml` + `pyve.toml`; `hatchling` build backend; editable install in dev; CLI via `pyproject.toml` entry points.
- Tooling: `ruff` (lint + format) + the framework-agnostic test suite in `testenv`, `mypy --strict` in `typecheck`, and the torch tests in `smoke-pytorch`; per the pyve essentials.
- YAML configuration, single file per recipe, schema-versioned.
- Content-addressed cache paths under a `./models/` tree by default (with `--cache-root` and `MODELFOUNDRY_CACHE_ROOT` overrides); parquet for tabular cached artifacts (trial history, training history, calibration); JSON for manifest / architecture / metrics / best-params.
- Every stochastic operation seeded; deterministic byte-equality between runs for unchanged inputs (excluding wall-clock fields).
- `rich`-based CLI output with per-epoch tables and per-trial progress; stdlib `logging` JSON-lines operational channel via `modelfoundry.logging.JsonFormatter` to `--log-target`.
- `check` command serves as the environment / installation / accelerator sanity check (mirrors DataRefinery).

**Architectural:**

- Library and CLI are co-equal surfaces; neither may grow capabilities the other lacks for the same operation (mirrors DataRefinery).
- Plugin interface must be honest — exercised by at least one non-default backend stub.
- Notebook-substrate-neutral: result accessors return `pandas.DataFrame` / `numpy.ndarray` / PNG `bytes`; no substrate-specific objects in the public API.
- No data prep in ModelFoundry — DataRefinery owns that surface entirely; ModelFoundry's `Data:` block is a binding, not a pipeline.
- Persistence is content-addressed and atomic; partial / corrupt instances never appear in the cache.
- Architecture must round-trip from `model/architecture.json` + weights alone; the sentiment-poc regression precedent (checkpoints unloadable without the original training-config object) must not recur.
- LLM features (if any) routed through `lmentry`; no provider lock-in; no hard LLM dependency.
- Loose-coupled DataRefinery binding in the pre-production release; tightening is a future `schema_version` bump, not a pre-production design point.

**Contract:**

- Honors DataRefinery's [`vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md) as the upstream contract: recipe-side `Augmentations` shape (lazy vs aggressive materialization), on-disk dataset layout (`dataset/<split>.jsonl` + sidecar PNGs under `<split>/images/`), per-record-seed stamps (`<AugmentationOp.name>_seed` for variants), manifest field set (`schema_version`, `plugin`, `plugin_version`, `recipe_hash`, `input_hash`, `seed`, `record_counts`, etc.), `report/drift.json` informational treatment pre-prod, and the schema-version coordination policy (hard error on higher-than-known recipe `schema_version`).
- Honors nbfoundry's [`consumer-dependency-spec.md`](nbfoundry/consumer-dependency-spec.md) as the downstream contract from the consumer side: BR-1..BR-12 (construction API, validation, materialization, status, inspection, report regeneration, `ModelInstance` notebook-shaped accessors, instance layout, loose-coupled DataRefinery binding, error contract, reproducibility, logging). The tightened Protocol shape replaces nbfoundry's current permissive stub on the pre-production release.
- ModelFoundry's own `vendor-dependency-spec.md` (for `modelmetrics` / `modelmachine` / replay harnesses) is forward-declared at the pre-production release, mirroring DataRefinery's pattern.

**Project / context:**

- License Apache-2.0; copyright Pointmatic; SPDX identifier `Apache-2.0` on every new source file (matches sibling projects).
- Purpose alignment: the pre-production path must support (a) a direct Python application consuming a DataRefinery instance, and (b) the nbfoundry lifecycle templates (`model_experimentation`, `model_optimization`, `model_evaluation`) without manual workarounds; both use the same `ModelFoundry.from_recipe(...).materialize()` surface.
- Integrates with the related-tools chain (DataRefinery upstream; nbfoundry / learningfoundry as opinionated downstream consumers; future `modelmetrics` / `modelmachine` / `datamachine` consumers of the `ModelInstance` contract).
- Author working preferences (inherited from sibling projects): plan-first with moderate-sized review chunks; strong recommendations over option menus; concise, verified, citation-bearing prose; document chain concept → features → tech-spec → stories with revisions scoped to the active document.

**Open items carried into this concept (to be closed downstream):**

- Final names for `Architecture` sub-sections (encoder / adapters / heads / etc.) and the per-section operation vocabulary — owned by `plan_features`.
- Final list of static logical checks for `validate` — owned by `plan_features` / `plan_tech_spec`.
- Which second-and-third backends are stubbed in the pre-production release (sklearn first; Keras and/or HuggingFace TBD) — owned by `plan_features`.
- Open questions 1–7 from nbfoundry's consumer-dependency-spec carry forward: DataRefinery binding semantics (lazy `DataRefinery` vs eager `Instance` — recommendation: eager `Instance`), Optimization-then-Training auto-composition (recommendation: yes, mirror sentiment-poc Story H.l), per-backend smoke ownership (modelfoundry owns), CLI verb inventory (mirror DataRefinery), plugin extras for accelerator wheels, notebook-primitive boundary refinements (`.predictions`? `.predict()` + `.predict_proba()` split?), cache-root default (recommendation: `./models/`).

## Value Mapping

**framework_lock_in_user_code**:
  - The `plugin` recipe field is the single backend selector; ModelFoundry resolves it to a registered plugin that implements `Architecture` / `Loss` / `Optimizer` / `Training` / `Optimization` / `Evaluation` / `Visualizations` primitives — user code never imports `torch` / `tensorflow` / `keras` / `optuna` / `peft`.
  - The `ModelInstance` API returns framework-agnostic primitives (`pandas.DataFrame`, `numpy.ndarray`, PNG `bytes`); `.predict()` / `.predict_proba()` return numpy/pandas, never `torch.Tensor` or `tf.Tensor`.
  - The plugin model mirrors DataRefinery's `OperationSpec` / `plugins.discovery`, so adding a backend is a packaging concern, not a contract change for downstream consumers.

**training_loop_reinvention**:
  - The `Training` recipe section declares max epochs, batch size, early-stopping monitor, and checkpoint cadence; the plugin owns the loop implementation against a framework-agnostic interface.
  - `Loss`, `Optimizer`, and `Schedule` are first-class recipe entries with shared op names across plugins (`adamw`, `cross_entropy_class_weighted`, `reduce_on_plateau`), so changing backends does not require rewriting these sections.
  - `materialize()` runs the canonical stage order (Architecture → Optimization → Training → Evaluation → OutputExpectations → Visualizations → manifest → promote); the user does not write the orchestration.

**brittle_save_load**:
  - The on-disk layout writes the **full canonical Architecture block** to `model/architecture.json` alongside weights, so `ModelInstance.load(path).predict(X)` rebuilds the model from disk alone without an external config object — the sentiment-poc regression precedent is built into the contract.
  - The manifest pins `plugin`, `plugin_version`, and `schema_version` so a loader can refuse a checkpoint produced by an incompatible plugin version with a clear error rather than a silent reconstruction failure.
  - `tokenizer/` (when applicable) is persisted under `model/` so the HuggingFace plugin's instances round-trip without a separate tokenizer download.

**hyperparameter_search_coupling**:
  - `Optimization` is a stage of `materialize()`, not a separate verb; the recipe declares `sampler` / `pruner` / `n_trials` / `search_space` against framework-agnostic names — Optuna is never named in the recipe.
  - Trial history is persisted as `optimization/trials.parquet` matching Optuna's `study.trials_dataframe()` shape; `.trials` returns it as a `pandas.DataFrame` that notebook cells render directly.
  - `baseline_trial: enqueue_recipe_defaults` enqueues the recipe's hyperparameter values as trial 0, so the recipe-as-truth discipline survives optimization without a follow-up edit.
  - Optimization-then-Training composition: best-trial hyperparameters are merged into the recipe before Training runs in the same `materialize()` call (open question #2 from the consumer spec, recommendation locked here).

**non_repeatable_training**:
  - Every stochastic source is seeded: weight init, data shuffling, dropout, augmentation realization (consuming DataRefinery's `<AugmentationOp.name>_seed` per-record stamps from the vendor spec), and the Optuna sampler.
  - Same `(recipe, data_instance, seed, variant)` tuple produces a byte-identical `ModelInstance` directory excluding wall-clock fields; determinism is asserted by integration tests (mirrors DataRefinery's discipline).
  - `--seed` overrides the recipe seed and **participates in cache identity**, so ad-hoc reruns at a different seed cache distinctly instead of overwriting.

**evaluation_ad_hockery**:
  - `Evaluation` is a declarative recipe section: `splits`, `primary_metric`, `metrics` list (with `macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `accuracy`, `confusion_matrix`, `ece`, `calibration_curve` as named ops), and `comparison.baseline_model_id`.
  - Metric implementations live in plugins and are validated at `validate()` time; missing or misnamed metrics surface before training starts.
  - `evaluation/metrics.json`, `evaluation/confusion_matrix.npz`, and `evaluation/calibration.parquet` are persisted artifacts; `.evaluation` / `.confusion_matrix` / `.calibration` accessors return them as dicts of numpy/pandas primitives.

**train_eval_skew**:
  - Each operation declares applicable `splits`; train-only behavior (class-weighted loss with `weight_source: train`, fit-on-train statistics, early-stopping monitor on `val`) is explicit in the recipe and machine-checked by `validate()`.
  - Inputs are bound to a materialized DataRefinery instance; the same record schema and label schema flow through training and evaluation — no second code path to drift from.
  - The `Loss` / `Optimizer` / `Training` sections describe execution policy applied at training time only; `Evaluation` and `Visualizations` declare their own splits, so accidental train-only operations against `val` / `test` are caught at validate time.

**expectation_drift**:
  - `OutputExpectations` declares post-materialization assertions (e.g. `val_macro_f1 >= 0.55`); failures abort `materialize()` with a `FAILED` marker, mirroring DataRefinery's FR-23 — there is no "I forgot to check the metric" path.
  - `validate()` cross-checks that every `OutputExpectations` metric is produced by `Evaluation.metrics`, so a recipe asserting against a metric it does not compute is rejected before training starts.

**ad_hoc_caching**:
  - Cache identity is `SHA-256(canonical_recipe_bytes) ⊕ SHA-256(data_instance_hash) ⊕ seed`, truncated to 16 hex chars per component for the path; full digests live in `manifest.json` for audit.
  - Atomic temp-then-promote materialization (writes to `<cache-root>/instances/.tmp/<run-id>/`, `os.replace` on success, `FAILED` marker on failure) mirrors DataRefinery's `cache.atomic`: the cache only ever contains complete, valid instances.
  - Cache hits are constant-time (compute key + `path.exists()` + load manifest); the user never knows whether a run was a hit or miss, and never maintains cache invalidation by hand.
  - Loose-coupled DataRefinery binding (BR-9 analog): re-materializing upstream data does **not** auto-invalidate downstream models; the user re-materializes ModelFoundry explicitly when ready. Tight coupling is a future `schema_version` bump.

**notebook_unfriendly_outputs**:
  - `ModelInstance` accessors are designed for direct rendering: `.evaluation` → `dict[str, dict[str, float]]` (per-split metrics), `.metrics` → alias for `.evaluation`, `.confusion_matrix` → `dict[str, np.ndarray]`, `.calibration` → `pd.DataFrame | None`, `.predictions` → `pd.DataFrame | None`, `.trials` → `pd.DataFrame | None`, `.best_params` → `dict | None`, `.figures` → `dict[str, bytes]` (PNG bytes).
  - The substrate-neutral surface means a Jupyter cell, a Marimo cell, an IPython REPL, and a plain `.py` script all consume `ModelInstance` the same way — no substrate-specific adapter, no `display()` shim, no kernel coupling.
  - `inspect(view=...)` renders exploration-mode visualizations on demand; reporting-mode visualizations are persisted by `materialize()` and re-loadable via `instance.render_report()`.

**comparison_baseline_gap**:
  - `Evaluation.comparison.baseline_model_id` is a first-class recipe entry; the plugin resolves it (e.g. a HuggingFace model id, an sklearn estimator class) and scores it on the same held-out split alongside the candidate model.
  - Baseline metrics flow into `evaluation/metrics.json` and the report's comparison subsection; the notebook reads them off `.evaluation` without writing a second scoring path.

**data_modeling_blur**:
  - The `Data:` recipe block binds to a materialized DataRefinery `Instance` — ModelFoundry never splits, samples, cleans, normalizes, tokenizes, or feature-engineers. DD-1 from the consumer spec is enforced at the API level: `from_recipe(..., data=DataRefineryInstance)` rejects anything else.
  - `validate()` cross-checks the bound DataRefinery instance's label schema, num-classes, and split presence against the recipe's `Architecture` / `Evaluation` declarations before training starts.
  - The vendor spec's per-record-seed stamps and on-disk JSONL + sidecar PNG layout are consumed read-only; the modeling layer can replay the data side post-hoc but never mutates it.

**hand_off_contract_gap**:
  - The on-disk `ModelInstance` layout (`recipe.yaml` / `manifest.json` / `model/` / `training/` / `optimization/` / `evaluation/` / `report/`) is the durable interface for downstream tools — a future `modelmetrics`, `modelmachine`, or CI replay harness binds against it the same way ModelFoundry binds against DataRefinery's manifest.
  - The in-memory `ModelInstance` API shape is part of the contract (BR-7 from the consumer spec): adding optional accessors is non-breaking; removing or renaming requires a major-version bump with a matching consumer update.
  - ModelFoundry forward-declares its own `vendor-dependency-spec.md` at the pre-production release, mirroring DataRefinery's discipline, so downstream tools (and nbfoundry, when its consumer spec tightens past the current permissive Protocol) bind against an authoritative document rather than a reverse-engineered surface.
