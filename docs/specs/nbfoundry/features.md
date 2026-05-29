# features.md -- nbfoundry (Python 3.12.13)

This document defines **what** the `nbfoundry` project does -- requirements, inputs, outputs, behavior -- without specifying **how** it is implemented. This is the source of truth for scope.

For a high-level concept (why), see [`concept.md`](concept.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For project-specific must-know facts that future LLMs need to avoid blunders, see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Project Goal

nbfoundry is a Marimo-based ML/DS notebook framework that lets practitioners author a single source notebook (or tree of notebooks) and compile it into two interchangeable artifacts: (1) a **standalone Python application** the author runs locally with first-class Apple Silicon / Metal acceleration, and (2) an **`ExerciseBlock`-compatible compiled exercise** that drops into a learningfoundry curriculum per `learningfoundry-dependency-spec.md`. The framework ships opinionated five-stage lifecycle templates (data exploration → data preparation → model experimentation → model optimization → model evaluation) and is a thin orchestration layer over modelfoundry's data and modeling primitives.

### Core Requirements

- **CR-1: Two-surface compiler.** Compile a single Marimo notebook source -- or a tree of related notebooks -- into both a standalone runnable Python app and an `ExerciseBlock`-compatible exercise dict from the same source, without rewrites.
- **CR-2: Five-stage lifecycle templates.** Provide opinionated, runnable Marimo notebook templates covering data exploration, data preparation, model experimentation, model optimization, and model evaluation. Templates are framework-agnostic at the workflow level; PyTorch / TensorFlow / Keras /Scikit-learn can each fill the modeling slots.
- **CR-3: Exercise compilation API (BR-1).** Expose `compile_exercise(yaml_path, base_dir) -> dict` returning the JSON-serializable exercise artifact defined in `learningfoundry-dependency-spec.md` §BR-1, including `sections`, `expected_outputs`, `hints`, optional `submission`, and `environment`.
- **CR-4: Exercise validation API (BR-2).** Expose `validate_exercise(yaml_path, base_dir) -> list[str]` returning an empty list on success or human-readable error strings on failure, including all BR-4 validator requirements.
- **CR-5: Error contract (BR-3).** Surface a typed `ExerciseError` carrying `file_path`, `message`, and optional structured `detail` (section index, field name).
- **CR-6: Submission schema support (BR-4).** Accept, validate, and emit the optional `submission` block (`pass_threshold`, `fields[]` with `name`/`type`/`label`/`placeholder`/`expected`) so `ExerciseBlock` can produce a `score / maxScore / passed` payload.
- **CR-7: Standalone artifact.** The standalone app produced by the compiler must run locally with no server infrastructure -- a single command starts the Marimo notebook with the pinned environment.
- **CR-8: Aggregate completion event.** A compiled exercise representing a tree of notebooks emits a single aggregate completion event back to learningfoundry, not one event per leaf notebook.
- **CR-9: Modelfoundry orchestration boundary.** Internally delegate data prep, training, optimization, and evaluation primitives to modelfoundry through a clearly bounded interface so the two-surface compiler is insulated from modelfoundry's internal evolution.
- **CR-10: Pinned Apple Silicon stack.** Ship a Pyve + micromamba environment specification pinned to Python 3.12.13 with Metal-compatible PyTorch / TensorFlow / Keras / Scikit-learn versions verified to accelerate on Apple Silicon out of the box.

### Operational Requirements

- **OR-1: CLI entry point.** Provide a `nbfoundry` CLI that exposes at minimum: `compile` (notebook → standalone artifact), `compile-exercise` (notebook + exercise YAML → exercise dict / JSON), `validate` (validate an exercise YAML), and `init` (scaffold a new notebook from a five-stage template).
- **OR-2: Python library entry point.** Expose `compile_exercise`, `validate_exercise`, and `ExerciseError` as importable symbols on the top-level `nbfoundry` package.
- **OR-3: Structured errors.** All user-facing errors (CLI and library) include the offending file path and a human-readable message; library errors are catchable as `ExerciseError`.
- **OR-4: Logging.** Provide leveled logging (info / warning / error) for compile and validate operations. Default CLI verbosity is concise; a `--verbose` flag enables debug-level output.
- **OR-5: Deterministic compile.** Given the same input notebook tree and exercise YAML, `compile_exercise` returns a byte-stable JSON-serializable dict (modulo platform-dependent paths, which are normalized).
- **OR-6: No side effects beyond declared file reads.** `compile_exercise` and `validate_exercise` only read files referenced by the input YAML (and the YAML itself) under `base_dir`; they do not write files, mutate the environment, or reach the network.
- **OR-7: Environment manifest emission.** Compiled exercises include the `environment` block (Python version, dependencies, setup instructions) so a learner can reproduce the runtime locally.

### Quality Requirements

- **QR-1: Reproducibility.** A notebook authored on one Apple Silicon machine runs deterministically on another after a single `pyve` + micromamba environment install step.
- **QR-2: Minimal runtime dependencies.** The runtime package depends only on what is needed to compile and run notebooks (Marimo, the pinned ML stack via the environment spec, and a small set of utility libraries). Dev / test dependencies are isolated to the testenv.
- **QR-3: Cross-platform compile, Apple-Silicon-first runtime.** The compiler itself runs on macOS (Apple Silicon), Linux, and Windows. The runtime acceleration story is verified specifically on Apple Silicon for v1; CUDA-on-Linux is best-effort and not the primary target.
- **QR-4: Type safety.** The public Python API (`compile_exercise`, `validate_exercise`, `ExerciseError`) is fully type-annotated and passes `mypy --strict` (or project-equivalent) on the public surface.
- **QR-5: Schema fidelity to dependency spec.** The compiled exercise dict matches the schema in `learningfoundry-dependency-spec.md` §BR-1 / §BR-4 byte-for-byte at the contract level (key names, value types, optional vs. required).
- **QR-6: Loose coupling to modelfoundry.** The internal modelfoundry interface is encapsulated behind a single integration module so the modelfoundry contract can be revised without touching the compiler core.

### Usability Requirements

- **UR-1: CLI-first developer experience.** A practitioner can run `nbfoundry init <name>` to scaffold a five-stage notebook template and `nbfoundry compile` to produce a runnable standalone app, without prior knowledge of Marimo internals.
- **UR-2: Library-first integration experience.** A learningfoundry curriculum author (or build script) can `from nbfoundry import compile_exercise` and use the function exactly as specified by §BR-1 with no additional setup beyond installing the package.
- **UR-3: Newcomer ramp.** A topic enthusiast following the README can install nbfoundry, scaffold a template, and run a working data-and-model experiment within minutes on a fresh Apple Silicon machine.
- **UR-4: Author/curriculum dual-purpose path.** A practitioner who has authored a personal experimentation notebook can wrap it with an exercise YAML and produce an `ExerciseBlock`-compatible artifact without modifying the underlying notebook source.

### Non-goals

- **NG-1: No Jupyter or iPython compatibility layer.** Marimo is the only supported substrate.
- **NG-2: No Marimo WASM (Option A) for v1.** The v1 embed surface is Option B (static display) per the dependency spec; WASM is deferred.
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
- A YAML file conforming to the format in `learningfoundry-dependency-spec.md` §"Exercise Definition Format". Required top-level keys: `title`, `description`, `sections` (≥ 1). Optional: `expected_outputs`, `hints`, `submission`, `environment`.
- `sections[].code_file` paths are resolved relative to `base_dir`.

**Environment manifest:**
- A pinned Pyve + micromamba environment spec (Python 3.12.13, Metal-compatible PyTorch / TensorFlow / Keras / Scikit-learn). Authors do not edit this directly; they install via the documented one-step command.

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
- A self-contained directory containing the compiled Marimo notebook(s), an `environment.yml` (or equivalent micromamba spec), and a launch entry point. Running the entry point starts the notebook locally; no server, no cloud dependency.

**Compiled exercise dict (BR-1):**
- A JSON-serializable Python dict matching the §BR-1 schema:
  - `type`: `"exercise"`
  - `source`: `"nbfoundry"`
  - `ref`: original ref path (string)
  - `status`: `"ready"` (real content) or `"stub"` (reserved; stubs are produced by learningfoundry's stub, not nbfoundry)
  - `title`, `instructions` (HTML), `sections[]`, `expected_outputs[]`, `hints[]`
  - `assets`: `list[str]` enumerating every relative asset path the dict references (BR-5); empty list when there are no binary assets
  - `submission`: optional, conforming to §BR-4 (or `None`)
  - `environment`: `{python_version, dependencies, setup_instructions}`

For `expected_outputs[i]` of `type: image`, the compiled dict carries the **relative `path`** (verbatim from the YAML's `reference`) plus a required **`alt`** string for accessibility (WCAG 1.1.1). Asset bytes are **never** inlined — staging is learningfoundry's responsibility per BR-5.

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

### FR-3: Exercise compilation (BR-1)

`compile_exercise(yaml_path, base_dir)` (and `nbfoundry compile-exercise` CLI) compiles an exercise YAML into the §BR-1 dict.

**Behavior:**
1. Read the YAML file at `base_dir / yaml_path`.
2. Validate required fields: `title`, `description`, ≥ 1 `sections` entry.
3. Resolve every `sections[i].code_file` path relative to `base_dir`; inline its contents into `sections[i].code`. If both `code` and `code_file` are present, error.
4. Render the top-level `description` and every `sections[i].description` from Markdown to HTML; place the top-level rendered HTML into `instructions`.
5. For each `expected_outputs[i]` of `type: image`: validate that `reference` resolves to an existing file under `base_dir` (do **not** read its bytes), validate that `alt` is non-empty, and emit the relative path verbatim as `path` in the compiled dict (BR-5). For `type: text` / `type: table`, pass `content` through. Asset bytes never enter the compiled dict — staging is learningfoundry's responsibility.
6. Enumerate every relative asset path referenced by the compiled dict into a top-level `assets: list[str]` field, sorted and de-duplicated (BR-5). Empty list when there are no binary assets.
7. If `submission` is present, validate it per §BR-4 (see FR-5) and pass it through unchanged.
8. Pass through `hints` and `environment` unchanged.
9. Set `type: "exercise"`, `source: "nbfoundry"`, `ref` to the original ref path string, `status: "ready"`.
10. Return the dict (CLI: serialize to JSON on stdout or `--out` path).

**Edge Cases:**
- Missing required field -> raise `ExerciseError` naming the field.
- `code_file` path escapes `base_dir` -> raise `ExerciseError` for security.
- Both `code` and `code_file` set on one section -> raise `ExerciseError`.
- Markdown rendering failure -> raise `ExerciseError` with the section index.
- Referenced image / data file missing -> raise `ExerciseError` naming the path.
- `expected_outputs[i]` of `type: image` missing `alt` -> raise `ExerciseError` (BR-1 accessibility constraint).
- Asset path that escapes `base_dir` (`..`, absolute) -> raise `ExerciseError` (path-escape rule, see SC-3).
- Asset file exceeds the configured single-asset size limit -> raise `ExerciseError` unless overridden by `--allow-large-assets`.
- Network references in YAML -> rejected (no network reads).

### FR-4: Exercise validation (BR-2)

`validate_exercise(yaml_path, base_dir)` (and `nbfoundry validate` CLI) returns all errors found, as opposed to raising on the first.

**Behavior:**
1. Run all the FR-3 validation checks without inlining or rendering.
2. Collect every error as a human-readable string with file path and offending location.
3. Return the list (empty if valid).
4. CLI prints each error on its own line; exit `0` if empty, `1` otherwise.

**Edge Cases:**
- YAML parse error -> single error string with file path and parser message; return immediately.
- File missing entirely -> single error string; return immediately.

### FR-5: Submission schema validation (BR-4)

When the YAML carries a `submission` block, both FR-3 and FR-4 enforce §BR-4's validator requirements:

**Behavior:**
1. `pass_threshold` (if present) is a float in `[0.0, 1.0]`; reject otherwise.
2. `fields` is non-empty when `submission` is present.
3. Each field's `expected.type` is compatible with the field's `type`:
   - `range` -> `number` only.
   - `equals` -> `number` or `text`.
   - `contains_all` -> `text` only.
4. `weight` (if present) is a positive integer.
5. Field `name` values are unique within one exercise.
6. Required keys per rule are present (e.g., `range` has at least one of `min` / `max`; `equals` has `value`; `contains_all` has `values`).

**Edge Cases:**
- `pass_threshold` outside `[0.0, 1.0]` -> reject with the exact value.
- `weight: 0` or negative -> reject.
- Duplicate field names -> reject naming the duplicates.
- `range` rule on `text` field (or vice versa) -> reject naming the field.

### FR-6: Aggregate completion semantics for notebook trees

A single exercise compilation unit may correspond to a tree of notebooks. The compiled artifact remains a single exercise dict, and the eventual completion event from `ExerciseBlock` is a single aggregate event.

**Behavior:**
1. Treat the tree's entry-point YAML as the canonical source for `title`, `instructions`, `sections`, `expected_outputs`, `hints`, and `submission`.
2. When the YAML's `sections[i].code_file` references a notebook within the tree, inline a representative excerpt (or the full content, per template policy) into `sections[i].code`.
3. The output dict shape is identical to a single-notebook exercise -- the tree structure is invisible to learningfoundry.

**Edge Cases:**
- Tree references a file outside `base_dir` -> reject (FR-3 path-escape rule).
- Tree references a notebook that fails to parse -> reject with the failing file and parse error.

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
spec_path = "environment.yml"     # path to the pinned micromamba env, relative to base_dir
```

**Defaults if no config file:** `default_out = "dist/"`, `markdown_flavor = "commonmark"`, `spec_path = "environment.yml"`.

**Environment variables:** none required for v1. (No telemetry, no network, no auth.)

---

## Testing Requirements

- **TR-1: Unit-test coverage on the public API.** `compile_exercise`, `validate_exercise`, and `ExerciseError` have unit tests covering valid input, every validator rejection (including all §BR-4 cases), markdown rendering, code_file inlining, and path-escape protection.
- **TR-2: Schema conformance fixture.** A representative "ready" exercise fixture round-trips through `compile_exercise` and matches a golden JSON file byte-for-byte (modulo path normalization).
- **TR-3: CLI integration tests.** `init`, `compile`, `compile-exercise`, and `validate` are exercised end-to-end against a sample notebook tree and exercise YAML; tests assert exit codes and stdout/stderr contents.
- **TR-4: Two-environment isolation.** Tests run via `pyve test` against the dev testenv; the runtime venv is not polluted with pytest / mypy / ruff.
- **TR-5: Type checking.** `mypy` (project-equivalent strictness) passes on the public API surface.
- **TR-6: Coverage target.** ≥ 85% line coverage on the `nbfoundry` package's public modules. Templates and generated artifacts are excluded from the coverage target.
- **TR-7: Cross-platform compile smoke test.** CI runs `compile` and `compile-exercise` against the sample fixture on macOS (Apple Silicon) at minimum; Linux is a stretch target.
- **TR-8: Validator contract tests.** Each §BR-4 validator requirement (threshold range, empty fields, mismatched rule/type, duplicate names, weight ≤ 0) has a dedicated test that asserts both the rejection and the human-readable error message.

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
- **PE-3: Standalone artifact cold start.** Launching the compiled standalone app takes ≤ 10 seconds on a warm environment (dependencies already installed); first-time install of the pinned micromamba environment is bounded by the upstream stack and is not constrained here.
- **PE-4: GPU/Metal acceleration.** PyTorch / TensorFlow / Keras / Scikit-learn workloads in the standalone artifact use Metal acceleration on Apple Silicon out of the box; a smoke benchmark must show non-trivial GPU utilization on a small training step.
- **PE-5: Compiler is offline.** Compile operations make zero network calls; latency is entirely local I/O bound.

---

## Acceptance Criteria

The project is "done" for v1 when **all** of the following hold:

1. **AC-1: Public API matches the dependency spec.** `from nbfoundry import compile_exercise, validate_exercise, ExerciseError` works, and the symbols match the §BR-1 / §BR-2 / §BR-3 signatures exactly.
2. **AC-2: BR-4 submission schema fully supported.** Every validator requirement in §BR-4 is enforced; a representative graded exercise fixture compiles to a dict that drives `ExerciseBlock`'s graded path correctly (verified against learningfoundry's component test suite).
3. **AC-3: Two-surface compile.** A single notebook source compiles to both a runnable standalone app and an `ExerciseBlock`-compatible dict from the same source, demonstrated by an end-to-end fixture.
4. **AC-4: Five-stage templates ship and run.** All five lifecycle templates (data exploration, data preparation, model experimentation, model optimization, model evaluation) are scaffoldable via `nbfoundry init` and run end-to-end on Apple Silicon with Metal acceleration.
5. **AC-5: Pinned environment reproduces.** A fresh `pyve` + micromamba install on a clean Apple Silicon machine produces a working PyTorch / TensorFlow / Keras / Scikit-learn stack on Python 3.12.13 with verifiable Metal acceleration.
6. **AC-6: CLI is usable.** `nbfoundry init`, `compile`, `compile-exercise`, and `validate` all run successfully against the documented sample, with concise stdout output and structured errors on stderr.
7. **AC-7: Tests and types pass.** Unit + integration tests pass under `pyve test`; mypy passes on the public surface; coverage on public modules is ≥ 85%.
8. **AC-8: License hygiene.** Every new source file in the package and templates carries the Apache-2.0 / Pointmatic SPDX header.
9. **AC-9: Local-first, no network at compile time.** The compile / validate operations make zero network calls (verified by a sandboxed test).
10. **AC-10: Modelfoundry boundary respected.** The modelfoundry integration is contained in a single module; the compiler core has no direct modelfoundry imports.
