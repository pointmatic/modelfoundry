# tech-spec.md -- nbfoundry (Python 3.12.13)

This document defines **how** the `nbfoundry` project is built -- architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns.

For requirements and behavior, see [`features.md`](features.md). For the implementation plan, see [`stories.md`](stories.md). For project-specific must-know facts (workflow rules, architecture quirks, hidden coupling), see [`project-essentials.md`](project-essentials.md) — `plan_tech_spec` populates it after this document is approved. For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Runtime & Tooling

| Concern | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.12.13 (env-pinned) | features.md CR-10; verified Metal-acceleration compatibility. |
| **`requires-python`** (pyproject.toml) | `>=3.12.13,<3.14` | 3.12.13+ is fine; 3.14.x is incompatible with several ML deps. The interpreter pin is carried by the project venv (env reproducibility), not in package metadata (PyPI-friendly). |
| **Environment manager** | Pyve + venv (exclusively) | features.md CR-10. The Metal ML stack is fully pip-installable on Apple Silicon, so no conda/micromamba anywhere. Two-environment model: runtime in `.venv/`, dev tools in the named testenv. |
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
| `markdown-it-py` | Markdown → HTML renderer for the banner `description` and each `hints[i]` | Supports CommonMark + GFM, matches `nbfoundry.toml`'s `markdown_flavor` toggle. |
| `pydantic` (v2) | Validation models for the `ExerciseDefinition` YAML schema | `model_validate` produces structured failures we map to `ExerciseError` via `errors.from_pydantic(...)`. |

**Standard library used (no third-party dep):** `logging` (OR-4), `pathlib`, `json`, `dataclasses` for non-validated internal types, `importlib.resources` for shipped templates, `tempfile` for atomic writes, `argparse` not used (Typer covers).

### Optional / system dependencies

- **(no system env manager)** — the project is exclusively Pyve + venv; the Metal ML stack is fully pip-installable on Apple Silicon, so no conda/micromamba (or any other system-level env manager) is required.
- **modelfoundry** — internal dependency, declared via the thin adapter `nbfoundry/_modelfoundry.py`. **Not** pinned in `pyproject.toml [project] dependencies` for v1 (interface TBD per concept.md Constraints); the adapter raises a clear "modelfoundry required" error if not importable. When the modelfoundry contract lands, declare as `nbfoundry[modelfoundry]` extra.

### Development dependencies (in `requirements-dev.txt`, installed into testenv only)

| Package | Purpose |
|---|---|
| `ruff` | Lint + format. |
| `mypy` | Strict type checking. |
| `pytest` | Test runner. |
| `pytest-cov` | Coverage measurement; fail-under 85 on `nbfoundry` public modules. |
| `types-PyYAML` | mypy stubs. |

### Pinned ML stack (per-stage venv/pip requirements in `src/nbfoundry/templates/`)

Three composable pip requirements files shipped as package data (the conda
`environment.yml` was deleted in Phase F.f.4 — the project is now exclusively
venv). `nbfoundry init` copies the **stage-appropriate** file into every
scaffolded project; `nbfoundry compile` emits the stage-appropriate file into
every standalone artifact (falling back to `requirements-base.txt` when the
source tree carries none). Defaults to the proven Apple Silicon path (Metal/MPS
PyTorch via the bare `torch` wheel, Apple's TensorFlow distribution +
`tensorflow-metal`, bundled Keras 3 from TF 2.16+). Cross-platform users follow
documented comment-block swaps inside each file.

The per-stage split (vs. one combined file) is what makes the torch+TF
co-residence SIGBUS (F.f.1) impossible by construction for learners: `torch` and
`tensorflow` are never installed into the same venv.

