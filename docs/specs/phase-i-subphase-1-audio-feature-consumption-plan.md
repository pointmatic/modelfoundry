# Subphase I-1 Plan — Audio Feature-Array Consumption

> **Mode:** `plan_phase` (pre-1.0). **Structure:** Subphase **I-1** under the existing
> `## Phase I: Segmented Recipe Architecture`. Stories continue monotonically from
> the phase's last story **I.k** → **I.l, I.m, …** (story letters reset only at a
> phase boundary, never a subphase boundary).
>
> **Multi-release exception.** Phase I already shipped (v0.16.0 → v0.17.1). Subphase
> I-1 is a follow-on subphase that ships its own release tag (**→ v0.18.0**, a minor —
> new additive capability). This is the documented Version-Cadence multi-release
> exception (`_phase-letters.md` § Subphases): the subphase's last code story owns the
> bump.

This subphase delivers **ModelFoundry's half of the audio feature-array seam** — the
PyTorch loader path that consumes prepared audio features (log-mel spectrograms) from
a materialized DataRefinery instance. It is the consuming counterpart to DataRefinery's
forward-declared `npy_per_record` sink.

It is derived from [`consumer-gap-solutions.md`](consumer-gap-solutions.md) **Gap 3**
(decision: build the feature-array path; spectrogram-as-image is rejected as lossy) and
is bound to [`datarefinery/vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md)
§ "Audio feature-array persistence — `npy_per_record` + `feature_path`" (Q1–Q6),
§ "Audio spectral features", § "`audio_normalize` statistics", § "Audio window records",
and § "Failure modes ModelFoundry SHOULD detect". The companion briefs are
[`modelfoundry-audio-feature-consumption.md`](modelfoundry-audio-feature-consumption.md)
(consume) and [`datarefinery-audio-feature-persistence.md`](datarefinery-audio-feature-persistence.md)
(persist).

---

## 1. Gap analysis — what exists vs. what's needed

| Area | Exists today | Needed |
|------|--------------|--------|
| **Image loader** | `_decode` PIL-decodes RGB → CHW 0-255; `_resolve_image_path` anchors instance-relative `path` to the instance root (Story I.k) | A **`feature_path` branch** that `np.load`s a `(n_mels, n_frames)` `float32` array and unsqueezes to `(1, n_mels, n_frames)` |
| **Normalization** | `_resolve_normalization_steps` reads `normalize`/`mean_subtract` from DR's **`Transformations`**, reshapes per-channel `.view(-1,1,1)` (image CHW) | An **`audio_normalize` branch** that reads DR's **`Featurizations`**, applies per-mel-bin stats on **axis 0** (`(feat − mean[:,None])/std[:,None]`); register `audio_normalize` in `_FIT_ON_TRAIN_OPS` |
| **Branch selection** | Always image | Per-record field presence: `feature_path` ⇒ feature path; `image_path`/bare `path` ⇒ image path |
| **Window/clip model** | Records are 1:1 with samples | Window records (`__w####`, `source_record_id`, `window_index`) are **first-class records**; clip-level results regroup by `source_record_id` (R7) |
| **MC-dropout stochastic path** | ✅ **already built & modality-agnostic** (`plugins/pytorch/stochastic.py`; `InferenceSpec`) | **Do not rebuild.** Only add clip-level aggregation *over* its per-record outputs |
| **Failure detection** | Sidecar-missing / instance-relative-path-missing refused at bind (Story I.k) | **Dangling `source_record_id`** (window resolves to no clip) → refuse |
| **Test substrate** | `tests/fixtures/datarefinery_instances/builder.py` synthesizes image instances (CIFAR smoke) | A synthesized **audio** instance: `features/<split>/<id>.npy`, `feature_path` JSONL, `audio_normalize` stats parquet, `manifest.sinks[…].format = npy_per_record` |
| **Gap 2 (image encoders)** | Frozen-encoder normalization works today (DR `resize` + fixed-stat `normalize`) | **Docs only**: recipe pattern + the 0-255 units caveat (HF stats × 255) |

**Cross-repo status.** DataRefinery has **not yet shipped** the `npy_per_record` sink
(forward-declared in the vendor-spec). Per the decision recorded with this plan, MF
builds its half **now against the pinned Q1–Q6 contract**, verified with a synthesized
`.npy` fixture that mimics the contract exactly. End-to-end against a *real* DR audio
instance is verified when DR ships; MF's half is complete and the seam stays aligned.

---

## 2. The pinned contract this subphase binds against (vendor-spec, verbatim facts)

These are the load-bearing facts every story must honor — copied here so the subphase
is self-contained and "perfectly aligned" with the vendor-spec:

- **Q1 — `feature_path` anchor: instance-root-relative.** Resolve `<instance>/<feature_path>`
  (e.g. `<instance>/features/train/<record_id>.npy`). Same bucket as I.k's sink-`path`
  resolution; **NOT** `image_path`'s `dataset/`-relative anchor.
- **Q2 — persisted field is the raw `mel`** (pre-normalize); MF applies `audio_normalize`
  at load. No double-normalize. (MF must *not* expect an already-normalized `feature`.)
- **Q3 — dtype: `.npy` is `float32`; `audio_normalize` `mean`/`std` are `float64`.**
  Apply `(mel − mean) / std` with promotion; byte-identity is over the float32 array.
- **Q4 — rank: always 2-D `(n_mels, n_frames)`** in v1 (mono). MF asserts `ndim == 2`
  and **owns the unsqueeze** to `(1, n_mels, n_frames)`. `(C, …)` multi-channel is future.
- **Q5 — `feature_path` may be nested**; join as a relative POSIX path onto the instance
  root verbatim (clip ids contain `/`). Do not assume a flat `features/<split>/` level.
- **Q6 — `feature_path` is authoritative** over any stray source `path` on the record;
  ignore `path` for feature resolution.
- **`audio_normalize` stats:** per-mel-bin, **`n_mels` rows**, **mel axis = axis 0** of
  `(n_mels, n_frames)`; same parquet shape (single `value` column, axis-0 order), same
  zero-variance guard (`std == 0 → 1.0` at apply, persisted `std` unmodified), same
  `stats_from_instance` parity as image `normalize`. Resolve the op id from the recipe's
  **`Featurizations`** section by op kind (`audio_normalize`).
- **Window records (R7):** `record_id = <clip_id>__w{window_index:04d}`; each carries
  `source_record_id` (parent clip) + `window_index`. `manifest.record_counts` is
  **post-windowing**. Every window of a clip shares one `source_record_id` and lands in
  one split (no straddling). **DR ships no aggregation op — MF owns the clip-level math**
  (mean / logit-average / vote). A window whose `source_record_id` resolves to no clip →
  **refuse** (corruption signal).
- **Cache identity & coupling:** the sink output is DR instance content, covered by DR's
  `(recipe_hash, input_hash, seed)`. MF consumes **read-only** and never re-hashes the
  instance (loose-coupling invariant in `project-essentials.md`).

---

## 3. Feature requirements (mini-features.md)

A new FR for `features.md` (formal edit handled in the doc/release story — see §6):

- **FR-AUDIO-1 — Audio feature-array consumption.** ModelFoundry's PyTorch loader
  consumes prepared float feature arrays from a materialized DataRefinery instance via
  the per-record `feature_path` field, applying the persisted per-mel-bin `audio_normalize`
  fit-on-train statistics at load. Selection is per-record (`feature_path` ⇒ feature path).
  Default image recipes are unaffected (additive).
- **FR-AUDIO-2 — Clip-level window aggregation (R7).** For instances whose records are
  windows of a parent clip, ModelFoundry regroups window-level predictions (including
  MC-dropout aggregates) by `source_record_id` to produce clip-level evaluation results,
  applying a recipe-declared aggregation policy. A window whose `source_record_id` does
  not resolve to a clip in the instance is refused.
- **FR-AUDIO-3 — Reproducibility parity.** An audio MC-dropout run is byte-deterministic
  and round-trips from disk exactly as the image path does (QR-3 / FR-25 unchanged).

**Recipe-surface impact (no-implicit-defaults discipline).** FR-AUDIO-2's aggregation
policy is a **new recipe field** (likely under `Evaluation`/`Inference`). Per Phase I's
no-implicit-defaults rule it must be either **author-required + scaffolder-emitted** or a
**mode-selecting optional** with a versioned "absent ⇒ behavior" mapping — *not* a silent
code default. The exact placement/shape is the one open design point, settled inside its
story (§4, I.o). **This is the only canonical-bytes-affecting change in the subphase**, and
it only affects *audio* recipes that declare it — existing image recipes' canonical bytes
are unchanged ⇒ **not a cache-invalidation event** for any existing instance.

---

## 4. Technical changes (mini-tech-spec) & story breakdown

Each story = one coherent unit → one commit. Sequence and IDs (continuing from I.k):

### I.l — Synthesized audio feature-array fixture builder *(test substrate, foundation-first)*
Extend [tests/fixtures/datarefinery_instances/builder.py](tests/fixtures/datarefinery_instances/builder.py)
(or add a sibling `audio_smoke/builder.py`) to emit a DataRefinery-shaped **audio**
instance matching the pinned contract: `features/<split>/<record_id>.npy`
(`(n_mels, n_frames)` `float32`); `<split>.jsonl` records carrying `feature_path`,
`source_record_id`, `window_index`, label, and `record_id = <clip>__w####`;
`fitted_statistics/<op_id>/{mean,std}.parquet` (per-mel-bin, `n_mels` rows, axis-0);
`manifest.record_counts` post-windowing; `manifest.sinks[<name>].format = npy_per_record`;
a recipe object exposing an `audio_normalize` `Featurizations` op. No `src/` change. The
substrate every following story tests against.

### I.m — Feature-array branch in `_decode` + per-record branch selection
[data.py:`_decode`](src/modelfoundry/plugins/pytorch/data.py#L210): when a record carries
`feature_path` (Q6: authoritative over `path`), resolve it **instance-root-relative**
(reuse the I.k precedence; Q1), nested-POSIX join (Q5), `np.load`, **assert `ndim == 2`**
(Q4) and unsqueeze to `(1, n_mels, n_frames)`. Image branch unchanged (additive). The
geometry guard (`_refuse_unbaked_geometry_transforms`) must treat the audio path correctly
(features are sinked content, not pre-transform pixels). Tests via the I.l fixture,
including a CWD-divergent resolution test (parity with I.k's regression).

### I.n — `audio_normalize` fit-on-train branch
[data.py:`_resolve_normalization_steps`](src/modelfoundry/plugins/pytorch/data.py#L89):
read DR's **`Featurizations`** for `audio_normalize` (today only `Transformations` is
scanned); register `audio_normalize` in
[`_FIT_ON_TRAIN_OPS`](src/modelfoundry/plugins/pytorch/data.py#L39); apply per-mel-bin
stats on **axis 0** with an audio-appropriate reshape (`mean[:, None] / std[:, None]`,
*not* the image `.view(-1,1,1)`), float64 stats over float32 array (Q3), same exact
zero-variance guard. Make the reshape modality-aware (image CHW vs audio mel-axis) driven
by the active branch. Tests assert per-mel-bin standardization byte-matches a reference.

### I.o — Clip-level window aggregation (R7) + dangling-key refusal
Group window-level predictions by `source_record_id` and apply the recipe-declared
aggregation policy (mean / logit-average / majority-vote) to produce clip-level results;
this layers over the **already-built** MC-dropout per-record outputs
([stochastic.py](src/modelfoundry/plugins/pytorch/stochastic.py)). **Design decision in
this story:** (a) where aggregation lives (loader vs. evaluation stage) and (b) the recipe
field shape for the policy (FR-AUDIO-2 / no-implicit-defaults — §3). Add the **dangling
`source_record_id`** failure-mode check (refuse a window with no resolvable clip),
alongside the existing bind-time gates. Validator cross-check that the aggregation policy
references a producible grouping.

### I.p — End-to-end audio MC-dropout integration test (acceptance)
A materialized (synthesized) audio instance + a 1-channel spectrogram-CNN recipe with
`Inference: {mode: mc_dropout, mc_samples: T}` trains end-to-end, producing per-record
`predictive_entropy` / `mc_variance` and `ece` over MC-aggregated means, **clip-level**
via I.o; assert **byte-deterministic** + **round-trips from disk** + **default image
recipes unaffected**. This is the brief's verification turned into the acceptance gate.

### I.q — Gap 2 docs: Encoder-normalization recipe pattern *(zero code)*
Document at the recipe surface the frozen-encoder normalization pattern: DR `resize` +
fixed-stat `normalize` applied at load over the uint8 sink, **in 0-255 units** with the
**HF stats × 255** conversion (ImageNet / ViT worked table) and the silent-mismatch
caveat. Closes the Gap 2 *intuition* gap. Orthogonal to audio; folded in because it is
the last open item in the same solutions doc.

### I.r — Doc sync, project-essentials append & release — **owns the bump (→ v0.18.0)**
Add FR-AUDIO-1/2/3 to `features.md`; reflect the loader branch + window/clip model in
`tech-spec.md`; refresh `concept.md`/`README.md` if scope wording needs it; re-ratify the
vendor-spec mirror note (status remains forward-declared until DR ships its sink — record
that MF's half is ready). Append any new must-know facts to `project-essentials.md`
(plan_phase Step 8). Owns the single minor bump for the subphase. Release note: new audio
consumption capability; **not cache-invalidating** for existing instances.

---

## 5. Out of scope (deferred) — *to be walked through at the approval gate*

1. **DataRefinery's `npy_per_record` sink** — DR's half (its own `plan_phase`). This
   subphase builds MF's consumer half against the pinned contract + a synthesized fixture.
2. **End-to-end verification against a real DR audio instance** — gated on (1); MF's half
   is verified against the synthesized fixture now, real-instance smoke when DR ships.
3. **Multi-channel `(C, n_mels, n_frames)` features** — vendor-spec Q4 pins v1 to 2-D mono;
   multi-channel is explicitly future. MF asserts `ndim == 2` and owns the unsqueeze.
4. **`plan_features` formal pass** — the FRs are captured in this plan and folded into
   `features.md` by I.r; a dedicated `plan_features` revision is not run unless the
   recipe-surface aggregation field (I.o) proves larger than a single field.
5. **Non-spectrogram audio / raw-waveform models** — only the prepared log-mel feature-array
   path is in scope; raw `sample_array` consumption is not (it is in-pipeline-only on DR's
   side anyway).
6. **Generalized `audio_normalize` beyond per-mel-bin** (e.g. global or per-frame) — the
   contract pins per-mel-bin axis-0 stats; other normalization shapes are out of scope.
7. **An architectural/investigation spike** — *deliberately omitted.* Q1–Q6 close the
   integration boundary; the residual design choice (aggregation placement + policy field)
   is small enough to settle inside I.o rather than a throwaway spike.

---

## 6. Cache-identity & contract-alignment checklist

- **Not cache-invalidating** for existing instances: the loader change is additive; image
  recipes' canonical bytes and materialized output bytes are unchanged. The only
  canonical-bytes surface is the new audio aggregation field (I.o), which only audio
  recipes declare — a new recipe authoring it produces *its own* identity, it does not
  perturb any existing instance. Minor bump (new feature), no production ceremony (pre-1.0).
- **Loose-coupling invariant preserved:** MF consumes the DR feature sink **read-only**;
  it never re-hashes the DR instance and never writes into DR's cache tree.
- **Determinism contract preserved:** the audio path runs under the same four invariants
  (deterministic algorithms, per-record worker seeding, serial Optuna, AMP off); the
  integration test (I.p) asserts byte-identity.
- **Vendor-spec alignment:** every binding fact in §2 traces to the vendor-spec. Any change
  MF needs to the *shared* contract is **proposed to DataRefinery** (attributed `MF:` in the
  Revision Log) and re-vendored — never edited in the MF mirror in isolation.
