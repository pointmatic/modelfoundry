# Project-Guide — Calm the chaos of LLM-assisted coding

This document provides step-by-step instructions for an LLM to assist a human developer in a project. 

## How to Use Project-Guide

### For Developers
After installing project-guide (`pip install project-guide`) and running `project-guide init`, instruct your LLM as follows in the chat interface: 

```
Read `docs/project-guide/go.md`
```

After reading, the LLM will respond:
1. (optional) "I need more information..." followed by a list of questions or details needed. 
  - LLM will continue asking until all needed information is clear.
2. "The next step is ___."
3. "Say 'go' when you're ready." 

For efficiency, when you change modes, start a new LLM conversation. 

### For LLMs

**Modes**
This Project-Guide offers a human-in-the-loop workflow for you to follow that can be dynamically reconfigured based on the project `mode`. Each `mode` defines a focused sequence of steps to guide you (the LLM) to help generate artifacts for some facet in the project lifecycle. This document is customized for default.

**Approval Gate**
When you have completed the steps, pause for the developer to review, correct, redirect, or ask questions about your work.  

**Rules**
- Work through each step methodically, presenting your work for approval before continuing a cycle. 
- When the developer says "go" (or equivalent like "continue", "next", "proceed"), continue with the next action. 
- If the next action is unclear, tell the developer you don't have a clear direction on what to do next, then suggest something. 
- Never auto-advance past an approval gate—always wait for explicit confirmation. 
- At approval gates, present the completed work and wait. Do **not** propose follow-up actions outside the current mode step — in particular, do not prompt for git operations (commits, pushes, PRs, branch creation), CI runs, or deploys unless the current step explicitly calls for them. The developer initiates these on their own schedule.
- After compacting memory, re-read this guide to refresh your context.
- Before recording a new memory, reflect: is this fact project-specific (belongs in `docs/specs/project-essentials.md`) or cross-project (belongs in LLM memory)? Could it belong in both? If project-specific, add it to `project-essentials.md` instead of or in addition to memory.
- When creating any new source file, add a copyright notice and license header using the comment syntax for that file type (`#` for Python/YAML/shell, `//` for JS/TS, `<!-- -->` for HTML/Svelte). Check this project's `project-essentials.md` for the specific copyright holder, license, and SPDX identifier to use.

---

## Project Essentials


### Pyve Essentials

#### Workflow rules — pyve environment conventions

This project uses `pyve` with **two separate environments**. Picking the wrong invocation form often "works" but leads to subtle drift. Use the canonical forms below:

- **Runtime code (the package itself):** `pyve run python ...` or `pyve run <entry-point> ...`.
- **Tests:** `pyve test [pytest args]` — **not** `pyve run pytest`. Pytest is not installed in the main `.venv/`; it lives in the dev testenv at `.pyve/testenv/venv/`.
- **Dev tools (ruff, mypy, pytest):** `pyve testenv run ruff check ...`, `pyve testenv run mypy ...`.
- **Install dev tools:** `pyve testenv --install -r requirements-dev.txt`. **Do not** run `pip install -e ".[dev]"` into the main venv — that pollutes the runtime environment with test-only dependencies and breaks the two-env isolation.

If `pytest` fails with "not found" that is the signal to use `pyve test`, not to `pip install pytest` into the wrong venv.

#### LLM-internal vs. developer-facing invocation

`pyve run` is for the LLM's own Bash-tool invocations; developer-facing command suggestions use the bare form verbatim from the mode template.

- ✅ Developer-facing: `project-guide mode plan_phase`
- ❌ Developer-facing: `pyve run project-guide mode plan_phase`
- ✅ LLM Bash-tool: `pyve run project-guide mode plan_phase`

**Why:** the LLM's Bash-tool shell does not auto-activate `.venv/`, so the LLM must wrap its own commands with `pyve run`. The developer's shell is typically already pyve/direnv-activated, so the bare form resolves correctly and matches the commands quoted throughout mode templates and documentation.

**How to apply:** never prepend environment wrappers (`pyve run`, `poetry run`, `uv run`, etc.) to commands you quote back to the developer from a mode template. Use the wrapper only when you execute the command yourself through the Bash tool.

#### Python invocation rule

Always use `python`, never `python3`. The `python3` command bypasses `asdf` version shims and may resolve to the system interpreter rather than the project-pinned version, leading to subtle version mismatches.

#### `requirements-dev.txt` story-writing rule

Any story that introduces dev tooling (ruff, mypy, pytest, types-* stubs) **must** include a task to create or update `requirements-dev.txt` so that `pyve testenv --install -r requirements-dev.txt` reproduces the full dev environment in one step. This keeps the dev environment reproducible and prevents "it works on my machine" drift.

#### Editable install and testenv dependency management

LLMs often get confused about *where* to install an editable package when using pyve's two-environment model. The wrong choice "works" but creates subtle drift.

**Main environment only (preferred for library projects):**
```bash
pyve run pip install -e .
```
Then configure pytest to find the source tree without a second editable install:
```toml
# pyproject.toml
[tool.pytest.ini_options]
pythonpath = ["."]   # or ["src"] for src layout
```
`pythonpath` handles import discovery cleanly and avoids maintaining two editable installs with potentially diverging dependency resolution.

