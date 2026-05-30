# stories.md -- ModelFoundry (Python 3.12.x)

This document breaks the `ModelFoundry` project into an ordered sequence of small, independently completable stories grouped into phases. Each story has a checklist of concrete tasks. Stories are organized by phase and reference modules defined in `tech-spec.md`.

Put **`vX.Y.Z` in the story title only when that story ships the package version bump** for that release. Doc-only or polish stories **omit the version from the title** (they share the release with the preceding code story, or use your project's doc-release policy). **One semver bump per owning story** — extra tasks on the *same* story share that bump; see `project-essentials.md`. Semantic versioning applies to the package. Stories are marked with `[Planned]` initially and changed to `[Done]` when completed.

For a high-level concept (why), see [`concept.md`](concept.md). For requirements and behavior (what), see [`features.md`](features.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For project-specific must-know facts, see [`project-essentials.md`](project-essentials.md) (`plan_phase` appends new facts per phase). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Version Cadence

Standard semantic versioning, with these conventions:

- **Every story belongs to a phase.** Bugfix stories included. No orphan stories.
- **Per-story bumping** (when a story owns its own release):
  - Bugfix or trivial change → **patch** (`vX.Y.Z+1`)
  - Feature or improvement → **minor** (`vX.Y+1.0`)
  - Breaking change → **major** (`vX+1.0.0`). Post-1.0 only, and only via the `plan_production_phase` mode, which negotiates with the developer about whether the breakage is substantively user-facing or technically-but-trivially breaking (example: a log-format change is technically breaking, but if logs aren't a core consumer capability, the developer may judge it minor or even patch).
- **Phase-bundling option:** a phase can run unversioned during work and ship a single release/tag at end-of-phase. Stories within the phase carry no version in their title; the phase's last story owns the bump (magnitude determined by the highest-impact change in the bundle).
- **No out-of-order implementation.** Story order in this file is the order of execution. If work order needs to change, **reorganize/renumber here first** — don't skip ahead and create version-number gaps.
- **Pre-1.0:** standard semver applies; version starts at `v0.1.0` (Story A.a).
- **Post-1.0:** every phase must go through `plan_production_phase` (the lighter `plan_phase` is pre-1.0 only). Major bumps only happen through that mode's negotiation step.

This is the authoritative cadence rule. **Do not extrapolate the bump magnitude from `pyproject.toml`'s current version** — re-read this section whenever you're about to assign a version to a story.

**ModelFoundry's release strategy: phase-bundling.** Each phase runs unversioned during work and ships a single minor bump at end-of-phase. The last story of each phase carries the `vX.Y.Z` version in its title; all other stories within the phase omit it. A.a is the documented exception per the Version Cadence rule above — it establishes `v0.1.0` in `pyproject.toml` as the scaffold baseline. No PyPI publish happens until Phase G's `publish.yml` is wired and the first tag is pushed; before that, version bumps land in `pyproject.toml` and `CHANGELOG.md` only.

---

## Phase A: Foundation

Establish the package skeleton, prove the environment is wired up, validate the most uncertain integration boundary (DataRefinery binding), and lay down the foundational infrastructure that the rest of the build depends on (logging, runtime config, error hierarchy). By end of Phase A, the project has a working `pyve` two-environment install, a `modelfoundry --version` command, an integration-spike outcome document confirming the DataRefinery binding pattern, and the shared library plumbing that subsequent phases consume.

### Story A.a: v0.1.0 Project Scaffolding [Done]

Establish the package skeleton — LICENSE, copyright header, `pyproject.toml`, `environment.yml`, `README.md`, `CHANGELOG.md`, `.gitignore`, and the empty `src/modelfoundry/` + `tests/` trees. This story is executed in `scaffold_project` mode (not `code_test_first`) and is marked `[Done]` by `scaffold_project` upon completion.

- [x] Create `pyproject.toml` with `hatchling` build backend, project metadata (name = `ml-modelfoundry`, distribution name `ml-modelfoundry`, import name `modelfoundry`, console script `modelfoundry = modelfoundry.cli.app:main`), `requires-python = ">=3.12,<3.14"`, runtime dependency pinset per `tech-spec.md` § Dependencies (base), optional-extras stubs (`[pytorch]`, `[sklearn]`, `[huggingface]`, `[keras]`, `[llm]`, `[notebook-smokes]`).
- [x] Update `environment.yml` from the pyve stub. (Deviation: the base runtime stack is declared authoritatively in `pyproject.toml` — it ships with the PyPI wheel; `environment.yml` does not. `environment.yml` is kept minimal as the pyve env shell with an explanatory comment, avoiding the conda/pip two-place dependency drift the project-essentials warns against.)
- [x] Create `requirements-dev.txt` with `ruff`, `mypy`, `pytest`, `pytest-cov`, `hypothesis`, `nbclient`, `ipykernel`, `types-pyyaml`, `build`.
- [x] Create `src/modelfoundry/__init__.py` (empty package init + `__version__` re-export), `src/modelfoundry/_version.py` (single source of truth, set to `"0.1.0"`), `src/modelfoundry/py.typed`.
- [x] Create empty `tests/` directory with a placeholder `tests/conftest.py`.
- [x] Create `README.md` placeholder with project name and one-line summary; `CHANGELOG.md` with v0.1.0 entry ("Project scaffolded"); `.gitignore` for Python + pyve + pytest artefacts (added `models/`, `data/`, `.hypothesis/`, `.mypy_cache/`, `.ruff_cache/`).
- [x] Stamp the Apache-2.0 / Pointmatic SPDX header on every new source file per `project-essentials.md` § File header conventions.
- [x] Configure `[tool.ruff]`, `[tool.mypy]` (with `strict = true`), `[tool.pytest.ini_options]` (with `pythonpath = ["src"]`) in `pyproject.toml`.
- [x] Two-environment install: `pyve run pip install -e .` + `pyve testenv init` + `pyve testenv run pip install -e .` + `pyve testenv install -r requirements-dev.txt`. (Pinned `python 3.12.13` via a new `.tool-versions` so the testenv builds on 3.12.13 — it had defaulted to asdf's 3.14.4, which `requires-python` correctly rejected.)
- [x] Bump version to v0.1.0 (already set in scaffold).
- [x] Update CHANGELOG.md.
- [x] Verify: `pyve run python -c "import modelfoundry; print(modelfoundry.__version__)"` prints `0.1.0`; `pyve testenv run ruff check src tests` passes; `pyve testenv run mypy src tests` passes.

### Story A.b: Hello World — `modelfoundry --version` [Done]

Smallest runnable artefact proving the environment + console script + version plumbing are wired. No CLI framework yet — just a stub `__main__.py` that prints `__version__` and exits.

- [x] Create `src/modelfoundry/__main__.py` that prints `f"modelfoundry {__version__}"` and exits 0.
- [x] Update `__init__.py` to re-export `__version__` from `_version.py`. (Already re-exported by A.a's scaffold; verified.)
- [x] Add a smoke test under `tests/unit/test_version.py`: imports `modelfoundry.__version__`, asserts it matches `_version.py`.
- [x] Verify: `pyve run python -m modelfoundry` prints `modelfoundry 0.1.0`; `pyve run modelfoundry` (the installed console script — point to a placeholder `cli.app:main` that re-uses the same print) prints the same; `pyve test tests/unit/test_version.py` passes.

### Story A.c: Integration spike — DataRefinery instance binding [Done]

Throwaway script in `scripts/`, not the package. Validate the most uncertain integration boundary before production modules land: can ModelFoundry read a materialized DataRefinery instance's manifest + JSONL records + sidecar PNGs per the vendor-dependency-spec, decode an image record into a numpy array, and produce something a PyTorch `DataLoader` could consume? Deliverable is the documented outcome (decision / pattern / hypothesis), not production code. See `docs/project-guide/developer/best-practices-guide.md` § "Hello World First — Spike Early, Spike Often."

- [x] Decide: spike against a real `ml-datarefinery` install (if available from PyPI or an internal index) or against a hand-rolled mock that mimics the vendor-dependency-spec's on-disk layout. Document the choice in the spike outcome doc. (Chose **real** `ml-datarefinery==0.17.0` for the source-resolution path; hand-rolled fixture for the aggressive-sidecar consumer path — see outcome doc.)
- [x] Create `scripts/spike_datarefinery_binding.py` (throwaway): load a DataRefinery instance from a `<datarefinery-cache>/instances/<recipe-hash16>/<input-hash16>/<seed>/` path, parse `manifest.json`, iterate `dataset/train.jsonl`, resolve `path` or `image_path` per the vendor-dep-spec, decode an image with Pillow.
- [x] Document the outcome in `docs/spikes/A.c-datarefinery-binding.md`: confirm or refine the `DataRefineryDataset` adapter pattern from `tech-spec.md` § `plugins.pytorch.data`; note any deviations or surprises (per-record-seed stamp shape, aggressive vs source-resolution record distinction, sidecar PNG path resolution).
- [x] Note any integration risks for future stories. (Flagged for B.i: DataRefinery 0.17.0 cannot materialize an aggressive instance from a scaffolded recipe — sidecar write fails on path-like `record_id`s; recommend filing upstream. Also: `label` is a string class name, not an int index — adapter must build a sorted label→index map.)
- [x] Verify: spike script runs end-to-end on the chosen DataRefinery instance (real or mocked) without error; outcome doc captures the binding pattern and any deviations from `tech-spec.md`.

### Story A.d: Logging foundation — `JsonFormatter` and `get_logger` [Done]

Two-channel logging discipline per `features.md` OR-4 / `tech-spec.md` § Logging. `rich`-based user output is handled later (per CLI verb); this story lands the stdlib `logging` JSON-lines operational channel.

- [x] Create `src/modelfoundry/logging.py` with `JsonFormatter` (one JSON object per line: `timestamp`, `level`, `logger`, `message`, plus arbitrary structured fields via `extra=`) and `get_logger(name: str = "modelfoundry") -> logging.Logger` helper.
- [x] Configure the formatter to write to a caller-supplied target (file path or `sys.stderr` / `sys.stdout`); never hijack the root logger. (`get_logger(target=...)` accepts `"stderr"`/`"stdout"`, a file path, or a writable stream; re-targeting replaces the prior JSON handler.)
- [x] Unit tests under `tests/unit/test_logging.py`: emitted JSON lines are valid JSON, contain `timestamp` / `level` / `message`, honour `extra={"stage": "x"}` fields.
- [x] Verify: `pyve test tests/unit/test_logging.py` passes; sample log emission produces parseable JSON.

### Story A.e: Runtime config — `RuntimeConfig` pydantic model [Done]

`tech-spec.md` § Data Models > `RuntimeConfig`. Loads cache root, data cache root, log level, log target, plugin path, variant, seed, overwrite. Precedence: CLI flags (set by caller) > env vars > built-in defaults. Recipe-level overrides are separate (per-recipe `Data.cache_root`).

- [x] Create `src/modelfoundry/core/config.py` with `RuntimeConfig(pydantic.BaseModel)` carrying the eight fields per `tech-spec.md`.
- [x] Add a `RuntimeConfig.from_env(prefix="MODELFOUNDRY_") -> RuntimeConfig` classmethod that reads `MODELFOUNDRY_CACHE_ROOT`, `MODELFOUNDRY_DATA_CACHE_ROOT`, `MODELFOUNDRY_LOG_LEVEL`, `MODELFOUNDRY_LOG_TARGET`, `MODELFOUNDRY_PLUGIN_PATH` (comma-separated for the tuple) and falls back to defaults. (`from_env(**overrides)` lets explicit CLI-flag overrides win over env-derived values; `extra="forbid"` rejects unknown keys.)
- [x] Unit tests: defaults are applied when env is empty; env vars override defaults; explicit constructor args override env vars.
- [x] Verify: `pyve test tests/unit/test_config.py` passes.

### Story A.f: v0.2.0 Exception hierarchy — `ModelfoundryError` and subclasses [Done]

`tech-spec.md` § Data Models > Exception hierarchy. Establishes the catch-all base + 10 subclasses for the rest of the build. Owns the Phase A v0.2.0 bump (covers A.b–A.f cumulatively).

- [x] Create `src/modelfoundry/core/errors.py` with `ModelfoundryError` base + subclasses `RecipeError`, `ValidationError`, `PluginError`, `DataBindingError`, `MaterializeError`, `ModelArtifactExistsError`, `OptimizationError`, `ExpectationError`, `CacheError`, `InspectionError`, `InstanceError`.
- [x] Each exception carries `message`, `recipe_path: Path | None = None`, `stage: str | None = None`, `detail: dict[str, Any] | None = None`.
- [x] Re-export the base + subclasses from `src/modelfoundry/__init__.py` so downstream consumers can `except ModelfoundryError:` cleanly per the consumer-dependency-spec BR-10.
- [x] Unit tests under `tests/unit/test_errors.py`: hierarchy is correct (every subclass is a `ModelfoundryError`); `detail` round-trips through repr.
- [x] Bump version to v0.2.0.
- [x] Update CHANGELOG.md (Phase A summary: hello world, integration spike outcome, logging foundation, runtime config, exception hierarchy).
- [x] Verify: `pyve test tests/unit/test_errors.py` passes; `from modelfoundry import ModelfoundryError` works; `pyve testenv run mypy src tests` clean.

---

## Phase B: Recipe + Cache + Plugin Foundation

Build the recipe → cache → plugin-protocol foundation that everything else depends on. By end of Phase B, the system can load a recipe, canonicalize it, compute a cache key, write/read a manifest, register and discover plugins, bind to a (mock-or-real) DataRefinery instance, derive seeds deterministically, persist/load forward-extensible checkpoints, evaluate `OutputExpectations`, and run static validation checks against the recipe. The PyTorch plugin and the materialize orchestrator come in Phase C; this phase is plugin-agnostic infrastructure.

### Story B.a: Recipe pydantic models + loader + schema-version gate [Done]

`features.md` FR-1, `tech-spec.md` § Data Models > `ModelRecipe`, § `recipe.loader`.

- [x] Create `src/modelfoundry/recipe/models.py` with `ModelRecipe` (top-level pydantic v2 model, `model_config = ConfigDict(extra="forbid", frozen=True)`) + per-section sub-models: `DataSpec`, `LossSpec`, `OptimizerSpec`, `ScheduleSpec`, `TrainingSpec`, `OptimizationSpec`, `EvaluationSpec`, `VisualizationSpec`, `ExpectationSpec`, `EarlyStoppingSpec`, `ComparisonSpec`, `SearchSpaceSpec`. `ArchitectureSpec` stays as a generic `dict[str, Any]` for now (plugins attach per-op typed sub-models in Phase C). (Op-bearing/under-specified specs — `Loss`/`Optimizer`/`Schedule`/`Visualization`/`SearchSpace` — use `extra="allow"` so plugin params survive until Phase C/B.m; framework specs use `extra="forbid"`.)
- [x] Create `src/modelfoundry/recipe/loader.py` with `SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})` and `load_recipe(path, *, variant=None, seed=None) -> ModelRecipe` (parse YAML via `yaml.safe_load`, gate on `schema_version`, apply variant overlay placeholder, return a `ModelRecipe`). (`seed` override is applied; `variant` is threaded as a placeholder — real overlay merge lands in B.b.)
- [x] Raise `RecipeError` (from Phase A) on malformed YAML, missing `schema_version`, unrecognized `schema_version`, unknown top-level keys (the `extra="forbid"` raises `pydantic.ValidationError` which the loader wraps as `RecipeError`).
- [x] Unit tests under `tests/unit/test_recipe_loader.py`: valid minimal recipe round-trips; missing `schema_version` → `RecipeError`; unrecognized `schema_version: 99` → `RecipeError` listing supported versions; malformed YAML → `RecipeError` with file/line context.
- [x] Verify: `pyve test tests/unit/test_recipe_loader.py` passes.

### Story B.b: Variant overlay [Done]

`features.md` FR-14, `tech-spec.md` § `recipe.variants`.

- [x] Create `src/modelfoundry/recipe/variants.py` with `apply_variant(recipe_dict, variant_name) -> dict` (deep-merge a named overlay from `variants.<name>` onto the base recipe before final pydantic construction). (Nested mappings merge recursively; scalars/lists replace wholesale. Returned dict clears `variants` so unused variants don't pollute cache identity — mirrors the DataRefinery family discipline.)
- [x] Update `loader.py` to apply the variant overlay before pydantic validation; raise `RecipeError` if `--variant` references an unknown name (with the list of available variants in the message).
- [x] Unit tests: variant overlay correctly merges nested sections; unknown variant raises clear error; selecting a variant changes the canonicalized recipe shape (verified later in B.d).
- [x] Verify: `pyve test tests/unit/test_recipe_variants.py` passes.

### Story B.c: Canonical bytes — `recipe.canonical` [Done]

`features.md` FR-4, `tech-spec.md` § `recipe.canonical`. **Cache identity foundation — see `project-essentials.md` § Cache identity is the reproducibility contract.**

- [x] Create `src/modelfoundry/recipe/canonical.py` with `canonical_bytes(recipe: ModelRecipe) -> bytes` (`model_dump(mode="json")` → `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` → `.encode("utf-8")`) and `recipe_hash(recipe: ModelRecipe) -> str` (SHA-256 hex of canonical bytes, full 64-hex digest).
- [x] Document inline that every pydantic field default participates in canonical bytes — this is the deliberate `SUPPORTED_SCHEMA_VERSIONS` invalidation lever.
- [x] Unit tests: cosmetic edits (whitespace in source YAML, key reordering) produce identical canonical bytes; semantic edits (value change, op add/remove) produce different bytes; variant selection perturbs canonical bytes. (Also: unused-variant edits do not perturb the no-variant bytes — confirms B.b's `variants`-clearing serves cache identity.)
- [x] Verify: `pyve test tests/unit/test_canonical.py` passes.

### Story B.d: Cache identity — `cache.identity` [Done]

`features.md` FR-4, `tech-spec.md` § `cache.identity`. **Implements the loose-coupling rule from `project-essentials.md` § Loose-coupled DataRefinery binding.**

- [x] Create `src/modelfoundry/cache/__init__.py` and `src/modelfoundry/cache/identity.py` with `CacheKey` dataclass (`recipe_hash16: str`, `data_instance_hash16: str`, `seed: int`) and `cache_key(recipe, data_instance_triple, seed) -> CacheKey` (compute 16-hex truncations; full hashes flow into the manifest separately).
- [x] `data_instance_triple` is the DataRefinery instance's `(recipe_hash, input_hash, seed)` XOR'd-and-truncated to 16 hex chars. ModelFoundry sees the upstream instance as a single hashed unit per the loose-coupling rule. (Each hash contributes its first-16-hex as a 64-bit operand; the DR-side seed is XORed in as a full 64-bit operand so it fully participates rather than being lost to truncation.)
- [x] Unit tests: same `(recipe, data_triple, seed)` → same `CacheKey`; different seed → different key; different data triple → different `data_instance_hash16`; **re-materializing DataRefinery into the same cache directory (same triple) is a no-op for ModelFoundry's cache identity**.
- [x] Verify: `pyve test tests/unit/test_cache_identity.py` passes.

### Story B.e: Cache layout — `cache.layout` [Done]

`tech-spec.md` § `cache.layout`. Path helpers for the on-disk ModelInstance directory.

- [x] Create `src/modelfoundry/cache/layout.py` with `CachePaths` (constructor takes `cache_root` + `CacheKey`; exposes `instance_dir`, `recipe_yaml`, `manifest_json`, `model_dir`, `weights_dir`, `architecture_json`, `tokenizer_dir`, `training_dir`, `training_history`, `checkpoints_dir`, `optimization_dir`, `trials_parquet`, `study_db`, `best_params_json`, `evaluation_dir`, `metrics_json`, `confusion_matrix_npz`, `calibration_parquet`, `predictions_parquet`, `report_dir`, `report_md`, `report_viz_dir`). (`checkpoints_dir` resolves under `model/` to match C.l's `model/checkpoints/checkpoint-best.pt`; constructor resolves `cache_root` to absolute so every helper is absolute.)
- [x] Path resolution: `<cache-root>/instances/<recipe-hash16>/<data-instance-hash16>/<seed>/...`. Helpers for `tmp_dir(run_id)` (`<cache-root>/instances/.tmp/<run-id>/`), `trash_dir(timestamp)` (`<cache-root>/.trash/<timestamp>/`).
- [x] Unit tests: paths resolve correctly; all helpers return absolute paths under the cache root; no helper escapes the cache root.
- [x] Verify: `pyve test tests/unit/test_cache_layout.py` passes.

### Story B.f: Atomic temp-then-promote — `cache.atomic` [Done]

`features.md` FR-5, `tech-spec.md` § `cache.atomic`.

- [x] Create `src/modelfoundry/cache/atomic.py` with `materialize_temp_dir(cache_root, cache_key)` context manager (yields `<cache-root>/instances/.tmp/<run-id>/`; on clean exit, `os.replace` to final path; on exception, write `FAILED` marker file containing failing stage + error class + message and leave the temp dir intact). (Stage is read from the exception's `.stage` when it's a `ModelfoundryError`; final-path-exists at promote raises `ModelArtifactExistsError`, promote/cross-device failures raise `MaterializeError`.)
- [x] `trash_existing(cache_root, key) -> Path` helper for `--overwrite` flag: moves existing instance to `<cache-root>/.trash/<timestamp>/<key>/`.
- [x] Document the same-filesystem-only requirement inline (cross-device `os.replace` fails).
- [x] Unit tests: clean exit promotes correctly; raised exception leaves `FAILED` marker; concurrent attempts fail cleanly pre-prod (per OR-10); `trash_existing` moves rather than deletes.
- [x] Verify: `pyve test tests/unit/test_atomic_promote.py` passes.

### Story B.g: Manifest model + JSON I/O [Done]

`tech-spec.md` § Data Models > `Manifest`. Pydantic model written to `manifest.json` at promote time.

- [x] Create `src/modelfoundry/core/manifest.py` with `Manifest(pydantic.BaseModel)` carrying the fields per `tech-spec.md` (schema_version, plugin, plugin_version, recipe_hash, data_instance_hash, bound_data_instance, seed, variant, created_at, elapsed_seconds, warnings, is_partial, failed_stage, epoch_history, optimization, evaluation, output_expectations, byte_identity_guaranteed, metric_tolerance) plus helper sub-models `ManifestWarning`, `OptimizationManifest`, `ExpectationOutcome`. (`extra="forbid"` on every sub-model; the tech-spec underspecifies the helper shapes, so I picked minimal sensible fields per the consuming stories — B.l for `ExpectationOutcome`, C.i for `OptimizationManifest`, vendor-dep-spec for `ManifestWarning`. C.i/B.l can extend these pre-prod if needed.)
- [x] `Manifest.write(path)` and `Manifest.load(path)` helpers (UTC ISO 8601 timestamps; pretty-printed JSON for human readability while still byte-stable for goldens).
- [x] Unit tests under `tests/unit/test_manifest.py`: round-trip a representative manifest; missing required fields → `pydantic.ValidationError`; `byte_identity_guaranteed=false` requires `metric_tolerance` to be set.
- [x] Verify: `pyve test tests/unit/test_manifest.py` passes.

### Story B.h: Plugin Protocol + OperationSpec + discovery [Done]

`features.md` FR-24, `tech-spec.md` § `plugins.base`.

- [x] Create `src/modelfoundry/plugins/__init__.py`, `src/modelfoundry/plugins/base.py` with `OperationSpec(pydantic.BaseModel)` (op_name, param_model, applies_to, requires_extras) and the `Plugin` Protocol decorated with `@runtime_checkable` (name, version, operations, `health_check`, `build_model`, `run_optimization`, `run_training`, `run_evaluation`, `render_visualization`, `save_model`, `load_model`, `predict`, `predict_proba`). (Protocol return types not yet implemented — `DataRefineryInstance`, `CheckReport`, `*Result`, `InstanceArtifacts` — are PEP 695 `type X = Any` forward stubs that the owning stories refine.)
- [x] Create `src/modelfoundry/plugins/discovery.py` with `discover_plugins(extra_paths: tuple[Path, ...] = ()) -> dict[str, Plugin]` that reads `pyproject.toml` entry points under the `modelfoundry.plugins` group and optionally walks extra paths from `MODELFOUNDRY_PLUGIN_PATH`. (`extra_paths` is supplied by callers as the resolved `RuntimeConfig.plugin_path` tuple, which A.e's `from_env` already parses from the env var.)
- [x] `PluginError` on duplicate plugin names or unresolvable entry points.
- [x] Unit tests with a synthetic in-process plugin: discovery finds the plugin; duplicate names raise `PluginError`; the `Plugin` Protocol's `isinstance` check works at runtime.
- [x] Verify: `pyve test tests/unit/test_plugin_discovery.py` passes.

### Story B.i: DataRefinery instance binding — `pipeline.data_binding` [Done]

`features.md` FR-6, `tech-spec.md` § `pipeline.data_binding`. Spike outcome from A.c locks the pattern here.

- [x] Create `src/modelfoundry/pipeline/__init__.py` and `src/modelfoundry/pipeline/data_binding.py` with `resolve_data_instance(data_spec: DataSpec, runtime_config: RuntimeConfig) -> DataRefineryInstance` (compute the DataRefinery canonical hash → locate the promoted instance under the resolved cache root → load its manifest → return a wrapper exposing `splits`, `label_schema`, `record_schema`, `manifest`). (Locates by scanning `<data-cache-root>/instances/<recipe-hash16>/*/<seed>/` — DR's `compute_cache_key` needs raw input hashes which aren't available without re-reading source bytes. Exactly-one-match required; multiple → ambiguous bind.)
- [x] If `ml-datarefinery` is installable, import `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS` and `datarefinery.Instance.load`; otherwise use the mock pattern from A.c's outcome doc. (Real DR is installable in this env; the binding uses `datarefinery.Instance.load` directly and also calls `datarefinery.recipe.variants.apply_variant` when `DataSpec.variant` is set — DR's `load()` does not accept `variant=` itself.)
- [x] Cross-validation helpers (consumed by the validator in B.m): `instance_provides_splits(splits: list[str]) -> bool`, `instance_num_classes() -> int`, `instance_schema_version() -> int`. (`instance_num_classes` scans `dataset/train.jsonl` for unique label values per A.c's finding that DR doesn't enumerate classes in the manifest.)
- [x] Raise `DataBindingError` on: instance not on disk, partial instance (FAILED marker), missing required manifest fields, schema-version higher than ModelFoundry's known max. (Also: ambiguous bind, missing recipe YAML, aggressive sidecar missing.)
- [x] Unit tests with a synthesized DataRefinery instance fixture (mimics the vendor-dep-spec on-disk layout): resolution succeeds; missing instance → clear error; partial instance refused; aggressive variant sidecar PNG missing → refused. (Fixture is hand-built via DR's own `Recipe`/`Manifest` models — fast and isolated, no `materialize` round-trip.)
- [x] Verify: `pyve test tests/unit/test_data_binding.py` passes.

### Story B.j: Seeding contract — `pipeline.seeding` [Done]

`features.md` FR-25, `tech-spec.md` § `pipeline.seeding`. **See `project-essentials.md` § Determinism contract is foundational.**

- [x] Create `src/modelfoundry/pipeline/seeding.py` with `derive_seed(master_seed: int, scope: str, *salts: bytes) -> int` (sha256-derived; documented scopes `"weight_init"`, `"data_shuffle"`, `"optuna_sampler"`, `"augmentation:<op_id>"`, `"dropout"`).
- [x] `worker_init_fn_factory(master_seed: int) -> Callable[[int], None]` returning a function that seeds each DataLoader worker deterministically from `(master_seed, worker_id)` — output bytes independent of `num_workers`. (Lazy `import torch` inside the worker_init_fn — silently skipped when the `[pytorch]` extra isn't installed; NumPy seed masked to 32-bit per its legacy API.)
- [x] Unit tests: same `(master_seed, scope, salts)` → same derived seed; different scope → different seed; `worker_init_fn` seeds NumPy + Python `random` + (if torch is installed) `torch.manual_seed` reproducibly per worker. (Torch path exercised via a fake-module monkey-patch since `torch` isn't in the base venv.)
- [x] Verify: `pyve test tests/unit/test_seeding.py` passes.

### Story B.k: Checkpoint format — `pipeline.checkpoint` (Q16 foundation) [Done]

`tech-spec.md` § `pipeline.checkpoint`. Forward-extensible dict layout per the Q16 developer directive — pre-production writes weights-only; future continued-training adds `optimizer_state` / `scheduler_state` / `rng_state` as additive keys with no public-API change.

- [x] Create `src/modelfoundry/pipeline/checkpoint.py` with `Checkpoint(pydantic.BaseModel)` carrying the pre-production keys (`epoch`, `weights`, `metric_value`, `recipe_hash16`, `schema_version: int = 1`) and `model_config = ConfigDict(extra="allow")` to tolerate future keys.
- [x] `Checkpoint.save(path)` and `Checkpoint.load(path)` helpers. Unknown keys on load are preserved (log-and-continue) so a future tool that reads a forward-extended checkpoint via a current loader sees the present-and-relevant keys without erroring on the new ones. (Persistence is pickle so tensor state_dicts round-trip; `torch.save` is itself pickle-based, so the PyTorch plugin can stack `torch.save(checkpoint.model_dump(), path)` without changing the schema contract.)
- [x] Unit tests: present-keys round-trip; unknown future-keys are preserved (not silently dropped); missing required keys → `pydantic.ValidationError`.
- [x] Verify: `pyve test tests/unit/test_checkpoint.py` passes.

### Story B.l: OutputExpectations evaluator — `pipeline.expectations` [Done]

`features.md` FR-15, `tech-spec.md` § `pipeline.expectations`.

- [x] Create `src/modelfoundry/pipeline/expectations.py` with `evaluate_expectations(expectations: list[ExpectationSpec], evaluation_metrics: dict[str, dict[str, Any]]) -> list[ExpectationOutcome]`. Supports `op: gte | lte | eq | within` per `ExpectationSpec`.
- [x] Failure handler: returns the list of outcomes; the materialize runner (Phase C) checks for any failures and writes the `FAILED` marker accordingly. (Module never raises; missing split, missing metric, and non-numeric observed each produce a `passed=False` outcome with a `detail` message.)
- [x] Unit tests: every `op` evaluated against passing + failing inputs; `within` with a 2-element list works; metric absent from evaluation → outcome marked failed with clear detail.
- [x] Verify: `pyve test tests/unit/test_expectations.py` passes.

### Story B.m: v0.3.0 Recipe validator — `recipe.validator` [Planned]

`features.md` FR-2, `tech-spec.md` § `recipe.validator`. Implements all 19 enumerated static logical checks; never short-circuits. Owns the Phase B v0.3.0 bump.

- [ ] Create `src/modelfoundry/recipe/validator.py` with `ValidationCheck` + `ValidationReport` pydantic models and `validate(recipe, data_instance, plugin) -> ValidationReport`.
- [ ] Implement checks 1..19 per `features.md` FR-2:
  - 1: schema_version recognised
  - 2: plugin recognised + discoverable
  - 3: section names valid for declared plugin
  - 4: every op declares applicable splits where applicable
  - 5: fit-on-train discipline (e.g. `weight_source: train`)
  - 6: `Training.early_stopping.monitor` references a produced metric
  - 7: `Optimization.search_space` keys reference real recipe paths
  - 8: `baseline_trial: enqueue_recipe_defaults` categorical hyperparameter defaults are valid choices
  - 9: `Optimization.sampler` ∈ {tpe, random, grid}; `pruner` ∈ {median, none}
  - 10: `Optimization.n_jobs` is absent or 1
  - 11: `Evaluation.metrics` names ∈ pre-production vocabulary
  - 12: `Evaluation.primary_metric` ∈ `Evaluation.metrics`
  - 13: `Evaluation.comparison.baseline_model_id` shape (name-format check; resolution at materialize)
  - 14: `OutputExpectations` references metrics produced on the declared split
  - 15: `Visualizations` ops each declare an output mode
  - 16: `variants` reference only declared sections + keys
  - 17: plugin-specific operation params validate against `OperationSpec.param_model`
  - 18: `Data:` binding cross-check (splits present, num_classes match, record schema compatible)
  - 19: DataRefinery schema-version coordination — error if bound instance's recipe schema is higher than ModelFoundry's known max
- [ ] One test per check under `tests/unit/test_recipe_validator.py` with focused recipe fixtures. Validator never short-circuits — all failures are reported.
- [ ] Bump version to v0.3.0.
- [ ] Update CHANGELOG.md (Phase B summary: recipe loader + variants + canonical bytes + cache identity + cache layout + atomic promote + manifest + plugin Protocol + DataRefinery binding + seeding + checkpoint + expectations + validator).
- [ ] Verify: `pyve test tests/unit/test_recipe_validator.py` passes; `pyve testenv run mypy src tests` clean.

---

## Phase C: PyTorch Plugin + Materialize Orchestrator

Implement the PyTorch plugin end-to-end (architecture vocabulary, losses, optimizers, schedules, deterministic training, DataRefinery dataset adapter, lazy augmentations, training loop, Optuna optimization, evaluation, visualizations, persistence), ship the sklearn stub for plugin-interface honesty, build the materialize orchestrator that sequences every stage atomically, and expose the `ModelFoundry`/`ModelInstance` library API. By end of Phase C, a Python program can call `ModelFoundry.from_recipe(...).materialize()` against a bound DataRefinery instance and get back a notebook-shaped `ModelInstance`.

### Story C.a: Architectural spike — deterministic PyTorch training loop [Planned]

Throwaway script in `scripts/`. Validate the most uncertain architectural assumption before the production PyTorch plugin lands: can `torch.use_deterministic_algorithms(True)` + `CUBLAS_WORKSPACE_CONFIG=:4096:8` + the `worker_init_fn_factory` from B.j produce byte-identical model state across two runs of a minimal CNN training loop on a synthetic dataset (CPU + `num_workers=1, 2, 4`)? Deliverable is the documented outcome.

- [ ] Create `scripts/spike_pytorch_determinism.py`: minimal `nn.Module` (2-layer CNN), synthetic 32-record image dataset, 2-epoch training loop. Run three times across `num_workers ∈ {1, 2, 4}` and compare `model.state_dict()` byte-by-byte.
- [ ] Run the same script with `torch.use_deterministic_algorithms(False)` to confirm non-determinism without the guard.
- [ ] Document outcome in `docs/spikes/C.a-pytorch-determinism.md`: which ops (if any) hard-error under deterministic mode; the env-var setup pattern; the `worker_init_fn` integration pattern; any platform-specific surprises on macOS-MPS (or CPU-only if MPS is sidestepped).
- [ ] Note any integration risks for C.e (determinism module) and C.h (trainer).
- [ ] Verify: spike runs; byte-identity holds under deterministic mode + worker_init_fn; outcome doc captures the production pattern.

### Story C.b: PyTorch plugin scaffold + health_check + registration [Planned]

`tech-spec.md` § `plugins.pytorch`. Smallest possible plugin: registers a `name = "pytorch"`, empty `operations`, working `health_check` (reports torch/torchvision/torchmetrics availability + accelerator detection). Used by the registration test in B.h's discovery harness.

- [ ] Create `src/modelfoundry/plugins/pytorch/__init__.py` and `src/modelfoundry/plugins/pytorch/plugin.py` implementing the `Plugin` Protocol skeleton (all methods raise `NotImplementedError` except `health_check`).
- [ ] Wire the plugin entry point into `pyproject.toml` under `[project.entry-points."modelfoundry.plugins"]`.
- [ ] `health_check` returns a `CheckReport` listing torch / torchvision / torchmetrics versions, accelerator (MPS / CUDA / CPU-only), and whether deterministic-algorithm mode is enable-able on this backend.
- [ ] Integration test: `discover_plugins()` finds the pytorch plugin; `health_check()` returns a non-error report on the test machine.
- [ ] Verify: `pyve test tests/integration/test_pytorch_plugin_registration.py` passes.

### Story C.c: PyTorch architecture vocabulary — `plugins.pytorch.architecture` [Planned]

`features.md` FR-7 / FR-ARCH-1, `tech-spec.md` § `plugins.pytorch` > `architecture.py`. CIFAR-10 baseline CNN vocabulary.

- [ ] Create `src/modelfoundry/plugins/pytorch/architecture.py` registering primitives (`Conv2d`, `BatchNorm2d`, `ReLU`, `MaxPool2d`, `AvgPool2d`, `AdaptiveAvgPool2d`, `Linear`, `Dropout`, `Flatten`), composites (`MLP`, `ConvBlock`, `ResidualBlock`), and baseline architectures (`simple_cnn`, `resnet8`). Each op pairs an `nn.Module` subclass with a pydantic `OperationSpec.param_model`.
- [ ] Recursive builder `build_model(arch_spec) -> nn.Module` reads the canonical `Architecture` block from the recipe and composes ops. Validates `num_classes` matches the bound DataRefinery instance's label count.
- [ ] Optional pretrained-encoder + LoRA path (`Encoder`, `LoRA`, `Pooling`, `Head`) declared in `requires_extras=("huggingface",)` so recipe-time validation works without `[huggingface]` installed; `build_model` raises a clear `ImportError` at materialize time if extras are missing.
- [ ] Unit tests: every op resolves; `simple_cnn` and `resnet8` instantiate cleanly; bad params → pydantic `ValidationError` → mapped to `PluginError`.
- [ ] Verify: `pyve test tests/unit/test_pytorch_architecture.py` passes.

### Story C.d: PyTorch losses, optimizers, schedules [Planned]

`features.md` FR-LOSS-1 / FR-OPT-1 / FR-OPT-2, `tech-spec.md` § `plugins.pytorch` > `losses.py` / `optimizers.py` / `schedules.py`.

- [ ] `losses.py`: `cross_entropy`, `cross_entropy_class_weighted` (with `weight_source: train | train_inverse_frequency | effective_number`, weights fit on train at training start, persisted to `training/class_weights.json`), `bce_with_logits` (recipe-time rejected when `num_classes > 2`).
- [ ] `optimizers.py`: `adamw`, `sgd`, `adam` with their typed params.
- [ ] `schedules.py`: `reduce_on_plateau`, `cosine`, `linear_warmup` with their typed params.
- [ ] Each op registered as an `OperationSpec` in the plugin's `operations` dict.
- [ ] Unit tests: each op constructs the correct `torch.nn` / `torch.optim` / `torch.optim.lr_scheduler` object with the expected hyperparameters; class-weighted loss correctly derives weights from a synthetic train-split label distribution.
- [ ] Verify: `pyve test tests/unit/test_pytorch_ops.py` passes.

### Story C.e: PyTorch determinism module — `plugins.pytorch.determinism` [Planned]

`features.md` QR-3, `tech-spec.md` § `plugins.pytorch` > `determinism.py`. C.a's spike outcome locks the pattern here.

- [ ] Create `src/modelfoundry/plugins/pytorch/determinism.py` with `enable_deterministic_algorithms() -> None` (sets `os.environ["CUBLAS_WORKSPACE_CONFIG"]` if unset; calls `torch.use_deterministic_algorithms(True)`; sets `torch.manual_seed` / `torch.cuda.manual_seed_all` / MPS seed as applicable).
- [ ] `documented_hard_error_ops: tuple[str, ...]` listing ops known to hard-error under deterministic mode (sourced from C.a's spike outcome).
- [ ] Integration into the plugin's `health_check`: report whether deterministic mode can be enabled on the installed backend; report which documented ops would hard-error.
- [ ] Unit tests: `enable_deterministic_algorithms()` is idempotent; environment variable is set; the hard-error documentation list matches the spike outcome.
- [ ] Verify: `pyve test tests/unit/test_pytorch_determinism.py` passes.

### Story C.f: PyTorch `DataRefineryDataset` adapter — `plugins.pytorch.data` [Planned]

`tech-spec.md` § `plugins.pytorch` > `data.py`. A.c's spike outcome locks the binding pattern.

- [ ] Create `src/modelfoundry/plugins/pytorch/data.py` with `DataRefineryDataset(torch.utils.data.Dataset)`: constructor takes the bound `DataRefineryInstance` + split name + recipe `Augmentations` policy; `__len__` reads `manifest.record_counts[split]`; `__getitem__` reads the JSONL line, resolves `path` or `image_path` per the vendor-dep-spec, decodes via Pillow, applies lazy augmentations.
- [ ] Honour per-record-seed stamps (`<AugmentationOp.name>_seed`) from DataRefinery's JSONL for aggressive variants (read directly); lazy augmentations realize via the C.g augmenters seeded from `pipeline.seeding`.
- [ ] `DataLoader` factory helper `build_dataloader(dataset, training_spec, master_seed) -> DataLoader` (uses `worker_init_fn_factory(master_seed)` from B.j; `generator` seeded; `pin_memory` toggled per accelerator availability).
- [ ] Unit tests against the synthesized DataRefinery fixture: dataset length matches manifest; record decoding produces a tensor of the expected shape; iteration with `num_workers=1` and `num_workers=2` produces identical output (per `worker_init_fn`).
- [ ] Verify: `pyve test tests/unit/test_pytorch_data_adapter.py` passes.

### Story C.g: PyTorch lazy augmentations — `plugins.pytorch.augmentations` [Planned]

`tech-spec.md` § `plugins.pytorch` > `augmentations.py`. Q4 from plan_tech_spec — torchvision-v2 realizers, semantic-equivalence (not byte-equivalence) with DataRefinery's Pillow aggressive realizers.

- [ ] Create `src/modelfoundry/plugins/pytorch/augmentations.py` with realizers for `random_crop`, `horizontal_flip`, `color_jitter`, `random_erasing` over `torchvision.transforms.v2`. Each realizer takes the op's param model + a per-record/per-variant seed (via `derive_seed`) and produces a transform.
- [ ] Composer helper `compose_augmentations(augmentations: list[AugmentationOp], master_seed: int) -> Callable` returning a callable suitable for `DataRefineryDataset.__getitem__`.
- [ ] Unit tests: each realizer with a fixed seed produces deterministic output; semantic-equivalence with DataRefinery's Pillow realizers verified in Phase E (Hypothesis property tests).
- [ ] Verify: `pyve test tests/unit/test_pytorch_augmentations.py` passes (basic determinism; equivalence to DataRefinery lives in E.g).

### Story C.h: PyTorch trainer — `plugins.pytorch.trainer` [Planned]

`features.md` FR-10, `tech-spec.md` § `plugins.pytorch` > `trainer.py`.

- [ ] Create `src/modelfoundry/plugins/pytorch/trainer.py` with `run_training(training_spec, model, recipe, data_instance, seed, temp_dir) -> TrainingResult`. Implements the training loop: per-epoch iteration, backprop + optimizer step, validation pass (for early-stopping monitor), schedule drive, history append to `training/history.parquet`, checkpoint write per `checkpoint_cadence` using the `Checkpoint` model from B.k, early-stopping evaluation, best-monitor-value promotion to `model/weights/`.
- [ ] Calls `enable_deterministic_algorithms()` from C.e before model construction.
- [ ] Uses `build_dataloader` from C.f with `worker_init_fn_factory` from B.j.
- [ ] Class weights (from C.d's `cross_entropy_class_weighted`) fit on the train split at training start; persist to `training/class_weights.json`.
- [ ] Integration test (small synthetic dataset): trainer runs 3 epochs, writes `history.parquet` with the expected columns, writes checkpoints, promotes the best checkpoint to `model/weights/`. Re-running with the same seed produces byte-identical history.
- [ ] Verify: `pyve test tests/integration/test_pytorch_trainer.py` passes.

### Story C.i: PyTorch Optuna optimization — `plugins.pytorch.optimization` [Planned]

`features.md` FR-11, `tech-spec.md` § `plugins.pytorch` > `optimization.py`.

- [ ] Create `src/modelfoundry/plugins/pytorch/optimization.py` with `run_optimization(opt_spec, recipe, data_instance, seed, temp_dir) -> OptimizationResult`. Builds Optuna `Study` with `RDBStorage("sqlite:///<temp-dir>/optimization/study.db")`; sampler seeded via `derive_seed(master_seed, "optuna_sampler")`; `n_jobs=1` enforced; pruner `MedianPruner` or none.
- [ ] `baseline_trial: enqueue_recipe_defaults`: calls `study.enqueue_trial(...)` with the recipe's hyperparameter values flattened from the search-space-relevant fields.
- [ ] Trial loop: sample hyperparameters → apply to recipe copy → run short Training (capped by `max_epochs_per_trial`) → report intermediate values per epoch → return `Evaluation.primary_metric` (or `Optimization.objective_metric`) evaluated on `val` as the trial value.
- [ ] Persists `trials.parquet` (matches Optuna's `study.trials_dataframe()` shape) and `best-params.json`.
- [ ] Best-trial params merged back into the recipe via `recipe.search_space.apply_params(...)` before the Training stage runs (auto-composition, FR-3 step 4.2 → 4.3).
- [ ] Integration test: 3-trial TPE study deterministic across reruns; baseline_trial enqueued correctly; best-params merge into the recipe.
- [ ] Verify: `pyve test tests/integration/test_pytorch_optimization.py` passes.

### Story C.j: PyTorch evaluation — `plugins.pytorch.evaluation` [Planned]

`features.md` FR-12 / FR-22, `tech-spec.md` § `plugins.pytorch` > `evaluation.py`. Metric implementations via `torchmetrics`; predictions persistence.

- [ ] Create `src/modelfoundry/plugins/pytorch/evaluation.py` with `run_evaluation(eval_spec, model, data_instance, temp_dir) -> EvaluationResult`. Iterates each split in `Evaluation.splits`; runs inference; computes metrics via `torchmetrics` (`MulticlassF1Score`, `MulticlassPrecision`, `MulticlassRecall`, `MulticlassAccuracy`, `MulticlassConfusionMatrix`, `CalibrationError`).
- [ ] `calibration_curve` via the sklearn helper from C.m's shared `plugins/sklearn/metrics.py`.
- [ ] Persists `evaluation/metrics.json`, `evaluation/confusion_matrix.npz`, `evaluation/calibration.parquet` (when applicable), and `evaluation/predictions.parquet` (columns: `split`, `record_id`, `true_label`, `pred_label`, `pred_proba_<class>` per declared class).
- [ ] `Evaluation.comparison.baseline_model_id`: lazy-resolve via the plugin's baseline resolver; failures emit a warning and continue.
- [ ] Integration test: every metric in the pre-production vocabulary computes against a hand-computed golden; `predictions.parquet` has the expected columns and row count.
- [ ] Verify: `pyve test tests/integration/test_pytorch_evaluation.py` passes.

### Story C.k: PyTorch visualizations — `plugins.pytorch.visualizations` [Planned]

`features.md` FR-13, `tech-spec.md` § `plugins.pytorch` > `visualizations.py`. Matplotlib renderers for the registered ops.

- [ ] Create `src/modelfoundry/plugins/pytorch/visualizations.py` with renderers for `training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid`. Each takes an `InstanceArtifacts` snapshot (history dataframe, evaluation dict, predictions dataframe, optional trials dataframe) and returns PNG bytes.
- [ ] `optimization_history` renders an empty-placeholder PNG when no Optimization stage ran (so manifest viz records stay consistent).
- [ ] `predictions_grid` renders labels-only when the bound DataRefinery instance does not expose per-record images.
- [ ] Unit tests: each renderer produces a PNG of nontrivial size; byte-deterministic across reruns with a fixed matplotlib backend (Agg).
- [ ] Verify: `pyve test tests/unit/test_pytorch_visualizations.py` passes.

### Story C.l: PyTorch persistence + round-trip — `plugins.pytorch.persistence` [Planned]

`features.md` FR-23 (round-trip from disk alone), `tech-spec.md` § `plugins.pytorch` > `persistence.py`. **See `project-essentials.md` § Cache identity is the reproducibility contract** for the architecture.json round-trip discipline.

- [ ] Create `src/modelfoundry/plugins/pytorch/persistence.py` with:
  - `save_model(model, model_dir)`: writes `model/weights/state_dict.pt` via `torch.save(model.state_dict(), ...)`; writes `model/architecture.json` (the canonical post-variant-overlay, post-Optimization-merge `Architecture` block, JSON-canonical bytes via `canonical_bytes`); writes `model/checkpoints/checkpoint-best.pt` (the `Checkpoint` model from B.k).
  - `load_model(path) -> nn.Module`: reads `model/architecture.json`, rebuilds the `nn.Module` via the C.c recursive builder, then `load_state_dict` from `model/weights/state_dict.pt`. No external config object required.
- [ ] `predict(model, X) -> np.ndarray | pd.Series` and `predict_proba(model, X) -> np.ndarray | pd.DataFrame` accepting `pd.DataFrame` (record-schema), `list[Path]` (image paths), or 4-D `np.ndarray` of shape `(N, H, W, C)`.
- [ ] Integration test: save a trained `simple_cnn` to a temp dir; load via `load_model`; `predict(X)` returns the same outputs as the original model on a fixed input batch (round-trip guarantee).
- [ ] Verify: `pyve test tests/integration/test_pytorch_round_trip.py` passes.

### Story C.m: sklearn stub plugin + shared metric implementations [Planned]

`features.md` FR-24 (sklearn stub for plugin-interface honesty), `tech-spec.md` § `plugins.sklearn`.

- [ ] Create `src/modelfoundry/plugins/sklearn/__init__.py`, `src/modelfoundry/plugins/sklearn/plugin.py` (stub): registers the full `OperationSpec` set (mirroring the pytorch plugin's ops where applicable); `materialize()` against `plugin: sklearn` raises the documented `PluginError` redirect message.
- [ ] `src/modelfoundry/plugins/sklearn/metrics.py`: shared sklearn-based metric implementations (`f1_score`, `confusion_matrix`, `calibration_curve`, hand-rolled ECE) consumed by the pytorch plugin (per C.j's calibration_curve dependency).
- [ ] Wire the sklearn entry point into `pyproject.toml` under `[project.entry-points."modelfoundry.plugins"]`.
- [ ] Integration test: `discover_plugins()` finds both `pytorch` and `sklearn`; sklearn `health_check()` reports "stub"; `materialize()` against a `plugin: sklearn` recipe raises `PluginError` with the documented message.
- [ ] Verify: `pyve test tests/integration/test_sklearn_stub.py` passes.

### Story C.n: Reporting — `reporting.report` + reporting visualizations pipeline [Planned]

`features.md` FR-18, `tech-spec.md` § `reporting`.

- [ ] Create `src/modelfoundry/reporting/__init__.py`, `src/modelfoundry/reporting/report.py` with `render_report(instance_artifacts) -> str` (Markdown summary of recipe + plugin + metrics + optimization summary + expectations + warnings).
- [ ] `src/modelfoundry/reporting/visualizations.py`: drives the reporting-mode visualizations from the recipe's `Visualizations` block where `mode: reporting`. Writes PNG bytes from each plugin renderer to `report/visualizations/<name>.png`.
- [ ] `instance.render_report()` (called from C.p) re-renders into a `report.tmp/` and atomically replaces `report/` on success — preserves the existing report on failure.
- [ ] Unit tests: `render_report` produces a Markdown doc with the expected section headings; viz dispatcher correctly routes mode=reporting ops to the plugin.
- [ ] Verify: `pyve test tests/unit/test_reporting.py` passes.

### Story C.o: Materialize orchestrator — `pipeline.runner.MaterializeRunner` [Planned]

`features.md` FR-3, `tech-spec.md` § `pipeline.runner`. The orchestrator that sequences every stage atomically.

- [ ] Create `src/modelfoundry/pipeline/runner.py` with `MaterializeRunner.run() -> Manifest`. Sequences the stages per FR-3 step 4: Architecture → Optimization (if declared) → Training → Evaluation → OutputExpectations → Reporting visualizations → Persistence → Report → Manifest.
- [ ] Wraps each stage with structured logging (`logging.JsonFormatter`) and elapsed-time accounting that flows into `Manifest.elapsed_seconds` and per-stage timing in the report.
- [ ] On any stage exception: writes the `FAILED` marker (via `cache.atomic`) naming the failing stage + error class + message; re-raises as `MaterializeError`. OutputExpectations failure handled the same way with `ExpectationError`.
- [ ] Stage skipping: `Optimization` absent → skip stage 2; `Evaluation.splits` empty → skip stage 4; manifest records skipped stages.
- [ ] Integration test against the C.f synthesized fixture: full materialize end-to-end produces a complete instance directory with manifest, model artifacts, training history, evaluation metrics, predictions, report.
- [ ] Verify: `pyve test tests/integration/test_materialize_runner.py` passes.

### Story C.p: v0.4.0 `ModelFoundry` class + `ModelInstance` notebook-shaped accessors [Planned]

`features.md` FR-22, `tech-spec.md` § Key Component Design > `ModelFoundry` + `ModelInstance`. The library entry point + the substrate-neutral result object. Owns the Phase C v0.4.0 bump.

- [ ] Create `src/modelfoundry/core/__init__.py`, `src/modelfoundry/core/modelfoundry.py` with `ModelFoundry.from_recipe(recipe_path, *, data, config=None, variant=None, seed=None) -> ModelFoundry` and the verbs `validate`, `materialize`, `status`, `inspect`, `report`, `clean`, `check`. Verbs are thin wrappers that share construction state.
- [ ] Top-level `materialize(...)` convenience function per `tech-spec.md`.
- [ ] `src/modelfoundry/core/instance.py` with `ModelInstance` frozen dataclass + the cached-property accessors (`metrics`, `evaluation`, `confusion_matrix`, `calibration`, `predictions`, `trials`, `best_params`, `figures`) + `predict(X)` / `predict_proba(X)` (delegated to the plugin) + `load(path)` classmethod + `render_report()`.
- [ ] Re-export `ModelFoundry`, `ModelInstance`, `materialize`, `ModelfoundryError` from `src/modelfoundry/__init__.py`.
- [ ] Integration test: full materialize via `ModelFoundry.from_recipe(...).materialize()`; every `ModelInstance` accessor returns the expected type and shape; `ModelInstance.load(path).predict(X)` round-trips per FR-23.
- [ ] Bump version to v0.4.0.
- [ ] Update CHANGELOG.md (Phase C summary: end-to-end PyTorch plugin + sklearn stub + materialize orchestrator + ModelFoundry library API).
- [ ] Verify: `pyve test tests/integration/test_modelfoundry_api.py` passes; `from modelfoundry import ModelFoundry, ModelInstance, materialize, ModelfoundryError` works.

---

## Phase D: CLI

Wrap the library API in a Typer-based CLI exposing all eight verbs (`init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`). Each verb emits `rich`-styled user output to stdout and structured JSON-lines operational logs to the configured log target. The CLI is co-equal with the library API — both go through the same `ModelFoundry` class. By end of Phase D, a developer can drive the full workflow from the shell against a real DataRefinery instance.

### Story D.a: CLI scaffolding — `cli.app` + shared options + exit-code mapping [Planned]

`tech-spec.md` § CLI Design.

- [ ] Create `src/modelfoundry/cli/__init__.py`, `src/modelfoundry/cli/app.py` with the root `typer.Typer()` instance + `main()` entry point + shared options (`--cache-root`, `--data-cache-root`, `--log-level`, `--log-target`, `--plugin-path`, `--verbose`, `--quiet`).
- [ ] Exit-code mapping: `0` success, `1` user/recipe/contract error (catches `RecipeError` / `ValidationError` / `DataBindingError` / `ExpectationError` / `ModelArtifactExistsError`), `2` system/plugin error (`PluginError` / `MaterializeError` / `CacheError` / `OptimizationError`), `130` SIGINT.
- [ ] Wire shared options into a per-invocation `RuntimeConfig` that is passed to every verb.
- [ ] Re-point the placeholder console script from A.a to the real `cli.app:main`.
- [ ] Verify: `pyve run modelfoundry --help` lists the scaffolded `init`/`validate`/`check`/`status`/`materialize`/`report`/`inspect`/`clean` placeholders; exit codes work for a deliberately-raised error.

### Story D.b: `validate` command [Planned]

`features.md` FR-2.

- [ ] Create `src/modelfoundry/cli/commands/validate_cmd.py`: takes a recipe path; calls `ModelFoundry.from_recipe(...).validate()`; renders the `ValidationReport` as a `rich` table; exits 0 if all checks pass, 1 otherwise.
- [ ] CLI smoke test against a valid recipe + a failing recipe.
- [ ] Verify: `pyve run modelfoundry validate <fixture-recipe>` works.

### Story D.c: `check` command [Planned]

`features.md` FR-19.

- [ ] Create `src/modelfoundry/cli/commands/check_cmd.py`: calls `ModelFoundry.check()`; renders a `rich` table summarising Python version, installed ModelFoundry version, plugin discovery, per-plugin `health_check` outputs, accelerator availability.
- [ ] Exit non-zero if any required dep is missing or any plugin's `health_check` reports an unrecoverable error.
- [ ] CLI smoke test.
- [ ] Verify: `pyve run modelfoundry check` works on the test machine.

### Story D.d: `status` command [Planned]

`features.md` FR-16.

- [ ] Create `src/modelfoundry/cli/commands/status_cmd.py`: takes a recipe path; resolves cache key; if instance exists, loads manifest + renders summary table (plugin, plugin_version, schema_version, recipe_hash, bound_data_instance, seed, variant, cache hit, materialize timestamp, elapsed seconds, primary metric, expectations passed/failed counts). If absent, reports "not materialized" with expected path.
- [ ] CLI smoke test against a fixture instance.
- [ ] Verify: `pyve run modelfoundry status <recipe>` works.

### Story D.e: `materialize` command [Planned]

`features.md` FR-3.

- [ ] Create `src/modelfoundry/cli/commands/materialize_cmd.py`: takes a recipe path + `--variant` + `--seed` + `--overwrite`; calls `ModelFoundry.from_recipe(...).materialize(overwrite=...)`; streams per-epoch `rich` progress tables during Training, per-trial progress bars during Optimization (with fd-level suppression for trial > 0); prints final summary on success; non-zero exit on failure.
- [ ] CLI smoke test against a tiny recipe + synthetic DataRefinery fixture (3-epoch, 2-trial); assert exit code, summary contents, instance directory created.
- [ ] Verify: `pyve run modelfoundry materialize <fixture-recipe>` works end-to-end.

### Story D.f: `report` command [Planned]

`features.md` FR-18.

- [ ] Create `src/modelfoundry/cli/commands/report_cmd.py`: takes an instance path; calls `ModelInstance.load(path).render_report()`; prints final path on success.
- [ ] CLI smoke test against a fixture instance.
- [ ] Verify: `pyve run modelfoundry report <instance>` re-renders report/.

### Story D.g: `inspect` command [Planned]

`features.md` FR-17.

- [ ] Create `src/modelfoundry/cli/commands/inspect_cmd.py`: takes an instance path + `--view <name>`; calls `ModelInstance.load(path).inspect(view=...)`; renders the requested view (writes PNG to a temp file for PNG views and prints the path; renders a `rich` table for text views like `view_manifest`).
- [ ] CLI smoke test.
- [ ] Verify: `pyve run modelfoundry inspect <instance> --view training_curves` works.

### Story D.h: `clean` command [Planned]

`features.md` FR-20.

- [ ] Create `src/modelfoundry/cli/commands/clean_cmd.py`: `--recipe-hash`, `--older-than`, `--failed`, `--orphans`, `--dry-run` selectors per `features.md` FR-20.
- [ ] `cache.cleaner` module implementation: `src/modelfoundry/cache/cleaner.py` with the selector logic.
- [ ] CLI smoke tests for each selector.
- [ ] Verify: `pyve run modelfoundry clean --dry-run --older-than 7d` works.

### Story D.i: v0.5.0 `init` deterministic scaffolder [Planned]

`features.md` FR-21. Owns the Phase D v0.5.0 bump.

- [ ] Create `src/modelfoundry/scaffolder/__init__.py`, `src/modelfoundry/scaffolder/init.py` with `scaffold_recipe(recipe_path, datarefinery_recipe_path, *, plugin="pytorch", force=False) -> Path`. Reads the bound DataRefinery instance's manifest, picks a baseline architecture / loss / optimizer / training policy / evaluation metrics / OutputExpectations for the dataset shape.
- [ ] Stamps the Apache-2.0 / Pointmatic header at the top of the recipe as a YAML comment.
- [ ] CLI: `src/modelfoundry/cli/commands/init_cmd.py` with `modelfoundry init <recipe-path> --data <datarefinery-recipe-path> [--plugin pytorch] [--force]`.
- [ ] Reserved `scaffolder/llm.py` per the deferred `[llm]` extra — note in the package tree comment that it's not implemented in the pre-production series.
- [ ] CLI smoke test: scaffold a recipe against the fixture DataRefinery instance; resulting recipe loads, validates, and materializes (small) cleanly.
- [ ] Bump version to v0.5.0.
- [ ] Update CHANGELOG.md (Phase D summary: full CLI surface — `init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`).
- [ ] Verify: every CLI verb works against the fixture; `pyve testenv run mypy src tests` clean.

---

## Phase E: Testing & Quality

Build the test suite. By end of Phase E, the project has: a synthesized DataRefinery fixture builder; validator check coverage (one test per FR-2 check 1..19); cache identity property tests (Hypothesis); atomic promote + checkpoint format tests; determinism + round-trip integration tests; loose-coupling guarantee test; PyTorch plugin tests (metrics + optimization + augmentations equivalence); OutputExpectations tests; plugin contract tests; CLI smoke tests; Jupyter substrate-neutral smoke; and the capstone CIFAR-10 end-to-end smoke (TR-12 / AC-2). Coverage ≥ 95% on the core invariant modules per TR-15.

### Story E.a: Test fixture foundation — `conftest` + synthesized DataRefinery builder + sample recipes [Planned]

`tech-spec.md` § Testing Strategy > Fixtures.

- [ ] Expand `tests/conftest.py` with shared fixtures: `tmp_cache_root` (pytest `tmp_path` based), `tmp_data_cache_root`, `runtime_config` (with the two cache roots wired).
- [ ] Create `tests/fixtures/datarefinery_instances/builder.py` that synthesizes a 100-record DataRefinery instance with 3 classes / 2 splits, mimicking the vendor-dep-spec's on-disk layout (manifest.json, dataset/<split>.jsonl, optional sidecar PNGs for an aggressive variant).
- [ ] Create `tests/fixtures/recipes/`: `minimal_pytorch.yml`, `pytorch_with_optimization.yml`, `pytorch_with_variants.yml`, `pytorch_failing_expectations.yml`, `sklearn_stub.yml`, plus a directory of `invalid_*.yml` (one per validator rejection).
- [ ] Verify: fixture builder runs to completion; sample recipes load cleanly through `recipe.loader`.

### Story E.b: Validator check tests — one per FR-2 check 1..19 [Planned]

`features.md` TR-3.

- [ ] Expand `tests/unit/test_recipe_validator.py` (started in B.m) to one test per FR-2 check 1..19 with a focused failing recipe fixture and an assertion on the resulting `ValidationCheck.detail` / `offending_path`.
- [ ] Validator does not short-circuit: a recipe with multiple distinct failures produces all of them in the report.
- [ ] Verify: every FR-2 check has a dedicated test that exercises both the pass and fail paths.

### Story E.c: Cache identity property tests (Hypothesis) [Planned]

`features.md` TR-2.

- [ ] Property tests under `tests/unit/test_cache_identity_properties.py` using `hypothesis`: cosmetic edits (whitespace, comments, key reordering) preserve canonical bytes (and thus the hash); semantic edits (value mutation, op add/remove, variant switch) perturb canonical bytes; seed change perturbs `cache_key`; data instance hash change perturbs `data_instance_hash16` but does NOT perturb the consuming recipe's `recipe_hash16`.
- [ ] Verify: property tests pass; Hypothesis examples persisted to `.hypothesis/`.

### Story E.d: Atomic promote + checkpoint format tests [Planned]

`features.md` TR-4.

- [ ] `tests/unit/test_atomic_promote.py` (expanding B.f's coverage): force failure at every materialize stage and assert the `FAILED` marker is written with the expected stage name; assert the final cache path is never touched on failure; `--overwrite` correctly trashes existing.
- [ ] `tests/unit/test_checkpoint.py` (expanding B.k's coverage): forward-extensible keys are preserved on load; missing required keys raise; round-trip via parquet is byte-stable.
- [ ] Verify: both test modules pass.

### Story E.e: Determinism + round-trip integration tests [Planned]

`features.md` TR-5 (determinism) + TR-6 (round-trip).

- [ ] `tests/integration/test_determinism.py`: materialize the fixture recipe twice (same `(recipe, data_instance, seed, variant)`); assert byte-identical instance contents excluding `manifest.created_at` / `manifest.elapsed_seconds`. Run with `num_workers ∈ {1, 2, 4}` and assert all three produce identical bytes (the worker_init_fn contract from B.j).
- [ ] `tests/integration/test_round_trip.py`: materialize; `ModelInstance.load(path).predict(X)` succeeds without external config; predictions match the in-process model's predictions.
- [ ] Verify: both integration tests pass on the test machine; document any platform-specific tolerances if the macOS-MPS path produces non-byte-identical outputs (escalate per QR-3 caveats).

### Story E.f: Loose-coupling guarantee test [Planned]

`features.md` TR-7. **Validates `project-essentials.md` § Loose-coupled DataRefinery binding.**

- [ ] `tests/integration/test_loose_coupling.py`: build a DataRefinery fixture instance; materialize a ModelFoundry recipe against it. Re-build the DataRefinery fixture (same shape, same seed → same triple, so `data_instance_hash16` is unchanged) and assert the ModelFoundry cache is unchanged; the second `materialize()` returns a cache hit.
- [ ] Also test: change the DataRefinery fixture's seed → different triple → `data_instance_hash16` changes → ModelFoundry's cache miss is correct.
- [ ] Verify: integration test passes; assertion explicitly checks that ModelFoundry never wrote to DataRefinery's cache tree.

### Story E.g: PyTorch plugin tests — metrics + optimization + augmentation equivalence [Planned]

`features.md` TR-9 (metrics) + TR-10 (optimization).

- [ ] `tests/unit/test_pytorch_metrics.py`: each pre-production metric (`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `accuracy`, `confusion_matrix`, `ece`, `calibration_curve`) validated against a hand-computed golden value on a tiny fixture of (predictions, labels).
- [ ] `tests/integration/test_pytorch_optimization.py` (expanding C.i coverage): TPE, Random, Grid samplers each deterministic across reruns from a fixed seed; `baseline_trial: enqueue_recipe_defaults` enqueues correctly; best-params merge into the recipe before Training; `n_jobs > 1` rejected at validate time.
- [ ] `tests/unit/test_pytorch_augmentations.py` (Hypothesis): for each augmentation op, generate random images via Hypothesis, apply via torchvision-v2 lazy realizer + DataRefinery's documented aggressive realizer, assert visual-semantic equivalence (same image dimensions; same colour-space statistics within a documented tolerance; same flip / crop / erase outcomes for the same seed). Byte-equivalence is NOT asserted (the two paths use different libraries).
- [ ] Verify: all three test modules pass.

### Story E.h: OutputExpectations tests [Planned]

`features.md` TR-11.

- [ ] `tests/unit/test_output_expectations.py` (expanding B.l coverage): every `op` (`gte`, `lte`, `eq`, `within`) with passing + failing inputs; multiple expectations all surface in the `FAILED` marker (not just the first); expectation referencing a metric absent from `Evaluation.metrics` is caught at validate time (E.b check 14) rather than at materialize time.
- [ ] Integration test against the fixture: `pytorch_failing_expectations.yml` materialize ends with the `FAILED` marker.
- [ ] Verify: test module passes.

### Story E.i: Plugin contract tests [Planned]

`tech-spec.md` § Testing Strategy > Plugin contract tests.

- [ ] `tests/plugin_contract/test_pytorch_contract.py`: the pytorch plugin's declared `OperationSpec` set is exhaustive (every op listed in `features.md` matches a registered op); the `Plugin` Protocol's runtime `isinstance` check passes; `mypy --strict` on the plugin source clean.
- [ ] `tests/plugin_contract/test_sklearn_stub_contract.py`: the sklearn stub registers the full `OperationSpec` set; `materialize()` against `plugin: sklearn` raises `PluginError` with the documented message.
- [ ] Verify: both contract tests pass.

### Story E.j: CLI smoke tests [Planned]

`tech-spec.md` § Testing Strategy > CLI tests.

- [ ] One test module per verb under `tests/cli/`: `test_cli_init.py`, `test_cli_validate.py`, `test_cli_check.py`, `test_cli_status.py`, `test_cli_materialize.py`, `test_cli_report.py`, `test_cli_inspect.py`, `test_cli_clean.py`. Each runs the verb against the fixture DataRefinery + a minimal recipe; assertions cover exit code, structured `rich` output, JSON-lines log content on the configured `--log-target`.
- [ ] Verify: every CLI test passes.

### Story E.k: Notebook Jupyter smoke (TR-8) [Planned]

`features.md` TR-8.

- [ ] `tests/notebook/test_jupyter_smoke.py`: uses `nbclient` to execute a notebook cell that runs `ModelFoundry.from_recipe(...).materialize()` against a cached fixture instance and asserts `.metrics`, `.evaluation`, `.figures`, `.predictions` accessors render expected types. Marimo headless smoke and IPython REPL smoke are deferred per Q14.
- [ ] Add `nbclient` + `ipykernel` to `requirements-dev.txt` (already there per A.a, but verify).
- [ ] Verify: Jupyter smoke passes.

### Story E.l: v0.6.0 CIFAR-10 end-to-end smoke (TR-12 / AC-2) [Planned]

`features.md` CR-16 / TR-12 / AC-2. **The capstone exercise of every contract surface.** Owns the Phase E v0.6.0 bump.

- [ ] Create `tests/fixtures/datarefinery_instances/cifar10_smoke/builder.py`: produces a downsized CIFAR-10 instance (e.g. 500 train / 100 val / 100 test records, 32×32 RGB) materialized through DataRefinery's `image_classification` plugin. If `ml-datarefinery` is not installable, fall back to the mock pattern from A.c with a documented integration risk.
- [ ] Create `tests/fixtures/recipes/cifar10_smoke.yml`: 3-epoch, batch-size-32, `simple_cnn` recipe; 2-trial Optimization with 1-epoch trials; `Evaluation.splits: [val, test]`; OutputExpectations on `val_macro_f1 >= <floor>` calibrated against the CI environment.
- [ ] `tests/integration/test_cifar10_smoke.py`: `ModelFoundry.from_recipe("cifar10_smoke.yml", data=cifar10_instance).materialize()`; assert `ModelInstance.evaluation["val"]["macro_f1"]` exceeds the documented floor; assert all OutputExpectations pass; assert `predictions.parquet` has the expected row count and columns; assert the round-trip `ModelInstance.load(path).predict(X)` works.
- [ ] Sized to fit a free-tier CI runner's per-job budget on CPU per PE-3.
- [ ] Bump version to v0.6.0.
- [ ] Update CHANGELOG.md (Phase E summary: complete test suite + CIFAR-10 capstone smoke).
- [ ] Verify: `pyve test tests/integration/test_cifar10_smoke.py` passes locally on CPU; coverage ≥ 95% on TR-15 core modules; `pyve testenv run mypy src tests` clean.

---

## Phase F: Documentation & Release

Polish the documentation surface for the first release. README quickstart with the CIFAR-10 walkthrough, docstring + FR-note pass, CHANGELOG curation, pyproject.toml metadata audit. By end of Phase F the project is ready for a tagged release; the actual PyPI publish happens in Phase G after `publish.yml` is wired.

### Story F.a: README — quickstart + CIFAR-10 walkthrough + library/CLI usage [Planned]

`features.md` UR-6 (CIFAR-10 quickstart). Replaces the A.a placeholder README.

- [ ] Replace the placeholder `README.md` with the full release-ready document: project name, one-paragraph summary, install (`pip install ml-modelfoundry[pytorch]`), CIFAR-10 quickstart walkthrough (assuming a materialized DataRefinery CIFAR-10 instance), library API example (`ModelFoundry.from_recipe(...).materialize()`), CLI example (`modelfoundry materialize <recipe>`), notebook-substrate-neutrality note (works identically in Jupyter / Marimo / IPython / `.py`), pointers to `docs/specs/` for deeper docs.
- [ ] Verify: README renders cleanly on GitHub; quickstart steps are reproducible by an external reader.

### Story F.b: Documentation polish — docstrings + FR notes + typo pass [Planned]

- [ ] Pass through every public-API surface (`ModelFoundry`, `ModelInstance`, `materialize`, error classes) and tighten docstrings to release quality (one-line summary + Args + Returns + Raises). Reference relevant FR numbers from `features.md`.
- [ ] Pass through `concept.md`, `features.md`, `tech-spec.md`, `project-essentials.md` for typos, outdated pointers, broken cross-references.
- [ ] Verify: `pydocstyle` (or `ruff` doc rules) clean; no broken `docs/specs/*` cross-links.

### Story F.c: v0.7.0 Release prep — CHANGELOG curation + pyproject.toml metadata audit [Planned]

Owns the Phase F v0.7.0 bump.

- [ ] Curate `CHANGELOG.md`: per-phase summary entries with the right semver headers; add the v0.1.0 → v0.7.0 changelog history if any phase summaries were skipped during work.
- [ ] Audit `pyproject.toml` metadata: project description, keywords, classifiers (`Development Status :: 3 - Alpha`, `License :: OSI Approved :: Apache Software License`, `Programming Language :: Python :: 3.12`, etc.), `urls` (homepage, repository, issues), `readme = "README.md"`, `license-file = "LICENSE"`, `[project.urls]`.
- [ ] Bump version to v0.7.0.
- [ ] Update CHANGELOG.md (Phase F summary: release-ready README + docstring pass + metadata audit).
- [ ] Verify: `pyve run python -m build` produces a clean sdist + wheel; `pyve run twine check dist/*` passes; `pyve testenv run mypy src tests` clean; `pyve testenv run ruff check src tests` clean.

---

## Phase G: CI/CD & Automation

Wire up CI/CD automation. `ci.yml` runs lint + types + tests + CIFAR-10 smoke on every PR and push to `main`; `publish.yml` performs PyPI Trusted Publishing on `v*.*.*` tags. The Phase G v0.8.0 tag is the **first PyPI publish** for `ml-modelfoundry`. GitHub branch protection and Codecov / Coveralls upload are explicitly out of scope per CR-1 and `tech-spec.md` § CI/CD Automation.

### Story G.a: GitHub Actions `ci.yml` [Planned]

`features.md` OR-12 / TR-16, `tech-spec.md` § CI/CD Automation.

- [ ] Create `.github/workflows/ci.yml` that triggers on PR + push to `main`. Matrix: macOS Apple Silicon primary; Linux as stretch entry. Steps: checkout, install `pyve` (or `micromamba` directly for CI ergonomics), `pyve testenv init && pyve testenv install -r requirements-dev.txt`, `pyve testenv run ruff check src tests`, `pyve testenv run ruff format --check src tests`, `pyve testenv run mypy src tests`, `pyve test`, `pyve test tests/integration/test_cifar10_smoke.py`.
- [ ] Document any CI-specific accommodation (e.g. `MODELFOUNDRY_*` env vars; fallback for `ml-datarefinery` if not available in the CI environment).
- [ ] Verify: workflow file is syntactically valid (e.g. `actionlint` or GitHub's editor); after merge to a PR branch, the workflow runs and all steps pass.

### Story G.b: v0.8.0 GitHub Actions `publish.yml` — first PyPI publish [Planned]

`features.md` OR-11 / AC-13. Owns the Phase G v0.8.0 bump and triggers the first PyPI publish for `ml-modelfoundry`.

- [ ] Create `.github/workflows/publish.yml` triggered on tag push matching `v*.*.*`. Steps: checkout, build via `pyve run python -m build`, publish to PyPI via PyPI Trusted Publishing (no API token in secrets — the OIDC token from GitHub Actions is the credential).
- [ ] Configure PyPI Trusted Publishing on the PyPI side (out-of-band): add `ml-modelfoundry` as a project, register the GitHub repo + workflow filename as a trusted publisher.
- [ ] Bump version to v0.8.0.
- [ ] Update CHANGELOG.md (Phase G summary: CI/CD wired; first PyPI publish).
- [ ] Push the `v0.8.0` tag → `publish.yml` triggers → `ml-modelfoundry==0.8.0` lands on PyPI.
- [ ] Verify: workflow file syntactically valid; tagged release publishes successfully; `pip install ml-modelfoundry[pytorch]` from a clean Python 3.12 venv installs cleanly and `modelfoundry --version` prints `0.8.0`.

---

## Future

<!--
This section captures items intentionally deferred from the active phases above:
- Stories not yet planned in detail
- Phases beyond the current scope
- Project-level out-of-scope items
The `archive_stories` mode preserves this section verbatim when archiving stories.md.
-->

**Close follow-on cycles (deferred from the pre-production release):**

- **`[huggingface]` plugin end-to-end** — transformers + peft + evaluate-based plugin honouring the same `Plugin` Protocol. Architecture vocabulary extends with `Encoder` (HF model id), `LoRA` (peft), `Pooling`, `Head` per the optional pretrained-encoder path. Pretrained-weight cache management (`~/.cache/huggingface/` or `HF_HOME` override) lives in the plugin's docs, not in `project-essentials.md`.
- **`[keras]` plugin end-to-end** — TensorFlow + Keras 3 backend. Likely shares the metric implementations from `plugins/sklearn/metrics.py` for ECE / calibration_curve.
- **`[llm]` extra implementation** — `init --llm-assist` flag routed through `lmentry` for interpretive baseline-model recommendations. Namespace claimed in `pyproject.toml`; no implementation in the pre-production series. Lands as its own FR with its own acceptance criteria.
- **sklearn plugin end-to-end** — promote the stub from C.m to a working scikit-learn implementation (MLPClassifier, RandomForest, GBM baselines for CIFAR-10 — likely needs feature-flattening from the DataRefineryDataset adapter).
- **Continued training** — `Training.persist_optimizer_state: bool = false` recipe field gated by a `schema_version` bump; the `Checkpoint` model's forward-extensible keys (`optimizer_state`, `scheduler_state`, `rng_state`, `training_step`) are populated; new `materialize --resume-from <checkpoint>` workflow. The Q16 foundation in B.k is what makes this a pure additive change with no public-API rework.
- **Tight-coupled DataRefinery binding (FR-26)** — `schema_version` bump that mixes the bound DataRefinery instance's `recipe_hash` into ModelFoundry's cache identity, so upstream re-materialization auto-invalidates downstream. Requires a documented migration of existing cached ModelInstances.
- **Marimo + IPython substrate-neutral smokes** — the Jupyter smoke in E.k is the canonical substrate-neutral test; Marimo headless and IPython REPL smokes extend the contract.
- **Parallel Optuna trials** — `n_jobs > 1` with a deterministic trial-ordering protocol on top of the parallel harness. Requires the determinism contract to extend cleanly.
- **`modelfoundry.toml` per-project config** — currently no per-project config file (recipe + CLI flags + env vars cover execution context). If recurring patterns emerge, a project config lands as its own FR.
- **Cross-platform first-class Linux** — currently Linux is best-effort pre-production; post-production gates require first-class status.
- **Codecov / Coveralls coverage upload** — deferred from Phase G; coverage produced locally via `pyve test --cov`.
- **GitHub branch protection** — explicitly out of scope for the pre-production series per CR-1.
- **Production-release ceremony** — when ModelFoundry transitions from pre-production to production (the `1.0.0` event), every cache-invalidating change becomes ceremonious per `project-essentials.md`; `OR-8` / `OR-9` / `OR-10` stability guarantees activate; `plan_production_phase` replaces `plan_phase` for adding new work.

**Forward-declared dependency contracts:**

- `docs/specs/modelfoundry/vendor-dependency-spec.md` for downstream consumers (a future `modelmetrics`, `modelmachine`, replay harness) — authored at the pre-production release, mirroring DataRefinery's vendor-dependency-spec discipline. Captures the on-disk `ModelInstance` layout + the in-memory `ModelInstance` API + schema-version coordination policy.