| File | Source class | Packages |
|---|---|---|
| `requirements-base.txt` | pip (PyPI) | `numpy`, `scipy`, `pandas`, `pyarrow`, `matplotlib`, `seaborn`, `plotly`, `scikit-learn>=1.5`, `pillow`, `h5py`, `pyyaml`, `click`, `rich`, `python-dotenv`, `marimo`, `ml-datarefinery` (Pointmatic-internal; adapter + template integration deferred to a future Phase I) |
| `requirements-torch.txt` | pip (PyPI) | `-r requirements-base.txt` + `torch>=2.5` (MPS wheel default; CUDA via `--index-url` `cu126`/`cu128` documented inline) + `transformers`, `datasets`, `peft`, `sentencepiece`, `protobuf`, `tiktoken` + `optuna` |
| `requirements-tf.txt` | pip (PyPI) | `-r requirements-base.txt` + `tensorflow-macos>=2.16` + `tensorflow-metal>=1.1` (Apple Silicon default; swap to `tensorflow` or `tensorflow[and-cuda]` documented inline). Keras 3 is the bundled `tf.keras` namespace — **no standalone `keras` pin**. |

Stage → file: `data_exploration` / `data_preparation` / `model_evaluation` →
`requirements-base.txt`; `model_experimentation` / `model_optimization` →
`requirements-torch.txt`. (`model_evaluation` was reshaped to a scikit-learn
example in F.j — evaluation is framework-agnostic — so it ships base, not torch.)
`requirements-tf.txt` is the TF-based-learner option, not bound to a shipped
template (validated by the `smoke-tensorflow` dev env).

**Phase F dropped (do not reintroduce):** `jupyterlab`, `ipykernel`, `ipywidgets`
(Marimo replaces them); standalone `keras>=3.x` (Keras 3 ships bundled with TF
2.16+ and is exposed as both `tf.keras` and bare `keras`; a separate pin pulls a
parallel minor and silently fights TF's bundled copy); `conda-lock` (no conda —
pip-tools `pip-compile --generate-hashes` is the venv lock path, deferred to
Phase H).

---

## Package Structure

Source layout, with one-line descriptions per file:

