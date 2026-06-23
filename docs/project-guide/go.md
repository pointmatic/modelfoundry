# Project-Guide — Calm the chaos of LLM-assisted coding

This document provides step-by-step instructions for an LLM to assist a human developer in a project. 

## How to Use Project-Guide

### For Developers
Pyve manages project-guide for you. From your project root, run `project-guide init` to scaffold the docs, then instruct your LLM as follows in the chat interface: 

```
Read `docs/project-guide/go.md`
```

After reading, the LLM will respond:
1. **First line, always:** "Mode: code_test_first." (so the developer can verify the active mode at a glance).
2. (optional) "I need more information..." followed by a list of questions or details needed.
  - LLM will continue asking until all needed information is clear.
3. "The next step is ___."
4. "Say 'go' when you're ready." 

For efficiency, when you change modes, start a new LLM conversation. 

### For LLMs

**Modes**
This Project-Guide offers a human-in-the-loop workflow for you to follow that can be dynamically reconfigured based on the project `mode`. Each `mode` defines a focused cycle of steps to guide you (the LLM) to help generate artifacts for some facet in the project lifecycle. This document is customized for code_test_first.

**Approval Gate**
When you have completed the steps, pause for the developer to review, correct, redirect, or ask questions about your work.  

**Rules**
- Work through each step methodically, presenting your work for approval before continuing a cycle. 
- When the developer says "go" (or equivalent like "continue", "next", "proceed"), continue with the next action. 
- If the next action is unclear, tell the developer you don't have a clear direction on what to do next, then suggest something. 
- **Step references include the step's name on first mention in a response.** Naked references like "Step 2" mean nothing to a developer who isn't authoring the mode template. On first mention in a response, pair the number with the step's name in parens — e.g., "Cycle Step 1 (read stories) done; per Step 2 (announce next story), …". Subsequent references in the same response can use the bare number after context is established.
- Never auto-advance past an approval gate—always wait for explicit confirmation. 
- At approval gates, present the completed work and wait. Do **not** propose follow-up actions outside the current mode step — in particular, do not prompt for git operations (commits, pushes, PRs, branch creation), CI runs, or deploys unless the current step explicitly calls for them. The developer initiates these on their own schedule.
- **Scope of authority — structural changes to `stories.md`.** This mode may append new stories under an **existing** `## Phase <Letter>:` heading and edit existing story bodies (status flips, task checkboxes, body prose), but may **not** create new `## Phase` headings, re-theme existing phases, or move stories between phases. Phase creation — the phase heading, its theme paragraph, and the bundle of stories it owns — is the exclusive job of `plan_phase` (or `plan_production_phase` post-1.0). If the current mode's work surfaces scope that feels architecturally distinct from the current phase's theme, **recommend** at the approval gate that the developer run `plan_phase` to draft a new phase; do not unilaterally start one. The developer may agree, redirect, or ask you to draft a phase proposal for their review — still as a recommendation, not an executed action. Subphase headings (`## Subphase <Letter>-N:`) under an existing `## Phase <Letter>:` heading are structural sub-groupings, not new phases; they are created under the same authority that created the phase and may be added by subsequent `plan_production_phase` invocations under that same phase (see `_phase-letters.md` § "Subphases").
- **Sequential, story-by-story documentation.** Every chunk of LLM-produced work that lands in the repo — code, tests, docs, templates — is captured as a single story in `docs/specs/stories.md` under the existing phase, in the order performed. One coherent unit of work → one story → one developer commit. Don't accumulate unrecorded work across multiple turns; don't merge two distinct units into one story for tidiness; don't skip the story because the change feels small. If the work is worth doing in the repo, it is worth a story heading in `stories.md`.
- **Documentation timing.** The default sequence is: write the story with its `[ ]` checklist → execute the tasks → flip them to `[x]` → present at the approval gate. The **`debug` exception** is the only legitimate inversion: when the root cause is unknown until exploration, the sequence becomes explore → reproduce → small-scope fix → write the story (Step 5). Either way, **the story exists on disk by the time the cycle reaches its approval gate.** Entering a gate with undocumented work is not in scope for any mode.
- **Spikes for uncertainty reduction.** When the path forward is uncertain — the design choice is non-obvious, the integration boundary is unproven, the fix path may not exist — document the work as a **spike**: a time-boxed, throwaway effort whose deliverable is the documented outcome (decision / pattern / hypothesis), not production code. Three flavors are recognized: **integration spike** (will external systems connect?), **architectural spike** (will this design work?), **investigation spike** (is there a viable path at all?). Full definitions, triggers, and placement rules live in `developer/best-practices-guide.md` § "Hello World First — Spike Early, Spike Often." Picking a spike is a legitimate action when the next step is genuinely unclear — don't fabricate a confident implementation when the right move is to scope the uncertainty first.
- **Approval-gate documentation handoff.** Every approval gate presents two things together: (a) the story (or stories) reflecting the current completion state — `[x]` for done, `[ ]` for outstanding, with a one-line note on any in-progress items — and (b) the list of files changed with line references. If you reach a gate with work that is not yet captured in a story, **write or update the story before pausing**, not after the developer asks. The handoff is for a developer returning to the conversation with reduced context; it must independently name what was done, what remains, and what decision is being asked for. The story is the artifact; do not defer authoring it to the developer.
- After compacting memory, re-read this guide to refresh your context.
- **Ground yourself in the strategic context.** At the start of a working session — or whenever you enter a fresh context (a new conversation, or after compaction) — read the strategic documents that exist *before* diving into mechanics. When present, read `docs/specs/concept.md` (the *why*), `docs/specs/features.md` and `docs/specs/tech-spec.md` (the *what* and the *how*), and the repo-root `README.md`. Also discover and read any **phase/subphase plan** for the active phase: look in `docs/specs/` for `phase-<letter>-*.md` and `phase-<letter>-subphase-<n>-*.md` (e.g. Phase Q → `phase-q-*.md`; Subphase Q-4 → `phase-q-subphase-4-*.md`). These supply the abstract purpose behind the concrete task and guard against short-sighted, mechanics-only implementation. **Degrade gracefully:** any of these documents may not exist yet — early planning modes are what author them — so silently skip the ones that are absent and never treat a missing doc as an error. This is a session-start grounding pass, not a re-read-on-every-turn instruction.
- Before recording a new memory, reflect: is this fact project-specific (belongs in `docs/specs/project-essentials.md`) or cross-project (belongs in LLM memory)? Could it belong in both? If project-specific, add it to `project-essentials.md` instead of or in addition to memory.
- When creating any new source file, add a copyright notice and license header using the comment syntax for that file type (`#` for Python/YAML/shell, `//` for JS/TS, `<!-- -->` for HTML/Svelte). Check this project's `project-essentials.md` for the specific copyright holder, license, and SPDX identifier to use.
- **Bundled artifact templates** live at `docs/project-guide/templates/artifacts/` in this project (installed by `project-guide init`, refreshed by `project-guide update`). When a mode step references an artifact template by name (e.g. `concept.md`, `stories.md`, `project-essentials.md`), that is the directory to read from — do not search the filesystem, the Python install location, or `site-packages`.
- **Files under `docs/project-guide/` are install output, not source.** Static files are regenerated by `project-guide update`; `go.md` is dynamically regenerated on every `project-guide mode` invocation. Hand-edits are silently lost on the next sync **unless** the file is first marked overridden via `project-guide override <file> "<reason>"` (reverse: `project-guide unoverride <file>`). If you find yourself wanting to edit one of these files, treat it as a substantive conflict — do **not** edit silently. Flag it to the developer and surface the options:
  1. **Override and edit locally** (`project-guide override`) — for project-specific divergence the developer wants to keep.
  2. **File an issue or PR** at https://github.com/pointmatic/project-guide — for changes that would benefit every consumer of project-guide.
  3. **Wait for developer guidance** when the right path isn't obvious.

