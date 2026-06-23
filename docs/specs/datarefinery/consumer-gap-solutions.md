# Consumer Gap Solutions — investigation conclusions

Investigation of the three gaps logged in
[`consumer-gap-analysis.md`](consumer-gap-analysis.md), each reproduced against the
current `main` source and concluded **confirmed** / **refuted** / **pending**. Each
confirmed gap carries either a concrete solution or a story/spike plan. This document
is an analysis artifact; it does **not** modify `stories.md` (structural story/phase
authority belongs to the code / `plan_phase` modes — see the recommendations per gap).

Investigated 2026-06-22 against Python 3.12.13, `requires-python = ">=3.12,<3.13"`.

## Verdict summary

| # | Gap | Verdict | Disposition |
|---|-----|---------|-------------|
| 1 | `image_folder` one-level only — fails on multi-level (taxonomy) trees | **confirmed** (one supporting detail corrected) | **Architectural spike first** — path-template layout + shared cross-plugin resolver; then implement (Phase K or own subphase) |
| 2 | Input-hash blind to symlinked-dir content — silent stale cache | **confirmed** (reproduced empirically) | Bugfix story → Phase K (`_iter_files` must follow symlinks; patch) |
| 3 | Audio float features cannot be persisted (only uint8 PNG sink ships) | **confirmed** (stronger than reported) | Architectural/integration spike + `plan_phase` (cross-repo, distinct theme) |

All three are genuine — none has an already-built solution in the tree. The Future
section of `stories.md` contains no entry for any of them.

---

## Gap 1 — `image_folder` fails on multi-level (taxonomy) trees

**Verdict: confirmed.** The one-level ImageFolder contract is reproduced in code, and
the validate/materialize asymmetry is real. One supporting claim in the analysis is
inaccurate and is corrected below.

### Evidence

In [`pipeline/inputs.py`](../../src/datarefinery/pipeline/inputs.py),
`_load_one_image_folder` enumerates classes as the **immediate** subdirectories of the
source root and globs image files **directly** (non-recursively) within each:

- [inputs.py:147](../../src/datarefinery/pipeline/inputs.py#L147) — `classes = sorted(p.name for p in root.iterdir() if p.is_dir())`
- [inputs.py:156-157](../../src/datarefinery/pipeline/inputs.py#L156-L157) — `for ext in _IMAGE_EXTENSIONS: for path in sorted(cls_dir.glob(f"*{ext}")):` (single-level `glob`, not `rglob`)
- [inputs.py:175-179](../../src/datarefinery/pipeline/inputs.py#L175-L179) — raises `"contains no .png/.jpg/.jpeg files"` when no images are found one level down

For a `category/class/image` tree, `classes` resolves to the **category** dirs, none of
which directly contain images, so `out` stays empty and the loader raises the exact
error quoted in the analysis. Confirmed.

**Validate/materialize asymmetry — confirmed.** Every validator check in
[`recipe/validator.py`](../../src/datarefinery/recipe/validator.py) has the signature
`check_NN_*(recipe: Recipe, plugin: Plugin)` — purely static, no filesystem access. So
no static check can observe directory nesting depth, and a misjudged layout passes all
29 checks then fails at `materialize`. Confirmed.

### Correction to the analysis

The analysis states `image_flat` is *"likewise non-recursive."* **This is inaccurate.**
`_enumerate_flat_images` uses `root.rglob("*")`
([inputs.py:191](../../src/datarefinery/pipeline/inputs.py#L191)) and **is** recursive
in file discovery. The reason `image_flat` does not solve the taxonomy case is
different: `image_flat` derives labels from a sidecar manifest (`label_from`, by-id or
by-row-order), **not** from the parent directory — so it cannot produce
`parent_directory_name` labels for a `category/class/image` tree. The gap's *conclusion*
(image_flat is not a workaround) holds; the *stated reason* (non-recursive) does not.

### Solution / plan

The naive fix is an opt-in `recursive: true` flag on `image_folder` (analysis option
1). That closes the reported symptom but bakes in a **brittle flavor-zoo**: real
datasets ship as `class/image`, `category/class/image`, *and* `split/category/class/image`
(a second form of the same example dataset), so an enumerated-flavor approach keeps
growing special cases — and the same special-casing is **already duplicated per
modality** (`audio_folder` / `audio_flat` in
[`plugins/audio_classification/inputs.py`](../../src/datarefinery/plugins/audio_classification/inputs.py)
reimplement the identical one-level contract; `AudioSource` subclasses `InputSource`
verbatim). So the better design generalizes along two axes.

**(A) Arbitrary path→role mapping instead of fixed flavors.** Replace the enumerated
source types with a **named-component path template**, mirroring the existing sink
path-template grammar ([`pipeline/sinks/template.py`](../../src/datarefinery/pipeline/sinks/template.py):
`{field}`, `{field|stem}`, `{split}`) for recipe-surface consistency:

```yaml
Input:
  sources:
    - name: logos
      type: image_tree
      path: datasets/logos
      layout: "{split}/*/{label}/{file}"   # split/category/class/image
```

Roles + wildcards express arbitrary nesting directly, so all flavors collapse to
templates:

| Layout template | Captures |
|-----------------|----------|
| `{label}/{file}` | today's strict `image_folder` (one level) |
| `**/{label}/{file}` | "label is the leaf dir at any depth" (covers `class/image` **and** `category/class/image`) |
| `{split}/*/{label}/{file}` | the new `split/category/class/image` form, in a single source |

- `{label}` subsumes `Labels.source.derivation: parent_directory_name` (label = whichever
  component is tagged, not hardcoded to the immediate parent).
- `{split}` folds partitioning **into the tree** — a strict superset of the current
  per-source `InputSource.partition` declaration. Reconcile the two: make `{split}` and
  `partition` mutually exclusive (template wins when present), keeping `partition` for
  the still-valid "separate roots per split" case.
- `*` = exactly one ignored ("category") level; `**` = any depth ignored.
- Bare `image_folder` stays as sugar for `{label}/{file}` — fully backward-compatible.

**(B) Factor the directory resolver across modalities — but NOT the record field name.**
Two distinct moves hide under "generalize to sample/observation":

- *The directory resolver* (which path components mean what; where files live) is
  modality-independent — **factor it out now.** A shared `path_tree` resolver takes the
  `layout` template + the plugin's file-extension set + the plugin's decode hook; the
  image and audio loaders both call it. This eliminates the per-plugin duplication and is
  the real payoff. Keep modality-prefixed type names at the recipe surface (`image_tree`,
  `audio_tree`) delegating to the shared resolver — clarity on top, DRY underneath.
- *The record field name* (`image` → `sample`/`observation`) is a **shape-binding
  contract surface** (the per-record JSONL field set binds ModelFoundry — see
  `project-essentials.md` § "Recipe / manifest / report shape changes"). Renaming `image`
  needs the full rename ceremony (schema bump + migration + `vendor-dependency-spec.md` +
  deprecation horizon). And it is **not required** by this work: each plugin already names
  its own payload (`image`, `sample_array`); only the *resolver* generalizes, and it deals
  in `path` + `record_id`, not the decoded field. **Defer the rename**; if ever done,
  prefer **"observation"** over **"sample"** ("sample" is overloaded — a PCM sample in
  audio, the whole dataset in statistics).

**(C) Additive validate check** (analysis option 3, still wanted): flag a source whose
layout cannot be satisfied by the tree (e.g. a `{label}` level that contains only further
subdirectories, no files) — failing fast at the cheap static gate with a message naming
the nesting, instead of deferring to `materialize`.

**Contract constraints to preserve:** the input hash must digest the **resolved** file
set so the same tree + seed still materializes byte-identically; traversal stays
deterministically sorted; no change to `Labels` / `Splits` / `Transformations` semantics
beyond `{label}`/`{split}` sourcing. New `layout` text adds to canonical recipe bytes
(a `core`/`plugin`-segment surface — pre-prod invalidation acceptable per
`project-essentials.md`).

**Coupling note:** the resolver and the Gap 2 hash fix must walk the **same** set — land
them together so loader and hasher never diverge again.

### Disposition — reclassified

This is **no longer a tidy Phase K feature story**: a path-template grammar + a shared
cross-plugin resolver + the `partition`/`{split}` reconciliation + the field-rename
decision is an architectural change to the plugin loader contract. Recommended path:

1. **Architectural spike first** to settle (a) the `layout` template grammar and its
   static validation (exactly one `{label}` for labeled sources; depth check), (b) the
   shared-resolver interface and how the image/audio plugins call it, (c) `{split}` vs
   `partition` precedence, (d) explicit deferral of the field rename (note "observation").
   Deliverable = the decided grammar + resolver boundary, not production code.
2. **Then implement** under Phase K if it stays bounded, or its own subphase if the
   resolver refactor grows — landed together with the Gap 2 symlink fix (shared
   enumeration). Phase/subphase creation is `plan_phase`'s authority, not `debug` mode's.

---

## Gap 2 — input-hash blind to symlinked-directory content

**Verdict: confirmed.** Reproduced empirically on Python 3.12.13; this is a genuine
reproducibility-contract bug (silent stale-cache / wrong-data) and the strongest
test-first debug candidate of the three.

### Evidence

The hasher and the loader walk **different** file sets through a directory symlink:

- Hasher: `_iter_files` uses `root.rglob("*")`
  ([inputs.py:382-383](../../src/datarefinery/pipeline/inputs.py#L382-L383)). On Python
  3.12 the `**` recursion **does not descend into symlinked directories** (the
  `recurse_symlinks` parameter is 3.13+, so 3.12 never follows). A symlink-to-dir is
  itself not a file (`is_file()` is `False`), so it is filtered out → an effectively
  **empty file set** → the **same** digest regardless of what the symlinks point at.
- Loader: `_load_one_image_folder` uses `iterdir()` + `is_dir()` (follows the symlink
  one level) then `cls_dir.glob("*.png")` (globs the symlinked dir's immediate children,
  which resolves fine) — so it **does** read the real images.

Empirical reproduction (temp tree, `view/brand_x -> real/brand_x` with two PNGs):

```
HASHER _iter_files sees files: []
LOADER  sees classes: ['brand_x'] images: ['1.png', '2.png']
```

The loader loads correctly on a cache miss; the hash is content-blind, so every
subsequent run is a stale **hit**. Two different symlink views collide on one hash.
Confirmed exactly as described.

### Solution / plan

A **bugfix story under Phase K** (patch bump per Version Cadence). Test-first:

1. Failing test — the reproduction above asserted as "two views with different symlink
   targets must yield different `_hash_image_folder` digests," plus a loader-vs-hasher
   file-set-parity assertion.
2. Fix `_iter_files` to follow symlinked directories with **cycle protection** (track
   visited resolved real-paths to avoid symlink loops). Because `recurse_symlinks=True`
   is unavailable on 3.12, implement an explicit walk (e.g. `os.walk(..., followlinks=True)`
   over the resolved root, or a manual stack that `resolve()`s each dir and dedupes
   visited real paths). Keep traversal deterministically sorted.
3. Keep the loader and hasher walking the **same** file set — the load/hash asymmetry is
   the root cause, so a shared enumeration helper is the durable fix.

**Prevention scan:** `_hash_image_flat` reuses `_hash_image_folder`
([inputs.py:355-356](../../src/datarefinery/pipeline/inputs.py#L355-L356)), so it
inherits the same blindness for symlinked `image_flat` roots and is fixed for free by
the `_iter_files` change. The audio plugin's hashing
(`plugins/audio_classification/inputs.py`) should be checked for the same `rglob`
pattern as a `[ ]` housekeeping item.

**Note:** this is *largely* obviated once Gap 1's native recursive ingestion lands
(symlink views disappear), but content-hashing must follow symlinks regardless — a
correct hash is independent of whether the workaround is still needed.

---

## Gap 3 — audio float features cannot be persisted

**Verdict: confirmed** — and the barrier is slightly stronger than the analysis states.

### Evidence

Three layers each block float-array persistence:

1. **JSONL serialization drops arrays.** The dataset writer coerces each record through
   `_coerce`, which returns the skip sentinel for numpy arrays — *"numpy arrays, bytes,
   custom objects: drop from persisted form"*
   ([runner.py `_coerce`](../../src/datarefinery/pipeline/runner.py)). So `sample_array`
   / `mel` / `feature` never reach `dataset/<split>.jsonl`; only JSON-native metadata
   survives. Confirmed.
2. **Only one sink format exists, and the model forbids declaring another.** The recipe
   model pins `format: Literal["png_per_record"]`
   ([models.py:502](../../src/datarefinery/recipe/models.py#L502)). Declaring
   `npy_per_record` is rejected by pydantic *before* materialize — stronger than the
   analysis (which shows the runtime float-dtype error). The sink runner's non-PNG
   branch is dead code guarded by that Literal
   ([sinks/runner.py:121-129](../../src/datarefinery/pipeline/sinks/runner.py#L121-L129)).
3. **The one writer is uint8-only.** `write_png_per_record` raises `MaterializeError` on
   any non-uint8 dtype
   ([sinks/writers.py:45-50](../../src/datarefinery/pipeline/sinks/writers.py#L45-L50)) —
   the exact message quoted in the analysis.

So the plugin faithfully *computes* windowed log-mel features but there is **no
serialization path for a float feature array**. Confirmed; no workaround exists on the
consumer side (the windowed `sample_array` is also in-pipeline-only, so re-featurizing
from the instance is impossible).

The full brief is now in-repo at
[`datarefinery-audio-feature-persistence.md`](datarefinery-audio-feature-persistence.md);
it ties the gap to the audio requirements R4 (spectral featurization), R5 (fit-on-train
normalization), and R7 (clip↔window aggregation via `source_record_id`), and confirms my
reading: `png_per_record` is the only writer, `npy_per_record` / `parquet` are deferred,
arrays are in-pipeline-only.

The requirements doc the brief links (`audio-classification-requirements.md`) is **not
missing** — it was moved and renamed to
[`.archive/phase-j-audio-classification-requirements.md`](.archive/phase-j-audio-classification-requirements.md)
when Phase J was archived, so the brief's link is merely stale. The companion
[`modelfoundry-audio-feature-consumption.md`](modelfoundry-audio-feature-consumption.md)
(the consuming half of the seam) is **also in-repo now**; it targets the *ModelFoundry*
repo (its fix lives there) but usefully pins one producing-side constraint: the consumer
resolves a `feature_path` (instance-root-relative, `<instance>/<feature_path>`) into a
`(1, n_mels, n_frames)` model-input tensor (always 2-D `(n_mels, n_frames)` `float32` on
disk in v1) and applies the persisted per-mel-bin `audio_normalize` fit-on-train stats.
Its fix is required for an end-to-end unblock; this doc covers DataRefinery's producing
half only.

**Root cause worth noting:** that archived requirements spec specifies R4 (compute the
spectral feature) and R5 (fit-on-train normalize) on the data side, but its "Contract
impact → Cross-repo contract (unaffected)" line scopes *feature consumption* entirely to
the modeling repo and asserts the DR↔MF surface is untouched. Feature **persistence on
the DR side** — the bridge between "computed" (R4) and "consumed" (modeling repo) — was
never specified by any R-requirement, so it fell through the seam. Gap 3 is precisely
that unspecified bridge, which is why no writer for it exists.

### Solution / plan

This is a **feature bundle plus a cross-repo contract change**, not a Phase K
ingestion/bugfix item, and it cannot be created in `debug` mode. Recommended path:

- **Architectural / integration spike first.** The brief lays out three behavior-level
  options; the spike chooses among them and settles the paired ModelFoundry contract:
  1. **`npy_per_record` (brief's preferred).** Persist the **raw `mel`** field (the
     pre-normalize `log_mel_spectrogram` output, `float32`) per record (e.g.
     `features/<split>/<record_id>.npy`) and rewrite a per-record `feature_path`
     (**instance-root-relative**, resolved `<instance>/<feature_path>` — the J.g
     sink-`path` bucket, *not* `image_path`'s `dataset/`-relative anchor), mirroring how
     `png_per_record` persists pixels + rewrites the JSONL `path`. The consumer applies
     the persisted per-mel-bin `audio_normalize` stats at load — so persist `mel`, **not**
     the already-normalized `feature`, or the consumer double-normalizes. Smallest change —
     reuses the sink mechanism + stage model, keeps the "arrays are in-pipeline; persist
     via sidecar" convention intact. *(Both pins — `mel` not `feature`, instance-root
     anchor — were ratified in the 2026-06-23 MF review round; see
     [`modelfoundry/vendor-dependency-spec.md`](modelfoundry/vendor-dependency-spec.md)
     § "Audio feature-array persistence", Q1/Q2.)*
  2. **Inline npy-bytes / base64 in the JSONL** — simplest to wire but bloats the JSONL
     and breaks the in-pipeline-array convention. Not preferred.
  3. **A uint8-quantization sink mode** (spectrogram → image through the existing PNG
     path) — lossy (quantization + range clipping). **ModelFoundry has rejected this
     route** (see cross-repo section below): the consumer documented five reasons it is
     lossy and contract-breaking (high-dynamic-range float32 → 256 levels; wrong
     normalization/channel semantics; not round-trippable, breaking the reproducibility
     contract). Keep it only as a documented-and-rejected alternative; **do not build it.**
     The spike should commit to option 1.

  The new per-record `feature_path` field is a **shape-binding surface** (per
  `project-essentials.md` § "Recipe / manifest / report shape changes need a cross-repo
  coordination check"): `modelfoundry/vendor-dependency-spec.md` must be updated in the
  same change, and the rollout coordinated with the companion
  `modelfoundry-audio-feature-consumption.md` fix (neither half unblocks the consumer
  alone). The brief notes the change is **additive ⇒ no `schema_version` bump**, but sink
  output is instance content, so cache identity must cover it exactly as `png_per_record`
  does today (same recipe + inputs + seed ⇒ byte-identical features; a changed
  featurization param ⇒ cache miss). Determinism and the `source_record_id` (R7)
  clip↔window grouping are unaffected.

  **Spike deliverables** (documented outcomes, not production code):
  1. The chosen serialization format (1/2/3 above), with the rejected options and why.
  2. The `feature_path` record-field contract sketch + the `modelfoundry/vendor-dependency-spec.md`
     update naming it as a shape-binding surface, coordinated with the companion
     `modelfoundry-audio-feature-consumption.md` fix. **Pin the persisted array shape /
     orientation** the consumer expects — `(n_mels, n_frames)` on disk, loaded as a
     `(1, n_mels, n_frames)` / `(C, n_mels, n_frames)` tensor — so producer and consumer
     agree; mismatched axis order is the obvious way a "paired" fix still fails to line up.
  3. **A new feature-persistence requirement that closes the seam at the requirements
     layer** — the missing "R-level" rule that the data side MUST be able to *persist*
     R4/R5 features for downstream consumption. The archived audio requirements spec
     covers compute (R4) + normalize (R5) but scoped *consumption* to the modeling repo
     and declared the cross-repo surface "unaffected," leaving persistence unspecified.
     Restate this requirement in DataRefinery's live document chain (not the archived
     Phase J doc) so the seam cannot silently re-open the next time a modality computes a
     non-uint8 feature; refresh the brief's stale link to the renamed archive copy at the
     same time.
- **Then a new phase/subphase via `plan_phase`** to deliver the chosen sink writer
  (`format` Literal extension, the writer, `feature_path` rewrite, manifest wiring) and
  coordinate rollout with the ModelFoundry consumption fix (paired). It is architecturally
  distinct from Phase K's data-ingestion theme — egress/persistence, not ingestion — and
  crosses repos, so it warrants its own phase rather than an append.
  - **Double-normalize guardrail (validator check, from the 2026-06-23 MF review).** The
    contract blesses `field: mel` (pre-normalize) for the consumer-applied path, but an
    author *could* point a `feature_path`-rewriting `npy_per_record` sink at the
    already-normalized `feature` field — the consumer would then re-apply `audio_normalize`
    and silently double-normalize. The `plan_phase` story should add a validator check that
    a `feature_path`-rewriting `npy_per_record` sink targets the pre-normalize field
    (`mel`), failing fast at `validate`. This is the egress analogue of check 26
    (pixel-altering transform ⇒ qualifying sink). MF mirrors the guard at load (verify the
    rewriting sink's `field == mel` before applying stats). No contract change now — both
    sides carry it into their execution stories (DR `plan_phase`, MF `plan_features`).

---

## Cross-repo coordination with ModelFoundry

ModelFoundry's own conclusions are recorded in
[`modelfoundry/consumer-gap-solutions.md`](modelfoundry/consumer-gap-solutions.md)
(reviewed 2026-06-22). Three points bind the DataRefinery side:

**1. Gap 3 — the seam is aligned; commit to `npy_per_record`, drop the PNG hack.** MF
independently confirms the shared contract this doc proposes — `npy_per_record` at
`features/<split>/<record_id>.npy`, `(n_mels, n_frames)` `float32` on disk → `(1|C, n_mels, n_frames)`
tensor, `feature_path` **instance-root-relative** (`<instance>/<feature_path>`), persisting
the raw `mel` so the consumer applies per-mel-bin `audio_normalize` stats at load — with
the axis orientation pinned identically on both sides (ratified in the 2026-06-23 MF review
round, vendor-dependency-spec Q1/Q2). Critically, **MF rejects the
spectrogram-as-image PNG route (my option 3)** as lossy and contract-breaking (five
documented reasons: HDR float32 → 256 levels; wrong per-mel normalization shape; fake
3-channel RGB vs. true 1-channel; non-round-trippable → breaks the reproducibility
contract; pure divergence, not reuse). The joint spike should therefore **settle on option
1 and not build option 3.** MF also notes it consumes the sink output **read-only** (the
loose-coupling invariants in `project-essentials.md` hold — MF never re-hashes the
instance), so cache identity for the features stays DataRefinery's responsibility.

**2. MF's Gap 2 hinges on a DataRefinery question — and the answer is YES (refutes their
`pending`).** MF's encoder-preprocessing gap is blocked on whether DR's `normalize` can
persist **fixed, author-supplied** mean/std (so a frozen pretrained encoder gets exact
ImageNet stats), which they could not answer from their repo. **It can.**
`NormalizeOp.fit`
([operations/transformations.py](../../src/datarefinery/plugins/image_classification/operations/transformations.py))
honors pinned stats: *"If the recipe pinned mean/std, honor it as the fit output"* — when
both `mean` and `std` params are present they are used as-is and persisted to
`fitted_statistics/`; absent ⇒ fit from train (`mean`/`std` are `required=False`
mode-selecting optionals, [plugin.py:212-218](../../src/datarefinery/plugins/image_classification/plugin.py#L212)).
So an author writes the encoder's exact `mean: [...]` / `std: [...]` into a `normalize`
op and DR applies them across all splits — **MF's cheapest option (1) works today with
zero DataRefinery code change.** This is the highest-leverage cross-repo answer to relay
back; it likely closes MF's Gap 2 without a spike.

**3. `vendor-dependency-spec.md` status discrepancy — reconcile.** MF's doc says the spec
is "forward-declared (authored at the pre-production release)," but
[`modelfoundry/vendor-dependency-spec.md`](modelfoundry/vendor-dependency-spec.md) **is
present and substantial in this repo** (~68 KB). The two repos may be looking at different
copies of the same family doc; settle which is authoritative before the Gap 3 work updates
it with the `feature_path` surface, so the update lands in the right place. (Related: MF
flags a directory-convention question — these seam docs live at `docs/specs/` here but the
copied briefs cross-link to a `docs/specs/modelfoundry/` layout. A doc-layout decision for
the developer, not a code fix.)

---

## Recommended next actions (developer's call)

1. **Gap 2 → Phase K now.** Append a `_iter_files`-symlink bugfix story under the
   existing `## Phase K` heading (test-first; patch). This is a normal debug bugfix — no
   new phase needed.
2. **Gap 1 → architectural spike, then implement.** The generalized path-template +
   shared-resolver design (above) is bigger than a single story: spike the grammar and
   resolver boundary first, then implement under Phase K (if bounded) or a new subphase,
   landed together with the Gap 2 fix so loader and hasher share one enumeration. The
   field rename (`image` → `observation`) is a separate, deferred contract event.
   (I did not append any of these to `stories.md`: structural story/phase edits are the
   code/`plan_phase` modes' authority, and this is `debug` mode.)
3. **Gap 3 → `plan_phase`.** Run an architectural/integration spike on the float-feature
   serialization format + ModelFoundry contract, then `plan_phase` for the sink-writer
   bundle. Recommended, not executed — phase creation is `plan_phase`'s job.