```
nbfoundry/                                    # repo root
├── pyproject.toml                            # build backend (hatchling), deps, console script, ruff/mypy/pytest config
├── requirements-dev.txt                      # dev tools for testenv (ruff, mypy, pytest, pytest-cov, type stubs)
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
│       ├── compiler.py                       # compile_exercise + validate_exercise: YAML → Option-C dict; orchestrates load → validate → render → codegen.generate → assemble
│       ├── codegen.py                        # generate(defn, base_dir) → notebook_source string; ensure_marimo_pinned(env) helper
│       ├── schema.py                         # Pydantic models for the Option-C input (ExerciseDefinition + SectionModel + EnvironmentModel) + output TypedDict (CompiledExercise)
│       ├── markdown.py                       # markdown-it-py wrapper; respects markdown_flavor (commonmark | gfm)
│       ├── paths.py                          # path-escape protection (SC-3): resolve & verify under base_dir
│       ├── errors.py                         # ExerciseError dataclass + helpers; maps Pydantic errors → ExerciseError list
│       ├── logging_setup.py                  # stdlib logging configuration; --verbose/--quiet wiring
│       ├── config.py                         # nbfoundry.toml loader; precedence: CLI > toml > defaults
│       ├── standalone.py                     # `nbfoundry compile` artifact emitter (notebook + requirements-*.txt + launch.py)
│       ├── notebooks.py                      # Marimo notebook discovery, parse, tree walking; entry-point detection (used by `nbfoundry compile` standalone path; the Option-C exercise compile path does NOT call `notebooks.parse_all`)
│       ├── _modelfoundry.py                  # thin adapter Protocol; raises clear error when modelfoundry not importable
│       └── templates/
│           ├── __init__.py                   # importlib.resources entry point
│           ├── requirements-base.txt         # agnostic core (data_* stages); -r-included by the framework files
│           ├── requirements-torch.txt        # torch-family stack (model_* stages); -r requirements-base.txt
│           ├── requirements-tf.txt           # TF-family stack (TF-learner option); -r requirements-base.txt
│           ├── data_exploration/             # five-stage lifecycle template (Marimo .py only; stage requirements emitted by init)
│           ├── data_preparation/
│           ├── model_experimentation/
│           ├── model_optimization/
│           ├── model_evaluation/
│           └── standalone/
│               └── launch.py                 # cross-platform launcher embedded in compiled standalone artifacts
├── tests/
│   ├── conftest.py                           # shared fixtures: fixtures_dir, exercises_dir, tmp_base_dir, sample_yaml
│   ├── unit/
│   │   ├── test_build_time_purity.py         # authoritative AC-10 AST scan over the compile path (schema/compiler/codegen/cli/...) — asserts no ML framework imports at build time
│   │   ├── test_schema.py                    # ExerciseDefinition / SectionModel accept/reject; retired-name absence; CompiledExercise key set
│   │   ├── test_codegen.py                   # generate() shape + determinism + cell layout; ensure_marimo_pinned() append/passthrough cases
│   │   ├── test_compiler.py                  # FR-3 happy + first-error semantics; FR-4 collect-all; description/hints HTML rendering; code_file inlining
│   │   ├── test_markdown.py                  # commonmark vs gfm, edge cases
│   │   ├── test_paths.py                     # SC-3 path-escape: ../, absolute, symlinks
│   │   ├── test_errors.py                    # ExerciseError shape; Pydantic → ExerciseError mapping (driven by ExerciseDefinition)
│   │   ├── test_modelfoundry_adapter.py      # raises when modelfoundry missing; mockable Protocol
│   │   ├── test_config.py                    # precedence; missing toml; bad keys
│   │   ├── test_public_api.py                # public re-exports + BR-1/BR-2/BR-3 signature shape
│   │   ├── test_notebooks.py                 # Marimo notebook discovery/parse (used by `nbfoundry compile` standalone path)
│   │   ├── test_smoke_env_requirements.py    # template requirements-*.txt smoke
│   │   └── test_standalone_requirements.py   # standalone artifact requirements emission
│   ├── integration/
│   │   ├── test_cli_init.py                  # FR-1: scaffold from each of five templates
│   │   ├── test_cli_init_requirements.py     # FR-1: stage-appropriate requirements emitted alongside the scaffolded notebook
│   │   ├── test_cli_compile.py               # FR-2: standalone artifact end-to-end
│   │   ├── test_cli_compile_exercise.py      # FR-3 end-to-end via CLI; JSON stdout / --out; tree fixture exercises code_file inlining
│   │   ├── test_cli_validate.py              # FR-4 end-to-end via CLI; exit codes
│   │   ├── test_determinism.py               # OR-5: byte-stable Option-C dicts within one process and across fresh corpus copies
│   │   ├── test_marimo_loads_generated.py    # AC-2: importlib.util loads notebook_source; asserts a top-level marimo.App instance (no ML deps, no subprocess)
│   │   ├── test_no_network.py                # AC-9: sandbox proves zero network calls
│   │   └── test_e2e_*.py                     # hardware-deferred Apple Silicon Metal smokes (deselected by default; opt-in via `-m hardware`)
│   └── fixtures/
│       └── exercises/
│           ├── valid_minimal.yaml            # Option-C minimal definition
│           └── tree/                         # exercise.yaml + sections/*.py — exercises code_file inlining
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
| **Configuration files** | Hyphens or dots | `pyproject.toml`, `requirements-base.txt`, `requirements-dev.txt`, `.gitignore` |

Private modules use a leading `_` (e.g., `_modelfoundry.py`, `_version.py`).

---

## Key Component Design

Public API signatures match `learningfoundry/consumer-dependency-spec.md` BR-1 / BR-2 / BR-3 verbatim.

### `nbfoundry.compile_exercise(yaml_path: Path, base_dir: Path) -> dict` — FR-3

```python
def compile_exercise(yaml_path: Path, base_dir: Path) -> dict[str, Any]:
    """Compile an exercise definition YAML → Option-C wire dict. Raises ExerciseError on first invalid input."""