---

## Project Essentials

<!--
This file captures project-specific must-know facts that future LLMs need to
avoid blunders on the ModelFoundry project. Anything covered by the bundled
pyve-essentials artifact (auto-rendered into every `go.md` under
`## Project Essentials > ### Pyve Essentials`) is intentionally NOT duplicated
here. General engineering hygiene (e.g. logging discipline) lives in the
tech-spec, not here. Only project-specific gotchas belong below.

Heading convention: NO top-level `#` heading (the rendered `go.md` wrapper
provides `## Project Essentials`); use `###` for sibling sections.
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

- **Copyright**: `Copyright (c) 2026 Pointmatic`
- **SPDX identifier**: `SPDX-License-Identifier: Apache-2.0`

Python example:
```python
# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
```

YAML / shell example:
```yaml
# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
```

Markdown documents under `docs/` are not source files in this rule's sense
and do not carry copyright headers; the project `LICENSE` file at the repo
root is authoritative.

### Cache identity is the reproducibility contract — invalidations are ceremonious

ModelFoundry's cache key is `SHA-256(canonical_recipe_bytes) ⊕ SHA-256(data_instance_hash) ⊕ seed`. Cache directory paths use the **first 16 hex characters** of each hash; the **full hash** is recorded in `manifest.json`. Truncation is intentional — it keeps paths short and human-quotable while the full hash stays available for audit. Do not "fix" the truncation; doing so would change every cache path and orphan every existing ModelInstance on every developer's disk.

