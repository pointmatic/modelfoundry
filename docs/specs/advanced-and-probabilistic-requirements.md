# Requirement Spec: Advanced (Pretrained-Encoder/LoRA) and Probabilistic (MC-Dropout) Modeling Paths

**Target repo:** ModelFoundry
**Status:** Proposed (consumer requirement)
**Type:** Activate deferred architecture path + extend inference/evaluation contracts

This document is written to drop into ModelFoundry's own document chain. It states *what* a consumer project needs from the modeling side and *which existing contracts* that touches — not *how* to implement it. Terminology follows ModelFoundry's `concept.md` / `features.md` / `tech-spec.md`.

---

## Context

A consumer project is building two classifiers on the same modeling grammar:

- **Model 1 (advanced method)** — an image classifier built by **transfer learning**: a pretrained encoder fine-tuned (optionally via LoRA) with a fresh classification head.
- **Model 2 (probabilistic method)** — an audio classifier (spectrogram CNN) that produces **calibrated predictive uncertainty** via **MC-dropout**: dropout kept active at inference, T stochastic forward passes, aggregated to mean class probabilities plus an uncertainty estimate.

Both datasets are class-imbalanced, so evaluation must be imbalance-aware rather than relying on plain accuracy.

The relevant ModelFoundry surfaces already exist in contract but not in active implementation:

