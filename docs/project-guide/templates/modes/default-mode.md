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
| 6 | `{% if test_first %}code_test_first{% else %}code_direct{% endif %}` | Implement stories with fast iteration |

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
| **{% if test_first %}Test-First{% else %}Direct{% endif %}** | `project-guide mode {% if test_first %}code_test_first{% else %}code_direct{% endif %}` | {% if test_first %}TDD red-green-refactor cycle{% else %}Direct commits, fast iteration{% endif %} |
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
