# Consumer Gap Solutions — ModelFoundry

Investigation conclusions for each gap logged in
[`consumer-gap-analysis.md`](consumer-gap-analysis.md). Every gap was reproduced
against the **current source** (not the gap author's recollection); each entry
records a **verdict**, the **evidence** (file:line) behind it, and a **solution**
— a concrete fix, a planned spike/story, or the specific information still
needed.

**Verdict vocabulary**

- **confirmed** — gap reproduced against the code; a solution is determined, or a
  spike/story is planned to develop one.
- **refuted** — the claim (or a load-bearing sub-claim) is wrong: an already-built
  path exists; the corrected information / example is given.
- **pending** — needs more information, data, clarification, or a worked example
  before a verdict or solution can be fixed.

> **Method note.** Three independent read-only investigations (one per gap) traced
> the claims to source. Where a gap bundles several sub-claims, each is graded
> separately — Gap 2 and Gap 3 each contain a sub-claim that is **refuted** even
> though the headline gap is **confirmed**.

---

## Verdict summary

| # | Gap | Headline verdict | Notable sub-finding | Disposition |
|---|-----|------------------|---------------------|-------------|
| 1 | DR writes instance-relative `path`; MF resolves a bare `path` relative to **CWD** | **confirmed** | Workaround script exists (at `scripts/examples/`, not the cited path) | ✅ **FIXED — Story I.k, v0.17.1**: `_decode` anchors instance-relative `path` to the instance + bind-time fail-fast gate |
| 2 | MF encoder path applies **no** HF image-processor preprocessing | **confirmed** (headline) — blocking "collision" sub-claim **refuted** | `normalize` is a fit-on-train op applied at load (resize-via-sink + normalize coexist); DR **confirmed** it persists fixed author-supplied stats | ✅ **No spike — zero-code recipe pattern** (DR `resize` + fixed-stat `normalize` in **0-255 units** = HF stats × 255); document the pattern + units caveat |
| 3 | PyTorch loader is image-only; no audio / feature-array path | **confirmed** | MC-dropout path is **already built and modality-agnostic** (not the blocker) | ✅ **RESOLVED (Subphase I-1)** — DR shipped `npy_per_record`/`feature_path` (v0.24.0–v0.25.0); MF built the feature-array loader + per-mel-bin `audio_normalize` (Stories I.l–I.n), **verified end-to-end against a real DR materialize** (I.m.1). Spectrogram-as-image stayed rejected (lossy). Clip aggregation lands in I.o.2 |

---

## Doc-hygiene findings (apply regardless of gap disposition)

Both artifacts the analysis cites **exist** in this repo, but they were **authored
in / copied from the consumer project**, which explains two things: the cited
paths are **stale** (the consumer's layout differs), and the script **does not run
here** (it targets the consumer's `data/instances/` layout and instances, not
ModelFoundry's). Treat them as **reference copies of consumer-side artifacts**, not
as MF-native tooling. Fixing the citation paths is a one-line-each correction;
nothing here blocks a fix.

- **Workaround script** — cited as `scripts/add_mf_image_path_sidecar.py`
  ([gap analysis Gap 1](consumer-gap-analysis.md), "Workaround applied"); the copy
  here is [`scripts/examples/add_mf_image_path_sidecar.py`](../../scripts/examples/add_mf_image_path_sidecar.py).
  It documents the consumer's idempotent sidecar patch (adds
  `image_path = ../images/...`); it is **illustrative — not runnable in this repo**.
  The Gap-1 fix below **supersedes the technique** entirely.
- **Audio brief** — cited as `briefs/modelfoundry-audio-feature-consumption.md`
  (i.e. `docs/briefs/…`, [gap analysis Gap 3](consumer-gap-analysis.md), "Filed as");
  the copy here is [`docs/specs/modelfoundry-audio-feature-consumption.md`](modelfoundry-audio-feature-consumption.md).
  Its companion DR brief is `datarefinery-audio-feature-persistence.md`. As a
  consumer-authored seam brief, its behavior-level requirements are the input to
  MF's own `plan_features`; the implementation design is MF's to author.
- **Also note:** the script header and the brief reference
  `docs/specs/modelfoundry/consumer-gap-analysis.md` (a `modelfoundry/`
  subdirectory — the consumer's family-doc layout), whereas the analysis lives at
  `docs/specs/consumer-gap-analysis.md` here. Settle the intended directory
  convention for these copied seam docs so the cross-links resolve — a doc-layout
  question for the developer, not a code fix.

---

## Gap 1 — bare `path` resolved relative to CWD, not the instance

### Verdict: **confirmed**

Reproduced exactly. DataRefinery's `png_per_record` sink rewrites each record's
`path` to an **instance-relative** string; ModelFoundry's loader resolves a bare
`path` (no `image_path` sidecar) with a bare `Path(...)`, which Python anchors to
the **current working directory**. Both tools' `validate` pass because no check
verifies image resolvability — the failure only surfaces mid-training as
`FileNotFoundError`.

### Evidence

- **MF resolves bare `path` against CWD** — [plugins/pytorch/data.py:213-214](../../src/modelfoundry/plugins/pytorch/data.py#L213-L214):
  ```python
  relative = record.get("image_path")
  path = self._dataset_dir / str(relative) if relative else Path(str(record["path"]))
  ```
  The `else` branch is a bare `Path(...)` → CWD-relative. Only `image_path` is
  instance-anchored (relative to `_dataset_dir = instance.path / "dataset"`,
  [data.py:62](../../src/modelfoundry/plugins/pytorch/data.py#L62)).
- **DR writes `path` (not `image_path`), instance-relative** — the installed
  `datarefinery` package's `pipeline/path_rewrite.py` (`qualifying_image_sinks`)
  rewrites the `image` field's record `path` for `format == "png_per_record"`
  sinks; it never emits an `image_path` field.
- **No validate-time resolvability gate** — `recipe/validator.py` checks 1–22
  validate metadata (splits, counts, schemas, input-shape) but never that a
  record's image file exists. `pipeline/data_binding.py::_verify_aggressive_sidecars`
  ([data_binding.py:211-232](../../src/modelfoundry/pipeline/data_binding.py#L211))
  checks **only** `image_path` sidecars (`if not relative: continue`) — bare
  `path` records are skipped.

### Why both `validate`s pass but training dies

The instance is well-formed (splits, labels, counts all correct), so MF `validate`
and DR `materialize` are green. The mismatch is purely in *runtime path
resolution*, exercised only when the DataLoader pulls pixels — deep into a
potentially long run. This is the silent-failure class the gap names.

### Solution (determined — debug story)

Two layers, smallest first:

1. **Fix the resolution (1 file).** In [data.py:_decode](../../src/modelfoundry/plugins/pytorch/data.py#L210),
   anchor a bare **relative** `path` to the **instance root** (DR writes
   `images/train/<Class>/<id>.png`, which is instance-root-relative — note that
   is one level *above* `dataset/`, matching the consumer's `../images/...`
   sidecar workaround). Preserve absolute paths as-is for back-compat:
   ```python
   relative = record.get("image_path")
   if relative:
       path = self._dataset_dir / str(relative)
   else:
       bare = Path(str(record["path"]))
       path = bare if bare.is_absolute() else self.instance.path / bare
   ```
   This **supersedes** the consumer-side
   [`scripts/examples/add_mf_image_path_sidecar.py`](../../scripts/examples/add_mf_image_path_sidecar.py)
   technique (which patches in an `image_path = ../images/...` sidecar so MF's
   instance-anchored branch resolves) — once a bare relative `path` anchors to the
   instance, no sidecar patch is needed at all, in this repo or the consumer's.
2. **Add the cheap gate.** Extend `_verify_aggressive_sidecars` (or add a
   validator check) to confirm every record's image is resolvable from the
   instance — surfacing the error at `validate`/bind time rather than mid-train.
   Cover both branches (bare `path` and `image_path`).

**Test-first (debug mode):** a `_decode` unit test where the record carries only
an instance-relative `path`, run with `cwd != instance.path`, currently raises
`FileNotFoundError` and must pass after the fix. (Existing
`test_pytorch_data_adapter` fixtures pass today only because the test's CWD
happens to align with where the PNGs are written — they don't exercise the
CWD-divergent case.)

**Cross-repo note (housekeeping, not blocking).** The DR-side alternative — have
`png_per_record` also emit an `image_path` sidecar relative to `dataset/` — would
align both tools on MF's preferred branch. Record as a family-coordination item;
the MF-side fix stands alone and is the smaller change.

### ✅ Resolution — shipped (Story I.k, v0.17.1)

Both layers landed via the debug cycle:

- **Resolution fix** — extracted
  [`_resolve_image_path`](../../src/modelfoundry/plugins/pytorch/data.py#L210): a
  bare `path` is used as-is when **absolute** and anchored to **`self.instance.path`**
  when **relative** (the sink case); `image_path` sidecars unchanged.
- **Fail-fast gate** — `_verify_aggressive_sidecars` →
  [`_verify_record_images_resolvable`](../../src/modelfoundry/pipeline/data_binding.py#L211)
  refuses an instance-relative bare `path` whose file is absent **at bind time**
  (absolute source paths skipped).
- **Tests** — `test_decode_resolves_instance_relative_path_from_other_cwd`
  (regression; failed with `FileNotFoundError` before the fix) +
  `test_instance_relative_path_missing_refused` / `_present_binds` (gate). Full CI
  gate green.
- **Patch, not cache-invalidating** — resolution logic only; recipe hash /
  canonical bytes / output bytes unchanged for runs that already succeeded. The
  consumer-side sidecar script is now obsolete.

Outstanding (tracked as `[ ]` housekeeping on Story I.k): fix the stale citation
paths in `consumer-gap-analysis.md`; optional DR-side `image_path`-sidecar
alignment.

---

## Gap 2 — encoder path applies no HF image-processor preprocessing

### Verdict: **confirmed** (headline) — blocking sub-claim **refuted**; ✅ resolvable today (zero code)

The headline fact is true: MF never instantiates or applies a HuggingFace image
processor. But the gap's **diagnosis** — that supplying the encoder's
normalization on the data side is impossible because it *collides* with the
uint8-only `png_per_record` sink — is **refuted** by how MF actually applies
normalization. That changes the recommended path.

### Evidence (headline confirmed)

- **Encoder spec carries no preprocessing field** —
  [plugins/pytorch/architecture.py:133-137](../../src/modelfoundry/plugins/pytorch/architecture.py#L133)
  (`EncoderParams`: `source`, `id`, `frozen` only).
- **No image processor is ever loaded or applied** —
  [architecture.py:650-651](../../src/modelfoundry/plugins/pytorch/architecture.py#L650)
  loads `AutoModel.from_pretrained(...)` only; the forward pass
  ([architecture.py:548-554](../../src/modelfoundry/plugins/pytorch/architecture.py#L548))
  feeds `pixel_values=x` straight through. No `AutoImageProcessor` /
  `image_mean` / `image_std` / `image_size` anywhere under `plugins/pytorch/`.
- **Load-time normalization is DR-stats-or-`[0,1]`** —
  [data.py:179-208](../../src/modelfoundry/plugins/pytorch/data.py#L179): with no
  fit-on-train op, `image = image / 255.0` (`[0,1]`); a frozen ImageNet-pretrained
  ViT then sees the wrong input distribution.
- **The behavior is contract-documented** (so it is by-design, not an
  implementation oversight) — `features.md` FR-21 / validator check 21 specify
  "normalization in 0-255 pixel units" as the **data-side** contract. The gap is
  the *intuition mismatch* (a `transformers` user expects auto-preprocessing) plus
  the silent quality cost.

### The "collision" sub-claim — **refuted**, with the corrected mechanism

The gap states a `normalize` transform "makes the image `float`, which the
`png_per_record` sink rejects (uint8 only)," concluding resize-persistence and
normalization can't coexist. **In MF's model they can**, because `normalize` /
`mean_subtract` are **fit-on-train ops applied at load over the persisted uint8
pixels** — they do **not** rewrite the sinked bytes:

- [data.py:39](../../src/modelfoundry/plugins/pytorch/data.py#L39):
  `_FIT_ON_TRAIN_OPS = frozenset({"normalize", "mean_subtract"})`.
- [data.py:_resolve_normalization_steps](../../src/modelfoundry/plugins/pytorch/data.py#L89)
  reads each `normalize`/`mean_subtract` op's persisted `mean`/`std` vectors.
- [data.py:__getitem__](../../src/modelfoundry/plugins/pytorch/data.py#L179)
  applies `(x - mean) / std` at load on the 0-255 pixels.
- The geometry guard ([data.py:72-85](../../src/modelfoundry/plugins/pytorch/data.py#L72))
  treats fit-on-train ops as *non*-baked, so a pipeline of **resize (baked → uint8
  PNG sink) + normalize (fit-on-train → stats applied at load)** passes the guard
  and is the intended shape.

So the consumer's documented mitigation ("train with `[0,1]`, note the caveat")
was **not the only option** — declaring the encoder's expected normalization as a
DR `normalize` op would have MF apply it at load over the uint8 sink, no collision.

### Residual open question — **RESOLVED** (DataRefinery, 2026-06-23): no spike needed

The one uncertainty — could DR persist **fixed**, author-supplied `normalize`
mean/std (so a frozen encoder gets its *exact* pretrained stats rather than
fit-on-train) — is **answered yes** by DataRefinery. Verified in `NormalizeOp.fit`:
`mean`/`std` are `required=False` mode-selecting optionals — **supply both and DR
honors them as-is and persists them**; omit them and it fits from train. So the
encoder's exact ImageNet (or ViT `[-1,1]`) stats go in via a normalize op, and MF
applies them at load. **This closes Gap 2 with zero code change in either repo** —
no spike, no `Encoder`-op change.

### Solution — the zero-code recipe pattern (works today), with the critical units caveat

The pattern: **DR `resize` (to the encoder's input size, baked → uint8 PNG sink) +
DR `normalize` with fixed encoder stats (persisted, applied at load by MF).** The
Gap-1 fix (now shipped) makes the sink's instance-relative paths resolve, so the
whole chain works end-to-end.

> ⚠ **Units caveat — the easy way to get this silently wrong.** MF applies
> `(x - mean) / std` on **0-255 pixel units with NO `/255` rescale**
> ([data.py:189-199](../../src/modelfoundry/plugins/pytorch/data.py#L189-L199);
> the deliberate H.a contract). HuggingFace image processors define
> `image_mean`/`image_std` in **`[0,1]` units** (applied *after* a `/255` rescale).
> So the stats written into the DR `normalize` op must be **scaled to 0-255**:
> `mean₂₅₅ = image_mean × 255`, `std₂₅₅ = image_std × 255`. Then MF computes
> `(x₂₅₅ − image_mean·255)/(image_std·255) = (x₂₅₅/255 − image_mean)/image_std` —
> exactly the encoder's expected rescale-then-normalize. Writing the raw `[0,1]`
> HF values directly would be a *new* silent mismatch (mean ≈ 0.5 subtracted from
> 0-255 pixels). This units conversion is the recipe-surface contract to document.

Worked examples (per-channel R,G,B):

| Encoder norm | HF `[0,1]` stats | DR `normalize` op (0-255 units) |
|---|---|---|
| ImageNet | mean `[.485,.456,.406]`, std `[.229,.224,.225]` | mean `[123.675,116.28,103.53]`, std `[58.395,57.12,57.375]` |
| ViT `[-1,1]` | mean `[.5,.5,.5]`, std `[.5,.5,.5]` | mean `[127.5,127.5,127.5]`, std `[127.5,127.5,127.5]` |

**Still worth doing (docs, not a spike):** document this `Encoder`-normalization
recipe pattern (resize + fixed-stat normalize, in 0-255 units) at the recipe
surface so the next consumer doesn't re-derive it — that closes the *intuition*
gap. The `Encoder`-op-applies-HF-preprocessing idea is **no longer needed** and is
dropped (it would have moved a behavior-affecting value into the recipe with
cache-identity cost, for no benefit over the data-side path).

---

## Gap 3 — PyTorch loader is image-only; no audio / feature-array path

### Verdict: **confirmed** (headline) — MC-dropout sub-claim **refuted-in-the-good-sense** (already built)

The loader is image-only end-to-end; there is no path to consume audio /
spectrogram feature arrays. Confirmed. The gap's own assertion that the
**MC-dropout stochastic path is already implemented and modality-agnostic** is
also confirmed — i.e. the stochastic inference machinery is **not** the blocker;
the gap is purely getting non-image features *into* the model.

### Evidence (loader is image-only)

- **`_decode` always PIL-decodes RGB** —
  [data.py:210-220](../../src/modelfoundry/plugins/pytorch/data.py#L210)
  (`Image.open(path)` → `.convert("RGB")`); an `.ogg` path cannot be decoded. No
  `.npy` / `np.load` / array / `feature_path` branch exists in the file.
- **Normalization resolver is image-only** —
  [data.py:89-103](../../src/modelfoundry/plugins/pytorch/data.py#L89) matches
  only `normalize` / `mean_subtract` and reshapes for CHW image channels
  (`.view(-1, 1, 1)`); there is no `audio_normalize` branch, and
  `_FIT_ON_TRAIN_OPS` ([data.py:39](../../src/modelfoundry/plugins/pytorch/data.py#L39))
  does not register it.

### Evidence (MC-dropout already built and modality-agnostic — sub-claim refuted)

- [plugins/pytorch/stochastic.py:94-118](../../src/modelfoundry/plugins/pytorch/stochastic.py#L94)
  (`mc_forward_proba`) runs T seeded active-dropout passes over an arbitrary
  `batch` tensor and softmaxes the **logits** — it never touches input decoding.
- `mc_aggregate` / `predictive_entropy` / `enable_mc_dropout` operate purely on
  probability stacks and `nn.Module` dropout layers
  ([stochastic.py:61-91](../../src/modelfoundry/plugins/pytorch/stochastic.py#L61)).
- The recipe `Inference` block is modality-agnostic and already modeled —
  [recipe/models.py:91-128](../../src/modelfoundry/recipe/models.py#L91)
  (`InferenceSpec`: `mode: point|mc_dropout`, `mc_samples`).

So **no work is needed on the stochastic path** — the consumer's note is
accurate, and confirming it scopes the real work to the loader alone.

### Decision: spectrogram-as-image is **not** the right solution

Asked directly — *is modeling the spectrogram as an image correct?* **No.** It is a
lossy stopgap, not the right contract. Build the **feature-array consumption path**.
Reasons, specific to audio features (not generic preference):

1. **Quantization is genuinely lossy here.** A log-mel spectrogram is `float32`
   with high dynamic range (a dB-scale field). The PNG route requires quantizing to
   **uint8 (256 levels) + range clipping** — the DataRefinery brief's own option 3
   wording. For natural images 8-bit *is* the native representation; for audio
   features it discards precision the model trains on. (Both briefs flag the route
   as "lossy.")
2. **Wrong normalization contract.** The image path applies image semantics
   (0-255 pixel units, RGB per-channel stats or `/255`); audio needs
   `audio_normalize` — **per-mel-bin** fit-on-train standardization (R5). Forcing
   audio through the image normalizer applies statistics of the wrong shape and
   meaning.
3. **Wrong channel semantics.** `_decode` does `.convert("RGB")` →
   [data.py:219](../../src/modelfoundry/plugins/pytorch/data.py#L219) — 3 channels.
   A spectrogram is **1 channel** `(1, n_mels, n_frames)` (or `C` feature
   channels). RGB triples the data meaninglessly / fakes a 3-channel encoding.
4. **Breaks the reproducibility contract.** A PNG round-trip of a float array is
   **not lossless** — you cannot recover the exact features the determinism
   guarantee (QR-3/FR-25) is defined over. The `.npy` feature-array path *is*
   lossless and round-trips, which is why DR's preferred sink is `npy_per_record`,
   not a quantized PNG.
5. **It would add divergence, not reuse.** The PNG route is not free even on the
   data side — DR would have to ship a **new uint8-quantization sink mode** (its
   brief's option 3) purely to work around MF's missing branch, producing a second,
   lossy representation of features DR already computes as float. The proper path
   reuses DR's existing sink mechanism (`npy_per_record`, additive) and keeps the
   "arrays are in-pipeline; persist via a sidecar" convention intact.

The developer already **declined** the spectrogram-PNG interim
([`consumer-gap-analysis.md`](consumer-gap-analysis.md) Gap 3, "Model 2 build
paused"). This verdict confirms that call: the interim is a hack; the
feature-array path is the solution.

### Plan: the proper feature-array consumption path (cross-repo, `plan_features`)

This is a new capability spanning two repos, not a debug fix. Both briefs exist and
agree on the contract —
[`modelfoundry-audio-feature-consumption.md`](modelfoundry-audio-feature-consumption.md)
(consume) paired with
[`datarefinery-audio-feature-persistence.md`](datarefinery-audio-feature-persistence.md)
(persist). **Neither half alone unblocks the consumer — they land together.**

**Shared on-disk contract (pin jointly with DR before coding):**
- DR ships an **`npy_per_record`** array sink: persists the float field per record
  at `features/<split>/<record_id>.npy`, shape **`(n_mels, n_frames)`**, and
  rewrites a **`feature_path`** relative to `dataset/` (mirrors how
  `png_per_record` rewrites `image_path`). Sink output is instance content →
  covered by cache identity exactly as PNG is.
- DR persists the **`audio_normalize`** fit-on-train stats (per-mel-bin).

**ModelFoundry side (the story):**
- **Feature-array branch in `_decode`** ([data.py:210](../../src/modelfoundry/plugins/pytorch/data.py#L210)):
  when a record carries `feature_path`, `np.load` it into a
  `(1, n_mels, n_frames)` tensor (general `(C, n_mels, n_frames)` if multi-channel)
  instead of `Image.open`. Default image path unchanged (additive).
- **`audio_normalize` branch in `_resolve_normalization_steps`**
  ([data.py:89](../../src/modelfoundry/plugins/pytorch/data.py#L89)): read
  per-mel-bin stats with audio-appropriate reshape; register `audio_normalize` in
  [`_FIT_ON_TRAIN_OPS`](../../src/modelfoundry/plugins/pytorch/data.py#L39) so the
  geometry guard treats it as fit-on-train, not a baked transform.
- **Branch selection** to decide in the story: per-record (`feature_path` /
  `image_path` / bare `path` presence) vs. per-instance (manifest modality flag).
  Per-record field presence is the lighter-touch option and composes with the
  Gap-1 resolution precedence.
- **Window→clip regrouping** by `source_record_id` (R7) for evaluating MC-dropout
  predictions at the clip level — confirm where this lives (loader vs. evaluation).

**Already done — do not rebuild:** the MC-dropout stochastic path
([stochastic.py](../../src/modelfoundry/plugins/pytorch/stochastic.py#L94)) and the
`Inference` recipe block ([models.py:91-128](../../src/modelfoundry/recipe/models.py#L91))
are modality-agnostic and implemented. The work is purely the loader.

**Acceptance tests** (from the MF brief's verification): a materialized audio
instance + spectrogram-CNN recipe with `Inference: {mode: mc_dropout, mc_samples: T}`
trains end-to-end producing per-record `predictive_entropy` / `mc_variance` and
`ece` over MC-aggregated means; the run is deterministic and round-trips from disk;
default image recipes are unaffected.

**Mode note:** route through **`plan_features`** (new capability + cross-repo
contract), not `debug`. Sequence: settle the shared contract with DR → DR ships
`npy_per_record` → MF ships the consumption branch (or in parallel against the
agreed contract, since neither ships value alone).

### Cross-repo coordination (DataRefinery contract, status 2026-06-23)

DataRefinery's own solutions doc
([`datarefinery/consumer-gap-solutions.md`](datarefinery/consumer-gap-solutions.md)
Gap 3) and its **vendored dependency contract**
([`datarefinery/vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md))
were both reviewed across several rounds. The feature-array transport is the
**§ "Audio feature-array persistence — `npy_per_record` + `feature_path`"** in the
vendor-spec, with **MF's review-round questions Q1–Q6 pinned** (2026-06-23).
**Status: SHIPPED (DR v0.25.0; MF Subphase I-1).** DR shipped the `npy_per_record`
sink + `feature_path` rewrite (v0.24.0–v0.25.0) and MF built the loader branch +
per-mel-bin `audio_normalize` (Stories I.l–I.n), **verified end-to-end against a real
DR materialize** (Story I.m.1). The Q1–Q6 pins below are the as-shipped contract,
confirmed against the installed DR. Clip-level aggregation (R7) lands in I.o.2.

**Pinned feature-transport contract (the binding facts for MF's loader story):**

- **Q1 — `feature_path` anchor: instance-root-relative**, resolve `<instance>/<feature_path>`
  (e.g. `<instance>/features/<split>/<record_id>.npy`). It is the **J.g sink-`path`
  bucket, NOT `image_path`'s `dataset/`-relative anchor** — the earlier
  "anchored as `image_path`" wording was self-contradictory and is corrected.
  MF's shipped Story I.k precedence already resolves bare/sink `path` against the
  instance root, so `feature_path` joins that branch.
- **Q2 — sink persists the RAW `mel` (pre-normalize); the consumer applies
  `audio_normalize` at load** — the audio analogue of "normalization is applied by
  the consumer, not baked." No double-normalize. (An author *may* sink any field,
  but the blessed path is `field: mel` + consumer-applied stats; MF consumes `mel`.)
- **Q3 — dtype asymmetry:** the `.npy` is **`float32`** (`power_to_db(...).astype(float32)`);
  the `audio_normalize` `mean`/`std` stats are **`float64`** (same promotion as image
  `normalize`). Apply `(mel − mean) / std` with promotion; byte-identity is over the
  float32 array.
- **Q4 — rank: always 2-D `(n_mels, n_frames)`** in v1 (mono); MF asserts `ndim == 2`
  and **owns the unsqueeze** to `(1, n_mels, n_frames)`. `(C, …)` is future, not v1.
- **Q5 — `feature_path` may be nested**; join as a relative POSIX path (same as
  `image_path`, Story J.h) — do not assume a flat `features/<split>/`.
- **Q6 — `feature_path` is authoritative** over any stray source `path` on the same
  record; MF ignores `path` for feature resolution (same rule as `image_path`).
- **Branch selection / cache identity / coupling:** per-record field presence
  (`feature_path` ⇒ feature path; else image path); sink output covered by DR's cache
  identity exactly as PNG; MF consumes **read-only** (never re-hashes the instance).

**Surrounding audio contract also pinned (from the 2026-06-22 additions):**

- **`audio_normalize` stats** (J.t): per-mel-bin `mean`/`std`, **`n_mels` rows**,
  **mel axis = axis 0** of `(n_mels, n_frames)`; apply
  `(feature − mean[:, None]) / std[:, None]`; same parquet shape + exact
  zero-variance guard (`std == 0 → 1.0`) as image `normalize`. This is exactly
  MF's `_resolve_normalization_steps` audio branch — now precisely specified
  (was "audio-appropriate reshape" hand-wave in the plan above).
- **mel orientation** (J.s): `(n_mels, n_frames)` librosa-native — confirms the
  `(1, n_mels, n_frames)` load target.
- **Window records** (J.q): the `window` Generation op uses `replace_input_records`,
  so `record_counts` is **post-windowing**; window ids are `…__w{window_index:04d}`
  (vs image `…__v{variant_index:03d}`), carrying `source_record_id` (parent clip) +
  `window_index`. MF must treat windows as first-class records, not clips.
- **Aggregation contract R7** (J.u): `source_record_id` is DR's clip↔window grouping
  key; **DR ships no aggregation op** — MF owns the clip-level aggregation math
  (mean/logit-avg/vote) for MC-dropout eval. New **failure mode**: a window whose
  `source_record_id` resolves to no clip → refuse (MF should add this check
  alongside its existing sidecar-missing detection).

**Still-open cross-repo coordination items:**

1. **Float-array path** — ✅ **landed.** Both *solutions docs* committed to
   `npy_per_record` and DR demoted its PNG option 3 to "do not build"; this is now
   **contract, not intent** — the *vendor-spec* § "Audio feature-array persistence" is
   ratified shipped (DR v0.25.0) and MF consumes it (Subphase I-1).
2. **`feature_path` shape-binding surface → vendor-dependency-spec
   (authority RESOLVED 2026-06-23; one nicety left).** The DR vendor-spec's new
   `DR:`/`MF:` Revision-Log path convention + its link evidence resolve the earlier
   "does the spec exist?" confusion — it was a **directory-convention mix-up**, not a
   missing doc. The convention: each repo files DR-pushed/shared docs under a subdir
   named for the *other* tool.
   - **The DR↔MF shared contract** (`vendor-dependency-spec.md`) — authored
     **canonically in DataRefinery** (`DR:docs/specs/modelfoundry/…`, the ~68 KB copy)
     and vendored into MF at **`MF:docs/specs/datarefinery/vendor-dependency-spec.md`**
     ([the mirror](datarefinery/vendor-dependency-spec.md)). Proof it's DR-canonical:
     this MF copy's relative links are DR-relative (they resolve to *swapped* targets
     in the MF tree). It **exists** — there was never a missing shared contract.
   - **MF's own downstream contract** (how *future* consumers — modelmetrics/modelmachine
     — bind against MF) is a **separate, not-yet-authored** doc forward-declared in
     `MF:docs/specs/stories.md` Future. (Its eventual home should follow the same
     "subdir named for the other tool" convention; the literal `docs/specs/modelfoundry/`
     path in that forward-declaration is a maintainer call, not this seam's concern.)

   So there is no real "missing contract." **Remaining nicety (not blocking):** no
   written rule that the DR↔MF contract is *edited in DR and vendored into MF* — so
   when Gap-3 `plan_features` needs a change, MF **proposes it to DR** (attributed
   `MF:` in the Revision Log) to absorb and re-vendor, rather than editing the MF
   mirror in isolation (which would drift). The MF mirror's relative links are also
   DR-relative (broken in the MF tree) — cosmetic. MF consumes the instance
   read-only regardless (loose-coupling invariants hold — MF never re-hashes it).
3. **Versioning-scheme divergence (governance).** The vendor-spec states DR uses
   **per-segment versions with *no* global umbrella counter** (line 404) and asserts
   "MF adopts the horizontal mechanism wholesale." But MF's segmented identity
   carries an **umbrella combiner version** (`SUPPORTED_COMBINER_VERSIONS`, per
   `project-essentials.md`) that DR does not. This joins the already-recorded
   `join_stable` byte-format divergence (DR `b"\x1f".join` unframed vs MF labeled /
   length-framed) on the **divergence ledger** of the "governed cross-tool-family
   standard." Functionally inert for MF (it consumes DR's `recipe_hash` opaquely,
   never recomputes it), so it is a **coordination/governance item, not a bug** —
   align at the family level; do not change MF's combiner unilaterally.

**Net:** the audio seam's *supporting* surfaces (stats, orientation, windowing,
aggregation key, failure mode) are now pinned and de-risk MF's eventual loader; but
the **feature-array transport itself is still unshipped on DR's side and absent from
the contract**, so MF Gap-3 remains blocked on that — sequencing confirmed, not
closed. Gap 2's enabling fact is independently **corroborated** by the same spec:
image `normalize` "can pin either [mean/std] as params (in which case the pinned
value is the persisted value)" (line 293) — the fixed-stats path MF's Gap-2
resolution relies on is now in the authoritative contract, not just DR's verbal
reply.

---

## Recommended next actions

1. **Gap 1 → ✅ DONE (Story I.k, v0.17.1).** Fixed via the debug cycle: loader
   anchors instance-relative `path` to the instance + bind-time fail-fast gate;
   full CI gate green. Consumer-side sidecar workaround is now obsolete.
2. **Gap 2 → ✅ no spike; document the recipe pattern.** DataRefinery confirmed
   `normalize` persists fixed author-supplied stats, so a frozen encoder gets exact
   stats today with **zero code in either repo**: DR `resize` + `normalize` with the
   encoder's stats **in 0-255 units (HF stats × 255)**. Only task left is to
   document this `Encoder`-normalization pattern + the units caveat at the recipe
   surface (a docs change — `plan_features`/`plan_tech_spec` or a short doc story).
   The Encoder-op-applies-HF-preprocessing idea is dropped.
3. **Gap 3 → ✅ RESOLVED (Subphase I-1, DR v0.25.0).** Decision held: spectrogram-as-image
   is lossy and wrong; MF built the feature-array path. **Status (reconciled 2026-06-23,
   verified against installed DR 0.25.0):** DR **shipped** feature-array persistence —
   the `npy_per_record` sink + `feature_path` rewrite (v0.24.0–v0.25.0; `SinkOp.format`
   is now `Literal['png_per_record','npy_per_record']`) and the vendor-spec §
   "Audio feature-array persistence" is ratified shipped. MF authored the consumer half
   in Subphase I-1: the synthesized fixture (I.l), the feature-array `_decode` branch
   (I.m), the per-mel-bin `audio_normalize` apply (I.n), and a **real-DR end-to-end
   materialize smoke** (I.m.1) — synthesized fixture and real DR output agree. The R7
   clip-level window aggregation + dangling-window failure mode land in I.o.2. The
   modality-agnostic MC-dropout path was reused unchanged.
