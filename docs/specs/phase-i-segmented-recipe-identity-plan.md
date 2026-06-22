# Phase I Plan: Segmented Recipe Identity (horizontal axis + no-implicit-defaults)

**Mode:** plan_phase · **Phase:** I · **Status:** Draft for approval

Source spike: [`phase-i-recipe-architecture-spike.md`](phase-i-recipe-architecture-spike.md).
Scope decisions (developer, 2026-06-22):
- **Axis:** horizontal segmented canonical bytes (`core`/`plugin`/`overlays`/`extensions`) **+ no-implicit-defaults**. The **vertical stage-waterfall is deferred** to its own future phase.
- **Representation:** recipe stays **flat on disk**; segment-aware hashing via **discriminated unions** on the plugin surface.

> **Heading refinement.** The placeholder heading ([stories.md:29](stories.md)) frames Phase I as "parameters segmented by plugin, underlying data flat." Accurate but partial — recommend extending the description to also name **no-implicit-defaults** and the `core`/`overlays`/`extensions` segments (not only `plugin`), since they ship together. Proposed wording in §6.

---

## 1. Gap analysis — flat total identity vs. segmented sparse identity

| Surface | Today | Gap (this phase) |
|---|---|---|
| **Canonical bytes** | Total `model_dump(mode="json")` over the whole `ModelRecipe`; every field (incl. defaults) hashed ([canonical.py:25](../src/modelfoundry/recipe/canonical.py#L25)) | Segment-aware combiner (`join_stable`): hash `core`/`plugin`/`overlays`/`extensions` independently; an **empty segment contributes a fixed nothing** |
| **Plugin partitioning** | `Loss`/`Optimizer`/`Training`/`Evaluation` are flat shared specs; plugin params ride on `extra="allow"` ([models.py:34-54](../src/modelfoundry/recipe/models.py#L34)) | Discriminated unions per shared spec (e.g. `PyTorchTraining` vs `SklearnTraining`) so a PyTorch-surface change leaves sklearn recipes byte-identical |
| **Experimentation** | `extra="forbid"` on `ModelRecipe` + structural specs ([models.py:173](../src/modelfoundry/recipe/models.py#L173)) blocks any unknown key | Sanctioned `extensions:` island where `extra` is relaxed *only inside the namespace*; enters identity only when non-empty |
| **Defaults** | Code-supplied pydantic defaults are in canonical bytes for every omitting recipe (`num_workers=2`, `precision="fp32"`, `Inference=None`, …) | **No implicit defaults**: interpreting code supplies no behavior value; scaffolder emits every value into recipe text; absent key ⇒ no hash contribution (sparse) |
| **Versioning** | One global `schema_version` ([loader.py:26](../src/modelfoundry/recipe/loader.py#L26)); no migration registry | Per-segment versions; migration-registry seam keyed by `(segment, from, to)` (empty pre-1.0 — zero support window) |
| **Validator** | 21 checks; checks 3 (`section_ops_registered`) + 17 (`op_params_match_spec`) assume flat specs ([validator.py:80](../src/modelfoundry/recipe/validator.py#L80)) | Adapt 3 + 17 to discriminated unions; add an `extensions`-claim check |
| **Enforcement** | Pinned golden hash ([test_canonical.py](../tests/unit/test_canonical.py)) + cosmetic/semantic Hypothesis props ([test_cache_identity_properties.py](../tests/unit/test_cache_identity_properties.py)) | Per-segment isolation pin tests; conscious golden re-pin (one-time) |

---

## 2. Feature requirements

- **F1 — Segmented canonical bytes.** Identity composed from independently-hashed `core`/`plugin`/`overlays`/`extensions` segments via a stable combiner; empty segment ⇒ fixed-nothing; introducing the mechanism (extensions empty for everyone) breaks no existing cache *beyond* the one-time combination-function change.
- **F2 — Discriminated-union plugin surface.** A plugin-surface change scopes to that plugin's recipes only; cross-plugin isolation is tested.
- **F3 — `extensions:` namespace.** Declarative bespoke params, `extra` relaxed only inside; plugins declare which keys they consume; recipe stays declarative (params only, never code — §7 of the spike).
- **F4 — No implicit defaults.** Interpreting code supplies no behavior-affecting value; scaffolder emits all values explicitly; **mode-selecting optionality is kept** (absence is meaningful) and its "absent ⇒ behavior" mapping becomes part of the versioned segment contract.
- **F5 — Per-segment versioning.** Replace the single `schema_version` with per-segment versions + a migration-registry seam (empty pre-1.0).
- **F6 — Enforcement + one-time rollout.** Per-segment isolation tests; conscious golden re-pin; release-note the single cache-invalidation event.

---

## 3. Technical changes

- **`recipe/canonical.py`** — replace the flat dump with `join_stable(H(core), H(plugin), H(overlays…), H(extensions))`. Combiner must be **prefix-capable** (accept an upstream digest, `H(H_upstream ‖ segment)`) per the cross-repo agreement with DR, *even though the vertical axis is deferred* — so the waterfall can layer later without re-specifying the combiner. Match DR's combiner shape.
- **`recipe/models.py`** — introduce discriminated unions on the shared stage specs (flat on disk via a discriminator field; concrete per-plugin variant types). Define the segment partitioning (which fields are `core` vs `plugin` vs `overlays` vs `extensions`). Add the `extensions` island.
- **No-implicit-defaults** — drop value-defaults from the param models / specs; **catalog and keep mode-selecting optionals** (current examples: `Inference.mc_samples=None ⇒ point mode`, `Training.early_stopping=None ⇒ none`, `Optimization=None ⇒ no HPO`, `Optimizer.schedule=None ⇒ constant LR`, `Data.variant=None`). The "absent ⇒ behavior" mapping moves into the versioned segment contract.
- **`scaffolder/init.py`** — becomes the value-emitter: emit every behavior-affecting field explicitly (extends [init.py:87](../src/modelfoundry/scaffolder/init.py#L87), which already emits most).
- **`recipe/loader.py`** — per-segment version gate + migration-registry seam keyed by `(segment, from, to)` (empty pre-1.0).
- **`recipe/validator.py`** — adapt checks 3 + 17 to discriminated unions; add an extensions-claim check; preserve the comprehensive (never-short-circuit) behavior.
- **Mass migration** — rewrite ~24 recipes (15 `recipes/` + 9 valid fixtures) + 14 invalid fixtures + the scaffolder template to the new flat-discriminated + explicit-values form. One-time.
- **Tests** — per-segment isolation pin tests; extend `test_cache_identity_properties.py`; **consciously re-pin** `_PINNED_HASH` in `test_canonical.py` (the deliberate sign-off the test exists to force).

### ⚠ Cache-identity / release discipline (load-bearing)

This phase changes canonical bytes **once** (combiner + representation + no-implicit-defaults all perturb bytes). Per project-essentials "Cache identity is the reproducibility contract" and the spike §8:

- **Ship as a single phase-bundled release** (Version Cadence "phase-bundling option"): stories run unversioned; the **last story owns one minor bump**; one documented cache-invalidation event, not one per story. This is the correct cadence precisely because the goal is "canonical bytes change once."
- Pre-prod (OR-9): release-note + re-materialize; **no migration written** (pre-1.0 support window = zero). The per-segment version *scheme* lands; actual migrations do not.
- The golden re-pin is the conscious reviewer sign-off.

---

## 4. Open-Questions (spike §9) — recommended defaults (settle at the approval gate / I.a spike)

| Question | Recommended default |
|---|---|
| Plugin-surface representation | **Flat + discriminated unions** (developer-decided). |
| `join_stable` shape + empty-segment marker | Length-framed, labeled concatenation of per-segment digests + a fixed empty sentinel; **prefix-capable**; match DR's shape. Exact bytes = **I.a spike** deliverable. |
| Overlay composition | Keep `variants` semantics unchanged; model the **selected variant's resolved delta as the `overlays` segment** so a variant edit scopes to that segment. First-class *composable additive* overlays (the LoRA-analogy) **deferred** (§6). |
| Versioning | **Per-segment versions**, plus a thin top-level umbrella that versions only the **combination function** (so the one-time rearchitecture is itself a version event). Migration registry seam present, empty pre-1.0. |
| Extensions namespace | A single **`extensions:` block** (not scattered `x-*` keys); `extra="allow"` only inside; plugins declare consumed keys; validator warns on unclaimed keys. |
| No-implicit-defaults rollout | Param models drop value-`default=`; **mode-selecting optionals kept** and cataloged; scaffolder emits values; one-time fixture/recipe/template rewrite. |

---

## 5. Proposed story breakdown (single ordered bundle — no subphases)

Vertical-axis deferral makes this tractable as one session's bundle. Led by an **architectural spike** (spike §9 leaves the combiner + representation mechanics genuinely unproven). **Phase-bundled release:** stories carry no version in title; **I.h owns one minor bump** at end-of-phase.

- **I.a — Architectural spike: `join_stable` + discriminated-union representation + segment boundaries + per-segment version scheme + mode-selecting-optionality catalog + `num_workers` classification.** Throwaway; deliverable = a decisions doc settling the §4 mechanics with a small proof (stable bytes; cross-plugin isolation demonstrated; validator-on-unions feasible) **and the `num_workers` recipe-vs-execution-context decision** (Option A: move to `RuntimeConfig` + `--num-workers` + `MODELFOUNDRY_NUM_WORKERS`), implemented in the bundle. *No bump.*
- **I.b — Segment model + segment-aware canonical bytes** (`join_stable`, empty-segment sentinel, prefix-capable). Horizontal isolation pin test scaffolding. *(bundled)*
- **I.c — Discriminated-union plugin surfaces** (flat shared specs → unions); adapt validator checks 3 + 17. *(bundled)*
- **I.d — `extensions:` namespace** (relaxed island; empty-bag = no hash change; validator extension-claim check). *(bundled)*
- **I.e — No-implicit-defaults** (drop value-defaults; keep + catalog mode-selecting optionals; scaffolder emits all values). *(bundled)*
- **I.f — One-time mass migration** (rewrite ~24 recipes + 14 invalid fixtures + scaffolder template; re-pin `_PINNED_HASH` with conscious sign-off). *(bundled)*
- **I.g — Per-segment versioning + migration-registry seam** keyed by `(segment, from, to)` (empty pre-1.0). *(bundled)*
- **I.h — Enforcement, release & docs** (per-segment isolation Hypothesis/pin tests; release-note the single invalidation; update `project-essentials.md` for the segmented-identity contract + the cross-family governance status). **Owns the minor bump.**

> Size note: 8 stories, single bundle. If you'd rather split (e.g. I-1 mechanism `I.a–I.d`, I-2 no-implicit-defaults + rollout `I.e–I.h`), say so — but the vertical deferral keeps it within single-session range.

---

## 6. Out of scope (negotiate item-by-item — Step 4)

1. **Vertical stage-waterfall** — deferred to its own future phase (Phase J candidate). `join_stable` is kept **prefix-capable** here so it is not precluded. *(This is the big deferral; confirm.)*
2. **Recipe-activated code** — extensions carry parameters only; plugins own code (spike §7). Any recipe-driven code activation is a separate trust-boundary effort.
3. **First-class composable additive overlays** (the LoRA-analogy) — `variants` semantics stay as-is; the composable-overlay generalization is deferred.
4. ~~**`num_workers` cache-identity reclassification**~~ — **pulled into Phase I (decided 2026-06-22): folded into I.a, implemented as Option A** (move `num_workers` out of `TrainingSpec` into `RuntimeConfig` + `--num-workers` CLI flag + `MODELFOUNDRY_NUM_WORKERS`). Rides the one-time Phase I invalidation; removes a tracked-but-output-neutral field from recipe identity. The Future bullet will be struck through and redirected to I.a.
5. **Tight-coupled DataRefinery binding (FR-26)** — unchanged; the upstream `recipe_hash` still must not enter cache identity ([identity.py:5](../src/modelfoundry/cache/identity.py#L5)).
6. **Cross-repo divergence from the horizontal standard** — out of scope by governance: the horizontal mechanism is the DR-coordinated family standard (spike §3 Governance); Phase I *adopts*, it does not redesign.
