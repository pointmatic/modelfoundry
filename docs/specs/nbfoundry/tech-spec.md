# tech-spec.md -- nbfoundry (Python 3.12.13)

This document defines **how** the `nbfoundry` project is built -- architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns.

For requirements and behavior, see [`features.md`](features.md). For the implementation plan, see [`stories.md`](stories.md). For project-specific must-know facts (workflow rules, architecture quirks, hidden coupling), see [`project-essentials.md`](project-essentials.md) — `plan_tech_spec` populates it after this document is approved. For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Runtime & Tooling

| Concern | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.12.13 (env-pinned) | features.md CR-10; verified Metal-acceleration compatibility. |
| **`requires-python`** (pyproject.toml) | `>=3.12.13,<3.14` | 3.12.13+ is fine; 3.14.x is incompatible with several ML deps. The exact 3.12.13 pin lives in `environment.yml` (env reproducibility), not in package metadata (PyPI-friendly). |
| **Environment manager** | Pyve + micromamba | features.md CR-10. Two-environment model: runtime in `.venv/`, dev tools in `.pyve/testenv/venv/`. |
| **Build backend** | `hatchling` | Modern PEP 517 backend; first-class src-layout support; minimal config. |
| **Package layout** | `src/nbfoundry/` (src layout) | Avoids the editable-install footgun called out in `docs/project-guide/go.md` § Pyve Essentials. |
| **Linter / formatter** | `ruff check` + `ruff format` | Single tool covers lint + format. Default rule set + `B`, `I`, `UP`, `SIM`, `RUF`. |
| **Type checker** | `mypy --strict` over the **whole package** | features.md QR-4; user direction: strict everywhere, drives sanity longer term. |
| **Test runner** | `pytest` + `pytest-cov` | Run via `pyve test`; never bare `pytest` (see `go.md` § Pyve Essentials). |
| **CI** | GitHub Actions | TR-7 cross-platform compile smoke on macOS (Apple Silicon) at minimum; Linux as stretch. |
| **Pre-commit hooks** | **Not used in v1**; CI gates only | Vendored hook envs drift from project Python; revisit if drift becomes painful. |
| **Versioning** | Semver — start at `0.1.0`; large minor versions allowed (e.g., `0.11.x`, `0.167.x`); `1.0.0` reserved for stable, production-quality, feature-complete release | User direction. |
| **License** | Apache-2.0 (SPDX `Apache-2.0`); copyright Pointmatic | features.md SC-1; header on every new source file (see `go.md` rules). |

### Invocation rules (LLM-internal vs. developer-facing)

Per `docs/project-guide/go.md` § Pyve Essentials, the LLM wraps its own Bash-tool commands with `pyve run` (e.g., `pyve run python -m nbfoundry.cli ...`); developer-facing command quotations use the bare form (e.g., `nbfoundry compile ...`). Always `python`, never `python3`.

### Two-environment install

This project ships a **CLI** (`nbfoundry`), so per `go.md` the testenv requires an editable install:

```bash
pyve run pip install -e .
pyve testenv run pip install -e .
pyve testenv --install -r requirements-dev.txt
```

`requirements-dev.txt` lists `ruff`, `mypy`, `pytest`, `pytest-cov`, plus any `types-*` stubs needed by mypy.

---

## Dependencies

### Runtime (declared in `pyproject.toml [project] dependencies`)

| Package | Purpose | Notes |
|---|---|---|
| `marimo` | Notebook substrate; parser used by `compile` to validate notebook source | features.md NG-1, FR-2; CR-7. |
| `typer` | CLI framework | User direction: `typer` for v1; reconsider `click` when we outgrow it. |
| `pyyaml` | YAML parsing for exercise definitions (`safe_load` only) | features.md FR-3. No round-trip needed. |
| `markdown-it-py` | Markdown → HTML renderer for `description` / `instructions` / `sections[i].description` | Supports CommonMark + GFM, matches `nbfoundry.toml`'s `markdown_flavor` toggle. |
| `pydantic` (v2) | Validation models for YAML schema and BR-4 submission rules | Cheap, well-typed BR-4 errors; `model_validate` produces structured failures we map to `ExerciseError`. |

**Standard library used (no third-party dep):** `logging` (OR-4), `pathlib`, `json`, `dataclasses` for non-validated internal types, `importlib.resources` for shipped templates, `tempfile` for atomic writes, `argparse` not used (Typer covers).

### Optional / system dependencies