- The **pretrained-encoder + LoRA path** (`Encoder` / `LoRA` / `Pooling` / `Head` architecture ops) is **contract-named but deferred**, gated behind a deferred `[huggingface]` extra.
- The **inference path is single-pass only today** — `ModelInstance.predict()` / `.predict_proba()` return point estimates; there is no active-dropout sampling or uncertainty surface.
- The **imbalance-aware metric vocabulary already exists** (`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `ece`, `calibration_curve`) and `cross_entropy_class_weighted` loss is available; this requirement mainly elevates them to first-class use and confirms they cover the consumer's needs.

This spec asks ModelFoundry to (R1) activate the deferred pretrained-encoder/LoRA path, (R2) add an MC-dropout stochastic-inference path with a predictive-uncertainty metric, and (R3) confirm/round out imbalance-aware evaluation — all on the existing PyTorch plugin, under the existing `Plugin` protocol and `ModelInstance` contract.

---

## Requirements

Behavior-level, numbered. Each is a capability the recipe author must be able to express and the materialized `ModelInstance` must honor.

### R1 — Activate the pretrained-encoder / LoRA path (advanced method)

The PyTorch plugin SHALL implement the already-declared optional `Architecture` operations behind the `[huggingface]` extra:

- **R1.1** — `Encoder` (`source: huggingface`, `id: <model id>`, `frozen: bool`): instantiate a pretrained encoder by id; honor `frozen` to freeze/unfreeze encoder weights.
- **R1.2** — `LoRA` (`rank`, `alpha`, `dropout`, `target_modules`): apply low-rank adapters to the named modules for parameter-efficient fine-tuning.
- **R1.3** — `Pooling` (`type: attention | mean | max`, `hidden_dim`) and classification `Head` (`type: mlp`, `hidden_dims`, `num_classes`, `id2label`): compose the head over pooled encoder features.
- **R1.4** — The path SHALL be **extras-gated** per the existing `OperationSpec.requires_extras` mechanism: plugins remain discoverable without the extra installed; a recipe that references these ops without `[huggingface]` installed fails at materialize time (not load/validate time) with a clear extras-install pointer.
- **R1.5** — Pretrained weights SHALL load through a mechanism that supports an **offline warm cache** (a pre-populated local weights cache), so materialization is reproducible and does not require live network access at run time.

### R2 — MC-dropout stochastic-inference path (probabilistic method)

The PyTorch plugin and the `ModelInstance` contract SHALL support stochastic inference with dropout active:

- **R2.1** — A declared inference mode in which `Dropout` layers remain **active at inference** and the model runs **T stochastic forward passes** (author-declared T; the consumer targets T≈20–50).
- **R2.2** — Aggregation of the T passes into (a) **mean class probabilities** used as the point prediction and (b) a **predictive-uncertainty estimate** (predictive entropy and/or variance across passes).
- **R2.3** — A surface on `ModelInstance` to obtain both the mean prediction and the uncertainty estimate from disk alone (e.g., a stochastic-predict accessor and/or persisted per-record uncertainty in `evaluation/predictions.parquet`), without re-deriving from an external config.
- **R2.4** — The T forward passes SHALL be **seeded and reproducible**: same `(recipe, data_instance, seed, variant)` yields byte-identical mean probabilities and uncertainty (subject to the existing plugin-documented determinism caveats). Dropout RNG follows the existing `derive_seed(master_seed, "dropout")` discipline, extended deterministically across the T passes.
- **R2.5** — A **predictive-uncertainty metric** SHALL be available in the `Evaluation` stage output (e.g., mean predictive entropy per split), alongside the existing calibration outputs, so uncertainty quality is reportable.

### R3 — Imbalance-aware evaluation

- **R3.1** — The `Evaluation` stage SHALL, as first-class recipe-selectable metrics, produce the existing imbalance-aware set — `macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `confusion_matrix` — for every split, not plain accuracy alone.
- **R3.2** — Calibration outputs (`ece`, `calibration_curve`) SHALL be produced for the probabilistic model and SHALL be computed over the MC-aggregated mean probabilities (R2.2), so calibration reflects the stochastic predictor actually deployed.
- **R3.3** — The existing `cross_entropy_class_weighted` loss (`weight_source: train | train_inverse_frequency | effective_number`) SHALL remain usable for both models, with class weights fit on the train split only and persisted for audit, preserving the fit-on-train discipline.

---

## Contract impact

Which existing ModelFoundry invariants/contracts this touches; the claim that none are silently violated (the consumer's VT-3 gate cross-checks this against the current contracts).

- **Stage model (unchanged).** All work maps onto existing stages — `Architecture`, `Optimization`, `Training`, `Evaluation`, `OutputExpectations`, `Visualizations`, `Persistence`, `Reporting`. No new stage is introduced.
- **Plugin protocol (extended, additively).** R1 implements already-declared `Architecture` ops (no new protocol method). R2 is the one genuine extension: stochastic inference needs a way to request T active-dropout passes and surface aggregated uncertainty. This SHOULD be additive to the `Plugin` predict surface / `ModelInstance` API so existing single-pass `predict()` / `predict_proba()` semantics are preserved by default (T = 1, dropout inactive) — see Open Questions for the exact shape.
- **Extras gating (preserved).** R1 uses the existing `OperationSpec.requires_extras = ("huggingface",)` mechanism and the existing "discoverable without extras; execution-time error with install pointer" rule. Activating the path is the implementation of an already-contracted surface, not a new contract.
- **Determinism / seeding (preserved and extended).** R2 extends the existing seeded-dropout contract (`derive_seed(master_seed, "dropout")`) across T passes; the `(recipe, data_instance, seed, variant)` → byte-identical `ModelInstance` guarantee must continue to hold for stochastic inference, subject to documented caveats (QR-3).
- **Round-trip-from-disk (preserved).** The pretrained/LoRA architecture must serialize to `model/architecture.json` + weights such that `ModelInstance.load(path).predict(X)` rebuilds from disk alone. MC-dropout aggregation and uncertainty must likewise be reconstructable from the persisted instance without an external config.
- **Evaluation outputs (unchanged shape).** R3 uses the existing metric vocabulary and the existing `evaluation/` artifact layout (`metrics.json`, `confusion_matrix.npz`, `calibration.parquet`, `predictions.parquet`). The predictive-uncertainty metric (R2.5) and per-record uncertainty (R2.3) extend these files additively.
- **Optimization stage (unaffected).** No change requested to the Optuna-backed `Optimization` contract; a later consumer story builds on it as-is.
- **Cross-repo / loose-coupled DataRefinery binding (preserved).** ModelFoundry continues to consume a materialized `DataRefineryInstance` (splits, label schema, on-disk dataset layout, per-record-seed stamps, manifest) under the existing **loose-coupled** rule: the upstream instance's `recipe_hash` does not participate in the ModelFoundry recipe's cache identity, and re-materializing upstream does not auto-invalidate downstream. Nothing here requests tight coupling. The audio features this consumer needs (windowed spectrogram features, fit-on-train normalization) are produced on the **DataRefinery** side per the companion audio-classification requirement; ModelFoundry only consumes the resulting instance.

---

## Acceptance criteria

Testable, for ModelFoundry to verify (phrased in the existing acceptance-criteria / contract-test conventions: `ModelInstance`, `materialize()`, named stages, the error hierarchy, and the unit / integration / CLI / plugin-contract / Hypothesis taxonomy).

1. A recipe declaring an `Encoder` + `LoRA` + `Pooling` + `Head` architecture materializes a `ModelInstance` end-to-end via `materialize()` when `[huggingface]` is installed; with the extra absent, materialization raises the extras-gated error with an install pointer (and recipe load/validate still succeed against the in-tree vocabulary).
2. Pretrained-weight loading succeeds from a pre-populated offline warm cache with no network access; the run is reproducible.
3. A recipe declaring MC-dropout inference with T passes produces, for each evaluated record, a mean-probability prediction and an uncertainty estimate (predictive entropy/variance); both are recoverable from the persisted instance via the `ModelInstance` API alone.
4. Stochastic inference is deterministic: re-running the same `(recipe, data_instance, seed, variant)` yields byte-identical mean probabilities, uncertainty values, and metrics (excluding wall-clock fields), subject to documented caveats.
5. Default single-pass `predict()` / `predict_proba()` behavior is unchanged for recipes that do not request stochastic inference (no active dropout, point estimates).
6. `evaluation/metrics.json` contains `macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, and `confusion_matrix` per split; for the probabilistic model, `ece` / `calibration_curve` are computed over the MC-aggregated mean probabilities, and a predictive-uncertainty metric is present.
7. `cross_entropy_class_weighted` fits class weights on the train split only and persists them (`training/class_weights.json`); validation rejects fitting on non-train splits.
8. Plugin-contract tests assert the new architecture ops' `OperationSpec`s (including `requires_extras`) and any added stochastic-inference surface; Hypothesis tests confirm cache-identity invariants still hold (cosmetic recipe edits → no hash change; semantic edits → hash change) with the new ops present.
9. A round-trip test loads a persisted pretrained/LoRA `ModelInstance` and a persisted MC-dropout `ModelInstance` from disk and reproduces predictions/uncertainty without an external config object.

---

## Open questions

1. **Shape of the stochastic-inference surface (primary).** Should T-pass MC-dropout be expressed as (a) new `ModelInstance` / plugin methods (e.g., `predict_proba_mc(X, n_passes)`), (b) an optional `n_passes` parameter threaded through the existing `predict_proba()` with an active-dropout flag, or (c) a declared `Evaluation`/inference-mode recipe block that the plugin honors internally? The consumer's preference is the least invasive option that keeps default single-pass semantics untouched (R2 / criterion 5) and surfaces uncertainty as a first-class, persisted artifact.
2. **Where uncertainty is persisted.** Per-record uncertainty in `evaluation/predictions.parquet` vs. a dedicated `evaluation/uncertainty.parquet` vs. a scalar summary in `metrics.json` — or some combination. Which fits the existing artifact conventions best?
3. **LoRA serialization.** Should `model/weights/` persist merged weights, base + adapter deltas separately, or both? This affects round-trip fidelity (criterion 9) and instance size.
4. **Predictive-uncertainty metric choice.** Is mean predictive entropy sufficient as the headline uncertainty metric, or is a calibration-of-uncertainty measure (e.g., correlation of uncertainty with error) also wanted in v1?
5. **Encoder-source breadth.** Is `source: huggingface` the only pretrained source in scope for activation now, or should the path be authored to admit other sources later without a contract change?
