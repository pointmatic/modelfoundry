# Subphase H-1 Plan: Advanced (Pretrained-Encoder/LoRA) & Probabilistic (MC-Dropout) Modeling Paths

**Mode:** plan_phase · **Phase:** H · **Subphase:** H-1 · **Status:** Draft for approval

Source requirement: [`advanced-and-probabilistic-requirements.md`](advanced-and-probabilistic-requirements.md) (R1/R2/R3).
Scope decision (developer, 2026-06-21): **full spec — R1 + R2 + R3** under Subphase H-1.

> **Proposed subphase retitle.** The current heading `## Subphase H-1: Audio Classification` is too narrow — R1 is an *image* classifier (pretrained encoder/LoRA). Recommend retitling to **`## Subphase H-1: Advanced & Probabilistic Modeling Paths`** so the heading matches the bundled scope. Flagged here rather than silently renamed.

---

## 1. Gap analysis — contract vs. active implementation

| Surface | In contract today | Active today | Gap (this subphase) |
|---|---|---|---|
| **R1** `Encoder`/`LoRA`/`Pooling`/`Head` ops | ✅ registered in `ARCHITECTURE_OPERATIONS` with `requires_extras=("huggingface",)` ([architecture.py:188](src/modelfoundry/plugins/pytorch/architecture.py#L188)) | ❌ `_require_huggingface()` raises `NotImplementedError` ([architecture.py:475](src/modelfoundry/plugins/pytorch/architecture.py#L475)) | Implement the build path; honor `frozen`; offline warm cache |
| **R1** `[huggingface]` extra | ✅ declared (`transformers`/`peft`/`evaluate`, [pyproject.toml:55](pyproject.toml#L55)) | ❌ no plugin code imports it | Wire transformers + peft; keep extras-gating (discoverable without extra; execution-time error w/ install pointer) |
| **R2** stochastic inference | ❌ none | ❌ `_forward_proba()` is `.eval()` + `no_grad` single-pass ([persistence.py:123](src/modelfoundry/plugins/pytorch/persistence.py#L123)) | New: active-dropout, T passes, seeded; aggregate to mean probs + uncertainty; persist; accessor |
| **R2** predictive-uncertainty metric | ❌ none | ❌ | Add to `Evaluation` output (mean predictive entropy per split) |
| **R3** imbalance metrics | ✅ implemented: `macro_f1`, `per_class_*`, `ece`, `calibration_curve` ([evaluation.py:145](src/modelfoundry/plugins/pytorch/evaluation.py#L145)) | ✅ recipe-selectable | Elevate to first-class defaults; confirm coverage; compute `ece`/calibration over MC mean probs (R3.2) |
| **R3** `cross_entropy_class_weighted` | ✅ fits on train, persists `training/class_weights.json` ([trainer.py:309](src/modelfoundry/plugins/pytorch/trainer.py#L309)) | ✅ | Confirm usable for both models; keep fit-on-train discipline |

**Net:** R1 is "activate a stubbed-but-contracted path" (the hard new boundary). R2 is the one genuine protocol/`ModelInstance` extension. R3 is mostly elevation + one new computation site (calibration over MC means).

---

## 2. Feature requirements (mapped to the spec)

- **R1 — advanced path.** A recipe declaring `Encoder` + `LoRA` + `Pooling` + `Head` materializes end-to-end with `[huggingface]` installed; without it, materialize-time extras error with install pointer (load/validate still succeed). Pretrained weights load from an **offline warm cache** (no run-time network). Round-trips from disk (criterion 9).
- **R2 — probabilistic path.** A declared inference mode keeps `Dropout` active, runs **T** seeded forward passes, aggregates to (a) mean class probabilities (the point prediction) and (b) a predictive-uncertainty estimate. Both recoverable from the persisted instance via `ModelInstance` API alone. **Default single-pass `predict()`/`predict_proba()` semantics unchanged** when stochastic inference is not requested (criterion 5). Deterministic across T passes (criterion 4).
- **R3 — imbalance-aware eval.** `macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `confusion_matrix` per split as first-class; `ece`/`calibration_curve` over MC-aggregated mean probs for the probabilistic model; class-weighted loss fit-on-train preserved.

---

## 3. Technical changes (under the existing stage model — no new stage)

- **Architecture build path** (`plugins/pytorch/architecture.py`): replace the `NotImplementedError` stub in `_compose()` with the real Encoder→(LoRA)→Pooling→Head composition; lazy-import `transformers`/`peft` behind the existing `_require_huggingface()` gate; honor `frozen`. Offline warm cache via HF's `HF_HOME`/`local_files_only` (cache management lives in plugin docs, not `project-essentials.md`, per the Future note).
- **Stochastic inference surface** — see Open-Question default Q1 below. Touches the `Plugin` protocol ([base.py:107](src/modelfoundry/plugins/base.py#L107)), `ModelInstance` ([core/instance.py](src/modelfoundry/core/instance.py)), and the PyTorch `_forward_proba()` path. Additive: existing methods keep single-pass semantics.
- **Determinism/seeding** (`pipeline/seeding.py`): extend the seeded-dropout discipline across T passes — derive a per-pass seed from `derive_seed(master_seed, "dropout", pass_index_bytes)` so the T-pass sequence is reproducible (preserves QR-3; the four determinism invariants in `project-essentials.md` hold).
- **Evaluation** (`plugins/pytorch/evaluation.py`): add a predictive-uncertainty metric (mean predictive entropy per split) to `_compute_metrics`; route the probabilistic model's `ece`/`calibration_curve` through the MC-aggregated mean probs; extend `predictions.parquet` with per-record uncertainty columns (additive).
- **LoRA serialization** — see Open-Question default Q3; `save_model`/`load_model` extended so a LoRA instance round-trips from disk alone.

### ⚠ Cache-identity / schema note (load-bearing)

Per `project-essentials.md` "Cache identity is the reproducibility contract": adding a **new recipe field** for the stochastic-inference mode shifts the canonical bytes of *every existing recipe that omits it* (canonical form includes all pydantic defaults), invalidating every cached ModelInstance.

- **Pre-production (current, OR-9):** acceptable — **release-note only, no `schema_version` bump required**. Users re-materialize. The R1 ops are already in the registered vocabulary, so activating them is *not* itself a vocabulary change.
- A canonical-hash pinning test (if present) will need a consciously-reviewed update when the field lands.
- **Not requested / refused:** any tight-coupling of the bound DataRefinery `recipe_hash` into cache identity (FR-26 stays deferred). Audio spectrogram features are produced **upstream in DataRefinery**, consumed read-only here.

---

## 4. Open-Questions — recommended defaults (settle at the approval gate)

| # | Question | Recommended default | Rationale |
|---|---|---|---|
| **Q1** | Shape of stochastic-inference surface | **(c) recipe-declared inference block** honored by the plugin internally, **plus** an additive `ModelInstance` accessor (e.g. `predict_proba_mc`) reading from disk | Recipe-as-truth: MC-dropout changes the materialized instance & its metrics, so it's recipe *semantics*, not a runtime call param. Keeps default single-pass `predict*()` untouched (criterion 5). |
| **Q2** | Where uncertainty is persisted | **Per-record columns in `evaluation/predictions.parquet`** + a **scalar summary** (mean predictive entropy/split) in `metrics.json` | Additive to existing artifacts; no new file; matches the spec's "extend additively." |
| **Q3** | LoRA serialization | **Base + adapter deltas separately** (peft native adapter save); base supplied by the offline warm cache | Smaller instance, clean round-trip. Decide concretely in the H.i spike. |
| **Q4** | Headline uncertainty metric | **Mean predictive entropy** for v1; defer uncertainty-vs-error correlation | Single, interpretable, reportable alongside `ece`. |
| **Q5** | Encoder-source breadth | Implement **`source: huggingface` only**; `source` stays a dispatch point so other sources add later without a contract change | `source` is already a param; no vocabulary change needed to extend. |

---

## 5. Proposed story breakdown (Step 6 detail — for shape review)

Story letters continue from H.h. Phase H is **per-story bumps**; feature stories take a **minor**, spike/test/doc stories carry **no bump**. Versions provisional.

**R1 — advanced path**
- **H.i — Integration spike: `[huggingface]` boundary.** Load a pretrained encoder from an *offline warm cache*, apply a peft LoRA adapter, run a forward pass. Deliverable: documented decisions for Q3 (LoRA serialization) and Q5 (source breadth) + a viable-path verdict. *Throwaway; no bump.* (New integration boundary ⇒ integration spike per Step 6.)
- **H.j — Activate Encoder + Pooling + Head composition** (R1.1, R1.3, R1.4, R1.5): real `_compose()` build path, extras-gated, offline warm cache, `frozen` honored. *Minor.*
- **H.k — Activate LoRA adapters + serialization** (R1.2) per the spike decision; round-trips from disk. *Minor.*
- **H.l — R1 contract/round-trip/extras-gating tests** (criteria 1, 2, 8, 9): plugin-contract assertions for the now-active ops, offline-cache reproducibility, disk round-trip. *No bump.*

**R2 — probabilistic path**
- **H.m — Stochastic-inference surface** (R2.1, R2.4): recipe-declared inference block (Q1), active-dropout, T seeded passes via `derive_seed(…, "dropout", pass_idx)`; default single-pass preserved. *Minor.*
- **H.n — Aggregation + uncertainty persistence** (R2.2, R2.3): mean probs + predictive entropy/variance; persist to `predictions.parquet` (Q2); `ModelInstance` accessor. *Minor (or folded into H.m).*
- **H.o — Predictive-uncertainty metric + MC-calibration** (R2.5, R3.2): mean predictive entropy in `metrics.json`; `ece`/`calibration_curve` over MC means. *Minor.*

**R3 — imbalance-aware eval**
- **H.p — First-class imbalance defaults + class-weighted-loss confirmation + cache-identity Hypothesis tests** (R3.1, R3.3, criterion 8): elevate imbalance metric defaults; confirm fit-on-train `class_weights.json`; Hypothesis tests that cache identity holds with the new ops/field (cosmetic edit → no hash change; semantic → change). *No bump.*

**Optional closer**
- **H.q — Consumer-facing example recipes + docs** for both paths (advanced image + probabilistic audio), referencing fixtures. *No bump.*

> Size note: this is a large subphase (~8–9 stories across two new paths). Alternative if you prefer tighter bundles: split into **H-1 (R2+R3, audio/probabilistic)** and a later **H-2 (R1, advanced/LoRA)**. Recommend keeping it as one H-1 per your scope decision, but the option stands.

---

## 6. Out of scope (to negotiate item-by-item — Step 4)

1. **Non-HuggingFace encoder sources** (Q5) — path admits them later without a contract change; not implemented now.
2. **Uncertainty-vs-error / calibration-of-uncertainty metric** (Q4) — mean predictive entropy only in v1.
3. **Merged-weights LoRA serialization** — if Q3 lands on deltas-only, the merged-weights option is deferred.
4. **`[keras]` plugin** — separate Future item; ECE/calibration sharing noted there, not here.
5. **Tight-coupled DataRefinery binding (FR-26)** — stays deferred behind a future `schema_version` bump.
6. **Upstream audio feature engineering** (spectrograms, fit-on-train normalization) — produced in **DataRefinery**, consumed read-only here.
7. **Parallel Optuna trials / search-space op-choice** — unaffected; remain in Future.
8. **The consumer's real datasets** — ModelFoundry ships recipes/fixtures; the consumer binds their own materialized DataRefinery instance.