```

**Behavior (orchestration):**

1. `paths.resolve_under(base_dir, yaml_path)` — SC-3 path-escape guard. Returns the canonical resolved path; raises `ExerciseError` on escape or missing file.
2. Read and `yaml.safe_load` the file. Reject if the top-level value is not a mapping.
3. `schema.ExerciseDefinition.model_validate(data)` — Pydantic v2 (`extra="forbid"`) validates required fields (`title`, `description`, `sections[]` ≥ 1), section `code` XOR `code_file`, and optional `hints` / `environment`. Pydantic errors → `errors.from_pydantic(...)` → first `ExerciseError`.
4. For each section with `code_file`: resolve under `base_dir` via `paths.resolve_under` (SC-3 path-escape + existence). The file is NOT read here — codegen (step 5) reads it.
5. Render markdown → HTML for top-level `description` and each `hints[i]` via `markdown.render(...)`. Per `nbfoundry.toml`'s `markdown_flavor` (default `commonmark`).
6. Call `codegen.generate(defn, base_dir=base_dir)` to produce `notebook_source` (the self-contained `marimo.App()` module as a string). For each section, codegen reads `code` inline or `code_file` from disk (under the same SC-3 guard) and inlines the body into one marimo code cell.
7. Call `codegen.ensure_marimo_pinned(defn.environment)` to surface a `marimo>=<installed-version>` pin into `environment.dependencies` if the author omitted marimo, or pass through verbatim if present. Returns `None` if the author omitted `environment` entirely.
8. Construct the final dict with stable key order:

   ```python
   {
       "type": "exercise",
       "source": "nbfoundry",
       "ref": str(yaml_path),
       "title": defn.title,
       "description": rendered_description_html,
       "hints": [rendered_hint_html, ...],
       "environment": compiled_environment_or_none,
       "notebook_source": notebook_source_string,
   }
   ```
9. Return the dict. **No file writes, no network, no module imports beyond what's already declared as a runtime dep** (OR-6, SC-2, SC-4). The compile path is **build-time ML-free** (AC-10): the only Python imports invoked at build time are stdlib, `yaml`, `pydantic`, `markdown-it-py`, and other `nbfoundry.*` modules. Framework imports (`torch`, `tensorflow`, …) appear only as source text inside `notebook_source` cells.

**Edge cases:** see features.md FR-3.

### `nbfoundry.validate_exercise(yaml_path: Path, base_dir: Path) -> list[str]` — FR-4

Same input-stage pipeline as `compile_exercise` but **collects every error** instead of raising on the first, and skips the rendering / codegen stages (steps 5–8 above). YAML parse failure, non-mapping top level, or missing YAML short-circuit and return a single-element list (FR-4 edge cases).

Implementation note: `compile_exercise` and `validate_exercise` share a single `_validate(...) -> tuple[ExerciseDefinition | None, Path | None, list[ExerciseError]]` core inside `compiler.py`. `compile_exercise` raises on the first error then proceeds to the codegen + assembly stages; `validate_exercise` returns the formatted error strings. There is **no separate `validator.py`** — both functions live in `compiler.py`.

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
3. **Atomic write:** stage output into `tempfile.mkdtemp(dir=out.parent)`; copy notebooks, write the stage `requirements-*.txt` (fallback `requirements-base.txt`), write `launch.py`; `os.replace(tmp, out)` on success. Partial output never visible.
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

The build-time compile path (`compiler.py`, `codegen.py`, `schema.py`, `cli.py`, …) does **not** import this module — only the templates do (FR-7 step 2). The exclusion is enforced by `tests/unit/test_build_time_purity.py` (the sibling boundary test). The Protocol shape is **provisional**; concrete method signatures land when modelfoundry's contract is finalized (concept.md Constraints). v1 ships the adapter wired enough to run a Hello-World / spike notebook end-to-end.

---

## Data Models

All data shapes live in `schema.py` as Pydantic v2 models (input) and `TypedDict`s (output). Pydantic generates input validation with `extra="forbid"`; the `TypedDict` types the wire shape. The retired Option-B models (`RawSectionModel`, `RawExerciseModel`, `RawExpectedOutputModel`, `ExpectedRule`, `SubmissionFieldModel`, `SubmissionModel`, `CompiledSection`, `CompiledExpected*`, `CompiledSubmission*`) were deleted in Story I.b; see features.md § "Retired in v0.46.0".

### Input (parsed from YAML)

```python
class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SectionModel(_StrictModel):
    """One section of an exercise definition.

    Exactly one of `code` or `code_file` must be present. The chosen body
    lands inside one marimo code cell at compile time (codegen.py). The
    legacy `editable` flag is gone — cell editability is LearningFoundry's
    `ExerciseBlock` concern. `hide_code` (default False) opts the section's
    code cell into marimo's hidden-code state (`@app.cell(hide_code=True)`).
    """
    title: str
    description: str
    code: str | None = None
    code_file: Path | None = None
    hide_code: bool = False

    @model_validator(mode="after")
    def code_xor_code_file(self) -> Self:
        if (self.code is None) == (self.code_file is None):
            raise ValueError("exactly one of `code` or `code_file` is required")
        return self