**Segmented identity (Phase I, v0.16.0).** The canonical form is no longer a flat total `model_dump`. The recipe's fields are partitioned into independently-hashed **segments** — `core` / `plugin` / `overlays` / `extensions` (`recipe/canonical.py::recipe_segments`, per the I.a spike Decision 2) — and combined by **`join_stable`**: a labeled, length-framed concatenation of per-segment SHA-256 digests. Each segment's sub-document is canonicalized with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`; an **empty segment is sparse-omitted** (contributes nothing); the combiner is **prefix-capable** (`H(H_upstream ‖ segment)`) so the deferred vertical stage-waterfall can layer on later. `canonical_bytes(recipe)` is the combiner pre-image and `recipe_hash = SHA-256(canonical_bytes)`. The recipe stays **flat on disk** — segmentation lives only in the hashing. The exact `join_stable` byte format is the **DataRefinery-coordinated family standard** (a governed shared contract — see below); confirm any change to it cross-repo.

**Every authored field still participates**, so a field rename/reorder, a change to the `join_stable` combiner, or a value change shifts the hash. **No-implicit-defaults (Phase I) means the recipe — not the model — supplies behavior-affecting values**, so there are no field-default changes to silently invalidate omitting recipes (the old hazard); the remaining identity levers are the combiner, the segment partition, and authored values. Changing the canonical-form algorithm or the partition is itself cache-invalidating.

**Pre-production rules** (current state per `features.md` OR-9): cache invalidation across ModelFoundry versions is acceptable. Note the change in the release notes; users re-materialize.

**Post-production rules** (after the production-release event — i.e. the `1.0.0` transition): any change that invalidates the cache is a **ceremonious event**, not a silent or subtle one. The blast radius is real — every existing user must re-run every recipe over every DataRefinery instance, recomputing every materialized ModelInstance. For a training job, that is potentially hours-to-days of compute per user, multiplied across every user. Therefore, every cache-invalidating change MUST:

1. **Bump the version** — the umbrella combiner version (`SUPPORTED_COMBINER_VERSIONS` in `src/modelfoundry/recipe/versioning.py`, carried as the recipe's `schema_version`) for a combiner change, or the relevant **per-segment** version (`SEGMENT_VERSIONS`) for a segment-scoped change. (`recipe/loader.py` re-exports `SUPPORTED_SCHEMA_VERSIONS` as the umbrella for back-compat.)
2. **Ship a documented migration** in `recipe.versioning.MIGRATIONS` keyed by `(segment, from_version, to_version)`, or — if no migration is possible — rely on `migrate_segment`'s refusal-with-pointer ("re-materialize"). The registry is **empty pre-1.0** (zero support window); post-1.0 segment bumps register their migration here.
3. **Announce the blast radius prominently** in release notes and in the upgrade-time CLI output: name the operation that changed, state that all existing ModelInstances are now stale, and document the recompute cost (rough order of magnitude — training is more expensive than data prep).
4. **Be reviewed deliberately.** A unit test pins the canonical hash of a representative fixture recipe; bumping that pinned value requires a reviewer to consciously sign off on the invalidation.

This applies equally whether the trigger is a pydantic default change, a canonical-form algorithm change, a plugin-implementation change that affects output bytes (e.g. a metric implementation shift), or anything else that perturbs the cache identity or the bytes the cache stores. **No silent invalidations after production release.**

**How to apply:** before merging any change in `recipe/`, `cache/`, `pipeline/`, or any plugin's `evaluation.py` / `persistence.py` (post-prod), ask "could this affect the canonical bytes or the materialized output bytes?" If yes, run the canonical-hash pinning test and check whether it would need to change. If it would, the change is cache-invalidating and must follow the ceremony above.

Modeled on DataRefinery's identical entry — the discipline travels across the project family.

### No implicit defaults — the recipe carries every behavior-affecting value (Phase I)

The interpreting code supplies **no** behavior-affecting value; the `init` scaffolder emits every value explicitly into the recipe text, so values are audit-visible, versioned, and in the canonical bytes. The param models in `src/modelfoundry/recipe/models.py` therefore carry **no value-`default=`** for behavior-affecting fields — they are author-**required** (`Training.precision` / `checkpoint_cadence` / `device`, `Evaluation.calibration_bins`, `Optimization.sampler` / `pruner` / `baseline_trial`, `Visualization.mode`, `Inference.mode` when the block is present).

The bright line is **required vs. mode-selecting-optional**:

- **Required field** = the recipe must author it; adding/removing one is a cache-invalidating schema change (bump + ceremony).
- **Mode-selecting optional** = absence is *meaningful* and maps to a behavior, so it stays `| None = None` and its "absent ⇒ behavior" mapping is part of the **versioned segment contract** (changing the mapping is a per-segment bump). Kept examples: `Inference=None ⇒ point`, `Training.early_stopping=None ⇒ none`, `Optimization=None ⇒ no HPO`, `Optimizer.schedule=None ⇒ constant LR`, `Evaluation.comparison=None`, `Data.variant=None`.
- **Invariant-not-default** = a single legal value (e.g. `Optimization.n_jobs=1`, the pre-prod determinism lock) keeps its constant; it is not an author choice.

**How to apply:** do **not** reintroduce a value-`default=` on a behavior-affecting field to "make recipes shorter" — that re-creates the silent default-shift invalidation hazard Phase I removed. New behavior-affecting fields are author-required and emitted by the scaffolder; new optional *modes* follow the mode-selecting pattern.

### Segmented identity + no-implicit-defaults is a governed cross-tool-family standard

The **horizontal segmented-identity mechanism + no-implicit-defaults** is the **DataRefinery-coordinated cross-tool-family standard** (spike §3 Governance; the four-tool family DataRefinery → ModelFoundry → nbfoundry → learningfoundry shares one identity model). This is a **stronger** commitment than the usual "the discipline travels across the family" framing used elsewhere in this doc (which means parallel independent copies): the segment boundaries, the `extensions` namespace, the no-implicit-defaults rules, and the `join_stable` byte format are a **governed shared contract**. **Diverging from it is a cross-repo coordination event, not an in-tree decision** — raise it with the family, don't fork it locally. The **vertical stage-waterfall axis is ModelFoundry's own** (deferred to a future phase); `join_stable` is kept prefix-capable so it can layer in without re-specifying the combiner. *(Open cross-repo item: DataRefinery has not yet implemented its `join_stable`; when it does, confirm the two byte formats match — see `docs/spikes/I.a-segmented-recipe-identity.md`.)*

### Loose-coupled DataRefinery binding is intentional in both directions

ModelFoundry consumes a materialized DataRefinery `Instance` (FR-6) and is **loose-coupled** to it by design (CR-15, FR-4, FR-26, and the consumer-dependency-spec's BR-9). Two specific invariants make this work:

1. **Upstream `recipe_hash` does NOT participate in the consuming ModelFoundry recipe's cache identity.** The bound DataRefinery instance is treated as a single hashed unit (`data_instance_hash16` = XOR of DataRefinery's `recipe_hash ⊕ input_hash ⊕ seed`). Re-materializing DataRefinery into the same cache directory is a **no-op** for ModelFoundry's cache identity. The user re-materializes ModelFoundry explicitly when they want to pick up upstream changes.
2. **ModelFoundry never writes to DataRefinery's cache tree.** Derived bytes (predictions, intermediate features, anything the model produces) live in ModelFoundry's own cache directory (`<cache-root>/instances/<key>/...`), never in `<datarefinery-cache>/instances/<...>/`. The vendor instance is consumed read-only.

**Why:** the four-tool family (DataRefinery → ModelFoundry → nbfoundry → learningfoundry) evolves on independent schedules. Tight upstream-downstream coupling would make a routine DataRefinery re-materialization silently invalidate every consuming ModelInstance for every user — a high-blast-radius event masquerading as a low-impact upstream tweak. The deliberate loose coupling makes the boundary inspectable: users know to re-run ModelFoundry when they re-run DataRefinery, and the cache directories stay cleanly separated for audit.

**How to apply:** when working in `src/modelfoundry/cache/identity.py`, `src/modelfoundry/pipeline/data_binding.py`, or any plugin's `data.py` adapter, refuse the following tempting moves:

- "Let's mix the bound DataRefinery instance's `recipe_hash` into the consumer's cache key so upstream changes auto-invalidate downstream." **No.** That's tight coupling — the documented future upgrade behind a `schema_version` bump (FR-26), not a pre-production enhancement. Quietly adding it would silently invalidate every existing downstream cache for every user the moment their DataRefinery cache moved.
- "Let's add a warning when the bound DataRefinery instance's `created_at` is older than the consuming ModelInstance's last materialization." **No.** Stale-downstream detection is part of the future tight-coupling FR. A pre-production warning here would either be noisy (most reads are intentional) or quietly suggest auto-invalidation is "almost" available, which it is not.
- "Let's cache derived predictions or augmented variants under `<datarefinery-cache>/...` so ModelFoundry's cache directory stays smaller." **No.** That corrupts the upstream cache identity story. DataRefinery's instance is read-only; every byte ModelFoundry produces goes in ModelFoundry's own cache tree.
- "Let's write predicted-label columns back into the bound DataRefinery instance's `dataset/<split>.jsonl` so downstream tools can read them in one place." **No.** Same reason — vendor instance is read-only. ModelFoundry's `evaluation/predictions.parquet` is the canonical predictions surface.

The path forward for tight coupling is a story under FR-26 (currently deferred to a future `schema_version` bump), not an in-band code change in `cache/` or `pipeline/`.

### Determinism contract is foundational — do not weaken it to "fix" a hard error

Per `features.md` QR-3 / FR-25 and `tech-spec.md` § Determinism plumbing, ModelFoundry's reproducibility guarantee (same `(recipe, data_instance, seed, variant)` tuple → byte-identical ModelInstance) is **conditional** on four specific plugin-side defaults:

1. **Deterministic-algorithm mode is on by default.** The PyTorch plugin calls `torch.use_deterministic_algorithms(True)` and sets `CUBLAS_WORKSPACE_CONFIG=:4096:8` before model construction. A small number of ops (atomic ops in some `scatter` / `index_select` backward paths, cuDNN conv algorithm autotune) **hard-error** under deterministic mode rather than fall back to a non-deterministic kernel.
2. **DataLoader workers are seeded per-worker from the master seed.** `pipeline.seeding.worker_init_fn_factory` produces a `worker_init_fn` that makes output bytes independent of `num_workers`. The pattern matches DataRefinery's `pipeline.workers` per-record-seed contract.
3. **Optuna trials are serial.** `Optimization.n_jobs` is locked to `1` (FR-2 check 10). Parallel trials make trial ordering non-deterministic.
4. **AMP is off by default.** Mixed-precision Tensor Core ops introduce kernel-level non-determinism. Recipes that opt into AMP via `Training.precision: "amp"` are stamped with `manifest.byte_identity_guaranteed: false` and `manifest.metric_tolerance` from the plugin's documented tolerance table.

**Why:** the reproducibility guarantee is the foundational claim ModelFoundry makes about its outputs. A byte-identical ModelInstance is what makes `clean` safe to run, makes cache hits trustworthy, makes `manifest.recipe_hash` checks meaningful, and makes the cross-repo dependency-spec contract enforceable. Silently weakening any of the four caveats means a different user (or the same user on a different machine, or under different system load) sees different bytes from "the same" recipe — which is the notebook-era problem ModelFoundry exists to fix.

**How to apply:** any change to `src/modelfoundry/plugins/pytorch/determinism.py`, `src/modelfoundry/pipeline/seeding.py`, the PyTorch plugin's `trainer.py` / `optimization.py`, or any call site that touches RNG state must preserve all four invariants. Tempting LLM mistakes to refuse:

- "Op X hard-errors under deterministic mode; let's disable deterministic mode so the user can train." **No.** That removes the byte-identity guarantee. If a recipe genuinely needs op X, the path is (a) check if a deterministic alternative exists in `torchmetrics` / `torch.nn` and use it, (b) document the limitation and refuse the recipe at validate time, or (c) raise it with the developer. Silently flipping `torch.use_deterministic_algorithms(False)` is a determinism regression.
- "Let's seed per-worker rather than per-record, since per-record seeding is wasteful." **No** — per-record seeding via `worker_init_fn` is what makes worker-count irrelevant to output bytes (mirrors DataRefinery's contract). Per-worker seeding makes output depend on `num_workers`, which is exactly what we are guarding against.
- "Let's allow `n_jobs > 1` for the Optuna stage so trials run in parallel and training finishes faster." **No.** Parallel trials produce non-deterministic trial order, which propagates into best-params selection and breaks the reproducibility contract. Parallel optimization is a future upgrade with its own design (likely a deterministic trial ordering protocol on top of the parallel harness).
- "Let's enable AMP by default since it's much faster." **No** — AMP relaxes the byte-identity guarantee to "metric-equivalent within a documented tolerance," which is a strictly weaker contract. Opt-in via `Training.precision: "amp"` is the only sanctioned path, and the manifest's `byte_identity_guaranteed: false` stamp must follow.
- "Let's add a `--allow-nondeterministic` CLI flag so users can opt out of deterministic mode at runtime." **No** — that's a recipe-semantic flag dressed as an execution-context flag (recipe-as-truth violation), AND it would invite silent weakening. If non-determinism is ever a legitimate trade-off, it goes in the recipe with the same byte-identity-guarantee stamp pattern AMP uses, not as a CLI override.
- "The trainer enables deterministic mode, so weight init is covered." **No** — weight initialization happens in `build_model`, which the plugin-agnostic runner calls *before* the trainer. The weight-init RNG must be seeded *before* `build_model`, via the runner's `prepare_for_build(seed)` hook (PyTorch: `enable_deterministic_algorithms(derive_seed(seed, "weight_init"))`), at **both** the `architecture` stage and the post-Optimization rebuild. Seeding only inside the trainer leaves initial weights drawn from the process's entropy-seeded RNG, so the same recipe trains to different weights every run — the latent bug E.e's determinism test caught (fixed in E.e.1).
- "Checkpoints can use `Checkpoint.save` (pickle), per B.k's helper." **No** — raw-pickling torch tensors is non-deterministic across equal-but-distinct tensors (the pickle embeds storage identity), so two reproducible runs produce different checkpoint bytes. The PyTorch plugin persists checkpoints with `torch.save(checkpoint.model_dump(), path)` (byte-stable); `Checkpoint`'s pickle `save`/`load` helpers are the substrate-neutral fallback, kept torch-free in `pipeline/`, not the torch persistence path.

The integration test suite includes the determinism checks in `tests/integration/test_determinism.py`: one materializes a fixture recipe twice and asserts byte-identical ModelInstance contents (excluding the wall-clock `manifest.created_at` / `manifest.elapsed_seconds` and `report.md`, which renders those same timings); another asserts the trained *output* artifacts (weights / predictions / metrics / history) are identical across `num_workers ∈ {1, 2, 4}` — note `num_workers` is a recipe field, so it legitimately perturbs `recipe.yml` and `recipe_hash`, and only the output is compared. Any change to the caveats above must keep these green; if it cannot, the change is a determinism regression and must be reverted or escalated. Modeled on DataRefinery's "Determinism contract in `pipeline.workers`" entry — the discipline travels across the project family.



### Pyve Essentials

#### Workflow rules — pyve environment conventions

This project uses `pyve` with **two separate environments**. Picking the wrong invocation form often "works" but leads to subtle drift. Use the canonical forms below:

- **Runtime code (the package itself):** `pyve run python ...` or `pyve run <entry-point> ...`.
- **Tests:** `pyve test [pytest args]` — **not** `pyve run pytest`. Pytest is not installed in the main `.venv/`; it lives in the dev test env at `.pyve/envs/testenv/venv/`, which Pyve **auto-creates (installing `pytest`) on the first `pyve test`** when the backend is venv.
- **Dev tools (ruff, mypy, pytest):** `pyve env run ruff check ...`, `pyve env run mypy ...`.
- **Provision a test env (when you need to pre-install dev tools or add another env):** the default `testenv` auto-creates on the first `pyve test`; to set one up explicitly, `pyve env init [<name>]` creates `.pyve/envs/<name>/venv/` (default name `testenv`), and `pyve env purge` removes one. See the [pyve `env` subcommand reference](https://pointmatic.github.io/pyve/usage/#env-subcommand).
- **Install dev tools:** `pyve env install -r requirements-dev.txt`. **Do not** run `pip install -e ".[dev]"` into the main venv — that pollutes the runtime environment with test-only dependencies and breaks the two-env isolation.

Pyve 3.0.x uses the env layout `.pyve/envs/<name>/<backend>/` — the default test env is `.pyve/envs/testenv/venv/`, and additional named envs live alongside it. The default `testenv` auto-creates on the first `pyve test`. Pre-3.0 projects migrate transparently the first time `pyve update` / `pyve test` / `pyve env …` runs against a 3.x binary.

If `pytest` fails with "not found" that is the signal to use `pyve test`, not to `pip install pytest` into the wrong venv. If `pyve env install` or `pyve env run` fails complaining the env doesn't exist, run `pyve test` (which auto-creates the default `testenv`) or `pyve env init` first.

#### Named test environments (`[tool.pyve.testenvs]`)

Pyve v2.8.0 introduced declarative test-env configuration in `pyproject.toml` under `[tool.pyve.testenvs]`. Each named entry can pick its `backend` (`venv` / `micromamba` / `inherit`), declare its dependency source (`requirements` / `extra` / `manifest`), and opt into lazy lifecycle (`lazy = true`). The default single-`testenv` workflow above remains identical — declaring the table is opt-in awareness for projects that need multiple test envs (e.g., a `lint` env separate from `test`, or a conda-backed env for native deps).

Project-guide does not duplicate Pyve's schema; one paragraph + a pointer. For the full schema and worked examples, see Pyve's [`testing.md` § "Named test environments"](https://pointmatic.github.io/pyve/testing/#named-test-environments).

#### `pyve update` vs. `pyve init --force`

`pyve update` is the **non-destructive** refresh path (Pyve v2.0+): preserves the env contents, refreshes Pyve-managed files (and any project-guide scaffolding pyve oversees), and is the right command for picking up a Pyve upgrade. `pyve init --force` is the **destructive** rebuild: purges and recreates the main venv. Reach for `pyve init --force` only when env contents are known-corrupt; default to `pyve update`. For diagnostics, use `pyve check` (CI-safe 0/1/2 exit codes) — Pyve v2.0 hard-removed the legacy `pyve doctor` / `pyve validate` aliases in favor of it.

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

Any story that introduces dev tooling (ruff, mypy, pytest, types-* stubs) **must** include a task to create or update `requirements-dev.txt` so that `pyve env init && pyve env install -r requirements-dev.txt` reproduces the full dev environment in two commands. This keeps the dev environment reproducible and prevents "it works on my machine" drift.

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
pyve env init                                    # one-time, creates .pyve/envs/testenv/venv/
pyve env run pip install -e .
pyve env install -r requirements-dev.txt
```
Use this when tests invoke CLI entry points (console scripts), because `pythonpath` only handles imports — it does not register entry points.

