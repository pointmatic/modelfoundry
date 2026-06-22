# tech-spec.md -- DataRefinery (Python 3.12.x)

This document defines **how** the `DataRefinery` project is built -- architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns.

For requirements and behavior, see [`features.md`](features.md). For motivation and scope, see [`concept.md`](concept.md). For the implementation plan, see [`stories.md`](stories.md). For project-specific must-know facts (workflow rules, architecture quirks, hidden coupling), see [`project-essentials.md`](project-essentials.md) — `plan_tech_spec` populates it after this document is approved. For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Runtime & Tooling

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12.x | Pinned via `asdf`/`pyve`. Use `python`, never `python3`, to honor the `asdf` shim. |
| Environment manager | `pyve` (venv backend) | Two environments: runtime in `.venv/`, dev tools (testenv) in `.pyve/envs/testenv/`. |
| Build backend | `hatchling` | Configured via `pyproject.toml`; no `setup.py`. |
| Package layout | `src/` layout (`src/datarefinery/...`) | Forces tests against the *installed* package, surfaces packaging bugs that flat layout hides. |
| Linter / formatter | `ruff` | Single tool for lint and format; replaces flake8/isort/black. |
| Type checker | `mypy --strict` | With pydantic v2 mypy plugin auto-loaded; `py.typed` marker shipped in package. |
| Test runner | `pytest` (+ `pytest-cov`, `hypothesis`) | Lives in the testenv (`pyve test`); not in the runtime venv. |
| Editable install | Testenv editable install required | Tests exercise CLI entry points; `pythonpath` alone does not register console scripts. |

**Canonical command forms** (developer-facing; the LLM uses `pyve run` wrappers when invoking from the Bash tool — see `project-essentials.md`):

```bash
project-guide mode plan_stories      # change mode after this spec is approved
pyve test                            # run the test suite
pyve env run ruff check src tests
pyve env run ruff format --check src tests
pyve env run mypy src tests
```

---

## Dependencies

### Runtime (required)

| Package | Purpose |
|---|---|
| `numpy` | Numerical primitives used throughout the pipeline (image arrays, statistics). |
| `pandas` | Tabular intermediate representation; manifest building. |
| `scipy` | Statistical operations referenced by transformations and reporting. |
| `scikit-learn` | Splitter implementations (stratified, key-based), encoders, normalizers. |
| `pyarrow` | Parquet I/O for image manifests, tabular caches, vector fitted-statistics. |
| `pyyaml` | Recipe parsing (loaded with `yaml.safe_load`). |
| `pydantic` (`>=2`) | Recipe model, manifest, drift schema, runtime config; provides canonical-form intermediate via `model_dump(mode="json")`. |
| `rich` | User-facing CLI output: progress bars, tables, color. |
| `typer` | CLI framework (built on click; migration path to raw click stays open). |
| `pillow` | Image decoding/encoding for the image_classification plugin. Stays in core because v1 ships the image plugin in-tree. |
| `matplotlib` | Renders the FR-VIZ visualizations (`pixel_distribution`, FR-VIZ-2/3/4). Stays in core because reporting-mode visualizations run at materialize time; gating behind an extra would surprise users whose recipes declare a visualization. |

### Optional extras

| Extra | Pulls In | Purpose |
|---|---|---|
| `[llm]` | `lmentry` | Optional LLM-enhancement layer in the `init` scaffolder (FR-17). DataRefinery never imports `lmentry` from the deterministic path. |
| `[corruptions]` | `scikit-image`, `opencv-python-headless` | Runtime backends for the vendored Hendrycks-Dietterich corruption module (`plugins.image_classification._corruptions`), consumed by the `imagecorruptions_apply` Generation op (FR-GEN-1). The corruption *vocabulary* is in-tree so recipe-time validation works without the extras; only execution requires them. |

### Development (`requirements-dev.txt`)

| Package | Purpose |
|---|---|
| `ruff` | Lint + format. |
| `mypy` | Strict type checking. |
| `pytest` | Test runner. |
| `pytest-cov` | Coverage reporting. |
| `hypothesis` | Property-based tests for cache-identity invariants and split determinism. |
| `types-pyyaml` | Type stubs for `pyyaml`. |
| `build` | `python -m build` for sdist + wheel. |

### System

None beyond Python 3.12.x and a POSIX-compatible filesystem (macOS first-class pre-prod; Linux best-effort pre-prod, first-class post-prod; Windows via WSL2). `os.replace` cross-device-rename limitation is documented in FR-5.

---

## Package Structure

```
src/datarefinery/
  __init__.py                # public API: DataRefinery, Instance, materialize, __version__
  __main__.py                # `python -m datarefinery` -> cli.app:app
  py.typed                   # PEP 561 marker (ships in wheel)
  logging.py                 # JSON formatter + get_logger() helper
  cli/
    __init__.py
    app.py                   # root typer.Typer instance, shared options, exit-code mapping
    commands/
      __init__.py
      init_cmd.py            # `init` verb
      validate_cmd.py        # `validate` verb
      check_cmd.py           # `check` verb
      status_cmd.py          # `status` verb
      materialize_cmd.py     # `materialize` verb
      report_cmd.py          # `report` verb
      inspect_cmd.py         # `inspect` verb
      clean_cmd.py           # `clean` verb
  core/
    __init__.py
    datarefinery.py          # DataRefinery class (entry-point class for library callers)
    instance.py              # Instance dataclass (loaded materialized artifacts)
    config.py                # RuntimeConfig (cache root, log level, plugin path, workers)
    errors.py                # exception hierarchy
  recipe/
    __init__.py
    models.py                # pydantic v2 Recipe model + per-section models
    loader.py                # FR-1 load + schema-version gate
    validator.py             # FR-2 enumerated checks 1–23
    canonical.py             # JSON-canonical bytes for cache identity (FR-4)
    overlays.py              # FR-14 recipe overlays (J.n.5; was variants.py)
  cache/
    __init__.py
    identity.py              # SHA-256 over canonical recipe + raw inputs + seed
    layout.py                # CachePaths helpers under <cache-root>
    atomic.py                # temp-then-promote (os.replace), FAILED marker
    cleaner.py               # FR-21 selectors, listing, removal
  pipeline/
    __init__.py
    runner.py                # PipelineRunner: stage sequencing
    inputs.py                # disk-backed input loader (FR-3): image_folder + image_flat with label_from join
    fitted_stats.py          # FR-6 persistence (JSON for scalars, parquet for vectors)
    contracts.py             # FR-23 InputContracts / OutputExpectations evaluation
    workers.py               # opt-in ProcessPoolExecutor wrapper with deterministic seeding (per-record + per-record-variant)
    stages/
      __init__.py
      filters.py             # FR-8
      generation.py          # FR-9
      splits.py              # FR-7
      transformations.py     # FR-10 (incl. fit-on-train)
      augmentations.py       # FR-11 lazy policy capture + aggressive variant realization
      featurizations.py      # FR-12 (also drives derived labels via FR-22)
      visualizations.py      # FR-13
  reporting/
    __init__.py
    report.py                # report.md renderer
    drift.py                 # drift.json schema + writer (placeholder v1)
    visualizations.py        # reporting-mode rendering (writes to report/visualizations/)
  plugins/
    __init__.py
    base.py                  # Plugin protocol/ABC + OperationSpec
    discovery.py             # entry-point + plugin-path discovery
    image_classification/
      __init__.py
      plugin.py              # full v1 implementation
      operations/            # resize, normalize, augment, etc.
      filters_sample_per_class.py   # FR-FILTER-1 (Story H.j)
      filters_sample_per_class_fractional.py  # FR-FILTER-2 (Story H.k)
      filters_stratified_sampling.py  # shared helper for the two stratified-sampling ops
      filters_drop_by_label.py      # FR-FILTER-3 (Story H.l)
      _corruptions.py               # FR-GEN-1: vendored Hendrycks-Dietterich corruptions (Story H.m.1)
      _corruption_data/             # vendored frost textures + upstream attribution NOTICE
      _corruption_names.py          # FR-GEN-1: dependency-free corruption vocabulary (Story H.m.2)
      generation_imagecorruptions.py # FR-GEN-1: `imagecorruptions_apply` Generation op (Story H.m.2)
      augmentations/                # FR-11 aggressive-mode realizer scaffolding (Story H.p)
        __init__.py
        _realizer.py                # per_variant_seed + emit_variants helpers; Realizer callable type
        random_crop.py              # FR-AUG-1 `random_crop` op + RandomCropParams (Story H.q)
        horizontal_flip.py          # FR-AUG-2 `horizontal_flip` op + HorizontalFlipParams (Story H.q)
        color_jitter.py             # FR-AUG-3 `color_jitter` op + ColorJitterParams (Story H.r)
        random_erasing.py           # FR-AUG-4 `random_erasing` op + RandomErasingParams (Story H.r)
      visualizations/               # FR-VIZ matplotlib-backed visualizations (Stories H.t-H.w)
        __init__.py
        _render.py                  # shared matplotlib helpers (deterministic DPI, PNG encoding)
        pixel_distribution.py       # FR-VIZ-1 `pixel_distribution` op + PixelDistributionParams (Story H.t)
        augmented_sample_grid.py    # FR-VIZ-2 `augmented_sample_grid` op + AugmentedSampleGridParams (Story H.u)
        corruption_severity_grid.py # FR-VIZ-3 `corruption_severity_grid` op + CorruptionSeverityGridParams (Story H.v); lazy-imports [corruptions] backend
        severity_ladder.py          # FR-VIZ-4 `severity_ladder` op + SeverityLadderParams (Story H.w); single-corruption complement to FR-VIZ-3
    tabular/
      __init__.py
      plugin.py              # stub: section list + operation outline only
    text/
      __init__.py
      plugin.py              # stub: section list + operation outline only
  scaffolder/
    __init__.py
    init.py                  # FR-17 deterministic image-classification scaffolder
    llm.py                   # FR-17 optional lmentry enhancement (lazy import)
tests/
  unit/                      # pure-function tests (loader, canonical, identity, splits…)
  integration/               # end-to-end materialize on synthesized fixture
  cli/                       # CLI smoke per verb
  plugin_contract/           # every plugin asserts its declared schema
  fixtures/                  # synthesized CIFAR-10-shaped fixture builder
  conftest.py
docs/
  specs/                     # concept.md, features.md, tech-spec.md, stories.md, project-essentials.md
  project-guide/             # rendered go.md and bundled artifact templates
.github/workflows/
  ci.yml                     # ruff + mypy --strict + pytest on PRs and main
  publish.yml                # PyPI Trusted Publishing on tagged releases
pyproject.toml               # package metadata, deps, entry points, tool configs
requirements-dev.txt         # dev tool pinset for testenv
pyve.toml                    # pyve project config (venv backend, root + testenv envs)
.tool-versions               # asdf Python pin (3.12.x)
LICENSE                      # Apache-2.0
README.md
```

