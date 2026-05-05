Generate a combined concept/features/tech-spec document for a new phase in an existing project, then add the phase and stories to `docs/specs/stories.md`.

Use this mode when the developer wants to add a significant new capability to a project that already has an established codebase and spec documents.

## Prerequisites

Before planning a new phase, the following should exist:
- `docs/specs/concept.md`
- `docs/specs/features.md`
- `docs/specs/tech-spec.md`
- `docs/specs/stories.md`

## Steps

1. Read the existing spec documents to understand the current project state.

   `docs/specs/stories.md` may be in one of two shapes:

   a. **Populated** — contains one or more `## Phase <Letter>:` sections from prior phases. Use the highest existing phase letter as the basis for the next one (see step 5).

   b. **Empty (post-archive)** — `archive_stories` was just run and `stories.md` contains only the header and a `## Future` section, no phases. In this case, look in `docs/specs/.archive/` for files named `stories-vX.Y.Z.md`. Read the one with the highest version and find its highest `## Phase <Letter>:` heading — that is the basis for the next phase letter. Phase letters **continue across the archive boundary**; they do not reset.

   If neither `stories.md` nor `.archive/` contains any phases, this is a fresh project — start at `A`.

2. Gather information from the developer about the new phase:
   - phase_name: A short name for the phase (e.g., "Mode System", "API Integration")
   - problem_gap: What capability is missing or what problem this phase solves
   - new_features: What the phase will add (functional requirements)
   - technical_approach: How it will be built (architecture changes, new modules, new dependencies)
   - constraints: Any limitations or compatibility requirements with existing code
   - scope: What this phase will and won't do

3. Generate a phase plan document at `docs/specs/phase-<letter>-<name>-plan.md` that combines:
   - **Gap analysis**: What exists vs. what's needed
   - **Feature requirements**: What the phase adds (mini features.md)
   - **Technical changes**: New/modified modules, dependencies, config changes (mini tech-spec.md)
   - **Out of scope**: What's deferred to future phases

4. Present the phase plan to the developer for approval.

5. After approval, add a new phase section and stories to `docs/specs/stories.md`:
   - **Determine the next phase letter** by applying the algorithm from step 1:
     - If `stories.md` had existing phases, the next letter is the successor of the highest one (e.g., `K` → `L`).
     - If `stories.md` was empty but `.archive/` had a `stories-vX.Y.Z.md`, read the latest archived file, find its highest phase letter, and take its successor (e.g., archived Phase `J` → next phase `K`).
     - If neither had phases, start at `A`.
   - The successor follows the base-26-no-zero scheme (`Z` → `AA`, `ZZ` → `AAA`). See the Phase and Story ID Scheme below for details.
   - If `stories.md` was empty, **insert the new phase as the first phase** in the file (after the header and `---`, before any `## Future` section). Otherwise append after the highest existing phase but before `## Future`.
   - Break the phase into stories following the standard story format.
   - Include a spike story if the phase introduces a new integration boundary.

6. Present the updated stories to the developer for approval.

7. **After the stories are approved, append any new must-know facts to `project-essentials.md`.** Run this step **once** at the end of phase planning — not per-story.

   First, check whether `docs/specs/project-essentials.md` exists:
   - **If it does NOT exist**: this is a legacy project that has never had project-essentials captured. Create it fresh from the artifact template at `templates/artifacts/project-essentials.md`. The **File header conventions** section is mandatory baseline content — pre-fill `<YEAR>`, `<OWNER>`, and `<LICENSE>` from the project's `LICENSE` file and `pyproject.toml` (or equivalent manifest) and remove the trailing TODO note. Do **not** ask the developer whether to include the headers — the question below is only ever about *additional* facts. Note: this is the same create path as `refactor_plan`, and legacy projects are the highest-value case for a first-time capture.
   - **If it exists**: read the current content and keep it in mind for the next sub-step.

   Then ask the developer: **"Does this phase introduce any new must-know facts that future LLMs should know? New architecture boundaries, new workflow rules, new gotchas?"** Put these concrete worked examples in front of them — phase planning is specifically about *adding* capability, so the relevant gotchas are usually about interactions between the new and old worlds:

   - **New architecture boundary.** Did the phase introduce a new module, layer, or integration surface that has rules the rest of the codebase doesn't? *Example:* "Phase K adds an `archive` action type. Action handlers live in `project_guide/actions.py`; metadata registration is in `.metadata.yml`; the runtime split is that only `archive` actions fire deterministically via the CLI, while `create`/`modify` are LLM-handled. Don't add new action types without updating both files and the `VALID_ARTIFACT_ACTIONS` constant."
   - **New workflow rule or CLI contract.** Did the phase add a flag, env var, or error-message format that downstream tooling may depend on? *Example:* "Phase L added `--no-input` with a pinned error-message contract in `tests/test_cli.py::test_require_setting_contract_exit_code_and_message`. Downstream tools (pyve) may cite this message verbatim — do not change it without a coordinated release."
   - **New hidden coupling between files.** Did the phase introduce a pair of files (or a file and a generated output) that must stay in sync? *Example:* "Phase M wires the render pipeline to `docs/specs/project-essentials.md` via `_header-common.md`'s {% raw %}`{% if project_essentials %}`{% endraw %} guard — removing the guard silently breaks every render. Covered by the post-render placeholder validator from M.b."
   - **New deferred-but-documented item.** Did the phase explicitly defer something to a future phase? That deferral itself may be a must-know fact — future work on adjacent areas may accidentally re-implement what you decided to skip.
   - **Principle**: if the phase introduced a new *invariant* or *convention* that someone working in this codebase a year from now would waste an hour rediscovering, it belongs in project-essentials. If the phase was a straightforward feature addition with no new invariants, skip this step.

   **Skip if there are none.** Not every phase introduces new must-know facts. A pure feature addition that follows existing conventions does not need new project-essentials content — confirm with the developer and skip.

   If the developer provides new facts, **append** (do not rewrite or reorder) them to `docs/specs/project-essentials.md`. The append-only semantics are deliberate: `plan_phase` runs once per phase and is not the place to refactor existing project-essentials content — that's `refactor_plan`'s Final Step job. Add new `###` subsections under the appropriate category (or create a new category if none fits). Follow the artifact template's heading convention: **do NOT include a top-level `#` heading** (the rendered `go.md` wrapper provides `## Project Essentials`), and use `###` for subsections so they nest correctly.

   Present the updated file to the developer for approval. Show only what was added (since this is an append operation, the diff is minimal).

{% set next_mode = 'code_test_first' if test_first else 'code_direct' %}
{% include "modes/_header-sequence.md" %}

{% include "modes/_phase-letters.md" %}
