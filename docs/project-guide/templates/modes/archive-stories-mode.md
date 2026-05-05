Archive the completed `docs/specs/stories.md` so the next phase can start with a clean slate. The current file is moved to `docs/specs/.archive/stories-vX.Y.Z.md` (version derived from the latest story in the file), and a fresh empty `stories.md` is re-rendered from the artifact template with the `## Future` section preserved verbatim.

This mode is intended to run after all active stories are `[Done]` and before the developer plans the next phase. Phase letters continue across the archive boundary (see below).

## Prerequisites

- `docs/specs/stories.md` exists.
- Ideally, all stories in `stories.md` are `[Done]`. The mode will **warn** but not block if any are not — the developer may choose to proceed anyway (e.g. to drop deferred work).

## Steps

### 1. Read `docs/specs/stories.md`

Load the current stories file. You will need:

- The **latest versioned story heading** (`### Story X.y: vN.N.N ...`) — this becomes the archive version suffix.
- The **latest `## Phase <Letter>:` heading** — informational only, but useful to show the developer which phase is being closed.
- Whether a `## Future` section is present — it will be preserved verbatim.

### 2. Check for non-`[Done]` stories

Scan all `### Story X.y: ... [<status>]` headings. If **any** story's status is not `[Done]`, list them for the developer:

> ⚠ The following stories are not marked `[Done]`:
> - `Story J.o: v2.0.14 ... [In Progress]`
> - `Story J.r: v2.0.16 ... [Planned]`
>
> Archiving now will move these to `.archive/` along with the completed stories. You can:
> 1. Finish or explicitly drop them first, then archive.
> 2. Move them to the `## Future` section (they will carry over to the fresh `stories.md`).
> 3. Proceed anyway (they stay in the archived file only).
>
> How would you like to proceed?

Wait for the developer's decision before continuing.

### 3. Show the planned archive path

Compute the archive target:

- **Source**: `docs/specs/stories.md`
- **Latest version**: `vX.Y.Z` (from step 1)
- **Archive target**: `docs/specs/.archive/stories-vX.Y.Z.md`
- **Future section**: will be preserved (or the template default will be used if none is present)

Present this to the developer and await explicit approval.

> I will archive `docs/specs/stories.md` → `docs/specs/.archive/stories-v2.0.20.md`.
> The fresh `stories.md` will contain an empty body and carry over the current `## Future` section.
> Say "go" to proceed.

### 4. Perform the archive

After approval, run:

```bash
project-guide archive-stories
```

This CLI command wraps `project_guide.actions.perform_archive` — it moves the source to `.archive/` and re-renders a fresh `stories.md` from the bundled artifact template. If the archive target already exists (or any pre-check fails), the command raises an error and leaves the workspace untouched.

On success, the command prints the archived path, the version, the phase letter, and whether a Future section was carried.

### 5. Suggest next mode

After the archive succeeds, suggest the next step:

> ✓ Archived `stories.md` → `.archive/stories-vX.Y.Z.md` (Phase X closed).
> The fresh `stories.md` is empty and ready for the next phase.
>
> Next, run:
> ```bash
> project-guide mode {{ next_mode }}
> ```
>
> `plan_phase` will read `.archive/` to continue the phase letter sequence (e.g. if the archive's last phase was `K`, the next phase is `L`). See the Phase and Story ID Scheme below.

{% include "modes/_header-sequence.md" %}

{% include "modes/_phase-letters.md" %}
