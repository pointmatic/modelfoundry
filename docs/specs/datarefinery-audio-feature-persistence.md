# Brief: audio spectrogram features cannot be persisted for downstream model training

| Field | Value |
|-------|-------|
| Target repo | DataRefinery |
| Related spec | [`audio-classification-requirements.md`](../datarefinery/audio-classification-requirements.md) (R4 spectral featurization, R5 fit-on-train normalization, R7 aggregation key) |
| Sanitized | yes |
| Date | 2026-06-22 |

> **Paired fix.** This brief and [`modelfoundry-audio-feature-consumption.md`](modelfoundry-audio-feature-consumption.md)
> describe the two halves of one consumer-blocking seam: the data side cannot
> *persist* the computed audio features (this brief), and the modeling side
> cannot *consume* them (the companion brief). Neither fix alone unblocks the
> consumer; they must land together (a documented schema/contract coordination).

## Symptom

A consumer project prepares an audio classifier's inputs with the
`audio_classification` plugin and then trains the model in a separate modeling
tool that binds the materialized instance. The data recipe runs the documented
chain — `audio_folder` decode → `window` Generation → `log_mel_spectrogram`
Featurization (`mel`) → fit-on-train `audio_normalize` (`feature`) — and
`materialize` succeeds.

But the materialized `dataset/<split>.jsonl` carries **only metadata**:
`record_id`, `source_record_id`, `window_index`, `label`, `path`, `sample_rate`.
The `sample_array` / `mel` / `feature` arrays the plugin computed are **absent**
— they are in-pipeline only. Attempting to persist them with a `Sinks` entry:

```yaml
Sinks:
  - name: persist_feature
    format: png_per_record
    field: feature            # float32 (n_mels, n_frames)
    stage: post_Featurizations
    path_template: "features/{split}/{record_id}.png"
```

fails at `materialize`:

```
sink 'persist_feature' at stage 'post_Featurizations': format='png_per_record'
expects uint8 on field 'feature'; got float32 — move the sink earlier than
normalize or pick a different field.
```

`png_per_record` is the only sink format that ships; `npy_per_record` / `parquet`
are listed as deferred. So the float spectrogram features the plugin produces
**cannot leave the instance** in any form a downstream model can read.

## Affected contract / abstraction

- The audio Featurization outputs are **in-pipeline only**: per the audio
  plugin's "in-pipeline vs persisted" rule, `sample_array` / `mel` / `feature`
  are never serialized to `dataset/<split>.jsonl`, which carries only the
  binding metadata.
- The `Sinks` contract's only writer is `write_png_per_record`
  (`datarefinery/pipeline/sinks/writers.py`), which requires **uint8 HxW or
  HxWxC** and raises `MaterializeError` on any other dtype. `npy_per_record`
  and `parquet` array sinks are documented as deferred.
- The instance's on-disk dataset layout (`dataset/<split>.jsonl` + any sink
  sidecars) is the **cross-repo consumption surface** a modeling tool binds to.

## Diagnosis

The audio plugin faithfully *computes* windowed spectrogram features, but there
is **no serialization path for a float feature array**. `png_per_record` is
uint8-by-design (it targets image pixels); the array sink formats that would fit
a `(n_mels, n_frames)` `float32` spectrogram are deferred. Consequently a
downstream modeling repo has no way to read the prepared features from a
materialized audio instance — the modality boundary the audio plugin proves on
the *data* side never reaches a *model*. This half is DataRefinery's: the
producing side owns feature persistence.

## Recommended fix

Behavior-level options (implementation design is DataRefinery's own tech-spec):

1. **Ship an array sink format (`npy_per_record`, preferred).** Persist the
   named float field per record under the instance (e.g.
   `features/<split>/<record_id>.npy`) and rewrite a `feature_path` (relative to
   `dataset/`), mirroring how `png_per_record` rewrites `image_path`. Smallest
   change, reuses the existing sink mechanism and stage model, and keeps the
   "arrays are in-pipeline" convention intact for the JSONL.
2. **Optional inline serialization** of the array into the JSONL (npy-bytes /
   base64). Simpler to wire but bloats the JSONL and breaks the in-pipeline-array
   convention — not preferred.
3. **A uint8-quantization sink mode** (spectrogram → image) so the
   spectrogram-as-image technique works through the existing PNG path. Lossy
   (quantization + range clipping), but unblocks the common CNN-on-spectrogram
   pattern with minimal new surface.

**Contract impact.** A new sink format is additive. The sink's output is part of
instance content, so cache identity must cover it exactly as `png_per_record`
does today (same recipe + inputs + seed ⇒ byte-identical features; a changed
featurization invalidates). Determinism and the clip↔window grouping
(`source_record_id`) are unaffected. No `schema_version` bump if purely additive
— but coordinate the rollout with the companion ModelFoundry fix so a consumer
gets a working end-to-end path in one step.

## Verification

- An audio recipe with a `Sinks` entry persisting `feature` as `npy_per_record`
  **materializes without error**; each record gains a `feature_path` resolving to
  an on-disk array of shape `(n_mels, n_frames)`.
- Re-running the same recipe + inputs + seed yields a **byte-identical** instance
  and a cache **hit**; a changed `log_mel_spectrogram` / `audio_normalize`
  parameter yields a cache **miss** and different feature bytes.
- A downstream reader loads the persisted arrays and reconstructs the windowed
  feature set, regrouping windows to clips by `source_record_id` (R7).
- Existing image recipes and the `png_per_record` sink are unaffected.
