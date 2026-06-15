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

### Story B.m: v0.3.0 Recipe validator — `recipe.validator` [Done]

`features.md` FR-2, `tech-spec.md` § `recipe.validator`. Implements all 19 enumerated static logical checks; never short-circuits. Owns the Phase B v0.3.0 bump.

- [x] Create `src/modelfoundry/recipe/validator.py` with `ValidationCheck` + `ValidationReport` pydantic models and `validate(recipe, data_instance, plugin) -> ValidationReport`. (Signature extended with `*, variants_block: dict[str, Any] | None = None` so the variants check has access to the pre-overlay block — B.b's `apply_variant` clears `variants` before pydantic construction; check 16 emits a skip-message if the caller doesn't supply it. The CLI / library entry points should thread the raw variants dict from the loader.)
- [x] Implement checks 1..19 per `features.md` FR-2:
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
- [x] One test per check under `tests/unit/test_recipe_validator.py` with focused recipe fixtures. Validator never short-circuits — all failures are reported. (24 tests total: per-check failure + happy path + multi-failure non-short-circuit. Checks 9, 10, 15 are pydantic-Literal-enforced at construction time; tests document that the validator sanity-passes any successfully constructed recipe.)
- [x] Bump version to v0.3.0.
- [x] Update CHANGELOG.md (Phase B summary: recipe loader + variants + canonical bytes + cache identity + cache layout + atomic promote + manifest + plugin Protocol + DataRefinery binding + seeding + checkpoint + expectations + validator).
- [x] Verify: `pyve test tests/unit/test_recipe_validator.py` passes; `pyve testenv run mypy src tests` clean.

### Story B.n: v0.3.1 Recipe amendment — `Training.device` execution knob [Done]

`features.md` QR-5 / NG-13 follow-up. Adds a recipe-level device knob so users can force CPU execution on machines with GPU acceleration available (e.g. CPU-speed benchmarking, debugging non-deterministic ops, cross-device parity checks). Eval and inference inherit; the field drives every model-execution stage in the PyTorch plugin (Phase C). Cache-invalidating per `project-essentials.md` § Cache identity — acceptable pre-prod with a release-notes callout.

- [x] Add `device: Literal["auto", "cpu", "cuda", "mps"] = "auto"` to `TrainingSpec` in `src/modelfoundry/recipe/models.py`. Inline comment: "applies to Training + Evaluation + inference; resolved by the plugin's `health_check`-reported availability at materialize time."
- [x] Extend `recipe.validator.validate` with **check 20**: `Training.device` is either `"auto"` or matches one of the plugin's `health_check`-reported available accelerators. The synthetic `Plugin` in tests gets a stubbed `health_check` returning an object with an `accelerators` field; check 20 reads that list. Tolerant of plugins whose `health_check` doesn't expose accelerator info (skip with a message). (`_extract_accelerators` handles both dict-shaped and attribute-shaped report objects.)
- [x] Update the validator test fixture's good recipe and stub `_Plugin.health_check` to expose accelerators; add per-check tests for: device=`"auto"` passes; device=`"cuda"` on a CPU-only plugin fails; happy-path now sweeps checks 1..20. (Added 4 check-20 tests: auto-passes-without-plugin-info, explicit-unavailable-fails, explicit-available-passes, skip-when-plugin-doesnt-expose-accelerators.)
- [x] Update `tests/unit/test_canonical.py` to document the deliberate v0.3.1 invalidation: add a `test_device_field_perturbs_canonical_bytes` that loads two recipes (one default-device, one explicit `Training.device: cpu`) and asserts their hashes differ.
- [x] Bump version to v0.3.1.
- [x] Update CHANGELOG.md `[0.3.1]` section: cache-invalidation notice ("all existing v0.3.0 ModelInstances are stale; re-materialize") + new field summary.
- [x] Document the new knob in the user-facing specs:
  - [x] `docs/specs/features.md` — extend **QR-5** to name the `Training.device` field and reference FR-2 check 20; append the new **check 20** to the FR-2 enumeration so the static-check list is authoritative.
  - [x] `docs/specs/tech-spec.md` — update the `TrainingSpec` code block to include the `device` field with the same inline-comment rationale that lives in the source; add a **Device resolution** paragraph under Cross-Cutting Concerns describing the auto-detect order, the canonical-bytes participation, and the validator's plugin-tolerance behavior.
  - [x] `README.md` — add a short **Choosing an accelerator** subsection under Usage demonstrating the recipe field, the canonical-hash-distinction note, and the `variants:` overlay pattern for CPU-bench side-by-side.
