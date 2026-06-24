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

---

### Story I.b: Segment model + segment-aware canonical bytes [Done]

F1. Replace the flat total dump ([canonical.py:25](../../src/modelfoundry/recipe/canonical.py#L25)) with the segmented combiner from I.a.

- [x] Implement `join_stable` + per-segment extraction in `recipe/canonical.py`; empty segment ⇒ fixed-nothing. → `recipe_segments` (core/plugin/overlays partition) + `join_stable` (length-framed, label-keyed, sparse-omit); `canonical_bytes` is now the combiner pre-image, `recipe_hash = sha256(canonical_bytes)` preserved.
- [x] Prefix-capable combiner signature (accepts an upstream digest) — unused now, kept for the deferred vertical axis. → `join_stable(segments, *, upstream=None)`; `H(H_upstream ‖ segment)` composes (tested).
- [x] Horizontal-isolation pin-test scaffolding: a PyTorch-only fixture's `recipe_hash` MUST NOT move when the sklearn surface changes (and vice-versa). → [test_segmented_identity.py](../../tests/unit/test_segmented_identity.py) (19 tests); full F2 strength matures with I.c unions + I.e no-implicit-defaults.

> **Note:** the `_PINNED_HASH` golden in [test_canonical.py](../../tests/unit/test_canonical.py) is `xfail(strict=True)` from here through I.e — the conscious re-pin is deferred to **I.f** (the single sign-off, per phase cadence). **`join_stable` byte format remains a cross-repo confirmation precondition** to settle with DataRefinery before the phase ships (DataRefinery has not yet implemented its combiner — open question #3 in their Phase-J spike).

**Version:** **no bump** (bundled — Phase I cadence).

---

### Story I.c: Discriminated-union plugin surfaces + validator adaptation [Done]

F2. Convert the flat shared specs (`Loss`/`Optimizer`/`Schedule`/`Training`/`Evaluation`/`Visualization`) from `extra="allow"` op-bags ([models.py:34-54](../../src/modelfoundry/recipe/models.py#L34)) to discriminated unions per I.a; recipe stays flat on disk.

- [x] Define per-plugin variant types behind a discriminator; keep YAML flat. → spike-faithful realization (I.a Decision 3): the **op→`param_model` registry IS the discriminated union** (op = discriminator, variant = plugin's `OperationSpec`). New [recipe/sections.py](../../src/modelfoundry/recipe/sections.py) (`resolve_sections`/`iter_op_sections`) realizes it at validate time; `recipe/models.py` stays plugin-agnostic and `canonical.py` stays plugin-free (no `models.py` plugin import).
- [x] Adapt validator checks 3 (`section_ops_registered`) + 17 (`op_params_match_spec`) to unions; preserve the never-short-circuit behavior. → both checks read one shared `resolve_sections` pass; check 3 now also rejects an op registered for the **wrong section** (`applies_to` mismatch — closes the `Loss: {op: adamw}` gap); never-short-circuit preserved (tested).

> **Scope note:** kept as a single story (developer offered I.c.# subdivision if large) — checks 3 & 17 share the section enumeration and are tightly coupled, so splitting them would leave intermediate inconsistent states. Realized as a validator-side concretization rather than `models.py` unions, per the I.a constraint that core stays plugin-agnostic. F2 byte-level isolation was already delivered by I.b's plugin-free hashing + the registry; this story formalizes the union and hardens validation.

**Version:** **no bump** (bundled).

---

### Story I.d: `extensions:` namespace [Done]

F3. A sanctioned declarative bag where `extra` is relaxed only inside the namespace; enters identity only when non-empty.

- [x] Add the `extensions:` block to `ModelRecipe` (the only relaxed island; `ModelRecipe` stays `extra="forbid"` elsewhere — [models.py:173](../../src/modelfoundry/recipe/models.py#L173)). → `extensions: dict[str, Any] = {}`; wired as a 4th segment in `recipe_segments` ([canonical.py](../../src/modelfoundry/recipe/canonical.py)).
- [x] Empty bag ⇒ byte-identical hash to pre-mechanism (test). → empty/absent sparse-omitted (I.b combiner); non-empty perturbs. Tested in [test_segmented_identity.py](../../tests/unit/test_segmented_identity.py).
- [x] Plugins declare which extension keys they consume; validator warns on unclaimed keys. Params only — never recipe-activated code (spike §7). → `Plugin.extension_keys: tuple[str, ...]` (Protocol attr; `()` on pytorch/sklearn/random); new **validator check 22** (`extensions_keys_claimed`) warns non-fatally (`passed=True` + message) on unclaimed keys, read tolerantly via `getattr`. Check count 21 → 22.

**Version:** **no bump** (bundled).

---

### Story I.e: No implicit defaults + `num_workers` reclassification (Option A) — split into I.e.1 - I.e.3

> **Restructured (developer-approved 2026-06-22):** the original I.e model changes are **mechanically coupled** to I.f's recipe/fixture rewrite — all 29 recipe files set `num_workers` (removing it from `extra="forbid"` `TrainingSpec` breaks them) and most omit `precision`/`calibration_bins`/`sampler`/`pruner`/`baseline_trial` (dropping their defaults makes them required → omitting recipes fail to load). I.e-then-I.f as written yields a **red suite between the two stories**. To keep the suite green at every boundary, each model change lands **with** its corresponding recipe/fixture rewrite: split into **I.e.1** (`num_workers`) + **I.e.2/I.e.3** (no-implicit-defaults); **I.f** rescoped to the conscious golden re-pin + invalid-fixture verification.

---

### Story I.e.1: `num_workers` → execution context (Option A) [Done]

F4 (part). Move `num_workers` out of recipe identity into execution context, stripping it from every recipe in the same step (green-preserving). Per I.a Decision 6.

- [x] Remove `num_workers` from `TrainingSpec` ([models.py](../../src/modelfoundry/recipe/models.py)); add `num_workers: int = 0` to `RuntimeConfig` ([config.py](../../src/modelfoundry/core/config.py)) + `--num-workers` CLI flag + `MODELFOUNDRY_NUM_WORKERS` (precedence CLI > env > default; **default `0`, was `2`** — PyTorch-portable, deterministic; users tune per machine).
- [x] `Plugin` Protocol signature change: `num_workers` keyword threaded to `run_training` / `run_optimization` → `build_dataloader` (off `TrainingSpec`); runner passes `self.config.num_workers`. pytorch threads it through trainer/optimization/`_make_objective`; sklearn/random accept it (no DataLoader).
- [x] Strip `num_workers` from all 29 recipes/fixtures + scaffolder emits none. The E.e `worker_init_fn` output-neutrality guard stays green — determinism test now varies `num_workers` via `RuntimeConfig` (no longer perturbs `recipe_hash`) and asserts byte-identical output.

**Version:** **no bump** (bundled).

---

### Story I.e.2: No implicit defaults — Part a: emit explicit values (corpus + scaffolder) [Done]

F4 (part). Make every behavior-affecting value **explicit in the recipe text** while the model defaults still exist — a purely additive, **provably zero-byte change** (an explicit value equal to the current default leaves `model_dump`, hence `recipe_hash`, unchanged). This is the user-facing no-implicit-defaults deliverable; I.e.3 then removes the now-redundant code defaults.

- [x] Scaffolder ([init.py](../../src/modelfoundry/scaffolder/init.py)) becomes the value-emitter — emits `precision`/`checkpoint_cadence`/`device` (Training) + `calibration_bins` (Evaluation) explicitly. (The baseline scaffold has no `Optimization`/`Visualizations`, so `sampler`/`pruner`/`baseline_trial`/viz `mode` are N/A there.) Test in [test_cli_init.py](../../tests/cli/test_cli_init.py).
- [x] Rewrite the **29 ModelFoundry recipe/fixture files** to author the missing values (= current defaults). One-time text migration, comment-preserving, inserting `precision`/`checkpoint_cadence`/`calibration_bins` (+ `device` and `baseline_trial` where missing). **Correction to the planning estimate: the corpus is 29 MF recipes, not 37** — the other 8 `recipes/*.yaml` are *DataRefinery* data-prep recipes (`InputSource`/`Transformations`/`Splits`, no `Training`/`Architecture`), out of scope for the MF no-implicit-defaults rule.
- [x] Verified zero byte change: the migration script snapshotted `recipe_hash` for all 28 loadable files and confirmed **0 changed**; the `_PINNED_HASH` `xfail` stays put (no new invalidation). Byte-neutrality also pinned as an invariant test in [test_segmented_identity.py](../../tests/unit/test_segmented_identity.py) (`test_explicit_default_values_are_byte_neutral`).

**Version:** **no bump** (bundled).

---

### Story I.e.3: No implicit defaults — Part b: drop the code defaults (enforcement) [Done]

F4 (part). The interpreting code supplies no behavior-affecting value. With the corpus already authoring every value (I.e.2), dropping the model defaults is green — only the test fixtures that relied on the defaults need fixing.

- [x] Dropped value-`default=`s from the param models per the I.a catalog ([models.py](../../src/modelfoundry/recipe/models.py)): `precision`, `checkpoint_cadence`, `device` (Training), `calibration_bins` (Evaluation), `sampler`/`pruner`/`baseline_trial` (Optimization), `mode` (Visualization + Inference) — all author-required. **Kept mode-selecting optionals** (`Inference=None`, `early_stopping=None`, `Optimization=None`, `Optimizer.schedule=None`, `Evaluation.comparison=None`, `Data.variant=None`). **Kept `Optimization.n_jobs=1`** as a constrained invariant (I.a Decision 4).
- [x] Fixed the inline test recipe dicts + direct `TrainingSpec`/`EvaluationSpec`/`OptimizationSpec`/`VisualizationSpec` constructions across ~20 unit/cli/integration/plugin-contract/notebook test files (the test-fixture churn the model flip forces).
- [x] Confirmed green: the I.e.2 corpus authors every value, so no recipe broke — only test fixtures. The `_PINNED_HASH` `xfail` stays put (final conscious re-pin is I.f).

**Version:** **no bump** (bundled).

---

### Story I.f: Golden re-pin + invalid-fixture verification [Done]

F6 (enforcement portion, rescoped — the recipe/fixture/template rewrites moved into I.e.1-I.e.3 to keep each story green). What remains is the conscious sign-off + invalid-fixture correctness.

- [x] Confirmed the invalid fixtures still fail for the *right* reason under the new schema — the fixture-verification layer in [test_recipe_validator.py](../../tests/unit/test_recipe_validator.py) is green (15 passed, 1 pre-existing check-13 xfail). The I.e.2 corpus migration added the now-required values to the invalid fixtures too, so none acquired a spurious "missing field" failure.
- [x] **Consciously re-pinned `_PINNED_HASH`** in [test_canonical.py](../../tests/unit/test_canonical.py) (`60cc77…` → `eca50b…`) and removed the `xfail` — the deliberate reviewer sign-off for Phase I's one-time cache-invalidating change (combiner + discriminated surfaces + extensions segment + num_workers reclassification + no-implicit-defaults). `_PINNED_RECIPE` updated to the explicit-values form.

**Version:** **no bump** (bundled).

---

### Story I.g: Per-segment versioning + migration-registry seam [Done]

F5. Replace the single global `schema_version` gate ([loader.py:26](../../src/modelfoundry/recipe/loader.py#L26)) with per-segment versions + a thin combiner umbrella.

- [x] Per-segment version scheme + umbrella gate. New [recipe/versioning.py](../../src/modelfoundry/recipe/versioning.py): `SUPPORTED_COMBINER_VERSIONS` (umbrella = the recipe's `schema_version`, versions the `join_stable` combination function) + `SEGMENT_VERSIONS` (`core`/`plugin`/`overlays`/`extensions`, **code-tracked, not recipe fields** — keeping them out of the recipe text is byte-neutral, avoiding a second Phase I invalidation after I.f's re-pin). Loader sources `SUPPORTED_SCHEMA_VERSIONS` from the umbrella (back-compat alias).
- [x] Migration registry keyed by `(segment, from, to)` — the **seam only**, empty pre-1.0. `migrate_segment()` routes single-step chains and refuses-with-pointer on a missing step (the sanctioned "re-materialize" behavior); tested directly. Recipe-level per-segment version fields are deferred to a future (post-1.0) schema change, landed only when migrations become necessary.

> **Design note (developer-flagged 2026-06-22):** per-segment versions are code constants, not recipe fields — authoring them into the recipe would enter the canonical bytes and trigger a second Phase I invalidation right after the conscious re-pin. The scheme + seam land byte-neutrally; the pinned hash is unchanged.

**Version:** **no bump** (bundled).

---

### Story I.h: Enforcement, release & docs — owns the bump [Done]

F6 (enforcement portion). Lock isolation, ship the single release, record the contract.

- [x] Per-segment isolation + extensions Hypothesis props added to [test_cache_identity_properties.py](../../tests/unit/test_cache_identity_properties.py): empty-extensions-no-change, non-empty-extensions-perturbs, core-change-isolates-to-core-segment (plugin segment byte-identical), recipe-hash-is-pure-function-of-segments. (Cosmetic/semantic props already existed; deterministic cross-plugin pytorch-vs-sklearn isolation lives in [test_segmented_identity.py](../../tests/unit/test_segmented_identity.py).)
- [x] Release-noted the single cache-invalidation event in [CHANGELOG.md](../../CHANGELOG.md) (v0.16.0): blast radius + re-materialize + no migration (OR-9) + recipe-author migration guide + the conscious re-pin.
- [x] Updated [project-essentials.md](project-essentials.md): rewrote the cache-identity entry for segmented `join_stable` + per-segment versioning/migration registry; added the **no-implicit-defaults rule** (required vs. mode-selecting-optional vs. invariant) and the **cross-family governance status** (governed shared contract — divergence is a cross-repo event).

**Version:** **minor → v0.16.0** — the single phase-bundled Phase I release (assumes Phase H ships through v0.15.0). **Cache-invalidating** for every recipe (segmented combiner + discriminated representation + no-implicit-defaults all perturb canonical bytes): pre-prod OR-9 — release-note + re-materialize, **no `schema_version`-style migration** (per-segment version scheme lands; migrations are zero-support-window pre-1.0).

---

### Story I.i: Documentation refresh — align concept / features / tech-spec / README with shipped Phase I [Done]

Reconcile the spec docs to what Phase I actually shipped (the code is the source of truth; this is alignment, not new requirements — any *net-new* requirement is `plan_features`/`plan_tech_spec` territory, flag don't author). `project-essentials.md` was already updated in I.h. **Doc-only — rides the v0.16.0 release, no separate bump.**

- [x] **`tech-spec.md`** — updated `TrainingSpec`/`OptimizationSpec`/`EvaluationSpec`/`ModelRecipe` snippets (removed `num_workers`; dropped value-defaults → author-required; added `extensions` + the no-implicit-defaults note); rewrote `recipe.canonical` (FR-4) for `recipe_segments` + `join_stable`; added a `recipe.versioning` (FR-5) section; replaced the `Training.num_workers` perf note with the `RuntimeConfig.num_workers` reclassification; validator → checks 1–22; module tree gains `sections.py` + `versioning.py`; dependency-table canonical-form line; the per-plugin-specs paragraph now describes the discriminated-union resolver + check 22.
- [x] **`features.md`** — rewrote FR-4 for segmented identity; replaced the field-default-perturbs-bytes hazard with the no-implicit-defaults rule; CR-4 + loader gate now describe the umbrella + per-segment versioning scheme; recipe-shape list gains `extensions`, the `Training` field corrections + `num_workers`-is-execution-context note; FR-2 checks: check 3 strengthened (`applies_to`), added checks 21 (architecture-input) + 22 (extensions-claim warn); TR-3 → checks 1..22.
- [x] **`concept.md`** — Scope cache-identity line now segmented (not flat `model_dump`); recipe-section list gains `extensions` + a no-implicit-defaults / `num_workers`-as-execution-context note.
- [x] **`README.md`** — segmented-identity phrasing in the intro; the `Training` device snippet authors `precision`/`checkpoint_cadence`/`device` with a no-implicit-defaults + `num_workers`-moved note; `--num-workers` added to the shared-options line.

**Version:** **no bump** (doc-only; rides the v0.16.0 Phase I release).

---

**Story bundle I.j.1–I.j.5 — DataRefinery v0.23.0 adoption + family `overlays` standard.** *(Authored in `debug` mode by developer direction, 2026-06-22: a `[Planned]` `I.j.#` split under the existing Phase I, not a new phase/subphase — phase/subphase creation is `plan_phase` territory. If the developer prefers this carry a Subphase I-1 heading, that is a one-line `plan_phase` follow-up.)*

**Why this bundle exists.** Upgrading the upstream dependency to **DataRefinery v0.23.0** (`pyproject.toml`: `ml-datarefinery>=0.23`) surfaced two *coordinated* upstream changes, not loose drift. Grounded in the vendored DR `concept`/`features`/`tech-spec`:

1. **DR Story J.n.3 — segmented identity became authoritative.** DR's cache identity switched from flat `sha256(to_canonical_bytes)` to `recipe_identity_hash(recipe)` (its own segmented `join_stable`), riding a DR-recipe `schema_version` **2→3** bump. `dr.Instance.load` now hard-validates `recipe.json` ↔ `manifest.recipe_hash`.
2. **DR Story J.n.5 — `variants` → `overlays`.** DR renamed *and widened* the concept: a single `variant: str` became an ordered `overlays: Sequence[str]` (last-writer-wins per section); `resolve_instance(variant=…)` → `resolve_instance(overlays=…)`; DR `manifest.variant` → `manifest.overlays: list[str]`.

What blew this past a bugfix (developer decision, 2026-06-22): rather than a minimal compat patch, **ModelFoundry adopts the family `overlays` standard end-to-end** — renaming MF's *own* `variants:` recipe surface to `overlays:`, widening it to a multi-overlay list, and updating MF's ModelInstance manifest contract to match. Renaming MF's canonical overlay field (`recipe/canonical.py::_OVERLAY_FIELD`) **perturbs the `overlays` segment's canonical bytes → invalidates every MF cache**, so this is a *second* ceremonious cache-invalidation event after I.h's v0.16.0 — handled with the full ceremony (re-pin the canonical-hash test with conscious sign-off, CHANGELOG blast-radius note, re-materialize per OR-9). The four-tool family's segmented-identity + `overlays` namespace is a **governed shared contract** (`project-essentials.md`); this bundle keeps MF *in unity* with it.

**Release shape — phase-bundled, one minor.** Stories I.j.1–I.j.5 run **unversioned during work**; **I.j.3 owns the single bump → v0.17.0** (one cache-invalidation event, not five). Compat lands first (I.j.1) so "green on DR 0.23" is isolated from the invalidating rename.

**Scope guard — three distinct meanings of "variant", only one is renamed.** (a) MF's *recipe overlay* (`variants:` block, `apply_variant`, `manifest.variant`, `--variant`, canonical `_OVERLAY_FIELD`) — **renamed → `overlays`**. (b) DR's boundary kwarg — **mapped** to DR's `overlays`. (c) `OperationSpec.variant` in [recipe/sections.py](../../src/modelfoundry/recipe/sections.py) = "the typed op param instance" (e.g. `cross_entropy` is a *variant* of loss) and the "weighted variant" loss comment — **left untouched** (unrelated meaning).

---

### Story I.j.1: DataRefinery v0.23.0 compatibility — restore green [Done]

Get the suite green on DR v0.23.0 with **zero change to MF's own surface or cache identity** (the family rename follows in I.j.2). Debug-mode reproduction: `pyve test --env smoke-pytorch tests/unit/test_data_binding.py tests/unit/test_pytorch_augmentations.py tests/unit/test_fixture_foundation.py tests/integration/test_loose_coupling.py` → **19 failed, 37 passed, 1 error** before the fix.

- [x] **RC-A — fixtures use DR's authoritative identity hash.** In [tests/fixtures/datarefinery_instances/builder.py](../../tests/fixtures/datarefinery_instances/builder.py) and [cifar10_smoke/builder.py](../../tests/fixtures/datarefinery_instances/cifar10_smoke/builder.py), replaced `sha256(to_canonical_bytes(dr_recipe))` with `recipe_identity_hash(dr_recipe)` (`from datarefinery.recipe.segments import recipe_identity_hash`) on the same in-memory recipe written to `recipe.json`; bumped the embedded DR recipe `schema_version: 2 → 3` (v3 loads the existing recipe shape directly). **Broader than planned:** the same old-style hash builder is *duplicated inline* in 9 more test files — `test_pytorch_data_adapter`, `test_pytorch_trainer` (×2), `test_pytorch_optimization`, `test_materialize_runner`, `test_pytorch_evaluation`, `test_sklearn_baseline`, `test_modelfoundry_api`, `test_init_cmd`, `test_materialize_cmd` — all migrated identically (+ dropped the now-unused `import hashlib`). Also updated the `test_data_binding::test_cross_validation_helpers` assertion `schema_version == 2 → 3` (DR's loader now bootstrap-migrates v1 → v3, was v1 → v2). Test-fixture-only.
- [x] **RC-B(interim) — DR boundary kwarg.** Mapped MF's still-named `variant` to DR's new kwarg at [data_binding.py](../../src/modelfoundry/pipeline/data_binding.py) `_resolve_via_library`: `overlays=[variant] if variant else None`; updated the module docstring. MF's own `variant` surface stays put — **superseded by I.j.2**. Four *direct* `dr.resolve_instance(..., variant=None)` call-sites in tests (`test_random_baseline`, `test_cifar10_resnet20`, `test_example_recipes`, `test_validate_cmd`) also retargeted `variant=None → overlays=None` (surfaced by whole-tree mypy).
- [x] **RC-C — DR augmentation params now fully required.** `test_pytorch_augmentations` passed partial params to DR realizers. **Broader than the planned `RandomErasingParams` note:** DR v0.23 made *all three* param models fully-required — `RandomCropParams` (now needs `padding_mode`), `ColorJitterParams` (`hue`), `RandomErasingParams` (`scale`+`ratio`). Passed the full set in each affected case, using values equal to MF's own defaults so the shared dict drives both realizers identically (MF's models still default them — adapter unaffected).
- [x] **RC-D — stale version string.** `datarefinery_version="0.19.0"` → `"0.23.0"` in both [builder.py](../../tests/fixtures/datarefinery_instances/builder.py) and [cifar10_smoke/builder.py](../../tests/fixtures/datarefinery_instances/cifar10_smoke/builder.py).
- [x] Re-ran the DR-touching surface + heavier `smoke-pytorch` integration tests → green. Full CI gate green: ruff check + ruff format --check + mypy (typecheck env) + light (567 passed / 47 skipped / 1 xfailed) + smoke-pytorch (768 passed / 15 skipped / 1 xfailed).

**Version:** unversioned (rides the I.j.3 v0.17.0 bundle).

---

### Story I.j.2: Adopt the family `overlays` standard across MF (atomic rename + multi-overlay list) [Done]

One coherent cross-layer rename of MF's *own* overlay surface `variants` → `overlays`, widened to an ordered list (last-writer-wins per section, mirroring DR). Atomic so the tree stays green; **cache-invalidating** so the canonical-hash pin is re-pinned **in this story**. **Byte-mover correction:** the actual canonical-byte shift comes from **`DataSpec.variant: None` → `overlays: []`** (the `Data` sub-document lives in the hashed `core` segment), *not* the `ModelRecipe.overlays`-catalog `_OVERLAY_FIELD` rename — the catalog is always cleared by the loader pre-hash (sparse-omitted), so it never contributes bytes. Both renames still land; only the `DataSpec` one moves the pin.

- [x] **Recipe layer.** [recipe/models.py](../../src/modelfoundry/recipe/models.py) `ModelRecipe.variants:` → `overlays:`; `DataSpec.variant` → `overlays: list[str] = []`. `git mv` [recipe/variants.py](../../src/modelfoundry/recipe/overlays.py) → `recipe/overlays.py`; `apply_variant(dict, str|None)` → `apply_overlays(dict, Sequence[str]|None)` with ordered last-writer-wins merge (accumulate `_deep_merge` over the list) + unknown-name error. [recipe/loader.py](../../src/modelfoundry/recipe/loader.py) param/import/call. [recipe/__init__.py](../../src/modelfoundry/recipe/__init__.py) docstring.
- [x] **Cache identity.** [recipe/canonical.py](../../src/modelfoundry/recipe/canonical.py) `_OVERLAY_FIELD = "variants"` → `"overlays"` (+ partition comment). Segment label stays `"overlays"` (already named so since Phase I) — this aligns the *recipe field* to the *segment*. (Byte-neutral on its own, per the correction above.)
- [x] **Validator.** Check 16 `variants_keys_declared` → `overlays_keys_declared`; `variants_block` param → `overlays_block` ([validator.py](../../src/modelfoundry/recipe/validator.py)). (Op-param "variant" at validator.py:146/454 left — scope guard.)
- [x] **Consumer surface (same commit, stays green).** [core/config.py](../../src/modelfoundry/core/config.py) `RuntimeConfig.variant` → `overlays: list[str] = []`; [core/manifest.py](../../src/modelfoundry/core/manifest.py) `manifest.variant` → `overlays: list[str]` (**MF ModelInstance on-disk contract change**); [core/modelfoundry.py](../../src/modelfoundry/core/modelfoundry.py) (`overlays` param/attr/docstrings, `Sequence[str]|None` normalized to `list`); [pipeline/runner.py](../../src/modelfoundry/pipeline/runner.py); [data_binding.py](../../src/modelfoundry/pipeline/data_binding.py) (dropped the I.j.1 interim bridge — passes the real `overlays` list to DR); [reporting/report.py](../../src/modelfoundry/reporting/report.py) (joins the list).
- [x] **CLI.** [cli/app.py](../../src/modelfoundry/cli/app.py) `--variant` → `--overlay` (repeatable `list[str]`); [materialize_cmd.py](../../src/modelfoundry/cli/commands/materialize_cmd.py) + [status_cmd.py](../../src/modelfoundry/cli/commands/status_cmd.py) param/pass-through + manifest display (join overlays).
- [x] **Re-pin + tests.** Re-pinned `_PINNED_HASH` (`eca50b…` → `1ab1a6…`) in [test_canonical.py](../../tests/unit/test_canonical.py) with a conscious-sign-off comment. `git mv` `test_recipe_variants.py` → `test_recipe_overlays.py` (added ordered/last-writer-wins list tests). Updated `test_cache_identity_properties.py` (Hypothesis props), `test_config.py`, `test_recipe_validator.py`, `test_manifest.py`, `test_segmented_identity.py` (comment), `test_fixture_foundation.py`, `test_cifar10_resnet20.py`, and the `overlays=[]` manifest-construction sites across `test_reporting`/`test_cache_cleaner`/`test_inspection_view`/`test_pytorch_summary`/`tests/cli/{clean,inspect,report,status,materialize}_cmd`. `git mv` fixtures `pytorch_with_variants.yml` → `…_overlays.yml` (87% sim), `invalid_variants_keys.yml` → `invalid_overlays_keys.yml` (89%); `variants:`→`overlays:` in `cifar10_resnet20.yml` (both copies) + `cifar10_cnn.yml` (+ `--variant`→`--overlay` in those recipes' comments). Left `recipe/sections.py` op-variant terminology and `test_data_binding.py`'s **DataRefinery**-recipe `variants:` block untouched (scope guard — DR-side, green under DR v0.23).

> **Rename history note.** `recipe/overlays.py` (27% git-similarity) and `test_recipe_overlays.py` (43%) fell below git's default 50% rename threshold despite `git mv` — the single→list rewrite + docstring changes diverged the content, so a default `git log` shows delete+add (`--follow -M30%` traces them). `_deep_merge` and file structure were preserved (not rewritten from scratch).

**Version:** unversioned (rides I.j.3).

---

### Story I.j.3: Cache-invalidation release ceremony — owns v0.17.0 [Done]

The single ceremonious release for the bundle's one cache-invalidation event (per `project-essentials.md` "invalidations are ceremonious" + OR-9 pre-prod rules).

- [x] **CHANGELOG.md** — added the `## [0.17.0] - 2026-06-22` entry: DR v0.23.0 adoption + the MF `overlays` rename; blast radius (every MF cache invalidated → re-materialize, second event after v0.16.0), recipe-author migration note (`variants:` → `overlays:`, repeatable `--overlay`, `manifest.variant`→`overlays`), and the conscious canonical re-pin reference (`eca50b…` → `1ab1a6…`, I.j.2).
- [x] **Bump** → `0.17.0` in [src/modelfoundry/_version.py](../../src/modelfoundry/_version.py) (the version source of truth; `pyproject.toml` reads it dynamically via `[tool.hatch.version]`, so there is no literal version line in `pyproject.toml` to edit). `modelfoundry.__version__` now reports `0.17.0`.
- [x] Confirmed the full CI gate green at the bump: ruff check + ruff format --check (162 files) + mypy (typecheck env, 162 files) + light (569 passed / 47 skipped / 1 xfailed, incl. `test_release_metadata` CHANGELOG↔version guard) + smoke-pytorch (770 passed / 15 skipped / 1 xfailed).

**Version:** **minor → v0.17.0** (cache-invalidating family-standard adoption; second invalidation event after I.h's v0.16.0; pre-prod OR-9 — release-note + re-materialize, no migration written, zero pre-1.0 support window).

---

### Story I.j.4: Documentation & shared-contract alignment [Done]

Reconcile MF's spec docs to the shipped `overlays` surface (alignment, not net-new requirements — the code is source of truth). Doc-only; rides v0.17.0.

- [x] **MF `features.md`** — FR-14 retitled `Variants` → `Overlays` (list semantics, last-writer-wins; **flipped** the now-contradicted "CLI rejects multiple `--variant` flags" to "repeatable `--overlay`, applied in order"); CR-12 `Variants` → `Overlays`; the `(recipe, data_instance, seed, overlays)` determinism tuple (CR-5/QR-1/§Persistence/AC-6); OR-5 overlay-selection, UR-4/§13 recipe-shape lists, NG-9; `Data.overlays`, check 16, `--overlay` flag-table row, status-report fields, TR-1/TR-2 ("overlay merge"/"overlay switch"). Left op-param "class-weighted variant", DR "aggressive variant sidecar", "ResNet variant", "aggressive-mode variants", and "invariant(s)" untouched.
- [x] **MF `tech-spec.md`** — module tree `recipe/variants.py` → `recipe/overlays.py` (`# FR-14 overlay application`); `from_recipe`/module-`materialize`/`load_recipe` signatures `variant: str|None` → `overlays: Sequence[str]|None`; `DataSpec`/`RuntimeConfig` `overlays: list[str] = []`; `Manifest.overlays: list[str]`; `ModelRecipe.overlays` catalog; call-site `overlays=overlays`; loose-coupling note; `--overlay` flag-table + subcommand list; added a `recipe_segments` docstring note on `_OVERLAY_FIELD = "overlays"` (cleared pre-hash). Left op-param `param_model = variant` + aggressive-augmentation + "invariant" untouched.
- [x] **MF `concept.md`** + **`README.md`** — `overlays` phrasing + the determinism tuple; the two `README` YAML examples (`variants:` → `overlays:`) + their `--overlay` commands; concept recipe-section lists + "Named **overlays** … last-writer-wins". Left DR per-record-seed "for variants" + "invariants" untouched.
- [x] **`docs/guides/recipe-authoring.md`** — N/A: absent for MF (degraded gracefully, no error).

**Version:** no bump (doc-only; rides v0.17.0).

---

### Story I.j.5: Cross-repo governance — `join_stable` byte-format divergence [Done]

Record the family-contract status surfaced by the upgrade. **Not an MF code change** — a governance/coordination action.

- [x] **Finding — verified empirically against the installed DR v0.23.0.** DR has now *implemented* its `join_stable` (`datarefinery.recipe.segments.join_stable`), closing the open precondition. **The byte formats diverge:** DR is `b"\x1f".join(digests)` (`_JOIN_SEP = b"\x1f"`, an unframed unit-separator join of the raw per-segment digests); MF uses a **labeled, length-framed, label-sorted, prefix-capable** concatenation ([canonical.py](../../src/modelfoundry/recipe/canonical.py)). Both kept prefix-capability (DR exposes `prefix_hash`). This does **not** functionally break MF — MF consumes the DR instance as an opaque hashed unit (reads DR's `manifest.recipe_hash`, XORs into `data_instance_hash16`; never recomputes DR's hash with MF's combiner). It becomes load-bearing only if/when the deferred vertical / cross-tool hash-chain axis ships.
- [x] **Updated `project-essentials.md`** — replaced the "DR has not yet implemented `join_stable`" open item with the resolved status (DR v0.23 implemented it; formats diverge — both forms quoted; doesn't break MF; aligning is a cross-repo coordination event, not an in-tree fix; do not change MF's combiner unilaterally). Same resolution note added to the I.b cross-repo checkpoint in [`docs/spikes/I.a-segmented-recipe-identity.md`](../spikes/I.a-segmented-recipe-identity.md).
- [x] **Surfaced to the family** — recorded as the open coordination question in both docs ("is `join_stable`'s byte format meant to be byte-identical across the four tools, or only structurally analogous?"). The cross-team ask (DataRefinery → ModelFoundry → nbfoundry → learningfoundry) is a developer/maintainer action outside this repo; MF's combiner is **not** altered unilaterally.

**Version:** no bump (doc/governance; rides v0.17.0).

---

### Story I.k: DR→MF persisted-image hand-off — resolve an instance-relative `path` against the instance (Gap 1) [Done]

Bug fix (debug cycle). Surfaced by the consumer happy-path run logged in
[`consumer-gap-analysis.md`](consumer-gap-analysis.md) Gap 1 (verdict in
[`consumer-gap-solutions.md`](consumer-gap-solutions.md)): DataRefinery's
`png_per_record` sink rewrites each record's `path` to an **instance-relative**
string (`images/<split>/<Class>/<id>.png`), but MF's loader resolved a bare `path`
with `Path(str(record["path"]))` — **CWD-relative**. Both MF `validate` (22 checks)
and DR `materialize` pass; training then dies pulling pixels (`FileNotFoundError`)
— a silent-failure class. The next consumer would hit the same wall, so the fix is
on MF's side (no DR change, no per-instance sidecar patch needed).

- [x] **Reproduce (test-first).** `test_decode_resolves_instance_relative_path_from_other_cwd` in [test_pytorch_data_adapter.py](../../tests/unit/test_pytorch_data_adapter.py): a record with only an instance-relative bare `path`, decoded from a CWD that is not the instance, raised `FileNotFoundError` before the fix. Added a `relative_paths` flag to the fixture builder to mimic the sink's `path` rewrite.
- [x] **Fix the resolution.** Extracted [`_resolve_image_path`](../../src/modelfoundry/plugins/pytorch/data.py#L210): an `image_path` sidecar still resolves under `dataset/`; a bare `path` is used as-is when **absolute** (normal external-source flow) and anchored to **`self.instance.path`** when **relative** (the sink case) — never CWD.
- [x] **Cheap fail-fast gate.** Renamed `_verify_aggressive_sidecars` → [`_verify_record_images_resolvable`](../../src/modelfoundry/pipeline/data_binding.py#L211) (called at bind time, [data_binding.py:124](../../src/modelfoundry/pipeline/data_binding.py#L124)): keeps the `image_path`-sidecar "sidecar missing" check **and** now refuses an instance-relative bare `path` whose file is absent (surfaces at bind, before the long run); absolute source paths are skipped (loader uses them as-is). Tests `test_instance_relative_path_missing_refused` / `test_instance_relative_path_present_binds` in [test_data_binding.py](../../tests/unit/test_data_binding.py).
- [x] **Full CI gate green.** ruff check + ruff format --check (162 files) + mypy (typecheck env, 162 files) + light (571 passed / 47 skipped / 1 xfailed) + smoke-pytorch (773 passed / 15 skipped / 1 xfailed).
- [x] **Prevention scan.** `_decode`/`_resolve_image_path` is the only image-path resolution site (sklearn/random plugins have no image loader); the bind-time verifier was the only sidecar gate. No other CWD-relative `Path(record[...])` construction found.
- [ ] **Housekeeping — stale doc citations.** `consumer-gap-analysis.md` cites the workaround script and audio brief at paths that don't match where the consumer-copied files landed (`scripts/examples/add_mf_image_path_sidecar.py`, `docs/specs/modelfoundry-audio-feature-consumption.md`); and the copied seam docs reference a `docs/specs/modelfoundry/` subdir that doesn't exist here. Settle the directory convention and fix the links (developer call — see solutions doc "Doc-hygiene findings").
- [ ] **Housekeeping — cross-repo.** Optionally raise with the family whether DR's `png_per_record` should also emit an `image_path` sidecar relative to `dataset/` (aligning both tools on MF's preferred branch). Not required — the MF-side fix stands alone.

**Version:** **patch → v0.17.1** (bug fix). **Not cache-invalidating** — this is path *resolution* logic only; the recipe hash, canonical bytes, and materialized output bytes are unchanged for any run that already succeeded (it only makes previously-failing instance-relative paths resolve). No ceremony.

---

## Subphase I-1: Audio Feature-Array Consumption

ModelFoundry's consumer half of the audio feature-array seam — the PyTorch loader path that consumes prepared log-mel spectrogram feature arrays from a materialized DataRefinery instance via the per-record `feature_path` field, applying the persisted per-mel-bin `audio_normalize` fit-on-train statistics at load. The MC-dropout stochastic path and `Inference` recipe block are **already built and modality-agnostic** ([stochastic.py](../../src/modelfoundry/plugins/pytorch/stochastic.py), [models.py:91-128](../../src/modelfoundry/recipe/models.py#L91)) — this subphase adds only the loader branch + the clip-level window aggregation that layers over it.

Derived from [`consumer-gap-solutions.md`](consumer-gap-solutions.md) Gap 3 (decision: build the feature-array path; spectrogram-as-image is rejected as lossy) and bound to [`datarefinery/vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md) § "Audio feature-array persistence" (Q1–Q6), § "Audio spectral features", § "`audio_normalize` statistics", § "Audio window records" (R7), and § "Failure modes ModelFoundry SHOULD detect". Full gap analysis, the pinned-contract facts, the mini-features/tech-spec, and the out-of-scope walkthrough live in [`phase-i-subphase-1-audio-feature-consumption-plan.md`](phase-i-subphase-1-audio-feature-consumption-plan.md).

---

> **Release cadence (Subphase I-1) — phase-bundled, one minor (multi-release exception).** Phase I already shipped (I.h → v0.16.0, I.j.3 → v0.17.0, I.k → v0.17.1). Subphase I-1 is a follow-on subphase that ships its **own** release tag — the documented Version-Cadence multi-release exception (`_phase-letters.md` § Subphases). Stories I.l–I.q carry no version; **I.r owns the single minor bump → v0.18.0** (new additive capability). **Not cache-invalidating** for any existing instance: the loader change is additive and the only canonical-bytes surface (the I.o aggregation-policy recipe field) is authored only by *audio* recipes — no existing image instance is perturbed. Pre-prod, no production ceremony.

> **Cross-repo sequencing — RESOLVED (DR v0.25.0).** DataRefinery has now **shipped** the `npy_per_record` sink + `feature_path` rewrite (DR Stories K.c/K.d, v0.24.0–v0.25.0); the vendor-spec § "Audio feature-array persistence" is ratified **shipped**, no longer forward-declared. MF built its half against the pinned Q1–Q6 contract with a synthesized `.npy` fixture (Story I.l), and Story I.m.1 **verified the loader end-to-end against a real DR materialize** — the synthesized fixture and real DR output agree. MF consumes the instance **read-only** (never re-hashes it — loose-coupling invariant).

---

### Story I.l: Synthesized audio feature-array fixture builder [Done]

Test substrate, foundation-first — no `src/` change. Extend the fixture machinery ([tests/fixtures/datarefinery_instances/builder.py](../../tests/fixtures/datarefinery_instances/builder.py), or add a sibling `audio_smoke/builder.py`) to emit a DataRefinery-shaped **audio** instance matching the pinned contract, so every following story has something to test against. → New [tests/fixtures/datarefinery_instances/audio_smoke/builder.py](../../tests/fixtures/datarefinery_instances/audio_smoke/builder.py) (`build_dr_audio_instance`), wired as a `dr_audio_instance` conftest fixture ([tests/conftest.py](../../tests/conftest.py)), verified by [test_audio_fixture_foundation.py](../../tests/unit/test_audio_fixture_foundation.py) (11 tests). Loads through the **real installed DR v0.23.0** `audio_classification` plugin + `dr.Instance.load` (the `npy_per_record` sink format is a plain `str`, so the forward-declared value persists/round-trips cleanly despite DR not shipping the sink yet).

- [x] **Feature arrays on disk.** Write `features/<split>/<record_id>.npy` as `(n_mels, n_frames)` `float32` (vendor-spec Q3/Q4); allow a nested `record_id` (`<clip>/<...>__w####`) to exercise the nested-POSIX case (Q5). → `clip_id = <class>/clip_<n>` ⇒ `feature_path` nests below `features/<split>/` by default; array written `rng.random(...).astype(np.float32)`, rank-2.
- [x] **Window-record JSONL.** Each `<split>.jsonl` record carries `feature_path` (instance-root-relative, Q1), `source_record_id` (parent clip), `window_index`, label, and `record_id = <clip_id>__w{window_index:04d}`. Optionally include a stray source `path` on one record to exercise Q6 (`feature_path` authoritative). → `windows_per_clip` (default 2) windows per clip; `stray_path_on_first=True` rides a `path` on one record.
- [x] **`audio_normalize` fitted stats.** `fitted_statistics/<op_id>/{mean,std}.parquet` — per-mel-bin, **`n_mels` rows**, axis-0 order, single `value` column (parity with image `normalize`); include a zero-variance mel bin to exercise the `std == 0 → 1.0` guard. → `op_id = "audio_norm"` (= the `audio_normalize` featurization step name; exported as `AUDIO_NORM_OP_ID`); `float64` stats; `zero_variance_bin` (default 3) writes `std == 0.0`.
- [x] **Manifest + recipe.** `manifest.record_counts` **post-windowing**; `manifest.sinks[<name>].format = "npy_per_record"`; a recipe object exposing an `audio_normalize` op in its **`Featurizations`** section. Add a builder variant that produces a **dangling `source_record_id`** (window → no clip) for the I.o failure-mode test. → `record_counts` = window counts (8 train / 4 val by default); `sinks["features"].format = "npy_per_record"`; recipe authors a `log_mel_spectrogram` + `audio_normalize` `Featurizations` pair; `dangling_source_record_id=True` appends one orphan window whose `source_record_id` matches no `record_id` prefix.

**Version:** no bump (test fixtures; rides v0.18.0).

---

### Story I.m: Feature-array branch in `_decode` + per-record branch selection [Done]

Add the feature-array load path; image path unchanged (additive). → New branch in [data.py:`__getitem__`](../../src/modelfoundry/plugins/pytorch/data.py#L179) + `_decode_features`/`_resolve_feature_path`; bind gate extended in [data_binding.py:`_verify_record_images_resolvable`](../../src/modelfoundry/pipeline/data_binding.py#L211). Verified by [test_pytorch_audio_data.py](../../tests/unit/test_pytorch_audio_data.py) (7 tests) against the I.l fixture.

- [x] **Branch selection.** In [data.py:`_decode`](../../src/modelfoundry/plugins/pytorch/data.py#L210) / `_resolve_image_path` precedence: a record carrying `feature_path` takes the feature branch; `feature_path` is **authoritative over a stray `path`** (Q6); `image_path`/bare `path` keep the image branch. → `__getitem__` checks `"feature_path" in record` first and returns `_decode_features(...)`; the image branch (augment + normalize) is untouched (label resolution factored into a shared `_label_for`).
- [x] **Resolve `feature_path`.** Instance-root-relative (`<instance>/<feature_path>`, Q1 — the I.k sink-`path` bucket, **not** `dataset/`-relative); nested POSIX join, verbatim (Q5). A missing feature file is refused at bind time (extend the I.k `_verify_record_images_resolvable` gate to cover `feature_path`). → `_resolve_feature_path` joins `self.instance.path / feature_path`; the bind gate now checks `feature_path` **first** (authoritative) and raises `"feature array not resolvable"` when absent.
- [x] **Load + shape.** `np.load`, **assert `ndim == 2`** (Q4 — refuse otherwise), unsqueeze to `(1, n_mels, n_frames)`; preserve the raw `float32` mel values (no `/255`, no premature normalize — normalization is I.n's job, applied at `__getitem__`). → `np.ascontiguousarray(array, dtype=np.float32)` → `torch.from_numpy(...).unsqueeze(0)`; rank≠2 raises `DataBindingError` naming `ndim`. Test asserts `torch.equal` to the raw unsqueezed array (verbatim, un-normalized).
- [x] **Geometry guard.** Confirm `_refuse_unbaked_geometry_transforms` does not false-trip on the audio path (features are sinked content, not pre-transform pixels); add/adjust as needed. → No code change needed: the audio recipe's `Transformations` is empty (it uses `Featurizations`), so the guard returns early; covered by `test_audio_instance_binds_without_geometry_guard`.
- [x] **Tests (via I.l fixture).** Decode resolves a nested instance-relative `feature_path` from a **CWD that is not the instance** (parity with I.k's regression); `feature_path` wins over `path`; non-2-D array refused; default image fixtures still decode unchanged. → All four covered (foreign-CWD, Q6 stray-path authority, rank guard); image-path coverage unchanged in [test_pytorch_data_adapter.py](../../tests/unit/test_pytorch_data_adapter.py) (full smoke suite green).

**Version:** no bump (rides v0.18.0).

---

### Story I.m.1: Real-DR audio materialize end-to-end smoke [Done]

Ordering-insert (sub-numbered for placement, not a split of I.m): now that **DataRefinery v0.24.0** shipped the `npy_per_record` sink + `feature_path` rewrite (DR Stories K.c/K.d), verify MF's I.m loader against an **actually-materialized** DR audio instance — not just the synthesized I.l mimic. A real `dr.materialize` proves the seam end-to-end and pins MF's loader assumptions to DR's true output bytes. **Skip-if-absent** on `librosa`/`soundfile`/`torch` so the light env and audio-less CI stay green. Distinct from I.p (the MF-internal MC-dropout *acceptance* test on the synthesized fixture). → New [test_audio_real_dr.py](../../tests/integration/test_audio_real_dr.py) (6 tests, module-scoped real materialize); **no `src/` change** — MF's I.m loader binds real DR v0.24.0 output unmodified.

- [x] **Env: audio decode deps.** Add `librosa` + `soundfile` to the smoke-pytorch env ([tests/integration/env/pytorch.txt](../../tests/integration/env/pytorch.txt)) — DR's `audio_flat` source decodes via `librosa.load`; both are `ml-datarefinery[audio]`'s closure. Light env unaffected (test skips without them).
- [x] **Synthesized WAV source + real materialize.** A helper synthesizes per-class sine-tone `.wav` clips (offline, no downloads) in a flat layout + an id→label CSV, authors a DR `audio_classification` recipe (`audio_flat` + `label_from` `by_id`/`kind: direct`; `window` Generation op; `log_mel_spectrogram` + fit-on-train `audio_normalize` Featurizations with explicit `splits` + `fit_source: train`; an `npy_per_record` Sink on field `mel` at `post_Featurizations`), and runs a real `dr.materialize`. → **Spike-discovered DR wiring** (recorded so I.n–I.r don't re-derive it): the `window` op needs `seed` + explicit `splits`; featurization ops need **explicit `splits`** (empty ≠ all — no-implicit-defaults); `audio_normalize` needs `fit_source: train`; `mel`/`feature_path` must **not** be in `Output.record_schema` (the Generation stage requires every declared Output field on each generated record, but `mel` is post-Featurizations and `feature_path` is sink-rewritten); `audio_folder` doesn't stamp `label` (use `audio_flat` + `label_from` `by_id` / `kind: direct`, mirroring the image `_materialize` fixture).
- [x] **MF end-to-end bind + decode.** Bind the materialized instance through MF (`resolve_data_instance` real consumer path → schema gate + `_verify_record_images_resolvable` + `DataRefineryDataset`); assert the feature branch decodes real DR output to `(1, n_mels, n_frames)` float32, `feature_path` resolves instance-root-relative (Q1) and nested (Q5), the stray source `.wav` `path` is ignored in favor of `feature_path` (Q6), `audio_normalize` fitted stats are per-mel-bin, labels resolve (3 classes), and `record_counts` is post-windowing. → Verified against a real instance: `feature_path = features/<split>/clips/<n>.wav__w####.npy`, feature `(1, 16, 32)` float32, decode is **byte-verbatim** to DR's `.npy` (no normalize at load — I.n's job).
- [x] **Full CI gate green.** ruff + ruff format + mypy (166) + light (581 passed / 49 skipped — audio integration module skips without torch/librosa) + smoke-pytorch (796 passed / 15 skipped / 1 xfailed; the 6 real-DR audio tests materialize + bind green).

**Version:** no bump (rides v0.18.0).

> **Cross-repo note.** DR v0.24.0 shipped the sink; MF verified the pinned Q1–Q6 contract against DR's actual `write_npy_per_record` / `feature_path_rewrite_plan` code. The forward-declared vendor-spec § "Audio feature-array persistence" status (and the I.j.5 governance entry) want a "shipped/verified" doc update — folded into the subphase's doc-sync story (I.q/I.r), not here.

---

### Story I.n: `audio_normalize` fit-on-train branch [Done]

Apply the persisted per-mel-bin statistics at load — the audio analogue of image `normalize`, on the correct axis. → New `_resolve_audio_normalization_steps` + audio apply in [data.py:`__getitem__`](../../src/modelfoundry/plugins/pytorch/data.py#L210); `_read_vector` gains a `dtype` param. Verified by [test_pytorch_audio_data.py](../../tests/unit/test_pytorch_audio_data.py) (byte-match + zero-variance + fit-on-train registration) and the real-DR end-to-end ([test_audio_real_dr.py](../../tests/integration/test_audio_real_dr.py)).

- [x] **Read DR `Featurizations`.** Extend [data.py:`_resolve_normalization_steps`](../../src/modelfoundry/plugins/pytorch/data.py#L89) to scan the bound recipe's **`Featurizations`** section (today only `Transformations` is scanned) for an `audio_normalize` op and read its `mean`/`std` vectors (`n_mels` rows) from `fitted_statistics/`. → Done as a sibling `_resolve_audio_normalization_steps` (keeps the image resolver's CHW reshape untouched); reads `Featurizations` tolerantly via `getattr(..., None) or []` (image recipes omit/empty it).
- [x] **Register fit-on-train op.** Add `audio_normalize` to [`_FIT_ON_TRAIN_OPS`](../../src/modelfoundry/plugins/pytorch/data.py#L39) so the geometry guard treats it as non-baked.
- [x] **Apply on the mel axis.** Per-mel-bin standardization on **axis 0**: `(feat − mean[:, None]) / std[:, None]` — **not** the image CHW `.view(-1, 1, 1)`. Make the reshape modality-aware, driven by the active branch (I.m). `float64` stats over the `float32` array with promotion (Q3); same exact zero-variance guard (`std == 0 → 1.0` at apply, persisted `std` unmodified). → Audio stats reshape to `(1, n_mels, 1)` (mel bins on axis 1 of the `(1, n_mels, n_frames)` tensor); applied only in the feature branch; `_read_vector(..., dtype=torch.float64)` promotes, output cast back to `float32`.
- [x] **Tests.** Per-mel-bin standardized output byte-matches a hand-computed reference (including the zero-variance bin); image `normalize`/`mean_subtract` reshape path unchanged. → `test_audio_normalize_applied_per_mel_bin` byte-matches a torch reference incl. the planted std==0 bin; `_decode_features` raw-verbatim test split out; image adapter suite unchanged (full smoke green).

**Version:** no bump (rides v0.18.0).

---

> **Split at implementation time (I.o → I.o.1 + I.o.2).** The story proved oversized: the settled design + the byte-neutral recipe surface is one coherent commit, and the aggregation engine (math + a Plugin-Protocol signature change across all four plugins + evaluation wiring + dangling refusal + validator) is a second. Split per the scope-splitting rule to keep each a clean unit.

### Story I.o.1: `WindowAggregation` recipe surface + byte-neutral canonical wiring [Done]

The settled design (R7) + the recipe section it introduces. → New `WindowAggregationSpec` + `ModelRecipe.WindowAggregation` ([models.py](../../src/modelfoundry/recipe/models.py)); sparse-merge into the plugin segment ([canonical.py](../../src/modelfoundry/recipe/canonical.py)). The aggregation math + wiring is I.o.2.

- [x] **Design decision (settled per the I.a frozen contract; memorialized in `tech-spec.md`).** (a) Aggregation lives in the **evaluation stage** ([evaluation.py](../../src/modelfoundry/plugins/pytorch/evaluation.py)) — regroup window predictions by `source_record_id`; the loader is untouched. (b) The policy is a new **top-level `WindowAggregation` section** in the **plugin** segment (I.a Decision 2: `Evaluation`/`Inference` are plugin-segment), **sparse-omitted when absent** so existing image recipes' canonical bytes are byte-identical (I.a's "omitting an optional yields identical bytes" — no re-pin, not a cache-invalidation event). **Mode-selecting optional** (no-implicit-defaults): `WindowAggregation = None ⇒ window-level eval`; when present, `policy: Literal["mean","logit_average","majority_vote"]` is author-required. The "absent ⇒ window-level" mapping is part of the versioned plugin-segment contract. *(Top-level, not nested under `Evaluation`: a field inside the always-present `Evaluation` sub-doc would bake a `null` into every recipe and perturb all of them — only a sparse top-level section delivers the audio-only byte-shift the subphase promises.)* → The sparse-optional-section rule is now memorialized in [tech-spec.md](../../docs/specs/tech-spec.md) § "Adding a recipe section byte-neutrally", with `WindowAggregation` as the worked example.
- [x] **Recipe surface + byte-neutral canonical.** `WindowAggregationSpec(policy=...)` (`extra="forbid"`, author-required `policy`); `ModelRecipe.WindowAggregation: … | None = None`. `recipe.canonical` sparse-merges it into the plugin segment only when present (`_SPARSE_PLUGIN_FIELDS`), so an absent section contributes nothing. Verified in [test_segmented_identity.py](../../tests/unit/test_segmented_identity.py): absent ⇒ not in plugin segment + no `WindowAggregation` bytes; present ⇒ in plugin segment + perturbs hash; policy change perturbs. The pinned `_PINNED_HASH` ([test_canonical.py](../../tests/unit/test_canonical.py)) is **unchanged** (no re-pin — image recipes byte-identical).

**Version:** no bump (rides v0.18.0).

---

### Story I.o.2: Clip-level window aggregation engine (R7) + dangling-key refusal + validator [Planned]

The consumer-owned aggregation math (DR ships no aggregation op). Layers over the **already-built** MC-dropout per-record outputs ([stochastic.py](../../src/modelfoundry/plugins/pytorch/stochastic.py)), driven by the I.o.1 `WindowAggregation` policy.

- [ ] **Group + aggregate.** Regroup window-level predictions (incl. MC-dropout means / `predictive_entropy` / `mc_variance`) by `source_record_id` into clip-level results; apply the declared policy. All three policies produce a clip-level `(C,)` probability vector (mean of window probs / logit-space mean / normalized vote histogram) so clip-level metrics + uncertainty compute uniformly. `window_index` available for order-sensitive policies. Thread `recipe.WindowAggregation` through the `Plugin.run_evaluation` Protocol (base + pytorch/sklearn/random) into the evaluation stage; emit a clip-level predictions surface + clip-level metrics when present.
- [ ] **Dangling-key failure mode.** Per vendor-spec § Failure modes: a window whose `source_record_id` does not resolve to its clip — DR guarantees `record_id == f"{source_record_id}__w{window_index:04d}"`, so a mismatch (or missing `source_record_id`) → **refuse**. Test via the I.l dangling-key fixture variant.
- [ ] **Validator cross-check.** When `WindowAggregation` is declared, cross-check the bound instance's records carry `source_record_id` (a producible grouping); surface a misdeclaration at `validate`, not mid-run.

**Version:** no bump (rides v0.18.0).

---

### Story I.p: End-to-end audio MC-dropout integration test (acceptance) [Planned]

The brief's verification, turned into the acceptance gate.

- [ ] **End-to-end run.** A materialized (synthesized, I.l) audio instance + a 1-channel spectrogram-CNN recipe with `Inference: {mode: mc_dropout, mc_samples: T}` trains end-to-end, producing per-record `predictive_entropy` / `mc_variance` and `ece` over MC-aggregated means, **clip-level** via I.o.
- [ ] **Reproducibility parity.** Assert **byte-deterministic** across two runs (excluding wall-clock fields) and **round-trips from disk** (`ModelInstance.load(path).predict(...)` without external config) — the four determinism invariants hold on the audio path exactly as the image path.
- [ ] **Image path unaffected.** A default image MC-dropout/integration test stays green (additive guarantee).
- [ ] **Full CI gate green.** ruff check + ruff format --check + mypy (typecheck) + light + smoke-pytorch.

**Version:** no bump (rides v0.18.0).

---

### Story I.q: Gap 2 docs — Encoder-normalization recipe pattern [Planned]

Zero code (image-encoder, orthogonal to audio; folded in as the last open item in the same solutions doc). Closes the Gap 2 *intuition* gap so the next consumer doesn't re-derive it.

- [ ] **Document the pattern** at the recipe surface: a frozen pretrained encoder gets its exact stats today via DR `resize` (baked → uint8 sink) + fixed-stat `normalize` (applied at load by MF over the uint8 pixels) — **no `Encoder`-op preprocessing, no code change**.
- [ ] **Units caveat + conversion table.** MF applies `(x − mean)/std` on **0-255 pixel units with no `/255`** ([data.py:189-199](../../src/modelfoundry/plugins/pytorch/data.py#L189-L199)); HF stats are `[0,1]`-unit, so write **`mean₂₅₅ = image_mean × 255`, `std₂₅₅ = image_std × 255`** into the DR `normalize` op. Include the worked ImageNet / ViT `[-1,1]` table from [`consumer-gap-solutions.md`](consumer-gap-solutions.md) Gap 2.

**Version:** no bump (doc-only; rides v0.18.0).

---

### Story I.r: Doc sync, project-essentials append & release — owns the bump (→ v0.18.0) [Planned]

- [ ] **`features.md`** — add FR-AUDIO-1 (feature-array consumption), FR-AUDIO-2 (clip-level window aggregation R7 + dangling-key refusal), FR-AUDIO-3 (reproducibility parity).
- [ ] **`tech-spec.md`** — reflect the loader feature-array branch, the `audio_normalize` mel-axis read path, the window/clip record model, and the aggregation-policy recipe field.
- [ ] **`concept.md` / `README.md`** — adjust scope wording if needed (audio feature consumption now in scope on the PyTorch plugin).
- [ ] **Vendor-spec mirror note** — record that MF's consumer half is **ready**; the seam stays **forward-declared** until DR ships `npy_per_record` (re-ratified to shipped when both land). Any change MF needs to the *shared* contract is **proposed to DR** (attributed `MF:`), never edited in the MF mirror in isolation.
- [ ] **`project-essentials.md`** — append any new must-know facts (plan_phase Step 8): the `feature_path`/`audio_normalize`/window-aggregation loader contract and the read-only loose-coupling reminder.
- [ ] **Release** — owns the single minor bump **→ v0.18.0**; release note: new audio feature-array consumption capability; **not cache-invalidating** for existing instances.

**Version:** **minor → v0.18.0** (new additive capability; multi-release-exception bump for Subphase I-1). Not cache-invalidating for existing instances.

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
