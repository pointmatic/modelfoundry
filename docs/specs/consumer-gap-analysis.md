# Consumer Gap Analysis — ModelFoundry (and the DataRefinery → ModelFoundry seam)

A running log of friction met taking a real consumer project through the intended happy
path: **recipe-writing → data-preparation (DataRefinery) → model-building (ModelFoundry)**.
This file covers the **ModelFoundry** side and the **DR → MF hand-off seam**; the
DataRefinery-internal gaps live in
[`../datarefinery/consumer-gap-analysis.md`](../datarefinery/consumer-gap-analysis.md).
Entries are consumer-sanitized for hand-off into the public dependency repos.

"Intuition gaps" (the behavior is *implemented* correctly but a competent consumer cannot
predict the required wiring from the docs/recipe surface) are logged here too — those are
the ones that cost the most time.

## Gap index

| # | Gap | Surface | Severity | Status |
|---|-----|---------|----------|--------|
| 1 | DR `png_per_record` sink writes `path`; MF resolves a bare `path` **relative to CWD** (not the instance) — persisted resized images aren't found | DR→MF seam | blocks `training` after both `validate` clean (workaround exists) | workaround applied; fix requested |
| 2 | MF applies **no** encoder preprocessing (HF image-processor resize/normalize) — the consumer must encode the backbone's expected normalization as DR stats, which collides with the `png_per_record` uint8 sink | MF encoder path (intuition) | correctness risk (degraded features) | documented; mitigation pending |
| 3 | PyTorch loader is **image-only** (`Image.open`) — no path to consume audio / feature-array instances; normalization resolver handles only image ops | MF data-load path | **blocks** the audio (probabilistic) model (no workaround) | fix requested ([brief](../briefs/modelfoundry-audio-feature-consumption.md)); blocks Model 2 |

---

## Gap 1 — persisted-image hand-off: DR writes `path`, MF resolves it relative to CWD

| Field | Value |
|-------|-------|
| Surface | DR→MF seam |
| Related contracts | DR `SinkOp` (`format: png_per_record`, rewrites `path`); MF loader `DataRefineryDataset._decode` (`modelfoundry/plugins/pytorch/data.py`) |
| Sanitized | yes |
| First hit | 2026-06-22 |

### Symptom

A consumer resizes images in DataRefinery (a pixel-altering transform), which — per the DR
validator — **requires** a `png_per_record` sink to persist the transformed pixels. DR
materializes cleanly; ModelFoundry `validate` passes all 22 checks; then `materialize`
fails in the **training** stage:

```
stage 'training' failed: [Errno 2] No such file or directory:
"images/train/<Class>/<id>.png"
```

The file exists — under `<instance>/images/train/<Class>/<id>.png`. Both tools were green;
the failure only appears once training starts pulling pixels.

### Affected contract / abstraction

- **DR side:** the `png_per_record` sink writes images under the instance and **rewrites
  the record's `path`** to an *instance-relative* string (e.g. `images/train/<Class>/<id>.png`).
  `SinkOp` exposes only `{name, stage, splits, field, format, path_template}` — there is no
  option to emit a differently-named field.
- **MF side:** `DataRefineryDataset._decode` resolves pixels as:

  ```python
  relative = record.get("image_path")
  path = self._dataset_dir / str(relative) if relative else Path(str(record["path"]))
  ```

  i.e. it prefers an **`image_path`** field resolved relative to `<instance>/dataset/`, and
  otherwise treats **`path`** as-is — a bare `Path(...)` resolved against the **current
  working directory**, not the instance.

The two conventions don't meet: DR emits `path` (instance-relative); MF's only
instance-anchored resolution is via `image_path`, which DR never writes. The fallback
silently reinterprets DR's instance-relative `path` as CWD-relative.

### Diagnosis

A pure intuition gap with no surfaced contract: nothing in the recipe surface tells a
consumer that "persist resized images in DR, consume in MF" requires an `image_path`
sidecar relative to `dataset/`. Both `validate` passes reinforce the false confidence. It
is also a silent-failure-class issue: a *correct-looking* pipeline dies deep into a
(potentially long) run.

### Recommended fix

- **Make the hand-off explicit on one side.** Either DR's `png_per_record` sink emits an
  `image_path` sidecar (relative to `dataset/`) in addition to / instead of rewriting
  `path`, **or** MF resolves a bare `path` relative to the **instance** (or `dataset/`)
  rather than CWD. Aligning on `image_path`-relative-to-`dataset/` (already MF's preferred
  branch) is the smallest change.
- **Cross-validate at the cheap gate:** MF `validate` (or DR materialize) should check that
  every record's image is resolvable from the instance, so the error surfaces before
  training rather than mid-run.

### Workaround applied

Patch the materialized instance to add the `image_path` sidecar MF expects, pointing at the
sink's PNGs relative to `dataset/` (the PNGs are at `<instance>/images/...`, so
`image_path = ../images/...`), via
[`scripts/add_mf_image_path_sidecar.py`](../../../scripts/add_mf_image_path_sidecar.py).
**Caveat:** this mutates a content-addressed instance, so it must be re-run after any
`clean` + re-`materialize` of the DR data. (A non-mutating alternative is a CWD symlink so
the bare-`path` fallback resolves; the sidecar is closer to MF's intended mechanism.)

### Verification

- After the patch, every record carries `image_path` resolving (via `dataset/`) to an
  existing PNG; MF training reads pixels and proceeds past the load.
- A fixed hand-off (DR emits `image_path`, or MF anchors `path` to the instance) removes the
  patch entirely.

---

## Gap 2 — encoder path applies no HF preprocessing (normalization is the consumer's job)

| Field | Value |
|-------|-------|
| Surface | MF PyTorch encoder path (intuition) |
| Related contract | MF loader normalization (`data.py`: DR fit-on-train `normalize`/`mean_subtract` stats applied at load, else `/255`); `Encoder` op |
| Sanitized | yes |
| First hit | 2026-06-22 |

### Symptom / intuition gap

Loading a pretrained HuggingFace encoder (`Encoder { id: <hf vit> }`), one reasonably
expects MF to apply that backbone's **own** image preprocessing (resize + ImageNet-style
normalization via the HF image processor), the way `transformers` pipelines do. It does
**not**: `data.py` feeds the encoder either the DR-fitted `normalize`/`mean_subtract`
result or, if no such op is declared, raw pixels scaled to `[0,1]`. A frozen ViT trained on
`[-1,1]`-normalized inputs then receives `[0,1]` inputs — a silent distribution mismatch
that degrades features (and is only partly recoverable by LoRA + the head).

