# Spike I.a — Segmented recipe identity (`join_stable`, discriminated-union surface, segment boundaries, `num_workers`)

> **Type:** architectural spike (will this design work?).
> **Status:** complete. **Deliverable:** this document. The script
> `scripts/spike_segmented_identity.py` is throwaway evidence (16/16 claims pass),
> not production code.
> **Date:** 2026-06-22. **Feeds:** Stories I.b–I.h.
> **Sources:** [`phase-i-recipe-architecture-spike.md`](../specs/phase-i-recipe-architecture-spike.md) (the memo), [`phase-i-segmented-recipe-identity-plan.md`](../specs/phase-i-segmented-recipe-identity-plan.md) (the plan §4 / §9 open questions).

## Questions answered

The plan left five mechanics "genuinely unproven" (plan §4 / §9). This spike
settles each with a small proof so I.b–I.h implement against decisions, not guesses:

1. **`join_stable`** — exact byte format, empty-segment semantics, prefix-capability.
2. **Segment boundaries** — which `ModelRecipe` field lands in `core` / `plugin` / `overlays` / `extensions`.
3. **Discriminated-union plugin surface, flat on disk** — and how validator checks 3 + 17 adapt.
4. **No-implicit-defaults catalog** — which value-defaults to drop, which mode-selecting optionals to keep.
5. **Per-segment version scheme** + migration-registry seam.
6. **`num_workers` classification** (Option A) — the concrete signature changes.

---

## Decision 1 — `join_stable` byte format

```
frame(label, payload) := len(label):u32be ‖ label ‖ len(payload):u32be ‖ payload
join_stable(segments, upstream=None) :=
    SHA-256(
        [ frame(b"\x00upstream", upstream) ]                 # only if upstream given
        ‖ for label in sorted(present, non-empty segments):
              frame(label_utf8, SHA-256(segment_canonical_bytes))
    )
segment_canonical_bytes := json.dumps(sub_doc, sort_keys=True,
                                       separators=(",",":"), ensure_ascii=False).encode()
all-empty combination := SHA-256(b"\x00mf-empty-combination")
```

**Properties proved** (`scripts/spike_segmented_identity.py` Part 1):