**Rule of thumb:** use `pythonpath` for library/package projects; use editable install in testenv for projects whose tests exercise CLI entry points.

**Important:** When `pyve` purges and reinitialises the main environment, the testenv remains intact and the testenv editable install survives. Re-running `pyve run pip install -e .` restores the main-environment editable install. See `developer/python-editable-install.md` for the full decision guide.


---

# code_test_first mode (cycle)

> Generate code with a test-first approach


Implement stories using test-driven development (TDD). Write a failing test before writing any implementation code.

**Next Action**
Restart the cycle of steps. 

---

## Version Cadence (quick reference)

When bumping the package version for a completed story, follow the **Version Cadence** rule documented at the top of `docs/specs/stories.md`. Quick reference:

- Bugfix or trivial change → **patch**
- Feature or improvement → **minor**
- Breaking change → **major** (post-1.0 only; only via `plan_production_phase`)
- **Phase-bundled releases:** stories within a phase can run unversioned during work; the phase ships a single release/tag at end-of-phase, with bump magnitude determined by the highest-impact change in the bundle.

**Do not extrapolate the bump magnitude from `pyproject.toml`'s current version.** Re-read `docs/specs/stories.md`'s Version Cadence section if unsure.

## Out-of-scope items in stories

When announcing a story (Step 2 in code cycles, or the equivalent gate in other cycle modes), check whether the story or its parent phase plan has an "Out of scope" section. If so, **briefly summarize those items to the developer**. They are a negotiation point — the developer may opt some items back into scope before implementation begins. Do not silently treat them as deferred.