class EnvironmentModel(_StrictModel):
    """Learner-runtime environment.

    Surfaced verbatim in the compiled output so `learningfoundry launch`
    can install the right deps before spawning marimo. ML frameworks
    declared here are imported only at notebook-run time on the learner's
    machine; the compiler never imports them.
    """
    python_version: str
    dependencies: list[str]
    setup_instructions: str


class ExerciseDefinition(_StrictModel):
    """Author-provided exercise definition (Option C input). Replaces
    the retired `RawExerciseModel`."""
    title: str
    description: str            # markdown source
    sections: Annotated[list[SectionModel], Field(min_length=1)]
    hints: list[str] = []       # each item is markdown source; compiler renders to HTML
    environment: EnvironmentModel | None = None
```

### Output (compiled artifact — Option-C wire shape)

```python
class CompiledEnvironment(TypedDict):
    python_version: str
    dependencies: list[str]
    setup_instructions: str


class CompiledExercise(TypedDict):
    """Option-C wire shape returned by `compile_exercise`.

    `description` and `hints` are HTML (banner markdown rendered by the
    compiler). `notebook_source` is a complete, self-contained
    `marimo.App()` module **as a string** — the `.py` notebook the
    learner runs locally via `marimo edit` / `marimo run`.
    """
    type: Literal["exercise"]
    source: Literal["nbfoundry"]
    ref: str
    title: str
    description: str            # rendered HTML
    hints: list[str]            # each item rendered HTML
    environment: CompiledEnvironment | None
    notebook_source: str
