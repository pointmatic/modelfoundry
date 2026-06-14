# concept.md — DataRefinery

This document defines why the `DataRefinery` project exists.
- **Problem space**: problem statement, why, pain points, target users, value criteria
- **Solution space**: solution statement, goals, scope, constraints
- **Value mapping**: Pain point to solution mapping

For requirements and behavior (what), see [`features.md`](features.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For an authoring-side walk-through of the recipe surface (section-by-section, fit-on-train discipline, variants, contracts, Filters-vs-Splits for class imbalance), see [`docs/guides/recipe-authoring.md`](../guides/recipe-authoring.md). For writing a third-party plugin (the `Plugin` protocol, `OperationSpec`, discovery), see [`docs/guides/plugin-authoring.md`](../guides/plugin-authoring.md). For project-specific must-know facts (workflow rules, hidden coupling, tool-wrapper conventions that the LLM would otherwise random-walk on), see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

## Problem Space

### Problem Statement
Preparing data for ML training is a recurring, specialized chore: setting up environments and accelerator drivers, exploring raw data, cleaning and transforming it, splitting train/val/test, generating features, and keeping all of that both reproducible across experiments and consistent between training and inference. The work is typically done in throwaway notebooks and scripts, the steps decay between projects, and the resulting artifacts are hard to hand off, replay, or audit. In coursework and research settings — where the focus is modeling, not data prep — each cohort and each project rediscovers the same gotchas.

**Why this problem exists:**
The problem persists because data prep sits at the intersection of three forces that resist commoditization:

- **Project-specific shape.** Every dataset has its own quirks (label encoding, metadata layout, class balance), so practitioners reach for a general-purpose stack (NumPy/Pandas/SciPy/Scikit-learn) and wire it together by hand each time. The stack is powerful but composable in many incompatible ways, so two practitioners solve the same problem differently.
- **Reproducibility requires discipline that's easy to skip.** Seeding every stochastic operation, persisting fitted statistics on the training split, replaying the same transformation chain at inference — none of it is hard individually, but under deadline pressure it gets shortcut, and the resulting train/inference skew shows up later as silent quality regressions.
- **Knowledge doesn't accumulate.** Notebook-based prep produces narrative artifacts, not declarative ones. There is no single object that says "this is what was done"; the truth is scattered across cells, files, and the practitioner's memory. Six months later — or for the next student in the curriculum — the steps have to be reconstructed.

### Pain Points
- **Tooling friction**: getting Python, accelerator drivers, and the scientific stack to cooperate consumes time that should go to modeling.
- **Exploration sprawl**: cleaning and transformation logic accumulates across notebooks and ad-hoc scripts with no canonical record of what was actually applied.
- **Train/inference skew**: transformations re-implemented at serving time drift from the training pipeline, producing silent quality regressions.
- **Reproducibility gaps**: unseeded stochastic ops and lost fitted statistics (normalization parameters, encoders) make "same data, same recipe, same result" aspirational rather than guaranteed.
- **Implicit splits and leakage**: train/val/test splits done in-line risk leakage (e.g., fitting normalizers before splitting, augmenting validation).
- **Augmentation discipline**: stochastic augmentation accidentally applied to validation/test inflates reported metrics.
- **Class-imbalance ad-hockery**: filtering, oversampling, and weighting strategies live in scattered code with no clear distinction between "remove data" and "weight at training time."
- **Cache invalidation by hand**: practitioners re-run pipelines to be safe, or skip re-running and trust stale outputs.
- **Knowledge decay**: between projects (and between cohorts), the prep playbook has to be reconstructed; specialized gotchas are relearned.
- **Hand-off friction**: downstream tools (training, evaluation, inference, drift detection) need a stable contract, but notebook outputs don't provide one.

### Target Users
- **Primary — deep-learning curriculum** (students and instructors) doing image classification. They need a reproducible, low-friction path from raw images to a training-ready dataset so the course can focus on modeling.
- **Secondary — ML practitioners on tabular and text problems** who want the same recipe-driven discipline outside imagery; served first via plugin stubs, later via full plugins.
- **Indirect beneficiaries — downstream tools** (ModelFoundry, ModelMetrics, ModelMachine, DataMachine) and their users, who consume DataRefinery instances and reports against a stable contract rather than hand-rolled outputs. The shape-binding contract is pinned in [`modelfoundry/vendor-dependency-spec.md`](modelfoundry/vendor-dependency-spec.md).
- **Indirect beneficiaries — notebook framework** (NbFoundry) and its users, who drive DataRefinery as a library + CLI inside Marimo cells. The interaction-binding contract (library entry points, CLI verbs, notebook-output ergonomics) is pinned in [`nbfoundry/vendor-dependency-spec.md`](nbfoundry/vendor-dependency-spec.md).
- **Adjacent — occasional data-prep practitioners** (data scientists, researchers) who don't do this daily and need the playbook captured in a tool rather than in muscle memory.
- **Negatively impacted by the status quo (and helped indirectly)** — reviewers, collaborators, and future maintainers who today have to reverse-engineer prep work from notebooks.

### Value Criteria
- **Time-to-training-ready**: elapsed time from raw data to a materialized dataset a downstream tool can consume.
- **Reproducibility guarantee**: same recipe + same inputs + same seed produces a byte-identical instance; deviations are detectable.
- **Train/inference parity**: transformations applied at training are replayable at inference without re-implementation.
- **Recipe legibility**: a colleague (or future self) can read the recipe and understand what the pipeline does without reading code.
- **Reusability within a category**: a recipe written for one image-classification dataset transfers to another with bounded edits.
- **Reduction in ad-hoc code**: prep work that previously lived in notebooks is captured declaratively in the recipe.
- **Clear failure modes**: failures during materialization leave inspectable temp state and never produce partial cached instances.
- **Offline operability**: the deterministic path works without network access; LLM assistance is strictly an enhancement layer.
- **Plugin-interface honesty**: a second category (tabular, ideally text) can be sketched against the same abstractions without those abstractions being "image with extra steps."

## Solution Space
`datarefinery` is a Python project to refine raw data into reproducible, training-ready datasets from a single recipe.

### Solution Statement
DataRefinery is a Python tool — usable as a library or a CLI — that compiles a single YAML **recipe** into a materialized **instance**: the recipe itself, the prepared dataset, the fitted statistics produced during preparation, and a report describing both. The recipe declares the data category, raw inputs, output contract, splits, contracts, filters, generation, transformations, augmentations, featurizations, and visualizations; each operation declares the stages and splits it applies to, so train-only behavior is explicit. DataRefinery executes the recipe deterministically, seeds every stochastic step, persists training-split statistics so the same preparation can be replayed at inference, and caches the result by the recipe's normalized semantic form plus raw-input hash plus seed. Re-running an unchanged recipe over unchanged inputs returns the cached instance unchanged; any semantic edit invalidates and rebuilds. A category-specific **plugin** contributes the operations that make sense for that data shape — Image (classification) ships first, with at least one additional category (tabular, ideally also text) sketched as a stub to keep the abstractions honest. An `init` command bootstraps a starter recipe from raw inputs deterministically, with an optional LLM enhancement layer for interpretive judgments.

### Goals
Mapped to the value criteria above:

- **Compress time-to-training-ready** by replacing per-project notebook wiring with a single recipe and a small set of CLI verbs (`init`, `validate`, `check`, `status`, plus pipeline-driving verbs).
- **Guarantee reproducibility** by seeding every stochastic operation and persisting fitted statistics with the instance, so the same recipe + inputs + seed produces an identical instance.
- **Eliminate train/inference skew** by making the recipe and persisted statistics the single source of truth that downstream tools (ModelMachine) replay at inference.
- **Make pipelines legible** through a declarative YAML recipe whose section names (`Input`, `Output`, `InputContracts`, `OutputExpectations`, `SampleData`, `Filters`, `Generation`, `Splits`, `Transformations`, `Augmentations`, `Featurizations`, `Visualizations`) describe intent without leaking into ML term collisions.
- **Enable reuse within a category** by keeping operations plugin-scoped and recipes self-contained; a recipe for one image-classification dataset transfers to another with bounded edits.
- **Cut ad-hoc code** by absorbing common prep work (splits, normalization, augmentation policy, class-imbalance handling) into recipe sections rather than scattered scripts.
- **Make failures inspectable** through atomic temp-then-promote materialization: partial instances never appear in the cache; failed runs leave a marked temp directory for diagnosis.
- **Stay operable offline** by keeping the deterministic scaffolder and full pipeline path free of network or LLM dependencies; LLM enhancement is strictly opt-in via `lmentry`.
- **Validate plugin-interface honesty** by sketching a second (and ideally third) category as a stub so category-agnostic abstractions are exercised, not just asserted.
- **Provide a stable downstream contract** via the report's drift-relevant subsection, which DataMachine consumes against a defined shape.

### Scope
**In scope (v1):**

- Recipe-driven pipeline with the section set above; explicit per-operation stage/split applicability.
- Schema-versioned YAML recipes; load-time refusal of unknown versions; documented migration path between versions.
- Materialized instance = recipe + dataset + fitted statistics + report. No statistical artifacts persisted outside the report.
- Cache identity from normalized semantic recipe form + raw-input hash + seed. Whitespace/key-order edits do not trigger rebuilds.
- Atomic temp-then-promote materialization; no partial instances in cache.
- Named **variants** within a recipe (any section, including `Filters`); experiment knobs are variants, not separate recipes.
- Class-imbalance handling split cleanly: removal lives in `Filters`; weighting/resampling-during-training lives in `Splits` as a strategy ModelFoundry honors.
- Image plugin scoped to **classification**.
- Tabular stub at minimum (recipe section list and operation outline); text stub strongly preferred.
- Python library API and CLI as co-equal surfaces.
- CLI verbs: `init`, `validate`, `check`, `status`, plus pipeline-driving verbs (names to be settled in features spec).
- `validate`: schema correctness plus an enumerated set of static logical checks (defined in features/tech spec).
- Deterministic `init` scaffolder; optional LLM enhancement layer via `lmentry` as an extra.
- Visualization output modes: exploration (on demand, not persisted) and reporting (persisted into the instance's report).
- Report whose drift-relevant subsection is a stable contract for DataMachine.
- `rich`-based CLI ergonomics with per-stage progress and structured tables.

**Out of scope (v1):**

- Image plugin tasks beyond classification (detection, segmentation) — accommodated by the plugin interface, not implemented.
- Model framework abstraction, training, evaluation, inference — owned by ModelFoundry, ModelMetrics, ModelMachine.
- Production streaming and drift-detection logic — owned by DataMachine.
- Persisted statistical artifacts beyond the report (no sidecar pickles, no separate stats files).
- Recipe inheritance and multi-file recipe composition — variants suffice for v1.
- Resume-from-stage during materialization — atomic temp-then-promote is the v1 failure model.
- Hard LLM dependency — DataRefinery must work fully offline.

### Constraints
**Technical (inherited project conventions):**

- Python 3.12.x pinned; environments managed by `pyve` with micromamba backend.
- `pyproject.toml` + `environment.yml`; `hatchling` build backend; editable install in dev; CLI via `pyproject.toml` entry points.
- Tooling: `ruff` (lint + format), `mypy --strict`, `pytest` with `pytest-cov`.
- YAML configuration, single file per recipe, schema-versioned.
- Parquet for tabular caches; content-addressed cache paths under a `data/` tree (`data/raw/`, `data/preprocessed/`, etc.).
- Every stochastic operation seeded; deterministic equality between runs at the byte level for unchanged inputs.
- `rich`-based CLI output with per-stage progress.
- `check` command serves as the environment/installation sanity check.

**Architectural:**

- Library and CLI are co-equal surfaces; neither may grow capabilities the other lacks for the same operation.
- Plugin interface must be honest — exercised by at least one non-image category stub.
- LLM features routed through `lmentry`; no provider lock-in.

**Project / context:**

- Purpose alignment: the v1 path must support a deep-learning curriculum for image classification end-to-end, without manual workarounds.
- Integrates with `LearningFoundry` (curriculum presentation) and the related-tools chain (ModelFoundry, ModelMetrics, ModelMachine, DataMachine) — DataRefinery's outputs are inputs to those tools.
- Author working preferences: plan-first with moderate-sized review chunks; strong recommendations over option menus; concise, verified, citation-bearing prose; document chain concept → features → tech-spec → stories with revisions scoped to the active document.

**Open items carried into this concept (to be closed downstream):**

- Names for pipeline-driving CLI verbs (materialize, report, etc.).
- Exact contents of the report's drift-relevant subsection (placeholder acceptable here; finalized before DataMachine work).
- Enumerated list of static logical checks for `validate` (deferred to features or tech spec).
- Whether the second plugin stub is tabular only or tabular + text (author leaning toward both; final scope set in features spec).

## Value Mapping
**Tooling friction**:
  - `check` command verifies the environment (installation, dependencies, accelerator availability) so setup problems surface as a clear diagnosis instead of opaque pipeline failures.
  - Inherited project conventions (`pyve` + micromamba, pinned Python 3.12.x, `pyproject.toml` + `environment.yml`) give a single reproducible install path; editable dev install plus entry-point-registered CLI removes ad-hoc PATH wiring.
  - The deterministic `init` scaffolder produces a working starter recipe from raw inputs without requiring network access or LLM credentials, so a new project becomes runnable in minutes.

**Exploration sprawl**:
  - The recipe is the single canonical artifact: every operation that touches the data is declared in YAML, with explicit stage/split applicability, eliminating the "what was actually applied?" question.
  - `Visualizations` are first-class recipe entries with declared output modes (exploration vs. reporting), so exploratory views are reproducible from the recipe rather than living in throwaway notebook cells.
  - The materialized instance's report is the persisted summary of the prepared dataset, replacing scattered notebook narratives with one document downstream consumers can read.

**Train/inference skew**:
  - A DataRefinery instance pairs the recipe with the fitted statistics produced from the training split, so inference-time tools (ModelMachine) replay the exact same transformations rather than re-implementing them.
  - Per-operation stage/split declarations make train-only behavior (augmentation, fit-on-train statistics) explicit in the recipe, preventing accidental reuse of training-only logic at inference.
  - Library and CLI are co-equal surfaces driven by the same recipe; there is no second code path at serving time to drift from the training path.

**Reproducibility gaps**:
  - Every stochastic operation is seeded; same recipe + same inputs + same seed produces a byte-identical instance.
  - Fitted statistics are persisted with the instance — not in sidecar files — so the replay contract is structural rather than conventional.
  - Cache identity uses the recipe's normalized semantic form (parsed, key-sorted, comments stripped) plus raw-input hash plus seed, so meaningful edits invalidate the cache and cosmetic edits do not, removing both stale-result risk and spurious rebuild churn.
  - Schema-versioned recipes with documented migrations prevent silent semantic drift across DataRefinery versions.

**Implicit splits and leakage**:
  - `Splits` is a dedicated recipe section with declared stratification, class-balance strategy, and seed — splitting is explicit, not in-line.
  - Each operation declares which stages and splits it applies to, so fit-on-train / apply-to-all patterns (e.g., normalization) cannot accidentally fit on the full dataset.

**Augmentation discipline**:
  - `Augmentations` is a distinct section from `Transformations` and `Generation`, each with different semantics (stochastic train-only vs. deterministic per-split vs. record-count-changing).
  - Operations declare applicable splits explicitly; augmentations applied to validation or test are caught by `validate`'s static logical checks rather than discovered after the fact.

**Class-imbalance ad-hockery**:
  - The recipe surface separates the two distinct concepts cleanly: imbalance handled by *removing* records lives in `Filters`; imbalance handled by *weighting or resampling at training time* lives in `Splits` as a sampling strategy ModelFoundry honors.
  - Imbalance experiments are expressed as named variants on `Filters` or `Splits` within a single recipe rather than as forked notebooks.

**Cache invalidation by hand**:
  - Content-addressed cache identity is computed by DataRefinery on every run; users do not maintain it manually.
  - Atomic temp-then-promote materialization guarantees the cache only ever contains complete, valid instances — there is no "is this output fresh?" question for the user to answer.
  - Failed runs leave a marked temp directory for inspection rather than corrupting the cache or requiring manual cleanup.

**Knowledge decay**:
  - The recipe captures the data-prep playbook in a portable, declarative artifact that survives between projects and cohorts; students inherit a working recipe rather than reconstructing one.
  - The plugin model concentrates category-specific knowledge (image-classification operations) in a reusable place, so practitioners write recipes against curated operations rather than rediscovering the relevant scientific-stack idioms each time.
  - Schema versioning and documented migrations let recipes age gracefully across DataRefinery releases.

**Hand-off friction**:
  - The materialized instance is the contract downstream tools bind against: `Output` declares the structural shape (record layout, field names, dtypes); `OutputExpectations` covers value-range and distributional assertions on the materialized data.
  - The report's drift-relevant subsection is a stable, defined contract DataMachine reads against — handoff is structural, not narrative.
  - `status` summarizes instance lifecycle and configuration so downstream users can confirm what they are consuming.