## Story execution order

**Sequential is the strong default — not an absolute.** The next story to work on is normally the next-in-sequence `[Planned]` story in `stories.md`, and that is the right pick in the overwhelming majority of cycles. Two bounded departures are legitimate:

- **One story out of order is allowed.** Pulling a *single* `[Planned]` story ahead of its position — because it makes the *implementation* flow more naturally, unblocks the story you actually want to write next, or the developer asked for it — is fine. Do it deliberately and name it in your Step 2 (announce next story) beat so the developer can redirect cheaply. This mirrors the shipped `project-guide git-push` single-story out-of-sequence opt-in: one uncommitted `[Done]` story is unambiguous to attribute, so the wrapper offers to commit it in place rather than erroring.
- **Cherry-picking is not.** Working *multiple* stories non-sequentially — hopping around the `[Planned]` list picking whatever looks appealing — is the corrupting pattern the sequence rule exists to prevent. A scatter of out-of-order `[Done]` stories is exactly the genuine multi-story out-of-sequence state `project-guide git-push` hard-errors on (attribution across several uncommitted stories is ambiguous). One deliberate step out of line is fine; a scatter is not.

**When the sequencing itself looks wrong.** If you judge the *overall* order of `[Planned]` stories is off — a structural mis-sequence, not just one story you want to pull forward — raise it with the developer instead of silently reordering a whole bundle. Offer to do a resequencing pass (flag it as **token-expensive**: it touches IDs and their cross-references across the file), or let the developer resequence themselves. Reordering more than a single sanctioned insert is the developer's call, not yours to make unilaterally.

