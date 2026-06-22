# stories.md -- modelfoundry (python)

This document breaks the `modelfoundry` project into an ordered sequence of small, independently completable stories grouped into phases. Each story has a checklist of concrete tasks. Stories are organized by phase and reference modules defined in `tech-spec.md`.

Put **`vX.Y.Z` in the story title only when that story ships the package version bump** for that release. Doc-only or polish stories **omit the version from the title** (they share the release with the preceding code story, or use your project’s doc-release policy). **One semver bump per owning story** — extra tasks on the *same* story share that bump; see `project-essentials.md`. Semantic versioning applies to the package. Stories are marked with `[Planned]` initially and changed to `[Done]` when completed.

For a high-level concept (why), see [`concept.md`](concept.md). For requirements and behavior (what), see [`features.md`](features.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For project-specific must-know facts, see [`project-essentials.md`](project-essentials.md) (`plan_phase` appends new facts per phase). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Version Cadence

Standard semantic versioning, with these conventions:

- **Every story belongs to a phase.** Bugfix stories included. No orphan stories.
- **Per-story bumping** (when a story owns its own release):
  - Bugfix or trivial change → **patch** (`vX.Y.Z+1`)
  - Feature or improvement → **minor** (`vX.Y+1.0`)
  - Breaking change → **major** (`vX+1.0.0`). Post-1.0 only, and only via the `plan_production_phase` mode, which negotiates with the developer about whether the breakage is substantively user-facing or technically-but-trivially breaking (example: a log-format change is technically breaking, but if logs aren't a core consumer capability, the developer may judge it minor or even patch).
- **Phase-bundling option:** a phase can run unversioned during work and ship a single release/tag at end-of-phase. Stories within the phase carry no version in their title; the phase's last story owns the bump (magnitude determined by the highest-impact change in the bundle).
- **No out-of-order implementation.** Story order in this file is the order of execution. If work order needs to change, **reorganize/renumber here first** — don't skip ahead and create version-number gaps.
- **Pre-1.0:** standard semver applies; version starts at `v0.1.0` (Story A.a).
- **Post-1.0:** every phase must go through `plan_production_phase` (the lighter `plan_phase` is pre-1.0 only). Major bumps only happen through that mode's negotiation step.

This is the authoritative cadence rule. **Do not extrapolate the bump magnitude from `pyproject.toml`'s current version** — re-read this section whenever you're about to assign a version to a story.

---

## Phase I: Segmented Recipe Architecture

This phase refactors recipe **identity** so canonical bytes are composed from independent **segments** — `core` / `plugin` / `overlays` / `extensions` — rather than a single total `model_dump`. A recipe contributes only the segments it uses, so a plugin-surface change scopes to that plugin's recipes and never invalidates another plugin's caches. The recipe stays **flat on disk** (segmentation lives in the hashing, via discriminated-union plugin surfaces). Shipped together: **no implicit defaults** (the interpreting code supplies no behavior-affecting value; the scaffolder emits every value explicitly into the recipe text), a sanctioned `extensions:` namespace for bounded experimentation, and per-segment versioning. The horizontal mechanism + no-implicit-defaults are the **DataRefinery-coordinated cross-tool-family standard** (Phase I *adopts*, it does not redesign); the **vertical stage-waterfall axis is deferred to a future phase** — the combiner is kept prefix-capable so it can layer in later.

This is based on [`phase-i-recipe-architecture-spike.md`](phase-i-recipe-architecture-spike.md); design decisions, open-question defaults, and out-of-scope in [`phase-i-segmented-recipe-identity-plan.md`](phase-i-segmented-recipe-identity-plan.md).

---

> **Release cadence (Phase I) — phase-bundled, one minor.** Unlike Phase H's per-story bumps, Phase I runs **unversioned during work and ships a single release at end-of-phase** (Version Cadence "phase-bundling option"). The whole point is that canonical bytes change **once**: per-story bumps would mean multiple cache-invalidation events. Stories I.a–I.g carry no version; **I.h owns the single minor bump** (→ **v0.16.0**, assuming Phase H ships through v0.15.0). One documented cache-invalidation event: pre-prod OR-9 — release-note + re-materialize, no migration written (pre-1.0 support window = zero). The per-segment version *scheme* lands; actual migrations do not.

---

### Story I.a: Architectural spike — `join_stable`, discriminated-union representation, segment boundaries & `num_workers` classification [Done]

The combiner bytes, the flat→discriminated-union conversion, and the validator-on-unions adaptation are genuinely unproven (spike §9). **Throwaway architectural spike** — deliverable is a decisions doc + a small proof, not production code; it de-risks I.b–I.h. **Deliverable:** [`docs/spikes/I.a-segmented-recipe-identity.md`](../spikes/I.a-segmented-recipe-identity.md) (decisions) + `scripts/spike_segmented_identity.py` (throwaway proof, 16/16 claims pass).

- [x] **`join_stable` design.** Labeled, length-framed concatenation of per-segment SHA-256 digests + a fixed empty-segment sentinel; **prefix-capable** (`H(H_upstream ‖ segment)`) so the deferred vertical axis isn't precluded; **match DataRefinery's combiner shape** (cross-repo coordination). Prove stable bytes + cross-plugin isolation on a toy fixture. → Decision 1; empty-segment = sparse omission (not a per-segment sentinel); byte format is a flagged cross-repo confirmation precondition for I.b (DataRefinery not importable this session).
- [x] **Segment boundaries.** Catalog which `ModelRecipe` fields land in `core` (`schema_version`, `plugin`, `seed`, `Data` binding, stage skeleton) vs `plugin` (the discriminated per-plugin surfaces) vs `overlays` (`variants` selected delta) vs `extensions`. → Decision 2 (full field-by-field table). Key finding: byte-level cross-plugin isolation comes from **sparse hashing + no-implicit-defaults**, with unions/segments adding schema-isolation + versioning scope.
- [x] **Discriminated-union prototype.** Convert one shared spec (e.g. `TrainingSpec`) to a discriminated union (flat on disk via a discriminator field); confirm validator checks 3 (`section_ops_registered`) + 17 (`op_params_match_spec`) ([validator.py:137,441](../../src/modelfoundry/recipe/validator.py#L137)) can adapt. → Decision 3: top-level `plugin` is the injected discriminator (YAML stays flat); `canonical_bytes` stays plugin-free; `recipe/models.py` stays plugin-agnostic.
- [x] **No-implicit-defaults catalog.** Enumerate current value-defaults to drop ([models.py](../../src/modelfoundry/recipe/models.py): `Training.num_workers=2`, `precision="fp32"`, `checkpoint_cadence=1`, …) vs **mode-selecting optionals to keep** (`Inference.mc_samples=None ⇒ point`, `early_stopping=None ⇒ none`, `Optimization=None ⇒ no HPO`, `Optimizer.schedule=None ⇒ constant LR`, `Data.variant=None`). → Decision 4 (drop / keep / invariant-not-default tables).
- [x] **Per-segment version scheme.** Per-segment versions + a thin top-level umbrella versioning only the combination function; migration-registry seam keyed by `(segment, from, to)`. → Decision 5 (umbrella versions the combiner; seam empty pre-1.0; absent⇒behavior mappings become versioned contract).
- [x] **`num_workers` classification (Option A, decided 2026-06-22).** Design moving `Training.num_workers` out of `TrainingSpec` into `RuntimeConfig` + `--num-workers` CLI flag + `MODELFOUNDRY_NUM_WORKERS`, incl. the `Plugin` Protocol signature change to thread it to the trainer DataLoader (no longer riding `TrainingSpec` into `run_training`/`run_optimization`). Implemented in the bundle (I.e). → Decision 6 (concrete 4-step signature change; proposed default `2 → 0`, confirm at I.e).
- [x] **Verdict + decisions doc** feeding I.b–I.h. → Verdict: design works, proceed; three sharpening findings + per-story touch-ups recommended.

**Version:** **no bump** (throwaway spike; no shipped `src/` change).

### Story I.b: Segment model + segment-aware canonical bytes [Done]

F1. Replace the flat total dump ([canonical.py:25](../../src/modelfoundry/recipe/canonical.py#L25)) with the segmented combiner from I.a.

- [x] Implement `join_stable` + per-segment extraction in `recipe/canonical.py`; empty segment ⇒ fixed-nothing. → `recipe_segments` (core/plugin/overlays partition) + `join_stable` (length-framed, label-keyed, sparse-omit); `canonical_bytes` is now the combiner pre-image, `recipe_hash = sha256(canonical_bytes)` preserved.
- [x] Prefix-capable combiner signature (accepts an upstream digest) — unused now, kept for the deferred vertical axis. → `join_stable(segments, *, upstream=None)`; `H(H_upstream ‖ segment)` composes (tested).
- [x] Horizontal-isolation pin-test scaffolding: a PyTorch-only fixture's `recipe_hash` MUST NOT move when the sklearn surface changes (and vice-versa). → [test_segmented_identity.py](../../tests/unit/test_segmented_identity.py) (19 tests); full F2 strength matures with I.c unions + I.e no-implicit-defaults.

> **Note:** the `_PINNED_HASH` golden in [test_canonical.py](../../tests/unit/test_canonical.py) is `xfail(strict=True)` from here through I.e — the conscious re-pin is deferred to **I.f** (the single sign-off, per phase cadence). **`join_stable` byte format remains a cross-repo confirmation precondition** to settle with DataRefinery before the phase ships (DataRefinery has not yet implemented its combiner — open question #3 in their Phase-J spike).

**Version:** **no bump** (bundled — Phase I cadence).

### Story I.c: Discriminated-union plugin surfaces + validator adaptation [Done]

F2. Convert the flat shared specs (`Loss`/`Optimizer`/`Schedule`/`Training`/`Evaluation`/`Visualization`) from `extra="allow"` op-bags ([models.py:34-54](../../src/modelfoundry/recipe/models.py#L34)) to discriminated unions per I.a; recipe stays flat on disk.

- [x] Define per-plugin variant types behind a discriminator; keep YAML flat. → spike-faithful realization (I.a Decision 3): the **op→`param_model` registry IS the discriminated union** (op = discriminator, variant = plugin's `OperationSpec`). New [recipe/sections.py](../../src/modelfoundry/recipe/sections.py) (`resolve_sections`/`iter_op_sections`) realizes it at validate time; `recipe/models.py` stays plugin-agnostic and `canonical.py` stays plugin-free (no `models.py` plugin import).
- [x] Adapt validator checks 3 (`section_ops_registered`) + 17 (`op_params_match_spec`) to unions; preserve the never-short-circuit behavior. → both checks read one shared `resolve_sections` pass; check 3 now also rejects an op registered for the **wrong section** (`applies_to` mismatch — closes the `Loss: {op: adamw}` gap); never-short-circuit preserved (tested).

> **Scope note:** kept as a single story (developer offered I.c.# subdivision if large) — checks 3 & 17 share the section enumeration and are tightly coupled, so splitting them would leave intermediate inconsistent states. Realized as a validator-side concretization rather than `models.py` unions, per the I.a constraint that core stays plugin-agnostic. F2 byte-level isolation was already delivered by I.b's plugin-free hashing + the registry; this story formalizes the union and hardens validation.

**Version:** **no bump** (bundled).

### Story I.d: `extensions:` namespace [Planned]

F3. A sanctioned declarative bag where `extra` is relaxed only inside the namespace; enters identity only when non-empty.

- [ ] Add the `extensions:` block to `ModelRecipe` (the only relaxed island; `ModelRecipe` stays `extra="forbid"` elsewhere — [models.py:173](../../src/modelfoundry/recipe/models.py#L173)).
- [ ] Empty bag ⇒ byte-identical hash to pre-mechanism (test).
- [ ] Plugins declare which extension keys they consume; validator warns on unclaimed keys. Params only — never recipe-activated code (spike §7).

**Version:** **no bump** (bundled).

### Story I.e: No implicit defaults + `num_workers` reclassification (Option A) [Planned]

F4. The interpreting code supplies no behavior-affecting value; the scaffolder emits all values.

- [ ] Drop value-`default=`s from the param models / specs per the I.a catalog; **keep mode-selecting optionals** (the "absent ⇒ behavior" mapping moves into the versioned segment contract).
- [ ] Scaffolder ([init.py:87](../../src/modelfoundry/scaffolder/init.py#L87)) becomes the value-emitter — emit every behavior-affecting field explicitly.
- [ ] **`num_workers` → execution context (Option A):** remove from `TrainingSpec`; add to `RuntimeConfig` + `--num-workers` + `MODELFOUNDRY_NUM_WORKERS`; `Plugin` Protocol signature change to thread it to the DataLoader. (The E.e `worker_init_fn` output-neutrality guard stays green.)

**Version:** **no bump** (bundled).

### Story I.f: One-time mass migration (recipes, fixtures, template, golden re-pin) [Planned]

F6 (migration portion). Rewrite every recipe surface to the flat-discriminated + explicit-values form; one-time.

- [ ] Rewrite the ~24 recipes (15 `recipes/` + 9 valid `tests/fixtures/recipes/`) and 14 invalid fixtures (keep them invalid for the *right* reason under the new schema) + the scaffolder template.
- [ ] **Consciously re-pin `_PINNED_HASH`** in [test_canonical.py](../../tests/unit/test_canonical.py) — the deliberate reviewer sign-off the test exists to force (one cache-invalidating change is landing).

**Version:** **no bump** (bundled).

### Story I.g: Per-segment versioning + migration-registry seam [Planned]

F5. Replace the single global `schema_version` gate ([loader.py:26](../../src/modelfoundry/recipe/loader.py#L26)) with per-segment versions + a thin combiner umbrella.

- [ ] Per-segment version fields + gate; thin top-level umbrella for the combination-function version.
- [ ] Migration registry keyed by `(segment, from, to)` — the **seam only**, empty (pre-1.0 zero support window; users re-materialize).

**Version:** **no bump** (bundled).

### Story I.h: Enforcement, release & docs — owns the bump [Planned]

F6 (enforcement portion). Lock isolation, ship the single release, record the contract.

- [ ] Per-segment isolation tests + extend the Hypothesis cosmetic/semantic props ([test_cache_identity_properties.py](../../tests/unit/test_cache_identity_properties.py)): cross-plugin isolation; empty-extensions-no-change; semantic edit → hash change; cosmetic → no change.
- [ ] Release-note the single cache-invalidation event (OR-9: re-materialize; no migration written).
- [ ] Update `project-essentials.md`: the segmented-identity contract + the no-implicit-defaults rule (`required` vs. mode-selecting-optional = bump vs. free) + the **cross-family governance status** (the horizontal model is the DR-coordinated shared standard — stronger than the existing "discipline travels" framing; divergence is a cross-repo event).

**Version:** **minor → v0.16.0** — the single phase-bundled Phase I release (assumes Phase H ships through v0.15.0). **Cache-invalidating** for every recipe (segmented combiner + discriminated representation + no-implicit-defaults all perturb canonical bytes): pre-prod OR-9 — release-note + re-materialize, **no `schema_version`-style migration** (per-segment version scheme lands; migrations are zero-support-window pre-1.0).

---

## Future

<!--
This section captures items intentionally deferred from the active phases above:
- Stories not yet planned in detail
- Phases beyond the current scope
- Project-level out-of-scope items
The `archive_stories` mode preserves this section verbatim when archiving stories.md.
-->

### Story ?.?: CIFAR-10 ResNet20 Canonical Benchmark

Story H.f.9 had some leftover tasks that were out of scope, but are relevant to proving correctness. So far, we've identified several bugs in the process of trying to answer questions about why the model is not learning or why accuracy is much lower than expected. One theory for confirming there are no bugs is matching a canonical architecture, using same data preparation methods/specs, and following the same training regime. If we can match expected performance on a proven standard, then we have validated correctness.

- [x] **High-vs-high comparison.** [scripts/experiments/canonical_comparison.py](../../scripts/experiments/canonical_comparison.py) — same crop+flip instance, v0.10.2: **resnet20 0.7764 > simple_cnn 0.7305 > sklearn MLP 0.4653 > random 0.1012**. The canonical regime helps both CNNs (`simple_cnn` 0.672 → 0.730), and ResNet-20's lead over `simple_cnn` **widens from +0.0070 (dynamic) to +0.0459 (canonical)** — capacity pays off at budget. Baselines reproduce the postfix_ladder numbers to the digit (regime- & instance-invariant floor). Folded into the scoreboard in [canonical_benchmark.md](../../scripts/experiments/canonical_benchmark.md).
- [ ] **Robustness / "real-world" eval.** Route the trained models through [recipes/cifar10c-eval.yaml](../../recipes/cifar10c-eval.yaml) (gaussian_noise / motion_blur / fog / jpeg_compression × severities 1/3/5); tabulate per-corruption, per-severity degradation + calibration (`ece`) under shift. Hypothesis: the BN-heavier `resnet20` (19 BN layers vs 3) may degrade more under **noise** (BN running-stat mismatch — Schneider et al. 2020) while holding on **structured** corruptions (blur/fog/jpeg) — expect per-corruption flips, not a uniform winner. Run only on **converged + best-weights-fixed** checkpoints (a stale checkpoint carries the wrong BN stats into a shift eval).
- [ ] **Deferred refinement — true paper protocol.** Source the **official labeled 10k CIFAR-10 test split** (not on disk — the Kaggle `test/` is 300k unlabeled distractors) + the full 50k train (vs the 28k carved) as an upstream DataRefinery recipe (FR-6), for an apples-to-the-paper number.

### Close follow-on cycles (deferred from the pre-production release)

- ~~**`[huggingface]` plugin end-to-end**~~ — **pulled into active scope: Subphase H-1 (R1, stories H.i–H.l).** Activates the deferred `Encoder`/`LoRA`/`Pooling`/`Head` path on the existing PyTorch plugin (not a separate plugin) per [`advanced-and-probabilistic-requirements.md`](advanced-and-probabilistic-requirements.md). Pretrained-weight cache management (`~/.cache/huggingface/` or `HF_HOME` override) lives in the plugin's docs, not in `project-essentials.md`.
- **`[keras]` plugin end-to-end** — TensorFlow + Keras 3 backend. Likely shares the metric implementations from `plugins/sklearn/metrics.py` for ECE / calibration_curve.
- **`[llm]` extra implementation** — `init --llm-assist` flag routed through `lmentry` for interpretive baseline-model recommendations. Namespace claimed in `pyproject.toml`; no implementation in the pre-production series. Lands as its own FR with its own acceptance criteria.
- **Additional sklearn baselines** — C.m ships a working `MLPClassifier` baseline (Subphase C-1); extend with RandomForest / GBM baselines for CIFAR-10 (reusing the C.f feature-flattening + normalization path).
- **Continued training** — `Training.persist_optimizer_state: bool = false` recipe field gated by a `schema_version` bump; the `Checkpoint` model's forward-extensible keys (`optimizer_state`, `scheduler_state`, `rng_state`, `training_step`) are populated; new `materialize --resume-from <checkpoint>` workflow. The Q16 foundation in B.k is what makes this a pure additive change with no public-API rework.
- **Configurable best-weights / restore criterion (advanced optimization)** — today (H.f.10, v0.10.2) `restore_best_weights` is coupled to early stopping and selects on the early-stopping monitor (default `val_loss`); a no-early-stopping run keeps the converged final model. Advanced cases want "best" defined by a *different* success driver: validation **accuracy** or `macro_f1` instead of loss, or a bespoke objective (risk-adjusted score, prediction diversity, calibration/ECE, a custom utility). Likely shape: a `checkpoint_selection: {monitor: <any produced metric>, mode: min|max}` recipe block (a Keras `ModelCheckpoint(save_best_only)` analog) decoupled from early stopping and validated against produced metrics (extends FR-2 check 6). **Crucially, this need not be engineered up front:** `training/history.parquet` already persists per-epoch `train_loss` / `val_loss` / `val_accuracy` / `learning_rate`, so an alternate "best" epoch can be identified **post-hoc** from the persisted history, and a bespoke selector built only when a concrete need arises. Caveat: restoring an arbitrary epoch's *weights* requires that epoch to have been checkpointed (`Training.checkpoint_cadence`), so a post-hoc-restore path either constrains selection to persisted-cadence epochs or runs at `checkpoint_cadence: 1`.
- **Tight-coupled DataRefinery binding (FR-26)** — `schema_version` bump that mixes the bound DataRefinery instance's `recipe_hash` into ModelFoundry's cache identity, so upstream re-materialization auto-invalidates downstream. Requires a documented migration of existing cached ModelInstances.
- ~~**`num_workers` cache-identity reclassification**~~ — **pulled into Phase I (decided 2026-06-22): Option A, folded into Story I.a / implemented in I.e.** `Training.num_workers` moves out of `TrainingSpec` into `RuntimeConfig` + `--num-workers` + `MODELFOUNDRY_NUM_WORKERS` (the execution-context home), riding Phase I's one-time segmented-identity invalidation rather than incurring its own. The output-neutrality guard (E.e `worker_init_fn`) stays green. *(History: surfaced by E.e.1; the deferred Option A/B trade-off — Option A "reclassify as execution context" vs Option B "exclude from canonical bytes" — is resolved in favor of A.)*
- **Optional `Loss`/`Optimizer` recipe sections for baseline plugins (Gap A, Option B)** — filed from the Story H.f bundle (developer call 2026-06-17: ship the localized **Option A** now — baseline plugins register the loss/optimizer ops their recipes declare — and file the cleaner schema change here). Today `ModelRecipe` *requires* `Loss` and `Optimizer`, and validator check 3 (`section_ops_registered`) rejects any op a plugin doesn't register, so baseline/dummy plugins (`sklearn`, `random`) must register loss/optimizer ops they may only nominally use — schema-theater for a model that has no real loss or optimizer (a `DummyClassifier` most of all). The cleaner long-term shape: make `Loss`/`Optimizer` `| None = None` (mirroring `Optimization`), and have the validator only check the sections that are present, so a baseline recipe can omit blocks it has no concept of. **Blast radius:** the core recipe model + `recipe.validator` + every plugin's op table + the recipe fixtures + the `init` scaffolder template; likely a `schema_version`-coordination question for recipes that already carry the blocks. `plan_features`-shaped, deferred from the H.f bundle.
- **Robust capacity-vs-budget study (scaling + regime)** — **largely resolved by H.f.5 + H.f.6.** H.f.4's sweep showed the crossover is noisy / non-monotonic on the 1,700-image subset with the minimal (no-schedule, no-early-stopping) recipes; H.f.5 added the regime (cosine + early stopping — fixed the small model) and H.f.6 added 10x data on MPS (`resnet20` crosses over decisively, 0.594 > MLP 0.451). The three in-repo runners under [`scripts/experiments/`](../../scripts/experiments/) carry the evidence. **Still open if wanted:** scaling further (full 50k / GPU) and a true budget × data grid for a published curriculum figure — a `plan_features`-shaped follow-up, no longer blocking.
- **Marimo + IPython substrate-neutral smokes** — the Jupyter smoke in E.k is the canonical substrate-neutral test; Marimo headless and IPython REPL smokes extend the contract.
- **Parallel Optuna trials** — `n_jobs > 1` with a deterministic trial-ordering protocol on top of the parallel harness. Requires the determinism contract to extend cleanly.
- **Search-space op-choice dimensions** — a grouped/conditional Optuna search-space mechanism so optimizer (AdamW / SGD+momentum) and LR schedule (`reduce_on_plateau` / `cosine`) can be **genuine search dimensions** rather than `variants:`. The current flat `recipe.search_space.suggest_params` + per-op `extra="forbid"` param models can't carry op-conditional params: a single `Optimizer.schedule` block can't validate for both ops (`cosine` *requires* `T_max`, which `reduce_on_plateau` rejects), and SGD's `momentum` breaks an AdamW trial the same way. Likely an `optimizer`/`schedule` group categorical that swaps the whole sub-block as a unit (plus a default for `CosineParams.T_max`). A `plugins.pytorch.optimization` + `recipe.search_space` enhancement touching the determinism-sensitive trial path. Surfaced by the C.r CIFAR-10/ResNet-20 deliverable (R5), which ships these comparisons as `variants:` instead. Sibling to **Parallel Optuna trials** above.
- **`modelfoundry.toml` per-project config** — currently no per-project config file (recipe + CLI flags + env vars cover execution context). If recurring patterns emerge, a project config lands as its own FR.
- **Cross-platform first-class Linux** — currently Linux is best-effort pre-production; post-production gates require first-class status.
- **Codecov / Coveralls coverage upload** — deferred from Phase G; coverage produced locally via `pyve test --cov`.
- **GitHub branch protection** — explicitly out of scope for the pre-production series per CR-1.
- **Production-release ceremony** — when ModelFoundry transitions from pre-production to production (the `1.0.0` event), every cache-invalidating change becomes ceremonious per `project-essentials.md`; `OR-8` / `OR-9` / `OR-10` stability guarantees activate; `plan_production_phase` replaces `plan_phase` for adding new work.

**Forward-declared dependency contracts:**

- `docs/specs/modelfoundry/vendor-dependency-spec.md` for downstream consumers (a future `modelmetrics`, `modelmachine`, replay harness) — authored at the pre-production release, mirroring DataRefinery's vendor-dependency-spec discipline. Captures the on-disk `ModelInstance` layout + the in-memory `ModelInstance` API + schema-version coordination policy.
