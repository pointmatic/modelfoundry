<!--
This file captures must-know facts future LLMs need to avoid blunders when
working on this project. Anything a smart newcomer could miss on day one and
waste time on goes here.

This content gets injected verbatim under a `## Project Essentials` section
in every rendered `go.md`, so entries below should use `###` for subsections
(not `##`, which would collide with the wrapper heading). Do NOT include a
top-level `#` title — the wrapper provides it.

What belongs here:

- **Workflow rules — tool wrappers and environment conventions.** A common
  source of "random walks" by LLMs: multiple invocation forms all *work*,
  but only one is canonical. Capture which form to use so future LLMs don't
  pick whatever happens to succeed first. Examples:
    - Python invocation (`pyve run python ...` vs `python -m ...` vs
      `.venv/bin/python ...`)
    - Dev-tool installation (dedicated testenv vs `pip install -e ".[dev]"`
      into the main venv — different isolation guarantees)
    - Test invocation (`pyve test`, `poetry run pytest`, `make test` vs
      bare `pytest`)

- **Architecture quirks.** Source-of-truth vs generated/installed file
  locations (edit the source, not the copy); build outputs that get
  regenerated; files that look hand-edited but aren't.

- **Domain conventions.** Money stored in cents, all timestamps UTC, IDs
  are strings not ints, and similar non-obvious rules.

- **Hidden coupling.** Files that mirror each other; auto-generated code;
  regenerated outputs that look hand-edited.

- **Dogfooding / meta notes.** If the project uses itself, capture the
  rules that keep the dogfood loop safe.

This file is **always** created — the **File header conventions** section
below is mandatory baseline content. Additional sections beyond file
headers are optional and should be added only when the developer
identifies real must-know facts.

The `plan_tech_spec`, `refactor_plan`, and `plan_phase` modes prompt for new
entries at natural points in the project lifecycle.

**Sibling bundled artifacts (do NOT duplicate here):** when `pyve` is
detected at init time, the bundled `templates/artifacts/pyve-essentials.md`
is auto-rendered into every `go.md` under `## Project Essentials > ### Pyve
Essentials`. That artifact is package-versioned and improves across
releases independently of this file — projects pick up upstream changes
automatically on the next `project-guide mode` invocation. Do NOT copy or
merge pyve-specific rules into this file; capture only project-specific
deviations or facts not covered by the bundled artifact.

- **File header conventions.** Mandatory baseline content. Every project
  documents the copyright holder, license, and SPDX identifier so LLMs
  apply them consistently. The LLM substitutes `<YEAR>`, `<OWNER>`, and
  `<LICENSE>` from `concept.md` / `LICENSE` / `pyproject.toml` during
  `scaffold_project` / `plan_tech_spec` / `plan_phase` create /
  `refactor_plan` create, and removes the trailing TODO note in the same
  pass — without asking the developer whether to include the headers.
-->

### File header conventions

Every new source file must begin with a copyright notice and license
identifier. Use the comment syntax for the file type:

| File type | Comment syntax |
|-----------|---------------|
| Python, YAML, shell, Makefile | `#` |
| JavaScript, TypeScript, Go, Java, C/C++ | `//` or `/* */` |
| HTML, Svelte, XML | `<!-- -->` |
| CSS, SCSS | `/* */` |

**This project's header:**

- **Copyright**: `Copyright (c) <YEAR> <OWNER>` — replace `<YEAR>` and `<OWNER>`
- **SPDX identifier**: `SPDX-License-Identifier: <LICENSE>` — e.g. `Apache-2.0`, `MIT`, `GPL-3.0-only`

Python example:
```python
# Copyright (c) <YEAR> <OWNER>
# SPDX-License-Identifier: <LICENSE>
```

TypeScript example:
```typescript
// Copyright (c) <YEAR> <OWNER>
// SPDX-License-Identifier: <LICENSE>
```

HTML example:
```html
<!-- Copyright (c) <YEAR> <OWNER> -->
<!-- SPDX-License-Identifier: <LICENSE> -->
```

> **TODO:** Replace `<YEAR>`, `<OWNER>`, and `<LICENSE>` above with this
> project's actual values, then delete this note.
