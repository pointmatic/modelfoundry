# Spike memo — Segmented + staged recipe identity (scoped & waterfall cache invalidation)

**Status:** design spike — exploratory. Deliverable is this memo + a `plan_phase` recommendation. **No code, no tests, no version bump, no frozen commitments** — final decisions belong to the `plan_phase` round this memo feeds.
**Trigger:** Two converging pressures. (1) DataRefinery's [Phase-J recipe-architecture spike](datarefinery/phase-j-recipe-architecture-spike.md) proposes **segmented canonical bytes** (scoped, blast-radius-bounded identity) for the upstream tool; the four-tool family should share one identity model. (2) Subphase H-1 surfaced the same hazard locally — a new stochastic-inference recipe field would invalidate *every* existing recipe's cache under the flat model (see [subphase-h-1 plan §3 cache note](subphase-h-1-advanced-probabilistic-plan.md)). Separately, the developer raised that ModelFoundry's **extreme per-stage compute asymmetry** (a 1,000-GPU-hour Training stage feeding cheap downstream Evaluation/Visualization/Reporting) makes a *staged*, waterfall invalidation worth designing now.
**Audience:** the `plan_phase` invocation that will turn this into a phase (Phase I candidate) of stories.

---

## 1. Problem

Cache identity is ModelFoundry's core contract (project-essentials § "Cache identity is the reproducibility contract"):

```
cache_key = SHA-256(canonical_recipe_bytes) ⊕ SHA-256(data_instance_hash) ⊕ seed
canonical_recipe_bytes = json.dumps(recipe.model_dump(mode="json"), sort_keys=True, separators=(",",":"), ensure_ascii=False)
```

