# features.md -- nbfoundry (Python 3.12.13)

This document defines **what** the `nbfoundry` project does -- requirements, inputs, outputs, behavior -- without specifying **how** it is implemented. This is the source of truth for scope.

For a high-level concept (why), see [`concept.md`](concept.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For project-specific must-know facts that future LLMs need to avoid blunders, see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Project Goal

nbfoundry is a Marimo-based ML/DS notebook framework that lets practitioners author a single source definition and compile it into two interchangeable artifacts: (1) a **standalone Python application** the author runs locally with first-class Apple Silicon / Metal acceleration, and (2) an **Option-C exercise dict** whose `notebook_source` field is itself a self-contained marimo notebook — emitted into a learningfoundry curriculum per `learningfoundry/consumer-dependency-spec.md`. LearningFoundry's SvelteKit `<ExerciseBlock>` component renders the banner (title / description / hints / environment); the learner runs the notebook locally via `learningfoundry launch <id>`. The framework ships opinionated five-stage lifecycle templates (data exploration → data preparation → model experimentation → model optimization → model evaluation) and is a thin orchestration layer over modelfoundry's data and modeling primitives.

### Core Requirements

- **CR-1: Two-surface compiler.** Compile a single Marimo notebook source -- or a definition that splits its sections across sibling `code_file` references -- into both a standalone runnable Python app and an Option-C exercise dict (whose `notebook_source` is itself a marimo notebook) from the same source, without rewrites.
- **CR-2: Five-stage lifecycle templates.** Provide opinionated, runnable Marimo notebook templates covering data exploration, data preparation, model experimentation, model optimization, and model evaluation. Templates are framework-agnostic at the workflow level; PyTorch / TensorFlow / Keras /Scikit-learn can each fill the modeling slots.
- **CR-3: Exercise compilation API (BR-1).** Expose `compile_exercise(yaml_path, base_dir) -> dict` returning the JSON-serializable Option-C wire shape defined in `learningfoundry/consumer-dependency-spec.md` §BR-1: `{type, source, ref, title, description, hints, environment, notebook_source}`. `notebook_source` is a self-contained `marimo.App()` module **as a string**; the learner runs it locally via `marimo edit` / `marimo run`.
- **CR-4: Exercise validation API (BR-2).** Expose `validate_exercise(yaml_path, base_dir) -> list[str]` returning an empty list on success or human-readable error strings on failure (collect-all-errors semantics).
- **CR-5: Error contract (BR-3).** Surface a typed `ExerciseError` carrying `file_path`, `message`, and optional structured `detail` (section index, field name).
- **CR-6: Generated marimo notebook (Option C).** Generate the `notebook_source` field as a byte-stable, self-contained `marimo.App()` module from an `ExerciseDefinition` input. Cell layout: one header cell (banner markdown), then per-section one `mo.md(...)` cell and one code cell. All auto-generated markdown cells (the banner and the per-section header cells) are emitted with hidden code (`@app.cell(hide_code=True)`) since they are pure presentation; code cells are visible by default and hideable per-section via `hide_code`. Framework imports (e.g. `import torch`) appear only as **source text** inside emitted cells; the compiler imports no ML framework at build time (FR-7 / AC-10).
- **CR-7: Standalone artifact.** The standalone app produced by the compiler must run locally with no server infrastructure -- a single command starts the Marimo notebook with the pinned environment.
- **CR-8: Multi-section exercises from one definition.** An exercise definition with multiple `sections` (each either inline `code` or a `code_file` reference) compiles to a single `notebook_source` module. The marimo notebook is the unit the learner runs; the `code_file` mechanism lets authors split section bodies across sibling files without producing multiple notebooks.
- **CR-9: Modelfoundry orchestration boundary.** Internally delegate data prep, training, optimization, and evaluation primitives to modelfoundry through a clearly bounded interface so the two-surface compiler is insulated from modelfoundry's internal evolution.
- **CR-10: Pinned Apple Silicon stack.** Ship Pyve + venv per-stage pip requirements (`requirements-base.txt` / `requirements-torch.txt` / `requirements-tf.txt`) targeting Python 3.12.13 with Metal-compatible PyTorch / TensorFlow / Keras / Scikit-learn verified to accelerate on Apple Silicon out of the box. (The Metal stack is fully pip-installable — `tensorflow-macos` / `tensorflow-metal` and torch's MPS build are PyPI wheels — so no conda/micromamba is required.)

### Operational Requirements

- **OR-1: CLI entry point.** Provide a `nbfoundry` CLI that exposes at minimum: `compile` (notebook → standalone artifact), `compile-exercise` (notebook + exercise YAML → exercise dict / JSON), `validate` (validate an exercise YAML), and `init` (scaffold a new notebook from a five-stage template).
- **OR-2: Python library entry point.** Expose `compile_exercise`, `validate_exercise`, and `ExerciseError` as importable symbols on the top-level `nbfoundry` package.
- **OR-3: Structured errors.** All user-facing errors (CLI and library) include the offending file path and a human-readable message; library errors are catchable as `ExerciseError`.
- **OR-4: Logging.** Provide leveled logging (info / warning / error) for compile and validate operations. Default CLI verbosity is concise; a `--verbose` flag enables debug-level output.
- **OR-5: Deterministic compile.** Given the same input notebook tree and exercise YAML, `compile_exercise` returns a byte-stable JSON-serializable dict (modulo platform-dependent paths, which are normalized).
- **OR-6: No side effects beyond declared file reads.** `compile_exercise` and `validate_exercise` only read files referenced by the input YAML (and the YAML itself) under `base_dir`; they do not write files, mutate the environment, or reach the network.
- **OR-7: Environment manifest emission.** Compiled exercises include the `environment` block (Python version, dependencies, setup instructions) so a learner can reproduce the runtime locally.

### Quality Requirements

- **QR-1: Reproducibility.** A notebook authored on one Apple Silicon machine runs deterministically on another after a single `pyve init` + `pip install -r requirements-<stage>.txt` step.
- **QR-2: Minimal runtime dependencies.** The runtime package depends only on what is needed to compile and run notebooks (Marimo, the pinned ML stack via the environment spec, and a small set of utility libraries). Dev / test dependencies are isolated to the testenv.
- **QR-3: Cross-platform compile, Apple-Silicon-first runtime.** The compiler itself runs on macOS (Apple Silicon), Linux, and Windows. The runtime acceleration story is verified specifically on Apple Silicon for v1; CUDA-on-Linux is best-effort and not the primary target.
- **QR-4: Type safety.** The public Python API (`compile_exercise`, `validate_exercise`, `ExerciseError`) is fully type-annotated and passes `mypy --strict` (or project-equivalent) on the public surface.
- **QR-5: Schema fidelity to dependency spec.** The compiled exercise dict matches the Option-C wire shape in `learningfoundry/consumer-dependency-spec.md` §BR-1 exactly at the contract level (key names, value types, optional vs. required). `notebook_source` content varies with the installed marimo version (the `__generated_with` string), so the contract is structural — not byte-for-byte — at the dict level; byte-stability within one toolchain installation is covered by TR-2.
- **QR-6: Loose coupling to modelfoundry.** The internal modelfoundry interface is encapsulated behind a single integration module so the modelfoundry contract can be revised without touching the compiler core.

### Usability Requirements

- **UR-1: CLI-first developer experience.** A practitioner can run `nbfoundry init <name>` to scaffold a five-stage notebook template and `nbfoundry compile` to produce a runnable standalone app, without prior knowledge of Marimo internals.
- **UR-2: Library-first integration experience.** A learningfoundry curriculum author (or build script) can `from nbfoundry import compile_exercise` and use the function exactly as specified by §BR-1 with no additional setup beyond installing the package.
- **UR-3: Newcomer ramp.** A topic enthusiast following the README can install nbfoundry, scaffold a template, and run a working data-and-model experiment within minutes on a fresh Apple Silicon machine.
- **UR-4: Author/curriculum dual-purpose path.** A practitioner who has authored a personal experimentation notebook can wrap it with an exercise YAML and produce an Option-C exercise dict (whose `notebook_source` LearningFoundry's launch CLI materializes for learners) without modifying the underlying notebook source.

### Non-goals

- **NG-1: No Jupyter or iPython compatibility layer.** Marimo is the only supported substrate.
- **NG-2: No Marimo WASM (Option A) for v1.** The v1 LearningFoundry embed surface is Option C (banner + `learningfoundry launch` + notebook-emit) per the consumer dependency spec; WASM is deferred. The earlier Option-B (static display) and graded-submission paths were retired in v0.46.0 — see "Retired in v0.46.0" below.
- **NG-3: No WYSIWYG notebook editor or authoring GUI.** Notebooks are authored directly in Marimo.
- **NG-4: No managed cloud platform, hosted runtime, or vendor-specific deployment** (Colab / SageMaker / Vertex). nbfoundry is local-first.
- **NG-5: No real-time multi-user collaboration on a notebook.**
- **NG-6: No user accounts, authentication, or telemetry.** Identity and progress tracking belong to learningfoundry.
- **NG-7: No reimplementation of modelfoundry primitives.** Data prep, training, optimization, and evaluation logic live in modelfoundry, not nbfoundry.
- **NG-8: No non-ML/DS exercise flavors** (interactive NN animations, simulations). Those are produced by other tools targeting the same generic `<ExerciseBlock>` scaffold.
- **NG-9: No CUDA/Linux-first acceleration tuning.** Apple Silicon Metal is the primary acceleration target; CUDA is unsupported in v1 beyond whatever the upstream stack provides.

---

## Inputs

**Author-supplied notebook source(s):**
- One or more Marimo notebooks (pure-Python `.py` files), typically scaffolded from a five-stage lifecycle template. A compilation unit is either a single notebook or a tree of related notebooks rooted at an author-declared entry point.

**Exercise definition (curriculum mode only):**
- A YAML file conforming to the Option-C `ExerciseDefinition` shape. Required top-level keys: `title`, `description`, `sections` (≥ 1). Optional: `hints` (markdown strings), `environment` (`{python_version, dependencies, setup_instructions}`).
- Each `sections[i]` has `title`, `description`, and **exactly one** of `code` (inline Python snippet) or `code_file` (relative path). Optional `hide_code: true` emits that section's code cell as `@app.cell(hide_code=True)` so the learner sees the cell's output but not its source (default `false`).
- `sections[].code_file` paths are resolved relative to `base_dir` (path-escape guarded; SC-3).

**Environment manifest:**
- Pinned Pyve + venv per-stage pip requirements (`requirements-base.txt` / `requirements-torch.txt` / `requirements-tf.txt`; Python 3.12.13, Metal-compatible PyTorch / TensorFlow / Keras / Scikit-learn). Authors do not edit these directly; they install via the documented one-step command.

**CLI flags / arguments:**
- `nbfoundry compile <notebook-or-dir> [--out <path>]`
- `nbfoundry compile-exercise <yaml-path> [--base-dir <path>] [--out <path>]`
- `nbfoundry validate <yaml-path> [--base-dir <path>]`
- `nbfoundry init <name> [--template <stage>]` -- where `<stage>` is one of the five lifecycle stages.
- Global: `--verbose`, `--quiet`, `--version`, `--help`.

**Library API arguments:**
- `compile_exercise(yaml_path: Path, base_dir: Path) -> dict`
- `validate_exercise(yaml_path: Path, base_dir: Path) -> list[str]`

## Outputs

**Standalone artifact:**
- A self-contained directory containing the compiled Marimo notebook(s), the stage-appropriate pip requirements (`requirements-*.txt`), and a launch entry point. Running the entry point starts the notebook locally; no server, no cloud dependency.

**Compiled exercise dict (BR-1, Option C):**
- A JSON-serializable Python dict matching the §BR-1 Option-C wire shape:
  - `type`: `"exercise"`
  - `source`: `"nbfoundry"`
  - `ref`: original ref path (string)
  - `title`: string
  - `description`: HTML (rendered from the YAML's `description` markdown)
  - `hints`: `list[str]` (each item HTML, rendered from the corresponding YAML markdown hint; empty list when no hints)
  - `environment`: `{python_version, dependencies, setup_instructions}` or `None`. When present, `dependencies` is guaranteed to include `marimo` (a `marimo>=<installed-version>` pin is appended if the author omitted it).
  - `notebook_source`: a complete, self-contained `marimo.App()` module **as a string** — the `.py` notebook the learner runs locally via `marimo edit` / `marimo run`.

The compiled dict is **the entire LearningFoundry handoff**: the SvelteKit banner consumes `title` / `description` / `hints` / `environment`, and `learningfoundry launch <id>` reads `notebook_source` to materialize the runnable notebook on the learner's machine. There are no static-display fields and no separate asset list — the notebook renders its own outputs at run time.

**Validation report:**
- A list of human-readable error strings (`list[str]`); empty list signals "valid".

**CLI console output:**
- `compile` / `compile-exercise`: status lines on stdout, errors on stderr, non-zero exit code on failure.
- `validate`: prints each error on its own line; exit `0` on valid, `1` on errors.
- `init`: prints the scaffolded path on success.

**Errors:**
- Library: `ExerciseError(file_path, message, detail=None)` for any malformed input.
- CLI: matching messages with exit code `1`.

---

## Functional Requirements

### FR-1: Notebook scaffolding from five-stage lifecycle templates

`nbfoundry init <name>` creates a new Marimo notebook (or directory of notebooks) seeded from one of the five lifecycle stage templates: data exploration, data preparation, model experimentation, model optimization, model evaluation.

**Behavior:**
1. Resolve `--template <stage>` to one of the five known templates; default to data exploration if omitted.
2. Copy the template's Marimo notebook source(s) into `<name>/` under the current working directory.
3. Stamp the Apache-2.0 / Pointmatic copyright header on every new file.
4. Print the created path to stdout.

**Edge Cases:**
- `<name>` already exists -> abort with a non-zero exit and a "path exists" error; do not overwrite.
- Unknown template stage -> error listing valid stages; non-zero exit.
- Read-only filesystem -> propagate the OS error with the offending path.

### FR-2: Standalone artifact compilation

`nbfoundry compile <notebook-or-dir>` produces a self-contained runnable directory.

**Behavior:**
1. Discover the notebook entry point (single file, or root-of-tree).
2. Validate that all referenced notebooks parse as Marimo notebooks.
3. Emit a target directory containing the notebook(s), a pinned environment spec, and a launch script that invokes Marimo against the entry point.
4. Print the output directory path on success.

**Edge Cases:**
- Notebook fails to parse -> abort with a clear file-and-line error; non-zero exit.
- Output path exists and is non-empty -> abort unless `--force` is passed (deferred; v1 may simply error).
- Missing referenced files inside a notebook tree -> error listing every missing reference.

### FR-3: Exercise compilation (BR-1, Option C)

`compile_exercise(yaml_path, base_dir)` (and `nbfoundry compile-exercise` CLI) compiles an exercise definition YAML into the §BR-1 Option-C wire shape.

**Behavior:**
1. Read the YAML file at `base_dir / yaml_path`; reject if the top-level value is not a mapping.
2. Validate the input against the `ExerciseDefinition` schema (Pydantic, `extra="forbid"`): required fields `title`, `description`, ≥ 1 `sections` entry, each section is `code` XOR `code_file`. Optional `hints`, `environment`. Schema-shape failures raise the **first** `ExerciseError` (`validate_exercise` collects all — see FR-4).
3. For every `sections[i].code_file`, resolve the path relative to `base_dir` via `paths.resolve_under` (raises on escape or missing file). The actual file contents are read at codegen time (FR-5), not here.
4. Render the top-level `description` and each entry in `hints` from Markdown to HTML (the schema's `commonmark` / `gfm` flavor toggle applies).
5. Call `codegen.generate(defn, base_dir=base_dir)` to produce `notebook_source` (FR-5).
6. Call `codegen.ensure_marimo_pinned(defn.environment)` to surface `marimo` into `environment.dependencies` (FR-5); `None` when the author omitted `environment`.
7. Assemble and return the 8-key dict: `{type: "exercise", source: "nbfoundry", ref: str(yaml_path), title, description, hints, environment, notebook_source}`. CLI serializes to JSON on stdout or `--out` path.

**Edge Cases:**
- Missing required field -> raise `ExerciseError` naming the field.
- `code_file` path escapes `base_dir` -> raise `ExerciseError` (SC-3).
- Both `code` and `code_file` set on one section -> raise `ExerciseError`.
- Markdown rendering failure -> raise `ExerciseError` with the section index.
- Referenced `code_file` missing -> raise `ExerciseError` naming the path.
- Network references in YAML -> rejected (no network reads).
- Top-level value is a list, scalar, or non-mapping -> raise `ExerciseError`.

### FR-4: Exercise validation (BR-2)

`validate_exercise(yaml_path, base_dir)` (and `nbfoundry validate` CLI) returns all errors found, as opposed to raising on the first.

**Behavior:**
1. Run the FR-3 schema-validation and path-escape checks without rendering markdown or generating notebook source.
2. Collect every error as a human-readable string with file path and offending location.
3. Return the list (empty if valid).
4. CLI prints each error on its own line; exit `0` if empty, `1` otherwise.

**Edge Cases:**
- YAML parse error -> single error string with file path and parser message; return immediately.
- File missing entirely -> single error string; return immediately.
- Top-level value is not a mapping -> single error string; return immediately.

### FR-5: Notebook source generation (Option C)

`codegen.generate(defn, base_dir)` turns an `ExerciseDefinition` into the `notebook_source` string. The sibling helper `codegen.ensure_marimo_pinned(env)` surfaces the marimo pin into the compiled `environment.dependencies`. Both are pure functions called by FR-3's pipeline.

**Behavior:**
1. Emit a module-level prelude: `import marimo`, `__generated_with = "<installed marimo version>"`, `app = marimo.App()`.
2. Emit one header cell that does `import marimo as mo` and renders `# {title}\n\n{description}` via `mo.md(...)`. The cell exports `mo` so subsequent markdown cells reuse it via marimo's reactive arg-injection. The header cell is emitted with hidden code (`@app.cell(hide_code=True)`) — it is pure presentation, so the learner sees the rendered banner, not the boilerplate (Story I.h).
3. For each section, emit two cells in order: a markdown cell (`mo.md('## {section.title}\n\n{section.description}')`) and a code cell whose body is the section's code (read from `code` inline or from `code_file` via `paths.resolve_under`). The markdown cell is emitted with hidden code (`@app.cell(hide_code=True)`) — like the banner, it is pure presentation (Story I.i). The code cell is hidden only when the section sets `hide_code: true`.
4. Emit a footer: `if __name__ == "__main__": app.run()`.
5. The marimo version (for `__generated_with` and the `marimo>=...` pin) is sourced at gen time via `importlib.metadata.version("marimo")`; never hard-coded.
6. `ensure_marimo_pinned(env)`: if `env` is `None`, return `None`; otherwise append `marimo>=<installed>` to `env.dependencies` only when no existing marimo specifier (with or without extras or a version) is already present.

**Invariants:**
- **Byte-stable output.** Same input → byte-identical module string across runs and processes (no timestamps, no environment-derived values).
- **Build-time purity (FR-7 / AC-10).** Framework imports (`torch`, `tensorflow`, `keras`, the HuggingFace stack, `optuna`, `modelfoundry`, `datarefinery`) appear only as **source text** inside emitted cells; `codegen.py` and the rest of the compile path import none of them.
- **Valid Python.** The generated module parses with `ast.parse` and marimo loads it as a `marimo.App`.

**Edge Cases:**
- Empty / whitespace-only code body in a section -> emit `pass` so the cell function stays syntactically valid.
- `code_file` exists but is unreadable (OSError) -> raise `ExerciseError` naming the path.
- `code_file` resolves outside `base_dir` -> raise `ExerciseError` (SC-3).

### FR-6: Multi-section exercises from `code_file` references

A single exercise definition may split its section bodies across sibling `.py` files via `sections[i].code_file`. The compiled artifact remains a single notebook (`notebook_source`); LearningFoundry never sees the on-disk file layout.

**Behavior:**
1. Treat the YAML as the canonical source for `title`, `description`, `hints`, `sections`, and `environment`.
2. For every section that uses `code_file`, the codegen step (FR-5) reads the referenced file relative to `base_dir` and inlines its contents verbatim into one marimo code cell.
3. The output dict shape is identical to a single-file exercise — the file split is invisible to LearningFoundry.

**Edge Cases:**
- `code_file` references a path outside `base_dir` -> reject (SC-3 path-escape).
- `code_file` references a missing file -> reject naming the path (`paths.resolve_under` raises during validation; FR-3 step 3).
- Multiple sections may share `code_file` references freely; no de-duplication is performed (the same file inlined twice yields two cells).

### FR-7: Modelfoundry orchestration boundary

nbfoundry depends on modelfoundry internally for data preparation, training, optimization, and evaluation primitives. The dependency is encapsulated behind a single integration module.

**Behavior:**
1. The five-stage templates import modelfoundry primitives through the integration module, not directly.
2. The compiler does not import modelfoundry; it operates on the notebook source as text/AST and on the exercise YAML.
3. When the modelfoundry interface is finalized (see Constraints in `concept.md`), revisions land entirely within the integration module.

**Edge Cases:**
- modelfoundry unavailable at runtime -> templates raise a clear "modelfoundry required" error (compile-time success is preserved).
- modelfoundry interface drift -> caught by the integration module's tests, not by every template.

### FR-8: Apache-2.0 / Pointmatic copyright header on every new source file

Every source file produced by nbfoundry (templates, scaffolds, generated standalone artifacts) carries an Apache-2.0 SPDX header attributing copyright to Pointmatic, using the comment syntax appropriate to the file type.

**Behavior:**
1. Templates ship with the header in place.
2. `nbfoundry init` does not strip or modify the header when scaffolding.
3. The compiler preserves the author's existing header on hand-authored notebooks; it does not inject one.

**Edge Cases:**
- Author has stripped the header -> compiler does not re-inject; that is the author's choice.

---

## Retired in v0.46.0

Phase I migrated the LearningFoundry consumer contract from Option B (static display) to Option C (banner + `learningfoundry launch` + notebook-emit). The following requirements are retired in this release; they are listed here so cross-references from older commits, fixtures, or external docs resolve to a documented status rather than vanishing silently:

- **BR-4 (graded submission schema).** Authors no longer declare a `submission` block with `pass_threshold` / `fields[]` / `expected` rules. Grading is parked in `stories.md` § "Future" as a future marimo-cell-output concern; if it returns, it will be via a new BR-* slot, not by reinstating BR-4.
- **BR-5 (image asset enumeration).** Authors no longer declare `expected_outputs` with image references; the compiled dict no longer carries an `assets: list[str]` field; `--allow-large-assets` (CLI flag and `compile_exercise(..., allow_large_assets=...)` kwarg) is gone. The notebook renders its own outputs at run time; LearningFoundry no longer stages binary assets.
- **`status: "ready"` / `instructions` / `sections[]` / `expected_outputs[]` / `submission` / `assets` wire fields.** All retired from the BR-1 dict in favor of the 8-key Option-C shape (see Outputs above and CR-3).
- **`editable` per-section flag.** Cell editability is LearningFoundry's `ExerciseBlock` concern under Option C; `nbfoundry`'s `SectionModel` no longer accepts it.

BR-1, BR-2, BR-3 are preserved (they describe the public API surface, not the wire shape) and their numbering is intentionally not renumbered to keep cross-references stable.

---

## Configuration

**Configuration precedence (high to low):**
1. CLI flags.
2. Per-project `nbfoundry.toml` at `base_dir` (if present).
3. Built-in defaults.

**`nbfoundry.toml` (optional, v1):**

```toml
[compile]
default_out = "dist/"

[exercise]
markdown_flavor = "commonmark"   # commonmark | gfm

[environment]
spec_path = "requirements-base.txt"   # path to the pinned venv/pip requirements, relative to base_dir
```

**Defaults if no config file:** `default_out = "dist/"`, `markdown_flavor = "commonmark"`, `spec_path = "requirements-base.txt"`.

**Environment variables:** none required for v1. (No telemetry, no network, no auth.)

---

## Testing Requirements

- **TR-1: Unit-test coverage on the public API.** `compile_exercise`, `validate_exercise`, and `ExerciseError` have unit tests covering valid input, every schema rejection (extra-field, code-XOR-code_file, empty sections, etc.), markdown rendering of `description` + `hints`, `code_file` inlining, and path-escape protection.
- **TR-2: Compile is byte-stable.** A representative exercise fixture compiles twice within one process and across separate process invocations to byte-identical dicts (`notebook_source` included). Replaces the pre-Option-C "golden JSON byte-for-byte" check, which is incompatible with the marimo-version-derived `__generated_with` string in `notebook_source`.
- **TR-3: CLI integration tests.** `init`, `compile`, `compile-exercise`, and `validate` are exercised end-to-end against the Option-C fixture corpus (`valid_minimal.yaml` plus a `tree/` fixture exercising `code_file`); tests assert exit codes, JSON output shape, and stdout/stderr contents. A `marimo`-loads-the-generated-module smoke imports `notebook_source` via `importlib.util` and asserts a top-level `marimo.App` instance (no ML deps, no subprocess).
- **TR-4: Two-environment isolation.** Tests run via `pyve test` against the dev testenv; the runtime venv is not polluted with pytest / mypy / ruff.
- **TR-5: Type checking.** `mypy --strict` passes on `src/nbfoundry/` (the typed public + internal surface).
- **TR-6: Coverage target.** ≥ 85% line coverage on the `nbfoundry` package's public modules. Templates and generated artifacts are excluded from the coverage target.
- **TR-7: Cross-platform compile smoke test.** CI runs `compile` and `compile-exercise` against the sample fixture on macOS (Apple Silicon) at minimum; Linux is a stretch target.
- **TR-8: Build-time purity (AC-10).** An authoritative AST scan asserts that every module on the build-time compile path (`schema.py`, `compiler.py`, `codegen.py`, `cli.py`, plus the `__init__.py` re-export surface and supporting modules) imports **none** of the forbidden ML packages (`torch`, `tensorflow`, `keras`, `transformers`, `datasets`, `peft`, `sentencepiece`, `tiktoken`, `optuna`, `modelfoundry`, `datarefinery`). Framework imports may only appear as **source text** inside the generated `notebook_source` cells.

---

## Security and Compliance Notes

- **SC-1: License and copyright.** Apache-2.0; copyright Pointmatic. SPDX identifier `Apache-2.0` on all new source files.
- **SC-2: Local-first, no network reads.** `compile_exercise` and `validate_exercise` do not perform network I/O. YAML references that look like URLs are rejected.
- **SC-3: Path-escape protection.** All file references inside an exercise YAML must resolve to paths under `base_dir`; references that traverse outside (`..`, absolute paths leaving `base_dir`) are rejected with a clear error.
- **SC-4: No code execution at compile time.** The compiler reads notebook source as text/AST; it does not execute author-supplied Python during `compile_exercise` / `validate_exercise`. (The standalone artifact does run the notebook, but only when the practitioner explicitly launches it.)
- **SC-5: No secrets.** nbfoundry does not read, store, or transmit credentials. The exercise dict's `environment.dependencies` lists package names only; it does not embed credentials or registry tokens.
- **SC-6: No PII.** nbfoundry does not collect, store, or transmit personally identifying information. Identity and progress tracking are learningfoundry's concern.

---

## Performance Expectations

- **PE-1: `compile_exercise` latency.** ≤ 1 second for a typical single-notebook exercise on Apple Silicon (M-series), ≤ 5 seconds for a small notebook tree (≤ 10 notebooks). These are user-facing budgets, not micro-benchmark targets.
- **PE-2: `validate_exercise` latency.** ≤ 500 ms for a typical single-notebook exercise.
- **PE-3: Standalone artifact cold start.** Launching the compiled standalone app takes ≤ 10 seconds on a warm environment (dependencies already installed); first-time install of the pinned venv/pip requirements is bounded by the upstream stack and is not constrained here.
- **PE-4: GPU/Metal acceleration.** PyTorch / TensorFlow / Keras / Scikit-learn workloads in the standalone artifact use Metal acceleration on Apple Silicon out of the box; a smoke benchmark must show non-trivial GPU utilization on a small training step.
- **PE-5: Compiler is offline.** Compile operations make zero network calls; latency is entirely local I/O bound.

---

## Acceptance Criteria

The project is "done" for v1 when **all** of the following hold:

1. **AC-1: Public API matches the dependency spec.** `from nbfoundry import compile_exercise, validate_exercise, ExerciseError` works, and the symbols match the §BR-1 / §BR-2 / §BR-3 signatures exactly.
2. **AC-2: Generated notebook is marimo-loadable.** The `notebook_source` field of a successfully compiled exercise parses as valid Python and loads under `marimo.App` (verified by an integration smoke that imports the generated module and asserts a top-level `marimo.App` instance).
3. **AC-3: Two-surface compile.** A single source can produce both (a) a runnable standalone marimo notebook (via `nbfoundry compile`) and (b) an Option-C exercise dict whose `notebook_source` is itself a runnable marimo notebook (via `nbfoundry compile-exercise`), demonstrated by an end-to-end fixture.
4. **AC-4: Five-stage templates ship and run.** All five lifecycle templates (data exploration, data preparation, model experimentation, model optimization, model evaluation) are scaffoldable via `nbfoundry init` and run end-to-end on Apple Silicon with Metal acceleration.
5. **AC-5: Pinned environment reproduces.** A fresh `pyve init` + `pip install -r requirements-<stage>.txt` on a clean Apple Silicon machine produces a working PyTorch / TensorFlow / Keras / Scikit-learn stack on Python 3.12.13 with verifiable Metal acceleration.
6. **AC-6: CLI is usable.** `nbfoundry init`, `compile`, `compile-exercise`, and `validate` all run successfully against the documented sample, with concise stdout output and structured errors on stderr.
7. **AC-7: Tests and types pass.** Unit + integration tests pass under `pyve test`; mypy passes on the public surface; coverage on public modules is ≥ 85%.
8. **AC-8: License hygiene.** Every new source file in the package and templates carries the Apache-2.0 / Pointmatic SPDX header.
9. **AC-9: Local-first, no network at compile time.** The compile / validate operations make zero network calls (verified by a sandboxed test).
10. **AC-10: Modelfoundry boundary respected.** The modelfoundry integration is contained in a single module; the compiler core has no direct modelfoundry imports.