---

## Filename Conventions

| File Type | Convention | Examples |
|-----------|------------|----------|
| Documentation (Markdown) | Hyphens | `tech-spec.md`, `project-essentials.md` |
| Workflow files | Hyphens | `publish.yml`, `ci.yml` |
| Python modules | Underscores (PEP 8) | `validator.py`, `image_classification/plugin.py` |
| Python packages | Underscores (PEP 8) | `datarefinery/`, `image_classification/` |
| Configuration files | Hyphens or dots | `pyproject.toml`, `requirements-dev.txt`, `.gitignore` |

CLI command modules use a `_cmd.py` suffix (`materialize_cmd.py`) so the verb name `materialize` does not collide with the Python keyword-adjacent identifiers and stays readable in import paths.

---

## Key Component Design

### `DataRefinery` (core/datarefinery.py)

Library entry point. Construction loads + validates the recipe once; verbs are methods that share that state. CLI commands are thin typer wrappers.

```python
class DataRefinery:
    @classmethod
    def from_recipe(
        cls,
        recipe_path: pathlib.Path,
        config: RuntimeConfig | None = None,
        overlays: Sequence[str] | None = None,
        seed: int | None = None,
    ) -> "DataRefinery": ...

    def validate(self) -> ValidationReport: ...      # FR-2
    def materialize(self) -> Instance: ...           # FR-3
    def status(self) -> StatusReport: ...            # FR-19
    def inspect(self, view: str | None = None) -> InspectionView: ...  # FR-20
    def report(self) -> Instance: ...                # FR-15 re-render
    def clean(self, selector: CleanSelector) -> CleanReport: ...       # FR-21
    @staticmethod
    def check(config: RuntimeConfig | None = None) -> CheckReport: ... # FR-18

    @property
    def recipe(self) -> Recipe: ...
    @property
    def cache_key(self) -> CacheKey: ...
```

Top-level convenience for one-shot scripters:

```python
def materialize(
    recipe_path: pathlib.Path,
    *,
    config: RuntimeConfig | None = None,
    overlays: Sequence[str] | None = None,
    seed: int | None = None,
) -> Instance:
    return DataRefinery.from_recipe(recipe_path, config, overlays, seed).materialize()
```

### `Instance` (core/instance.py)

Loaded materialized artifacts. Dataclass-style (not pydantic) since it represents on-disk state.

```python
@dataclasses.dataclass(frozen=True)
class Instance:
    path: pathlib.Path                         # the instance directory
    manifest: Manifest                         # parsed manifest.json
    recipe: Recipe                             # canonicalized recipe used
    fitted_statistics: FittedStatistics        # lazy accessor
    report_path: pathlib.Path
    is_partial: bool                           # True when loaded from a FAILED temp dir

    @classmethod
    def load(cls, path: pathlib.Path) -> "Instance": ...
    def render_report(self) -> None: ...
```

### `recipe.loader` (FR-1)

```python
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1, 2})
LATEST_SCHEMA_VERSION: int = 2

def load(path: pathlib.Path) -> Recipe:
    """Parse YAML, gate on schema_version, apply registered migrations
    from the loaded version to LATEST_SCHEMA_VERSION, return validated
    pydantic Recipe (v2 shape)."""
```