- **micromamba** — required to install/launch the pinned environment (system-level, not a Python package).
- **modelfoundry** — internal dependency, declared via the thin adapter `nbfoundry/_modelfoundry.py`. **Not** pinned in `pyproject.toml [project] dependencies` for v1 (interface TBD per concept.md Constraints); the adapter raises a clear "modelfoundry required" error if not importable. When the modelfoundry contract lands, declare as `nbfoundry[modelfoundry]` extra.

### Development dependencies (in `requirements-dev.txt`, installed into testenv only)

| Package | Purpose |
|---|---|
| `ruff` | Lint + format. |
| `mypy` | Strict type checking. |
| `pytest` | Test runner. |
| `pytest-cov` | Coverage measurement; fail-under 85 on `nbfoundry` public modules. |
| `types-PyYAML` | mypy stubs. |

### Pinned ML stack (in `src/nbfoundry/templates/environment.yml`)

Single sectioned cross-platform stack shipped as package data. `nbfoundry init`
copies it into every scaffolded project; `nbfoundry compile` emits it into every
standalone artifact unless the source tree carries its own. Defaults to the
proven Apple Silicon path (Metal/MPS PyTorch, Apple's TensorFlow distribution +
`tensorflow-metal`, bundled Keras 3 from TF 2.16+). Cross-platform users follow
documented comment-block swaps inside each framework section.

Sections (`# core`, `# framework`, `# huggingface`, `# optimization`,
`# dev tooling`) are comment-delimited within the one shared file. The
per-template `environment.yml` copies were removed in Phase F.b — one source
of truth.

| Section | Channel | Packages |
|---|---|---|
| core | conda-forge | `python=3.12.13` (exact), `numpy`, `scipy`, `pandas`, `pyarrow`, `matplotlib`, `seaborn`, `plotly`, `scikit-learn>=1.5`, `pillow`, `h5py`, `pyyaml`, `click`, `rich`, `python-dotenv`, `marimo`, `conda-lock` |
| core (pip) | pypi | `ml-datarefinery` (Pointmatic-internal; adapter + template integration deferred to a future Phase I) |
| framework | conda-forge | `pytorch>=2.5` (MPS default; cross-platform swap to `cu126` / `cu128` pip wheels documented inline) |
| framework (pip) | pypi | `tensorflow-macos>=2.16` + `tensorflow-metal>=1.1` (Apple Silicon default; swap to `tensorflow` or `tensorflow[and-cuda]` documented inline). Keras 3 is the bundled `tf.keras` namespace — **no standalone `keras` pin**. |
| huggingface | conda-forge | `transformers`, `datasets`, `peft`, `sentencepiece`, `protobuf`, `tiktoken` |
| optimization | conda-forge | `optuna` |
| dev tooling | conda-forge | `ruff`, `mypy`, `pytest`, `pytest-cov` (so scaffolded student projects ship dev-tool-complete) |