```

### `ErrorDetail`

```python
@dataclass(frozen=True, slots=True)
class ErrorDetail:
    section_index: int | None = None
    field_name: str | None = None
    yaml_pointer: str | None = None  # e.g. "sections[0].code_file"
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
spec_path = "requirements-base.txt"
```

**Precedence (high → low):** CLI flags → `nbfoundry.toml` → built-in defaults. Implemented in `config.load(base_dir) -> Config`, which produces an immutable `Config` dataclass that the CLI merges with parsed flag values before calling library functions.

The `[assets]` section (`max_single_asset_mb` / `warn_single_asset_mb` / `allow_large_assets`) and the corresponding `AssetsConfig` dataclass were retired in v0.46.0 with the Option-C migration (Story I.f.1). Image assets are no longer staged by the compiler; the notebook renders its own outputs at run time.

**No environment variables required for v1.**

---

## CLI Design

Console script: `nbfoundry = nbfoundry.cli:main`.

### Subcommands

| Subcommand | Synopsis | Behavior |
|---|---|---|
| `init` | `nbfoundry init <name> [--template <stage>]` | FR-1: scaffold a five-stage notebook from `templates/<stage>/` via `importlib.resources.files`. Default stage: `data_exploration`. |
| `compile` | `nbfoundry compile <notebook-or-dir> [--out <path>]` | FR-2: emit standalone artifact (atomic write). |
| `compile-exercise` | `nbfoundry compile-exercise <yaml-path> [--base-dir <path>] [--out <path>]` | FR-3: writes the 8-key Option-C JSON dict (including `notebook_source`) to `--out` if given, else stdout. |
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
| `1` | `ExerciseError`, validation failure, missing file, parse failure, `code_file` escape / missing. |
| `2` | CLI misuse (Typer default — bad flags, missing required arg). |

`stderr` carries error messages; `stdout` carries the success payload (path, JSON, scaffolded directory).

---

## Cross-Cutting Concerns

| Concern | Implementation |
|---|---|
| **Path-escape protection (SC-3)** | `paths.resolve_under(base_dir, candidate)`: reject absolute → `(base_dir / candidate).resolve(strict=True)` (raises on missing) → assert resolved path is contained under the resolved base. Symlinks are resolved before the check. |
| **No network at compile time (SC-2, AC-9)** | The compiler performs zero socket I/O. AC-9 is enforced in tests by a sandbox fixture that monkey-patches `socket.socket.connect` / `connect_ex`. The compile + validate paths must succeed under the sandbox. |
| **No code execution at compile time (SC-4)** | The compiler reads `code` / `code_file` as text and emits it as source text inside marimo code cells. No `exec`, no `eval`, no `subprocess` calls in the compile path. Python / marimo syntax is evaluated at notebook run time on the learner's machine, not at build time. |
| **Atomic writes** | `nbfoundry compile` (and `compile-exercise --out <path>`): stage output into `tempfile.mkdtemp(dir=parent)`; on success, `os.replace(tmp_dir, target)` for the directory case, or write-to-temp-file + `os.replace` for the JSON case. Partial output never visible to the user; Ctrl-C leaves the original target unchanged. |
| **Build-time purity (FR-7, AC-10)** | The build-time compile path imports **zero** ML framework — `torch`, `tensorflow`, `keras`, the HuggingFace stack (`transformers`/`datasets`/`peft`/`sentencepiece`/`tiktoken`), `optuna`, `modelfoundry`, `datarefinery`. Framework imports appear only as **source text** inside emitted `notebook_source` cells; they execute at notebook run time on the learner's machine. Enforced by `tests/unit/test_build_time_purity.py`, an authoritative AST scan parametrized over every module on the build-time compile path (`__init__.py`, `schema.py`, `compiler.py`, `codegen.py`, `cli.py`, `config.py`, `errors.py`, `logging_setup.py`, `markdown.py`, `notebooks.py`, `paths.py`, `standalone.py`). A sibling test asserts none of those modules import the `_modelfoundry.py` boundary either (the original AC-10 guarantee, carried forward). |
| **Codegen byte-stability (OR-5, FR-5)** | `codegen.generate(defn, base_dir=...)` produces a byte-identical `notebook_source` for the same input across separate process invocations: cell order = sections in input order (header + per-section markdown + code); markdown payloads emitted via `repr()` for deterministic escape rules; no timestamps or environment-derived values in the module. `__generated_with` (and the `marimo>=...` pin appended by `ensure_marimo_pinned`) is read from `importlib.metadata.version("marimo")` at gen time — not hard-coded. |
| **Determinism (OR-5) — dict + JSON** | The compiled dict literal uses a fixed key order (`CompiledExercise` above). JSON serialization uses `json.dumps(d, sort_keys=False, ensure_ascii=False, separators=(",", ": "), indent=2)` — keys are already in canonical order from the TypedDict construction; explicit non-sort keeps the human-readable order. |
| **Logging (OR-4)** | `logging_setup.configure(level)` installs a `StreamHandler` on stderr with format `%(levelname)s %(name)s: %(message)s`. Library code logs to `logging.getLogger("nbfoundry.<module>")`; CLI maps `--verbose/--quiet` to levels. No third-party logging deps. |
| **Error mapping** | All public-API exits go through `errors.ExerciseError`. Pydantic `ValidationError` → list of `ExerciseError` via `errors.from_pydantic(yaml_path, ve)` that walks `ve.errors()` and constructs a `yaml_pointer` from each `loc` tuple. |
| **License header (FR-8, SC-1)** | Every new `.py` / `.yml` / `.toml` / `.sh` file in this repo and every template file ships with an `# SPDX-License-Identifier: Apache-2.0` + `# Copyright Pointmatic` header at the top, using the comment syntax of the file type. Compiler does not inject headers into author-authored notebooks; it preserves whatever the author has (FR-8 step 3 / edge case). |

