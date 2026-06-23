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

The **horizontal segmented-identity mechanism + no-implicit-defaults** is the **DataRefinery-coordinated cross-tool-family standard** (spike §3 Governance; the four-tool family DataRefinery → ModelFoundry → nbfoundry → learningfoundry shares one identity model). This is a **stronger** commitment than the usual "the discipline travels across the family" framing used elsewhere in this doc (which means parallel independent copies): the segment boundaries, the `extensions` namespace, the no-implicit-defaults rules, and the `join_stable` byte format are a **governed shared contract**. **Diverging from it is a cross-repo coordination event, not an in-tree decision** — raise it with the family, don't fork it locally. The **vertical stage-waterfall axis is ModelFoundry's own** (deferred to a future phase); `join_stable` is kept prefix-capable so it can layer in without re-specifying the combiner. *(Cross-repo status, resolved at v0.17.0 / DR v0.23.0: DataRefinery has now **implemented** its `join_stable`, and **the two byte formats diverge** — DR uses `b"\x1f".join(digests)` (an unframed unit-separator join of the raw per-segment digests, `datarefinery.recipe.segments.join_stable`), while MF uses a **labeled, length-framed, label-sorted, prefix-capable** concatenation (`recipe/canonical.py::join_stable`). This does **not** functionally break MF: MF consumes the DR instance as an opaque hashed unit — it reads DR's `manifest.recipe_hash` and XORs it into `data_instance_hash16`, and never recomputes DR's hash with MF's combiner. The divergence only becomes load-bearing if/when the deferred vertical / cross-tool hash-chain axis ships (both sides kept the combiner prefix-capable — DR exposes `prefix_hash` — precisely so adoption needs no combiner redesign). **Aligning the byte formats is a cross-repo coordination event, not an in-tree fix** — surface it to the family (is the format meant to be byte-identical across tools, or only structurally analogous?); do not unilaterally change MF's combiner. See `docs/spikes/I.a-segmented-recipe-identity.md`.)*

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