| Property | Why it matters | Mechanism |
|---|---|---|
| Deterministic | identity must be stable | sorted labels + compact JSON (reuses today's `canonical.py` recipe-side rules) |
| Length-framed | no boundary-ambiguity collisions (`{"a":"bc"}` ≠ `{"ab":"c"}`) — principle 5 "no silent collisions" | `u32be` length prefixes on both label and payload |
| Label-keyed | a value moving *between* segments changes the hash | label is framed into the digest |
| **Sparse** (empty ⇒ nothing) | empty `extensions` for everyone is a no-op (I.d's "empty bag ⇒ byte-identical" test passes *by construction*) | empty/absent/`{}`/`[]`/`None` segments are omitted from the join, not sentinel-stuffed |
| **Prefix-capable** | the deferred vertical stage-waterfall layers on later without re-specifying the combiner | optional `upstream` 32-byte digest, framed first; `H(H_upstream ‖ segment)` composes |

**Empty-segment semantics — decision: sparse omission, not a per-segment sentinel.**
The plan's phrase "fixed empty-segment sentinel" is satisfied by a single
degenerate constant for the *all-empty* combination; individual empty segments
are simply omitted. This is what makes I.d's invariant ("adding the `extensions`
segment, empty, must not move the hash relative to the I.b/I.c state") hold
without special-casing — an omitted segment and an empty one are identical bytes.

> ⚠ **Cross-repo coordination checkpoint (governed shared contract, spike §3).**
> The horizontal combiner is the DataRefinery-coordinated family standard. The
> byte format above is ModelFoundry's proposal; **before I.b writes
> `recipe/canonical.py`, confirm it byte-for-byte against DataRefinery's
> `join_stable`** (frame field widths, label encoding, the upstream-frame label,
> the all-empty constant, sort collation). A divergence here is a cross-repo
> event, not an in-tree decision. DataRefinery's repo was not importable in this
> session, so this confirmation is an explicit I.b precondition.
>
> **Resolved at Story I.j.5 (v0.17.0 / DR v0.23.0):** DataRefinery has now
> implemented its `join_stable` and **the two byte formats diverge** — DR's
> `datarefinery.recipe.segments.join_stable` is `b"\x1f".join(digests)` (an
> unframed unit-separator join of the raw per-segment digests), whereas MF keeps
> the labeled, length-framed, label-sorted, prefix-capable form above. This does
> **not** functionally break MF: MF consumes the DR instance as an opaque hashed
> unit (reads DR's `manifest.recipe_hash`, XORs it into `data_instance_hash16`)
> and never recomputes DR's hash with MF's combiner. Both sides kept the combiner
> prefix-capable (DR exposes `prefix_hash`), so the divergence is load-bearing
> only if/when the deferred vertical / cross-tool hash-chain axis ships.
> **Aligning the formats is a cross-repo coordination event for the family — do
> not change MF's combiner unilaterally.**

---

## Decision 2 — Segment boundaries

Catalog of every `ModelRecipe` field ([models.py](../../src/modelfoundry/recipe/models.py)) → segment:

| Field | Segment | Rationale |
|---|---|---|
| `schema_version` → per-segment versions + umbrella | **core** | governs the combiner; see Decision 5 |
| `plugin` | **core** | the discriminator that selects the plugin surface; a change is correctly a whole-world event |
| `seed` | **core** | global; feeds weight-init via `prepare_for_build`; upstream of every stage in the vertical chain |
| `Data` (`DataSpec`) | **core** | the binding. The bound `data_instance_hash` enters the **cache key** (XOR), not the recipe bytes — unchanged ([identity.py](../../src/modelfoundry/cache/identity.py)); loose-coupling invariant preserved |
| `Architecture` | **plugin** | already an opaque plugin-interpreted dict bag (the precedent, spike §2) |
| `Loss`, `Optimizer` (+ `schedule`) | **plugin** | op + plugin-typed params |
| `Training` | **plugin** | trainer params — **minus `num_workers`** (Decision 6 moves it out of recipe identity entirely) |
| `Optimization` | **plugin** | `search_space` keys reference plugin param paths; the HPO surface is plugin-shaped. (`sampler`/`pruner`/`n_jobs` are pre-prod-locked invariants, not free defaults — Decision 4.) |
| `Inference` | **plugin** | MC-dropout is a torch/plugin concept (`Dropout` active, per-pass seeding) |
| `Evaluation` | **plugin** | metrics are plugin-produced; the core vocabulary in `validator.py` is a pre-prod stand-in for plugin-registered metrics (validator check 11 comment) |
| `Visualizations` | **plugin** | op-bearing, plugin-rendered |
| `OutputExpectations` | **plugin** | assertions over plugin-produced metric/split pairs |
| `variants` (selected, *resolved delta*) | **overlays** | model the selected variant's resolved delta as the segment so a variant edit scopes to `overlays`; `variants` semantics otherwise unchanged (plan §4 open-Q). First-class composable additive overlays remain deferred (out-of-scope 3) |
| `extensions:` (new) | **extensions** | sparse; enters identity only when non-empty (Decision 3 / I.d) |

**Key finding — what actually delivers cross-plugin isolation (F2).** Isolation
is *not* primarily the `core`/`plugin` split. It is the conjunction of:

1. **Sparse hashing** — a PyTorch recipe never authors sklearn fields, so they
   never enter its bytes; and
2. **No-implicit-defaults** — there are no code-injected defaults to shift when
   a *shared* spec gains a field (Decision 4).

Part 2 of the proof shows a PyTorch recipe's hash is **unmoved** when the sklearn
surface gains a field, while the sklearn recipe's hash correctly moves. The
discriminated unions (Decision 3) and the `plugin` segment grouping add
**schema/validation isolation** and **per-segment versioning scope** on top — they
are complementary to, not the source of, byte-level isolation. I.b/I.c should be
written with this ordering in mind: the no-implicit-defaults work (I.e) is
load-bearing for the isolation guarantee, not a cosmetic follow-on.

---

## Decision 3 — Discriminated-union plugin surface, flat on disk

**Decision: top-level `plugin` is the discriminator; the loader injects it; the
YAML stays flat (no per-section discriminator written).** Proof Part 3 validates
flat `Training` dicts into `PyTorchTraining` / `SklearnTraining` via a pydantic
`Field(discriminator=...)` union after injecting `kind = recipe.plugin`, and shows
a pytorch-only field (`precision`) is rejected on the sklearn variant.

**The load-bearing constraint the framing must respect: `recipe/models.py` stays
plugin-agnostic.** It cannot `import` plugins (they are discovered at runtime;
third parties add ops without editing core). So the literal "`PyTorchTraining`
class in models.py" reading of the plan is wrong — it would re-couple core to the
plugin set and kill runtime discovery. Two consequences:

- **Identity needs no plugin.** Because no-implicit-defaults guarantees every
  behavior-affecting value is written in the recipe text, the **plugin segment's
  canonical bytes are computed from the authored fields alone** — `canonical.py`
  does *not* need the plugin's `param_model`. Keep `canonical_bytes(recipe)`
  plugin-free.
- **Validation keeps using the plugin.** The "discriminated union" is realised at
  *validate* time from the discovered plugin's registered `OperationSpec`s, exactly
  as `validator.py` already does — lifted from per-op `model_extra` bags to typed
  variants. `models.py` keeps a *shape* (a section has an `op` + params); the
  concrete typing is resolved against `plugin.operations`.

**Validator checks 3 + 17 adaptation** (proof Part 3b):

- `_iter_ops` ([validator.py:712](../../src/modelfoundry/recipe/validator.py#L712)) changes from reading `recipe.Loss.op` + `model_extra` to yielding `(label, op, params)` where `params` is the typed variant dump minus structural keys (`kind`, `op`).
- **Check 3** (`section_ops_registered`) is unchanged in spirit: op-name ∈ `plugin.operations`.
- **Check 17** (`op_params_match_spec`) still validates params against `OperationSpec.param_model`; some of its work becomes redundant with the typed variant (pydantic validated the shape at load), but it stays as the comprehensive report entry. **Never-short-circuit behavior preserved** — both checks accumulate over all ops.

---

## Decision 4 — No-implicit-defaults catalog

**Drop** (code-supplied value-defaults → the scaffolder emits them explicitly;
[init.py](../../src/modelfoundry/scaffolder/init.py) already emits most):

| Field | Today | After |
|---|---|---|
| `Training.num_workers=2` | hashed for every recipe | **removed from recipe entirely** (Decision 6) |
| `Training.precision="fp32"` | default hashed | scaffolder emits `fp32` |
| `Training.checkpoint_cadence=1` | default hashed | scaffolder emits `1` |
| `Training.device="auto"` | default hashed (scaffolder already emits it) | emit (no change to template) |
| `Evaluation.calibration_bins=10` | default hashed | scaffolder emits `10` |
| `Optimization.sampler="tpe"` / `pruner="median"` | defaults hashed | emit explicitly (when the `Optimization` block is present) |
| `Optimization.baseline_trial="enqueue_recipe_defaults"` | default hashed | emit explicitly; the absent⇒enqueue mapping is removed |
| `Visualization.mode="reporting"` | default hashed | emit explicitly per viz |
| `Inference.mode="point"` | default hashed *when block present* | emit explicitly when the block is present |

**Keep** (mode-selecting optionals — absence is meaningful; the "absent ⇒
behavior" mapping moves into the versioned segment contract, Decision 5):

- `Inference = None ⇒ point mode` (the whole block)
- `Inference.mc_samples = None` (valid only under `mc_dropout`)
- `Training.early_stopping = None ⇒ no early stopping`
- `Optimization = None ⇒ no HPO`
- `Optimizer.schedule = None ⇒ constant LR`
- `ScheduleSpec.monitor`, `Optimization.objective_metric`, `Optimization.max_epochs_per_trial` = `None`
- `Evaluation.comparison = None ⇒ no baseline comparison`
- `Data.variant` / `Data.seed` / `Data.cache_root = None ⇒ execution-context resolution`
- Empty collections `Visualizations=[]`, `OutputExpectations=[]`, `variants={}` — naturally sparse (omitted from the join)

**Invariant-not-default** (a distinct third category, do not "emit" these as if
author-chosen): `Optimization.n_jobs = Literal[1]` is a pre-prod determinism lock
(QR-3 / FR-2 check 10), not a default. Keep it as a constrained constant; it
contributes to bytes only when the `Optimization` block is present, and the
validator continues to assert it.

Proof Part 4 demonstrates the payoff: omitting an optional yields identical bytes
(sparse), and the *code-injected* default — the thing we are removing — is exactly
what `WOULD` invalidate every omitting recipe today. This is the dissolution of
the project-essentials "default-shift nightmare" and the H-1 cache flag.

---

## Decision 5 — Per-segment version scheme

- Replace the single `SUPPORTED_SCHEMA_VERSIONS = frozenset({1})` ([loader.py:26](../../src/modelfoundry/recipe/loader.py#L26)) with **per-segment versions** (`core`, `plugin:<name>`, `overlays`, `extensions`) **+ a thin top-level umbrella** that versions only the *combination function* (`join_stable` shape). The one-time Phase I rearchitecture is itself an umbrella-version event.
- **Migration-registry seam** keyed by `(segment, from, to)` — a dict of callables, **empty pre-1.0** (zero support window, OR-9). The seam lands; no migrations are written this phase.
- The "absent ⇒ behavior" mappings kept in Decision 4 become **part of the versioned segment contract**: a change to what an absent optional means is a segment-version bump, because it changes interpretation without changing bytes.
- Loader flow: gate the umbrella version first (refuse unknown combiner), then per-segment versions, then route through any registered `(segment, from, to)` migration (none, pre-1.0).

---

## Decision 6 — `num_workers` classification (Option A, decided 2026-06-22)

`num_workers` is **output-neutral by contract** — the E.e `worker_init_fn`
guarantee makes trained bytes independent of worker count (`test_determinism.py`
asserts identity across `num_workers ∈ {1,2,4}`). It is therefore execution
context, not recipe semantics, and should not sit in recipe identity. Move it:

1. **Remove** `num_workers` from `TrainingSpec` ([models.py:70](../../src/modelfoundry/recipe/models.py#L70)). (It leaves recipe identity — rides the one-time Phase I invalidation.)
2. **Add** `num_workers: int = Field(ge=0, default=0)` to `RuntimeConfig` ([config.py:25](../../src/modelfoundry/core/config.py#L25)); wire `MODELFOUNDRY_NUM_WORKERS` into `RuntimeConfig.from_env`. *(Default value to confirm at I.e; `0` is the deterministic-by-default, no-subprocess choice — propose `0`, was `2`.)*
3. **Add** `--num-workers` CLI flag (precedence: CLI > env > default, matching the existing `RuntimeConfig` rungs).
4. **Thread it to the DataLoader, off `TrainingSpec`:** the `Plugin` Protocol's `run_training` / `run_optimization` ([base.py:129-150](../../src/modelfoundry/plugins/base.py#L129)) gain a `num_workers: int` parameter; the runner passes `self.config.num_workers` ([runner.py:110,129](../../src/modelfoundry/pipeline/runner.py#L110)). `build_dataloader` ([data.py:223](../../src/modelfoundry/plugins/pytorch/data.py#L223)) takes `num_workers` as an argument instead of reading `training_spec.num_workers`.

This is a `Plugin` Protocol signature change touching every plugin
(`pytorch`/`sklearn`/`random`) — a deliberate part of the I.e bundle, not a
drive-by. The E.e output-neutrality guard stays green by construction (it already
varies `num_workers` and compares only output).

---

## Verdict

**The design works; proceed with I.b–I.h as planned.** All 16 spike claims pass.
No blocking surprises. Three findings sharpen the downstream stories:

1. **No-implicit-defaults (I.e) is the load-bearing isolation mechanism**, not a
   cosmetic follow-on — sequence it as a first-class part of the bundle, and note
   in I.b/I.c that byte-level cross-plugin isolation depends on it.
2. **Keep `canonical_bytes(recipe)` plugin-free** — identity hashes authored
   fields; the plugin is needed only for *validation*. This preserves the
   plugin-agnostic `recipe/models.py` and avoids re-coupling core to plugins
   (the one design trap that would break runtime plugin discovery).
3. **The `join_stable` byte format is a cross-repo coordination checkpoint** —
   confirm byte-for-byte against DataRefinery before I.b implements (DataRefinery
   was not importable this session).

**Story touch-ups recommended** (for the developer / a future `plan_phase`, not
applied here): I.b should carry the explicit "confirm `join_stable` vs
DataRefinery" precondition; I.c should note the plugin-agnostic-models constraint
and the identity-is-plugin-free split; I.e should record the `num_workers`
default change (`2 → 0`) as an intentional behavior change to mention in the
release notes alongside the cache invalidation.

## How to re-run

```bash
pyve run python scripts/spike_segmented_identity.py
```

Writes nothing to disk; prints a findings summary; exits 0 when all claims hold.
