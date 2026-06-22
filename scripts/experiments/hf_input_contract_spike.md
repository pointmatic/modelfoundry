# Story H.j.2 — DR↔MF input-shape/preprocessing contract: spike findings

**Type:** throwaway investigation spike (design the contract for H.j.3 to implement).
**Deliverable:** the decisions below + the validator design. No shipped `src/` change.
**Reproducer:** [hf_input_contract_spike.py](hf_input_contract_spike.py) (run in `smoke-huggingface`).

## Verdict: implementable as ONE validator check with a TWO-PART, split-by-extra body

The contract decomposes into two comparisons with *different* dependencies, which is what resolves
the R1.4 tension cleanly:

| Part | Source of "required" | Needs `[huggingface]`? | When it runs |
|---|---|---|---|
| **Input shape** (HWC vs encoder native) | encoder-introspected (`AutoConfig`) | **yes** | validate, *conditional* on the extra being importable |
| **Normalization scale** (H.a class) | the adapter's 0-255 decode contract | **no** | validate, **always** |

Both are concretely demonstrated by the reproducer: the shape check flags a CIFAR-32 instance against
the ViT-224 encoder with an actionable message and passes the native-224 H.j.1 fixture; the encoder
requirement is read offline, config-only (no weights), in ~1.6 s.

## Decisions (answering the spike questions)

### Q1 — Where the *produced* input spec comes from (transformers-free)

- **Shape:** `data_instance.record_schema["image"]["shape"]` → `[H, W, C]` (DataRefinery's HWC
  convention). Already on the `DataRefineryInstance` wrapper; this is the same field
  `summary.derive_input_size` reads. No manifest enrichment needed.
- **Normalization:** `data_instance.fitted_statistics`, read via the adapter's **existing**
  `DataRefineryDataset._resolve_normalization_steps` / `_read_vector(op.name, "mean"|"std")`
  ([data.py](../../src/modelfoundry/plugins/pytorch/data.py)). H.j.3 must **reuse that accessor**, not
  a guessed one — the spike reproducer's best-effort `_first_mean` returned `None` on the synthetic
  fixture precisely because the `FittedStatistics` view structure differs from the guess; the real
  path reads `recipe.Transformations` → the `normalize` op → the fitted mean/std vectors.

### Q2 — Where the architecture's *requirement* lives: **encoder-introspected, no new recipe field**

`AutoConfig.from_pretrained(Encoder.id, local_files_only=True)` exposes `image_size`, `num_channels`,
`patch_size` offline and config-only (no weights). The requirement is therefore **derived from the
existing `Encoder.id`** — no new recipe field, so **cache identity is unchanged** (recipe-as-truth: the
id already pins the requirement). Rejected alternatives: a recipe-declared `input_size` (redundant with
the encoder, author-error-prone, and a cache-identity-perturbing field); a static lookup table
(brittle, doesn't scale). For a ViT the contract is **exact match** (`H == W == image_size`,
`C == num_channels`) because the position-embedding table is fixed to `(image_size/patch_size)²+1`
tokens; resolution-interpolation is a documented future flag, not v1.

### Q3 — R1.4 tension resolved by the split

`validate()` must succeed **without** the extra (R1.4). The split makes that automatic:
- the **normalization** check is transformers-free → always runs, even on a torch-less/transformers-less
  install;
- the **shape** check needs `AutoConfig` → run it **only when `transformers` is importable** (guard with
  `importlib.util.find_spec`). When the extra is absent, the shape comparison is skipped and validate
  still passes structurally (R1.4 preserved) — and any attempt to *materialize* the encoder path
  already fails with the H.j.1 extras-error, so nothing slips through silently.

### Q4 — Generalization to the H.a class: confirmed

The normalization-scale check reads the **same** fitted stats the adapter consumes and flags a
units mismatch against the adapter's 0-255 decode contract (e.g. a `[0,1]`-scale mean applied in
0-255 space — the exact H.a signature). It is encoder-independent and transformers-free, so it closes
the H.c-filed "validate-time normalization sanity check" follow-up for **every** recipe, not just the
encoder path.

## Validator design for H.j.3

- **Add one check (check 21, `architecture_input_compat`)**, sibling to
  `_check_18_data_binding_compat` ([validator.py](../../src/modelfoundry/recipe/validator.py)) — same
  shape: accumulate `issues: list[str]`, return `_ok`/`_fail(21, ...)`. It receives `(recipe,
  data_instance)`, which is all it needs.
- **Body:** (a) if the Architecture declares an `Encoder` op *and* `transformers` is importable,
  compare the DR `record_schema` HWC to the `AutoConfig` requirement; (b) always, compare the fitted
  normalize stats' scale to the adapter's 0-255 decode contract (via the reused `_read_vector` path).
- **Keep the validator import-safe:** guard the `AutoConfig` import (`find_spec("transformers")`) so
  the default `testenv` (no torch, no transformers) still imports and runs the validator — the
  normalization half runs there; the shape half no-ops.

## Finding — materialize does not gate on validate (carried from H.f.1)

`materialize()` does **not** run `validate()` (the H.f.1 finding). So the validator check protects the
**documented `validate → materialize` workflow**, which is the primary win (and where the H.a-class
generalization pays off). For a user who skips `validate` and materializes a shape-mismatched instance,
the ViT errors during the forward pass — not silent-wrong, but not the clean early message either.
**Recommendation for H.j.3:** ship the validator check as the core; optionally add a *cheap* runner-side
pre-build assertion (the extra is guaranteed present at materialize, so the same `AutoConfig` shape
check is ~free) as a backstop. Do **not** change the broader "materialize gates on validate" policy
inside H.j.3 — that affects all 20 checks and is a separate decision.

## Out of scope (H.j.3 and beyond)

- Resolution-interpolation (feeding a non-native size to an encoder that supports pos-embedding
  interpolation) — a future `Encoder` flag, not v1's exact-match contract.
- Text/audio encoder input contracts (sequence length, tokenizer/vocab) — R1 is image; other
  modalities reuse the same split-by-extra pattern when they land.
- DataRefinery-side manifest enrichment — not needed; `record_schema` + `fitted_statistics` already
  carry everything (the upstream-coordination note in the H.j parent stands, but the MF side is
  self-sufficient here).
