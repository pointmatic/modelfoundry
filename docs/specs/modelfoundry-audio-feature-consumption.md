# Brief: PyTorch loader is image-only — no audio / feature-array consumption path

| Field | Value |
|-------|-------|
| Target repo | ModelFoundry |
| Related spec | [`advanced-and-probabilistic-requirements.md`](../modelfoundry/advanced-and-probabilistic-requirements.md) (R2 MC-dropout probabilistic path — the model that consumes the audio features) |
| Sanitized | yes |
| Date | 2026-06-22 |

> **Paired fix.** This brief and [`datarefinery-audio-feature-persistence.md`](datarefinery-audio-feature-persistence.md)
> are the two halves of one consumer-blocking seam: the data side cannot
> *persist* the computed audio features (companion brief), and the modeling side
> cannot *consume* them (this brief). Neither fix alone unblocks the consumer.

## Symptom

A consumer project wants to train the **probabilistic (MC-dropout) model** on
audio features prepared by the data tool's `audio_classification` plugin. The
model recipe is a spectrogram CNN with active-dropout stochastic inference
(`Inference: {mode: mc_dropout, mc_samples: T}`), bound to a materialized audio
instance. Materialization fails at the data-load step.

The PyTorch loader decodes **every** record as an image:

```python
# DataRefineryDataset._decode (modelfoundry/plugins/pytorch/data.py)
relative = record.get("image_path")
path = self._dataset_dir / str(relative) if relative else Path(str(record["path"]))
with Image.open(path) as handle:
    array = np.asarray(handle.convert("RGB"), dtype=np.float32)
```

For an audio instance, each record's `path` points at an audio clip (e.g.
`.ogg`), which `PIL.Image.open` cannot decode → load error. There is **no** code
path that reads windowed spectrogram feature arrays, decodes audio, or applies
the `audio_normalize` fit-on-train statistics. The normalization resolver
(`_resolve_normalization_steps`) recognizes only the image `normalize` /
`mean_subtract` Transformations on 0–255 pixels.

## Affected contract / abstraction

- The PyTorch plugin's data loader (`DataRefineryDataset._decode`) and its
  normalization-step resolver (`_resolve_normalization_steps`) are
  **image-specialized end-to-end**: PIL RGB decode, 0–255 pixel units, image
  fit-on-train stats only.
- The **loose-coupled DataRefinery binding** — "consume a materialized
  instance's `dataset/<split>.jsonl` + sidecars" — currently assumes the image
  modality. The data tool now ships a second real modality (audio) whose
  features are float spectrogram arrays, with **no consumption counterpart** on
  the modeling side.

## Diagnosis

ModelFoundry's PyTorch feature path has no audio/array branch. The modality the
data tool added has no model-side consumer. Even once the data side can persist
float spectrogram features (companion DataRefinery brief), ModelFoundry needs a
loader that **reads those arrays** — and honors the persisted `audio_normalize`
fit-on-train statistics — rather than decoding RGB pixels. This half is
ModelFoundry's: the consuming side owns the load path. The MC-dropout stochastic
inference itself is already implemented and modality-agnostic; the gap is purely
in getting audio features *into* the model.

## Recommended fix

Behavior-level options (implementation design is ModelFoundry's own tech-spec):

1. **Add a feature-array consumption path to the loader (preferred).** When the
   bound instance exposes per-record feature arrays (the companion DR sink,
   resolved via a `feature_path` relative to `dataset/`), load those arrays into
   the model's input tensor (e.g. a single-channel `(1, n_mels, n_frames)` or
   `(C, n_mels, n_frames)` spectrogram) instead of `Image.open`, and apply the
   persisted `audio_normalize` statistics under the existing fit-on-train
   contract. Default image path unchanged.
2. **Spectrogram-as-image interim.** Document/support consuming a uint8
   spectrogram-PNG instance through the *existing* image path (works today **iff**
   the data side can emit the PNG, per the companion brief's option 3). A
   stopgap — lossy and it doesn't exercise the float-feature contract — but it
   unblocks the common CNN-on-spectrogram pattern with no new loader surface.

**Contract impact.** Additive loader branch; the default image consumption path
and its determinism / round-trip guarantees are unchanged. Coordinate with the
DataRefinery feature-persistence fix — they are a pair, and a consumer needs both
to get a working end-to-end audio path in a single step.

## Verification

- Binding a materialized audio instance (with persisted spectrogram features) and
  materializing a spectrogram-CNN recipe with
  `Inference: {mode: mc_dropout, mc_samples: T}` **trains end-to-end** and
  produces, per evaluated record, a mean-probability prediction plus
  `predictive_entropy` / `mc_variance`; `ece` / `calibration_curve` are computed
  over the MC-aggregated means.
- The run is **deterministic** (same `(recipe, data_instance, seed)` ⇒
  byte-identical metrics) and **round-trips from disk** (a reloaded
  `ModelInstance` reproduces predictions + uncertainty).
- Default single-pass image recipes are **unaffected** (no behavior change for
  the existing CIFAR-scale image path).