**If an ad-hoc request needs a new story before existing `[Planned]` work,** insert it at the correct position first (per the *Exception — developer-signaled priority insert* rule on Option 1 Append in the Phase and Story ID Scheme section) — do not append at the tail and then work it out of order.

**Recovery when already out of order.** If a story was marked `[Done]` while earlier `[Planned]` stories remain unstarted *and the result looks wrong* — a scatter, or a pulled-forward story that now strands its prerequisites — do not silently continue. Surface it and let the developer choose between (a) moving the completed story to its proper position (renumber per Option 3, allowed by the reference-accretion rule on the untouched `[Planned]` placeholders) or (b) undoing the work and restoring `[Planned]` status on the out-of-order story. Do not pick (a) or (b) unilaterally. A single, deliberate, developer-sanctioned out-of-order story is **not** a defect to recover from — leave it.

## Story scope & splitting

Story scope is re-assessed at **implementation time**, not only when the story was planned — a heading that looked right on the roadmap can prove too large once you open it.

- **Split an oversized `X.y` into an `X.y.#` bundle.** When the story as written is too big to land as one coherent unit/commit, split it into `X.y.1`, `X.y.2`, … (the pre-implementation split described in the "Sub-numbered stories" section: drop the bare `X.y` heading; the sequence becomes `…, X.x, X.y.1, X.y.2, X.z, …`). Each sub-numbered story is still one unit of work → one story → one commit.
- **Sub-numbering is also a practical ordering device.** Inserting an `X.y.1` to get the ordering you want is legitimate *even when the new story is not semantically or procedurally a child of `X.y`* — proximity in the sequence is a sufficient reason on its own, distinct from the conceptual-follow-up framing in Option 2 (Sub-number extension).
- **No 4th level.** The depth limit is hard: `X.y.#` is the floor, never `X.y.#.#`. If you are already working inside a 3-level `X.y.#` bundle and need finer ordering, either resequence the small `X.y.#` bundle or append to the existing `X.y.#` list — do not invent `X.y.1.1`.