- [x] Verify: `pyve test tests/unit/test_recipe_validator.py tests/unit/test_canonical.py` passes; `from modelfoundry.recipe.models import TrainingSpec; TrainingSpec.model_fields["device"]` exists; `mypy src tests` clean (invoked as `python -m mypy` due to a pyve v3 path-migration leftover in the installed `mypy` script's shebang — not caused by this story).

Out of scope (left for the Phase C stories where they naturally live):
- PyTorch plugin's device resolution (lands in C.b `health_check` and C.e `determinism` + propagation through C.h trainer / C.j evaluation / C.l predict).
- "Force CPU" environment variables for non-recipe escape hatches — recipe-level `device: cpu` is the supported path.

### Story B.o: Pyve 3.0 env reconfiguration — two micromamba envs (utility root + test) [Done]

**Re-scoped 2026-06-12** (Pyve v3.0.6 installed; the original "bare-OS `none` root + single micromamba testenv" design is **reversed** by developer decision). The repo runs **two micromamba environments** under Pyve's v3.0 `pyve.toml` (`pyve_schema = "3.0"`) `[env.<name>]` mechanism:

- **`root`** — a micromamba **"utility"** env: instantiate a ModelFoundry and run scripts ad hoc.
- **`testenv`** — a micromamba **test** env carrying the full runtime/dep stack + pytest/ruff/mypy to exercise the whole suite; `environment.yml` is its manifest; `default = true`.

Rationale: the pyve `none` (bare-OS, unmanaged) backend is reserved for languages with no managed-env concept (Rust/C++/Ruby); for a first-class language+backend combo like Python+micromamba there is no reason to give up the reproducibility/isolation a managed env provides — so the root is a micromamba utility env, **not** `none`. Doc/infra change — **no package version bump** (does not touch the shipped wheel's code or runtime deps); shares the post-B.n housekeeping release.

> State at re-scope: Pyve v3.0.6 materialized `pyve.toml` (schema 3.0) with `[env.root]` (micromamba, `purpose = "utility"`) + `[env.testenv]` (micromamba, `default = true`, `frameworks = [pytest, ruff, mypy]`). Both micromamba envs are materialized on disk and working (`pyve run modelfoundry --version`, `pyve env run python -m pytest` both succeed). Gaps to close: `[env.testenv]` lacks a `manifest` key so `pyve test` errors; `pyve check` reports a stale pending backend flip on `root` (leftover from the earlier `none`-root prep). `pyve testenv …` is now a deprecated alias for `pyve env …` (removed in v4.0).

- [x] Update [`env-dependencies.md`](env-dependencies.md) §3–§5 (the authoritative env spec) from the bare-OS-`none`-root topology to this two-micromamba-env design — record the `none`-backend-reservation rationale and the future-second-test-env note. (Rewrote the orienting paragraph, §2 root term, §3 backend-usage + config note, §4.0 YAML (`root.backend none → micromamba`) + §4.1 table, §5.0 root section, §5.1 testenv (`pyve.toml [env.testenv]` manifest), §6/§7/§8, metadata `3.0.4 → 3.0.6` / `2026-06-12`, and a §9 changelog row. §3's Pyve-owned catalog rows left to the vendored-template refresh.)
- [x] Declare `manifest = "environment.yml"` under `pyve.toml [env.testenv]` so the conda-backed test env resolves (`pyve test` requires it under v3.0.6); keep `[env.root]` as the micromamba `purpose = "utility"` env. (Added the key; `pyve test` now runs the suite green — **364 passed** — un-parking the canonical runner.)
- [x] Remove (or reconcile) the now-stale `[tool.pyve.testenvs.testenv]` table in `pyproject.toml` — it is the v2.8 location, superseded by `pyve.toml [env.<name>]` under schema 3.0. (Removed.)
- [x] Reconcile the `pyve check` discrepancy (the recorded env-spec showed a pending `root` backend flip). (Updating `env-dependencies.md` §4.0 `root.backend → micromamba` **cleared the destructive flip** — the recorded "env spec" `pyve check` compares against is §4.0. With developer sign-off, ran `pyve env sync --dry-run` then `pyve env sync --yes`: a clean, **non-destructive** `pyve.toml` metadata reconcile (added `[env.root] languages/frameworks`), no env rebuild; `pyve check [env-spec]` is now empty. Evaluation note: sync had no functional value here, but demonstrates the env-spec→`pyve.toml` scaffolding path.)
- [x] Update `.gitignore` / any path assumptions for the materialized env paths (`.pyve/envs/<name>/conda/`); reconcile `.envrc` if it still hard-codes a stale env name / `CONDA_PREFIX`. (**No change needed** — `.gitignore` already ignores `.pyve/` wholesale; the pyve-managed `.envrc` activates the root micromamba env, which is correct under this topology.)
- [x] Update `environment.yml`'s header comment to state it is the **testenv** manifest. (Reworded to "the shared conda manifest for both micromamba envs" — root + testenv — with per-env provisioning commands.)
- [x] Switch command references `pyve testenv …` → `pyve env …` where this story touches them (the legacy alias is removed in v4.0). (Done across `env-dependencies.md`; the deprecation is also noted there.)
- [ ] **Future (out of scope here):** add a *second* isolated test env only if frameworks collide (e.g. Metal Keras vs Metal PyTorch on macOS). (Forward note — intentionally not actioned.)
- [x] Verify: `pyve test` runs the suite green against the micromamba testenv; `pyve run modelfoundry --version` prints the version from the utility root; `pyve env run ruff check src tests` + `pyve env run mypy src tests` clean; no stale `pyve check` env-spec discrepancy remains. (All green: `pyve test` **364 passed**; `pyve run modelfoundry --version` → `modelfoundry 0.3.1`; `pyve env run testenv -- ruff check` clean + `mypy` clean (88 files); `pyve check` 0 errors, `[env-spec]` empty. Lone remaining `pyve check` warning — config `3.0.5 → 3.0.6` — is a separate `pyve update` housekeeping item, not env-topology.)

### Story B.p: Reconcile stale env-layout docs with the pyve 3.0 topology [Done]

Fix the docs that `env-dependencies.md` flags as describing the **pre-3.0** `.venv/` + `.pyve/testenvs/` two-environment layout, so they match the **two-micromamba-env** topology B.o establishes — a micromamba **utility** root + a micromamba **test** env, declared in `pyve.toml` (schema 3.0). Doc-only — **no version bump**.

- [x] `docs/specs/tech-spec.md` § Runtime & Tooling: rewrite the **Environment manager** row — replace "Two-environment model: runtime in `.venv/`, dev tools in `.pyve/testenv/venv/`" with the pyve-3.0 topology (two micromamba envs in `pyve.toml`: a `purpose = "utility"` **root** for ad-hoc runs/scripts, and a `default = true` **testenv** holding the editable package + PyTorch plugin + dev tooling, with `environment.yml` as its manifest); point to `env-dependencies.md` as the authoritative env spec. (Row rewritten with both env paths; the Canonical-command block's `pyve testenv run …` lines also switched to `pyve env run testenv -- …`.)
- [x] `docs/specs/tech-spec.md` § Two-environment install: rewrite the command sequence to the pyve-3.0 `pyve env …` flow B.o establishes (both envs declared in `pyve.toml`; the editable package + `[pytorch]` extra + dev tooling provisioned into the micromamba `testenv`); drop the main-`.venv/` editable install and the deprecated `pyve testenv …` form. (Rewritten to `pyve env init root`/`testenv` + `pyve run` / `pyve env run testenv -- pip install …`, with the `pyve env install`-skips-conda note.)
- [x] `docs/specs/tech-spec.md` § Package Structure + § CI/CD: update the `environment.yml` annotation (now the testenv manifest) and confirm the CI-parity prose describes the micromamba testenv (CPU). (Annotation reworded to "shared conda manifest for both micromamba envs"; added a `pyve.toml` tree entry. § CI/CD already describes `pyve test` on macOS/Linux CPU — no `.venv` claims there, confirmed no change needed.)
- [x] Add a cross-reference to `env-dependencies.md` from `tech-spec.md` where the env model is introduced, so the two stay in sync. (Both the Environment-manager row and § Two-environment install now link `env-dependencies.md` — `grep -c` → 2.)
- [x] Flag — **do not hand-edit** — the bundled `docs/project-guide/go.md` § Pyve Essentials (lines ~170–227): it describes pyve **v2.8**'s `.pyve/testenvs/<name>/` layout and the `pyve testenv …` verb, both stale vs the running pyve **3.0.6** (`.pyve/envs/<name>/`, `pyve env …`). This is project-guide **install output** (pyve-owned, refreshed by `project-guide update`); per `go.md` § "Files under `docs/project-guide/` are install output," the fix is upstream — file an issue/PR against the pyve / project-guide repo (or pick it up via `project-guide update`), or `project-guide override` it only if a local divergence is intended. Record the chosen path in the story notes; no silent edit. (**Chosen path: upstream / `project-guide update`** — left unedited. The staleness is confirmed (the go.md Pyve Essentials still references `.pyve/testenvs/testenv/venv/`, `pyve testenv init`, and the v2.8 layout). Recommended at this gate that the developer run `project-guide update` to pull the refreshed go.md once pyve/project-guide ship the 3.0 layout text, or file an upstream issue; no local `project-guide override` applied since the divergence is upstream-fixable, not project-specific.)
- [x] Verify: `grep -rn -E '\.venv/|\.pyve/testenv' docs/specs/tech-spec.md` returns no remaining layout claims; `tech-spec.md` references `env-dependencies.md`; the upstream go.md staleness is captured (issue link or override note). (Verified: stale-claim grep → none; `env-dependencies.md` referenced 2×; go.md staleness captured above with the chosen upstream path.)

### Story B.q: DataRefinery v0.19.0 adoption — schema v2 + `recipe.json` binding [Done]

`features.md` FR-6 / FR-2 follow-up; cross-repo contract per [`datarefinery/vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md). Bring ModelFoundry's DataRefinery binding up to the ratified v0.19.0 contract so the Phase C CIFAR-10 deliverable (C.r) can bind a schema-v2 instance. Built against `ml-datarefinery==0.17.0` originally (A.c/B.i); v0.19.0 brings schema v2, `recipe.json` (not `recipe.yaml`), and `class_balance` (0.18.0+). No Phase C dependency — lands in Phase B. Dependency + doc/infra change — **no package version bump**; shares the post-B.n housekeeping release.

- [x] Bump the `ml-datarefinery` dependency pin to `>= 0.19.0` in `pyproject.toml` (and `requirements-dev.txt` if pinned there); reinstall into the testenv. (`requirements-dev.txt` does not pin `ml-datarefinery` — it's a runtime dep, owned by `pyproject.toml`; no change needed there. Reinstalled into the conda testenv → `ml-datarefinery 0.19.0`.)
- [x] Update ModelFoundry's tracked DataRefinery `SUPPORTED_SCHEMA_VERSIONS` to include **2** wherever it is asserted (B.m validator check 19 / B.n check 20 coordination and any binding-side gate), tracking `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS` / `LATEST_SCHEMA_VERSION`. (**No code change required** — `data_binding.DR_SUPPORTED_SCHEMA_VERSIONS` is derived dynamically from `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS`, and validator check 19 / the binding gate read `max(DR_SUPPORTED_SCHEMA_VERSIONS)`; both now resolve `{1, 2}` / max `2` automatically. Check 20 is `Training.device`, unrelated to DR schema. Nothing hard-codes DR's max.)
- [x] Re-validate `pipeline.data_binding` (B.i): read the persisted recipe from **`recipe.json`** (the canonical v2 shape), not `recipe.yaml` (no longer persisted per the vendor-spec); confirm the manifest fields ModelFoundry binds against still resolve under the v0.19.0 manifest (incl. the new `class_balance` field — read-and-ignore for now per Subphase C-1 §C10). (`Instance.load` reads `recipe.json` + `manifest.json`; ModelFoundry binds against `manifest.record_counts` and read-and-ignores `class_balance`. Verified a v1 source recipe migrates to byte-identical v2 on load, so binding sees `schema_version: 2`.)
- [x] Update the synthesized DataRefinery fixture(s) to the v2 / `recipe.json` on-disk shape so the binding + validator contract tests exercise the current contract. ([tests/unit/test_data_binding.py](tests/unit/test_data_binding.py): fixture recipe now declares `schema_version: 2`; manifest carries `datarefinery_version: "0.19.0"` + a populated `class_balance` so every binding test exercises a v0.19.0-shaped manifest; `test_cross_validation_helpers` now asserts `instance_schema_version() == 2`.)
- [x] Verify: `pyve test tests/unit/test_data_binding.py tests/unit/test_recipe_validator.py` passes against the v0.19.0 shapes; `pyve testenv run mypy src tests` clean. (Run via the conda testenv interpreter — `pyve test`/`pyve env run` are parked on the Pyve v3.0.6 conda-`env run` fix per B.o. Target files: **40 passed**; full suite **225 passed**; `mypy src tests` clean (46 files); `ruff check` clean. Incidental fix: [src/modelfoundry/pipeline/seeding.py](src/modelfoundry/pipeline/seeding.py) — the optional `import torch` `type: ignore` gained `unused-ignore` so it's clean whether or not the type-check env has the `[pytorch]` extra installed; the now-torch-bearing conda testenv surfaced the previously-needed ignore as unused.)

---

## Phase C: PyTorch Plugin + Materialize Orchestrator

Implement the PyTorch plugin end-to-end (architecture vocabulary, losses, optimizers, schedules, deterministic training, DataRefinery dataset adapter, lazy augmentations, training loop, Optuna optimization, evaluation, visualizations, persistence), ship a working sklearn `MLPClassifier` baseline, build the materialize orchestrator that sequences every stage atomically, and expose the `ModelFoundry`/`ModelInstance` library API. By end of Phase C, a Python program can call `ModelFoundry.from_recipe(...).materialize()` against a bound DataRefinery instance and get back a notebook-shaped `ModelInstance`.

## Subphase C-1: Reprioritize to Client Requirements

Phase C is reprioritized to deliver one client vertical first: declaratively build, tune, train, and **summarize** a **ResNet-20** over a materialized **CIFAR-10** DataRefinery instance, **CPU-only** within a per-step time budget, **readable from a notebook**. The client and requirements are sanitized to keep this public repo generic (CIFAR-10 is a public dataset). The PyTorch vertical (C.a–C.p) is the spine; this subphase weaves in the few additions the requirements need:

- **C.c** adds the `resnet20` baseline (the anchor architecture).
- **C.f** applies DataRefinery's fitted per-channel normalization at load and derives the class set from all labeled splits (interim until DR `manifest.label_classes`).
- **C.i** makes `batch_size` and `early_stopping.patience` tunable.
- **C.m** is promoted from a stub to a **working sklearn `MLPClassifier`** baseline.
- **C.q** (new) generates the torchinfo **model summary** as a materialize-time artifact + accessor + `inspect` view.
- **C.r** (new) is the tested deliverable: a real-shape CIFAR-10 / ResNet-20 recipe calibrated to the CPU budget, materialized end-to-end, owning the Phase C release bump.

Upstream dependency: the CIFAR-10 DataRefinery instance (DR-1) and the v0.19.0 contract (Phase B story **B.q**). See [`phase-c-subphase-1-reprioritize-plan.md`](phase-c-subphase-1-reprioritize-plan.md) for the full plan, conflicts, scope decisions, and the DataRefinery ↔ ModelFoundry contract status.

### Story C.a: Architectural spike — deterministic PyTorch training loop [Done]

Throwaway script in `scripts/`. Validate the most uncertain architectural assumption before the production PyTorch plugin lands: can `torch.use_deterministic_algorithms(True)` + `CUBLAS_WORKSPACE_CONFIG=:4096:8` + the `worker_init_fn_factory` from B.j produce byte-identical model state across two runs of a minimal CNN training loop on a synthetic dataset (CPU + `num_workers=1, 2, 4`)? Deliverable is the documented outcome.

- [x] Create `scripts/spike_pytorch_determinism.py`: minimal `nn.Module` (2-layer CNN), synthetic 32-record image dataset, 2-epoch training loop. Run three times across `num_workers ∈ {1, 2, 4}` and compare `model.state_dict()` byte-by-byte. (State-dict hashed as SHA-256 over each tensor's raw bytes in sorted-key order; all three worker counts produce an identical hash, and a repeat run reproduces it.)
- [x] Run the same script with `torch.use_deterministic_algorithms(False)` to confirm non-determinism without the guard. (Finding: on **CPU** the loop is already byte-deterministic *without* the guard — same hash both ways. The guard's value is the CUDA path + as a hard-error tripwire; documented in the outcome doc. CPU-only non-determinism couldn't be induced with the C-1 op vocabulary.)
- [x] Document outcome in `docs/spikes/C.a-pytorch-determinism.md`: which ops (if any) hard-error under deterministic mode; the env-var setup pattern; the `worker_init_fn` integration pattern; any platform-specific surprises on macOS-MPS (or CPU-only if MPS is sidestepped). (No ops hard-error on CPU; MPS sidestepped per the Subphase C-1 CPU budget.)
- [x] Note any integration risks for C.e (determinism module) and C.h (trainer). (**Key finding:** B.j's `worker_init_fn_factory` returns an **unpicklable closure** that crashes `DataLoader(num_workers>0)` under macOS `spawn`; the spike demonstrates the spawn-safe fix — a module-level fn bound via `functools.partial` — that C.f/C.h must adopt, with a recommended rework of B.j. Full detail + the C.e/C.f/C.h pattern in the outcome doc.)
- [x] Verify: spike runs; byte-identity holds under deterministic mode + worker_init_fn; outcome doc captures the production pattern. (`RESULT: PASS`; spike + `ruff check` clean. Run via the conda testenv interpreter — `pyve run`/`pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.a.1: Repair B.j `worker_init_fn` picklability — DataLoader `spawn`-safety [Done]

Bugfix for the latent defect the **C.a** determinism spike surfaced: `pipeline.seeding.worker_init_fn_factory` returned a **nested closure**, which the macOS/Windows `spawn` start method cannot pickle — so `DataLoader(num_workers>0)` crashes with `AttributeError: Can't get local object 'worker_init_fn_factory.<locals>._worker_init_fn'` on the project's primary CI platform (macOS, per `env-dependencies.md` §5.1). Left unrepaired this would block C.f (data adapter) and C.h (trainer) the moment they use workers. Inserted here, immediately after the spike that found it, so the fix lands before any consumer depends on it. No package version bump — rides the phase-bundled Phase C release (C.r owns the bump).

- [x] Refactor [src/modelfoundry/pipeline/seeding.py](../../src/modelfoundry/pipeline/seeding.py): extract the worker body to a **module-level** `_seed_worker(master_seed, worker_id)` and return `functools.partial(_seed_worker, master_seed)` from `worker_init_fn_factory`. Public API (`worker_init_fn_factory(master_seed) -> Callable[[int], None]`) and seeding behavior are unchanged; the result is now picklable and `spawn`-safe. Preserves the four determinism invariants (`project-essentials.md` § Determinism contract is foundational).
- [x] Add a regression guard [tests/unit/test_seeding.py](../../tests/unit/test_seeding.py)::`test_worker_init_fn_is_picklable_for_spawn` — `pickle.dumps`/`loads` round-trip succeeds and the restored callable seeds identically to the original.
- [x] Update the C.a spike [scripts/spike_pytorch_determinism.py](../../scripts/spike_pytorch_determinism.py) to consume the now-fixed `worker_init_fn_factory` directly (dropping its local workaround) and turn the `[0]` picklability probe into a positive regression confirmation; re-ran end-to-end under `spawn`.
- [x] Add a closing "repaired in C.a.1" note to [docs/spikes/C.a-pytorch-determinism.md](../spikes/C.a-pytorch-determinism.md) and a `Fixed` entry to `CHANGELOG.md` `[Unreleased]`.
- [x] Verify: spike `RESULT: PASS` with `picklable: True`; `test_seeding.py` 12 passed; full suite **226 passed**; `mypy src tests` clean (46 files); `ruff check` clean. (Run via the conda testenv interpreter — `pyve run`/`pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.b: PyTorch plugin scaffold + health_check + registration [Done]

`tech-spec.md` § `plugins.pytorch`. Smallest possible plugin: registers a `name = "pytorch"`, empty `operations`, working `health_check` (reports torch/torchvision/torchmetrics availability + accelerator detection). Used by the registration test in B.h's discovery harness.

- [x] Create `src/modelfoundry/plugins/pytorch/__init__.py` and `src/modelfoundry/plugins/pytorch/plugin.py` implementing the `Plugin` Protocol skeleton (all methods raise `NotImplementedError` except `health_check`). (`plugin: Plugin = PyTorchPlugin()` is annotated as `Plugin` so mypy statically checks Protocol conformance. **Import-safe without `[pytorch]`:** the entry point ships in ModelFoundry's own table and is loaded by `discover_plugins()` on *every* install, so torch is imported lazily inside `health_check`/`_detect_accelerators`, never at module top level — a sklearn-only install can still discover the plugin.)
- [x] Wire the plugin entry point into `pyproject.toml` under `[project.entry-points."modelfoundry.plugins"]`. (`pytorch = "modelfoundry.plugins.pytorch.plugin:plugin"`; reinstalled editable into the conda testenv so `importlib.metadata` sees it.)
- [x] `health_check` returns a `CheckReport` listing torch / torchvision / torchmetrics versions, accelerator (MPS / CUDA / CPU-only), and whether deterministic-algorithm mode is enable-able on this backend. (Concrete `PyTorchHealthReport` pydantic model — `plugin`, `available`, `{torch,torchvision,torchmetrics}_version`, `accelerators`, `deterministic_algorithms_available`. `accelerators` uses the `Training.device` vocabulary (`cpu`/`cuda`/`mps`) so B.n's validator check 20 reads it directly. The shared `CheckReport` Protocol alias stays `Any` — its canonical refinement remains D.c's job.)
- [x] Integration test: `discover_plugins()` finds the pytorch plugin; `health_check()` returns a non-error report on the test machine. ([tests/integration/test_pytorch_plugin_registration.py](tests/integration/test_pytorch_plugin_registration.py): discovery + `isinstance(_, Plugin)` + `operations == {}`; health report asserts `available`/`cpu`-present/`deterministic` (guarded by `pytest.importorskip("torch")`); stub methods raise `NotImplementedError` with the owning-story pointer. On this Apple-Silicon machine the report shows torch 2.12.0 / accelerators `('cpu','mps')`.)
- [x] Verify: `pyve test tests/integration/test_pytorch_plugin_registration.py` passes. (Integration: 3 passed; full suite **229 passed**; `mypy src tests` clean (49 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.c: PyTorch architecture vocabulary — `plugins.pytorch.architecture` [Done]

`features.md` FR-7 / FR-ARCH-1, `tech-spec.md` § `plugins.pytorch` > `architecture.py`. CIFAR-10 baseline CNN vocabulary.

- [x] Create `src/modelfoundry/plugins/pytorch/architecture.py` registering primitives (`Conv2d`, `BatchNorm2d`, `ReLU`, `MaxPool2d`, `AvgPool2d`, `AdaptiveAvgPool2d`, `Linear`, `Dropout`, `Flatten`), composites (`MLP`, `ConvBlock`, `ResidualBlock`), and baseline architectures (`simple_cnn`, `resnet8`, `resnet20`). Each op pairs an `nn.Module` subclass with a pydantic `OperationSpec.param_model`. (19 ops total incl. the deferred HF path. **Import-safe without `[pytorch]`:** the param models + `ARCHITECTURE_OPERATIONS` registry are pure pydantic at module top; torch is imported lazily inside `build_model`/`_kit`, preserving C.b's sklearn-only-discovery property. The plugin wires `operations = dict(ARCHITECTURE_OPERATIONS)`.)
- [x] **`resnet20` baseline (Subphase C-1 / G2):** the canonical CIFAR residual network — a 3×3 conv stem → three stages of three `ResidualBlock`s at 16/32/64 channels → `AdaptiveAvgPool2d` global average pool → single `Linear` head. The block supports **option-B projection shortcuts** (1×1 conv on the two downsampling blocks), **bias-free convs** (a `BatchNorm2d` follows each), and **strided-conv downsampling** (stride-2 first conv of stages 2 and 3 — no max-pool). Extend `ResidualBlock` params as needed for the projection-shortcut + stride path. (`ResidualBlock(in_channels, out_channels, stride)`; option-B shortcut auto-engages when `stride != 1` or channels change. Measured **exactly 272,474 params** at `num_classes=10` — 21 conv / 21 batchnorm / 1 linear.)
- [x] Recursive builder `build_model(arch_spec) -> nn.Module` reads the canonical `Architecture` block from the recipe and composes ops. Validates `num_classes` matches the bound DataRefinery instance's label count. (`build_model` supports two block shapes — named baseline `{type, num_classes, in_channels}` and explicit `{num_classes, layers:[{op,...}]}` composed into an `nn.Sequential`. It validates `num_classes` is a positive int and each op's params; **the `num_classes` ↔ DR-label-count cross-check is FR-2 check 18** — the validator owns it since `build_model` doesn't receive the bound instance.)
- [x] Optional pretrained-encoder + LoRA path (`Encoder`, `LoRA`, `Pooling`, `Head`) declared in `requires_extras=("huggingface",)` so recipe-time validation works without `[huggingface]` installed; `build_model` raises a clear `ImportError` at materialize time if extras are missing. (Param models + OperationSpecs registered; building one without `transformers` raises `ImportError` with the `pip install 'ml-modelfoundry[huggingface]'` pointer; with the extra present it raises `NotImplementedError` (build path deferred).)
- [x] Update the user-facing specs: `features.md` FR-ARCH-1 baseline-architectures list and `tech-spec.md` `[pytorch]` vocabulary line to include `resnet20`.
- [x] Unit tests: every op resolves; `simple_cnn`, `resnet8`, and `resnet20` instantiate cleanly; **a test pins `resnet20`'s canonical layer inventory and total parameter count (≈272,474)** so the architecture can't silently drift; bad params → pydantic `ValidationError` → mapped to `PluginError`. ([tests/unit/test_pytorch_architecture.py](tests/unit/test_pytorch_architecture.py): 18 tests — registry, baseline forward shapes, the `272_474`/inventory pin, explicit-layer + composite composition, 8 error cases, HF-without-extras `ImportError`. Also updated the C.b registration test, which had asserted `operations == {}`.)
- [x] Note: adding `resnet20` vocabulary perturbs canonical bytes only for recipes that select it (a new op); acceptable pre-prod with a CHANGELOG callout per `project-essentials.md` § Cache identity. (Callout added to `CHANGELOG.md` `[Unreleased]`.)
- [x] Verify: `pyve test tests/unit/test_pytorch_architecture.py` passes. (Architecture: 18 passed; full suite **247 passed**; `mypy src tests` clean (51 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.d: PyTorch losses, optimizers, schedules [Done]

`features.md` FR-LOSS-1 / FR-OPT-1 / FR-OPT-2, `tech-spec.md` § `plugins.pytorch` > `losses.py` / `optimizers.py` / `schedules.py`.

- [x] `losses.py`: `cross_entropy`, `cross_entropy_class_weighted` (with `weight_source: train | train_inverse_frequency | effective_number`, weights fit on train at training start, persisted to `training/class_weights.json`), `bce_with_logits` (recipe-time rejected when `num_classes > 2`). (`derive_class_weights(weight_source, class_counts)` returns mean-normalized weights — `train` = sklearn-balanced, `train_inverse_frequency` = `1/n_c`, `effective_number` = Cui et al. class-balanced; the trainer (C.h) fits + persists `training/class_weights.json`. `build_loss` enforces the binary-only `bce_with_logits` constraint as a **materialize-time `PluginError`** when `num_classes > 2` — the backstop to FR-2 check 17's recipe-time rejection; not modified the validator here.)
- [x] `optimizers.py`: `adamw`, `sgd`, `adam` with their typed params. (`learning_rate` → torch `lr`; `build_optimizer(op, params, model_parameters)`.)
- [x] `schedules.py`: `reduce_on_plateau`, `cosine`, `linear_warmup` with their typed params. (`reduce_on_plateau`'s watched metric is `ScheduleSpec.monitor` (fed to `scheduler.step(value)` by the trainer); op params carry only LR knobs. `linear_warmup` is a `LambdaLR` warming 0→1 over `warmup_steps` then linearly decaying toward `min_lr` by `total_steps`.)
- [x] Each op registered as an `OperationSpec` in the plugin's `operations` dict. (`LOSS_OPERATIONS` / `OPTIMIZER_OPERATIONS` / `SCHEDULE_OPERATIONS` merged into `PyTorchPlugin.operations` alongside `ARCHITECTURE_OPERATIONS`; all three modules are import-safe without `[pytorch]` — lazy torch in the builders.)
- [x] Unit tests: each op constructs the correct `torch.nn` / `torch.optim` / `torch.optim.lr_scheduler` object with the expected hyperparameters; class-weighted loss correctly derives weights from a synthetic train-split label distribution. ([tests/unit/test_pytorch_ops.py](tests/unit/test_pytorch_ops.py): 18 tests — registries, each loss/optimizer/schedule build + hyperparams, class-weight derivation (balanced→uniform, imbalanced→minority-upweighted across all three sources), bce multiclass guard, unknown-op errors.)
- [x] Verify: `pyve test tests/unit/test_pytorch_ops.py` passes. (18 passed; full suite **265 passed**; `mypy src tests` clean (55 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.e: PyTorch determinism module — `plugins.pytorch.determinism` [Done]

`features.md` QR-3, `tech-spec.md` § `plugins.pytorch` > `determinism.py`. C.a's spike outcome locks the pattern here.

- [x] Create `src/modelfoundry/plugins/pytorch/determinism.py` with `enable_deterministic_algorithms() -> None` (sets `os.environ["CUBLAS_WORKSPACE_CONFIG"]` if unset; calls `torch.use_deterministic_algorithms(True)`; sets `torch.manual_seed` / `torch.cuda.manual_seed_all` / MPS seed as applicable). (Signature `enable_deterministic_algorithms(seed: int | None = None)`; idempotent; seeds CUDA/MPS only when available. Import-safe without `[pytorch]` — lazy torch.)
- [x] `documented_hard_error_ops: tuple[str, ...]` listing ops known to hard-error under deterministic mode (sourced from C.a's spike outcome). (Empty `()` — the C.a spike found no Subphase C-1 CPU op trips the guard; the constant's docstring records the canonical GPU candidates to populate when one does.)
- [x] Integration into the plugin's `health_check`: report whether deterministic mode can be enabled on the installed backend; report which documented ops would hard-error. (`PyTorchHealthReport` gains `documented_hard_error_ops`; `deterministic_algorithms_available` now sourced from `determinism.deterministic_mode_supported()`.)
- [x] Unit tests: `enable_deterministic_algorithms()` is idempotent; environment variable is set; the hard-error documentation list matches the spike outcome. ([tests/unit/test_pytorch_determinism.py](tests/unit/test_pytorch_determinism.py): 6 tests — env-var set, mode enabled, idempotent, does-not-override-existing-CUBLAS, reproducible seeding, empty hard-error list — with a fixture that restores global torch deterministic state so it can't leak into other tests. Also extended the C.b health-check assertion.)
- [x] Verify: `pyve test tests/unit/test_pytorch_determinism.py` passes. (6 passed; full suite **271 passed**; `mypy src tests` clean (57 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.f: PyTorch `DataRefineryDataset` adapter — `plugins.pytorch.data` [Done]

`tech-spec.md` § `plugins.pytorch` > `data.py`. A.c's spike outcome locks the binding pattern.

- [x] Create `src/modelfoundry/plugins/pytorch/data.py` with `DataRefineryDataset(torch.utils.data.Dataset)`: constructor takes the bound `DataRefineryInstance` + split name + recipe `Augmentations` policy; `__len__` reads `manifest.record_counts[split]`; `__getitem__` reads the JSONL line, resolves `path` or `image_path` per the vendor-dep-spec, decodes via Pillow, applies lazy augmentations. (Constructor takes `augmentations: Callable | None` — the C.g lazy-augmentation callable applied to the normalized CHW tensor; `image_path` sidecar wins over `path`. This module imports `torch` at top — it's loaded by the trainer at materialize time, not during plugin discovery, so the import-safe rule doesn't apply. **Also extended the B.i `DataRefineryInstance` wrapper** with a `fitted_statistics` field, additively, populated by `resolve_data_instance`.)
- [x] **Apply DataRefinery normalization (Subphase C-1 / C8):** read the fitted per-channel `mean`/`std` via `Instance.fitted_statistics.get_vector(<normalize_op_id>, ...)`, line up the **RGB** channel order, and apply `(x - mean) / std` producing float32 tensors — for **every** split (train/val/test/inference). Replicate DataRefinery's **exact zero-variance guard** (`std == 0 → 1.0`, equality not tolerance). Resolve `<normalize_op_id>` (and any chained `mean_subtract`) from `recipe.json` in `Transformations` order. Per `datarefinery/vendor-dependency-spec.md` § "Fitted statistics ModelFoundry binds against." (Steps precomputed in `__init__` from `recipe.Transformations` order; mean/std read as `pyarrow` `value`-column vectors → `(3,1,1)` tensors; zero-variance guard via `torch.where(std == 0.0, ones, std)`.)
- [x] **Class-set derivation (interim, Subphase C-1):** build the label→index map by scanning **all labeled splits + sorting ascending** (matches the future DR `manifest.label_classes` producer computation); do not scan train-only. Adopt `manifest.label_classes` directly once DR v0.20.0 is taken up.
- [x] **Refuse lazy-mode geometry transforms (guard):** if the bound recipe declares a pixel-altering Transformation (e.g. `resize`) without aggressive sidecars / a sink, raise `DataBindingError` rather than silently decode pre-transform source pixels (vendor-spec § "Consumer-applied transformations" J.g interim guidance). The CIFAR-10 flow declares none — this is a guard, not a feature. (Any `Transformations` op outside `{normalize, mean_subtract}` triggers the guard unless the records carry `image_path` sidecars or `manifest.sinks` is non-empty.)
- [x] Honour per-record-seed stamps (`<AugmentationOp.name>_seed`) from DataRefinery's JSONL for aggressive variants (read directly); lazy augmentations realize via the C.g augmenters seeded from `pipeline.seeding`. (Aggressive variant pixels resolve via `image_path`; the per-record-seed-driven lazy realization is wired through the `augmentations` callable in C.g — `data.py` passes the decoded tensor to it.)
- [x] `DataLoader` factory helper `build_dataloader(dataset, training_spec, master_seed) -> DataLoader` (uses `worker_init_fn_factory(master_seed)` from B.j; `generator` seeded; `pin_memory` toggled per accelerator availability). (Shuffle order owned by a seeded `generator`; `worker_init_fn` is the spawn-safe C.a.1 partial; `pin_memory` engages only for CUDA.)
- [x] Unit tests against the synthesized DataRefinery fixture: dataset length matches manifest; record decoding produces a **normalized float32** tensor of the expected shape with the **RGB-ordered** stats applied and the zero-variance guard exercised; the all-splits label scan yields the expected sorted class order; a `resize`-bearing fixture is refused; iteration with `num_workers=1` and `num_workers=2` produces identical output (per `worker_init_fn`). ([tests/unit/test_pytorch_data_adapter.py](tests/unit/test_pytorch_data_adapter.py): 6 tests with a hand-built fitted-stats parquet + source-PNG fixture bound via a real `datarefinery.Instance.load`. The `num_workers=2` case spawns workers — exercising the C.a.1 picklability fix end-to-end on macOS.)
- [x] Verify: `pyve test tests/unit/test_pytorch_data_adapter.py` passes. (6 passed; full suite **277 passed**; `mypy src tests` clean (59 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.g: PyTorch lazy augmentations — `plugins.pytorch.augmentations` [Done]

`tech-spec.md` § `plugins.pytorch` > `augmentations.py`. Q4 from plan_tech_spec — torchvision-v2 realizers, semantic-equivalence (not byte-equivalence) with DataRefinery's Pillow aggressive realizers.

- [x] Create `src/modelfoundry/plugins/pytorch/augmentations.py` with realizers for `random_crop`, `horizontal_flip`, `color_jitter`, `random_erasing` over `torchvision.transforms.v2`. Each realizer takes the op's param model + a per-record/per-variant seed (via `derive_seed`) and produces a transform. (Param models mirror the vendor-dep-spec § Per-op param schemas; `build_realizer(op, params, seed)` validates the params (→ `PluginError`) and returns a transform whose randomness is drawn from a **local `torch.Generator`** seeded from `seed` — it never perturbs the global RNG, preserving the determinism invariants. Pixel ops go through `torchvision.transforms.v2.functional`. **Import-safe without `[pytorch]`:** param models + `AUGMENTATION_PARAMS` are pure pydantic; torch/torchvision import lazily inside `build_realizer`.)
- [x] Composer helper `compose_augmentations(augmentations: list[AugmentationOp], master_seed: int) -> Callable` returning a callable suitable for `DataRefineryDataset.__getitem__`. (`AugmentationOp` is a small `extra="ignore"` pydantic view of a DataRefinery lazy op — `name`/`op`/`params`/`seed`; extra DR fields like `splits`/`materialization`/`expansion` pass through harmlessly. Each op's seed = `derive_seed(master_seed, "augmentation:<name>", <op.seed bytes>)`, the documented seeding scope. Returns `None` for an empty policy — the no-aug path `data.py` already expects. Per-record variety, independent of `num_workers`, is the trainer's job, C.h — it re-salts this same scope with the record id.)
- [x] Unit tests: each realizer with a fixed seed produces deterministic output; semantic-equivalence with DataRefinery's Pillow realizers verified in Phase E (Hypothesis property tests). ([tests/unit/test_pytorch_augmentations.py](../../tests/unit/test_pytorch_augmentations.py): 21 tests — registry, per-op fixed-seed determinism, cross-seed divergence, flip-p1/p0 semantics, crop output shape, erasing-p0 identity, unknown-op / invalid-params / oversized-crop `PluginError`s, composer order + empty-policy-`None` + master-seed and per-op-seed sensitivity + DR-field tolerance.)
- [x] Verify: `pyve test tests/unit/test_pytorch_augmentations.py` passes (basic determinism; equivalence to DataRefinery lives in E.g). (21 passed; full suite **298 passed**; `mypy src tests` clean (61 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.h: PyTorch trainer — `plugins.pytorch.trainer` [Done]

`features.md` FR-10, `tech-spec.md` § `plugins.pytorch` > `trainer.py`.

- [x] Create `src/modelfoundry/plugins/pytorch/trainer.py` with `run_training(training_spec, model, recipe, data_instance, seed, temp_dir) -> TrainingResult`. Implements the training loop: per-epoch iteration, backprop + optimizer step, validation pass (for early-stopping monitor), schedule drive, history append to `training/history.parquet`, checkpoint write per `checkpoint_cadence` using the `Checkpoint` model from B.k, early-stopping evaluation, best-monitor-value promotion to `model/weights/`. (`TrainingResult` is a frozen dataclass carrying `epochs_run` / `best_epoch` / `best_metric_value` / `monitor` / `mode` / `history` / artifact paths — the orchestrator C.o records it in the manifest. Periodic checkpoints land as `model/checkpoints/checkpoint-epoch-NNNN.pt`; the best monitored value also writes `checkpoint-best.pt` + promotes `model/weights/state_dict.pt`. Monitor resolves from `Training.early_stopping`; absent it, `val_loss` (min) when a val split exists else `train_loss` (min). `reduce_on_plateau` is stepped with its `ScheduleSpec.monitor` value; other schedules step unconditionally. The plugin's `run_training` delegates here via a lazy import to keep `plugin.py` torch-free at discovery.)
- [x] Calls `enable_deterministic_algorithms()` from C.e before model construction. (Enabled at loop start (idempotent) + the training-time RNG seeded from the `"dropout"` scope; weight-init reproducibility is the model-construction caller's job — the orchestrator/test seeds before `build_model` — documented in the module + exercised by the byte-identity test.)
- [x] Uses `build_dataloader` from C.f with `worker_init_fn_factory` from B.j. (Train loader shuffles via the seeded generator; the val loader is built `shuffle=False`. Lazy `Augmentations` from the bound DataRefinery recipe (train-split, `materialization: lazy`) are composed via C.g and applied to the train split only.)
- [x] Class weights (from C.d's `cross_entropy_class_weighted`) fit on the train split at training start; persist to `training/class_weights.json`. (Fit cheaply via a new additive `DataRefineryDataset.class_counts()` — reads labels from the JSONL records without decoding images; the JSON records `weight_source` / `class_counts` / `class_weights` / `classes`.)
- [x] Integration test (small synthetic dataset): trainer runs 3 epochs, writes `history.parquet` with the expected columns, writes checkpoints, promotes the best checkpoint to `model/weights/`. Re-running with the same seed produces byte-identical history. ([tests/integration/test_pytorch_trainer.py](../../tests/integration/test_pytorch_trainer.py): 4 tests over a hand-built DataRefinery instance (real `Instance.load`) + a tiny Flatten→Linear model — history/checkpoints/best-weights, **byte-identical reruns** (state_dict bytes + `history.parquet` bytes + `result.history`), class-weighted-loss persistence, and best-checkpoint-tracks-monitor. Updated the C.b registration test, which asserted `run_training` was a stub.)
- [x] Verify: `pyve test tests/integration/test_pytorch_trainer.py` passes. (4 passed; full suite **302 passed**; `mypy src tests` clean (63 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.i: PyTorch Optuna optimization — `plugins.pytorch.optimization` [Done]

`features.md` FR-11, `tech-spec.md` § `plugins.pytorch` > `optimization.py`.

- [x] Create `src/modelfoundry/plugins/pytorch/optimization.py` with `run_optimization(opt_spec, recipe, data_instance, seed, temp_dir) -> OptimizationResult`. Builds Optuna `Study` with `RDBStorage("sqlite:///<temp-dir>/optimization/study.db")`; sampler seeded via `derive_seed(master_seed, "optuna_sampler")`; `n_jobs=1` enforced; pruner `MedianPruner` or none. (Sampler seed masked to 32 bits — Optuna/NumPy reject a 64-bit seed. `tpe`→`TPESampler`, `random`→`RandomSampler`, `grid`→`GridSampler` over a categorical-only grid (`search_space.categorical_grid`, raises on a continuous distribution). `OptimizationResult` is a frozen dataclass — `best_params`/`best_value`/`objective_metric`/`direction`/`n_trials` + the three artifact paths. The plugin's `run_optimization` delegates here via lazy import.)
- [x] `baseline_trial: enqueue_recipe_defaults`: calls `study.enqueue_trial(...)` with the recipe's hyperparameter values flattened from the search-space-relevant fields. (`search_space.baseline_params(recipe)` reads the recipe's current value at each dotted search-space path; enqueued with `skip_if_exists=True` so it lands as trial 0.)
- [x] Trial loop: sample hyperparameters → apply to recipe copy → run short Training (capped by `max_epochs_per_trial`) → report intermediate values per epoch → return `Evaluation.primary_metric` (or `Optimization.objective_metric`) evaluated on `val` as the trial value. (Per-epoch reporting + pruning go through the new additive `run_training(..., epoch_callback=)` hook — the callback reports `val_*` and raises `optuna.TrialPruned` on `should_prune()`. Each trial seeds from `derive_seed(seed, "trial", <number>)` so the study reruns identically. The objective metric resolves to the trainer's `val_accuracy`/`val_loss` — `accuracy`→maximize, `loss`→minimize; the richer Evaluation vocabulary is C.j's. Trial value = best of that metric over the trial's epochs.)
- [x] **Tunable `batch_size` + `early_stopping.patience` (Subphase C-1 / G4):** ensure the search-space mechanism can target these recipe paths (`Training.batch_size` as a categorical, e.g. `{32,64,128}`; `Training.early_stopping.patience` as an int range), that B.m validator check 7 accepts them, and that `apply_params` threads `batch_size` through to `build_dataloader` (C.f) and `patience` through to the early-stopping monitor (C.h) within each trial. (New `recipe/search_space.py`: `suggest_params` supports `log_uniform`/`uniform`/`int`/`categorical`; `apply_params` deep-sets the dotted paths and rebuilds the frozen `ModelRecipe`, so `batch_size`/`patience` take effect in each trial's training. Check 7 already accepts these paths — they are real recipe paths.)
- [x] Persists `trials.parquet` (matches Optuna's `study.trials_dataframe()` shape) and `best-params.json`.
- [x] Best-trial params merged back into the recipe via `recipe.search_space.apply_params(...)` before the Training stage runs (auto-composition, FR-3 step 4.2 → 4.3). (`run_optimization` returns `best_params`; the merge-back via `apply_params` is exercised by the test. The orchestrator C.o applies it before the final Training stage.)
- [x] Integration test: 3-trial TPE study deterministic across reruns; baseline_trial enqueued correctly; best-params merge into the recipe; a study that varies `batch_size` and `patience` runs and the chosen values take effect in the trial's DataLoader / early-stopping. ([tests/integration/test_pytorch_optimization.py](../../tests/integration/test_pytorch_optimization.py): 4 tests — artifact + best-params persistence, baseline-trial-is-trial-0-defaults, deterministic reruns (best params + value + the full per-trial param sequence from `trials.parquet`), and `apply_params` merge-back asserting the chosen `batch_size`/`patience`/LR land in the rebuilt recipe.)
- [x] Verify: `pyve test tests/integration/test_pytorch_optimization.py` passes. (4 passed; full suite **306 passed**; `mypy src tests` clean (66 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.j: PyTorch evaluation — `plugins.pytorch.evaluation` [Done]

`features.md` FR-12 / FR-22, `tech-spec.md` § `plugins.pytorch` > `evaluation.py`. Metric implementations via `torchmetrics`; predictions persistence.

- [x] Create `src/modelfoundry/plugins/pytorch/evaluation.py` with `run_evaluation(eval_spec, model, data_instance, temp_dir) -> EvaluationResult`. Iterates each split in `Evaluation.splits`; runs inference; computes metrics via `torchmetrics` (`MulticlassF1Score`, `MulticlassPrecision`, `MulticlassRecall`, `MulticlassAccuracy`, `MulticlassConfusionMatrix`, `CalibrationError`). (Uses the `torchmetrics.functional.classification` API — `multiclass_{accuracy,f1_score,precision,recall,confusion_matrix,calibration_error}`. Computes the validator's `EVALUATION_METRIC_VOCABULARY` (`macro_f1` / `per_class_f1` / `per_class_precision` / `per_class_recall` / `accuracy` / `confusion_matrix` / `ece` / `calibration_curve`) per the recipe's requested `metrics`. Eval runs on the model's existing device (`next(model.parameters()).device`) — the Protocol passes no `TrainingSpec`; a simple `shuffle=False, num_workers=0` loader makes metrics order-independent. `EvaluationResult` is a frozen dataclass: `metrics` (`{split: {metric: value}}`) + artifact paths + `warnings`. The plugin's `run_evaluation` delegates here via lazy import. **Additive C.f extension:** `DataRefineryDataset.record_ids()` aligns predictions to record ids.)
- [x] `calibration_curve` via the sklearn helper from C.m's shared `plugins/sklearn/metrics.py`. (**Forward-created the shared module here** — `src/modelfoundry/plugins/sklearn/{__init__,metrics}.py` with the multiclass **confidence-reliability** `calibration_curve` (equal-width confidence bins → mean-confidence + observed-accuracy + count). This is the C.j slice; **C.m extends the same module** with `f1_score`/`confusion_matrix`/hand-rolled ECE + the working `MLPClassifier` baseline. Reference-accretion, flagged at the gate.)
- [x] Persists `evaluation/metrics.json`, `evaluation/confusion_matrix.npz`, `evaluation/calibration.parquet` (when applicable), and `evaluation/predictions.parquet` (columns: `split`, `record_id`, `true_label`, `pred_label`, `pred_proba_<class>` per declared class). (`metrics.json` is the `{split: {metric: value}}` shape B.l's `evaluate_expectations` consumes directly; `confusion_matrix.npz` keys per split; `calibration.parquet` only when `calibration_curve` is requested.)
- [x] `Evaluation.comparison.baseline_model_id`: lazy-resolve via the plugin's baseline resolver; failures emit a warning and continue. (The baseline resolver is deferred to the C.m sklearn baseline + C.p library API; pre-prod records a clear warning naming the unresolved `baseline_model_id` and continues — no hard failure.)
- [x] Integration test: every metric in the pre-production vocabulary computes against a hand-computed golden; `predictions.parquet` has the expected columns and row count. ([tests/integration/test_pytorch_evaluation.py](../../tests/integration/test_pytorch_evaluation.py): 5 tests — **sklearn is the golden reference** (accuracy / macro-f1 / per-class precision-recall-f1 / confusion-matrix cross-checked against `sklearn.metrics` computed from the persisted `predictions.parquet`), predictions columns + row count + softmax-sums-to-1, confusion `.npz` + calibration `.parquet` shapes, `metrics.json` expectations shape, and the deferred-baseline warning.)
- [x] Verify: `pyve test tests/integration/test_pytorch_evaluation.py` passes. (5 passed; full suite **311 passed**; `mypy src tests` clean (70 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.k: PyTorch visualizations — `plugins.pytorch.visualizations` [Done]

`features.md` FR-13, `tech-spec.md` § `plugins.pytorch` > `visualizations.py`. Matplotlib renderers for the registered ops.

- [x] Create `src/modelfoundry/plugins/pytorch/visualizations.py` with renderers for `training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid`. Each takes an `InstanceArtifacts` snapshot (history dataframe, evaluation dict, predictions dataframe, optional trials dataframe) and returns PNG bytes. (`render_visualization(viz, artifacts)` dispatches on `VisualizationSpec.op` (unknown op → `PluginError`); `confusion_matrix`/`calibration_curve` read their split from a `split` extra on the viz spec, defaulting to the first evaluation split. **Defined `InstanceArtifacts` concretely** — promoted the `base.py` forward stub from `type = Any` to a frozen dataclass (`history`/`evaluation`/`predictions`/`trials`/`class_names`, all optional); C.p constructs + extends it. The plugin's `render_visualization` delegates here via lazy import (keeps `plugin.py` matplotlib-free at discovery).)
- [x] `optimization_history` renders an empty-placeholder PNG when no Optimization stage ran (so manifest viz records stay consistent). (Placeholder also covers a present-but-all-pruned trials frame — `NaN` trial values are dropped, and an empty result short-circuits to the placeholder.)
- [x] `predictions_grid` renders labels-only when the bound DataRefinery instance does not expose per-record images. (Labels-only is the only path wired here — a grid of `true:`/`pred:` text cells, green/red by correctness, capped by a `max_items` viz extra (default 16). Per-record image thumbnails are a future enhancement once the artifacts snapshot carries decoded images.)
- [x] Unit tests: each renderer produces a PNG of nontrivial size; byte-deterministic across reruns with a fixed matplotlib backend (Agg). ([tests/unit/test_pytorch_visualizations.py](../../tests/unit/test_pytorch_visualizations.py): 14 tests — PNG-magic + nontrivial-size and byte-identity reruns for all five ops, the no-trials placeholder, labels-only grid, the `split` extra, and the unknown-op `PluginError`. Determinism comes from the forced Agg backend + a pinned `Software` PNG-metadata tag + no timestamp.)
- [x] Verify: `pyve test tests/unit/test_pytorch_visualizations.py` passes. (14 passed; full suite **325 passed**; `mypy src tests` clean (72 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.l: PyTorch persistence + round-trip — `plugins.pytorch.persistence` [Done]

`features.md` FR-23 (round-trip from disk alone), `tech-spec.md` § `plugins.pytorch` > `persistence.py`. **See `project-essentials.md` § Cache identity is the reproducibility contract** for the architecture.json round-trip discipline.

- [x] Create `src/modelfoundry/plugins/pytorch/persistence.py` with:
  - `save_model(model, model_dir)`: writes `model/weights/state_dict.pt` via `torch.save(model.state_dict(), ...)`; writes `model/architecture.json` (the canonical post-variant-overlay, post-Optimization-merge `Architecture` block, JSON-canonical bytes via `canonical_bytes`); writes `model/checkpoints/checkpoint-best.pt` (the `Checkpoint` model from B.k). (**Self-describing model:** the bare Protocol signature is `save_model(model, path)` with no recipe, so `architecture.build_model` was extended to attach the source `Architecture` block to the module as `model.architecture_spec`; `save_model` reads it (→ `PluginError` if a model wasn't built by `build_model`) and writes canonical JSON via the shared sort-keys/compact form. The re-persist `checkpoint-best.pt` carries `epoch=-1` / `metric_value=NaN` provenance — the metric-bearing best checkpoint is the trainer's C.h artifact; this is the from-disk persistence copy.)
  - `load_model(path) -> nn.Module`: reads `model/architecture.json`, rebuilds the `nn.Module` via the C.c recursive builder, then `load_state_dict` from `model/weights/state_dict.pt`. No external config object required. (Missing artifact → `InstanceError`; `torch.load(..., weights_only=True)` for the safe load path; returns the model in `eval()`.)
- [x] `predict(model, X) -> np.ndarray | pd.Series` and `predict_proba(model, X) -> np.ndarray | pd.DataFrame` accepting `pd.DataFrame` (record-schema), `list[Path]` (image paths), or 4-D `np.ndarray` of shape `(N, H, W, C)`. (`_to_batch` coerces every input to an `(N, C, H, W)` float32 tensor — integer ndarrays are scaled `/255` to match the data adapter's `[0,1]` decode; a DataFrame resolves its `path`/`image` column; runs on the model's device under `eval()` + `no_grad`. Returns `pd.Series`/`pd.DataFrame` for DataFrame input, plain `np.ndarray` otherwise; unsupported input / non-4-D ndarray → `PluginError`. **Note:** dataset-fitted normalization isn't applied here — `predict` takes ready pixels; record-schema normalization parity when stats are needed is the orchestrator's job, since the Protocol passes no bound instance.)
- [x] Integration test: save a trained `simple_cnn` to a temp dir; load via `load_model`; `predict(X)` returns the same outputs as the original model on a fixed input batch (round-trip guarantee). ([tests/integration/test_pytorch_round_trip.py](../../tests/integration/test_pytorch_round_trip.py): 8 tests — round-trip proba+preds equality, self-describing `architecture.json`, proba shape + softmax-sum, image-paths + DataFrame-`path` inputs, unsupported / 3-D-ndarray / un-attributed-model `PluginError`s.)
- [x] Verify: `pyve test tests/integration/test_pytorch_round_trip.py` passes. (8 passed; full suite **333 passed**; `mypy src tests` clean (74 files); `ruff check` clean. **All four previously-stubbed plugin methods are now implemented**, so the `_not_implemented` helper + the C.b stub-probe test were retired. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.m: sklearn plugin — working `MLPClassifier` baseline + shared metrics [Done]

`features.md` FR-24, `tech-spec.md` § `plugins.sklearn`. **Subphase C-1 (G5): promoted from a stub to a working baseline** so the brief's sklearn "ceiling baseline" is materializable through ModelFoundry (e.g. as an `Evaluation.comparison.baseline_model_id`), not just a redirect.

- [x] Create `src/modelfoundry/plugins/sklearn/__init__.py`, `src/modelfoundry/plugins/sklearn/plugin.py` implementing the `Plugin` Protocol for a real `MLPClassifier` baseline: `build_model`, `run_training`, `run_evaluation`, `save_model`/`load_model`, `predict`/`predict_proba`. Registers the `OperationSpec` set it supports. (`build_model` constructs an `MLPClassifier` from a `{type: mlp_classifier, ...}` Architecture block (wrong type → `PluginError`); `run_training` fits + persists `model/estimator.joblib` (joblib pickles the whole fitted estimator, so `load_model` returns it directly — no architecture.json rebuild needed) and writes `training/history.parquet` from `loss_curve_`; `run_evaluation` mirrors C.j's artifact shapes (`metrics.json`/`predictions.parquet`/`confusion_matrix.npz`/`calibration.parquet`). `run_optimization`/`render_visualization` raise `NotImplementedError` — the baseline is a fixed comparison model. Registers the `mlp_classifier` `OperationSpec`; `health_check` reports `accelerators=("cpu",)` so validator check 20 reads it. Import-safe without heavy extras — sklearn/joblib/the torch feature path import lazily inside methods.)
- [x] Feature-flattening data path: adapt the bound `DataRefineryInstance` records (uint8 PNG → normalized float32 per C.f's stats) into the flat `(n_samples, n_features)` matrix sklearn expects; reuse the C.f normalization + all-splits label scan so train/inference parity and class ordering match the pytorch path. (`sklearn/data.py::feature_matrix` **reuses the C.f `DataRefineryDataset`** directly — flattens each normalized CHW tensor — so parity holds by construction, no re-implemented normalization to drift; a test asserts the features equal the pytorch path's flattened tensors. **Pre-prod coupling:** this means the sklearn feature path imports `torch`, so materializing a `plugin: sklearn` recipe currently needs the `[pytorch]` extra (lazy import keeps *discovery* torch-free). Deliberate parity-over-decoupling trade; torch-free extraction is future work.)
- [x] `src/modelfoundry/plugins/sklearn/metrics.py`: shared sklearn-based metric implementations (`f1_score`, `confusion_matrix`, `calibration_curve`, hand-rolled ECE) consumed by the pytorch plugin (per C.j's calibration_curve dependency). (Extended the C.j-seeded module with `accuracy` / `f1_score` / `precision_score` / `recall_score` / `confusion_matrix` (lazy `sklearn.metrics`) and `expected_calibration_error` (hand-rolled, count-weighted `|conf−acc|` over the `calibration_curve` bins). `calibration_curve` stays the C.j cross-plugin reliability form.)
- [x] Wire the sklearn entry point into `pyproject.toml` under `[project.entry-points."modelfoundry.plugins"]`; ensure the `[sklearn]` extra carries the needed deps. (`sklearn = "modelfoundry.plugins.sklearn.plugin:plugin"`; reinstalled editable so `importlib.metadata` sees it. The `[sklearn]` extra stays empty — scikit-learn + joblib are base deps — documented with a comment.)
- [x] Determinism: seed `MLPClassifier(random_state=...)` from `pipeline.seeding.derive_seed` so the baseline is reproducible like the rest of the pipeline. (`run_training` sets `random_state = derive_seed(seed, "weight_init") & 0xFFFFFFFF` before `fit`; a test asserts two runs give identical `predict_proba`.)
- [x] Integration test: `discover_plugins()` finds both `pytorch` and `sklearn`; sklearn `health_check()` reports ready; a small `plugin: sklearn` recipe materializes an `MLPClassifier` end-to-end and reports validation accuracy; round-trip `load_model(path).predict(X)` matches. ([tests/integration/test_sklearn_baseline.py](../../tests/integration/test_sklearn_baseline.py): 6 tests — both-plugins discovery + health, build→train→evaluate end-to-end (val accuracy + artifacts), joblib round-trip predict equality, training determinism, **C.f feature parity**, and the wrong-arch-type `PluginError`. The end-to-end drives the plugin methods directly since the materialize orchestrator is C.o.)
- [x] Verify: `pyve test tests/integration/test_sklearn_baseline.py` passes. (6 passed; full suite **339 passed**; `mypy src tests` clean (77 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.n: Reporting — `reporting.report` + reporting visualizations pipeline [Done]

`features.md` FR-18, `tech-spec.md` § `reporting`.

- [x] Create `src/modelfoundry/reporting/__init__.py`, `src/modelfoundry/reporting/report.py` with `render_report(instance_artifacts) -> str` (Markdown summary of recipe + plugin + metrics + optimization summary + expectations + warnings). (Stable headings `## Recipe` / `## Metrics` / `## Optimization` / `## Expectations` / `## Warnings`; reads recipe + manifest + the evaluation dict from the snapshot, degrading gracefully (`_No optimization stage._`, `_None declared._`, …) for partial/minimal instances. Metrics render as a per-split table of *scalar* metrics — `confusion_matrix`/`calibration_curve` are excluded from cells; expectations render ✅/❌. **Extended `InstanceArtifacts`** (base.py) additively with `recipe` + `manifest` fields so the snapshot carries what the report needs.)
- [x] `src/modelfoundry/reporting/visualizations.py`: drives the reporting-mode visualizations from the recipe's `Visualizations` block where `mode: reporting`. Writes PNG bytes from each plugin renderer to `report/visualizations/<name>.png`. (`render_reporting_visualizations(recipe, plugin, artifacts, viz_dir)` filters to `mode == "reporting"`, calls `plugin.render_visualization`, and writes each non-`None` PNG; filename is the viz's `name` extra when present, else its `op`.)
- [x] `instance.render_report()` (called from C.p) re-renders into a `report.tmp/` and atomically replaces `report/` on success — preserves the existing report on failure. (`rerender_report(instance_dir, artifacts, recipe, plugin)` builds the full report (md + visualizations) in `report.tmp/`, moves the live `report/` aside to `report.bak/`, swaps `report.tmp → report/`, then deletes the backup — restoring the backup if the swap fails. A failure *during* the tmp build never touches the live `report/`. C.p will call this; the helper lands here.)
- [x] Unit tests: `render_report` produces a Markdown doc with the expected section headings; viz dispatcher correctly routes mode=reporting ops to the plugin. ([tests/unit/test_reporting.py](../../tests/unit/test_reporting.py): 8 tests — all-headings, recipe+metrics rendering (scalar-only table), optimization/expectations/warnings, empty-artifacts degradation, reporting-mode-only routing, `name`-extra filename, atomic replace, and old-report-preserved-on-failure — with a stub plugin so the dispatcher tests stay torch-free.)
- [x] Verify: `pyve test tests/unit/test_reporting.py` passes. (8 passed; full suite **347 passed**; `mypy src tests` clean (81 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.o: Materialize orchestrator — `pipeline.runner.MaterializeRunner` [Done]

`features.md` FR-3, `tech-spec.md` § `pipeline.runner`. The orchestrator that sequences every stage atomically.

- [x] Create `src/modelfoundry/pipeline/runner.py` with `MaterializeRunner.run() -> Manifest`. Sequences the stages per FR-3 step 4: Architecture → Optimization (if declared) → Training → Evaluation → OutputExpectations → Reporting visualizations → Persistence → Report → Manifest. (`run()` computes the `CacheKey` from the recipe + the bound DR instance triple (`manifest.recipe_hash`/`input_hash`/`seed`), trashes the prior instance when `runtime_config.overwrite`, and materializes inside `cache.atomic.materialize_temp_dir` (atomic promote on clean exit). Optimization merges `best_params` back via `search_space.apply_params` and rebuilds the model from the merged recipe. The runner is plugin-agnostic — it drives the `Plugin` Protocol and duck-types the per-stage results, so the same path serves PyTorch and sklearn.)
- [x] Wraps each stage with structured logging (`logging.JsonFormatter`) and elapsed-time accounting that flows into `Manifest.elapsed_seconds` and per-stage timing in the report. (`_stage(name, fn)` times + JSON-logs `stage_start`/`stage_done`; total wall-clock → `Manifest.elapsed_seconds`; the per-stage `stage_timings` dict flows into `InstanceArtifacts` and renders as a new `## Stages` section in the report — small additive extension to `InstanceArtifacts` (base.py) + `render_report` (C.n).)
- [x] On any stage exception: writes the `FAILED` marker (via `cache.atomic`) naming the failing stage + error class + message; re-raises as `MaterializeError`. OutputExpectations failure handled the same way with `ExpectationError`. (Non-`ModelfoundryError` exceptions are wrapped as `MaterializeError(stage=...)`; domain errors propagate (annotated with their stage if unset). A failing `OutputExpectation` raises `ExpectationError(stage="output_expectations")`. The atomic context writes the `FAILED` marker (reading `exc.stage`) and leaves the temp dir for diagnosis — the final path is never touched.)
- [x] Stage skipping: `Optimization` absent → skip stage 2; `Evaluation.splits` empty → skip stage 4; manifest records skipped stages. (No `Optimization` → `manifest.optimization = None`; empty `Evaluation.splits` → evaluation skipped, `manifest.evaluation = {}`, logged `stage_skipped`.)
- [x] Integration test against the C.f synthesized fixture: full materialize end-to-end produces a complete instance directory with manifest, model artifacts, training history, evaluation metrics, predictions, report. ([tests/integration/test_materialize_runner.py](../../tests/integration/test_materialize_runner.py): 5 tests — full materialize (asserts `manifest.json` + `model/architecture.json` + `weights/state_dict.pt` + `training/history.parquet` + `evaluation/{metrics.json,predictions.parquet}` + `report/report.md` + a reporting-viz PNG + the `## Stages` section), the Optimization branch (`manifest.optimization` populated, `best-params.json` written), a failing expectation aborting without promote (+ `FAILED` marker naming the stage/error), evaluation-skip with empty splits, and existing-instance-blocks-without-overwrite (`ModelArtifactExistsError`).)
- [x] Verify: `pyve test tests/integration/test_materialize_runner.py` passes. (5 passed; full suite **352 passed**; `mypy src tests` clean (83 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.p: `ModelFoundry` class + `ModelInstance` notebook-shaped accessors [Done]

`features.md` FR-22, `tech-spec.md` § Key Component Design > `ModelFoundry` + `ModelInstance`. The library entry point + the substrate-neutral result object. (The Phase C release bump moved to C.r, the subphase's last story.)

- [x] Create `src/modelfoundry/core/__init__.py`, `src/modelfoundry/core/modelfoundry.py` with `ModelFoundry.from_recipe(recipe_path, *, data, config=None, variant=None, seed=None) -> ModelFoundry` and the verbs `validate`, `materialize`, `status`, `inspect`, `report`, `clean`, `check`. Verbs are thin wrappers that share construction state. (`from_recipe` loads the recipe (variant/seed overrides), binds `data` (accepts a pre-bound `DataRefineryInstance` *or* a data-cache-root path resolved via `resolve_data_instance`), discovers the plugin (unknown → `PluginError`), and precomputes the `CacheKey`/`CachePaths`. `materialize` drives `MaterializeRunner` then returns `ModelInstance.load(instance_dir)`; `status` reports materialized + manifest; `inspect`/`report` require a materialized instance (`InstanceError` otherwise); `clean` trashes via `cache.atomic.trash_existing`; `check` returns version + plugin `health_check`. `core/__init__.py` already existed.)
- [x] Top-level `materialize(...)` convenience function per `tech-spec.md`. (`materialize(recipe_path, *, data, config, variant, seed)` = `from_recipe(...).materialize()`.)
- [x] `src/modelfoundry/core/instance.py` with `ModelInstance` frozen dataclass + the cached-property accessors (`metrics`, `evaluation`, `confusion_matrix`, `calibration`, `predictions`, `trials`, `best_params`, `figures`) + `predict(X)` / `predict_proba(X)` (delegated to the plugin) + `load(path)` classmethod + `render_report()`. (The `summary` accessor is added by C.q.) (Frozen dataclass — `cached_property` writes into `__dict__`, bypassing the frozen `__setattr__`, so accessors cache without mutating the handle. Accessors lazily read on-disk artifacts (json/npz/parquet/png); `load(path)` resolves the plugin from `manifest.plugin` and reconstructs the model on first `predict`; `render_report()` re-renders atomically from the persisted `recipe.yml` (now written by the runner) + falls back to the saved `report.md`. **Runner now persists `recipe.yml`** into the instance so it is self-contained for `load` + re-render.)
- [x] Re-export `ModelFoundry`, `ModelInstance`, `materialize`, `ModelfoundryError` from `src/modelfoundry/__init__.py`.
- [x] Integration test: full materialize via `ModelFoundry.from_recipe(...).materialize()`; every `ModelInstance` accessor returns the expected type and shape; `ModelInstance.load(path).predict(X)` round-trips per FR-23. ([tests/integration/test_modelfoundry_api.py](../../tests/integration/test_modelfoundry_api.py): 4 tests — materialize + every accessor (metrics/evaluation/confusion-matrix shape/calibration/predictions row-count/trials-None/best-params-None/figures PNG), `ModelInstance.load(...).predict` round-trip equality, the `status`/`check`/`report`/`inspect`/`clean` verbs, and the top-level `materialize` + re-export smoke.)
- [x] Verify: `pyve test tests/integration/test_modelfoundry_api.py` passes; `from modelfoundry import ModelFoundry, ModelInstance, materialize, ModelfoundryError` works. (4 passed; full suite **356 passed**; `mypy src tests` clean (86 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.q: PyTorch model summary (torchinfo) — `plugins.pytorch.summary` [Done]

`features.md` **FR-27** (new — model summary), `tech-spec.md` § `plugins.pytorch` > `summary.py`. Subphase C-1 (G1, R2–R4): the brief requires a generated model summary reporting per-layer type, output shape, parameter count, mult-adds, and network totals (incl. trainable/non-trainable). Surfaced as a **materialize-time artifact** so it is reproducible and readable from disk alone.

- [x] Add `torchinfo` to the `[pytorch]` extra in `pyproject.toml`. (`torchinfo>=1.8`; installed into the conda testenv.)
- [x] Create `src/modelfoundry/plugins/pytorch/summary.py` with a capability that runs `torchinfo.summary(model, input_size=(N, C, H, W), verbose=0)` (input shape derived from the bound instance's record schema, e.g. `(N, 3, 32, 32)` for CIFAR-10) and returns a structured result: per-layer `(type, output_shape, param_count, mult_adds)` rows + totals (`total_params`, `trainable_params`, `non_trainable_params`, `total_mult_adds`). (`summarize(model, input_size) -> (ModelSummary, str)` runs torchinfo **once** — eval-mode probe with the training flag snapshotted/restored, so it never perturbs the persisted model's BN stats — and returns both the structured `ModelSummary` (pydantic) and the text render. `LayerSummary` rows also carry `depth`/`leaf`. `derive_input_size(data_instance)` reads the record-schema image shape (HWC → `(1, C, H, W)`), decoding one record via the C.f adapter as a fallback.)
- [x] Materialize-time artifact: the orchestrator (C.o) writes `model/summary.txt` (the torchinfo render) and `model/summary.json` (the structured rows + totals). Byte-deterministic for a fixed architecture + input size (no timestamps in the artifact). (`write_summary` writes both — canonical-sorted JSON, trailing newline. The runner adds a duck-typed `model_summary` stage after Persistence calling the **optional** `PyTorchPlugin.write_model_summary(model, data, model_dir)`; plugins without it (sklearn) skip the stage cleanly, so the runner stays plugin-agnostic. `CachePaths` gains `summary_txt`/`summary_json`.)
- [x] `ModelInstance.summary` cached-property accessor (extends C.p) reads `model/summary.json`; `inspect --view model_summary` (FR-17) renders the text summary. Substrate-neutral — renders in any notebook host. (Added `ModelInstance.summary` (structured dict) + `ModelInstance.summary_text` (text render); `print(mi.summary_text)` renders in any host. The **CLI** `inspect --view model_summary` surface is FR-17 / Story D.g — the CLI doesn't exist until Phase D — and reads `summary_text`; flagged at the gate.)
- [x] Author **FR-27** in `features.md` (model-summary requirement + the three reported quantities) and a `tech-spec.md` § `plugins.pytorch` > `summary.py` subsection; reference FR-17 for the inspect view. (FR-27 added (incl. the optional-plugin-capability + edge cases), the instance-dir tree now lists `model/summary.{txt,json}`, the tech-spec `summary.py` bullet + the `ModelInstance` block's `summary`/`summary_text` accessors added.)
- [x] Unit tests: summary of `resnet20` reports the pinned total (≈272,474) and the expected layer-type inventory; `model/summary.json` round-trips through the accessor; the rendered bytes are identical across two runs (determinism). ([tests/unit/test_pytorch_summary.py](../../tests/unit/test_pytorch_summary.py): 8 tests — the `272_474` pin + leaf inventory (21 Conv2d / 21 BatchNorm2d / 1 Linear / 1 AdaptiveAvgPool2d / 1 Flatten), text totals, layer-row shapes, byte-identical `summary.{txt,json}` reruns, accessor round-trip + absent→`None`, and `derive_input_size` from the record schema. The C.o materialize test also asserts `model/summary.{txt,json}` are written end-to-end.)
- [x] Verify: `pyve test tests/unit/test_pytorch_summary.py` passes. (8 passed; full suite **364 passed**; `mypy src tests` clean (88 files); `ruff check` clean. Run via the conda testenv interpreter — `pyve test` parked on the Pyve v3.0.6 conda fix per B.o.)

### Story C.q.1: DataRefinery instance resolution via `resolve_instance` — B.i binding repair [Done]

Bugfix for the latent defect surfaced while wiring the real CIFAR-10 instance for C.r. [`pipeline.data_binding.resolve_data_instance`](../../src/modelfoundry/pipeline/data_binding.py) (B.i) **re-derived** DataRefinery's cache key by hand — `sha256(to_canonical_bytes(recipe))[:16]` + a `<recipe-hash16>/*/<seed>/` bucket scan — instead of calling DataRefinery's resolver. That re-derivation diverged from DataRefinery on any recipe carrying a `variants:` block: DataRefinery clears `variants` for the default instance's cache key, ModelFoundry didn't, so a variants-bearing DR recipe (like `cifar10-base.yaml`) could never be located (hash `bb81a6f6…` vs the instance's `5e49ad15…`). The B.i binding tests used variant-free fixtures, hiding it. Per [`vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md) § "Resolving a materialized instance" (Story J.l), consumers MUST resolve via the blessed API and MUST NOT recompute the key. No package version bump — rides the phase-bundled Phase C release.

- [x] Refactor `resolve_data_instance` to resolve via `datarefinery.resolve_instance(recipe_path, cache_root=…, seed=…, variant=…)` → `StatusReport`: `miss` → `DataBindingError` ("no materialized instance"), `corrupt` → `DataBindingError`, `hit` → `status.instance_path`. Dropped the hand-rolled hash, the `_find_instance` scan, and the `apply_variant` dance; kept the post-resolution FAILED-marker / `is_partial` / aggressive-sidecar / schema-version-gate checks. The **ambiguous-bind** failure mode is **removed** — `resolve_instance` computes an exact key, so a multi-match scan is impossible. Behavioral change (documented): resolution now hashes the recipe's declared inputs, so the source inputs must be present on the resolving host (vendor-spec § Host portability); the prior B.i rationale for re-deriving ("avoid reading source bytes") is obsolete.
- [x] Bump the `ml-datarefinery` pin to `>=0.20.0` in [pyproject.toml](../../pyproject.toml) — `resolve_instance` / `StatusReport` ship in DR 0.20.0.
- [x] Rework [tests/unit/test_data_binding.py](../../tests/unit/test_data_binding.py): fixtures now **materialize tiny real instances** via `datarefinery.materialize` (a faked `input_hash` no longer resolves once the resolver hashes real inputs), using the `image_flat` + `label_from` CSV pattern that stamps `label` into records (the `derived: parent_directory_name` mode does not). Added **`test_variants_recipe_binds`** — the regression guard: a `variants:`-bearing recipe must resolve. Removed the obsolete ambiguous-bind test.
- [x] Verify: real `cifar10-base` + `cifar10c-eval` both bind via `resolve_data_instance` (num_classes 10); `test_data_binding.py` **12 passed**; full suite **364 passed** (`pyve test --env smoke-pytorch`); `ruff check` clean (testenv); `mypy src tests` clean — **88 files** (new full-closure `typecheck` env). The DataRefinery side (`resolve_instance` facade + the vendor-dep-spec § "Resolving a materialized instance") was implemented upstream by the developer.

> Env note: verification used the developer's revamped venv env topology — a light `testenv` (ruff), a lazy `smoke-pytorch` (full PyTorch closure; deps in [tests/integration/env/pytorch.txt](../../tests/integration/env/pytorch.txt)), and a lazy `typecheck` env (full type closure for `mypy`; deps in [requirements-typecheck.txt](../../requirements-typecheck.txt)). This supersedes B.o's two-micromamba design; **B.o / B.p / `env-dependencies.md` are now stale and need re-reconciliation to the venv+smoke+typecheck layout** (separate follow-up).

### Story C.q.2: PyTorch visualization `OperationSpec` registration — C.k repair [Done]

Bugfix for a latent defect surfaced while wiring C.r's deliverable recipe. The PyTorch plugin's five visualization renderers (`training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid`) are dispatched by `plugins.pytorch.visualizations._RENDERERS` but were **never registered as `OperationSpec`s** in `PyTorchPlugin.operations`. The FR-2 validator's check 3 (`section_ops_registered`) iterates `Visualizations` ops and requires each in `plugin.operations`, so `validate()` spuriously fails any recipe declaring a `Visualizations:` section — even though `materialize()` (which skips the validator) renders the figures fine. [plugin.py](../../src/modelfoundry/plugins/pytorch/plugin.py)'s own comment ("the visualization/evaluation stories extend this map further") flags the intended-but-missing wiring; this is a C.k omission against B.m's validator contract. No package version bump — rides the phase-bundled Phase C release.

- [x] Add `VISUALIZATION_OPERATIONS` to a new [`plugins/pytorch/visualization_specs.py`](../../src/modelfoundry/plugins/pytorch/visualization_specs.py): one `OperationSpec(applies_to="visualization")` per `_RENDERERS` entry, each with a param model matching the renderer's accepted params — `training_curves` / `optimization_history` (`NoVizParams`), `confusion_matrix` / `calibration_curve` (`SplitVizParams`: `split: str | None`, read via `_pick_split`), `predictions_grid` (`PredictionsGridParams`: `max_items: int = 16`). (Placed in a **separate matplotlib-free module**, not in `visualizations.py` — that module imports matplotlib at top and is loaded lazily at materialize time, so importing its registry into `plugin.py` would pull matplotlib into every `discover_plugins()` call. The specs module is pure pydantic; param models are `extra="forbid"` so the validator rejects params an op would silently ignore.)
- [x] Wire `**VISUALIZATION_OPERATIONS` into `PyTorchPlugin.operations` in [`plugin.py`](../../src/modelfoundry/plugins/pytorch/plugin.py). (Verified discovery stays matplotlib/torch-free: importing the plugin imports neither.)
- [x] Unit tests ([tests/unit/test_pytorch_visualizations.py](../../tests/unit/test_pytorch_visualizations.py)): the five viz ops are in `PyTorchPlugin().operations` as `applies_to="visualization"`; check 3 + check 17 pass for a recipe with a `Visualizations:` section (incl. `confusion_matrix {split: val}` + `predictions_grid {max_items: 8}`) against the **real** plugin; param models accept their real params and reject unknown ones (incl. a `split` on `predictions_grid`, which doesn't pick a split). (3 new tests; 17 in the file.)
- [x] Verify: `pyve test --env smoke-pytorch tests/unit/test_pytorch_visualizations.py` passes (**17 passed**); full suite **367 passed**; `ruff check` clean (testenv); `mypy src tests` clean — **89 source files** (typecheck env).

### Story C.r: v0.4.0 Deliverable — CIFAR-10 / ResNet-20 recipe + CPU-budget calibration + e2e [Done]

`features.md` FR-3 / FR-22; Subphase C-1 (G3, R1/R7/R8/R9). The tested client deliverable: a real-shape CIFAR-10 / ResNet-20 recipe materialized end-to-end on CPU, distinct from E.l's downsized CI smoke. **Owns the Phase C v0.4.0 bump** (the phase's last story, per Version Cadence).

- [x] **Hard prerequisites:** the DataRefinery CIFAR-10 instance (DR-1, ~1,700/300/1,000 balanced, with `normalize` + the lazy augmentation policy) and Phase B story **B.q** (ml-datarefinery ≥ 0.19.0 / schema v2). See [`phase-c-subphase-1-reprioritize-plan.md`](phase-c-subphase-1-reprioritize-plan.md) § 8. (Confirmed via the **blessed resolver** `datarefinery.resolve_instance("recipes/cifar10-base.yaml", cache_root="data")` → `hit` at `5e49ad15…/bd42cea6…/20260509`, `datarefinery_version` 0.19.0 / recipe schema v2, splits 1700/300/1000, `normalize_per_channel` + lazy `random_crop`/`horizontal_flip`/`color_jitter`. The instance ID never appears literally — the recipe's `Data.recipe` points at the DR recipe and binding re-hashes its declared inputs.)
- [x] Author `recipes/cifar10_resnet20.yml` (and a smaller fixture variant under `tests/fixtures/recipes/`): `plugin: pytorch`, `Architecture: resnet20`, `Loss: cross_entropy`, `Training.device: cpu`, the R5 search space, `Optimization` TPE + median pruning (`n_jobs=1`) with the `random`-sampler fallback documented, `Evaluation.splits: [val, test]`, `Evaluation.primary_metric: accuracy`. (**R5 op-choice resolution** — developer-approved: the genuine Optuna search dimensions are `Optimizer.learning_rate` / `weight_decay` (log-uniform), `Training.batch_size` ({32,64,128}), `early_stopping.patience` (5..15); the **AdamW-vs-SGD+momentum** and **reduce_on_plateau-vs-cosine** comparisons ship as `variants:` because the flat search space + per-op `extra="forbid"` param models can't carry op-conditional params — cosine's required `T_max` collides with plateau, and SGD's `momentum` breaks AdamW. Base = AdamW + reduce_on_plateau; variants `cosine`, `sgd_momentum`, `cpu_budget`. `early_stopping.monitor: val_loss` — the one monitor both validator check 6 and the trainer recognize. All four recipe forms pass the full 20-check validator clean.)
- [x] **CPU-budget calibration (measured, C5):** recorded in the recipe header + below. (Measured on Apple-silicon CPU: **≈7 s/epoch** over the 1,700-image train split @ `batch_size 128` (≈10–12 s @ 32); evaluation over val 300 + test 1000 ≈3 s. The downsized fixture — 2 trials × 1 epoch + 2 final epochs — materializes end-to-end in **≈37 s**. The deliverable's full 20-trial × ≤8-epoch study is minutes-scale; the `cpu_budget` variant (8 trials × 4 epochs + 15 final) ≈5–7 min; `random`-sampler fallback documented for the cheaper-search case.)
- [x] End-to-end integration test ([tests/integration/test_cifar10_resnet20.py](../../tests/integration/test_cifar10_resnet20.py)): materializes the fixture over the real DR-1 instance → asserts `model/summary.json` pins ResNet-20's **272,474** params, the Optuna study runs + persists `best-params.json`, the post-merge `recipe.yml` carries each best value at its dotted path (final training applies them), val + test `accuracy` are computed, and the FR-23 `ModelInstance.load(path).predict(X)` round-trip is byte-stable. Plus fast (no-train) tests that the deliverable + all variants validate clean and the variants flip optimizer/schedule. Binds via `resolve_instance`; **skips cleanly** where DR-1 isn't materialized.
- [x] Bump version to v0.4.0.
- [x] Update CHANGELOG.md (Phase C `[0.4.0]` summary + the C.r deliverable + the C.q.2 viz-registration fix entries).
- [x] Verify: `pyve test --env smoke-pytorch tests/integration/test_cifar10_resnet20.py` → **3 passed** (≈57 s); full suite **370 passed**; `ruff check` clean (testenv); `mypy src tests` clean — **90 source files** (typecheck env). (Note: the canonical runner is now `pyve test --env smoke-pytorch` — the torch/numpy/matplotlib closure — per the env revamp noted under C.q.1; ruff in `testenv`, mypy in `typecheck`.)

Out of scope (recommended follow-ups, now recorded):
- **Search-space op-choice dimensions** — a grouped/conditional search-space mechanism so optimizer/schedule op-choice can be genuine Optuna dimensions rather than variants. Recorded in the **`## Future`** section ("Search-space op-choice dimensions", sibling to Parallel Optuna trials).
- **Env-layout doc reconcile** to the current venv `testenv` + lazy `smoke-pytorch` + `typecheck` topology (the two-micromamba B.o/B.p design is stale). Recorded as **Story F.b.1** (Phase F, doc-only).

---

## Phase D: CLI

Wrap the library API in a Typer-based CLI exposing all eight verbs (`init`, `validate`, `check`, `status`, `materialize`, `report`, `inspect`, `clean`). Each verb emits `rich`-styled user output to stdout and structured JSON-lines operational logs to the configured log target. The CLI is co-equal with the library API — both go through the same `ModelFoundry` class. By end of Phase D, a developer can drive the full workflow from the shell against a real DataRefinery instance.

### Story D.a: CLI scaffolding — `cli.app` + shared options + exit-code mapping [Done]

`tech-spec.md` § CLI Design.

- [x] Create `src/modelfoundry/cli/__init__.py`, `src/modelfoundry/cli/app.py` with the root `typer.Typer()` instance + `main()` entry point + shared options (`--cache-root`, `--data-cache-root`, `--log-level`, `--log-target`, `--plugin-path`, `--verbose`, `--quiet`). (Modern `Annotated[... , typer.Option(...)]` style; also added an eager `--version` flag so the project-wide `modelfoundry --version` smoke that the A.b placeholder provided keeps working. `--verbose`/`--quiet` are `log_level` shorthands; supplying both is a usage error.)
- [x] Exit-code mapping: `0` success, `1` user/recipe/contract error (catches `RecipeError` / `ValidationError` / `DataBindingError` / `ExpectationError` / `ModelArtifactExistsError`), `2` system/plugin error (`PluginError` / `MaterializeError` / `CacheError` / `OptimizationError`), `130` SIGINT. (Pure `exit_code_for(exc)` function — also folds in `InstanceError`→1 and `InspectionError`→2 (the two domain classes the story didn't enumerate), defaults any other `ModelfoundryError`→1 and unexpected exceptions→2. `invoke`/`main` run the app with `standalone_mode=False` so this module owns rendering + exit codes; SIGINT arrives as typer's `130` return value, honored.)
- [x] Wire shared options into a per-invocation `RuntimeConfig` that is passed to every verb. (`build_runtime_config(...)` → `RuntimeConfig.from_env(**overrides)` so only explicitly-set flags override env→defaults; stored on `ctx.obj` by the callback for the verbs to read.)
- [x] Re-point the placeholder console script from A.a to the real `cli.app:main`. (The `pyproject.toml` entry already targeted `cli.app:main`; `main()` is now the real Typer entry.)
- [x] Verify: `pyve run modelfoundry --help` lists the scaffolded `init`/`validate`/`check`/`status`/`materialize`/`report`/`inspect`/`clean` placeholders; exit codes work for a deliberately-raised error. (All 8 verbs listed; `--help`→0, unknown-command→2, stub verb→0, `--version`→`modelfoundry 0.4.0`. [tests/cli/test_app.py](../../tests/cli/test_app.py): **33 passed**; full suite **403 passed**; `ruff check` + `mypy src tests` clean — 91 files.)

### Story D.b: `validate` command [Done]

`features.md` FR-2.

- [x] Create `src/modelfoundry/cli/commands/validate_cmd.py`: takes a recipe path; calls `ModelFoundry.from_recipe(...).validate()`; renders the `ValidationReport` as a `rich` table; exits 0 if all checks pass, 1 otherwise. (New `cli/commands/` package; `run(recipe, config)` binds via `config.data_cache_root` and returns 0/1, `render_validation(report, recipe)` draws the per-check table + summary. `app.py`'s `validate` verb gains the recipe `Argument` and delegates via a `_config(ctx)` helper that reads the shared-option `RuntimeConfig` off `ctx.obj`.)
- [x] CLI smoke test against a valid recipe + a failing recipe. ([tests/cli/test_validate_cmd.py](../../tests/cli/test_validate_cmd.py): `render_validation` unit tests (pass + fail summaries) and end-to-end CliRunner smokes binding the real DR-1 instance — the deliverable recipe → exit 0, a `primary_metric: ece`-broken copy (check 12) → exit 1, missing-arg → usage error 2; **skips if the DR-1 instance is absent**. 5 tests.)
- [x] Verify: `pyve run modelfoundry validate <fixture-recipe>` works. (Runs + renders the 20-check table. **Env caveat:** the utility `root` env has no `torch`, so check 20 (`device_available`) honestly fails there — `device: cpu` is unavailable when the plugin can't import torch; in `smoke-pytorch` (and a real `pip install ml-modelfoundry[pytorch]`) all 20 pass and it exits 0. Correct behavior, not a defect. `ruff` + `mypy` clean (94 files); full suite **408 passed**.)

### Story D.c: `check` command [Done]

`features.md` FR-19.

- [x] Create `src/modelfoundry/cli/commands/check_cmd.py`: calls `ModelFoundry.check_environment(config)`; renders a `rich` table summarising Python version, installed ModelFoundry version, plugin discovery, per-plugin `health_check` outputs, accelerator availability. (**Deviation:** the story said `ModelFoundry.check()`, but C.p already defined an *instance* `check()` with incompatible recipe-bound semantics — it health-checks only the one recipe's plugin. FR-19 is recipe-free and discovers *every* plugin, so I added a new **classmethod** `ModelFoundry.check_environment(config=None)` instead of overloading the taken name. It discovers all plugins, runs each `health_check()`, and returns `{python_version, modelfoundry_version, plugins:[reports], ok}` — keeping library/CLI co-equality. The instance `check()` is left intact for its C.p integration test. Also refined B.h's deferred `type CheckReport = Any` forward stub in [plugins/base.py](../../src/modelfoundry/plugins/base.py) — B.h named "the FR-19 / D.c CLI check story" as its refiner — into a `@runtime_checkable` Protocol carrying the `plugin` / `available` / `accelerators` subset both health reports share and the renderer reads; narrowed the C.b registration test's field access via `isinstance(report, PyTorchHealthReport)` accordingly.)
- [x] Exit non-zero if any required dep is missing or any plugin's `health_check` reports an unrecoverable error. (`ok = all(report.available)`; a discovered plugin whose extras aren't installed reports `available=False` → `run()` returns 1. CPU-only is **not** a failure — empty accelerator set renders as `—` informationally, per the FR-19 edge case + QR-5. Version detail harvested generically from each report's `*_version` fields, so heterogeneous `PyTorchHealthReport` / `SklearnHealthReport` shapes render through one path.)
- [x] CLI smoke test. ([tests/cli/test_check_cmd.py](../../tests/cli/test_check_cmd.py): 10 tests — `check_environment` (python/version probe, ok-when-all-available, not-ok-when-any-unavailable via monkeypatched `discover_plugins`), `render_check` (healthy + unhealthy), `run()` exit-code contract, and end-to-end `CliRunner` smokes for both healthy→0 and unavailable→1 plus a no-monkeypatch real-environment smoke. Fakes drive plugin availability so the exit code is deterministic regardless of whether the `[pytorch]` extra is installed in the running env.)
- [x] Verify: `pyve run modelfoundry check` works on the test machine. (Full `smoke-pytorch` env: pytorch + sklearn both `✓ available` (accelerators `cpu, mps`), `✓ environment healthy`, exit 0. Torch-less utility `root` env: pytorch `✗ unavailable`, `✗ environment unhealthy: 1 plugin(s) unavailable (pytorch)`, exit 1 — correct FR-19 extras-missing behavior, not a defect. Full suite **418 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (96 files).)

### Story D.d: `status` command [Done]

`features.md` FR-16.

- [x] Create `src/modelfoundry/cli/commands/status_cmd.py`: takes a recipe path; resolves cache key; if instance exists, loads manifest + renders summary table (plugin, plugin_version, schema_version, recipe_hash, bound_data_instance, seed, variant, cache hit, materialize timestamp, elapsed seconds, primary metric, expectations passed/failed counts). If absent, reports "not materialized" with expected path. (`run(recipe, config)` binds via `ModelFoundry.from_recipe(...)` and delegates to `mf.status()` — the C.p verb that resolves the cache key + loads the manifest. `render_status(recipe, status, *, primary_metric)` draws the two-column field/value table. **Primary-metric note:** the `Manifest` stores `evaluation` as `{split: {metric: value}}` but not the *name* of the primary metric — that lives on the recipe — so `run()` threads `mf.recipe.Evaluation.primary_metric` into the renderer, which looks the value up per eval split (`accuracy = 0.9123 (val)`). Expectations counted from `manifest.output_expectations`; `is_partial` surfaces a `failed_stage` row (FR-16 partial-state edge case) using the existing manifest fields. `status` is read-only → always exits 0; the not-materialized branch is a successful query, not an error.)
- [x] CLI smoke test against a fixture instance. ([tests/cli/test_status_cmd.py](../../tests/cli/test_status_cmd.py): 11 tests — `render_status` over an in-memory `Manifest` (summary fields, primary-metric name+value, passed/failed counts, variant placeholder, partial flag, not-materialized path), `run()` exit-0 for both materialized + not-materialized, and end-to-end `CliRunner` smokes. The materialized CLI smoke writes a **real** `Manifest` to disk and renders it back through the live command path; binding is monkeypatched via `from_recipe` because DataRefinery resolution hashes the recipe's declared *source inputs* (must be present on-host) and a full materialize is far too slow for a smoke — the real bind+status path is covered by `tests/integration/test_modelfoundry_api.py::test_verbs_status_report_check_clean`.)
- [x] Verify: `pyve run modelfoundry status <recipe>` works. (Ran `modelfoundry status recipes/cifar10_resnet20.yml` in `smoke-pytorch`: live DR-1 binding resolved + MF cache key computed + correctly reported `✗ not materialized` with the expected `models/instances/ca29ed58e9d9637d/e30b63b314af70ad/20260613` path, exit 0 — proves the full recipe-load → bind → key-resolve → render path. Full suite **429 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (98 files).)

### Story D.e: `materialize` command [Done]

`features.md` FR-3.

**Scope decision (2026-06-14):** the per-epoch / per-trial progress rendering has no existing seam (the runner only emits structured stage logs; the trainer/optimization are opaque and emit nothing to stdout). Per developer choice, D.e ships the verb + a **stage-level** progress seam + the reusable fd-suppression utility; the deep in-trainer per-epoch tables and per-trial Optuna bars are deferred to **Story D.e.1**.

- [x] Create `src/modelfoundry/cli/commands/materialize_cmd.py`: takes a recipe path + `--variant` + `--seed` + `--overwrite`; calls `ModelFoundry.from_recipe(...).materialize(...)`; ~~streams per-epoch `rich` progress tables during Training, per-trial progress bars during Optimization (with fd-level suppression for trial > 0)~~ → **stage-level** progress (see scope note; per-epoch/per-trial deferred to D.e.1); prints final summary on success; non-zero exit on failure. (`--overwrite` threads through `RuntimeConfig.overwrite` — the C.o runner already trashes the existing instance from `config.overwrite` (runner.py L75), so no `materialize(overwrite=...)` arg was needed; the story's phrasing predated that wiring. `--variant`/`--seed` go to `from_recipe`. Added a rendering-agnostic `StageObserver` Protocol + reusable `suppress_fd_output` (`os.dup2` fd 1/2) context manager in [pipeline/progress.py](../../src/modelfoundry/pipeline/progress.py); the runner's `_stage`/new `_skip_stage` invoke the observer (start/done/skipped); `ModelFoundry.materialize(*, stage_observer=None)` threads it through. The CLI's `RichStageProgress` renders one line per stage; `render_summary` draws the success panel (instance path, plugin, recipe hash, seed, variant, elapsed, primary metric, expectations, optimization). Materialize failures propagate to `cli.app`'s exit-code mapping — ExpectationError→1, MaterializeError→2.)
- [x] CLI smoke test against a tiny recipe + synthetic DataRefinery fixture (3-epoch, 2-trial); assert exit code, summary contents, instance directory created. ([tests/cli/test_materialize_cmd.py](../../tests/cli/test_materialize_cmd.py): 13 tests. The end-to-end test does a **real 3-epoch + 2-trial materialize** on a synthesized DR fixture through `materialize_cmd.run` (binding monkeypatched via `from_recipe` because DR path-resolution needs real source inputs on-host) and asserts exit 0, `materialized` summary, `training` stage progress, and `instance_dir` created + promoted. Fast unit tests cover `RichStageProgress` (start/done/skipped), `suppress_fd_output` (fd-1 silenced inside, restored after), `render_summary`, the runner's `StageObserver` seam, and `run()` delegation/exit/flag-threading (`--overwrite`→config, variant/seed→from_recipe, observer attached only when `progress=True`).)
- [x] Verify: `pyve run modelfoundry materialize <fixture-recipe>` works end-to-end. (`modelfoundry materialize --help` renders the recipe arg + `--variant`/`--seed`/`--overwrite`/`--progress/--no-progress` flags. The full end-to-end materialize is exercised by the automated test above — a quick CLI-binary run isn't possible because the only path-resolvable on-host DR instance is the full CIFAR-10 deliverable, whose ResNet-20 training is far too slow for a one-off check. Full suite **442 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (101 files).)

Out of scope (deferred to **Story D.e.1**):
- Per-epoch `rich` progress tables rendered *inside* the PyTorch trainer during Training.
- Per-trial Optuna progress bars during Optimization, with fd-level suppression (`suppress_fd_output`) for trial > 0 and trial 0 printing normally.
- The `progress`-flag plumbing through the `Plugin` Protocol's `run_training` / `run_optimization` that the above requires (the D.e seam stops at stage granularity in the runner).

### Story D.e.1: Per-epoch / per-trial materialize progress [Done]

`features.md` FR-3 follow-up; `tech-spec.md` § "User-facing output" + § "Optimization sub-process suppression". Realizes the per-epoch / per-trial progress rendering deferred from D.e — plugin-internal work touching the C.h trainer + C.i optimization. Builds on D.e's `StageObserver` seam and `suppress_fd_output` utility. No version bump (Phase D bundles into D.i v0.5.0).

- [x] Extend the `Plugin` Protocol's `run_training` / `run_optimization` (`plugins/base.py`) with an opt-in `progress` hook (a `bool` or an epoch/trial callback) so the runner can pass progress intent down per `tech-spec.md` § "Progress is opt-in via a `progress: bool` argument". (Chose the **callback object** form over a bare `bool` — task 4 wanted the CLI's `RichStageProgress` console reused, which a bool can't carry. Added a `ProgressReporter` Protocol in [pipeline/progress.py](../../src/modelfoundry/pipeline/progress.py) — `on_epoch(epoch, record)` / `on_trial_start(trial)` / `on_trial_done(trial, value)` — and a keyword-only `progress: ProgressReporter | None = None` on both Protocol methods + both plugins' impls. sklearn accepts it for conformance and ignores it — one `.fit()`, no epochs.)
- [x] PyTorch trainer (`plugins/pytorch/trainer.py`): render a per-epoch `rich` table (epoch, train/val loss, monitored metric) when progress is enabled. (Trainer calls `progress.on_epoch(epoch, record)` each epoch — independent of the existing Optuna `epoch_callback`; the `record` already carries `train_loss` / `val_loss` / `val_accuracy` / `learning_rate`. The `rich` rendering lives in the CLI's `RichStageProgress.on_epoch` so the trainer stays rich-free.)
- [x] PyTorch optimization (`plugins/pytorch/optimization.py`): render a per-trial `rich` progress bar; wrap trials > 0 in `pipeline.progress.suppress_fd_output` (trial 0 prints normally so the user can verify the recipe-defaults baseline trains correctly). (`_make_objective` fires `on_trial_start`/`on_trial_done` around each trial and wraps the inner `run_training` in `suppress_fd_output()` when `progress is not None and trial.number > 0` (else `nullcontext`). The inner trial training is deliberately called with **no** `progress` reporter so per-epoch rows don't drown the per-trial view.)
- [x] Thread the progress intent from `materialize_cmd` → `ModelFoundry.materialize` → `MaterializeRunner` → plugin, reusing D.e's `RichStageProgress` console. (Zero change to `materialize_cmd.run` — it already passes `RichStageProgress` as `stage_observer`. `RichStageProgress` now implements **both** `StageObserver` and `ProgressReporter`; the runner derives `progress = self.observer if isinstance(self.observer, ProgressReporter) else None` and forwards it to the Optimization + final Training stages. A library caller passing a bare `StageObserver` still gets stage-level progress only.)
- [x] Tests: trainer emits per-epoch rows when progress on (and is silent when off); optimization suppresses trial > 0 fd output while trial 0 prints; CLI smoke asserts per-epoch lines appear under `--progress`. ([tests/cli/test_materialize_cmd.py](../../tests/cli/test_materialize_cmd.py) grew to 18 tests: `RichStageProgress.on_epoch`/`on_trial_*` rendering (no torch); direct `run_training(progress=recorder)` → `epochs == [1,2,3]` + silent-without-progress; direct `run_optimization(progress=recorder)` → `trials_started/done == [0,1]`; and the existing real 3-epoch/2-trial e2e now also asserts `epoch` + `trial` appear in the streamed output. fd-suppression mechanics are pinned by D.e's standalone `suppress_fd_output` test.)
- [x] Verify: `pyve test --env smoke-pytorch` green; `ruff` + `mypy` clean. (Full suite **447 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (101 files). No import cycle from `plugins/base.py` → `pipeline/progress.py` — the latter is stdlib-only.)

### Story D.f: `report` command [Done]

`features.md` FR-18.

- [x] Create `src/modelfoundry/cli/commands/report_cmd.py`: takes an instance path; calls `ModelInstance.load(path).render_report()`; prints final path on success. (Operates on a self-contained instance dir — no recipe/binding. Resolves the plugin from the manifest via `discover_plugins(config.plugin_path)` so `--plugin-path` is honored, then `ModelInstance.load(path, plugin=…).render_report()` re-renders `report/` atomically and the command prints the `report/report.md` path. A path with no `manifest.json` raises `InstanceError` → exit 1; an undiscoverable manifest plugin raises `PluginError` → exit 2, both mapped by `cli.app`.)
- [x] CLI smoke test against a fixture instance. ([tests/cli/test_report_cmd.py](../../tests/cli/test_report_cmd.py): 5 tests. The fixture instance declares **no** `Visualizations`, so `rerender_report` never calls `plugin.render_visualization` — the whole path is torch-free (markdown re-render is pure pandas/string), and the fixture is hand-built (manifest + recipe + a stale `report.md`). Covers: `run()` re-renders + replaces the stale report + returns 0; `run()` on a non-instance path raises `InstanceError`; end-to-end `CliRunner` exit 0 + path printed; missing instance → exit 1; missing arg → usage error 2.)
- [x] Verify: `pyve run modelfoundry report <instance>` re-renders report/. (Exercised end-to-end via the `CliRunner` smoke; full suite **452 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (103 files).)

### Story D.g: `inspect` command [Done]

`features.md` FR-17.

- [x] Create `src/modelfoundry/cli/commands/inspect_cmd.py`: takes an instance path + `--view <name>`; calls `ModelInstance.load(path).inspect(view=...)`; renders the requested view (writes PNG to a temp file for PNG views and prints the path; renders a `rich` table for text views like `view_manifest`). (Added the FR-17 **behavior-2** on-demand path: `ModelInstance.inspect(*, view)` returns the `Manifest` for `view_manifest`/`manifest`, else dispatches the name as a plugin visualization op (`training_curves` / `optimization_history` / `confusion_matrix` / `calibration_curve` / `predictions_grid`) via `plugin.render_visualization` → PNG `bytes`. Unknown view → `InspectionError` (wraps the plugin's `PluginError`); no `recipe.yml` → `InspectionError`. The command resolves the plugin from the manifest honoring `--plugin-path`, writes PNG bytes to `mkdtemp()/<view>.png` and prints the path, or renders a two-column `rich` field/value table for the manifest. `InstanceError` (exit 1) for a non-instance path.)
- [x] CLI smoke test. ([tests/cli/test_inspect_cmd.py](../../tests/cli/test_inspect_cmd.py): 9 tests. `inspect()` unit (manifest view → `Manifest`; unknown view → `InspectionError`; PNG view → bytes with the PNG signature); `run()` (manifest → table; PNG → temp file exists + non-empty; non-instance → `InstanceError`); CLI (`view_manifest` exit 0; unknown view exit ≠ 0; missing arg → usage error 2). PNG tests `importorskip("matplotlib")` and use placeholder rendering — no torch / real training needed.)
- [x] Verify: `pyve run modelfoundry inspect <instance> --view training_curves` works. (End-to-end exercised via `CliRunner` + direct `run(view="training_curves")` against fixture instances — PNG written to a temp path, manifest rendered as a table. Full suite **461 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (105 files).)

Out of scope (recorded as the D.g.1 follow-up below):
- FR-17 **behavior 1** — the no-arg `inspect()` returning an `InspectionView` object with the six notebook-facing accessors (`view_training_curves()`, `view_confusion_matrix(split)`, `view_calibration(split)`, `view_predictions(split, n)`, `view_trials()`, `view_manifest()`) and the unfilled-stage `InspectionError` edge cases. Primarily an nbfoundry-consumer convenience, not exercised by the CLI verb.

### Story D.g.1: `InspectionView` accessor object (FR-17 behavior 1) [Done]

`features.md` FR-17 (behavior 1); consumer-facing exploration surface deferred from D.g. Builds on D.g's `ModelInstance.inspect(view=...)` on-demand renderer. No version bump (Phase D bundles into D.i v0.5.0).

- [x] Add `ModelInstance.inspect()` (no-arg) returning an `InspectionView` bound to the instance, with accessors `view_training_curves()`, `view_confusion_matrix(split)`, `view_calibration(split)`, `view_predictions(split, n)`, `view_trials()`, `view_manifest()` — each a thin wrapper over `inspect(view=...)` / the existing data accessors, threading the `split` / `n` params into the `VisualizationSpec`. (`inspect` now takes `view: str | None = None` with `@overload`s so `inspect()` types as `InspectionView` and `inspect(view=str)` as `bytes | Manifest` — the latter keeps D.g's `inspect_cmd` narrowing clean. Refactored D.g's single-view body into a shared `_render_view(view, **params)` that both `inspect(view=...)` and the PNG accessors call; the `split` param threads through `VisualizationSpec(op=…, split=…)` (extra="allow" → `_pick_split` reads `model_extra`). `InspectionView` is a frozen dataclass holding the instance.)
- [x] Raise `InspectionError` with a clear message when an accessor depends on an unfilled stage (e.g. `view_trials()` on an instance with no Optimization stage; partial-instance views per `is_partial`). (`view_trials()` raises when `instance.trials is None`; `view_predictions(split, n)` raises when predictions are absent or no rows match `split`; `view_confusion_matrix`/`view_calibration` raise when `split` is absent from `instance.evaluation`. These artifact-presence checks naturally cover partial instances — a stage that didn't run leaves its artifact absent — so no separate `is_partial` gate was needed. PNG views whose data is merely sparse still degrade to the renderer's placeholder, matching C.k behavior.)
- [x] Tests: each accessor returns the expected artifact / PNG; unfilled-stage accessors raise `InspectionError`; `view_predictions(split, n)` honors `n`. ([tests/unit/test_inspection_view.py](../../tests/unit/test_inspection_view.py): 11 tests. Data accessors (`view_manifest`/`view_trials`/`view_predictions`) are torch/matplotlib-free; the three PNG accessors `importorskip("matplotlib")` and assert the PNG signature. Fixture instance hand-built from artifact files (metrics.json + predictions/trials parquet) — no real training; toggles `with_eval`/`with_predictions`/`with_trials` to exercise the `InspectionError` paths.)
- [x] Verify: `pyve test --env smoke-pytorch` green; `ruff` + `mypy` clean. (Full suite **472 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (106 files).)

### Story D.h: `clean` command [Done]

`features.md` FR-20.

- [x] Create `src/modelfoundry/cli/commands/clean_cmd.py`: `--recipe-hash`, `--older-than`, `--failed`, `--orphans`, `--dry-run` selectors per `features.md` FR-20. (`run(config, *, recipe_hash, older_than, failed, orphans, dry_run)` validates the combo (`--orphans` requires `--older-than`; at least one selector required — both raise `CacheError` → exit 2), parses the duration, selects targets, and either reports (`--dry-run`) or removes them. "no matches" → exit 0 "nothing to clean"; a removal failure → exit 2 with the partial state reported, per the FR-20 edge case.)
- [x] `cache.cleaner` module implementation: `src/modelfoundry/cache/cleaner.py` with the selector logic. (`parse_duration("7d")` → `timedelta` (units `s/m/h/d/w`; invalid → `CacheError`); `select_targets(...)` enumerates promoted instances (`instances/<rh16>/<dh16>/<seed>/manifest.json`), temp dirs (`instances/.tmp/<run-id>/` ± `FAILED`), and trash (`.trash/<ts>/`), applying each active selector and unioning the results; `_prune_descendants` drops any target nested under another (so a `--recipe-hash` tree supersedes a per-instance `--older-than` hit). Age source: `manifest.created_at` for promoted instances (per spec), directory mtime for trash / orphan temp dirs. `remove_targets(..., dry_run=...)` deletes via `shutil.rmtree`, collecting per-dir failures into a `CleanResult`.)
- [x] CLI smoke tests for each selector. ([tests/unit/test_cache_cleaner.py](../../tests/unit/test_cache_cleaner.py): 20 tests — `parse_duration` units + invalid; each selector's target set (recipe-hash tree, old promoted, old trash, failed-only, orphan-only excluding failed/recent); dedup; dry-run-removes-nothing + real removal. [tests/cli/test_clean_cmd.py](../../tests/cli/test_clean_cmd.py): 9 tests — `run()` per selector + exit codes + validation raises, and `CliRunner` smokes (dry-run `--older-than`, `--failed`, no-selector errors). Note: `CliRunner` surfaces a raised `CacheError` as generic exit 1; the `CacheError`→2 mapping is covered by `exit_code_for` in test_app.py and confirmed manually below.)
- [x] Verify: `pyve run modelfoundry clean --dry-run --older-than 7d` works. (Manual end-to-end via the full env: empty cache → "nothing to clean" exit 0; `--failed --dry-run` → "would remove: …/failed-run (failed)" exit 0 (nothing removed); no-selector → "error: specify at least one selector…" exit **2** in the real CLI. Full suite **501 passed** in `smoke-pytorch`; `ruff check src tests` + `mypy src tests` clean (110 files).)

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
- [ ] `tests/plugin_contract/test_sklearn_baseline_contract.py`: the sklearn plugin registers the full `OperationSpec` set, satisfies the `Plugin` Protocol's runtime `isinstance` check, and materializes a small `MLPClassifier` recipe end-to-end (per C.m's promotion from stub to working baseline).
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

### Story F.b.1: Env-layout doc reconcile — B.o / B.p / `env-dependencies.md` repair [Planned]

The Pyve env topology was revamped (again) by the developer to a **venv**-based multi-env layout under `pyve.toml` (`pyve_schema = "3.0"`): a `purpose = "utility"` **`root`**, a light `default = true` **`testenv`** (ruff / mypy / pytest from `requirements-dev.txt`), a lazy **`smoke-pytorch`** carrying the full PyTorch closure (`-e .[pytorch]` from `tests/integration/env/pytorch.txt` — where the real test suite runs), lazy **`smoke-tensorflow`** / **`smoke-huggingface`** framework smokes, and a lazy **`typecheck`** env for `mypy --strict`. All are `backend = venv` — this **supersedes** B.o's two-micromamba design (utility root + conda testenv) and B.p's reconcile of it. `env-dependencies.md` §3–§5, the B.o / B.p story prose, and `tech-spec.md`'s env sections still describe the obsolete micromamba topology and actively mislead (flagged in the C.q.1 env note). Doc-only — rides the Phase F release; no version bump of its own.

- [ ] Rewrite [`env-dependencies.md`](env-dependencies.md) §3–§5 to the venv `root` / `testenv` + lazy `smoke-pytorch` / `smoke-tensorflow` / `smoke-huggingface` / `typecheck` topology as declared in `pyve.toml` (per-env `backend = venv`, `requirements`, `lazy` / `default` flags). Record **why venv** (every dep is a pip wheel on macOS arm64 — torch MPS, tf-macos/tf-metal, HF — so conda buys nothing, and the smoke envs stay isolated to dodge the Metal SIGFAULT) and the canonical commands: `pyve test --env smoke-pytorch` (the real suite — plain `pyve test` runs the light `testenv` and skips torch), `pyve env run testenv -- ruff …`, `pyve env run typecheck -- mypy …`.
- [ ] Reconcile [`tech-spec.md`](tech-spec.md) § Runtime & Tooling — rewrite the Environment-manager row + the Two-environment-install command block away from the B.o/B.p micromamba `pyve env init root`/`testenv` prose to the venv multi-env layout; point to `env-dependencies.md` as authoritative.
- [ ] Add a short "**superseded by F.b.1** — see `env-dependencies.md`" note to the B.o and B.p story bodies so they read as historical record, not current state.
- [ ] Sweep for residual obsolete references: no remaining "two micromamba envs", `.pyve/testenvs/`, `pyve testenv …`, or `manifest = "environment.yml"` test-env prose outside explicitly-historical context.
- [ ] Verify: no doc cross-reference points at the obsolete topology; `ruff check` (testenv) + `mypy src tests` (typecheck) still clean.

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
- **Additional sklearn baselines** — C.m ships a working `MLPClassifier` baseline (Subphase C-1); extend with RandomForest / GBM baselines for CIFAR-10 (reusing the C.f feature-flattening + normalization path).
- **Continued training** — `Training.persist_optimizer_state: bool = false` recipe field gated by a `schema_version` bump; the `Checkpoint` model's forward-extensible keys (`optimizer_state`, `scheduler_state`, `rng_state`, `training_step`) are populated; new `materialize --resume-from <checkpoint>` workflow. The Q16 foundation in B.k is what makes this a pure additive change with no public-API rework.
- **Tight-coupled DataRefinery binding (FR-26)** — `schema_version` bump that mixes the bound DataRefinery instance's `recipe_hash` into ModelFoundry's cache identity, so upstream re-materialization auto-invalidates downstream. Requires a documented migration of existing cached ModelInstances.
- **Marimo + IPython substrate-neutral smokes** — the Jupyter smoke in E.k is the canonical substrate-neutral test; Marimo headless and IPython REPL smokes extend the contract.
- **Parallel Optuna trials** — `n_jobs > 1` with a deterministic trial-ordering protocol on top of the parallel harness. Requires the determinism contract to extend cleanly.
- **Search-space op-choice dimensions** — a grouped/conditional Optuna search-space mechanism so optimizer (AdamW / SGD+momentum) and LR schedule (`reduce_on_plateau` / `cosine`) can be **genuine search dimensions** rather than `variants:`. The current flat `recipe.search_space.suggest_params` + per-op `extra="forbid"` param models can't carry op-conditional params: a single `Optimizer.schedule` block can't validate for both ops (`cosine` *requires* `T_max`, which `reduce_on_plateau` rejects), and SGD's `momentum` breaks an AdamW trial the same way. Likely an `optimizer`/`schedule` group categorical that swaps the whole sub-block as a unit (plus a default for `CosineParams.T_max`). A `plugins.pytorch.optimization` + `recipe.search_space` enhancement touching the determinism-sensitive trial path. Surfaced by the C.r CIFAR-10/ResNet-20 deliverable (R5), which ships these comparisons as `variants:` instead. Sibling to **Parallel Optuna trials** above.
- **`modelfoundry.toml` per-project config** — currently no per-project config file (recipe + CLI flags + env vars cover execution context). If recurring patterns emerge, a project config lands as its own FR.
- **Cross-platform first-class Linux** — currently Linux is best-effort pre-production; post-production gates require first-class status.
- **Codecov / Coveralls coverage upload** — deferred from Phase G; coverage produced locally via `pyve test --cov`.
- **GitHub branch protection** — explicitly out of scope for the pre-production series per CR-1.
- **Production-release ceremony** — when ModelFoundry transitions from pre-production to production (the `1.0.0` event), every cache-invalidating change becomes ceremonious per `project-essentials.md`; `OR-8` / `OR-9` / `OR-10` stability guarantees activate; `plan_production_phase` replaces `plan_phase` for adding new work.

**Forward-declared dependency contracts:**

- `docs/specs/modelfoundry/vendor-dependency-spec.md` for downstream consumers (a future `modelmetrics`, `modelmachine`, replay harness) — authored at the pre-production release, mirroring DataRefinery's vendor-dependency-spec discipline. Captures the on-disk `ModelInstance` layout + the in-memory `ModelInstance` API + schema-version coordination policy.
