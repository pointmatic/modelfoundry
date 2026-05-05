Define **how** the project is built -- architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns.

The high-level concept (why) should be captured in `concept.md`. The requirements and behavior (what) should be captured in `features.md`. The breakdown of this implementation plan (step-by-step tasks) should be written in `stories.md`.

## Prerequisites

Before starting, the developer must provide (or the LLM must ask for):

1. **Language / runtime** -- e.g. Python 3.14, Node 22, Go 1.23, etc.
2. **Preferred frameworks, libraries, or tools** (if any)

The approved `docs/specs/concept.md` and `docs/specs/features.md` must exist before starting this mode.

## Steps

1. Read `docs/specs/features.md` to understand the requirements.

2. Gather additional technical details from the developer (ask questions if needed):
   - runtime_and_tooling: Language version, package manager, linter, test runner, type checker
   - dependencies: Runtime, optional, system, and development dependencies with purpose for each
   - package_structure: Full directory tree with one-line descriptions per file
   - filename_conventions: Naming rules for different file types (see guidelines below)
   - key_components: For each major module -- function signatures, behavior, edge cases handled
   - data_models: Full model definitions with field types and defaults
   - configuration: Settings model with all fields, types, defaults, and precedence rules
   - cli_design: Subcommands table, shared flags, exit codes (if applicable)
   - library_api: Public API with usage examples (if applicable)
   - cross_cutting: Retry strategy, rate limiting, logging, caching, atomic writes, etc.
   - performance_implementation: Concurrency model, connection pooling, batching strategy, resource limits (if applicable)
   - testing_strategy: Unit tests, integration tests, and what each covers
   - packaging_and_distribution: Package metadata, registry (PyPI/npm/crates.io), installation methods, console scripts, package data inclusion (if applicable)

3. Generate `docs/specs/tech-spec.md` using the artifact template at `templates/artifacts/tech-spec.md`

4. Present the complete document to the developer for approval. Iterate as needed.

5. **After tech-spec approval, capture project essentials.** The **File header conventions** section is mandatory baseline content — pre-fill `<YEAR>`, `<OWNER>`, and `<LICENSE>` from the project's `concept.md` / `LICENSE` / `pyproject.toml` (whichever is authoritative for this mode) and remove the trailing TODO note. Do **not** ask the developer whether to include the headers — the question is only ever about *additional* facts.

   Then ask the developer whether there are any **additional** must-know facts that future LLMs would need to avoid blunders on this project — things that are **not** obvious from the tech-spec alone. Put these concrete worked examples in front of them to jog their memory (don't just name the categories — name the gotchas):

   - **Workflow rules — tool wrappers and environment conventions.** A common source of "random walks" by LLMs: multiple invocation forms all *work*, but only one is canonical. Capture which form to use so the LLM doesn't pick whatever happens to succeed first.
     - *Python invocation*: wrapper command (e.g., `pyve run python ...`, `poetry run python ...`, `hatch run python ...`, `uv run python ...`) vs `python -m ...` vs `.venv/bin/python ...`. All may execute, but only one matches the project's setup.
     - *Dev tool installation*: dedicated dev/test environment (e.g., `pyve testenv --install`, `poetry install --with dev`, `uv sync --extra dev`) vs `pip install -e ".[dev]"` into the main venv. Different isolation guarantees — the latter pollutes the runtime venv.
     - *Test invocation*: project-specific runner (e.g., `pyve test`, `poetry run pytest`, `make test`) vs bare `pytest`. Bare `pytest` may fail because the tool isn't in the active venv — that's a signal to use the wrapper, not to `pip install pytest`.
     - **Principle:** legitimate alternatives exist, but they should be intentional choices, not a random walk to whatever works.
   - **Architecture quirks** — source-of-truth vs generated/installed file locations (edit the source, not the copy); build outputs that get regenerated; files that look hand-edited but aren't.
   - **Domain conventions** — e.g., money stored in cents, all timestamps UTC, IDs are strings not ints, and similar non-obvious rules.
   - **Hidden coupling** — files that mirror each other, auto-generated code, regenerated outputs that look hand-edited.
   - **Dogfooding / meta notes** — if the project uses itself, capture the rules that keep the dogfood loop safe.

   Even if the developer has no additional facts, still create `project-essentials.md` with the file header conventions section pre-filled.

6. Generate `docs/specs/project-essentials.md` using the artifact template at `templates/artifacts/project-essentials.md`. The **File header conventions** section is mandatory; substitute `<YEAR>`, `<OWNER>`, and `<LICENSE>` with concrete values and remove the trailing TODO note. Append any additional facts the developer provided in step 5. Follow the template's heading convention: **do NOT include a top-level `#` heading** (the rendered `go.md` wrapper provides `## Project Essentials`), and use `###` for subsection headings so they nest correctly. Present the document to the developer for approval and iterate as needed.

7. Done — proceed to the next mode.

**Note:** Adapt sections to fit the project type:
- **Web apps**: Add routing, database schema, API endpoints, deployment
- **Mobile apps**: Add screen navigation, platform APIs, build targets
- **Data pipelines**: Add data models, transformations, scheduling
- **Bash utilities**: May only need sections 1-6; skip data models and API design

## Filename Convention Guidelines

Include a **Filename Conventions** section in the tech spec:

| File Type | Convention | Examples |
|-----------|------------|----------|
| **Documentation** (Markdown) | Hyphens | `getting-started.md`, `api-reference.md` |
| **Workflow files** | Hyphens | `deploy-docs.yml`, `run-tests.yml` |
| **Python modules** | Underscores (PEP 8) | `my_module.py`, `data_processor.py` |
| **Python packages** | Underscores (PEP 8) | `my_package/`, `utils/` |
| **JavaScript/TypeScript** | Hyphens or camelCase | `api-client.ts`, `dataProcessor.ts` |
| **Configuration files** | Hyphens or dots | `mkdocs.yml`, `.gitignore`, `pyproject.toml` |

{% include "modes/_header-sequence.md" %}
