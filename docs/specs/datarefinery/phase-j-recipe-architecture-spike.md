# Spike memo — Segmented recipe identity (scoped cache invalidation)

**Status:** design spike — exploratory. Deliverable is this memo + a `plan_phase` recommendation. **No code, no tests, no version bump, no frozen commitments** — final decisions belong to the `plan_phase` round this memo feeds.
**Trigger:** Story J.n Finding A — `target_sample_rate` on the shared `InputSource` would invalidate *every image recipe's* cache for an audio-only knob. Developer reframed this as a general architecture question: separate what is truly general from what is plugin / overlay / experimental, so DR has room to experiment before committing cache-breaking changes.
**Audience:** the `plan_phase` invocation that will turn this into a phase (Phase K candidate) of stories.

---

## 1. Problem

Cache identity is DR's core contract: `cache_key = SHA-256(canonical_recipe_bytes) ⊕ SHA-256(raw_input_bytes) ⊕ seed`, and `canonical_recipe_bytes = json.dumps(recipe.model_dump(mode="json"), sort_keys=True, …)` ([canonical.py:20-40](../../src/datarefinery/recipe/canonical.py#L20-L40)).

`model_dump` is **total** — every field on the whole `Recipe` graph serializes, always, including defaults for fields the recipe never meaningfully uses. Four consequences:

1. **Identity is coupled to class-hierarchy shape, not to pipeline behavior.** Two recipes that would materialize byte-identical output can hash differently if the *model* gained a field between them; a field no pipeline reads still moves the hash.
2. **Cross-modality blast radius.** A field added to a shared model (e.g. `InputSource`) perturbs canonical bytes for *every* recipe of *every* modality — the J.n Finding A failure. Adding audio invalidates image caches.
3. **No room to experiment.** `model_config = extra="forbid"` ([models.py:24](../../src/datarefinery/recipe/models.py#L24)) blocks any unknown key. You cannot prototype a parameter in a real recipe without first committing it to the schema — and the moment it ships with a default, it's in canonical bytes for everyone, forever.
4. **One global `schema_version`.** A single counter ([loader.py](../../src/datarefinery/recipe/loader.py): `SUPPORTED_SCHEMA_VERSIONS = {1,2}`, `LATEST = 2`) governs all shape changes, so a plugin-local change and a core change are indistinguishable to the migration/invalidation machinery — every bump is a whole-world event.

DR is pre-1.0; breaking schema changes are frequent and (today) *cheap* — users re-materialize, note it in release notes. Post-1.0 each break is hours-to-days of recompute per user (project-essentials § "Cache identity is the reproducibility contract"). **The cost of un-scoped identity rises sharply at 1.0.** This is the cheap moment to fix it — likely the last one.

---

## 2. The unifying insight

The developer's four layers (general / plugin variant / orthogonal variant / extensions) are not four mechanisms — they are one: **segmented canonical bytes**. Identity should be composed from independent segments, and a recipe contributes only the segments it actually uses.

There is already a working precedent in the codebase: **op-level `params: dict[str, Any]`** (`TransformationOp`, `AugmentationOp`, etc., [models.py:348-363](../../src/datarefinery/recipe/models.py#L348-L363)). Op params are opaque to core, plugin-interpreted, and **participate in canonical bytes only when the op is declared**. That is exactly the property we want — scoped, self-isolating identity — but it exists only on ops. The rearchitecture is largely: **lift the `params`-bag + plugin-partitioning pattern up from ops to sources, sections, and recipe-level, and make the hasher segment-aware so empty/unused segments contribute nothing.**

### Layer → precedent → gap

| Layer | Precedent in DR | Gap |
|---|---|---|
| **General core** | Splits, seed, Labels, stage skeleton, plugin name | None — changes here *should* invalidate everyone; this stays the small, ceremony-heavy core. |
| **Plugin surface** | the plugin system + op `params` | The recipe *model* isn't partitioned by plugin. Image/audio share `InputSource` and section types → no isolation. |
| **Orthogonal overlay (LoRA-like)** | `variants` (FR-14), applied pre-hash via `apply_variant` | Variants collapse into the base before hashing; not a composable, independently-identified dimension. |
| **Extensions (declarative)** | op `params: dict[str, Any]` | No `params`/extension bag above the op level; `extra="forbid"` blocks experimentation at source/section/recipe scope. |

---

## 3. Design principles (proposed)

1. **Identity is a function of what the recipe *does*, not how the model is shaped.** A field the active pipeline never reads should not move the hash.
2. **Scoped invalidation.** A plugin-surface change touches only that plugin's recipes. A core change touches everyone (correctly). An overlay/extension change touches only recipes that use it.
3. **Promotion is the one ceremony.** Moving a parameter from `extensions` into core/plugin surface is the deliberate, announced, cache-breaking event. Everything short of that is blast-radius-bounded.
4. **The recipe stays declarative.** Extensions carry *parameters* read by already-installed code. A recipe MUST NOT become an executable artifact that points at arbitrary code to run (see § 6).
5. **No silent collisions.** Scoping must never let two recipes that produce different output hash the same. "Doesn't break other caches" — never "doesn't affect identity at all."
6. **No implicit defaults.** No behavior-affecting value is ever supplied by the interpreting code at runtime. The recipe text is the complete description of behavior; identity hashes only what the author wrote (sparse — absent keys contribute nothing). See the resolved stance below.

### The honest benefit (reframe)

The win is **not** "experiments don't change the hash." If an experimental param affects output but is excluded from identity, two experiments collide on one instance — worse than a cache break. The achievable win is: experiments and plugin changes are **blast-radius-bounded**, and **promotion to core is the single ritual**. That converts "every change breaks every cache" into "changes are scoped; one deliberate moment breaks."

### Resolved stance (recommended to plan_phase; adjustable, not frozen)

Three commitments fell out of the design discussion. They sharpen the principles above into rules; plan_phase may revise but should start from them.

1. **No *implicit* defaults — kill code-supplied values, not recommended values.** The danger is never a default *value*; it is a value *applied silently by the interpreting code*, where absence-in-the-recipe lets a code change move outcomes with no recipe change. So the interpreting code supplies nothing. Recommended starting values still exist — but the **scaffolder (`init`) emits them explicitly into the recipe text**, so they are in canonical bytes, audit-visible, and versioned. *The default belongs to the tool that writes the recipe, never to the code that reads it.* This dissolves the project-essentials nightmare ("a pydantic default change silently shifts every omitting recipe's hash") — there are no omitting recipes. Two kinds of optionality must stay distinct:
   - **Default-value optionality** (absent ⇒ code fills in `X`): **eliminated**.
   - **Mode-selecting optionality** (absence is itself meaningful — `normalize` with no `mean`/`std` ⇒ "fit from train"; `f_max: None` ⇒ "Nyquist"): **kept**, but the "absent ⇒ behavior" mapping is part of the **versioned plugin-segment contract**, not a mutable code default. Changing what "absent" means is a behavior change ⇒ bump.

2. **`required` vs. `optional` *is* the bump-vs-free decision.** With no implicit defaults: adding a **required** param makes existing recipes that lack it *invalid* ⇒ **breaking** ⇒ plugin-segment version bump (+ support window). Adding a **mode-selecting optional** param leaves non-adopting recipes untouched (sparse hashing: absent key contributes nothing) ⇒ **free**. "Is the new param required or optional?" answers "is this release cache-breaking?" — a teachable rule.

3. **Content-addressed ⇒ the support window is a *re-derivability* horizon, not a validity one.** A behavior-only code change (same recipe text, different output) triggers a plugin-segment version bump with old schema **and** old behavior supported for a formal window. But because the cache is content-addressed, **existing on-disk instances never break** — their bytes are immutable regardless of code. The support window only governs whether an old instance stays *re-derivable from source* (i.e., whether the old code path is retained). So the cost is bounded: "re-derivable for N versions back," not "old code forever." When a plugin-version drops out of support, old instances still exist and are usable; they are merely no longer regenerable.
   - **Pre-1.0 policy: the support window is _zero_ by default** — a behavior bump retains no old code path unless a compelling reason arises. Pre-1.0, re-derivability of superseded instances is not promised; users re-materialize. The window becomes a real (non-zero) commitment only at/after 1.0, or earlier case-by-case.

**Scope note.** This is a breadth change, not a small diff: every existing op's `ParameterSpec(default=…)` ([plugins/base.py](../../src/datarefinery/plugins/base.py)) is re-examined, the scaffolder becomes the value-emitter, and adopting no-implicit-defaults is itself a one-time mass invalidation. Affordable **pre-1.0**; reinforces the do-it-now timing (§ 8).

---

## 4. The segment model (sketch — for plan_phase to refine)

Decompose `Recipe` canonical bytes into ordered, independently-hashed segments:

- **`core`** — universal: core-schema-version, plugin name, seed, `Splits`, `Labels`, the stage skeleton, the cache/determinism contract knobs.
- **`plugin`** — the active plugin's surface only: its source types (incl. audio's `target_sample_rate`), its section/op param shapes. An image recipe's `plugin` segment never contains audio fields.
- **`overlays`** — zero or more composable, independently-identified overlay dimensions (generalizing `variants`). Each overlay hashes on its own; their composition is order-stable.
- **`extensions`** — a sanctioned declarative bag (`extensions:` / `x-*` namespace) where `extra="forbid"` is relaxed *only inside the namespace*. Plugin/hook code reads it; it enters identity only when non-empty.

**Segment-aware canonical bytes (candidate):**
```
canonical = join_stable(
    H(core_segment),
    H(plugin_segment),      # empty-marker if (impossible) absent
    H(overlay_1) … H(overlay_n),   # empty list → contributes nothing
    H(extensions),          # empty bag → contributes nothing
)
recipe_hash = SHA-256(canonical)
```
Key property: an **empty segment contributes a fixed nothing**, so introducing the `extensions` mechanism (empty for everyone) breaks *no* existing cache, and an audio-plugin change leaves every image recipe's `recipe_hash` byte-identical (enforced by per-segment pin tests, § 7). **Design `join_stable` so it can also express *cumulative prefix* composition — `H(H_upstream ‖ segment)` — not only flat concatenation**, so the vertical axis (below) can be layered later without re-specifying the combiner. (Cheap to allow for now; expensive to retrofit.)

**Per-segment versioning.** Replace the single global `schema_version` with per-segment versions (e.g. `core` v_n, `plugin:image` v_m, `plugin:audio` v_k). A plugin-surface bump + migration invalidates only that plugin's recipes. Migration registry keyed by `(segment, from, to)`. Whether a thin global umbrella version remains is an open question for plan_phase.

### Vertical axis — stage-reuse (acknowledged, deferred; from the ModelFoundry reciprocal spike)

The downstream sibling [ModelFoundry spike](modelfoundry/phase-i-recipe-architecture-spike.md) adds a second, *orthogonal* axis: sub-hash each pipeline **stage** as a cumulative prefix hash and reuse an expensive upstream artifact when only downstream segments change. DR should record it — and design so as not to preclude it — but treat it as **secondary and deferred** (see honesty note below).

**The safe reframe DR adopts verbatim:** the *external* identity stays the global `recipe_hash` — `(recipe, input, seed, variant) → byte-identical instance` is unchanged — and stage sub-hashes are a **purely internal materialization-cache optimization** ("how we compute the instance," not "what it is"). No external guarantee weakens; the only new obligation is internal — a reused stage artifact must be byte-identical to a from-scratch run (a per-stage extension of the determinism contract).

**DR already has embryonic stage-reuse** worth crediting as precedent: the runner computes per-stage `viz_snapshots`; `export` re-runs sinks against an existing instance without re-materializing; `report()` re-renders from persisted state; `stop_after`/`STAGE_NAMES` perform partial runs. The waterfall would formalize these into prefix-keyed stage caching.

**Why secondary for DR (the honest asymmetry).** DR's compute gradient is far flatter than ModelFoundry's — whose 1,000-GPU-hour Training stage makes *it* the family's prime beneficiary and gives the vertical axis genuine urgency there. DR's stages run seconds-to-minutes (maybe hours for big jobs), so the axis is *real but not urgent*. DR's genuinely expensive cut-points are narrow — aggressive-augmentation realization, audio decode+window+featurize, normalize fit. If DR adopts this at all, prefer a **minimal cut** (cache only those boundaries; leave the cheap tail always-recomputed), or simply lean on the existing `export`/`report`/partial-run primitives. The full stage-artifact-store + materialization-control-flow overhaul ModelFoundry needs is **disproportionate to DR's gradient** — do not cargo-cult its cost structure.

**Soundness invariant if DR ever stages:** each stage must read *only* its declared upstream — a stage reading a field hashed into a *later* segment breaks reuse correctness. Enforced by stage-boundary pin tests (§ 7). The reason to record this now rather than ignore it is purely to keep the segment model + `join_stable` able to express prefix chains — **design-not-to-preclude, build-only-if-justified.**

---

## 5. What stays in core vs. moves out

- **Core (universal, ceremony-heavy):** stage model, Splits, Labels, seed, determinism/worker contract, cache-identity algorithm itself.
- **Plugin surface (scoped):** input source types and their params, plugin op param shapes, plugin-stamped fields. *Audio's `target_sample_rate` lives here* — the direct resolution of J.n Finding A, generalized.
- **Overlays (scoped, composable):** the `variants` mechanism, reconsidered as first-class orthogonal dimensions.
- **Extensions (scoped, experimental):** declarative bespoke params, pre-promotion.

---

## 6. The extensions trust boundary (must not be hand-waved)

There are **two** very different things under "extensions":

- **Declarative bespoke parameters — IN SCOPE, safe.** Data read by already-installed plugin/hook code. This is just op `params` generalized to higher scopes. It keeps the recipe a pure data artifact. Ship this confidently.
- **Recipe-activated arbitrary code (hooks/callbacks the recipe points at) — OUT OF SCOPE for this memo; needs its own trust-boundary design.** A recipe is checked into version control and handed off; DR's value proposition is "recipe = declarative source of truth." A recipe that names code to execute turns the artifact executable, with supply-chain/trust implications, on top of the already-unsandboxed-plugin posture (project-essentials). The *hook seam* belongs to plugins (installed, trusted code), not to the recipe text. Recommendation: the recipe carries **parameters**; **plugins** own the code that interprets them. If recipe-driven code activation is ever wanted, it is a separate, deliberate trust-boundary story — not a freebie riding along with declarative extensions.

---

## 7. Enforcement

Segmentation is only real if isolation is *tested*. Per-segment canonical-hash pin tests:

- An **image-only fixture's `recipe_hash` MUST NOT move** when the audio plugin surface changes (and vice-versa).
- A **recipe with no extensions MUST hash identically** before and after the extensions mechanism is introduced.
- Each segment gets its own pinned fixture; a hash change there forces a conscious per-segment `schema_version` bump + migration.
- *(Only if the vertical axis (§ 4) is adopted)* **a downstream-only segment change MUST leave the expensive upstream stage's prefix hash byte-identical** (vertical isolation — the test that guarantees the reused artifact), and a reused-upstream materialization MUST byte-match a from-scratch run (extends the determinism suite).

This subsumes and extends the existing [stories.md § Future "default-change discipline tooling"](stories.md) entry, which already calls for multi-fixture pin coverage + a CI guard against silent default changes.

---

## 8. Migration / rollout

- The rearchitecture itself changes canonical bytes **once** (the segment-combination function differs from today's flat dump). That is a one-time, deliberate, pre-1.0 invalidation — every existing recipe re-materializes once. Acceptable and cheap *now*; prohibitive post-1.0.
- **Strong timing argument:** do this **before 1.0**, before more modality/plugin surface accretes onto the flat model and multiplies the eventual migration. The developer's own observation ("breaking schema will happen more often than desired") is the case for building the scoping machinery now.

---

## 9. Open questions for plan_phase

*Resolved during the design discussion (now § 3 "Resolved stance"), no longer open:* sparse-hashing vs. version-pinning (answer: **both** — sparse via no-implicit-defaults is the default; per-segment versioning carries genuine behavior bumps); whether unused/default params perturb identity (answer: **no** — there are no implicit defaults); pre-1.0 support-window length (answer: **zero by default**).

Still open:

1. **Plugin-surface representation:** discriminated unions per shared model (per-type `ImageSource`/`AudioSource`) vs. a nested `plugin:` sub-document holding all plugin-scoped config. Trade-offs: unions are incremental and local; a sub-doc is a cleaner segment boundary but a bigger migration.
2. **Overlay composition & identity:** how `variants` maps onto first-class overlays; ordering/conflict rules; whether overlays compose additively (the LoRA analogy) or override.
3. **Segment-combination function:** exact `join_stable` (concatenated digests? Merkle?) and the empty-segment marker.
4. **Versioning:** per-segment versions only, or a thin global umbrella + per-segment? Migration-registry keying. (The *existence* of per-segment versioning is settled by the resolved stance; this is about the global-umbrella question and registry mechanics.)
5. **Extensions namespace:** syntax (`extensions:` block vs. `x-*` keys), where `extra="forbid"` relaxes, and how plugins declare which extension keys they consume (validator surface).
6. **Discovery/validator impact:** how the validator's stage/field checks and check-23 reserved-field logic adapt to segmented surfaces (ties to the Future "plugin-pluggable validator reserved-set hook").
7. **No-implicit-defaults rollout mechanics:** how `ParameterSpec` drops `default=` / how `required` is re-expressed; how the scaffolder sources the recommended values it now emits; how existing fixtures/recipes are mass-rewritten in the one-time migration.
8. **Vertical stage-reuse — adopt at all, and if so how minimal?** (§ 4 "Vertical axis".) Decide whether DR builds prefix-keyed stage caching or relies on the existing `export`/`report`/partial-run primitives; if it builds, scope to the minimal expensive-boundary cut (aggressive-augmentation realization / audio featurize / normalize fit) vs. full per-stage. Confirm `join_stable` supports cumulative-prefix composition regardless, so the door stays open.

---

## 10. Relationship to in-flight work

- **J.n Finding A** is the narrow first instance of this: the discriminated `AudioSource` is the **plugin-surface segment in miniature**. Under this architecture it is a stepping stone, not throwaway — but plan_phase may choose the nested-sub-doc representation instead, which would reshape it.
- **Subphase J-1 (audio, J.o–J.w) is PAUSED** pending this rearchitecture, per the developer's "design spike first" decision — so audio is built once, on the segmented foundation, rather than on the flat model and then refactored.
- **Cross-tool family standard.** The downstream sibling [ModelFoundry spike](modelfoundry/phase-i-recipe-architecture-spike.md) adopts DR's horizontal mechanism + no-implicit-defaults **wholesale** ("family policy, not DR-local"). That promotes the horizontal recipe-identity model to a **cross-repo contract across the tool family** — same governance status as the vendor-dependency-specs: DR holds it as the shared standard and coordinates changes cross-repo rather than diverging unilaterally. The **vertical stage-reuse axis is ModelFoundry's contribution** (justified by its 1,000-GPU-hour gradient); DR records it as an option (§ 4) and may adopt a minimal form later, but it is not part of the shared horizontal standard.
- **Recommendation:** run **`plan_phase`** to draft a new phase ("Segmented recipe identity / scoped cache invalidation", Phase K candidate) from this memo. Sequence it **before** resuming J-1 audio. Creating the phase heading + story bundle is `plan_phase`'s job, not this mode's.

---

## 11. Recommendation summary

1. Adopt **segmented canonical bytes** (core / plugin / overlays / extensions) as the unifying mechanism; it resolves J.n Finding A as a special case and gives DR room to experiment with bounded blast radius.
2. Adopt **no implicit defaults** (§ 3 resolved stance): the interpreting code supplies no behavior-affecting value; the scaffolder emits recommended values explicitly into the recipe; `required` vs. `optional` *is* the bump-vs-free rule; sparse hashing means absent keys don't perturb identity.
3. Keep the recipe **declarative**: extensions carry params; plugins own code. Defer any recipe-activated-code idea to a separate trust-boundary effort.
4. Enforce isolation with **per-segment canonical-hash pin tests**; adopt **per-segment versioning**, with the **pre-1.0 support window = zero by default** (re-derivability of superseded instances not promised until a compelling reason / 1.0).
5. **Acknowledge the vertical stage-reuse axis but defer it** (§ 4, from the ModelFoundry reciprocal spike): keep `join_stable` able to express prefix chains so it can be layered later, but DR's flatter compute gradient makes it secondary — build only a minimal expensive-boundary cut if/when justified, or lean on existing `export`/`report`/partial-run primitives. The horizontal mechanism + no-implicit-defaults are the **cross-tool-family standard** (ModelFoundry adopts them wholesale); coordinate changes cross-repo (§ 10).
6. **Do it pre-1.0**, before more surface accretes.
7. Next step: **developer runs `plan_phase`** against this memo; **J-1 audio stays paused** until the foundation lands.