`model_dump` is **total** — every field on the whole `ModelRecipe` graph ([recipe/models.py:135](../src/modelfoundry/recipe/models.py#L135)) serializes always, including defaults for fields a recipe never meaningfully uses. This yields the same four consequences DR identified, plus one ModelFoundry-specific one:

1. **Identity is coupled to class-hierarchy shape, not pipeline behavior.** A field added between two releases moves the hash even if output is byte-identical.
2. **Cross-surface blast radius.** A field added to a shared spec perturbs canonical bytes for every recipe — the H-1 stochastic-inference field would invalidate every existing (non-stochastic) recipe.
3. **No room to experiment.** `extra="forbid"` blocks prototyping a parameter in a real recipe without first committing it to the schema; once it ships with a default it is in canonical bytes for everyone, forever.
4. **One global `schema_version`** ([loader.py:26](../src/modelfoundry/recipe/loader.py#L26): `SUPPORTED_SCHEMA_VERSIONS = frozenset({1})`) governs all shape changes — a plugin-local change and a core change are indistinguishable; every bump is a whole-world event.
5. **(ModelFoundry-specific) Invalidation is all-or-nothing across a steep compute gradient.** Any recipe edit → full re-materialize, *including re-running the most expensive stage*. A user who trains for 1,000 GPU-hours and then tweaks an Evaluation metric, MC-dropout `T`, a calibration bin count, or a visualization re-pays the entire training cost for a change that provably cannot affect the trained weights.

ModelFoundry is pre-1.0; breaking schema changes are frequent and (today) *cheap* — users re-materialize, note it in release notes (OR-9). Post-1.0 each break is hours-to-days of recompute per user (project-essentials). **The cost of un-scoped, un-staged identity rises sharply at 1.0 — and ModelFoundry's training cost makes consequence (5) bite hardest of any tool in the family.** This is the cheap moment to fix it.

---

## 2. The unifying insight — two orthogonal axes of one mechanism

Identity should be composed from independent **segments**, and a recipe contributes only the segments it actually uses. ModelFoundry needs the mechanism along **two orthogonal axes**:

- **Horizontal (DR's axis) — by ownership/trust scope.** `core` / `plugin` / `overlays` / `extensions`. Resolves cross-surface blast radius and gives room to experiment. *Adopt DR's design wholesale* for family unity.
- **Vertical (ModelFoundry's own axis) — by execution-stage dependency along the compute waterfall.** Sub-hash each stage as a cumulative prefix; reuse the expensive upstream artifact when only downstream segments change.

They compose: a stage's segment can itself be plugin-scoped. Design them together rather than bolt the waterfall on later.

### Precedent already in the codebase

DR found its precedent in op-level `params: dict[str, Any]` (scoped, plugin-interpreted, in canonical bytes only when declared). ModelFoundry has the same precedent **at the stage level**: `Architecture: dict[str, Any]` ([recipe/models.py:142](../src/modelfoundry/recipe/models.py#L142)) is already an opaque, plugin-interpreted bag with exactly the self-isolating property we want. The horizontal rearchitecture is largely: **lift that pattern to the other stages and make the hasher segment-aware so empty/unused segments contribute nothing.** The vertical rearchitecture is new work, detailed in §4.

### Layer → precedent → gap (horizontal axis)

| Layer | Precedent in MF | Gap |
|---|---|---|
| **General core** | `schema_version`, `plugin`, `seed`, `Data` binding, the stage skeleton, determinism contract | None — changes here *should* invalidate everyone; small, ceremony-heavy core. |
| **Plugin surface** | the plugin system + `Architecture` dict bag + per-op param models | The recipe *model* isn't partitioned by plugin; `Loss`/`Optimizer`/`Training`/`Evaluation` are typed specs shared across plugins → no isolation. |
| **Orthogonal overlay** | `variants: dict[str, dict]` ([models.py:150](../src/modelfoundry/recipe/models.py#L150)), applied pre-hash | Variants collapse into the base before hashing; not a composable, independently-identified dimension. |
| **Extensions** | `Architecture` dict (the only relaxed bag today) | No sanctioned `extensions`/`x-*` bag above the architecture stage; `extra="forbid"` blocks experimentation elsewhere. |

---

## 3. Design principles (proposed — adopt DR's, unchanged)

DR's six principles and three "resolved-stance" commitments port directly; they are family policy, not DR-local. In brief:

1. **Identity is a function of what the recipe *does*, not how the model is shaped.**
2. **Scoped invalidation** — plugin change touches only that plugin's recipes; core change touches everyone (correctly); overlay/extension change touches only adopters.
3. **Promotion is the one ceremony** — moving a param from `extensions` into core/plugin surface is the deliberate, announced, cache-breaking event.
4. **The recipe stays declarative** — extensions carry *parameters* read by already-installed code; a recipe MUST NOT name arbitrary code to run (§7). ModelFoundry's plugins are unsandboxed (project-essentials), so this boundary is load-bearing here too.
5. **No silent collisions** — scoping must never let two recipes with different output hash the same.
6. **No implicit defaults** — the interpreting code supplies no behavior-affecting value; the **scaffolder (`init`) emits recommended values explicitly into the recipe text**, so they are in canonical bytes, audit-visible, versioned. This *directly dissolves* ModelFoundry's project-essentials nightmare and the H-1 flag — there are no omitting recipes to silently shift. `required` vs. `mode-selecting optional` becomes the bump-vs-free rule.

(Full reasoning, including the content-addressed re-derivability horizon and the pre-1.0 zero-support-window stance, in [DR's memo §3](datarefinery/phase-j-recipe-architecture-spike.md). ModelFoundry adopts it as-is unless `plan_phase` finds a divergence.)

**Governance (added after DR's reciprocal round).** DR's revised memo elevates the **horizontal mechanism + no-implicit-defaults** to a **cross-tool-family standard** — held by DR at the same governance status as the vendor-dependency-specs, coordinated cross-repo rather than diverged unilaterally ([DR memo §10](datarefinery/phase-j-recipe-architecture-spike.md)). Consequence for ModelFoundry: adopting the horizontal axis is **not a free local choice** — a future `plan_phase` that wants to diverge from the shared horizontal contract (segment boundaries, `extensions` namespace, no-implicit-defaults rules) must treat it as a **cross-repo coordination event**, not an in-tree decision. This is a stronger commitment than the existing "discipline travels across the family" pattern in project-essentials (which is parallel copies); it is a *governed shared contract*. The **vertical stage-waterfall axis remains ModelFoundry's own** — DR has ratified it as our contribution and is keeping `join_stable` prefix-capable for us (§4b), but it is not part of the shared standard and we own its design.

---

## 4. The segment model (sketch — for plan_phase to refine)

### 4a. Horizontal segments (per DR)

- **`core`** — `schema_version`, `plugin`, `seed`, `Data` binding, the stage skeleton, determinism/cache-identity knobs.
- **`plugin`** — the active plugin's surface only: its architecture-op shapes, loss/optimizer/training/eval param shapes. A PyTorch recipe's `plugin` segment never carries a sklearn-baseline field, and vice-versa.
- **`overlays`** — zero or more composable, independently-identified dimensions (generalizing `variants`).
- **`extensions`** — sanctioned declarative bag (`extensions:` / `x-*`), `extra="forbid"` relaxed only inside the namespace; enters identity only when non-empty.

Empty segment ⇒ fixed-nothing contribution, so introducing the mechanism (extensions empty for everyone) breaks no existing cache.

### 4b. Vertical segments — the stage waterfall (ModelFoundry's novel contribution)

ModelFoundry's stages form a compute gradient:

```
core(seed, data) → Architecture → Optimization → Training → Evaluation → OutputExpectations → Visualizations → Persistence → Reporting
                     cheap          VERY exp.      VERY exp.   cheap         cheap                cheap             —             cheap
```

Sub-hash each stage as a **cumulative prefix hash** over all upstream segments + its own:

```
H_arch  = H(core ‖ architecture_segment)                 # seed feeds weight_init (prepare_for_build) → in core
H_opt   = H(H_arch ‖ optimization_segment ‖ data_hash)   # Optuna study; reads data
H_train = H(H_opt  ‖ training_segment)                   # the weights — the 1,000-hour artifact
H_eval  = H(H_train ‖ evaluation_segment)
H_out   = H(H_eval  ‖ output_expectations_segment)
H_viz   = H(H_eval  ‖ visualizations_segment)            # depends on eval/predictions, not on each other
recipe_hash (global, external identity) = H(H_viz ‖ H_out ‖ reporting_segment)
```

**Cache artifacts at the expensive cut-points keyed by prefix hash** — the post-Optimization study (`best_params`) and the post-Training weights. Materialization becomes: walk the stage DAG, compute each stage's prefix hash, and recompute only from the first stage whose prefix changed. Change only `Evaluation`/`Visualizations` → `H_train` unchanged → trained weights are a hit → recompute from Evaluation onward. **That is the 1,000-hour win.**

**The reframe that makes it safe:** the *external* identity is still the **global `recipe_hash`** — `(recipe, data, seed, variant) → byte-identical ModelInstance` is unchanged. Stage sub-hashes are a **purely internal materialization-cache optimization** ("how we compute the instance," not "what it is"). No external guarantee is weakened. The only new obligation is internal: a reused stage artifact must be byte-identical to a from-scratch run — the per-stage extension of the existing four determinism invariants (project-essentials § "Determinism contract").

**Shared combiner shape (cross-repo).** DR's revised memo commits to designing `join_stable` so it can express **cumulative-prefix composition** (`H(H_upstream ‖ segment)`), not only flat concatenation — explicitly so this vertical axis can be layered later without re-specifying the combiner ("cheap to allow now; expensive to retrofit," [DR memo §4](datarefinery/phase-j-recipe-architecture-spike.md)). ModelFoundry should **match that combiner shape** when it builds the prefix chain, so the two tools' segment-combination functions stay consistent across the family.

**Embryonic stage-reuse precedent (already in the codebase).** Mirroring DR's credited precedents, ModelFoundry already has partial-run / re-render primitives the waterfall would *formalize* rather than invent: the `report` CLI command and `ModelInstance.render_report()` ([core/instance.py:231](../src/modelfoundry/core/instance.py#L231)) re-render from persisted state; `rerender_report()` ([reporting/visualizations.py:49](../src/modelfoundry/reporting/visualizations.py#L49)); the runner's `_skip_stage()` ([pipeline/runner.py:247](../src/modelfoundry/pipeline/runner.py#L247)); and `manifest.is_partial` / `failed_stage` ([core/manifest.py:77](../src/modelfoundry/core/manifest.py#L77)) plus the cached-property accessors that read each artifact from disk. These are the seed of prefix-keyed stage caching — and the basis for a **minimal first cut** (see §5.6).

**Per-segment versioning** (both axes): replace the single global `schema_version` with per-segment versions (`core` v_n, `plugin:pytorch` v_m, `stage:training` v_k, …). A change bumps and invalidates only its segment's scope. Migration registry keyed by `(segment, from, to)`. Whether a thin global umbrella version remains is open (§9).

---

## 5. The hard parts (must not be hand-waved — ModelFoundry-specific risk)

The vertical axis is **bigger and riskier than DR's horizontal-only change**: it alters the cache *storage/layout* and the materialization *control flow*, not just the hash. Honest list of what `plan_phase` must resolve:

1. **Storage layout.** Today: one instance per key under `<cache-root>/instances/<key>/...`. The waterfall needs a **stage-artifact store** keyed by prefix hash, with the final `ModelInstance` assembled by composing the latest stage outputs. `manifest.json`, the `clean` workflow, and instance-load all change shape.
2. **Stage-dependency DAG correctness.** Soundness depends on each stage reading **only** its declared upstream. Sharp edges: `seed` is global → `core`, upstream of all (a seed change correctly invalidates the chain). **Data binding placement** — `Architecture` is data-independent (the `Head`'s `num_classes` is recipe-authored, only *validated* against the label schema), so the built/initialized model can cache independent of data; the `data_instance_hash` enters at the first data-reading stage (Optimization/Training). The `Optimization → Training` feedback (`best_params` → post-Optimization rebuild+retrain) is monotonic and fine. A hidden coupling (a stage reading a field hashed into a *later* segment) is the one thing that breaks soundness.
3. **Clean serialization cut-points.** Each cacheable boundary needs well-defined hand-off bytes: weights ✓ (`torch.save(checkpoint.model_dump())`), Optuna study ✓ (`trials`), but the cut must be byte-stable and reload-exact.
4. **Collision safety.** Holds by construction *if* every stage's prefix includes all upstream segment bytes — but only if no stage reads un-prefixed config. Enforced by stage-boundary pin tests (§6).
5. **Determinism per stage.** A reused upstream artifact + a fresh downstream run must equal a full from-scratch run, bit-for-bit (excluding wall-clock manifest fields). The existing `test_determinism.py` suite extends to per-stage reuse assertions.
6. **Is it worth the permanent machinery cost?** For a tool that exists to fix notebook-era ML experimentation, downstream-only iteration after expensive training is likely *constant* — and the H-1 consumer (LoRA fine-tune → iterate on `T`/uncertainty/calibration/eval) is the poster child. But the waterfall is forever-maintained complexity; `plan_phase` should weigh a **minimal first cut** (cache only the two expensive boundaries — post-Optimization and post-Training — leave the cheap tail always-recomputed) against full per-stage caching.

---

## 6. Enforcement

Segmentation is only real if isolation is *tested*. Per-segment + per-stage canonical-hash pin tests:

- A **PyTorch-only fixture's `recipe_hash` MUST NOT move** when a sklearn-baseline plugin field changes (horizontal isolation).
- A **recipe with no extensions MUST hash identically** before and after the extensions mechanism is introduced.
- **Changing only a downstream stage segment (e.g. `Evaluation`) MUST leave `H_train` byte-identical** (vertical isolation) — the test that guarantees the 1,000-hour artifact is reused.
- **A reused-upstream materialization MUST byte-match a from-scratch one** (extends `tests/integration/test_determinism.py`).
- Each segment/stage gets its own pinned fixture; a hash change there forces a conscious per-segment `schema_version` bump + migration.

---

## 7. The extensions trust boundary (unchanged from DR)

Two different things hide under "extensions": **declarative bespoke parameters** (IN SCOPE — data read by already-installed plugin code; just `Architecture`'s dict-bag generalized) vs. **recipe-activated arbitrary code** (OUT OF SCOPE — turns the recipe executable, supply-chain/trust implications on top of ModelFoundry's already-unsandboxed-plugin posture). The recipe carries **parameters**; **plugins** own the code that interprets them. Recipe-driven code activation, if ever wanted, is a separate trust-boundary story — not a freebie.

---

## 8. Migration / rollout & timing

- The rearchitecture changes canonical bytes **once** (the segment-combination function differs from today's flat dump). One-time, deliberate, pre-1.0 invalidation — every recipe re-materializes once. Cheap *now* (OR-9), prohibitive post-1.0.
- Adopting **no implicit defaults** is itself a one-time mass invalidation (every `init` template + fixture rewritten to emit values explicitly).
- **Strong timing argument: do this before 1.0**, before more plugin/stage surface accretes onto the flat model and multiplies the eventual migration — and before the production-release ceremony makes every cache break hours-to-days per user.

---

## 9. Open questions for plan_phase

Inherits DR's still-open set (plugin-surface representation: discriminated unions vs. a nested `plugin:` sub-document; overlay composition & identity; the `join_stable` segment-combination function + empty-segment marker; per-segment-only vs. thin-global-umbrella versioning; extensions namespace syntax & validator surface; no-implicit-defaults rollout mechanics). **ModelFoundry-specific additions:**

1. **Vertical scope — full per-stage caching vs. minimal two-boundary cut** (post-Optimization + post-Training only). The minimal cut captures ~all the compute win at a fraction of the machinery.
2. **Stage-artifact store layout** and how the final `ModelInstance` is assembled from prefix-keyed stage outputs; impact on `manifest.json`, `clean`, and `ModelInstance.load`.
3. **Data-binding placement in the prefix chain** — confirm `Architecture` is data-independent and `data_instance_hash` enters at the first data-reading stage; reconcile with the loose-coupled DataRefinery binding (the upstream `recipe_hash` still must not participate — project-essentials § "Loose-coupled DataRefinery binding").
4. **`variant` in the waterfall** — `variant` is part of external identity; where does it enter the prefix chain (likely `core`, since it can perturb any stage)?
5. **Interaction with `num_workers` reclassification** ([stories.md § Future](specs/stories.md)) — both touch what belongs in recipe identity vs. execution context; sequence them coherently.

---

## 10. Relationship to in-flight work

- **Subphase H-1 (advanced/probabilistic modeling) is the local trigger and the prime beneficiary.** Its stochastic-inference recipe field is the narrow first instance of consequence (2); under no-implicit-defaults + sparse hashing the H-1 cache flag *evaporates*. And H-1's workflow (expensive fine-tune → iterate downstream on `T`/uncertainty/calibration/eval) is exactly what the waterfall accelerates. **Sequencing of H-1 vs. this phase is the open developer decision this memo informs** (mirrors DR pausing J-1 audio pending its rearchitecture).
- **DataRefinery Phase-J/K (reciprocal round complete).** DR's [revised memo](datarefinery/phase-j-recipe-architecture-spike.md) has ratified the split: the **horizontal mechanism + no-implicit-defaults is now the cross-tool-family standard** DR coordinates (governance ~ vendor-dependency-specs; see §3 Governance), and the **vertical stage-waterfall is acknowledged as ModelFoundry's contribution** — DR records it as an option, keeps `join_stable` prefix-capable for us, but defers it (its compute gradient is far flatter; no 1,000-GPU-hour stage). The two recipe surfaces stay unified on the horizontal axis; ModelFoundry owns the vertical one.
- **Recommendation:** run **`plan_phase`** to draft a new phase ("Segmented + staged recipe identity", Phase I candidate) from this memo. Decide H-1 sequencing at that point. Creating the phase heading + story bundle is `plan_phase`'s job, not the current mode's.

---

## 11. Recommendation summary

1. Adopt DR's **segmented canonical bytes** (horizontal: core / plugin / overlays / extensions) wholesale — family unity; resolves the H-1 cache flag and cross-surface blast radius as special cases.
2. Adopt **no implicit defaults** (scaffolder emits values; code supplies none; `required` vs. `optional` = bump vs. free; sparse hashing) — dissolves the project-essentials default-shift nightmare.
3. Add the **vertical stage-waterfall** as ModelFoundry's own axis — global hash = unchanged external identity; stage sub-hashes = internal compute-reuse. Highest-value member of the family for this because of the 1,000-hour Training stage. Consider a **minimal two-boundary first cut**.
4. Keep the recipe **declarative**; extensions carry params, plugins own code.
5. Enforce both axes with **per-segment + per-stage canonical-hash pin tests**; per-segment versioning; pre-1.0 support window = zero by default.
6. **Do it pre-1.0**, before more surface accretes.
7. Next step: **developer runs `plan_phase`** against this memo; **H-1 sequencing decided then.**