### Diagnosis

The encoder's expected normalization must be supplied **on the data side** as a DR
`normalize` op — but that collides with Gap-1's persistence: a `normalize` transform makes
the image `float`, which the `png_per_record` sink rejects (uint8 only). So the consumer is
pushed toward a config that the two contracts can't jointly satisfy without care:
resize (uint8, sinkable) + normalization (float, not sinkable) + a pretrained encoder that
needs its own stats. Nothing in either recipe surface flags this interaction.

### Recommended fix

- Let the `Encoder` op optionally apply its HF image processor's normalization (and even
  resize) so a pretrained backbone "just works" from uint8 instance pixels, **or**
- Document the required pattern explicitly: declare the encoder's `mean`/`std` as a DR
  `normalize` op whose stats MF applies at load, and define how that coexists with a
  `png_per_record` sink (e.g. sink the pre-normalize uint8 image, store stats separately).

### Mitigation (this deliverable)

Pending a clean resolution, Model 1 trains with MF's default `[0,1]` scaling (no DR
`normalize`), and the result is reported with this normalization caveat noted. Revisit if
accuracy indicates the mismatch is materially hurting the frozen-encoder features.

---

## Gap 3 — PyTorch loader is image-only; no audio / feature-array consumption path

| Field | Value |
|-------|-------|
| Surface | MF PyTorch data-load path |
| Related contract | `DataRefineryDataset._decode` + `_resolve_normalization_steps` (`modelfoundry/plugins/pytorch/data.py`); the loose-coupled DataRefinery binding |
| Sanitized | yes |
| First hit | 2026-06-22 |
| Filed as | [`briefs/modelfoundry-audio-feature-consumption.md`](../briefs/modelfoundry-audio-feature-consumption.md) (paired with the DataRefinery persistence brief) |

### Symptom

Building Model 2 (songbird audio, probabilistic / MC-dropout), the consumer binds
a materialized audio instance to a spectrogram-CNN recipe with
`Inference: {mode: mc_dropout, mc_samples: T}`. The PyTorch loader decodes **every**
record as an image:

```python
# DataRefineryDataset._decode
relative = record.get("image_path")
path = self._dataset_dir / str(relative) if relative else Path(str(record["path"]))
with Image.open(path) as handle:
    array = np.asarray(handle.convert("RGB"), dtype=np.float32)
```

For an audio instance, `path` points at an audio clip (`.ogg`), which
`PIL.Image.open` cannot decode. There is **no** code path that reads windowed
spectrogram feature arrays, decodes audio, or applies the `audio_normalize`
fit-on-train statistics (`_resolve_normalization_steps` recognizes only image
`normalize` / `mean_subtract` on 0–255 pixels).

### Affected contract / abstraction

The PyTorch plugin's loader and normalization resolver are image-specialized
end-to-end (PIL RGB decode, 0–255 units, image stats only). The loose-coupled
DataRefinery binding ("consume `dataset/<split>.jsonl` + sidecars") currently
assumes the image modality; the second real modality (audio) has no model-side
consumer.

### Diagnosis

ModelFoundry's PyTorch feature path has no audio/array branch. Even once the data
side can persist float spectrogram features ([DataRefinery Gap 3](../datarefinery/consumer-gap-analysis.md)),
ModelFoundry needs a loader that reads those arrays and honors the persisted
`audio_normalize` stats rather than decoding RGB pixels. The MC-dropout stochastic
path itself is already implemented and modality-agnostic (`pytorch/stochastic.py`,
verified present) — the gap is purely getting audio features *into* the model. This
is the consuming side's half of the seam.

### Recommended fix

(Full options in the brief.) Preferred: add a feature-array consumption branch —
when the instance exposes per-record arrays (via the paired DR `feature_path`
sink), load them into a `(C, n_mels, n_frames)` tensor and apply the persisted
`audio_normalize` stats, leaving the default image path unchanged. Interim:
document the lossy spectrogram-as-image PNG path. Coordinate with the DataRefinery
persistence fix (paired — neither alone unblocks the consumer).

### Workaround applied

**None — Model 2 build paused.** No model-side workaround exists while the loader
cannot read non-image inputs; the only consumer-side option is the bypass-the-plugin
spectrogram-PNG route flagged in [DataRefinery Gap 3](../datarefinery/consumer-gap-analysis.md),
which the developer declined in favor of treating Model 2 as blocked on the
dependency fix (Story C.c.2).

### Verification

- Binding a materialized audio instance (with persisted spectrogram features) and
  materializing the MC-dropout spectrogram-CNN recipe trains end-to-end, producing
  per-record `predictive_entropy` / `mc_variance` and `ece` over the MC-aggregated
  means; deterministic re-run; round-trips from disk.
- Default single-pass image recipes are unaffected.