---

## Performance Implementation

v1 is **single-threaded, single-process** — all work fits well inside the budgets in features.md (PE-1: ≤1s single notebook, ≤5s tree of ≤10; PE-2: ≤500ms validate; PE-3: ≤10s warm cold-start).

| Concern | Approach |
|---|---|
| **Concurrency model** | Synchronous; no `asyncio`, no thread pool, no multiprocessing. YAML files are tiny; markdown rendering is microseconds; asset existence checks are stat calls. |
| **Resource limits** | None enforced beyond the asset size policy above. Compile is offline (PE-5) — no rate limiting, no retries, no connection pooling needed. |
| **I/O** | All reads through `pathlib.Path.read_text(encoding="utf-8")`. No streaming; files are small. The only files the exercise compile path reads are the YAML definition and any `code_file` referenced from a section. |
| **Caching** | None in v1. Re-compilation is cheap; the user-facing budget is comfortable. |
| **Marimo parse cost** | Cached by Marimo internally; `notebooks.parse_all(...)` reuses the parser across files in a tree. |

A v2 option (when curriculum-scale performance bites) is to parallelize `notebooks.parse_all` and asset existence checks via `concurrent.futures.ThreadPoolExecutor`. Out of scope for v1.

---

## Testing Strategy

Tests live under `tests/`, run via `pyve test` (which invokes the testenv's pytest against the repo). Coverage measured by `pytest-cov` on `nbfoundry/` (templates and `templates/standalone/launch.py` excluded — they're generated/runtime files; see `[tool.coverage.run] omit` in `pyproject.toml`). `tests/fixtures/` is excluded from `ruff` (`[tool.ruff] extend-exclude`) because the `code_file` snippets are intentionally cross-cell-stateful for marimo and would otherwise trip `F821` / `B018`.