**Phase F dropped (do not reintroduce):** `jupyterlab`, `ipykernel`, `ipywidgets`
(Marimo replaces them); standalone `keras>=3.x` (Keras 3 ships bundled with TF
2.16+ and is exposed as both `tf.keras` and bare `keras`; a separate pin pulls a
parallel minor and silently fights TF's bundled copy).

---

## Package Structure

Source layout, with one-line descriptions per file:

```
nbfoundry/                                    # repo root
├── pyproject.toml                            # build backend (hatchling), deps, console script, ruff/mypy/pytest config
├── requirements-dev.txt                      # dev tools for testenv (ruff, mypy, pytest, pytest-cov, type stubs)
├── environment.yml                           # pinned Pyve + micromamba runtime env (Python 3.12.13 + ML stack)
├── README.md                                 # quickstart: install, scaffold, compile, embed
├── LICENSE                                   # Apache-2.0
├── .github/
│   └── workflows/
│       ├── ci.yml                            # ruff + mypy + pytest on macOS (primary), Linux (stretch)
│       └── publish.yml                       # PyPI release on tag (manual trigger v1)
├── src/
│   └── nbfoundry/
│       ├── __init__.py                       # re-exports compile_exercise, validate_exercise, ExerciseError, __version__
│       ├── _version.py                       # single source of truth for the version string
│       ├── cli.py                            # Typer app: init, compile, compile-exercise, validate (entry: main())
│       ├── compiler.py                       # compile_exercise(): YAML → BR-1 dict; orchestrates load → validate → render → assemble
│       ├── validator.py                      # validate_exercise(): collects all FR-3/FR-5/BR-4 errors; shared with compiler
│       ├── schema.py                         # Pydantic models for YAML input + compiled output (single source of truth for shape)
│       ├── markdown.py                       # markdown-it-py wrapper; respects markdown_flavor (commonmark | gfm)
│       ├── assets.py                         # asset path resolution, existence check, BR-5 enumeration, size warnings
│       ├── paths.py                          # path-escape protection (SC-3): resolve & verify under base_dir
│       ├── errors.py                         # ExerciseError dataclass + helpers; maps Pydantic errors → ExerciseError list
│       ├── logging_setup.py                  # stdlib logging configuration; --verbose/--quiet wiring
│       ├── config.py                         # nbfoundry.toml loader; precedence: CLI > toml > defaults
│       ├── standalone.py                     # `nbfoundry compile` artifact emitter (notebook + env spec + launch.py)
│       ├── notebooks.py                      # Marimo notebook discovery, parse, tree walking; entry-point detection
│       ├── _modelfoundry.py                  # thin adapter Protocol; raises clear error when modelfoundry not importable
│       └── templates/
│           ├── __init__.py                   # importlib.resources entry point
│           ├── environment.yml               # single shared sectioned ML stack (replaces per-template copies as of F.b)
│           ├── data_exploration/             # five-stage lifecycle template (Marimo .py only; env from shared file)
│           ├── data_preparation/
│           ├── model_experimentation/
│           ├── model_optimization/
│           ├── model_evaluation/
│           └── standalone/
│               └── launch.py                 # cross-platform launcher embedded in compiled standalone artifacts
├── tests/
│   ├── conftest.py                           # shared fixtures: tmp base_dir, sample YAML, golden dicts
│   ├── unit/
│   │   ├── test_compiler.py                  # FR-3 happy paths + every rejection
│   │   ├── test_validator.py                 # FR-4 collects all errors; FR-5 (BR-4) full matrix
│   │   ├── test_schema.py                    # Pydantic round-trips
│   │   ├── test_markdown.py                  # commonmark vs gfm, edge cases
│   │   ├── test_assets.py                    # BR-5 enumeration, missing-asset rejection, size warning, alt-required
│   │   ├── test_paths.py                     # SC-3 path-escape: ../, absolute, symlinks
│   │   ├── test_errors.py                    # ExerciseError shape; Pydantic → ExerciseError mapping
│   │   ├── test_modelfoundry_adapter.py      # raises when modelfoundry missing; mockable Protocol
│   │   └── test_config.py                    # precedence; missing toml; bad keys
│   ├── integration/
│   │   ├── test_cli_init.py                  # FR-1: scaffold from each of five templates
│   │   ├── test_cli_compile.py               # FR-2: standalone artifact end-to-end
│   │   ├── test_cli_compile_exercise.py      # FR-3 end-to-end via CLI; JSON stdout / --out
│   │   ├── test_cli_validate.py              # FR-4 end-to-end via CLI; exit codes
│   │   ├── test_determinism.py               # OR-5: byte-stable JSON across runs
│   │   ├── test_no_network.py                # AC-9: sandbox proves zero network calls
│   │   └── test_aggregate_tree.py            # FR-6: notebook tree → single dict
│   └── fixtures/
│       ├── exercises/
│       │   ├── valid_minimal.yaml            # smallest passing exercise
│       │   ├── valid_graded.yaml             # full submission block (BR-4)
│       │   ├── valid_with_assets.yaml        # image expected_outputs (path-only, BR-5)
│       │   ├── invalid_*.yaml                # one fixture per validator rejection
│       │   └── tree/                         # multi-notebook tree fixture (FR-6)
│       └── golden/
│           └── valid_graded.json             # TR-2 byte-for-byte goldens
└── docs/                                     # already-present specs and project-guide
```

---

## Filename Conventions

| File Type | Convention | Examples |
|-----------|------------|----------|
| **Documentation** (Markdown) | Hyphens | `getting-started.md`, `tech-spec.md` |
| **GitHub workflow files** | Hyphens | `ci.yml`, `publish.yml` |
| **Python modules** | Underscores (PEP 8) | `compiler.py`, `logging_setup.py`, `_modelfoundry.py` |
| **Python packages / template dirs** | Underscores (PEP 8) | `data_exploration/`, `model_experimentation/`, `templates/` |
| **YAML fixtures** | Underscores (mirrors Python) | `valid_minimal.yaml`, `invalid_missing_title.yaml` |
| **Configuration files** | Hyphens or dots | `pyproject.toml`, `environment.yml`, `requirements-dev.txt`, `.gitignore` |

Private modules use a leading `_` (e.g., `_modelfoundry.py`, `_version.py`).

---

## Key Component Design

Public API signatures match `learningfoundry-dependency-spec.md` BR-1 / BR-2 / BR-3 verbatim.

### `nbfoundry.compile_exercise(yaml_path: Path, base_dir: Path) -> dict` — FR-3

```python
def compile_exercise(yaml_path: Path, base_dir: Path) -> dict[str, Any]:
    """Compile an exercise YAML → BR-1-shaped dict. Raises ExerciseError on first invalid input."""
```

**Behavior (orchestration):**

1. `paths.resolve_under(base_dir, yaml_path)` — SC-3 path-escape guard. Returns the canonical resolved path; raises `ExerciseError` on escape.
2. Read and `yaml.safe_load` the file. Reject scalar URL-looking values up front (SC-2).
3. `schema.RawExerciseModel.model_validate(data)` — Pydantic v2 validates required fields, rule/type compatibility, BR-4 submission constraints in one pass. Pydantic errors → `errors.from_pydantic(...)` → first `ExerciseError`.
4. For each section: enforce mutual exclusivity of `code` / `code_file`; resolve `code_file` under `base_dir` (SC-3); read inline.
5. Render markdown → HTML for top-level `description` (becomes `instructions`) and each `sections[i].description` via `markdown.render(...)`. Per `nbfoundry.toml`'s `markdown_flavor` (default `commonmark`).
6. **Asset handling (BR-5).** For every `expected_outputs[i]` of `type: image`: validate the referenced `path` exists at `base_dir / path` (do **not** read bytes); validate `alt` is non-empty (BR-1 constraint); record the relative path in the running `assets[]` list. For `type: text`, pass `content` through. For `type: table`, v1 carries `content` as a string (BR-1 says fetched-CSV/JSON via `path` is deferred).
7. Asset size advisory: `assets.warn_if_large(base_dir, assets)` emits warnings (logger) for any single asset > 5 MB; aborts with `ExerciseError` for any > 10 MB unless `compile_exercise` is invoked with `allow_large_assets=True` (kwarg) — CLI exposes `--allow-large-assets`. (See Cross-Cutting.)
8. Pass through `hints` and `environment` unchanged.
9. Construct the final dict with stable key order:

   ```python
   {
       "type": "exercise",
       "source": "nbfoundry",
       "ref": str(yaml_path),
       "status": "ready",
       "title": ...,
       "instructions": ...,
       "sections": [...],
       "expected_outputs": [...],   # path-only for type=image; alt required
       "assets": sorted(unique(asset_paths)),   # OR-5 deterministic ordering
       "hints": [...],
       "submission": ... | None,
       "environment": {...},
   }
   ```
10. Return the dict. **No file writes, no network, no module imports beyond what's already declared as a runtime dep** (OR-6, SC-2, SC-4).

**Edge cases:** see features.md FR-3.

### `nbfoundry.validate_exercise(yaml_path: Path, base_dir: Path) -> list[str]` — FR-4

Same pipeline as `compile_exercise` but **collects every error** instead of raising on the first. Internally drives the same Pydantic model with `model_validate(..., strict=True)` and converts the full `ValidationError` tree into human-readable strings via `errors.format_errors(...)`. YAML parse failure or missing file short-circuits and returns a single-element list (FR-4 edge cases).

Implementation note: the compiler and validator share a single `_validate(...) -> tuple[Model | None, list[ExerciseError]]` core. `compile_exercise` raises on the first error; `validate_exercise` formats and returns the full list.

### `nbfoundry.ExerciseError` — BR-3

```python
@dataclass(frozen=True, slots=True)
class ExerciseError(Exception):
    file_path: Path
    message: str
    detail: ErrorDetail | None = None  # see Data Models

    def __str__(self) -> str:
        return f"{self.file_path}: {self.message}" + (f" [{self.detail}]" if self.detail else "")
```

Exposed as `nbfoundry.ExerciseError`. All library entry points either return clean output or raise this type — no leaking Pydantic / YAML / OS errors to callers.

### CLI — `src/nbfoundry/cli.py` (Typer)

Subcommands and flags: see `## CLI Design` below. Each subcommand is a thin adapter that:
1. Configures logging from `--verbose` / `--quiet`.
2. Loads `nbfoundry.toml` if present (`config.load(base_dir)`).
3. Calls into the library functions.
4. Maps `ExerciseError` → exit code 1 with message on stderr.
5. Emits success output on stdout (path, JSON, etc.).

### Notebook compiler — `standalone.py` (FR-2)

`compile(notebook_or_dir: Path, out: Path) -> Path`:
1. `notebooks.discover_entry(notebook_or_dir)` — single file or root-of-tree.
2. `notebooks.parse_all(...)` — uses `marimo` parser; aggregates parse failures with file/line.
3. **Atomic write:** stage output into `tempfile.mkdtemp(dir=out.parent)`; copy notebooks, write `environment.yml`, write `launch.py`; `os.replace(tmp, out)` on success. Partial output never visible.
4. Return `out`.

`launch.py` (shipped from `templates/standalone/launch.py`) shells out to `marimo edit` (or `marimo run` if a `--run` flag is later added) against the entry-point notebook, using the active environment.

### Modelfoundry adapter — `_modelfoundry.py` (FR-7)

```python
class ModelfoundryAdapter(Protocol):
    def prepare_data(self, ...) -> ...: ...
    def train(self, ...) -> ...: ...
    def optimize(self, ...) -> ...: ...
    def evaluate(self, ...) -> ...: ...

def get_adapter() -> ModelfoundryAdapter:
    """Import modelfoundry lazily; raise a clear error if unavailable. Templates call this."""
    try:
        import modelfoundry  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError(
            "modelfoundry is required for nbfoundry templates at runtime. "
            "Install it (TBD package name) or run with a stub adapter for spikes."
        ) from e
    return _RealAdapter(modelfoundry)
```

The compiler core (`compiler.py`, `validator.py`) does **not** import this module — only the templates do (FR-7 step 2). The Protocol shape is **provisional**; concrete method signatures land when modelfoundry's contract is finalized (concept.md Constraints). v1 ships the adapter wired enough to run a Hello-World / spike notebook end-to-end.

---

## Data Models

All data shapes live in `schema.py` as Pydantic v2 models. Names suffix `Model` for input shapes; the **compiled output** is an explicit `TypedDict` (the BR-1 contract) — Pydantic generates input validation, the TypedDict types the wire shape.

### Input (parsed from YAML)

```python
class RawSectionModel(BaseModel):
    title: str
    description: str
    code: str | None = None
    code_file: Path | None = None
    editable: bool = False

    @model_validator(mode="after")
    def code_xor_code_file(self) -> Self:
        if (self.code is None) == (self.code_file is None):
            raise ValueError("exactly one of `code` or `code_file` is required")
        return self


class RawExpectedOutputModel(BaseModel):
    description: str
    type: Literal["image", "text", "table"]
    # image: requires `path` and `alt`; text/table: requires `content`
    path: Path | None = None
    alt: str | None = None
    content: str | None = None

    @model_validator(mode="after")
    def shape_by_type(self) -> Self:
        if self.type == "image":
            if not self.path or not self.alt:
                raise ValueError("image expected_outputs require both `path` and `alt`")
            if self.content is not None:
                raise ValueError("image expected_outputs must not carry `content`")
        else:  # text | table
            if self.content is None:
                raise ValueError(f"{self.type} expected_outputs require `content`")
            if self.path is not None or self.alt is not None:
                raise ValueError(f"{self.type} expected_outputs must not carry `path`/`alt`")
        return self


class ExpectedRule(BaseModel):  # BR-4 comparison rule
    type: Literal["range", "equals", "contains_all"]
    min: float | None = None
    max: float | None = None
    value: float | str | None = None
    values: list[str] | None = None
    weight: PositiveInt = 1

    # validator: required keys per rule + numeric bounds


class SubmissionFieldModel(BaseModel):
    name: str
    type: Literal["number", "text"]
    label: str
    placeholder: str | None = None
    expected: ExpectedRule

    # validator: rule/type compatibility (range→number; contains_all→text; equals→number|text)


class SubmissionModel(BaseModel):  # BR-4
    pass_threshold: confloat(ge=0.0, le=1.0) = 0.0
    fields: list[SubmissionFieldModel] = Field(min_length=1)

    # validator: unique field names


class EnvironmentModel(BaseModel):
    python_version: str
    dependencies: list[str]
    setup_instructions: str


class RawExerciseModel(BaseModel):
    title: str
    description: str  # markdown source
    sections: list[RawSectionModel] = Field(min_length=1)
    expected_outputs: list[RawExpectedOutputModel] = []
    hints: list[str] = []
    submission: SubmissionModel | None = None
    environment: EnvironmentModel | None = None
```

### Output (compiled artifact — BR-1 wire shape)

```python
class CompiledSection(TypedDict):
    title: str
    description: str        # rendered HTML
    code: str
    editable: bool

class CompiledExpectedImage(TypedDict):
    description: str
    type: Literal["image"]
    path: str               # relative to base_dir
    alt: str

class CompiledExpectedTextOrTable(TypedDict):
    description: str
    type: Literal["text", "table"]
    content: str

CompiledExpectedOutput = CompiledExpectedImage | CompiledExpectedTextOrTable

class CompiledSubmissionField(TypedDict, total=False):
    name: str
    type: Literal["number", "text"]
    label: str
    placeholder: str
    expected: dict[str, Any]   # ExpectedRule serialized; keys per rule type

class CompiledSubmission(TypedDict):
    pass_threshold: float
    fields: list[CompiledSubmissionField]

class CompiledEnvironment(TypedDict):
    python_version: str
    dependencies: list[str]
    setup_instructions: str

class CompiledExercise(TypedDict):
    type: Literal["exercise"]
    source: Literal["nbfoundry"]
    ref: str
    status: Literal["ready"]   # "stub" is learningfoundry's domain, not nbfoundry's
    title: str
    instructions: str          # rendered HTML
    sections: list[CompiledSection]
    expected_outputs: list[CompiledExpectedOutput]
    assets: list[str]          # BR-5 enumeration; sorted, deduplicated
    hints: list[str]
    submission: CompiledSubmission | None
    environment: CompiledEnvironment | None
```

### `ErrorDetail`

```python
@dataclass(frozen=True, slots=True)
class ErrorDetail:
    section_index: int | None = None
    field_name: str | None = None
    yaml_pointer: str | None = None  # e.g. "submission.fields[2].expected.min"
```

---

## Configuration

`nbfoundry.toml` at `base_dir` (per features.md). Loaded via stdlib `tomllib`.

```toml
[compile]
default_out = "dist/"

[exercise]
markdown_flavor = "commonmark"   # commonmark | gfm

[environment]
spec_path = "environment.yml"

[assets]
max_single_asset_mb = 10         # error threshold
warn_single_asset_mb = 5         # warn threshold
allow_large_assets = false       # override flag default
```

**Precedence (high → low):** CLI flags → `nbfoundry.toml` → built-in defaults. Implemented in `config.load(base_dir) -> Config`, which produces an immutable `Config` dataclass that the CLI merges with parsed flag values before calling library functions.

**No environment variables required for v1.**

---

## CLI Design

Console script: `nbfoundry = nbfoundry.cli:main`.

### Subcommands

| Subcommand | Synopsis | Behavior |
|---|---|---|
| `init` | `nbfoundry init <name> [--template <stage>]` | FR-1: scaffold a five-stage notebook from `templates/<stage>/` via `importlib.resources.files`. Default stage: `data_exploration`. |
| `compile` | `nbfoundry compile <notebook-or-dir> [--out <path>]` | FR-2: emit standalone artifact (atomic write). |
| `compile-exercise` | `nbfoundry compile-exercise <yaml-path> [--base-dir <path>] [--out <path>] [--allow-large-assets]` | FR-3: writes JSON to `--out` if given, else stdout. |
| `validate` | `nbfoundry validate <yaml-path> [--base-dir <path>]` | FR-4: prints each error on its own line; exit 0 if empty, 1 otherwise. |

### Shared / global flags

| Flag | Effect |
|---|---|
| `--verbose, -v` | Sets logger level to DEBUG. |
| `--quiet, -q` | Sets logger level to WARNING; silences info banners. |
| `--version` | Prints `__version__`. |
| `--help` | Typer auto-generated. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. `validate` returns `0` for empty error list. |
| `1` | `ExerciseError`, validation failure, missing file, parse failure, asset oversize. |
| `2` | CLI misuse (Typer default — bad flags, missing required arg). |

`stderr` carries error messages; `stdout` carries the success payload (path, JSON, scaffolded directory).

---

## Cross-Cutting Concerns

| Concern | Implementation |
|---|---|
| **Path-escape protection (SC-3)** | `paths.resolve_under(base_dir, candidate)`: `Path(candidate).expanduser()` → reject absolute → `(base_dir / candidate).resolve(strict=True)` → assert `base_resolved` is `Path.is_relative_to(base_resolved)`. Symlinks are resolved before the check. |
| **No network at compile time (SC-2, AC-9)** | The compiler performs zero socket I/O. YAML scalars matching `re.compile(r"^https?://")` in path positions are rejected. AC-9 is enforced in tests by a sandbox fixture that monkey-patches `socket.socket.connect`. |
| **No code execution at compile time (SC-4)** | Source is parsed via `marimo`'s parser (which compiles to AST under the hood, not exec). No `exec`, no `eval`, no `subprocess` calls in the compiler path. |
| **Atomic writes** | `nbfoundry compile` (and `compile-exercise --out <path>`): stage output into `tempfile.mkdtemp(dir=parent)`; on success, `os.replace(tmp_dir, target)` for the directory case, or write-to-temp-file + `os.replace` for the JSON case. Partial output never visible to the user; Ctrl-C leaves the original target unchanged. |
| **Asset size policy** | `assets.check_size(...)`: warn at `warn_single_asset_mb` (default 5MB); error at `max_single_asset_mb` (default 10MB) unless `--allow-large-assets` (CLI) or `allow_large_assets=True` (lib kwarg). Total-size cap is **not** enforced in v1 (per-asset cap is sufficient signal). |
| **Determinism (OR-5)** | All list iteration is over either an authored ordering (e.g., `sections`) or `sorted(...)` (e.g., `assets`). `dict` literals in the output use a fixed key order (CompiledExercise above). JSON serialization uses `json.dumps(d, sort_keys=False, ensure_ascii=False, separators=(",", ": "), indent=2)` — keys are already in canonical order from the TypedDict construction; explicit non-sort keeps the human-readable order. Path normalization: every emitted path is the relative `Path` from `base_dir`, with forward slashes (`Path.as_posix()`). |
| **Logging (OR-4)** | `logging_setup.configure(level)` installs a `StreamHandler` on stderr with format `%(levelname)s %(name)s: %(message)s`. Library code logs to `logging.getLogger("nbfoundry.<module>")`; CLI maps `--verbose/--quiet` to levels. No third-party logging deps. |
| **Error mapping** | All public-API exits go through `errors.ExerciseError`. Pydantic `ValidationError` → list of `ExerciseError` via `errors.from_pydantic(yaml_path, ve)` that walks `ve.errors()` and constructs a `yaml_pointer` from each `loc` tuple. |
| **License header (FR-8, SC-1)** | Every new `.py` / `.yml` / `.toml` / `.sh` file in this repo and every template file ships with an `# SPDX-License-Identifier: Apache-2.0` + `# Copyright Pointmatic` header at the top, using the comment syntax of the file type. Compiler does not inject headers into author-authored notebooks; it preserves whatever the author has (FR-8 step 3 / edge case). |
| **Modelfoundry boundary (FR-7, AC-10)** | Only `_modelfoundry.py` and template code may import `modelfoundry`. A pytest fixture asserts no module under `nbfoundry/{compiler,validator,schema,cli,...}.py` imports the symbol (test_modelfoundry_adapter::test_compiler_core_does_not_import). |

---

## Performance Implementation

v1 is **single-threaded, single-process** — all work fits well inside the budgets in features.md (PE-1: ≤1s single notebook, ≤5s tree of ≤10; PE-2: ≤500ms validate; PE-3: ≤10s warm cold-start).

| Concern | Approach |
|---|---|
| **Concurrency model** | Synchronous; no `asyncio`, no thread pool, no multiprocessing. YAML files are tiny; markdown rendering is microseconds; asset existence checks are stat calls. |
| **Resource limits** | None enforced beyond the asset size policy above. Compile is offline (PE-5) — no rate limiting, no retries, no connection pooling needed. |
| **I/O** | All reads through `pathlib.Path.read_text(encoding="utf-8")` / `.read_bytes()`. No streaming; files are small. Asset bytes are **never** read by the compiler (BR-5) — `Path.is_file()` is sufficient. |
| **Caching** | None in v1. Re-compilation is cheap; the user-facing budget is comfortable. |
| **Marimo parse cost** | Cached by Marimo internally; `notebooks.parse_all(...)` reuses the parser across files in a tree. |

A v2 option (when curriculum-scale performance bites) is to parallelize `notebooks.parse_all` and asset existence checks via `concurrent.futures.ThreadPoolExecutor`. Out of scope for v1.

---

## Testing Strategy

Tests live under `tests/`, run via `pyve test` (which invokes the testenv's pytest against the repo). Coverage measured by `pytest-cov` on `nbfoundry/` (templates and `templates/standalone/launch.py` excluded — they're generated/runtime files).

| Test layer | What it covers | features.md tie-in |
|---|---|---|
| **Unit — schema** | Pydantic models accept valid input, reject every invalid permutation; BR-4 rule/type matrix; `weight` integer/positivity; duplicate-name detection. | TR-1, TR-8 |
| **Unit — compiler core** | `compile_exercise` happy path; markdown rendering; code/code_file mutual exclusion; section-level errors carry section index. | TR-1 |
| **Unit — validator** | `validate_exercise` returns *all* errors (not just first); empty list on valid input; YAML parse failure short-circuits. | TR-1 |
| **Unit — assets** | BR-5 enumeration: every referenced path appears in `assets[]`, no orphans, no duplicates; missing-asset rejection; `alt` required for image; size warning/error thresholds; `--allow-large-assets` override. | TR-1, BR-5 |
| **Unit — paths** | SC-3 path-escape: `..`, absolute, symlink-into-elsewhere, mixed-separator. | TR-1, SC-3 |
| **Unit — modelfoundry adapter** | Raises clear error when `modelfoundry` not importable; the compiler core does **not** import the adapter (AST scan). | AC-10, FR-7 |
| **Integration — CLI** | `init`, `compile`, `compile-exercise`, `validate` end-to-end; exit codes; stdout/stderr separation; `--out` writes JSON; `--allow-large-assets` flag. | TR-3, AC-6 |
| **Integration — schema fidelity** | The `valid_graded.yaml` fixture compiles to a dict matching `valid_graded.json` byte-for-byte (modulo path normalization). | TR-2, QR-5 |
| **Integration — determinism** | Two runs produce byte-identical JSON. | OR-5 |
| **Integration — no-network sandbox** | Monkey-patched `socket.socket.connect` raises; `compile_exercise` and `validate_exercise` succeed without triggering it. | AC-9, SC-2 |
| **Integration — tree (FR-6)** | A multi-notebook tree compiles to a single dict; tree-internal references inline correctly; tree-external references reject. | FR-6 |
| **Type check** | `pyve testenv run mypy --strict src/nbfoundry/` passes. | TR-5, QR-4 |
| **Coverage** | `pytest-cov --cov=nbfoundry --cov-fail-under=85` passes on public modules. | TR-6 |
| **Cross-platform** | GHA matrix: macOS-latest (Apple Silicon runner) primary; ubuntu-latest stretch. Windows out of v1 CI scope. | TR-7, QR-3 |

**Fixture organization.** Each invalid YAML fixture is named for the rejection it triggers (`invalid_pass_threshold_out_of_range.yaml`, `invalid_duplicate_field_name.yaml`, etc.) — TR-8 reads naturally from the directory listing.

---

## Packaging and Distribution

| Concern | Choice |
|---|---|
| **Registry** | PyPI as `nbfoundry`. |
| **Build backend** | `hatchling`. |
| **Package metadata** | `pyproject.toml` `[project]` block: name, version (read from `_version.py`), description, README, license `Apache-2.0`, authors `Pointmatic`, classifiers, `requires-python`. |
| **Console script** | `[project.scripts] nbfoundry = "nbfoundry.cli:main"`. |
| **Package data** | `[tool.hatch.build.targets.wheel.sources] "src" = ""` for src layout; `[tool.hatch.build.targets.wheel.force-include]` to ship `src/nbfoundry/templates/**` as package data; `importlib.resources.files("nbfoundry.templates")` reads them at runtime. |
| **Version source of truth** | `src/nbfoundry/_version.py`: `__version__ = "0.1.0"`. `pyproject.toml` uses `dynamic = ["version"]` + `[tool.hatch.version] path = "src/nbfoundry/_version.py"`. |
| **Optional extras** | `[project.optional-dependencies] modelfoundry = ["modelfoundry>=TBD"]` — wired but not pinned for v1. Future: `wasm = ["marimo[wasm]"]` if Marimo WASM lands. |
| **Release process (v1)** | Manual: tag `vX.Y.Z` → GHA `publish.yml` builds sdist + wheel via `hatch build` → `twine upload`. Trusted publishing via PyPI's OIDC (no long-lived tokens). |
| **Versioning** | Semver. Start at `0.1.0`; minor versions can grow large (`0.11.x`, `0.167.x`). `1.0.0` reserved for stable, production-quality, feature-complete release per AC-1..AC-10. |
| **`environment.yml` distribution** | Shipped as package data so `nbfoundry init` can copy it alongside the scaffolded notebook (FR-1) and so compiled standalone artifacts (FR-2) include a copy for reproducibility (CR-7). |