Edge cases mapped to features.md FR-1:
- Missing `schema_version` -> `RecipeError` naming the missing field.
- Unrecognized version -> `RecipeError` listing supported versions and migration path.
- Malformed YAML -> `RecipeError` wrapping `yaml.YAMLError` with line/column.
- Unknown top-level keys -> warning logged + recorded in the validation report (not a hard error per FR-1's "warning" treatment); v1 surfaces these in `validate` output.

### `recipe.migrations` (Phase I bundle 4 — Stories I.x.1 / I.x.2 / I.x.3)

```python
migrations: dict[tuple[int, int], Callable[[dict[str, Any]], dict[str, Any]]] = {
    (1, 2): v1_to_v2,   # composed chain
}
```

Each callable rewrites a recipe dict from one `schema_version` to the next, executed by the loader before pydantic validation. The chain for `(1, 2)` is the composition of `filters_reshape_v1_to_v2` (G15 / Story I.x.1 — lifts `FilterOp.predicate.op` and `FilterOp.predicate.seed` to top-level fields, renames the remaining keys to `params`), `generation_reshape_v1_to_v2` (G12 / Story I.x.2 — lifts `op` to top level from `name` (or from `params.op` if a recipe used that workaround), renames `applies_at` → `splits`, lifts the `output_schema_matches_input: true` workaround to `output_schema: "matches_input"`), and `assertion_naming_v1_to_v2` (G16a / Story I.x.3 — rewrites `InputContracts`/`OutputExpectations` assertion `kind` per `{dtype → dtype_equals, range → value_range, record_count → record_count_in_range}`; `required_field` and `distributional` unchanged). Each step is idempotent on already-v2 input so the chain remains robust under partial application.

### `recipe.validator` (FR-2)

Each of the 22 enumerated checks from features.md becomes a function in `validator.py` named `check_NN_<descriptor>`, returning a `CheckResult`. `validate()` runs them all and returns a `ValidationReport` listing every result; never short-circuits.

```python
def validate(recipe: Recipe, plugin: Plugin) -> ValidationReport: ...
```

### `recipe.canonical` (FR-4)

```python
def to_canonical_bytes(recipe: Recipe) -> bytes:
    """Pydantic model -> dict via model_dump(mode='json') -> json.dumps with
    sort_keys=True, separators=(',', ':'), ensure_ascii=False -> UTF-8 bytes."""
```

Why this is sufficient: the pydantic model is the recipe's *meaning* — defaults filled, aliases resolved, types coerced. Whitespace, comments, key order, and quote style are gone after parsing. JSON's canonical form has a much smaller surface than YAML's, and stdlib `json.dumps(sort_keys=True)` is deterministic for the value types pydantic emits in `mode="json"` (str, int, float, bool, None, list, dict).

**Subtlety to enforce in code review:** any change to a pydantic field default that affects semantics silently invalidates every existing cache. Pre-production, that's tolerable (features.md already says upgrades may invalidate). Post-production, default changes that affect semantics MUST go through a `schema_version` bump with a migration in `recipe.loader`. A unit test pins the canonical hash for a representative fixture recipe; bumping the test value requires a deliberate review.

> **Superseded for cache identity — segmented hash (Story J.n.3).** `to_canonical_bytes` still exists as the flat full-recipe dump, but the **authoritative cache identity is now `recipe.segments.recipe_identity_hash`** (the segmented join below). The "field-default silently invalidates every cache" subtlety is further dissolved by the **no-implicit-defaults** rollout (J.n.4); see the module below.

### `recipe.segments` (Story J.n.2 infra → J.n.3 authoritative)

```python
SEGMENT_ORDER = ("core", "plugin", "overlays", "extensions")
EMPTY_MARKER: bytes              # fixed 32-byte stand-in for an empty/absent segment
RECIPE_FIELD_SEGMENTS: dict[str, str]    # declarative field→segment map (CI-guarded for completeness)
segment_digest(value) -> bytes   # SHA-256 of sorted-compact JSON, or EMPTY_MARKER if empty
join_stable(digests) -> bytes    # b"\x1f".join(digests) — the stable canonical join
segments_of(recipe) -> dict      # partition the flat recipe into the four segments (J.n.3)
recipe_identity_hash(recipe) -> str      # AUTHORITATIVE cache identity (J.n.3)
prefix_hash(digests, upto) -> str        # cumulative-prefix hook for the deferred vertical axis (Q8)
```

The segmented hasher composes the recipe hash from independent per-segment digests, so an empty segment contributes a fixed nothing (additive) and a change to one segment cannot move another's digest (scoped invalidation — design Q1/Q3). Per-segment version constants (`CORE_SCHEMA_VERSION`, `PLUGIN_IMAGE_SCHEMA_VERSION`, `PLUGIN_AUDIO_SCHEMA_VERSION`, `OVERLAYS_SCHEMA_VERSION`, `EXTENSIONS_SCHEMA_VERSION`) and a `(segment, from, to)`-keyed `SEGMENT_MIGRATIONS` registry govern per-segment evolution (design Q4).

**Internal partition (Option 1).** The author-facing recipe stays *flat*; `segments_of` partitions `recipe.model_dump(mode="json")` per `RECIPE_FIELD_SEGMENTS` — `core`/`plugin` are field-keyed; `overlays`/`extensions` are single-namespace segments contributed as their bare mapping (so an empty/stripped namespace collapses to `EMPTY_MARKER`). A CI guard (`test_every_recipe_field_is_assigned_exactly_one_segment`) pins that every `Recipe` field has exactly one segment, so a new section cannot be added without consciously choosing its segment.

**Authoritative since J.n.3.** Identity switched from the flat `sha256(to_canonical_bytes)` to `recipe_identity_hash` (the segmented join). That combiner change is a canonical-form algorithm change, so it rode a `schema_version` **2→3** bump (loader `(2, 3)` bootstrap migration; v3 = the segmented-canonical era). This was the **one-time pre-1.0 cache-invalidation event** — every existing instance re-materializes once; prohibitive post-1.0 (design § 8). The `test_canonical_hash_pin` gate now pins the segmented identity; a representative image/audio pin pair (`tests/integration/test_segmented_identity.py`) locks Finding A — `AudioSource.target_sample_rate` never enters an image recipe's canonical bytes.

**Per-segment versions + migrations (Story J.n.7).** Each segment evolves on its own version axis — there is **no global umbrella counter** (a global one would re-couple every segment's changes). The flat `schema_version` stays the **on-disk era marker** (Option 1 keeps the recipe flat — no on-disk segment-version block, so per-segment versioning adds *no* new invalidation); `recipe.segments` carries the structural era-detection table:

```python
SEGMENT_VERSION_KEYS = ("core", "plugin:image", "plugin:audio", "overlays", "extensions")
SCHEMA_ERA_SEGMENT_VERSIONS: dict[int, dict[str, int]]   # flat schema_version → per-segment versions
current_segment_versions() -> dict[str, int]             # what this build is at (the constants)
apply_segment_migrations(flat, from_versions, to_versions) -> dict
```

On the loader read path, once the flat `(int, int)` chain has lifted a recipe to the segmented era, `apply_segment_migrations` replays the registered `SEGMENT_MIGRATIONS[(segment, v, v+1)]` steps to bring each segment from its era version up to `current_segment_versions()`. A `("core", …)` migration rewrites the core fields; a `("plugin:image", …)` migration touches the plugin fields only for an image-family recipe (Finding A — an audio bump never rewrites an image recipe, and vice-versa). **While every segment sits at the current era (the steady state for the entire pre-1.0 lifetime so far), the dispatch is an exact pass-through** — the read path cannot perturb canonical bytes while the registry is dormant. A segment-version bump without a registered migration is a hard load-time error, routing the author to the cache-identity ceremony.

**Pin-test discipline.** Isolation is *enforced, not asserted*. `tests/unit/test_segment_pin_hashes.py` pins each segment's digest for a representative image and audio fixture; an unexpected move of any single segment's digest is a blocking CI failure that forces a conscious per-segment version bump + migration. The empty-`overlays`/`extensions` digests are pinned to `EMPTY_MARKER`, so the J.n.5/J.n.6 mechanisms can never retroactively perturb a recipe that doesn't use them. The no-implicit-defaults guard (`tests/unit/test_no_implicit_defaults.py`, J.n.4) fails CI if any `ParameterSpec` reintroduces a `default`. (The Q8 vertical-axis stage-boundary pins are deliberately *not* implemented — Q8 declined for this bundle; `prefix_hash` keeps them adoptable later without a combiner redesign.)

### `recipe.overlays` (FR-14)

```python
def apply_overlays(recipe: Recipe, names: Sequence[str] | None) -> Recipe: ...
```

Overlays (Story J.n.5; the former `variants`) are applied **before** canonicalization in selection order, last-writer-wins per section, so `cache_key` reflects the resolved recipe. Overlay *definitions* are stripped before hashing (`overlays={}`), so they never enter identity. The applied names are recorded in `manifest.overlays`.

### `recipe.seeds` (G11 — Story I.n)

```python
def derive_seed(master_seed: int, op_name: str) -> int:
    master_u64 = master_seed & ((1 << 64) - 1)
    digest = hashlib.sha256(
        master_u64.to_bytes(8, "big") + op_name.encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")

def resolve_seed(
    value: int | SeedDerivationSpec | None,
    *,
    master_seed: int,
    op_name: str,
) -> int | None: ...
```

`SeedDerivationSpec(from_="master")` is the only spec form in v1.

Pinned by `tests/unit/test_seeds.py::test_derive_seed_is_pinned_for_a_known_master_op_pair`:

    derive_seed(20260509, "filter_train_pool") == 15455891160210205198

**Cache identity participation.** The master seed (`Recipe.seed`) is part of canonical bytes — changing it changes the recipe hash, which is the intended propagation channel. The `SeedDerivationSpec` is also preserved in canonical bytes (the cached `recipe.json` records the YAML intent, not the resolved integer). Changing the derivation function itself is a deliberate cache invalidation: bump the pinned value, follow the post-prod ceremonious-invalidation rules.

### `cache.identity` (FR-4)

```python
@dataclasses.dataclass(frozen=True)
class CacheKey:
    recipe_hash: str         # full SHA-256 hex (64 chars)
    input_hash: str          # full SHA-256 hex
    seed: int

    @property
    def short(self) -> str:  # first 16 hex chars of recipe_hash, used in paths
        return self.recipe_hash[:16]

def compute_cache_key(
    recipe: Recipe, raw_inputs: list[InputSource], seed: int,
) -> CacheKey: ...
```

Algorithm:

1. `recipe_hash = sha256(to_canonical_bytes(recipe))`.
2. `input_hash = sha256(b"\n".join(sha256(content_of(src)) for src in sorted(raw_inputs)))` — sources sorted by declared name to stabilize order.
3. `CacheKey(recipe_hash, input_hash, seed)`.

Display truncation: cache directory paths use `recipe_hash[:16]` and `input_hash[:16]`. Full hashes are recorded in `manifest.json`.

### `cache.atomic` (FR-5)

```python
def atomic_promote(temp_dir: pathlib.Path, final_dir: pathlib.Path) -> None:
    """os.replace temp_dir -> final_dir. Raises if cross-device."""

def mark_failed(temp_dir: pathlib.Path, exc: BaseException, stage: str) -> None:
    """Write FAILED marker (JSON: stage, exc_type, message, traceback)."""
```

Same-filesystem requirement for temp and cache documented; `materialize` validates `<cache-root>/instances/.tmp/` and the final cache path live on the same device before starting work.

### `cache.sibling_stats` (FR-TRANS-1)

```python
def resolve_sibling_stats(
    cache_root: pathlib.Path,
    recipe_path: pathlib.Path,
    op_id: str,
    *,
    required_vectors: tuple[str, ...] = (),
    required_scalars: tuple[str, ...] = (),
) -> FittedStatistics: ...
```

Resolves the sibling materialized instance whose fitted statistics will be imported via FR-TRANS-1 `stats_from_instance`. Returns a read-only `FittedStatistics` handle rooted at the sibling's `fitted_statistics/` directory; callers read named stats through the standard `get_vector(op_id, name)` / `get_scalar(op_id, name)` interface.

**Lookup rules** (in order):

1. Load the sibling recipe at `recipe_path` via `recipe.loader.load`.
2. Compute its canonical SHA-256 hash via `recipe.canonical.to_canonical_bytes`.
3. Locate candidate promoted instances under `<cache_root>/instances/<recipe_hash16>/<input_hash16>/<seed>/` — every directory with a readable `manifest.json` is a candidate.
4. Pick the **most-recent** candidate by `Manifest.created_at` (path-lexicographic tiebreak, so the choice is deterministic when timestamps collide).
5. Verify `fitted_statistics/<op_id>/` exists.
6. If `required_vectors` / `required_scalars` are passed, verify each named stat is present and readable.

**Three explicit failure modes**, each a distinct subclass of `MaterializeError` so callers can branch on the failure shape:

- `SiblingInstanceNotFoundError` — no promoted instance found under the expected shard, or the shard exists but contains no readable manifest.
- `SiblingOpNotFoundError` — instance located, but `fitted_statistics/<op_id>/` is absent.
- `SiblingStatsIncompatibleError` — instance + op_id located, but a caller-required statistic is missing or unreadable (e.g., corrupt parquet, malformed `scalars.json`).

**Dispatcher-vs-op-handle decision.** The `stats_from_instance` branch lives in `pipeline.stages.transformations.apply_transformations` (the stage dispatcher), not inside the operation handle (`NormalizeOp`). When `op.params["stats_from_instance"]` is set, the dispatcher resolves the sibling, materializes the sibling's `fitted_statistics/<op_id>/` directory contents into a `FittedValues`, and feeds that into the op's `apply` phase — the op handle itself is unaware that the stats came from a sibling rather than a local fit. This keeps the dispatch generic: any future fit-on-train op (e.g., `mean_subtract`, encoder vocabularies) picks up sibling-import support automatically by declaring `stats_from_instance` in its `OperationSpec.parameters` — no per-op code changes.

**Read-through, not copy.** The resolver returns a `FittedStatistics` handle rooted at the *sibling's* `fitted_statistics/` directory; the consuming run reads through to those bytes without persisting them under its own `fitted_statistics/<op_id>/`. The consuming instance therefore has no fitted-statistics directory for ops that imported their stats — this is intentional, so the materialized output honestly reflects "stats are owned by the sibling," not "stats are owned here too" (see FR-6 Behavior #6).

### `pipeline.runner` (FR-3, FR-7..FR-13)

```python
class PipelineRunner:
    def __init__(self, recipe: Recipe, plugin: Plugin, config: RuntimeConfig, seed: int): ...
    def run(self, temp_dir: pathlib.Path) -> RunResult: ...
```

Stage sequence (recipe-declared order; default below):

1. Load raw inputs (`Input`).
2. Evaluate `InputContracts` -> abort early on failure (FR-23).
3. Apply pre-split `Filters` (FR-8).
4. Evaluate `Splits` (FR-7) -> partition records into named splits.
5. Apply `Generation` (FR-9; default train-only post-split).
6. Apply `Transformations` (FR-10), persisting fit-on-train statistics (FR-6).
7. Compute `Featurizations` (FR-12) and derived `Labels` (FR-22).
8. Note `Augmentations` (FR-11) policies in the recipe; applied at training time, not materialized.
9. Evaluate `OutputExpectations` (FR-23) -> abort on failure with FAILED marker.
10. Render `Visualizations` declared `reporting` (FR-13) into the report.
11. Write `manifest.json` (FR-3.7).

**Stage-order rationale: `Transformations` precedes `Featurizations`, and fit-on-train *feature* scaling is a Featurization.** Transformations operate on *raw* inputs (e.g. the image `normalize` op on pixels), so they run before features are derived. Consequently, **fit-on-train standardization of a *derived* feature lives in the `Featurizations` stage, not `Transformations`** — it must fit *after* the feature exists, and `Featurizations` is the only stage that runs after derivation *and* supports fit-on-train + statistics persistence (`pipeline.fitted_stats`, FR-6) + sibling import (FR-TRANS-1). This is a deliberate, cross-modality staple (FR-12 behavior #5): audio `audio_normalize` (per-mel-bin, reading `log_mel_spectrogram`'s `mel` output → writing `feature`) is the first instance; tabular column scaling and text embedding normalization will follow the same convention. Such an op reads a prior featurization's output field and writes a *new* field (raw and scaled both retained, satisfying the no-overwrite collision guard). The shared fit / parquet-wrap / `std == 0 → 1.0` zero-variance-guard machinery lives in `plugins.normalize_stats`, parameterized by the statistics axis (channel-last for images, mel-axis-0 for audio). A future *post-Featurization transform stage* (so "normalize is always a Transformation" generalizes) is a possible later evolution but is not in v1; the Featurization-as-scaler convention covers the need.

After each named stage emits its records, the runner invokes
`pipeline.sinks.execute_sinks(...)` (Story I.d) to dispatch any
recipe-declared `Sinks` whose `stage` matches `post_<StageName>`.
Sink output lands under the (temp) instance directory and therefore
participates in the existing temp-then-promote atomic write (FR-5);
the per-sink summary is captured into `manifest.sinks[<name>]`. The
closed stage vocabulary mirrors `STAGE_NAMES` (with a `post_` prefix)
and is shared with G7-era visualization-stage selection.

**`datarefinery export` dispatch table (Story I.f).** Out-of-band
sink execution against an already-materialized instance. The verb
locates the bound cache via a sinks-stripped recipe-hash lookup so a
user adding a sink to an existing recipe still resolves to the
original instance. Per-stage reconstruction:

| Sink `stage` | Strategy | Notes |
|---|---|---|
| `post_OutputExpectations`, `post_Visualizations` | Read cached JSONL directly. | Trivial — cached state equals sink-visible state. |
| `post_Generation` | Re-load input subset from disk; re-run the recipe's `Generation` ops over it; match outputs to cached records by `record_id`; stamp uint8 `image` back onto each cached record. | Byte-identical to the materialize-time sink output because per-record seeds (Story I.e) make Generation deterministic. |
| every other `post_<stage>` | Refuse with a pointer to re-materialize. | The cached state has moved past these intermediate forms; reconstructing them deterministically requires more metadata than v1 carries. |

Writes are atomic per file (temp-then-`os.replace`) so an
interrupted export leaves at most one ``.export_tmp_*`` directory
behind, never a half-written sink artifact under the promoted
instance path. The bound instance's `manifest.json` is left
unmodified — re-running sinks does NOT update `manifest.sinks`
entries, since the bound instance was materialized without the new
sink declarations.

**Per-record-seed persistence (Story I.e).** Every stochastic op
that derives a per-record seed stamps that seed onto each output
record under `<op_name>_seed`:

- `Generation`: `imagecorruptions_apply` stamps
  `<GenerationOp.name>_seed = per_record_seed(op.seed, input_record)`
  on every corrupted (and preserved-original) output. The Generation
  stage threads `op_name=op.name` through `_invoke_one` so the
  plugin op knows the recipe-defined name. Ops whose stochasticity
  is op-level (`duplicate_minority_class`) accept `op_name` for
  contract uniformity but do not stamp.
- `Augmentations` (aggressive mode): the realizer's `emit_variants`
  takes a `stamp_field` kwarg; the stage passes
  `stamp_field=f"{AugmentationOp.name}_seed"`. Each variant carries
  the per-variant seed used by its realizer. Lazy mode is unchanged
  (no per-record realization at this stage).

The stamped seed is the value used by the op's RNG, enabling
post-hoc reconstruction of stage outputs from the cached state
(the future `datarefinery export` verb, Story I.f). Stamping does
NOT perturb canonical recipe bytes — it perturbs only the cached
record bytes for any recipe with a stochastic op. This is a
one-time pre-prod cache invalidation event at v0.17.0.

Each stage uses `pipeline.workers.run_parallel(...)` when applicable and the runtime config opts in.

### `pipeline.workers` (FR-9)

```python
def run_parallel(
    seed: int,
    fn: Callable[[Record], Record],
    items: Iterable[Record],
    workers: int,
) -> Iterator[Record]:
    """ProcessPoolExecutor when workers > 1; serial otherwise. Each record
    is seeded deterministically from (seed, record_id) so worker order does
    not affect output."""
```

Determinism contract: the per-record seed is derived as `seed_for_record = sha256(seed.to_bytes(8, 'big') + record_id_bytes).digest()[:8]`, decoded as a 64-bit int. `record_id` is the record's stable identifier from the input manifest (filename for image inputs, primary key for tabular). Output is collected and reordered by `record_id` before downstream stages so the iteration order is fixed regardless of worker scheduling.

FR-11 aggressive-mode extension (Story H.p): when an `AugmentationOp` declares `materialization=aggressive`, each input record fans out into `expansion` variants, each seeded by `seed_for_variant = sha256(seed.to_bytes(8, 'big') + op_id.encode() + record_id_bytes + variant_index.to_bytes(4, 'big')).digest()[:8]`. The per-variant seed depends only on `(global_seed, op_id, record_id, variant_index)`, so worker scheduling does not perturb the per-variant outcome — the same byte-identical guarantee extends one level. The augmentations stage sorts variant records by `record_id` (zero-padded variant index suffix preserves numeric order under lexicographic sort) before yielding, mirroring the per-record reorder invariant.

### `pipeline.fitted_stats` (FR-6)

```python
class FittedStatistics:
    def __init__(self, root: pathlib.Path): ...
    def put_scalar(self, op_id: str, name: str, value: float | int | str | bool) -> None: ...
    def put_vector(self, op_id: str, name: str, table: pyarrow.Table) -> None: ...
    def get_scalar(self, op_id: str, name: str) -> Any: ...
    def get_vector(self, op_id: str, name: str) -> pyarrow.Table: ...
```

Layout under `<instance>/fitted_statistics/`:

```
fitted_statistics/
  <op_id>/
    scalars.json     # one JSON object per scalar stat
    <name>.parquet   # one parquet file per vector stat
```

Never opaque pickles.

### `pipeline.contracts` (FR-23)

```python
def evaluate_input_contracts(records: Iterable[Record], contracts: list[Contract]) -> ContractResult: ...
def evaluate_output_expectations(
    dataset: Mapping[str, Sequence[Record]] | Iterable[Record],
    expectations: list[Expectation],
    *, skip_missing_label_field: str | None = None,
) -> ContractResult: ...
```

`evaluate_output_expectations` accepts the post-Splits `Mapping[str, list[Record]]` keyed by split (a flat iterable is also accepted and routed as one implicit split for backward compatibility). `evaluate_input_contracts` stays flat — input contracts run pre-Splits.

**Assertion kinds.** Flat kinds (every record across all splits): `record_count_in_range`, `required_field`, `dtype_equals`, `value_range`, `distributional` (v1 placeholder), `count_by_field`, `count_by_fields`, `shape_equals`, `value_in_set`, `per_class_count_equals`. Per-split kinds (consult the split structure; `OutputExpectations` only): `split_record_counts`, `per_class_count_per_split` (rounding-tolerant via optional `tolerance`, default 1). G6 + G16b (Story I.o) added the per-split / per-class / structural kinds; G16a (Story I.x.3) renamed the three remaining bare-verb v1 kinds (`record_count` → `record_count_in_range`, `dtype` → `dtype_equals`, `range` → `value_range`) — v1 recipes are auto-migrated by `recipe.migrations.assertion_naming_v1_to_v2`.

Failures abort materialization; partial state lives under `.tmp/` with the standard FAILED marker.

### `plugins.base`

```python
class Plugin(typing.Protocol):
    name: str
    supported_sections: frozenset[str]
    supported_operations: dict[str, OperationSpec]   # operation name -> param schema
    schema_version: int

    def operation_factory(self, section: str, op_name: str) -> Operation: ...
    def is_stub(self) -> bool: ...
```

`OperationSpec` is a pydantic model declaring the operation's parameter schema, fit-on-train flag, applicable splits, and stage-applicability rules. `recipe.validator` consults these for check 18.

### `plugins.discovery`

```python
def discover_plugins(extra_paths: list[pathlib.Path] | None = None) -> dict[str, Plugin]:
    """Walk entry-point group 'datarefinery.plugins' and any extra_paths.
    Raises PluginError on duplicate names."""
```

In-tree plugins register through the same entry-point group declared in `pyproject.toml`; there is one code path. The `--plugin-path` CLI flag and `DATAREFINERY_PLUGIN_PATH` env var append to the discovery search path for development.

### `scaffolder.init` (FR-17)

```python
def scaffold_image_classification(
    input_path: pathlib.Path,
    output_path: pathlib.Path,
    *,
    enhance: bool = False,
) -> None:
    """Inspect raw image inputs, emit a starter recipe. enhance=True activates
    the optional lmentry layer (lazy import; raises if not installed)."""
```

v1 scaffolder supports `image_classification` only; `tabular` and `text` recipes are written by hand against the stub plugins. Within `image_classification`, the scaffolder emits `image_folder` recipes only; users of `image_flat` + `label_from` hand-author the recipe in v1. Extending the scaffolder to detect flat layouts and emit `image_flat` recipes is a follow-up story.

### `scaffolder.llm` (FR-17 optional layer)

`lmentry` is imported lazily inside `enhance()`; ImportError is converted to `PluginError` pointing at the `[llm]` extra. Offline detection lives here so the deterministic recipe is still emitted with a "enhancement skipped" note.

---

## Data Models

All recipe-related models are pydantic v2 with `model_config = ConfigDict(extra="forbid", frozen=True)` to make every field explicit and the model hashable for caching.

### Recipe model

The recipe is **flat** on disk (author-facing) but partitioned into four
identity segments — `core`, `plugin`, `overlays`, `extensions` — by
`recipe.segments.RECIPE_FIELD_SEGMENTS` (Story J.n.3, design Q1; see
[`recipe.segments`](#recipesegments-story-jn2-infra--jn3-authoritative)).
Segmentation is internal (Option 1): it drives hashing, per-segment
versioning, and validation dispatch — not author shape. `schema_version`
is `3` (the segmented-canonical era).

```python
class Recipe(pydantic.BaseModel):
    schema_version: int = 3                        # FR-1; gate-checked at load; v3 = segmented era
    plugin: str                                    # FR-16; resolved against discovery
    seed: int = 0                                  # default seed; CLI --seed overrides for ad-hoc runs
    Input: InputSection
    Output: OutputSection
    Labels: LabelsSection
    SampleData: SampleDataSection | None = None
    InputContracts: list[Contract] = []
    Filters: list[FilterOp] = []
    Generation: list[GenerationOp] = []
    Splits: SplitsSection
    Transformations: list[TransformationOp] = []
    Augmentations: list[AugmentationOp] = []
    Featurizations: list[FeaturizationOp] = []
    OutputExpectations: list[Expectation] = []
    Visualizations: list[VisualizationOp] = []
    Sinks: list[SinkOp] = []                       # Story I.d (disk-output declarations)
    variants: dict[str, dict[str, Any]] = {}       # FR-14
```

Per-section models (sketch; full field definitions land alongside the FR-1 implementation):

| Model | Required fields |
|---|---|
| `InputSection` | `sources: list[SerializeAsAny[InputSource]]` (each with `name`, `type`, `path`, optional `label_from: LabelFromSpec`, optional `partition: str`, `unlabeled: bool = False`). Model-level validation: `unlabeled=true` requires `partition` and forbids `label_from`. **Plugin source subclasses (Story J.n.3, design Q1):** `InputSource` is the open base; `AudioSource(InputSource)` adds `target_sample_rate: int`. A before-validator selects the subclass *presence-based* (a source declaring an audio-only field is an `AudioSource`), keeping `type` a free `str`. `SerializeAsAny` so a selected subclass serializes its own fields. The base's `extra="forbid"` structurally enforces Finding A: an image source cannot carry `target_sample_rate`, so audio fields never enter an image recipe's canonical bytes. |
| `LabelFromSpec` | `path: pathlib.Path`, `join: Literal["by_id", "by_row_order"]`, `header: list[str] | None`, `id_field: str | None`, `label_field: str`. When `header` is omitted the loader reads column names from the CSV's header row; when `header` is provided the file is treated as **headerless** and the recipe-supplied names *are* the column names (recipe-as-truth, no heuristic header detection). |
| `OutputSection` | `record_schema: dict[str, FieldSpec]` (field name -> dtype/shape) |
| `LabelsSection` | `field: str`, `source: LabelSource` (direct or derived; FR-22) |
| `SampleDataSection` | `selector: SampleSelector` (declarative subset of `Input`) |
| `Contract` / `Expectation` | `field: str | None`, `assertion: AssertionExpr`, `severity: Severity` |
| `FilterOp` | `name`, `op`, `params: dict[str, Any] = {}`, `stages`, `splits`, `seed: int \| SeedDerivationSpec \| None` (top-level; G15 / Story I.x.1 reshape — v1 nested all of these inside `predicate` and is auto-migrated by `recipe.migrations.filters_reshape_v1_to_v2`). Plugin-contributed sampling ops declare their own pydantic param model alongside the `OperationSpec` schema — `SamplePerClassParams` (`n_per_class: int > 0`, `label: str \| None`, `exclude_already_labeled: list[str] \| None`), `SamplePerClassFractionalParams` (`n_per_class_base: int > 0`, `fractions: dict[str, float]` each in `[0.0, 1.0]`, plus inherited `label` / `exclude_already_labeled`), and `DropByLabelParams` (`labels: list[str]`, non-empty) are validated inside the op via `model_validate(params)`; recipe-level validation still goes through the plugin's `OperationSpec` (check 18). |
| `GenerationOp` | `name`, `op`, `inputs`, `output_schema: dict[str, FieldSpec] \| Literal["matches_input"]`, `seed: int \| SeedDerivationSpec`, `splits: list[str] = ["train"]`, `params: dict[str, Any] = {}`, `replace_input_records: bool = False` (G12 / Story I.x.2 reshape — v1 left `op` implicit in `name`, called the splits field `applies_at`, and required an explicit dict for `output_schema`; auto-migrated by `recipe.migrations.generation_reshape_v1_to_v2`). The `"matches_input"` shorthand is expanded at materialize time by `pipeline.stages.generation._resolve_output_schema` to `Output.record_schema` plus any fields named in `params.tag_fields` (list or dict form). Plugin-contributed parameterized ops declare a pydantic param model — e.g., `ImageCorruptionsApplyParams` (`corruption_types: list[str]` non-empty, `severities: list[int]` each in `[1,5]`, `preserve_original: bool = False`, `tag_fields: list[str] \| dict[str, str]`) — validated inside the op via `model_validate(params)`. Recipe-level validation runs through the plugin's `OperationSpec` (check 18 covers Generation as well as Filters / Transformations / etc). |
| `SplitsSection` | `ratios: dict[str, float]` or `key_assignment: KeyAssignment`, `stratify_by: str | None`, `seed: int | None`, `class_balance: ClassBalanceStrategy | None`, `applies_to: str | None`. When `applies_to` is set, it names a single source-declared partition to sub-partition via `ratios`; sibling partitions are preserved verbatim. |
| `TransformationOp` | `name`, `op`, `params`, `fit_source: str | None`, `splits`. A fit-on-train op may set `params["stats_from_instance"]` (validated as `StatsFromInstanceSpec` with `recipe: str` + `op_id: str`) to import fitted statistics from a sibling materialized instance instead of fitting locally; `fit_source` and `stats_from_instance` are mutually exclusive (validator check 22). Resolution lives in `cache.sibling_stats.resolve_sibling_stats`; the apply path is wired into `pipeline.stages.transformations.apply_transformations` (the stage dispatcher), so any future fit-on-train op picks up sibling-import support by declaring `stats_from_instance` in its `OperationSpec`. |
| `AugmentationOp` | `name`, `op`, `params`, `splits` (validator rejects non-train), `seed`, `materialization: Literal["lazy", "aggressive"] = "lazy"`, `expansion: int = 1`. Model-level validator rejects `expansion < 1` and `expansion > 1 + materialization=lazy` — surfaced as `RecipeError` through the loader. Aggressive ops dispatch through a plugin-registered `Realizer` (see `plugins/image_classification/augmentations/_realizer.py`); per-variant seeding extends the FR-3 determinism contract with an `(op_id, variant_index)` coordinate. The `image_classification` plugin registers per-op pydantic param models — `RandomCropParams` (`size: int \| tuple[int, int]`, `padding: int = 0`, `padding_mode: Literal["reflect", "replicate", "zero", "constant"] = "reflect"`; Story H.q FR-AUG-1), `HorizontalFlipParams` (`p: float = 0.5` in `[0.0, 1.0]`; Story H.q FR-AUG-2), `ColorJitterParams` (`brightness`/`contrast`/`saturation` in `[0.0, 1.0]`, `hue` in `[0.0, 0.5]`; Story H.r FR-AUG-3), and `RandomErasingParams` (`p` in `[0.0, 1.0]`, `scale` and `ratio` as ordered float tuples; Story H.r FR-AUG-4) — validated inside each realizer via `model_validate(params)`. Recipe-level validation continues through the plugin's `OperationSpec` (check 18). |
| `FeaturizationOp` | `name`, `inputs`, `output_field`, `op`, `params`, `splits`, `fit_source: str | None` |
| `VisualizationOp` | `name`, `op`, `params`, `stage`, `mode: Literal["exploration", "reporting"]`. The plugin op handle's `render(...)` returns either `bytes` (single PNG, persisted as `<op.name>.png`) or `Mapping[str, bytes]` (one PNG per key, persisted as `<op.name>_<key>.png`); the runner / exploration renderer also pass an optional `recipe: Recipe \| None = None` kwarg consumed by policy-aware ops (introduced Stories H.t / H.u). The `image_classification` plugin registers per-op pydantic param models — `PixelDistributionParams` (`bins: int = 64`, `splits: list[str]`; Story H.t FR-VIZ-1), `AugmentedSampleGridParams` (`n_base: int`, `n_variants: int`, `seed: int \| None = None`; Story H.u FR-VIZ-2), `CorruptionSeverityGridParams` (`n_images: int`, `corruption_types: list[str]`, `severities: list[int]` each in `1..5`; Story H.v FR-VIZ-3), and `SeverityLadderParams` (`n_examples: int`, `corruption_type: str`; Story H.w FR-VIZ-4). Recipe-time vocabulary validation for the two corruption-aware ops uses the in-tree `_corruption_names.CORRUPTION_NAMES_ALL` (no `[corruptions]` extras required for validation; only for execution). |
| `SinkOp` | `name`, `stage: Literal["post_InputContracts", "post_Filters", "post_Splits", "post_Generation", "post_Transformations", "post_Featurizations", "post_Augmentations", "post_OutputExpectations", "post_Visualizations"]`, `splits: list[str] \| None`, `field: str`, `format: Literal["png_per_record"]`, `path_template: str`. Story I.d disk-output declaration. The path-template grammar (`{field}`, `{field\|stem/lower/upper/str}`, `{split}`) is parsed at validate time; templates that escape the instance directory (absolute or `..` traversal) are rejected. v1 ships one writer — `png_per_record` requires uint8 H×W×C (or H×W) on the named field and writes via `PIL.Image.fromarray`. Sink output participates in canonical recipe bytes (cache identity) and the existing temp-then-promote atomic write (FR-5); per-sink summaries land in `manifest.sinks[<name>]`. |

### Manifest

```python
class Manifest(pydantic.BaseModel):
    schema_version: int                # manifest schema, separate from recipe schema
    datarefinery_version: str
    plugin: str
    plugin_version: str
    recipe_hash: str                   # full SHA-256 hex
    input_hash: str                    # full SHA-256 hex
    seed: int
    overlays: list[str]                # manifest v2 (J.n.5); was `variant: str | None`
    created_at: datetime.datetime
    elapsed_seconds: float
    is_partial: bool
    failed_stage: str | None
    record_counts: dict[str, int]      # split name -> count
    warnings: list[Warning]
    sinks: dict[str, SinkManifestEntry] # Story I.d: per-sink stage/format/files_written/bytes_total/path_template_resolved_root
    sinks_skipped: dict[str, str]      # Story I.f.1: sinks whose host stage was not reached under partial --stage
    class_balance: str | dict | None   # Story I.s / G10: hint copied verbatim from Splits.class_balance
    sample: SampleManifestEntry | None # Story J.a / FR-J-1: SampleData runtime emission summary; None when no SampleData declared
    label_classes: list[Any] | None    # Story J.f / FR-J-2: canonical class set (distinct labels, sorted ascending); None when fully-unlabeled
```

### Drift schema (FR-15 placeholder for v1)

```python
class DriftSchema(pydantic.BaseModel):
    schema_version: int = 0            # placeholder; bumped to 1 at production release
    plugin: str
    splits: dict[str, SplitDriftRecord]
    feature_summary: dict[str, FeatureDriftRecord]
    notes: list[str] = []
```

`SplitDriftRecord` and `FeatureDriftRecord` are typed JSON shapes (record count, mean/std for numeric, top-N value frequencies for categorical) — concrete enough for DataMachine to begin coding against, documented as unstable until production release.

### RuntimeConfig

```python
class RuntimeConfig(pydantic.BaseModel):
    cache_root: pathlib.Path = pathlib.Path("data")
    log_level: str = "INFO"
    log_target: pathlib.Path | None = None         # None -> stderr
    plugin_path: list[pathlib.Path] = []
    workers: int = 1                               # 1 = serial; >1 enables ProcessPoolExecutor
```

CLI flags / env vars populate this object before `DataRefinery.from_recipe(...)`.

---

## Configuration

### Recipe sections recap

Required for every recipe: `schema_version`, `plugin`, `Input`, `Output`, `Labels`, `Splits`, `OutputExpectations`. Optional but commonly present: `InputContracts`, `Filters`, `Generation`, `Transformations`, `Augmentations`, `Featurizations`, `Visualizations`, `Sinks`, `SampleData`, `variants`.

Plugin-specific operation parameters live inside each operation's `params` field and are validated against the plugin's `OperationSpec` schemas (validator check 18).

### Configuration precedence

Highest wins:

1. **Recipe file** — authoritative for data-pipeline semantics.
2. **CLI flags** — execution context only (`--cache-root`, `--log-level`, `--plugin-path`, `--variant`, `--seed`, `--workers`).
3. **Environment variables** — same execution-context surface, lower precedence.

Recipe semantics never read from CLI/env. The only field where CLI flag overrides recipe is `--seed`, which is the documented ad-hoc-run case (and the override changes the cache identity, so a different instance is produced).

### Environment variables

| Variable | Maps to |
|---|---|
| `DATAREFINERY_CACHE_ROOT` | `--cache-root` |
| `DATAREFINERY_LOG_LEVEL` | `--log-level` |
| `DATAREFINERY_LOG_TARGET` | `--log-target` |
| `DATAREFINERY_PLUGIN_PATH` | `--plugin-path` (PATH-style, `:`-separated on POSIX) |
| `DATAREFINERY_WORKERS` | `--workers` |

### Cache layout

```
<cache-root>/                              # default: ./data/
├── raw/                                   # raw input cache (when materialized from external sources)
├── instances/
│   ├── <recipe-hash16>/
│   │   └── <input-hash16>/
│   │       └── <seed>/
│   │           ├── recipe.json                       # canonical post-loader form (the bytes hashed for the cache key)
│   │           ├── dataset/
│   │           │   ├── train.jsonl                  # one record per line
│   │           │   ├── val.jsonl
│   │           │   ├── test.jsonl
│   │           │   └── <split>/images/<record_id>.png    # FR-11 aggressive-mode variants only (Story H.r.2)
│   │           ├── fitted_statistics/
│   │           ├── sample/                        # FR-J-1 SampleData runtime (Story J.a)
│   │           │   ├── <split>.jsonl              # subset of dataset/<split>.jsonl per SampleSelector
│   │           │   └── <split>/images/<record_id>.png   # sidecar PNGs for aggressive variants
│   │           ├── report/
│   │           │   ├── report.md
│   │           │   ├── drift.json
│   │           │   └── visualizations/
│   │           └── manifest.json
│   └── .tmp/
│       └── <run-id>/                       # in-flight or FAILED runs
└── plugins/                                # optional plugin-local caches (plugin-defined)
```

`<run-id>` is `<utc_iso_compact>-<8hex>` (e.g., `20260506T143022Z-a1b2c3d4`); deterministic enough for sorting, unique enough for concurrent runs with distinct keys.

---

## CLI Design

Single console script `datarefinery`, defined as a typer `Typer` instance at `datarefinery.cli.app:app`.

### Subcommands

| Verb | Purpose | Library equivalent |
|---|---|---|
| `init` | Scaffold a starter recipe (FR-17) | `datarefinery.scaffolder.scaffold_image_classification` |
| `validate` | Run schema + enumerated checks (FR-2) | `DataRefinery.validate()` |
| `check` | Report environment soundness (FR-18) | `DataRefinery.check()` |
| `status` | Summarize an instance (FR-19) | `DataRefinery.status()` |
| `materialize` | Run pipeline end-to-end (FR-3) | `DataRefinery.materialize()` |
| `report` | Re-render report from existing instance (FR-15) | `Instance.render_report()` |
| `inspect` | Read-only views (FR-20) | `DataRefinery.inspect()` |
| `clean` | Cache management (FR-21) | `DataRefinery.clean()` |
| `export` | Re-run sinks against an existing instance (Story I.f) | `DataRefinery.export()` |

### Shared options

```
--cache-root PATH       (env: DATAREFINERY_CACHE_ROOT, default: ./data)
--log-level LEVEL       (env: DATAREFINERY_LOG_LEVEL, default: INFO)
--log-target PATH       (env: DATAREFINERY_LOG_TARGET, default: stderr)
--plugin-path PATH      (env: DATAREFINERY_PLUGIN_PATH, repeatable)
--workers N             (env: DATAREFINERY_WORKERS, default: 1)
--seed INT              (recipe wins for non-ad-hoc; overrides per-run otherwise)
--variant NAME          (FR-14)
--no-color              (force non-rich output)
--quiet / --verbose     (level shortcuts)
--version               (datarefinery package version)
```

### Verb-specific options (selected)

- `materialize`: `--stage NAME` (partial run; result not promoted; manifest marked partial).
- `clean`: `--by-recipe HASH`, `--by-age DAYS`, `--orphans`, `--all`, `--yes` (required in non-TTY when `--all`).
- `inspect`: `--view NAME` to render a named exploration visualization; `--out PATH` for image/HTML output.
- `init`: `--enhance` (activates `lmentry`; errors if extra not installed).

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | User/recipe error: validation failure, contract failure, materialize failure under user control |
| 2 | System error: plugin not found, environment problem, filesystem/permissions |
| 130 | SIGINT (Ctrl-C) |

### Output

- **User-facing:** `rich` to stdout (progress bars, tables, summary). `--no-color` and non-TTY produce plain output. `rich.console.Console(stderr=True)` for warnings/errors.
- **Operational:** JSON-formatted lines via stdlib `logging` to `--log-target` (default stderr), with fields `timestamp`, `level`, `stage`, `op_id`, `message`. Library callers get a logger named `datarefinery` and control their own handlers; the CLI installs the JSON handler.

---

## Cross-Cutting Concerns

### Determinism

- Every stochastic operation is seeded.
- Recipe seed is the master; per-operation seeds are derived as `sha256(master_seed.to_bytes(8) + op_id.encode()).digest()[:8]` -> int. Per-record seeds inside parallel workers add the record id (see `pipeline.workers`).
- The validator catches sampling/augmentation operations declared without a seed (checks 5–11 + plugin-specific schemas).
- Determinism tests re-run a fixture pipeline twice and assert byte-identical output (acceptance criterion 2).

### Atomic materialization

- All pipeline writes target `<cache-root>/instances/.tmp/<run-id>/`.
- On success: `os.replace(temp, final)` — single filesystem operation.
- On failure: `mark_failed(temp, exc, stage)` writes `FAILED` JSON marker; final cache path untouched.
- Cross-device rename rejected up-front during materialize setup (validates `os.stat().st_dev` of both paths).

### Logging

Two output channels, strictly separated:

- **`rich` — user-facing output.** Progress bars, summary tables, the cache-hit/miss line, the final "instance materialized at ..." message. Goes to stdout/stderr for a human reading the terminal.
- **stdlib `logging` — operational output.** Stage starts/ends, op-ids, warnings, error context, timing. Emitted as one JSON object per line via `datarefinery.logging.JsonFormatter` with fields `{"ts", "level", "logger", "stage", "op_id", "message", ...extras}`. Goes to `--log-target` (default stderr alongside `rich`, but separable by redirecting to a file).

**Decision rule when adding new output:** ask "is this for a human watching the CLI run, or is this for someone debugging/monitoring the system later?" The first answer routes through `rich`; the second routes through `logging`. Never mix — emitting an operational warning via `console.print(...)` corrupts the user-facing surface (and breaks any downstream tool piping DataRefinery output), and emitting a progress message via `logger.info(...)` clutters the structured log stream.

Library callers get a no-op handler attached to the `datarefinery` logger by default; the CLI installs the JSON handler at startup based on `--log-target`. Library callers control their own logging configuration without DataRefinery hijacking the root logger.

### Error model

```
DataRefineryError                    # base
├── RecipeError                      # FR-1, FR-22 load/parse/schema-version failures
├── ValidationError                  # FR-2 check failures (carries ValidationReport)
├── PluginError                      # FR-16 discovery, duplicate names, missing extras
├── ContractError                    # FR-23 InputContracts / OutputExpectations failures
├── MaterializeError                 # FR-3, FR-5 stage failures, atomic-promote failures
└── CacheError                       # FR-4, FR-21 cache key, layout, clean problems
```

CLI's exit-code mapping reads the exception type to choose 1 (user/recipe/contract) vs 2 (system/plugin).

### Caching

- Content-addressed under `<cache-root>/instances/<recipe-hash16>/<input-hash16>/<seed>/`.
- Orphan temp directories from killed runs are cleanable via `clean --orphans`; default age threshold 24h, configurable.
- Cache hits are cheap: `compute_cache_key` + `pathlib.Path.exists()` + `Manifest` parse.
- **Sibling-instance references are loose-coupled in v1 (FR-TRANS-1, FR-ARCH-1).** When a recipe imports fitted statistics from a sibling instance via `stats_from_instance`, the sibling's `recipe_hash` is **not** mixed into the consuming recipe's cache identity. Re-materializing upstream does not auto-invalidate downstream; the user is responsible for re-materializing downstream when upstream changes. The loose-coupling choice is justified for small-scale single-author workflows where the failure mode (stale downstream after upstream re-fit) is detectable by inspection. Tight coupling — sibling `recipe_hash` participates in cache identity, so upstream changes auto-invalidate downstream — is a planned upgrade for multi-team and longitudinal workflows where loose-coupling failures are harder to spot; it will be a `schema_version` bump.

### Schema versioning

- Recipe `schema_version` gated by `recipe.loader.SUPPORTED_SCHEMA_VERSIONS`.
- Pre-production: schema version 1 may be redefined as design evolves; cache invalidation across DataRefinery versions is acceptable and noted in release notes.
- Post-production: each version is immutable; migrations live in `recipe.loader.migrations` keyed by `(from_version, to_version)`.
- `Manifest.schema_version` is a separate counter for the manifest format itself.
- Future upgrades that change cache-identity composition — notably FR-ARCH-1 tight coupling, where a sibling recipe's `recipe_hash` would begin participating in the consuming recipe's cache identity — are `schema_version` bumps, not silent shifts.

### Plugin trust boundary

- Plugins run in-process, unsandboxed. `check` lists discovered plugins so users can audit what is loaded.
- Duplicate-name plugins -> hard `PluginError` at discovery (FR-16 edge case).

### Concurrency (intra-run)

- Default `workers=1`: fully serial, simplest mental model and reproducible without seed-derivation ordering tricks.
- `workers>1`: `ProcessPoolExecutor` for per-record image operations declared parallelizable by the plugin's `OperationSpec`. Output reordered by `record_id` before downstream stages — worker scheduling does not affect bytes.

### Concurrency (inter-run)

- Pre-production: serialized externally by the user; running two `materialize` calls against the same cache root is unsupported (per FR-5 edge case). Defensive check: if `<run-id>` collision is observed during temp directory creation, fail with a clear error.
- Post-production: file-lock-based protocol (out of scope for v1 implementation; designed-for in cache layout).

---

## Performance Implementation

Per features.md, v1 commits to **no hard performance targets**. The implementation choices that carry performance implications:

- **Single-threaded default.** Serial is the boring baseline; correct first.
- **Opt-in process pool.** `--workers N` and the `RuntimeConfig.workers` field route per-record image ops through `concurrent.futures.ProcessPoolExecutor`. Determinism preserved by per-record seeding (see `pipeline.workers`).
- **No connection pooling** in v1 — the deterministic path performs no network I/O.
- **Resource limits** not enforced; memory and disk usage are user-managed. CIFAR-10-scale workloads on a developer laptop are the design target.
- **Reactive performance work.** When a representative workload exposes a problem, a story sets a target for the improvement. Up-front targets are out of scope.

Cache hits are constant-time (path stat + manifest parse). `validate` runs in seconds for any plausible recipe size — it never touches raw data beyond schema discovery.

---

## Testing Strategy

### Test categories

| Category | Path | Coverage focus |
|---|---|---|
| Unit | `tests/unit/` | Pure functions: loader, schema-version gate, canonical bytes, cache identity, splits/seeding, atomic promote, individual operations, fitted-statistics serdes. |
| Plugin contract | `tests/plugin_contract/` | Every plugin (including stubs) asserts its declared sections, operation list, and parameter schemas. |
| Integration | `tests/integration/` | End-to-end materialize on synthesized CIFAR-10-shaped fixture; byte-identical re-runs; cache hits on cosmetic edits; cache misses on semantic edits. |
| CLI smoke | `tests/cli/` | Every verb against fixture recipe; exit codes; output structure (parse JSON logs to validate fields). |

### Property-based tests (Hypothesis)

- **Cache-identity invariance:** generated YAML edits restricted to whitespace, comments, key-order permutations, and quote-style swaps must produce identical `cache_key`.
- **Cache-identity sensitivity:** generated semantic edits (changed scalar values, added/removed list items, added/removed sections) must produce a different `cache_key`.
- **Split determinism:** for a fixed seed, repeated splitting of a generated record list yields identical partitions across runs and across worker counts.

### Failure-mode tests

- Forced failure injected at every pipeline stage (filters, generation, splits, transformations, featurizations, visualizations, contracts) leaves a `FAILED`-marked temp directory and never touches the cache (acceptance criterion 4).
- Plugin not installed -> `validate` failure with the expected error pointer (FR-16 edge).
- Cross-device temp/cache -> materialize refuses up-front.

### Determinism tests

- Re-run a fixture pipeline twice with the same seed; assert byte-identical instance directory contents (filenames, file bytes, manifest contents excluding `created_at` and `elapsed_seconds`).

### Coverage thresholds

- **Always:** ≥95% on core invariants (recipe loader, schema-version gate, cache identity, splits/seeding, plugin interface, atomic promote/rollback).
- **Pre-production:** every FR exercised by at least a smoke test; no project-wide percentage gate.
- **Post-production:** ≥85% overall line coverage.

`pytest-cov` configured in `pyproject.toml` with per-module thresholds for the core-invariant set, and a project-wide gate enabled at production release.

### Fixtures

- `tests/fixtures/build_cifar10_shaped.py` synthesizes a ~50-image dataset at test time using NumPy-generated tensors written through Pillow as PNGs into a directory tree (`<class_name>/<image_id>.png`). No large binaries committed.
- A canonical-hash pinning test guards against accidental default-changes to pydantic models.

---

## Packaging and Distribution

### Package metadata

`pyproject.toml` (representative; final values land alongside the first packaging story):

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ml-datarefinery"     # distribution name; import name remains `datarefinery` (Hatch packages = ["src/datarefinery"])
version = "0.9.4"            # bumped per-story; first successful PyPI publish is v0.9.3
description = "Compile a YAML recipe into a reproducible, training-ready ML dataset instance."
requires-python = ">=3.12,<3.13"
license = { text = "Apache-2.0" }
readme = "README.md"
authors = [{ name = "Pointmatic" }]
classifiers = [
  "Development Status :: 3 - Alpha",
  "Intended Audience :: Science/Research",
  "License :: OSI Approved :: Apache Software License",
  "Programming Language :: Python :: 3.12",
  "Topic :: Scientific/Engineering :: Artificial Intelligence",
  "Operating System :: MacOS",
  "Operating System :: POSIX :: Linux",
]
dependencies = [
  "numpy",
  "pandas",
  "scipy",
  "scikit-learn",
  "pyarrow",
  "pyyaml",
  "pydantic>=2",
  "rich",
  "typer",
  "pillow",
]

[project.optional-dependencies]
llm = ["lmentry"]

[project.scripts]
datarefinery = "datarefinery.cli.app:app"

[project.entry-points."datarefinery.plugins"]
image_classification = "datarefinery.plugins.image_classification.plugin:plugin"
tabular = "datarefinery.plugins.tabular.plugin:plugin"
text = "datarefinery.plugins.text.plugin:plugin"

[tool.hatch.build.targets.wheel]
packages = ["src/datarefinery"]

[tool.hatch.build.targets.sdist]
include = ["src/datarefinery", "LICENSE", "README.md", "pyproject.toml"]
```

### Build artifacts

- **Wheel:** `ml_datarefinery-<version>-py3-none-any.whl` (pure-Python universal wheel; no native code ship in DataRefinery itself — Pillow brings its own platform-specific wheels as a transitive dep). The wheel installs `import datarefinery` and the `datarefinery` console script; PyPI normalises the distribution name to underscores in the artifact filename.
- **Sdist:** `ml_datarefinery-<version>.tar.gz` for downstream rebuilders (Linux distros, conda-forge, audit-build orgs).
- Both built by `python -m build` (or `hatch build`).

### Publishing

- **PyPI distribution name:** `ml-datarefinery`. The bare `datarefinery` name on PyPI was taken before this project began; the import name and console script remain `datarefinery` (same shape as `scikit-learn` / `import sklearn`).
- **Mechanism:** `pypa/gh-action-pypi-publish` with **PyPI Trusted Publishing** (OIDC). No long-lived API tokens.
- **Workflow:** `.github/workflows/publish.yml`:
  - Triggered on tag push matching `v*`.
  - Job 1 (`build`) builds wheel + sdist with `python -m build` and uploads to GH Actions artifact storage.
  - Job 2 (`publish-pypi`) publishes to **PyPI** under the `pypi` GitHub environment (required-reviewer protection — a maintainer must approve each deploy).
- **First publish:** v0.9.3 (Story H.g). Pre-v0.9.3 tags exist but were never published to PyPI.
- **Trusted-publisher setup:** the PyPI "pending publisher" binding plus the `pypi` GitHub Actions environment are configured once outside the repo. See `docs/guides/releasing.md` § "One-time PyPI Trusted Publisher setup".

### Package data

The wheel ships only Python source plus `py.typed`. Scaffolder templates (if introduced) live as Python modules (string constants), not as bundled YAML files, to avoid `package_data` complications. If non-Python assets become necessary, they are declared explicitly under `[tool.hatch.build.targets.wheel.force-include]`.

### Installation methods

| Mode | Command |
|---|---|
| End user (production) | `pip install ml-datarefinery` |
| End user with LLM enhancement | `pip install 'ml-datarefinery[llm]'` |
| End user with corruption-robustness extras | `pip install 'ml-datarefinery[corruptions]'` |
| Developer (runtime venv via pyve) | `pyve run pip install -e .` |
| Developer (testenv editable, required for CLI tests) | `pyve env run pip install -e .` |
| Developer (dev tools) | `pyve env install -r requirements-dev.txt` |