| Test layer | What it covers | features.md tie-in |
|---|---|---|
| **Unit — schema** | `ExerciseDefinition` / `SectionModel` accept valid input, reject extra fields under `extra="forbid"` (legacy `editable` / `expected_outputs` / `submission`); `code` XOR `code_file`; non-empty `sections`; retired Option-B names are gone from `nbfoundry.schema`; `CompiledExercise.__annotations__` is the exact 8-key set. | TR-1 |
| **Unit — compiler core** | `compile_exercise` happy path (8-key dict, `type` / `source` / `ref`, banner markdown rendered to HTML for `description` + `hints`); `notebook_source` is valid Python; `code_file` inlined; environment None / pinned-marimo cases; determinism; first-error semantics (missing file, schema failure, legacy field, `code_file` escape, non-mapping YAML); `validate_exercise` empty / single / multi-error cases. | TR-1 |
| **Unit — codegen** | `generate()` shape (header + per-section markdown + code cells); valid Python module (`ast.parse` clean); deterministic; `__generated_with` matches installed marimo; `code_file` inlining with path-escape + missing-file rejection; `ensure_marimo_pinned` cases (None / unpinned / pinned / extras / lookalike names). | TR-1, FR-5 |
| **Unit — paths** | SC-3 path-escape: `..`, absolute, symlink-into-elsewhere, mixed-separator. | TR-1, SC-3 |
| **Unit — modelfoundry adapter** | Raises clear error when `modelfoundry` not importable; the compiler core does **not** import the adapter (subsumed by the authoritative build-time-purity scan below). | AC-10, FR-7 |
| **Unit — build-time purity** | Authoritative AST scan: every module on the build-time compile path imports zero ML framework (`torch`, `tensorflow`, `keras`, `transformers`, `datasets`, `peft`, `sentencepiece`, `tiktoken`, `optuna`, `modelfoundry`, `datarefinery`). A sibling test confirms none of those modules import the `_modelfoundry.py` boundary either. | AC-10, FR-7, TR-8 |
| **Integration — CLI** | `init`, `compile`, `compile-exercise`, `validate` end-to-end; exit codes; stdout/stderr separation; `--out` writes JSON; tree fixture exercises `code_file` inlining. | TR-3, AC-6 |
| **Integration — determinism** | Same input compiled twice produces equal dicts; same input compiled in two fresh corpus copies produces byte-identical `notebook_source`. Replaces the pre-Option-C "byte-for-byte golden JSON" check (the marimo-version-derived `__generated_with` string makes a static golden unstable; byte-stability within one toolchain installation is the right contract). | OR-5, TR-2 |
| **Integration — no-network sandbox** | Monkey-patched `socket.socket.connect` raises; `compile_exercise` and `validate_exercise` succeed without triggering it. | AC-9, SC-2 |
| **Integration — marimo loads the generated module** | `compile_exercise` returns `notebook_source`; the test loads it via `importlib.util.spec_from_file_location` and asserts the module has a top-level `marimo.App` instance. No subprocess, no marimo server, no ML deps — confirms the generated `.py` is a valid marimo module. | AC-2, TR-3 |
| **Type check** | `pyve env run mypy --strict src/nbfoundry/` passes. | TR-5, QR-4 |
| **Coverage** | `pytest-cov --cov=nbfoundry --cov-fail-under=85` passes on public modules. | TR-6 |
| **Cross-platform** | GHA matrix: macOS-latest (Apple Silicon runner) primary; ubuntu-latest stretch. Windows out of v1 CI scope. | TR-7, QR-3 |

**Fixture organization (Option C).** The exercise corpus is small: `tests/fixtures/exercises/valid_minimal.yaml` for the canonical happy path, and `tests/fixtures/exercises/tree/exercise.yaml` + `tree/sections/{load,summarize}.py` for the `code_file` flavor. Invalid permutations are written inline in the relevant test files via `tmp_path` rather than carried as a fixture-per-rejection corpus — the I.b/I.c/I.d unit tests already exercise every schema rejection branch, so a `tests/fixtures/exercises/invalid_*.yaml` corpus is no longer needed. The Option-B `tests/fixtures/golden/` directory + `valid_graded.yaml` / `valid_with_assets.yaml` corpus + `tests/fixtures/exercises/assets/` were all deleted in Story I.e.

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
| **`requirements-*.txt` distribution** | The per-stage pip requirements (`requirements-base.txt` / `requirements-torch.txt` / `requirements-tf.txt`) ship as package data so `nbfoundry init` copies the stage-appropriate file alongside the scaffolded notebook (FR-1) and compiled standalone artifacts (FR-2) include a copy for reproducibility (CR-7). |