**Brittle cross-story dependencies.** When implementation reveals that two stories depend on each other so tightly that landing one without the other leaves the tree in a bad state, you **may** offer to reorganize tasks between them into a more self-contained structure. Reserve this for **extreme** cases. Stories within a phase / subphase / bundle are normally implemented in rapid succession, so the long-term repo risk from any single story briefly breaking the build is low, and reshuffling task boundaries (and the cross-references pointing at them) usually costs more than it saves. Offer it; do not do it unilaterally.

---


## Cycle Steps

For each story:

1. **Read** the story's checklist from `docs/specs/stories.md` — always re-fetch from disk with the `Read` tool at the start of each cycle. The developer may have edited the file since you last viewed it (added tasks, reworded scope, marked items done), so do not rely on prior conversation context for its contents.
2. **Identify and announce** the intended next story to the developer **before writing any tests or implementation**. State the **story ID** (e.g., `Story B.c`), **title**, and a **one-line scope summary** of what implementing it covers. Then wait for the developer to say "go" (a precise confirmation of *this specific story*) — or to redirect you to a different story. Do not start the red-green-refactor loop on the strength of your own pick; the announce-and-wait beat exists so the developer can redirect cheaply before any code is written.
3. For each task in the checklist:
   a. **Write a failing test** that describes the expected behavior
   b. **Run the test** -- confirm it fails (red)
   c. **Write the minimal implementation** to make the test pass
   d. **Run the test** -- confirm it passes (green)
   e. **Refactor** if needed -- clean up while tests still pass
   f. **Run full test suite** -- `pyve run pytest` -- no regressions
