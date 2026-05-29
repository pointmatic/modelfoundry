<!--
This file captures project-specific must-know facts that future LLMs need to
avoid blunders on the DataRefinery project. Anything covered by the bundled
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

DataRefinery's cache key is `SHA-256(canonical_recipe_bytes) ⊕ SHA-256(raw_input_bytes) ⊕ seed`. Cache directory paths use the **first 16 hex characters** of each hash; the **full hash** is recorded in `manifest.json`. Truncation is intentional — it keeps paths short and human-quotable while the full hash stays available for audit. Do not "fix" the truncation; doing so would change every cache path and orphan every existing instance on every developer's disk.

The canonical form is produced by `pydantic_model.model_dump(mode="json")` followed by `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. **This means every pydantic field default is part of the canonical bytes.** A field default change — even one that "looks like a no-op refactor" — silently shifts the canonical hash for every recipe that omits the field, invalidating every cached instance for every user.

**Pre-production rules** (current state per features.md): cache invalidation across DataRefinery versions is acceptable. Note the change in the release notes; users re-materialize.

**Post-production rules** (after the production-release event): any change that invalidates the cache is a **ceremonious event**, not a silent or subtle one. The blast radius is real — every existing user must re-run every recipe over every input, recomputing every materialized instance. That is potentially hours-to-days of compute per user, multiplied across every user. Therefore, every cache-invalidating change MUST:

1. **Bump `schema_version`** in `recipe/loader.py` (`SUPPORTED_SCHEMA_VERSIONS`).
2. **Ship a documented migration** in `recipe.loader.migrations` keyed by `(from_version, to_version)`, or — if no migration is possible — explicit refusal-with-pointer guidance in the loader.
3. **Announce the blast radius prominently** in release notes and in the upgrade-time CLI output: name the operation that changed, state that all existing instances are now stale, and document the recompute cost (rough order of magnitude).
4. **Be reviewed deliberately.** A unit test pins the canonical hash of a representative fixture recipe; bumping that pinned value requires a reviewer to consciously sign off on the invalidation.

This applies equally whether the trigger is a pydantic default change, a canonical-form algorithm change, an operation-implementation change that affects output bytes, or anything else that perturbs the cache identity or the bytes the cache stores. **No silent invalidations after production release.**

**How to apply:** before merging any change in `recipe/`, `cache/`, or `pipeline/` (post-prod), ask "could this affect the canonical bytes or the materialized output bytes?" If yes, run the canonical-hash pinning test and check whether it would need to change. If it would, the change is cache-invalidating and must follow the ceremony above.

### Sibling-instance dependencies are loose-coupled in v1

When a recipe imports fitted statistics from a sibling materialized instance via FR-TRANS-1 `stats_from_instance` (today: `normalize`, more fit-on-train ops later), the sibling's `recipe_hash` does **NOT** participate in the consuming recipe's cache identity. Re-materializing upstream does **NOT** auto-invalidate downstream — the user re-materializes downstream when upstream changes. This is the **FR-ARCH-1 loose-coupling decision** (documented in `features.md` FR-4 Edge Cases / FR-10 Behavior and in `tech-spec.md` § Caching).

**How to apply:** when extending sibling-stats functionality or touching anything in `src/datarefinery/cache/sibling_stats.py`, `src/datarefinery/pipeline/stages/transformations.py` (the `stats_from_instance` branch), or `src/datarefinery/cache/identity.py`, refuse the following tempting moves:

- "Let's mix the sibling `recipe_hash` into the consumer's cache key so upstream changes auto-invalidate downstream." **No.** That's tight coupling — the documented Future upgrade behind a `schema_version` bump, not a v1 enhancement. Quietly adding it would silently invalidate every existing downstream cache for every user the moment they `stats_from_instance`-link any recipe pair.
- "Let's add a warning when the resolver picks an instance whose `created_at` is older than the consumer's last materialization." **No.** Stale-downstream detection is also Future. A v1 warning here would either be noisy (most sibling reads are intentional) or quietly suggest auto-invalidation is "almost" available, which it is not.
- "Let's copy the sibling's `fitted_statistics/<op_id>/` into the consumer's own `fitted_statistics/` so the consuming instance is self-contained." **No.** Read-through is intentional (FR-6 #6): the consuming instance should honestly reflect "stats are owned by the sibling," not "stats are owned here too." Duplicating would also create a *third* place (after recipe text and cache key) where the upstream link is recorded, multiplying the surface where loose/tight coupling questions could re-surface.

The path forward for any of these is a story under FR-ARCH-1 (currently in Future), not an in-band code change in `cache/` or `pipeline/`.

### Recipe / manifest / report shape changes need a cross-repo coordination check

Three surfaces leave DataRefinery and bind downstream consumers (ModelFoundry today; other tools tomorrow). Any change to these shapes is a cross-repo contract change, not just an internal refactor:

1. **Recipe model** in `src/datarefinery/recipe/models.py` — every pydantic field, default, and validator becomes a contract surface the moment a release ships.
2. **Manifest schema** emitted by `pipeline.manifest.write_manifest` — every key, type, and emitted-bytes default is read by downstream tools.
3. **Report subsections** — `report/report.md`, `report/drift.json`, and persisted reporting-mode visualizations. Schema changes in `drift.json` and section ordering / heading text in `report.md` are both consumer-visible.

The authoritative cross-repo contract doc is **`docs/specs/modelfoundry/dependency-spec.md`** (Story H.s). Before changing a field name, dropping a field, changing an emitted-bytes default, renaming a manifest key, or restructuring a report subsection, **read `dependency-spec.md` first**, update it in the same commit, and decide whether the change requires a `schema_version` bump (the deliberate-invalidation lever; see § "Cache identity is the reproducibility contract" above).

**How to apply:** when working in `recipe/models.py`, `pipeline/manifest.py`, or `reporting/report.py` / `reporting/drift.py`, refuse the following tempting moves:

- "Let's drop this manifest field; nothing in this repo reads it." **No.** Internal-callers absence is not the criterion — downstream consumers (including ModelFoundry) bind against the documented manifest shape via `dependency-spec.md`. Silent removal breaks adopters. Update `dependency-spec.md`, deprecate explicitly, and follow the post-prod bump ceremony if applicable.
- "Let's rename `AugmentationOp.foo` to `bar`; it's clearer." **No, not without ceremony.** Renaming a recipe field perturbs canonical bytes for every recipe that uses it, AND breaks any cross-repo doc / tool that references the old name. A rename requires (a) `schema_version` bump in `recipe.loader.SUPPORTED_SCHEMA_VERSIONS`, (b) migration in `recipe.loader.migrations`, (c) `dependency-spec.md` update naming both old and new names with a deprecation horizon, (d) release-notes blast-radius announcement.
- "Pre-production, `drift.json` is documented as unstable, so I don't need to update `dependency-spec.md` when I change its shape." **No.** "Unstable" describes the post-prod stability commitment, not pre-prod hygiene. Pre-prod consumers (including ModelFoundry's adoption work) still read the doc to know what to bind against; not updating it as you change `drift.json` strands those consumers.

`dependency-spec.md` itself is the working document; keep it current as the source of truth. The CHANGELOG entry for each release should enumerate cross-repo contract changes prominently (see v0.15.0 for the FR-11 augmentation example).

### Recipe is authoritative for data-pipeline semantics

Configuration precedence in DataRefinery is **recipe → CLI flags → environment variables**, with a hard separation of concerns:

- **Recipe** is the single source of truth for *what the pipeline does* — sections, operations, parameters, splits, seeds, contracts.
- **CLI flags and env vars** control only *execution context* — `--cache-root`, `--log-level`, `--log-target`, `--plugin-path`, `--workers`. They never alter data-pipeline semantics.

**The only sanctioned CLI-overrides-recipe surface is `--seed`.** This is the documented ad-hoc-run case: a user wants to try the same pipeline with a different random seed without editing the recipe. The override changes the cache identity (so a different instance is produced), preserving the reproducibility contract.

**Why:** the recipe is the artifact users hand off, check into version control, and read six months later to understand what was done. If CLI flags could silently override pipeline semantics, the recipe would no longer be the source of truth — handoff would degrade back to "the recipe and the magic command-line incantation," which is the notebook-era problem DataRefinery exists to fix.

**How to apply:** when adding a new feature that has a "switch" or "toggle" character, route it through the recipe as a section field or a variant — not as a CLI flag or env var. Tempting LLM mistakes to refuse:

- "Let's add `--no-augment` so users can quickly disable augmentation." **No.** Augmentation policy lives in the recipe; the variant pattern (`Augmentations: []` under a named variant) covers this case explicitly. Users select the variant via `--variant no_augment`, which is execution-context selection, not recipe override.
- "Let's add `--cache-root-override` that supersedes a recipe-declared cache root." **N/A** — the recipe doesn't declare cache root; it's already execution-context.
- "Let's add `--operation-skip OP_NAME` for fast iteration." **No.** That's pipeline semantics. Use a variant or edit the recipe.

If a proposed CLI flag's effect would change the canonical bytes of the recipe, it is by definition a recipe-semantic flag and must be expressed in the recipe instead.

### Determinism contract in `pipeline.workers`

When `--workers > 1` (opt-in process pool), per-record operations are scheduled across workers via `concurrent.futures.ProcessPoolExecutor`. The determinism contract has two parts:

1. **Per-record seeding.** Each record's seed is derived as `sha256(global_seed.to_bytes(8, 'big') + record_id_bytes).digest()[:8]` decoded as a 64-bit int. Worker scheduling does not affect which seed each record receives, because the seed depends only on `(global_seed, record_id)` — not on which worker picks it up or in what order.
2. **Reorder by `record_id` before downstream stages.** `run_parallel(...)` collects worker outputs and sorts them by `record_id` before yielding. This ensures the iteration order presented to downstream stages is identical regardless of how many workers ran or how the OS scheduled them.

**Why:** the reproducibility guarantee in features.md is byte-identical re-runs. If worker output order leaked into downstream stages, two runs of the same recipe with the same seed and the same input could produce different materialized bytes whenever process scheduling differed — which is essentially every run on a different machine, or under different system load.

**How to apply:** any change to `pipeline/workers.py` or to call sites that iterate worker output must preserve both invariants. Tempting LLM mistakes to refuse:

- "Let's stream results as workers complete to reduce latency." **No** — that breaks the reorder-by-record-id invariant. If latency is a real concern, raise it with the developer; the fix is not to weaken the determinism contract.
- "Let's seed per-worker rather than per-record, since per-record seeding is wasteful." **No** — per-record seeding is what makes worker-count irrelevant to output. Per-worker seeding makes the output depend on the number of workers, which is exactly what we are guarding against.
- "Let's use the `as_completed` iteration pattern for `Future` objects." **Only if** the results are immediately reordered by `record_id` before crossing a stage boundary. The pattern is fine internally; the contract is at the boundary.

The integration test suite includes a determinism check that runs the same fixture pipeline with `workers=1`, `workers=2`, and `workers=4`, asserting all three produce byte-identical instances. Any change to `pipeline/workers.py` must keep that test green; if it cannot, the change is a determinism regression and must be reverted or escalated.

### DataRefinery does not resample at the Splits stage — `class_balance` is a training-time hint

`SplitsSection.class_balance` is a **forward-declared hint** that DataRefinery passes through `SplitResult.class_balance` and `manifest.class_balance` to consumer tools. The consumer (ModelFoundry today; other tools tomorrow) honors the strategy at training time via standard framework primitives (`WeightedRandomSampler` in PyTorch, `class_weight=` in Keras, etc.). DataRefinery's runtime performs **no resampling and no weight emission** at the Splits stage. The behavior contract is in `features.md` FR-7 #4 ("a sampling strategy ModelFoundry honors"); this entry pins the prevention pattern.

**Why:** the boundary keeps DataRefinery's "prepared dataset = materialized bytes" discipline coherent and avoids reimplementing framework primitives. Inflating the cached train split with oversampled records would multiply storage for every imbalance experiment; emitting a `class_weight` column on records would entangle DataRefinery's record schema with training-loop semantics. The decision was made deliberately during Phase I planning (Story I.o / G10) after considering the DR-side alternative; DR-side resampling lives in `stories.md § Future` as a deliberate revisit candidate, not an enhancement to be silently added.

**How to apply:** when working in `pipeline/stages/splits.py` or anything that reads `SplitsSection.class_balance`, refuse the following tempting moves:

- "Let's add an `oversample_minority_to_majority` branch in the Splits stage so the cached train split is balanced." **No.** That contradicts FR-7 #4 and the recipe-as-truth discipline; the strategy is a hint for the training tool, not a DR runtime behavior. The DR-side path is in Future for deliberate revisit if downstream evidence accumulates.
- "Let's emit a `class_weight: float` column on every train record so the consumer doesn't need to compute weights." **No.** The strategy is declarative; consumers compute weights from per-class counts at training time. Adding a column entangles record schema with training-loop semantics.
- "Let's add a `validate` warning when a recipe declares `class_balance` but ModelFoundry isn't installed." **No.** DataRefinery is independent of any specific consumer; the strategy is a contract surface for *any* training-time consumer (see `docs/specs/modelfoundry/dependency-spec.md` for the binding contract). Coupling validate behavior to a specific downstream tool inverts the dependency direction.

(Note: changing `class_balance.strategy` does invalidate the cache, which is **correct** — `class_balance` is in canonical bytes, so the invalidation happens automatically. That is the intended behavior; no action needed.)

The path forward for DR-side resampling is a story under the `stories.md § Future` "DR-side `class_balance` resampling" entry, not an in-band code change in `pipeline/stages/splits.py`. The precedent for "tempting upgrade documented in Future, not silently adopted" is the § "Sibling-instance dependencies are loose-coupled in v1" entry above.
