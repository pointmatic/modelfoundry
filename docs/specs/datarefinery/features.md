# features.md -- DataRefinery (Python 3.12.x)

This document defines **what** the `DataRefinery` project does -- requirements, inputs, outputs, behavior -- without specifying **how** it is implemented. This is the source of truth for scope.

For a high-level concept (why), see [`concept.md`](concept.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For project-specific must-know facts that future LLMs need to avoid blunders, see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Project Goal

DataRefinery compiles a single YAML **recipe** — declaring data category, raw inputs, output contract, splits, contracts, filters, generation, transformations, augmentations, featurizations, and visualizations — into a materialized **instance**: the recipe itself, the prepared dataset, the fitted statistics produced during preparation, and a report describing both. Re-running an unchanged recipe over unchanged inputs returns the cached instance unchanged; any semantic edit invalidates and rebuilds. A category-specific **plugin** contributes the operations relevant to that data shape; v1 ships an Image (classification) plugin, with tabular and text plugins stubbed to validate that category-agnostic abstractions are honest. DataRefinery is exposed as co-equal Python library and CLI surfaces, runs fully offline by default, and treats reproducibility as a first-class concern: every stochastic operation is seeded, fitted statistics are persisted with the instance, and cache identity is computed from the recipe's normalized semantic form so cosmetic edits never trigger rebuilds.

### Core Requirements

- **Production release.** Production release marks a transition in requirements as noted below, where pre-production requirements are relaxed. Production release is a declared event, not a version number.
- **Recipe-driven pipeline.** A single YAML recipe declares the entire preparation pipeline; the recipe is the only canonical artifact describing what the pipeline does.
- **Materialized instance.** Each successful pipeline run produces an instance composed of (recipe, prepared dataset, fitted statistics, report). All four are required for the instance to be considered complete.
- **Schema-versioned recipes.** Each recipe declares a schema version. DataRefinery refuses to load a recipe whose version it does not recognize. Prior to production release, schema version 1 itself may be redefined as the design evolves and there is no migration path between versioned recipes. After production release, schema versions are immutable and a documented migration path between versions ships with the tool.
- **Determinism.** Same recipe + same inputs + same seed must produce a byte-identical instance. Every stochastic operation is seeded.
- **Semantic cache identity.** Cache identity is derived from the recipe's normalized semantic form (parsed, key-sorted, comments stripped) plus raw-input hash plus seed. Whitespace or key-order edits do not trigger rebuilds; semantic edits do.
- **Atomic materialization.** Pipeline runs write to a temp location and atomically promote on success. On failure, the temp directory is left in place with a marker for inspection. Partial instances never appear in the cache.
- **Train/inference parity.** Fitted statistics produced from the training split are persisted with the instance so downstream tools (ModelMachine) can replay the same transformations at inference without re-implementation.
- **Plugin model.** A plugin specializes DataRefinery for a single data category and contributes the operations that make sense for that shape. v1 ships Image (classification) implementation plus tabular and text stubs (recipe section list and operation outline only).
- **Co-equal surfaces.** Python library API and CLI cover the same capabilities; neither grows operations the other lacks.
- **Variants.** A recipe may declare named variants on any section (including `Filters` and `Splits`); a new instance is materialized per variant. Recipe inheritance is out of scope for v1.
- **Offline operability.** The deterministic path (scaffolder, validation, materialization, reporting) works with no network access. LLM enhancement is strictly opt-in.

### Operational Requirements

- **CLI verbs.** Lifecycle and pipeline verbs are: `init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`. Each verb has a library equivalent.
- **Rich-based CLI ergonomics.** Per-stage progress bars, structured tables, color-aware output via `rich`. Output degrades cleanly in non-TTY contexts.
- **Diagnostic failures.** Failed materialization preserves the temp directory with a clear marker; failed validation produces structured, actionable error messages naming the offending section and field.
- **Logging.** Stdout/stderr are reserved for `rich` user-facing output; structured operational logs (level, timestamp, stage, op-id) go to a configurable log target. Default level is `INFO` for the CLI; library callers control their own logger.
- **Configuration precedence.** Recipe file → CLI flags → environment variables. The recipe is authoritative for data-pipeline semantics; CLI flags and env vars only control execution context (cache root, log level, seed override for ad-hoc runs, plugin search path).
- **Cache management.** A predictable on-disk layout under a configurable root (default `data/`); `clean` operates on cache entries by recipe hash, age, or marker.
- **Plugin discovery.** Plugins are discovered via `pyproject.toml` entry points; a plugin search path may be extended via configuration for development.
- **API and CLI surface stability.** Prior to production release, the library API, CLI verb names, and flag names may change without migration shims; deprecation aliases are best-effort. After production release, the public surface follows semver-style stability with documented deprecations.
- **Cache layout stability.** Prior to production release, a DataRefinery upgrade may invalidate all existing cached instances; users re-materialize. After production release, the cache layout is versioned and old instances remain readable, or `clean --upgrade` provides a documented migration path.
- **Materialize concurrency.** Prior to production release, `materialize` is serialized: running two materializations against the same cache root concurrently is unsupported. After production release, a file-lock-based concurrency protocol coordinates concurrent runs.

### Quality Requirements

- **Reproducibility guarantee.** A successful run is byte-identical when re-executed against unchanged inputs and seed. Any deviation is a defect.
- **Minimal runtime dependencies.** v1 depends on the standard scientific Python stack (NumPy, Pandas, SciPy, Scikit-learn), `rich`, `pyyaml`, and `pyarrow`. The Image plugin adds image-handling dependencies (Pillow at minimum). Optional extras: `[llm]` (`lmentry`) for the `init` scaffolder's LLM-enhancement layer; `[corruptions]` (`scikit-image`, `opencv-python-headless`) for the `imagecorruptions_apply` robustness-evaluation Generation op (the corruption *vocabulary* is in-tree so recipe validation works without the extras; only execution requires them).
- **Cross-platform.** Prior to production release, macOS is the only first-class platform; Linux is best-effort. After production release, Linux and macOS are both first-class. Native Windows is best-effort in any release (CI smoke only); Windows users are not left behind because WSL2 (Microsoft-supported Linux on Windows) provides the full Linux path on the same hardware, and the project documents WSL2 as the recommended Windows experience.
- **Hardware acceleration.** GPU acceleration is a bonus, not a requirement, in any release; pipelines must function correctly on CPU. Metal (Apple Silicon) compatibility is top-priority where acceleration is exercised; CUDA is supported as available. `check` reports acceleration availability without requiring it.
- **Type discipline.** `mypy --strict` clean across the package and plugin sources.
- **Lint and format discipline.** `ruff` (lint and format) clean.
- **Test coverage.** Coverage on core invariants (recipe loader, schema-version gate, cache identity computation, splits/seeding, plugin interface, atomic promote/rollback) ≥ 95% in any release — these tests are cheap to write alongside the code and prohibitively expensive to retrofit. Prior to production release, the project-wide 85% line-coverage gate is relaxed; every FR must be exercised by at least a smoke test, but no overall percentage threshold applies. After production release, overall line coverage ≥ 85%.

### Usability Requirements

- **Primary user — deep-learning curriculum.** A student or instructor can take raw image data and produce a training-ready instance for an image-classification dataset (CIFAR-10-scale) using the deterministic `init` scaffolder followed by `validate` and `materialize`, without manual workarounds.
- **Secondary user — ML practitioner.** A practitioner familiar with the standard scientific Python stack can read a recipe and understand the pipeline without reading DataRefinery source.
- **Co-equal surfaces.** Library users compose `DataRefinery` objects programmatically; CLI users invoke verbs against a recipe path. Both produce identical instances given the same inputs.
- **Discoverable installation.** End users install DataRefinery via `pip install ml-datarefinery` from a clean Python 3.12 venv with no extra configuration. The distribution name (`ml-datarefinery`) diverges from the import name and console script (both `datarefinery`); the install command is the only place users see the prefixed name.
- **Recipe legibility.** Section names use intent-driven vocabulary (`InputContracts`, `SampleData`, `OutputExpectations`, `Filters`, `Generation`, `Splits`, `Transformations`, `Augmentations`, `Featurizations`, `Visualizations`) chosen to avoid collision with standard ML terminology.

### Non-goals

- **Image plugin tasks beyond classification** (detection, segmentation). The plugin interface accommodates them; no implementation in v1.
- **Model framework abstraction, training, evaluation, inference.** Owned by ModelFoundry, ModelMetrics, ModelMachine.
- **Production streaming and drift-detection logic.** Owned by DataMachine. DataRefinery contributes only the report's drift-relevant subsection (placeholder in v1).
- **Persisted statistical artifacts beyond the report.** No sidecar pickles, no separate stats files outside the instance's report and persisted fitted-statistics block.
- **Recipe inheritance and multi-file recipe composition.** Variants suffice for v1.
- **Resume-from-stage during materialization.** Atomic temp-then-promote is the v1 failure model.
- **Hard LLM dependency.** DataRefinery must work fully offline. LLM assistance during `init` is an optional enhancement layer only.
- **Tabular and text plugin implementations.** v1 ships stubs (recipe section list and operation outline only); no working operations.
- **Hard performance targets.** v1 does not commit to throughput, latency, or memory targets; performance work happens reactively, in response to observed problems on representative workloads.
- **`init` for non-image categories.** v1 deterministic scaffolder supports Image only; tabular and text recipes are written by hand against the stub plugin sections.

---

## Inputs

**Raw data sources** (declared in the recipe's `Input` section):

- One or more declared sources. Each source has a type (e.g., directory of image files, parquet file, CSV file) and a path or URI.
- Sources are independent in v1: cross-source joins (records from source A joined with records from source B by a shared key) are out of scope. The one form of join the v1 image plugin supports is sidecar-manifest label joining within a single source via `InputSource.label_from`, where a CSV manifest supplies labels for an `image_flat` directory.
- Per-record metadata available alongside the primary content (filenames, directory paths, sidecar files) is addressable in derived operations.
- Example (image classification — ImageFolder layout, class subdirectories provide labels):
  ```yaml
  Input:
    sources:
      - name: images
        type: image_folder
        path: data/raw/cifar10/train
  ```
- Example (image classification — flat directory + sidecar manifest):
  ```yaml
  Input:
    sources:
      - name: images
        type: image_flat
        path: data/raw/myset/images
        label_from:
          path: data/raw/myset/labels.csv
          join: by_id
          id_field: filename
          label_field: class
  ```
- Example (image classification — pre-partitioned Kaggle-style `train/` + `test/`):
  ```yaml
  Input:
    sources:
      - name: train_data
        type: image_folder
        path: data/raw/myset/train
        partition: train
      - name: test_data
        type: image_folder
        path: data/raw/myset/test
        partition: test
  ```
- Example (image classification — labeled `train/` + **unlabeled** `test/` for downstream inference):
  ```yaml
  Input:
    sources:
      - name: train_data
        type: image_folder
        path: data/raw/myset/train
        partition: train
      - name: test_data
        type: image_flat
        path: data/raw/myset/test
        partition: test
        unlabeled: true
  ```
  Records loaded from the `test_data` source land without a `label` field; the partition flows through label-independent transformations (resize, normalize) and lands in the materialized instance for downstream inference. Label-dependent stages (`stratify_by`, `filter_by_label`, label-reading featurizations) are rejected at validate time when they target an unlabeled split (check 21).

**Recipe file** (single YAML file):

- Schema version declaration (top-level `schema_version`).
- Plugin declaration (top-level `plugin`).
- Section declarations matching the recipe section set.
- Optional `variants` block declaring named overrides.
- Example skeleton:
  ```yaml
  schema_version: 1
  plugin: image_classification
  Input: { ... }
  Output: { ... }
  Labels: { ... }
  SampleData: { ... }
  InputContracts: [ ... ]
  Filters: [ ... ]
  Generation: [ ... ]
  Splits: { ... }
  Transformations: [ ... ]
  Augmentations: [ ... ]
  Featurizations: [ ... ]
  OutputExpectations: [ ... ]
  Visualizations: [ ... ]
  variants:
    no_augment:
      Augmentations: []
  ```

**Seed** (CLI flag `--seed` or recipe field; recipe wins on conflict; CLI flag overrides for ad-hoc runs and changes the cache identity).

**Configuration** (CLI flags / environment variables, in the configuration precedence order above):

- `--cache-root` / `DATAREFINERY_CACHE_ROOT` — root directory for cache (default `data/`).
- `--log-level` / `DATAREFINERY_LOG_LEVEL` — operational log level.
- `--plugin-path` / `DATAREFINERY_PLUGIN_PATH` — extra plugin discovery paths (development).
- `--variant` — selects a named variant from the recipe at materialize time.

## Outputs

**Materialized instance** (atomic directory under the cache root, addressed by recipe hash + raw-input hash + seed):

```
data/instances/<recipe-hash>/<input-hash>/<seed>/
├── recipe.json                  # canonical post-loader recipe (v2-shape, key-sorted, the bytes hashed for the cache key)
├── dataset/                     # the prepared dataset (parquet for tabular; plugin-defined layout for image/text)
├── fitted_statistics/           # statistics fitted on the training split (persisted, not pickled sidecars)
├── report/
│   ├── report.md                # human-readable summary
│   ├── drift.json               # drift-relevant subsection (stable contract; v1 placeholder schema)
│   └── visualizations/          # rendered reporting-mode visualizations
└── manifest.json                # instance metadata (hashes, seed, plugin, schema version, timestamps)
```

**Console output** (CLI):

- Per-stage progress bars (`rich`).
- Structured tables for `status`, `inspect`, and `validate` results.
- Final summary: instance path, cache hit/miss, elapsed time, key counts (records, splits).

**Failure artifacts:**

- Temp directory at `<cache-root>/instances/.tmp/<run-id>/` left in place on failure with a `FAILED` marker file containing the failing stage, error class, and message.

---

## Functional Requirements

### FR-1: Recipe Loading and Schema Versioning

Load a YAML recipe, validate its schema version, and produce an in-memory recipe object.

**Behavior:**
1. Parse the YAML file.
2. Read `schema_version`; refuse to load if absent or unrecognized.
3. Apply schema-version migrations if a documented migration exists for the declared version.
4. Construct the recipe object with all declared sections.

**Edge Cases:**
- Missing `schema_version` -> hard error naming the missing field.
- Unrecognized `schema_version` -> hard error listing supported versions and the documented migration path.
- Malformed YAML -> structured error pointing to the offending line.
- Unknown top-level keys -> warning (forward-compatible recipes are not valid; readers should fail loudly).

### FR-2: Recipe Validation (`validate`)

Verify a recipe's correctness without running the pipeline. Covers schema correctness and an enumerated set of static logical checks.

**Behavior:**
1. Run schema validation (FR-1).
2. Run the enumerated static logical checks (see list below) and report each result.
3. Exit with non-zero status on any failure; produce a structured table (CLI) or a result object (library) listing each check, status, and offending location.

**Enumerated static logical checks (v1):**

1. Recipe schema version is recognized.
2. Plugin name is recognized and discoverable on the configured plugin path.
3. All section names declared in the recipe are valid for the declared plugin.
4. Every operation in `Filters`, `Generation`, `Transformations`, `Augmentations`, `Featurizations`, and `Visualizations` declares the stages and splits it applies to.
5. `Augmentations` operations are not declared on the validation or test splits.
6. Fit-on-train transformations (e.g., normalization) declare the training split as the fit source.
7. Operations in `Transformations`, `Augmentations`, `Featurizations`, and `Filters` reference only fields declared in `Input`, `Labels`, or produced by upstream sections.
8. `Splits` ratios sum to ≤ 1.0 (ratio-based splits) or partition the data exactly once (key-based splits); split names are unique.
9. Stratification keys referenced in `Splits` exist in the data declaration.
10. Class-imbalance strategy is declared in exactly one of `Filters` (removal) or `Splits` (weighting/resampling) per imbalance concern.
11. `Visualizations` operations each declare an output mode (`exploration` or `reporting`).
12. `variants` reference only declared sections and override only declared keys.
13. `Labels` source is declared and resolvable from the declared inputs.
14. `Generation` operations produce records whose schema is consistent with `Output`.
15. No operation references a split name that is not defined in `Splits`.
16. `SampleData` declaration is resolvable to a strict subset of the prepared dataset. Selector coherence is enforced at validate time (`n` xor `fraction`; bounds; `kind: per_class` requires a label source; `splits:` entries must match a defined split). Strict-subset enforcement is structural — the runtime stage (FR-J-1, Story J.a) produces `<= len(split)` records per selected split.
17. `InputContracts` and `OutputExpectations` reference only fields that exist at the relevant pipeline stage.
18. Plugin-specific operation parameters validate against the plugin's declared operation schemas.
19. `label_from_spec_resolves` — `InputSource.label_from` is structurally valid; manifest file at `label_from.path` exists; declared `header` (when present) matches the file's column count; `id_field` / `label_field` reference columns that resolve; no duplicate ids for `join: by_id`; row count matches enumerated record count for `join: by_row_order`; source-type consistency (`image_folder` + `label_from` is rejected; `image_flat` without `label_from` is rejected). Plugin-specific: only applies to `image_classification` in v1.
20. `partitions_consistent` — `InputSource.partition` declarations are all-or-nothing across sources; `partition` is not declared in `Output.record_schema` (reserved name); `Splits.applies_to` (when set) references a declared partition; `Splits.ratios` keys do not collide with sibling partition names when `applies_to` is set; `Splits.ratios` is empty (or unset) when source partitions are declared and `applies_to` is unset. Plugin-specific: only applies to plugins whose loader stamps `partition` (initially `image_classification`).
21. `unlabeled_consistency` — `InputSource.unlabeled` cross-section consistency. `unlabeled: true` requires `type: image_flat` (v1 restriction; `image_folder` derives labels from class subdirectories so the combination is contradictory). Model-level validation already enforces that `unlabeled: true` requires `partition` and forbids `label_from`. `Splits.stratify_by` is rejected when `Splits.applies_to` names an unlabeled partition (no label field to stratify by). Filters using `filter_by_label` and Featurizations using `label_from_path` (or whose `inputs` reference the recipe's label field) are rejected when they target unlabeled splits. Plugin-specific: only applies to plugins whose loader honors `unlabeled` (initially `image_classification`).
22. `stats_from_instance_mutually_exclusive_with_fit_source` — a `Transformations` op's `params["stats_from_instance"]` (FR-TRANS-1) and the op's `fit_source` field are mutually exclusive; declaring both is contradictory (the former imports fitted statistics from a sibling instance, the latter triggers a local fit), and check 6 short-circuits the fit-on-train requirement when `stats_from_instance` is set. The check additionally parses the spec against `StatsFromInstanceSpec` (`recipe: str`, `op_id: str`) so a misshapen spec surfaces at validate time rather than at materialize time.
23. `featurization_output_field_loader_collision` — a `Featurizations` op's `output_field` must not collide with a field the input loader stamps on every record (the runtime's `pipeline.stages.featurizations` collision check is the authoritative second-line defense; this check shifts the failure left to validate time). The image_classification loader stamps `record_id`, `image`, and `path` always; `label` when `Labels.source.kind == "direct"` and a label source exists (parent directory for `image_folder`; `label_from` sidecar for `image_flat`); `partition` when any `InputSource.partition` is declared. Plugin-specific: only applies to plugins whose loader stamps these fields (initially `image_classification`).

**Edge Cases:**
- Plugin not installed -> hard error pointing at the plugin name and discovery path.
- Multiple failures -> all are reported; `validate` does not short-circuit on the first failure.
- Unknown operation under a known plugin -> reported as a plugin-specific operation-schema failure (check 18).
- Optional-extras-gated op referenced in a recipe but extras not installed -> recipe-time checks that depend only on the in-tree vocabulary still fire (e.g., `imagecorruptions_apply` corruption-name validation in check 18); execution-time errors are deferred to materialization, with a clear extras-install pointer.

### FR-3: End-to-End Materialization (`materialize`)

Execute the recipe end-to-end and produce a materialized instance.

**Cross-repo contract — interaction-binding surfaces.** The library API (`DataRefinery.from_recipe`, `.materialize`, `.validate`, `.status`, `.inspect`, the top-level `materialize()` convenience, the `Instance` accessor) and the CLI surface (verb names, global + verb-specific flags, exit codes, error-message panel-title contracts, stdout/stderr discipline) are documented as cross-repo contract surfaces in [`nbfoundry/vendor-dependency-spec.md`](nbfoundry/vendor-dependency-spec.md). Changes to either follow the cross-repo coordination rule in [`project-essentials.md`](project-essentials.md) § "Recipe / manifest / report shape changes need a cross-repo coordination check."

**Behavior:**
1. Run `validate` (FR-2); fail fast on any failure.
2. Compute the cache identity (FR-4); on cache hit, return the existing instance unchanged.
3. On cache miss, create a temp directory under `<cache-root>/instances/.tmp/<run-id>/`.
4. Execute pipeline stages in the recipe-declared order (FR-7 through FR-13), writing intermediate artifacts to the temp directory.
5. Persist fitted statistics computed on the training split (FR-6).
6. Render reporting-mode visualizations and write the report (FR-15).
7. Write `manifest.json` with hashes, seed, plugin, schema version, and timestamps.
8. Atomically promote the temp directory to the final cache path (FR-5).
9. Print a summary (cache hit/miss, instance path, elapsed time, key counts).

**Edge Cases:**
- Cache hit on identical inputs -> no work performed; return existing instance path with `cache=hit` in the summary.
- Failure mid-stage -> temp directory left in place with `FAILED` marker; cache untouched (FR-5).
- Variant selected via `--variant` -> cache identity reflects the variant's normalized recipe form; different variants of the same recipe produce different instances.
- Stage flag (e.g., `--stage=raw`) -> partial run that materializes only up to and including the named stage; result is not promoted as a full instance and is marked partial in the manifest.

### FR-4: Semantic Cache Identity

Compute a stable identity for a (recipe, inputs, seed) triple that is invariant to cosmetic edits.

**Behavior:**
1. Parse the recipe; strip comments; canonicalize key order and value representations.
2. Hash the canonicalized form.
3. Hash the declared raw inputs (content hash for files; declared identifier hash for external sources where direct hashing is not feasible).
4. Combine the recipe hash, input hash, and seed into the cache key.

**Edge Cases:**
- Whitespace-only or comment-only edit -> identical hash; cache hit.
- Key reordering -> identical hash; cache hit.
- Semantic edit (changed value, added/removed operation) -> different hash; cache miss.
- Raw input file content changes -> different input hash; cache miss.
- Variant selection -> the normalized form includes the variant overlay; different variants produce different recipe hashes.
- Sibling-instance references (FR-TRANS-1 `stats_from_instance`) are **loose-coupled in v1**: the sibling recipe's `recipe_hash` does NOT participate in this recipe's cache identity. Re-materializing upstream does NOT auto-invalidate downstream — when upstream changes (e.g., the train recipe is re-fit and re-materialized), the user is responsible for re-materializing any downstream eval recipes that import its statistics. Tight coupling (sibling `recipe_hash` participates in cache identity, so upstream changes auto-invalidate downstream) is a documented Future upgrade tracked under FR-ARCH-1; it will be a `schema_version` bump.

### FR-5: Atomic Temp-then-Promote Materialization

Guarantee the cache contains only complete, valid instances.

**Behavior:**
1. All pipeline writes target the temp directory.
2. On successful completion, the temp directory is renamed to its final cache path in a single filesystem operation.
3. On failure, the temp directory is left in place with a `FAILED` marker; the final cache path is never touched.

**Edge Cases:**
- Process killed mid-run -> orphaned temp directory; `clean` removes orphans older than a configurable threshold.
- Filesystem rename across devices -> not supported; temp and cache must share a filesystem (documented requirement).
- Concurrent `materialize` calls for the same cache key -> pre-production: serialized externally by the user; running two against the same cache root is unsupported. Post-production: a file-lock-based protocol detects the temp directory and either waits or refuses (configurable; default refuse with clear error).

### FR-6: Fitted Statistics Persistence

Persist statistics fitted on the training split so the same preparation can be replayed at inference.

**Behavior:**
1. Operations that fit statistics (e.g., normalization parameters, encoder vocabularies) declare so in their plugin operation schema.
2. Statistics are fitted only on the training split.
3. Statistics are written to `fitted_statistics/` in a structured format (parquet for tabular stats, plugin-defined for others) — never as opaque pickles.
4. The instance's library API exposes the fitted statistics for downstream replay.
5. The same `fitted_statistics/<op_id>/` layout is also the **producer** side of FR-TRANS-1 `stats_from_instance`: a materialized instance's persisted fitted statistics are addressable by *other* recipes that reference this recipe via `stats_from_instance`, so train/inference parity holds when training and evaluation live in separate recipes.
6. On the **consumer** side, imported statistics are **read-through, not copied**: when a recipe imports fitted statistics via `stats_from_instance`, the apply phase reads directly from the sibling instance's `fitted_statistics/<op_id>/` and does not duplicate the bytes into the consuming instance's own `fitted_statistics/`. The consuming instance therefore has no `fitted_statistics/<op_id>/` for ops that import their stats — this is intentional, so the materialized output honestly reflects "stats are owned by the sibling," not "stats are owned here too."

**Edge Cases:**
- Operation that requires fitting but is not declared on the training split -> caught by `validate` (check 6).
- Statistics block missing on read -> instance is invalid; `inspect` reports the missing block.
- Sibling-instance fitted statistics referenced via `stats_from_instance` but the sibling has not been materialized (or has been cleaned) -> caught at materialize time with a clear "sibling instance not found" error pointing at the recipe path and the cache root.

### FR-7: Splits

Define train/validation/test partitioning, including stratification, class-balance handling, and seed.

**Behavior:**
1. Splits is a dedicated recipe section; splitting is never inline.
2. Each split is declared by name with a ratio (or key-based assignment), optional stratification key, and optional class-balance strategy.
3. The split seed is the recipe-level seed unless overridden.
4. Class-imbalance handled by *weighting or resampling at training time* lives in `Splits` as a sampling strategy ModelFoundry honors. Class-imbalance handled by *removing data* lives in `Filters` (FR-8).
5. When `Input.sources[*].partition` is declared on every source, the materialized splits honor those declarations (each partition becomes a split). Setting `Splits.applies_to: <partition-name>` together with `ratios: {...}` sub-partitions just that partition; sibling partitions are preserved verbatim (so `test` can stay heldout while `train` is carved into train/val). When `applies_to` is unset, `Splits.ratios` must be empty (or omitted) — declared partitions are the final partitioning.
6. When a source declares `unlabeled: true`, the resulting split (or sub-splits, if `applies_to` selects the unlabeled partition) materializes without a `label` field. `Splits.stratify_by` is rejected when `applies_to` names an unlabeled partition (check 21); sub-partitioning an unlabeled partition is allowed and produces unlabeled sub-splits.

**Edge Cases:**
- Ratio-based splits summing to less than 1.0 -> remainder is unassigned; recorded in the manifest.
- Stratification key with sparse classes -> reported as a warning during materialization with class counts per split.
- Key-based splits with unmapped records -> hard error during materialization.
- Some sources declare `partition` and some do not -> caught by `validate` (check 20).
- `Splits.applies_to` set but no source declares `partition` -> `MaterializeError` (defensively re-checked at load time even though check 20 catches it earlier).

### FR-8: Filters

Reduce the raw set by sampling or by inclusion/exclusion rules.

**Behavior:**
1. Each filter declares its predicate, the stages and splits it applies to, and any seed (for sampling).
2. Filters apply before splitting unless explicitly declared on a post-split stage.
3. Filters that remove data for class-balance reasons are declared in `Filters` and noted as such.

**Plugin-contributed ops (image_classification, FR-FILTER-1):**

`sample_per_class` produces a balanced subsample of `n_per_class` records per label, drawn deterministically via per-record seeding (`pipeline.workers.per_record_seed`) so the selection is invariant to input ordering and worker count. Parameters: `n_per_class` (positive integer, required), `seed` (integer, required), `label` (optional string), `exclude_already_labeled` (optional list of strings). When `label` is omitted the op is destructive — only the chosen records pass through. When `label` is set the op is **non-destructive marking**: the full record set passes through with the chosen records tagged in `sample_per_class_tags`; a later op (another `sample_per_class` with `exclude_already_labeled`, or `drop_by_label`) performs the actual subset. `exclude_already_labeled` removes records carrying any of the named tags from the candidate pool before stratified selection.

**Disjoint-pool pattern.** Chaining two `sample_per_class` ops with the second referencing the first's `label` in `exclude_already_labeled` selects two non-overlapping balanced sets from one labeled source — useful when a canonical train/test split is unavailable, when evaluating fairness on a balanced holdout drawn from the same pool as training, or when constructing any pair of independent balanced sets in a single recipe.

`sample_per_class_fractional` extends `sample_per_class` to per-class rates. Parameters: `n_per_class_base` (positive integer, required), `fractions` (`dict[str, float]`, each value in `[0.0, 1.0]`; missing labels default to 1.0), `seed` (integer, required), plus inherited `label` and `exclude_already_labeled` semantics from `sample_per_class`. Per-class surviving count = `floor(n_per_class_base × fractions.get(label, 1.0))`; `fractions[label] = 0.0` drops that class entirely. The op shares the disjoint-pool tagging mechanism with `sample_per_class` — a `sample_per_class_fractional` op can chain with a `sample_per_class` op (or another `sample_per_class_fractional`) via `exclude_already_labeled` to construct controlled-imbalance datasets that are disjoint from a balanced training pool.

`drop_by_label` is the destructive companion to `sample_per_class` / `sample_per_class_fractional`. Parameter: `labels: list[str]` (non-empty). Records carrying any of the named tags in `sample_per_class_tags` are removed; records without the tag field or carrying only non-matching tags pass through unchanged. **Canonical use case (sibling-recipe split):** two recipes replicate the same `sample_per_class` (or `sample_per_class_fractional`) chain with identical ops, parameters, and seeds — producing the same tagged record set — then each calls `drop_by_label` with a disjoint `labels` list, peeling off byte-identical, non-overlapping sub-instances. Without `drop_by_label` the recipes would either re-pick non-deterministically (breaking cross-recipe bit-identity) or carry unused records through the rest of the pipeline (wasting materialization time and disk space).

**Edge Cases:**
- Filter that empties a class entirely -> warning during materialization.
- Sampling filter without seed -> caught by `validate` as a determinism violation.
- `sample_per_class` with `exclude_already_labeled` referencing a tag that no record carries -> the exclusion is a no-op; all records remain candidates.
- `drop_by_label` referencing a label that no record carries -> no-op pass-through; not an error.

### FR-9: Generation

Produce new records added to the dataset (e.g., SMOTE, oversampling, externally synthesized data).

**Behavior:**
1. Each generation operation declares its inputs, output schema (must match `Output`), and seed.
2. Generation changes record count; this is recorded in the manifest.
3. Generation runs at a recipe-declared point in the pipeline (typically post-split, train-only, but configurable).

**Plugin-contributed ops (image_classification, FR-GEN-1):**

`imagecorruptions_apply` applies Hendrycks-Dietterich (ICLR 2019, "Benchmarking Neural Network Robustness to Common Corruptions and Perturbations") image corruptions to each input record. For each input the op emits one output record per `(corruption_type, severity)` pair, optionally including an untouched copy tagged `corruption="none"`. Parameters: `corruption_types: list[str]` (non-empty; names drawn from the canonical 19-corruption vocabulary), `severities: list[int]` (each in `[1, 5]`, non-empty), `preserve_original: bool = False`, `tag_fields: list[str] = ["corruption", "severity", "source_path"]`. Output count per input record = `len(corruption_types) × len(severities)`, plus 1 untouched copy when `preserve_original=True`. Per-record corruption seeds are derived from the recipe master seed via the `pipeline.workers.per_record_seed` contract, so output bytes are reproducible across runs and worker counts. The implementation is vendored from upstream `imagecorruptions==1.1.2` (Apache-2.0; full attribution preserved) and patched for NumPy 2.x, scikit-image 0.21+, and deterministic seeding compatibility; the canonical corruption vocabulary is enumerable at recipe-validate time without the extras installed.

**Edge Cases:**
- Generated records that fail `OutputExpectations` -> hard error during materialization.
- Generation declared on validation or test splits -> not blocked by default (atypical but legitimate); flagged in the report.
- `imagecorruptions_apply` referenced in a recipe but the `[corruptions]` extras (`scikit-image`, `opencv-python-headless`) are not installed -> recipe-time validation still verifies the corruption names against the in-tree vocabulary; materialization fails at the corruption call site with a clear `ImportError` pointing at `pip install 'ml-datarefinery[corruptions]'`.

### FR-10: Transformations

Apply deterministic modifications to one or more splits (e.g., resize, normalize, Winsorize).

**Behavior:**
1. Each transformation declares its inputs, parameters, fit source (if any), and the splits it applies to.
2. Fit-on-train transformations fit on the training split, persist their statistics (FR-6), and apply across declared splits using the persisted statistics.
3. Transformations are deterministic given inputs and (where applicable) fitted statistics.

**Plugin-contributed parameter (image_classification, FR-TRANS-1):**

`stats_from_instance` is a parameter recognized on fit-on-train Transformations operations (v1: `normalize`) that imports fitted statistics from a **sibling materialized instance** instead of fitting locally. Shape:

```yaml
stats_from_instance:
  recipe: <filesystem path to the sibling recipe YAML>
  op_id: <name of the op inside the sibling recipe whose fitted_statistics/<op_id>/ should be read>
```

The op resolves the sibling instance by computing the sibling recipe's canonical hash, locating the most-recent matching promoted instance under the cache root, and reading `fitted_statistics/<op_id>/`. No local fit phase runs. `stats_from_instance` and `fit_source` are mutually exclusive (check 22): exactly one must be set on a fit-on-train op.

**Why the parameter exists.** Train/inference normalization parity is a correctness invariant — evaluation data must be normalized with the same statistics the model was trained against. When training and evaluation data live in the same recipe, `fit_source: train` already handles this. The gap appears when they live in separate recipes:

- **Distribution-shift evaluation.** A held-out evaluation dataset (different distribution, e.g., domain transfer) must be normalized with the train statistics, not its own.
- **A/B evaluation.** Two evaluation recipes compare model behavior under different input pre-processing; both normalize against the same train statistics.
- **Cross-team workflows.** A team publishes a trained model + its train recipe; a downstream team writes an eval recipe that imports the published train statistics without re-fitting.
- **Longitudinal evaluation.** Evaluation runs at later time points re-use the original train statistics so drift is observable in the data, not absorbed by re-fitting.

In all four, re-fitting statistics on the evaluation data is a correctness bug, not an optimization. `stats_from_instance` makes the correct behavior expressible at the recipe surface.

**Sibling reference is loose-coupled in v1.** The sibling's `recipe_hash` does NOT participate in the consuming recipe's cache identity (see FR-4 Edge Cases). Re-materializing upstream does NOT auto-invalidate downstream — the user re-materializes downstream when upstream changes. Tight coupling (auto-invalidation) is a Future upgrade tracked under FR-ARCH-1.

**Edge Cases:**
- Fit-on-train transformation declared without the training split as the fit source -> caught by `validate` (check 6).
- Transformation parameters that are themselves data-dependent -> must be expressed as fit-on-train; otherwise caught at validation.
- `stats_from_instance` declared alongside `fit_source` -> caught by `validate` (check 22, mutual exclusion).
- `stats_from_instance` references a recipe whose promoted instance is not in the cache (never materialized, or `clean`-ed) -> hard error at materialize time naming the sibling recipe path and the expected cache lookup path ("sibling instance not found"). The recipe is still loadable and `validate`s clean — the sibling-resolve happens at materialize time so the error is actionable (the user re-materializes the sibling and retries).
- `stats_from_instance.op_id` names an op that does not exist in the sibling instance's `fitted_statistics/` (typo, op was renamed, sibling recipe was edited without re-materializing) -> hard error at materialize time naming the missing op_id and the sibling instance path.
- `stats_from_instance` references a sibling instance whose statistics format is incompatible with this op (e.g., this op requires a `mean` and `std` vector pair but the sibling op stored only `mean`) -> hard error at materialize time naming the missing statistic. In v1 this can surface for callers that pass `required_vectors=` / `required_scalars=` into the resolver; `normalize`'s apply path tolerates absent `std` per its existing edge handling.

### FR-11: Augmentations

Apply stochastic operations on the training split that expand the effective dataset. Each augmentation op chooses its materialization mode independently — lazy ops are policy-only (training-time realization) and aggressive ops produce persisted variant records during materialization.

**Behavior:**
1. Each augmentation declares its parameters, the splits it applies to (train-only by default; validation/test rejected by `validate`), a seed, a `materialization` mode (`lazy` or `aggressive`, default `lazy`), and an `expansion` factor (default `1`; must be `>= 1`; values `> 1` require `materialization=aggressive`).
2. **Lazy mode** (current behavior): augmentations apply on-the-fly during training; they are described in the recipe and report but do not produce additional persisted records. Record count is unchanged.
3. **Aggressive mode** (Story H.p): each input record is replaced by `expansion` augmented variant records at materialization time. Variant records carry `source_record_id: str` and `variant_index: int` metadata, and become peer records in the materialized dataset. Per-split record count becomes `N × expansion` per aggressive op (sequential composition: two aggressive ops with `expansion=a` and `expansion=b` produce `N × a × b` records).
4. The recipe declares the augmentation policy regardless of mode. The manifest captures the policy verbatim; the report renders each op with its mode (and expansion if aggressive).
5. Aggressive-mode determinism: each variant's seed is derived as `sha256(global_seed.to_bytes(8,"big") + op_id.encode() + record_id.encode() + variant_index.to_bytes(4,"big"))[:8]`. Worker count is irrelevant to output bytes (validated by the H.o spike against `workers=1/2/4`).
6. Materialization is per-op, not per-section: a single `Augmentations` block can mix lazy and aggressive ops.

**Edge Cases:**
- Augmentation declared on validation or test -> caught by `validate` (check 5).
- Augmentation seeded but with a non-train split -> caught by `validate` before the seed check matters.
- `expansion < 1` -> rejected by the `AugmentationOp` model-level validator (pydantic `ValidationError` surfaced through the recipe loader as `RecipeError`).
- `expansion > 1` paired with `materialization=lazy` -> rejected by the same model-level validator. Lazy mode has no variant fan-out; the pairing is meaningless and refused early.
- Aggressive op referenced in the recipe with no realizer registered by the declaring plugin -> hard error at materialization (`MaterializeError` from the augmentations stage).

**Available `image_classification` augmentation ops** (Story H.q):

- **FR-AUG-1 `random_crop`** — random spatial crop with optional pre-crop padding. Params (`RandomCropParams`): `size: int | tuple[int, int]` (positive; required), `padding: int = 0` (non-negative), `padding_mode: Literal["reflect", "replicate", "zero", "constant"] = "reflect"`. Aggressive realizer pads via `numpy.pad` (mapping `replicate -> edge`, `zero`/`constant -> constant fill 0`), then selects a random crop top-left coordinate via `numpy.random.default_rng(seed_for_variant)`.
- **FR-AUG-2 `horizontal_flip`** — random horizontal flip. Params (`HorizontalFlipParams`): `p: float = 0.5` in `[0.0, 1.0]`. Aggressive realizer runs a per-variant `rng.random() < p` coin flip and calls `Image.transpose(Image.FLIP_LEFT_RIGHT)` on heads. Pillow's transpose is RNG-free (H.o spike confirmed), so the only stochastic choice is the coin flip the realizer drives.
- **FR-AUG-3 `color_jitter`** — random color-space perturbations. Params (`ColorJitterParams`): `brightness: float = 0.0`, `contrast: float = 0.0`, `saturation: float = 0.0` (each in `[0.0, 1.0]`), `hue: float = 0.0` (in `[0.0, 0.5]`). For each enabled dimension the aggressive realizer draws an offset uniformly in `[-magnitude, +magnitude]` against the per-variant seed; brightness/contrast/saturation apply via Pillow's `ImageEnhance.Brightness/Contrast/Color` (each `enhance(1.0 + offset)`); hue applies via HSV-space rotation (H channel shifted by `round(offset * 256) mod 256`). **Edge case: hue is a no-op on `<3`-channel (grayscale) images** — HSV rotation requires a chroma component to rotate. Brightness/contrast/saturation paths still apply through Pillow's single-channel modes.
- **FR-AUG-4 `random_erasing`** — random rectangular region erasing (Zhong et al. 2020). Params (`RandomErasingParams`): `p: float = 0.5`, `scale: tuple[float, float] = (0.02, 0.33)` (area fraction range), `ratio: tuple[float, float] = (0.3, 3.3)` (aspect ratio range). Per-variant `rng.random() < p` decides whether to erase; area drawn uniformly from `scale`, aspect ratio drawn log-uniformly from `ratio` (matches the torchvision convention; the default range is symmetric in log space). The erased rectangle is filled with the input image's mean pixel value. Bounded retry (10 attempts) handles cases where the sampled (area, aspect) doesn't produce a rectangle that fits the image; if no valid rectangle is found, the image passes through unchanged.

**Aggressive-mode persistence (Story H.r.2):** each augmented variant's image bytes are written to a sidecar PNG at `dataset/<split>/images/<record_id>.png` using Pillow's `Image.save(format="PNG", optimize=False)` (deterministic encode), and the variant's JSONL line carries `image_path: str` (relative to the dataset directory) in place of the dropped numpy `image` array. Non-aggressive records — recognized by the absence of `source_record_id`/`variant_index` metadata — keep the existing "image bytes resolve via source `path`" behavior; no sidecars are written for lazy-only recipes. The detection rule lives in `pipeline.runner._is_aggressive_variant` and the write path in `pipeline.runner._prepare_record_for_persistence`. The materialized instance is self-contained: a consumer reading the JSONL can resolve every variant's image bytes without referring back to the (now-augmented-away) source image.

**Cross-repo contract:** downstream consumers (ModelFoundry today, other tools tomorrow) bind against the augmentation surface — `AugmentationOp` fields, on-disk variant layout, and `record_counts` post-augmentation semantics — via [`modelfoundry/vendor-dependency-spec.md`](modelfoundry/vendor-dependency-spec.md). Changes to this surface follow the cross-repo coordination rule in [`project-essentials.md`](project-essentials.md) § "Recipe / manifest / report shape changes need a cross-repo coordination check."

### FR-12: Featurizations

Derive new features from one or more existing inputs.

**Behavior:**
1. Each featurization declares its inputs, output field name, computation, and the splits it applies to.
2. Featurizations may reference any declared input source, including filenames and metadata — **including the output of an upstream featurization in the same stage** (Featurizations run in recipe-declared order within the stage).
3. Featurizations may be deterministic or fit-on-train; fit-on-train featurizations follow FR-6 and FR-10's rules.
4. The same machinery produces derived labels (see `Labels` declaration in FR-19).
5. **Fit-on-train normalization of a derived feature is a staple, cross-modality capability and lives here, not in `Transformations`.** Standardizing a feature that an earlier stage *derived* (audio log-mel spectra per-mel-bin now; tabular column scaling and text embedding normalization as those plugins mature) requires the fit to run *after* the feature exists. The pipeline runs `Transformations` **before** `Featurizations` (a Transformation normalizes *raw* inputs — e.g. the image `normalize` op on pixels), so a Transformation cannot see a derived feature. The `Featurizations` stage is the only stage that runs after derivation *and* supports fit-on-train + statistics persistence (FR-6) + sibling import (FR-TRANS-1). Such an op reads a prior featurization's output field and writes the scaled result to a new field (e.g. audio `log_mel_spectrogram` → `mel`, then fit-on-train `audio_normalize` → `feature`), keeping the raw and scaled features both present and the no-overwrite collision guard (check 23 / FR-12 edge case) satisfied.

**Edge Cases:**
- Featurization referencing a field not in `Input` or upstream output -> caught by `validate` (check 7).
- Featurization producing a name that collides with an existing field -> hard error during materialization.

### FR-13: Visualizations

Render standard or bespoke views over any pipeline stage.

**Behavior:**
1. Each visualization declares its inputs, the stage it observes, an output mode (`exploration` or `reporting`), and any parameters.
2. `exploration` visualizations are rendered on demand via the library API or `inspect`; not persisted.
3. `reporting` visualizations are rendered during materialization and persisted to `report/visualizations/`.
4. A visualization op handle may return either a single PNG (`bytes`) — persisted as `<op.name>.png` — or a `Mapping[str, bytes]` keyed by sub-name (e.g. split, augmentation op name) — persisted as one `<op.name>_<key>.png` per entry. Multi-output ops also surface every PNG via `RenderedVisualization.extras` so callers (e.g. `inspect`) can consume all of them in memory.
5. The op handle's `render(...)` receives an optional `recipe: Recipe | None` kwarg, populated by the pipeline-stage / exploration-mode runner. Policy-aware ops (e.g. `augmented_sample_grid` reading `recipe.Augmentations` + `recipe.seed`; future `corruption_severity_grid` reading `recipe.Generation`) consume it; ops that don't need it ignore the argument.

**Registered ops (image_classification plugin):**
- `class_distribution_histogram` — bar chart of per-class record counts across all splits. No params.
- `sample_grid` — tile the first N records' images into a square-ish grid. Params: `n: int = 16`, `per_class: bool = False`.
- `mean_image_per_class` — per-class mean image, tiled in a row. No params.
- `pixel_distribution` (FR-VIZ-1) — per-channel R/G/B pixel-value histograms for each requested split, rendered as a 1×3 matplotlib figure. Params: `bins: int = 64`, `splits: list[str]` (required, non-empty). Returns one PNG per requested split; persisted as `<op.name>_<split>.png`.
- `augmented_sample_grid` (FR-VIZ-2) — for each declared `AugmentationOp`, an `n_base × n_variants` grid showing the policy applied to a deterministic train-split sample. Mode-aware: aggressive ops group the materialized train split by `source_record_id` + `variant_index`; lazy ops realize variants inline via the plugin's realizer registry, seeded by `per_record_variant_seed(recipe.seed ^ (viz.seed or 0), record, vi, op_id=aug.name)`. Params: `n_base: int` (>0, required), `n_variants: int` (>0, required), `seed: int | None = None`. Returns one PNG per declared augmentation op; persisted as `<op.name>_<aug.name>.png`. Empty mapping (no PNGs written) when the recipe declares no augmentations.
- `corruption_severity_grid` (FR-VIZ-3) — a single `K-corruption × L-severity` figure. Each subplot tiles the same `n_images` train-split records side-by-side under that `(corruption_type, severity)` combination. Self-contained: the op's params declare the corruption universe, not `recipe.Generation`. Params: `n_images: int` (>0, required), `corruption_types: list[str]` (non-empty, vocabulary checked against `_corruption_names.CORRUPTION_NAMES_ALL`, no duplicates, required), `severities: list[int]` (non-empty, each in `1..5`, required). Returns single PNG `bytes`; persisted as `<op.name>.png`. Requires the `[corruptions]` extras at materialize time; the plugin remains importable without them (lazy-import inside `render(...)` raises a friendly `ImportError` with the install pointer when missing).
- `severity_ladder` (FR-VIZ-4) — single-corruption complement to `corruption_severity_grid`: renders `n_examples` train-split records across all five severities of one `corruption_type`, arranged as `n_examples × 5`. Params: `n_examples: int` (>0, required), `corruption_type: str` (non-empty, vocabulary-checked against `CORRUPTION_NAMES_ALL`, required). Single PNG `bytes`; persisted as `<op.name>.png`. Same `[corruptions]`-extras-required and deferred-extras-guard model as `corruption_severity_grid`.

**Edge Cases:**
- Visualization without an output mode -> caught by `validate` (check 11).
- `reporting` visualization that fails -> hard error during materialization (the report is not partial).
- Multi-output op returning an empty mapping, a non-string key, or a non-bytes value -> hard error (reporting) / `TypeError` (exploration). The empty-mapping case is allowed when documented per-op (e.g. `augmented_sample_grid` with no declared augmentations); the stage handles the no-write path explicitly rather than treating it as a failure.
- `pixel_distribution` requesting a split absent from the materialized splits -> hard error during materialization.
- `augmented_sample_grid` declared without a `recipe` context (e.g. exploration call site that forgot to thread it) -> `ValueError`.
- `augmented_sample_grid` against a train split smaller than `n_base` (or aggressive groups smaller than `n_variants`) -> hard error during materialization.
- `corruption_severity_grid` against a train split smaller than `n_images` -> hard error during materialization.
- `corruption_severity_grid` invoked without the `[corruptions]` extras -> `ImportError` with the `pip install 'ml-datarefinery[corruptions]'` pointer.
- `severity_ladder` against a train split smaller than `n_examples` -> hard error during materialization.
- `severity_ladder` invoked without the `[corruptions]` extras -> same friendly `ImportError`.

### FR-14: Variants

Allow a single recipe to declare named overrides on any section.

**Behavior:**
1. Variants are declared under a top-level `variants` block; each variant supplies overrides keyed by section name.
2. At materialize time, the user selects a variant via `--variant` (CLI) or argument (library). Default is the un-overridden recipe.
3. The variant overlay is applied before normalization and hashing; cache identity reflects the selected variant.

**Edge Cases:**
- Variant referencing an undeclared section or key -> caught by `validate` (check 12).
- Variant selecting a section to clear (empty list/object) -> allowed; for example, `Augmentations: []` disables augmentation.

### FR-15: Reporting

Emit a report describing the materialized instance and its preparation.

**Behavior:**
1. The report comprises `report.md` (human-readable summary), `drift.json` (drift-relevant subsection), and persisted reporting-mode visualizations.
2. `report.md` summarizes the recipe, inputs, splits, operations applied, fitted statistics, key counts, and any warnings raised during materialization.
3. `drift.json` is the contract DataMachine consumes against. Prior to production release, the schema is a placeholder documented in the tech spec and may change at any time; it is structured (typed JSON, not free-form) so callers can begin coding against it. The schema is finalized and frozen as a precondition for production release.
4. The `report` CLI verb re-renders the report from a materialized instance without rerunning the pipeline.

**Edge Cases:**
- Reporting visualization fails to render -> materialization fails (FR-13).
- Re-rendering a report against a stale fitted-statistics block -> hard error citing the inconsistency.

**Cross-repo contract:** the report surface — `report.md` augmentation-policy summary, `drift.json` schema, and the `report/visualizations/<name>.png` (or `<name>_<key>.png` for multi-output viz ops such as `pixel_distribution`) layout — is part of the documented cross-repo contract in [`modelfoundry/vendor-dependency-spec.md`](modelfoundry/vendor-dependency-spec.md). Schema changes follow the coordination rule in [`project-essentials.md`](project-essentials.md) § "Recipe / manifest / report shape changes need a cross-repo coordination check."

### FR-16: Plugin Interface

Specialize DataRefinery for a single data category.

**Behavior:**
1. A plugin contributes operation implementations for the recipe sections that apply to its category.
2. Plugins are discovered via `pyproject.toml` entry points; an additional plugin search path may be configured.
3. The plugin declares its name, the recipe sections it supports, and the operations it ships.
4. v1 ships:
   - **`image_classification`** — fully implemented Image plugin scoped to classification.
   - **`tabular`** — stub: declares supported sections and operation outline, no operation implementations.
   - **`text`** — stub: declares supported sections and operation outline, no operation implementations.
5. Stub plugins fail at materialize time with a clear "stub plugin; not implemented" error; they validate cleanly so a recipe can be authored against them.
6. Prior to production release, stub plugin section lists and operation outlines may change as Image-plugin development reveals what category-agnostic abstractions actually require. After production release, stub section lists are part of the plugin-interface contract and change only via documented schema versioning.

**Edge Cases:**
- Plugin not installed -> caught by `validate` (check 2).
- Plugin operation parameter mismatch -> caught by `validate` (check 18).
- Multiple plugins claiming the same name -> hard error at discovery.

### FR-17: `init` — Recipe Bootstrapping

Generate a starter recipe from raw inputs deterministically, with optional LLM enhancement.

**Behavior:**
1. **Deterministic scaffolder (always available, offline; v1: image only).** Inspects file types, dimensions, dtypes, directory structure, and basic stats. Emits a starter recipe with `Input` populated, common `Transformations` stubbed (commented out), `Splits` seeded with sensible defaults, and the chosen plugin's standard sections present. Sufficient for CIFAR-10 unaided.
2. **Optional LLM enhancement layer (activates only when configured).** Adds interpretive judgments the deterministic layer cannot make: column-name semantics, label-source inference when ambiguous, suggested augmentation policies, plain-English comments. Routed through `lmentry`. DataRefinery does not depend on `lmentry` at the package level; it is an optional extra.
3. v1 supports `init` for the `image_classification` plugin only. Tabular and text recipes are written by hand against the stub plugin sections.

**Edge Cases:**
- `init` invoked against tabular or text inputs in v1 -> error: "init scaffolder not available for this category in v1; write recipe manually against the stub plugin sections."
- LLM enhancement requested but `lmentry` not installed -> error pointing at the optional extra.
- LLM enhancement requested but offline -> warning; deterministic recipe emitted with a note that enhancement was skipped.

### FR-18: `check` — Environment Soundness

Verify the runtime environment.

**Behavior:**
1. Reports Python version, installed DataRefinery version, declared plugin versions, and discovered plugin paths.
2. Reports availability of optional hardware acceleration (Metal on Apple Silicon, CUDA elsewhere) without requiring it.
3. Reports availability of optional extras (`lmentry`).
4. Returns non-zero exit code on missing required dependencies; zero with warnings on missing optional ones.

**Edge Cases:**
- Plugin discovery failure -> reported as a soundness failure.
- Mismatched dependency versions -> reported with the conflicting requirement.

### FR-19: `status` — Instance Lifecycle and Configuration

Summarize a materialized instance.

**Behavior:**
1. Given an instance path or recipe + inputs (resolved via FR-4), report: recipe hash, input hash, seed, schema version, plugin, variant (if any), creation time, key counts (records per split), and warnings emitted at materialization time.
2. CLI renders a `rich` table; library returns a structured object.

**Edge Cases:**
- Instance directory present but missing `manifest.json` -> reported as a corrupt instance; `clean` is suggested.
- Recipe + inputs with no cached instance -> reports `cache=miss`; no error.

### FR-20: `inspect` — Read-Only Views

Render exploration-mode visualizations and structured data summaries against a materialized instance.

**Behavior:**
1. Lists all `exploration`-mode visualizations declared in the instance's recipe.
2. Renders a named exploration visualization to stdout (text) or to a configurable output path (image/HTML).
3. Provides a structured peek at fitted statistics, splits, and sample records.

**Edge Cases:**
- Exploration visualization references a stage no longer present in the instance -> hard error citing the inconsistency.
- `inspect` against a partial (failed) instance -> refuses with a pointer to the `FAILED` marker.

### FR-21: `clean` — Cache Management

Manage cache contents.

**Behavior:**
1. Lists cache entries by recipe hash, input hash, seed, age, or marker (e.g., orphaned temp directories).
2. Removes entries by selector after explicit confirmation (CLI) or with an explicit force flag (library).
3. By default, refuses to operate without a selector; "clean everything" requires `--all` plus confirmation.

**Edge Cases:**
- `clean --all` with confirmation in a non-TTY context -> requires `--yes` flag; refuses otherwise.
- Cache entry currently being read by another process -> reported and skipped.

### FR-22: Labels

Declare what the label is and how it is obtained: present in the raw input, or derived.

**Behavior:**
1. The `Labels` section declares the label field name and its source.
2. A directly-present label cites the source field.
3. A derived label is produced by the same machinery as featurizations (FR-12) and may draw on any declared input source, including filenames and metadata.
4. For `image_classification`, the `image_flat` source type accepts a `label_from` spec (see `Input` examples) that populates labels at load time from a sidecar CSV manifest. From `Labels`'s perspective this is `kind: direct` — the labels arrive intrinsically; no Featurization is involved.
5. An `image_flat` source may also declare `unlabeled: true` to indicate the partition has no labels (typical for Kaggle-style heldout test sets). `Labels.source.kind` remains `direct` — labels exist on partitions that aren't unlabeled. `OutputExpectations` whose `field` equals `Labels.field` treat records lacking the field as "skipped" when any source declares `unlabeled: true` (so `required_field: <label>` no longer fails on the unlabeled partition); records where the field is present but `None` still fail.

**Edge Cases:**
- Label source unresolvable from declared inputs -> caught by `validate` (check 13).
- Derived label whose computation depends on a non-train fit source -> follows FR-10's fit rules.

### FR-23: InputContracts and OutputExpectations

Declare assertions on the inputs and the materialized outputs.

**Behavior:**
1. `InputContracts` declares assertions the raw input data must satisfy (record count bounds, required fields, dtype constraints, allowed value ranges). Failures abort materialization before any expensive work.
2. `OutputExpectations` declares assertions the materialized dataset must satisfy (value-range, distributional, schema). Failures abort materialization at the end of the pipeline; the partial instance lives in the temp directory under the standard `FAILED` semantics (FR-5).
3. `Output` is the structural contract — record shape, field names, dtypes — that downstream tools bind against. `OutputExpectations` are peers of `Output`, not nested.

**Edge Cases:**
- Contract referencing a non-existent field -> caught by `validate` (check 17).
- Distributional expectation that is statistically reasonable but legitimately violated by a small input -> reported with the observed and expected distributions; configurable as warning vs. failure per assertion.

---

## Configuration

**Recipe file** (single YAML, schema-versioned):

- Top-level keys: `schema_version` (required), `plugin` (required), the recipe sections (most required, plugin-dependent), `variants` (optional).
- Recipe sections per FR-1 through FR-23.

**Configuration precedence** (highest wins):

1. **Recipe file** — authoritative for data-pipeline semantics (sections, operations, splits, seed).
2. **CLI flags** — execution context and ad-hoc overrides (cache root, log level, seed override, plugin path, variant selection, stage flag).
3. **Environment variables** — same execution-context surface as CLI flags, lower precedence.

The recipe never reads from CLI flags or environment variables for its data-pipeline semantics; only execution context flows from the outer environment inward.

**Cache layout** (under `<cache-root>`, default `data/`):

```
data/
├── raw/                              # raw input cache (when materialized from external sources)
├── instances/
│   ├── <recipe-hash>/
│   │   └── <input-hash>/
│   │       └── <seed>/               # a complete materialized instance
│   └── .tmp/
│       └── <run-id>/                 # in-flight or failed runs
└── plugins/                          # optional plugin-local caches (plugin-defined)
```

---

## Testing Requirements

- **Framework.** `pytest` with `pytest-cov`.
- **Coverage thresholds.**
  - Core invariants (recipe loader, schema-version gate, cache identity computation, splits/seeding, plugin interface, atomic promote/rollback) ≥ 95% in any release.
  - Overall line coverage ≥ 85% **after production release**. Pre-production: every FR is exercised by at least a smoke test; no project-wide percentage gate applies.
- **Test categories.**
  - **Unit** — pure functions, schema validation, cache identity computation, individual operations.
  - **Plugin contract** — every plugin (including stubs) is exercised against a contract test that asserts it declares the sections and operation schemas it claims.
  - **Integration** — end-to-end materialization on a small fixture dataset (image classification with a CIFAR-10-shaped fixture); asserts byte-identical re-runs and cache reuse.
  - **CLI smoke** — every verb runs against a fixture recipe and produces the expected exit code and output structure.
- **Determinism tests.** Re-run a fixture pipeline twice with the same seed; assert the resulting instance is byte-identical.
- **Cache identity tests.** Whitespace/comment edits → cache hit; semantic edits → cache miss.
- **Variant tests.** Each declared variant produces a distinct instance; default produces the un-overridden instance.
- **Failure mode tests.** Forced failures at every pipeline stage leave a `FAILED`-marked temp directory and never touch the cache.

---

## Security and Compliance Notes

- **License.** Apache-2.0 (see [`LICENSE`](../../LICENSE)). New source files carry the project's standard copyright and SPDX header per `project-essentials.md`.
- **Offline operability.** The deterministic path performs no network I/O. Any network-dependent feature (LLM enhancement) is opt-in via the `lmentry` extra and gated by explicit configuration.
- **No secrets in recipes.** Recipes are checked into version control; credentials for remote raw-input sources, when introduced, are sourced from the environment, not the recipe. v1 does not ship remote-source support beyond local paths.
- **Plugin trust boundary.** Plugins are executable code discovered via entry points. DataRefinery does not sandbox plugins; users install plugins they trust. `check` reports the discovered plugins so users can audit what is loaded.
- **No PII handling guarantees.** v1 does not provide PII detection, redaction, or compliance tooling. Users handling sensitive data are responsible for their own compliance posture.

---

## Performance Expectations

v1 does not commit to hard performance targets. The expected behavior is:

- **CIFAR-10-scale image classification on a developer laptop** completes `init`, `validate`, and `materialize` without manual workarounds and within an interactive working session (no specified upper bound).
- **Cache hits return immediately** (no pipeline work performed; only cache identity computation and manifest read).
- **`validate` runs in seconds** even for large recipes (it does not touch raw data beyond schema discovery).

Performance work is reactive: when a representative workload exposes a problem, a target is set for the improvement. Up-front targets are explicitly out of scope.

---

## Acceptance Criteria

DataRefinery v1 is complete when:

1. A recipe author can take CIFAR-10-shaped raw image data and produce a materialized instance via `init` → `validate` → `materialize` without manual workarounds, on macOS (first-class pre-production); Linux is best-effort pre-production. Windows users follow the documented WSL2 path.
2. The materialized instance contains recipe, dataset, fitted statistics, and report; re-running the same recipe + inputs + seed produces a byte-identical instance.
3. Cosmetic recipe edits (whitespace, comments, key reordering) result in a cache hit; semantic edits result in a cache miss.
4. A failed materialization leaves a `FAILED`-marked temp directory and never produces a partial cached instance.
5. `validate` correctly reports every check in the enumerated v1 list against fixture recipes designed to violate each one.
6. The Image classification plugin ships fully implemented; tabular and text plugins ship as stubs that validate cleanly and fail at materialize time with a clear "not implemented" message.
7. CLI verbs `init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean` are present, exercised by smoke tests, and have library equivalents.
8. The library API and CLI both materialize the same instance from the same recipe + inputs + seed.
9. The deterministic path runs offline; LLM enhancement during `init` is exercised only when `lmentry` is installed and explicitly configured.
10. Test coverage thresholds are met for the current release tier (≥ 95% on core invariants always; smoke-level FR coverage pre-production; ≥ 85% overall after production release); `ruff` and `mypy --strict` pass clean.
11. The report's `drift.json` placeholder schema is documented in the tech spec, structured (typed JSON), and exercised by a fixture so DataMachine work can begin coding against it. The schema is finalized and frozen as a precondition for production release.
12. `pip install ml-datarefinery==<version>` succeeds in a clean Python 3.12 venv and the installed package exposes `import datarefinery` plus the `datarefinery` console script. Verified manually on each release per `docs/guides/releasing.md` step 6.