4. **Add copyright/license headers** to every new source file
5. **Run linting** -- fix any issues immediately
6. **Mark tasks** as `[x]` in `stories.md` and change story suffix to `[Done]`
7. **Bump version** in package manifest and source — only if the story has a version assigned. **Determine the bump magnitude per the Version Cadence rule** (see `docs/specs/stories.md`'s Version Cadence section, summarized in this mode's header above): patch for bugfix, minor for feature, major for breaking (post-1.0 only via `plan_production_phase`). **Do not extrapolate from `pyproject.toml`'s current version** — re-read the cadence rule if unsure.
8. **Update CHANGELOG.md** with the version entry
9. **Present** the completed story concisely: what changed (files + line refs), verification results (test counts, lint status, red-green-refactor summary), and the suggested next story. Do not propose commits, pushes, or bundling options. Do not offer "want me to also…?" follow-ups.
10. **Wait** for the developer to say "go" before starting the next cycle. "Go" re-enters the cycle at **Step 1** — a fresh `stories.md` read and a new announce in Step 2 — never silent implementation of whatever you assumed was next.

## Red-Green-Refactor

The TDD cycle:

1. **Red** -- Write a test that fails. The test defines the desired behavior.
2. **Green** -- Write the simplest code that makes the test pass. No more.
3. **Refactor** -- Clean up the code while keeping tests green. Remove duplication, improve naming, simplify logic.

## Test Writing Guidelines

- **Test behavior, not implementation** -- assert on outputs and side effects, not internal state
- **One assertion per concept** -- each test should verify one thing
- **Use descriptive names** -- `test_override_with_nonexistent_guide_errors` not `test_override_3`
- **Prefer unit tests** -- test individual functions in isolation
- **Use integration tests sparingly** -- for verifying component interactions
- **Test edge cases** -- empty inputs, boundary values, error conditions

## Test Hierarchy

| Level | Speed | Scope | Use for |
|-------|-------|-------|---------|
| Unit | Fast | Single function | Core logic, edge cases, error paths |
| Integration | Medium | Multiple components | Verifying wiring, config loading |
| End-to-end | Slow | Full system | Final validation, smoke tests |

## When to Switch Modes

Switch to **code_direct** when:
- The story is straightforward and TDD overhead isn't justified
- The developer requests faster iteration

Switch to **debug** when:
- A bug is discovered during implementation
- Tests are failing unexpectedly and need root cause analysis