**Testenv editable install (required for CLI projects):**
```bash
pyve testenv run pip install -e .
pyve testenv --install -r requirements-dev.txt
```
Use this when tests invoke CLI entry points (console scripts), because `pythonpath` only handles imports — it does not register entry points.

**Rule of thumb:** use `pythonpath` for library/package projects; use editable install in testenv for projects whose tests exercise CLI entry points.

**Important:** When `pyve` purges and reinitialises the main environment, the testenv remains intact and the testenv editable install survives. Re-running `pyve run pip install -e .` restores the main-environment editable install. See `developer/python-editable-install.md` for the full decision guide.


---

# default mode (sequence)

> Getting started -- full project lifecycle overview


This is the default mode for new projects. It provides an overview of the full project lifecycle. For focused work, switch to a specific mode with `project-guide mode <name>`.

---

## Project Lifecycle

| Step | Mode | What it does |
|------|------|-------------|
| 1 | `plan_concept` | Define the problem and solution space |
| 2 | `plan_features` | Define requirements, inputs, outputs, behavior |
| 3 | `plan_tech_spec` | Define architecture, modules, dependencies |
| 4 | `plan_stories` | Break into phases and stories with checklists |
| 5 | `scaffold_project` | Scaffold LICENSE, headers, manifest, README, CHANGELOG, .gitignore |
| 6 | `code_test_first` | Implement stories with fast iteration |

## Get Started

To begin a new project, run:

```bash
project-guide mode plan_concept
```

## Suggesting the Next Step

When this mode is set, read `docs/specs/stories.md` (if it exists) and check the status of every `### Story X.y: ... [<status>]` heading.

### If all stories are `[Done]`

The current phase is complete. There is no in-progress work to resume. Suggest **both** of the following next steps to the developer and explain the trade-off:

> All stories in `stories.md` are marked `[Done]`. The current phase is finished. Two reasonable next steps:
>
> **Option A — `archive_stories` first, then `plan_phase`** (clean slate)
> ```bash
> project-guide mode archive_stories
> ```
> This moves the current `stories.md` to `docs/specs/.archive/stories-vX.Y.Z.md` and re-renders an empty `stories.md` (preserving the `## Future` section). Then `plan_phase` plans against an empty file. Phase letters continue across the archive boundary (`.archive/` is consulted to determine the next letter).
>
> *Use this when:* the completed phase is large enough that scrolling past it during planning is friction, or you want each phase as a self-contained file in `.archive/` for git history clarity.
>
> **Option B — `plan_phase` directly** (plan against history)
> ```bash
> project-guide mode plan_phase
> ```
> This appends the new phase to the existing `stories.md` alongside the completed phases.
>
> *Use this when:* the completed phases provide useful context that should remain visible during planning, or the project is still small enough that a single `stories.md` is comfortable to scroll.
>
> Which would you like?

Wait for the developer to choose before changing modes.

### If at least one story is non-`[Done]`

The current phase still has in-progress, planned, or otherwise incomplete work. Use the existing project lifecycle suggestions above — direct the developer to the relevant coding mode (`code_direct`, `code_test_first`) or, if planning artifacts are missing, to the appropriate planning mode.

### If `stories.md` does not exist

This is a fresh project. Direct the developer to `project-guide mode plan_concept` to begin the lifecycle.

## All Available Modes

### Planning (sequence)
| Mode | Command | Output |
|------|---------|--------|
| **Concept** | `project-guide mode plan_concept` | `docs/specs/concept.md` |
| **Features** | `project-guide mode plan_features` | `docs/specs/features.md` |
| **Tech Spec** | `project-guide mode plan_tech_spec` | `docs/specs/tech-spec.md` + `docs/specs/project-essentials.md` (initial) |
| **Stories** | `project-guide mode plan_stories` | `docs/specs/stories.md` |
| **Phase** | `project-guide mode plan_phase` | Add a new phase to `stories.md` + append to `project-essentials.md` |

### Scaffold (sequence)
| Mode | Command | Purpose |
|------|---------|---------|
| **Project Scaffold** | `project-guide mode scaffold_project` | One-time project scaffolding |

### Coding (cycle)
| Mode | Command | Workflow |
|------|---------|----------|
| **Test-First** | `project-guide mode code_test_first` | TDD red-green-refactor cycle |
| **Test-First** | `project-guide mode code_test_first` | TDD red-green-refactor cycle |
| **Debug** | `project-guide mode debug` | Test-driven debugging |

### Documentation (sequence)
| Mode | Command | Output |
|------|---------|--------|
| **Branding** | `project-guide mode document_brand` | `docs/specs/brand-descriptions.md` |
| **Landing Page** | `project-guide mode document_landing` | GitHub Pages + MkDocs docs |

### Post-Release (sequence)
| Mode | Command | Purpose |
|------|---------|---------|
| **Archive Stories** | `project-guide mode archive_stories` | Move completed `stories.md` to `.archive/` and re-render an empty one for the next phase |

### Refactoring (cycle)
| Mode | Command | Purpose |
|------|---------|---------|
| **Refactor Plan** | `project-guide mode refactor_plan` | Update `concept.md`/`features.md`/`tech-spec.md` for new features or legacy migration; terminal step refreshes `project-essentials.md` |
| **Refactor Document** | `project-guide mode refactor_document` | Update README, brand descriptions, landing page, and MkDocs config |

