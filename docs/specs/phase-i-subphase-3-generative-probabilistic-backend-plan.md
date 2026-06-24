# Subphase I-3 Plan — Generative-Probabilistic Backend (per-class GMM / HMM)

> **Mode:** `plan_phase` (pre-1.0). **Structure:** Subphase **I-3** under the existing
> `## Phase I: Segmented Recipe Architecture`. Stories continue monotonically from
> the phase's last story **I.y** → **I.z, I.aa, I.ab, …** (base-26 sub-letters; story
> letters reset only at a phase boundary, never a subphase boundary).
>
> **Multi-release exception.** Phase I already shipped v0.16.0 → v0.19.0 across Subphases
> I-1 / I-2. Subphase I-3 is a follow-on subphase that ships its own release tag
> (**→ v0.20.0**, a minor — a new model paradigm + the optional-sections schema cleanup).
> This is the documented Version-Cadence multi-release exception (`_phase-letters.md`
> § Subphases): the subphase's last code story owns the bump. **Multi-release fallback:**
> if the `hmmlearn` integration spike (I.aa) surfaces friction, the HMM half (I.ae + its
> recipe/test) may slip to a follow-on **v0.21.0**, shipping the proven GMM half at v0.20.0
> first — an explicit, documented use of the multi-release-subphase exception.
>
> **Scope note (theme distinctness).** A generative-probabilistic backend is a new model
> paradigm and is broader than Phase I's "Segmented Recipe Architecture" theme — but it
> continues the consumer-gap-driven, pre-1.0 follow-on pattern of I-1 (audio consumption)
> and I-2 (feature-code reconciliation), and is planned as a subphase at the developer's
> direction. If a standalone Phase J identity is later preferred, that is a `plan_phase`
> re-scoping decision, not an in-subphase one.

This subphase delivers ModelFoundry's first **generative-probabilistic** classifier backend,
closing **Gap 2** of [`consumer-gap-analysis2.md`](consumer-gap-analysis2.md): every shipped
backend (`pytorch` / `sklearn` / `random`) is a **discriminative** classifier, so a *pure /
classical generative* probabilistic model — a **per-class Gaussian Mixture Model**, or a
**Hidden Markov Model** for temporal structure — cannot be authored. The generative model is
the **classical-vs-Bayesian contrasting benchmark** for the audio classifier: scored on the
*same* held-out clips and clip-level aggregation as the MC-dropout spectrogram CNN, contrasting
a classical generative model against a modern discriminative BNN on **accuracy and calibration**.

The inputs already exist — the data side persists float `mel`/MFCC frame arrays (the
`feature_path` `.npy` sidecar, round-1 Gap 3 / Subphase I-1); a generative backend reads the
same per-window feature arrays the CNN consumes. **Only the model backend is missing.**

---

## 1. Gap analysis — what exists vs. what's needed

| Area | Exists today | Needed |
|------|--------------|--------|
| **Backend set** | `pytorch` / `sklearn` (`mlp_classifier`/`dummy_classifier`) / `random` — all **discriminative** | A **generative** classifier: per-class density fit + Bayes-rule prediction (GMM now; HMM for temporal structure) |
| **Architecture surface** | sklearn `Architecture` is a runtime-validated `dict[str, Any]`; new types are plugin-local ([sklearn/plugin.py](../../src/modelfoundry/plugins/sklearn/plugin.py) `_validate_architecture`) | A `gmm_classifier` (and `hmm_classifier`) arch type + params model (`n_components`, `covariance_type`, …) |
| **Prediction surface** | `model.predict_proba(x)` consumed generically by the sklearn evaluator | A wrapper exposing `predict_proba` = softmax over per-class `log p(x\|class) + log p(class)` (Bayes' rule); `GaussianMixture` has only `score_samples`, so the wrapper is custom |
| **Feature consumption** | sklearn MLP flattens the **whole** array to one vector ([sklearn/data.py](../../src/modelfoundry/plugins/sklearn/data.py) `feature_matrix`) | A **frame-level** adapter — treat each `n_mels`-vector **frame** as a sample, fit `p(frame\|class)`, score a clip by summing frame log-likelihoods (textbook GMM/HMM over MFCC frames, **not** the flattened-spectrogram path) |
| **Clip-level aggregation** | Implemented **only** on the PyTorch evaluator ([pytorch/aggregation.py](../../src/modelfoundry/plugins/pytorch/aggregation.py)); the sklearn `run_evaluation` **ignores** `window_aggregation` (explicit comment, [sklearn/plugin.py:248-269](../../src/modelfoundry/plugins/sklearn/plugin.py#L248)) | Window→clip aggregation (`mean`/`logit_average`/`majority_vote` by `source_record_id`) on the **generative/sklearn** evaluator, with dangling-key refusal parity |
| **Loss/Optimizer schema** | `ModelRecipe.Loss` / `Optimizer` are **required** ([recipe/models.py:222-223](../../src/modelfoundry/recipe/models.py#L222)); baselines register nominal no-op ops (schema-theater, e.g. `random`'s `_RecognizedNoOpParams`) | Make `Loss`/`Optimizer` `\| None = None` (the deferred Gap A / Option B cleanup) so a generative model omits them **honestly** — confirmed **not** cache-invalidating (see §6) |
| **HMM dependency** | none | `hmmlearn` behind a new packaging **extra**, gated like `[huggingface]` / `[audio]`; a **new integration boundary** ⇒ integration spike (I.aa) |

**What rides the existing contract unchanged** (verified): the sklearn evaluator is already
generic (`predict_proba`-based, no gradient/epoch loop), so metrics / calibration / ECE /
confusion-matrix consume the Bayes posteriors with no change; `run_optimization` stays
`NotImplementedError` (generative backends have **no HPO**, inherited).

---

## 2. The contract this subphase binds against (load-bearing facts)

- **Generative prediction is likelihood-based.** The wrapper computes per-class
  `log p(x|class)` (GMM: sum of frame `score_samples`; HMM: forward log-likelihood), adds
  `log p(class)` (class priors), and returns `predict`/`predict_proba` via Bayes' rule
  (softmax over the per-class log-evidence). It must **not** emit logits (the sklearn
  evaluator consumes `predict_proba` directly, not a model forward pass).
- **Frame-level consumption.** A clip's `(n_mels, n_frames)` array is consumed **frame-wise**
  (`n_frames` samples of dimension `n_mels`), not flattened to one vector. The data adapter
  is generative-specific and distinct from `feature_matrix`'s whole-array flatten.
- **Clip aggregation reuses the I-1 contract.** Window records carry `source_record_id` +
  `window_index`; clip-level results regroup by `source_record_id`; a window resolving to no
  clip is **refused** (parity with the PyTorch `verify_window_integrity` path / validator
  check 23). The aggregation math (`mean`/`logit_average`/`majority_vote`) is plugin-agnostic.
- **Determinism (four invariants) holds.** EM (GMM) and Baum-Welch (HMM) inits are **seeded**
  (`derive_seed(seed, "weight_init")` → estimator `random_state`); the path runs **offline**;
  byte-identity is asserted (I.af). `num_workers`/Optuna/AMP invariants are N/A or unchanged.
- **Optional Loss/Optimizer is byte-neutral.** Making them `| None = None` must leave the
  canonical bytes of every existing recipe that authors them **identical** (sparse-omit only
  when `None`, mirroring `WindowAggregation`'s I.o wiring). A canonical-hash pin test guards it.
- **Loose coupling preserved.** The generative backend consumes the bound DR audio instance
  **read-only**; it never re-hashes the instance and never writes into DR's cache tree.

---

## 3. Feature / fix requirements (mini-features.md)

Folded into `features.md` by the doc story (I.ag):

- **FR-GEN-1 — Generative-probabilistic classifier backend.** ModelFoundry can author a
  per-class generative classifier that fits a class-conditional density on the `train` split
  (seeded) and classifies by maximum class-conditional log-likelihood + log priors (Bayes'
  rule), exposing posteriors via `predict_proba`. Two architectures ship: **`gmm_classifier`**
  (sklearn `GaussianMixture` per class) and **`hmm_classifier`** (`hmmlearn` per class, behind
  the `[hmm]` extra), both consuming MFCC/mel frames frame-wise.
- **FR-GEN-2 — Clip-level aggregation on the generative path.** The generative evaluator
  regroups window-level predictions by `source_record_id` and applies the recipe-declared
  `WindowAggregation` policy, with dangling-key refusal — so a generative model is scored
  clip-level head-to-head with the discriminative CNN on identical splits.
- **FR-GEN-3 — Reproducibility parity.** A generative materialization is byte-deterministic
  and round-trips from disk (QR-3 / FR-25 unchanged) — the seeded EM/Baum-Welch fit reproduces.
- **FR-SCHEMA-1 — Optional `Loss`/`Optimizer` sections.** `Loss` and `Optimizer` become
  `| None = None`; `validate` checks only the sections present; a recipe for a model with no
  loss/optimizer (a generative density model) **omits** them rather than declaring nominal
  no-op ops. Byte-neutral for existing recipes (FR-4 unchanged for them).

**No-implicit-defaults discipline.** The new architecture params (`n_components`,
`covariance_type`, HMM `n_states`/topology) are **author-required** and scaffolder-emitted.
Making `Loss`/`Optimizer` optional is a *mode-selecting* change (absent ⇒ "no loss/optimizer"),
its absent⇒behavior mapping part of the versioned segment contract — **not** a value-default.

---

## 4. Technical changes (mini-tech-spec) & story breakdown

Each story = one coherent unit → one commit. Sequence and IDs continue from **I.y**.

### I.z — Generative-backend design pass *(design; deliverable = settled design note)*
Append a "Design Decisions" section to this plan settling the forks the audit surfaced:
- **Plugin topology** — GMM on the existing `sklearn` plugin (smallest reuse, no new dep) vs.
  a **new shared `generative` plugin** hosting GMM + HMM (so the Bayes wrapper + frame adapter
  + clip aggregation are written once). Recommendation to settle here, leaning shared-generative.
- **Recipe surface** — `gmm_classifier` / `hmm_classifier` arch params; class-prior policy
  (uniform vs. empirical-from-train); the frame-level data-adapter shape.
- **Bayes wrapper** — `predict`/`predict_proba` from per-class log-evidence; numerically
  stable softmax; joblib round-trip shape.
- **Clip aggregation placement** on the generative evaluator (reuse vs. port the I-1 math).
- **Optional Loss/Optimizer schema** — the `| None` + sparse-omit shape, the validator-check
  adaptation list, and the byte-neutrality guard.
- **Determinism plan** for EM/Baum-Welch seeding. **No code** beyond the note.

### I.aa — Integration spike: `hmmlearn` *(integration spike; time-boxed, throwaway)*
De-risk the **new integration boundary** before committing the HMM backend. Throwaway probe:
does `hmmlearn` install behind a `[hmm]` extra; fit a per-class HMM on frame sequences; classify
by **forward log-likelihood + Bayes**; **persist + round-trip** (joblib) and reproduce
**byte-identically** under a seeded fit; run **offline**? Deliverable = a documented **go/no-go**
+ the persistence/determinism pattern (or a fallback: hand-rolled HMM / defer HMM to v0.21.0).
Gates I.ae.

### I.ab — Optional `Loss`/`Optimizer` sections (schema foundation) *(code)*
Make `ModelRecipe.Loss`/`Optimizer` `| None = None` ([recipe/models.py:222](../../src/modelfoundry/recipe/models.py#L222));
adapt `validate` to check only present sections (check 3 `section_ops_registered`, check 6
schedule/early-stopping monitors, check 17 op-params — skip when the section is `None`);
`recipe/sections.py::iter_op_sections` skips `None` sections; **sparse-omit `None` Loss/Optimizer
in [recipe/canonical.py](../../src/modelfoundry/recipe/canonical.py)** so existing recipes that
author them are **byte-identical** (canonical-hash pin test); update fixtures + the `init`
scaffolder to omit them when the plugin has no concept of them. Foundation for the generative
recipes. **Not cache-invalidating** (§6).

### I.ac — `gmm_classifier` generative backend *(code)*
The per-class GMM: a frame-level data adapter (frames as samples), one seeded `GaussianMixture`
per class fit on its train frames, a Bayes-rule wrapper (`predict`/`predict_proba` from summed
frame log-likelihoods + log priors), seeded EM (`derive_seed(seed, "weight_init")`), joblib
persistence + round-trip. Classification + calibration on flat/per-window predictions first
(clip aggregation lands in I.ad). Registered per the I.z plugin topology.

### I.ad — Clip-level window aggregation on the generative evaluator *(code)*
Port window→clip aggregation (`mean`/`logit_average`/`majority_vote` by `source_record_id`) to
the generative/sklearn evaluation path (the PyTorch evaluator's [aggregation.py](../../src/modelfoundry/plugins/pytorch/aggregation.py)
math is plugin-agnostic — share or numpy-port it); add the **dangling `source_record_id`**
refusal (parity with check 23 / `verify_window_integrity`). The generative model now scores
**clip-level**, head-to-head with the CNN on identical splits.

### I.ae — `hmm_classifier` generative backend *(code; gated by I.aa)*
Per the I.aa spike outcome: per-class `hmmlearn` HMM behind the `[hmm]` extra (graceful
`MaterializeError` + install pointer without it, mirroring `[huggingface]`); frame-**sequence**
consumption (order matters); forward-log-likelihood Bayes classification; seeded Baum-Welch;
persistence + round-trip per the spike pattern. Reuses the I.ac wrapper surface + the I.ad
clip aggregation.

### I.af — Example recipes + end-to-end audio benchmark *(recipes + integration test; acceptance)*
Bundled `gmm`/`hmm` recipes binding the audio instance; an integration test materializing the
generative model(s) end-to-end and scoring **clip-level, head-to-head** with the MC-dropout CNN
on identical splits + the same `WindowAggregation` — contrasting accuracy + calibration. Assert
**byte-determinism** + **round-trips from disk** + **existing discriminative recipes unaffected**.
The brief's verification turned into the acceptance gate.

### I.ag — Doc sync, project-essentials append & release — **owns the bump (→ v0.20.0)**
Add FR-GEN-1/2/3 + FR-SCHEMA-1 to `features.md`; reflect the generative backend, the frame
adapter, the generative-path clip aggregation, and the optional-sections schema in `tech-spec.md`;
update `concept.md` (generative backend now in scope; plugin-interface-honesty value strengthened)
+ `README.md` if a runnable example warrants it; append must-know facts to `project-essentials.md`
(plan_phase Step 8). Update `## Future` (close Gap 2; record the deferred native-likelihood
surface + HMM-sequence-labeling as their own items). Owns the single minor bump **→ v0.20.0**.

---

## 5. Out of scope (deferred) — *to be walked through at the approval gate*

1. **Model-native likelihood / open-set / anomaly surface** — exposing per-clip log-likelihood
   as an uncertainty signal for open-set rejection / OOD / novelty. Deliberately deferred
   (developer call): I-3 ships classification + calibration only. It needs a **new model-native
   uncertainty contract** in `InferenceSpec` (none exists — the current surface is MC-dropout-
   specific). Its own future story.
2. **HMM beyond per-class Bayes classification** — sequence labeling, syllable segmentation,
   Viterbi state decoding. Only clip-level **classification** by forward log-likelihood is in scope.
3. **Generative HPO** — sklearn `run_optimization` stays `NotImplementedError`; `n_components`/
   `covariance_type`/HMM topology are explored via `variants:`/overlays, not Optuna.
4. **PyTorch-native generative models** — the generative path is sklearn/`hmmlearn` (numpy),
   not a `torch.nn.Module`. A torch density model is out.
5. **Raw-waveform / non-feature-array inputs** — only the prepared mel/MFCC `feature_path`
   arrays (Subphase I-1) are consumed; raw `sample_array` is not.
6. **Unsupervised / density-estimation / clustering surfaces** — the broader GMM value
   (soft assignment, clustering independent of labels) is out; only the supervised per-class
   Bayes classifier.
7. **Generalizing optional-sections beyond Loss/Optimizer** — only `Loss`/`Optimizer` become
   optional; `Architecture` / `Training` / `Evaluation` stay required.

---

## 6. Cache-identity & contract-alignment checklist

- **New architecture types are additive.** `gmm_classifier` / `hmm_classifier` live on the
  runtime-validated sklearn/generative `Architecture` `dict`; no `recipe/models.py` change, and
  a recipe authoring them produces *its own* identity — **no existing instance is perturbed**.
- **Optional Loss/Optimizer is byte-neutral (the I.ab design constraint).** A recipe that
  authors `Loss`/`Optimizer` keeps **identical** canonical bytes (sparse-omit only when `None`,
  mirroring `WindowAggregation`); only a *new* recipe omitting them differs. A canonical-hash
  pin test on a representative fixture guards the invariant. **Not cache-invalidating**;
  minor bump, pre-prod, no production ceremony.
- **The `[hmm]` extra is packaging-only** — not a cache-identity surface.
- **Determinism contract preserved** — seeded EM/Baum-Welch; offline; I.af asserts byte-identity
  + disk round-trip on the generative path. The I.aa spike confirms `hmmlearn` reproduces before
  the HMM backend is committed.
- **Loose-coupling invariant untouched** — the generative backend consumes the bound DR audio
  instance read-only; never re-hashes it; never writes into DR's cache tree.
- **Plugin-interface honesty strengthened** — the generative backend exercises the `Plugin`
  protocol with a **non-gradient, likelihood-based** model (no logits, no epoch loop, no HPO),
  a stronger test of the framework-agnostic abstractions than another discriminative classifier
  (a `concept.md` Value Criterion).

---

## 7. Design Decisions (Story I.z)

> The forks §1/§4 surfaced, settled so I.ab–I.af are implement-ready. Grounded in a code
> audit of [sklearn/plugin.py](../../src/modelfoundry/plugins/sklearn/plugin.py),
> [sklearn/data.py](../../src/modelfoundry/plugins/sklearn/data.py),
> [pytorch/aggregation.py](../../src/modelfoundry/plugins/pytorch/aggregation.py),
> [recipe/canonical.py](../../src/modelfoundry/recipe/canonical.py),
> [recipe/sections.py](../../src/modelfoundry/recipe/sections.py),
> [recipe/models.py](../../src/modelfoundry/recipe/models.py), and
> [recipe/validator.py](../../src/modelfoundry/recipe/validator.py). **No production code** —
> these decisions become the I.ab–I.af task contracts.

### D-I.z.1 — Plugin topology: a **new shared `generative` plugin** *(settled)*

**Decision.** GMM **and** HMM live on a new `modelfoundry.plugins.generative` plugin, **not**
bolted onto the `sklearn` plugin.

**Rationale.**
- The audit confirms the `sklearn` plugin is honestly the **discriminative MLP baseline**:
  `build_model` hard-refuses anything but `mlp_classifier` ([sklearn/plugin.py:374](../../src/modelfoundry/plugins/sklearn/plugin.py#L374)),
  `run_training` is a single MLP `.fit()` with a solver/learning-rate mapping, and `run_evaluation`
  is built around `feature_matrix` + `model.predict_proba(x)` over a flat `(n_samples, n_features)`
  matrix ([sklearn/plugin.py:268-269](../../src/modelfoundry/plugins/sklearn/plugin.py#L268)).
  None of that fits a per-class density model. Folding GMM in would fan out `_validate_architecture`
  and muddy the plugin's identity.
- The Bayes wrapper, the **frame-level** adapter, and the clip-aggregation wiring are written
  **once** on the shared plugin and reused by both `gmm_classifier` (sklearn `GaussianMixture`,
  no new dep) and `hmm_classifier` (`hmmlearn`, `[hmm]` extra). Only the per-class density
  estimator differs.
- **Dependency isolation.** The plugin ships in the entry-point table and is loaded by
  `discover_plugins()` on every install, so — mirroring the sklearn plugin's lazy-import
  discipline — `sklearn` / `hmmlearn` / `joblib` import **inside methods**, never at module top.
  GMM stays dependency-light (sklearn is already a dep); `hmmlearn` imports only on the HMM path.
- **Torch-free.** Unlike `sklearn/data.py`'s `feature_matrix` (which reuses the C.f
  `DataRefineryDataset` and so drags in `torch`), the generative frame adapter reads the
  `feature_path` `.npy` arrays **directly with numpy** (see D-I.z.2), so the whole generative
  path — fit, score, aggregate — is numpy-native and needs neither the `[pytorch]` nor the
  torch-coupled sklearn-baseline extras.

### D-I.z.2 — Recipe surface *(settled)*

**Architecture types** (`gmm_classifier`, `hmm_classifier`) stay on the runtime-validated
`dict[str, Any]` `Architecture` (no `recipe/models.py` change — they are additive, §6). The
generative plugin validates its own arch dict with pydantic param models (`extra="forbid"`),
exactly as `MLPClassifierParams` does ([sklearn/plugin.py:52](../../src/modelfoundry/plugins/sklearn/plugin.py#L52)).

**Default policy — follow the established plugin-op convention.** No-implicit-defaults
(Story I.e) was deliberately scoped to the **plugin-agnostic structural fields** in
`recipe/models.py` (`Training.precision`, `device`, `Evaluation.calibration_bins`,
`Optimization.sampler`, `Visualization.mode`, `Inference.mode`, …) — I.e.3 dropped the code
defaults **there**. Plugin-local **op** param models were intentionally left with
library-friendly value-defaults, and an audit confirms this is the **universal shipped
convention**: pytorch `Conv2dParams` (`kernel_size=3, stride=1, …`), `DropoutParams` (`p=0.5`),
`CrossEntropyClassWeightedParams` (`weight_source="train", beta=0.999`), every augmentation
param, and the sklearn `MLPClassifierParams` / `SklearnOptimizerParams`. The generative param
models **follow that same convention** — they are not held to the stricter `recipe/models.py`
standard (doing so would make the generative backend the lone outlier across the plugin layer).
Either way the **`init` scaffolder emits every value explicitly** into the generated recipe
(I.e.2), so scaffolded recipes carry the values in the canonical bytes; the param-model default
is only a fallback for **hand-authored partial recipes** (a dormant, pre-prod-cheap
default-shift exposure shared by every plugin op, not unique to this backend).

The split between *defaulted* and *author-required* tracks **convention vs. genuine modeling
fork**, mirroring how the pytorch ops default the conventional knobs but require the
shape-defining ones:

- **`gmm_classifier`** — **author-required** (no universal default — genuine modeling choices):
  `num_classes`, `n_components`, `class_prior` (`Literal["empirical","uniform"]`). **Defaulted**
  (conventional EM knobs, scaffolder-emitted): `covariance_type` (`Literal["full","tied","diag","spherical"]`,
  default `"full"`), `max_iter`, `n_init`, `reg_covar`, `tol`.
- **`hmm_classifier`** (param set **pending the I.aa spike**) — **author-required**: `num_classes`,
  `n_states`, `class_prior`. **Defaulted**: `covariance_type`, and the Baum-Welch knobs (`n_iter`,
  `tol`, topology / `init_params`) at whatever defaults the spike confirms are deterministic.

Whatever the default, the value is passed **explicitly** to the estimator (never left to fall
through to the *library's* own default — that is the genuine no-implicit-defaults concern: a
sklearn/hmmlearn version default-shift must never silently change output bytes; ModelFoundry's
param-model default is the pinned value).

**Class-prior policy** is **author-required** (a real Bayes modeling fork, not a convention): the
recommended scaffolder value is **`empirical`** (`log p(class)` from train class frequencies);
`uniform` is offered for balanced/debug runs.

**Frame-level data adapter** (the §2 contract): a clip/window `(n_mels, n_frames)` array is
consumed **frame-wise** — `n_frames` samples of dimension `n_mels` — **not** flattened to one
vector (that is `feature_matrix`'s discriminative path, explicitly avoided). The adapter is
generative-specific, numpy-native, and reads the `feature_path` arrays per the Subphase I-1
read-only contract. For **benchmark fairness** (the generative model must see the *same* inputs
as the MC-dropout CNN), the adapter applies the I-1 **`audio_normalize`** transform — but
**numpy-ported**, not via the torch loader: stats on the **mel axis** reshaped to `(n_mels, 1)`,
`float64`-promoted, with the exact `std == 0 → 1.0` zero-variance guard (the project-essentials
I-1 audio contract). This keeps the path torch-free (D-I.z.1) while preserving input parity.

### D-I.z.3 — Bayes wrapper *(settled)*

**Shape.** A custom picklable wrapper object (NOT a raw `GaussianMixture`, which exposes only
`score_samples`) holding: `class_densities: list[<estimator>]` (one fitted density per class,
class-index ordered), `log_priors: np.ndarray (C,)`, and `class_names: list[str]`.

**Math.** For a window with frames `F = (f_1..f_T)`, per class `c`:
`log_evidence_c = Σ_t density_c.score_samples(F)[t]  +  log_prior_c`
(frame-independence ⇒ sum of per-frame log-likelihoods; `score_samples` already returns the
mixture log-likelihood `log Σ_k π_k 𝒩(f|μ_k,Σ_k)`). The prior is added **once per window**, not
per frame. Posterior `predict_proba` = a **numerically stable softmax** (`scipy.special.logsumexp`)
over the `(C,)` `log_evidence` vector; `predict` = its argmax. The wrapper **never emits logits**
— the evaluator consumes `predict_proba` directly (§2).

**No length normalization.** DataRefinery's `window` op slices **fixed-length** windows, so `T`
is constant across the windows being compared and length-normalizing the summed log-likelihood is
moot at the window level. Documented as an explicit assumption (revisit only if variable-length
clips are ever scored pre-aggregation).

**Persistence is byte-stable under joblib.** Unlike torch tensors (whose pickle embeds storage
identity — the B.k checkpoint hazard in project-essentials), fitted sklearn estimators store
`means_`/`covariances_`/`weights_` as **numpy arrays that pickle by value**, so two seeded fits
produce byte-identical `joblib.dump` output. The whole wrapper round-trips via one
`joblib.dump`/`load`; the generative plugin's `save_model`/`load_model` mirror the sklearn
plugin's `estimator.joblib` pattern.

### D-I.z.4 — Clip aggregation placement, optional `Loss`/`Optimizer` schema, seeding *(settled)*

**(a) Clip aggregation — numpy port in a shared torch-free module.** The
[pytorch/aggregation.py](../../src/modelfoundry/plugins/pytorch/aggregation.py) math
(`verify_window_integrity` / `group_windows` / `aggregate_probs` / `_apply_policy` for
`mean`/`logit_average`/`majority_vote`) is plugin-agnostic **except** it is written in
`torch.Tensor`. **Decision:** numpy-port it into a **new torch-free shared module**
(`pipeline/aggregation.py`), consumed by the **generative evaluator** in I.ad. The PyTorch
evaluator's `aggregation.py` is left **untouched** in I-3 — re-pointing the determinism-critical
torch path would re-open the I.p byte-identity test for no I-3 benefit; migrating it onto the
shared module is recorded as a **Future** item (I.ag). Byte-parity between the numpy and torch
ports is **not** required (the two models run on separate numpy/torch paths and the benchmark
compares *metrics*, not bytes); a semantic-equivalence test on a small fixture guards against
drift. The **dangling-`source_record_id` refusal** is ported verbatim (parity with check 23 /
`verify_window_integrity`).

**(b) Optional `Loss`/`Optimizer` (I.ab) — `| None = None` + sparse-omit. Precise adaptation
list:**
- `recipe/models.py:222-223` — `Loss: LossSpec | None = None`, `Optimizer: OptimizerSpec | None = None`.
- `recipe/canonical.py` — **move** `"Loss"`/`"Optimizer"` out of `_PLUGIN_FIELDS`
  ([canonical.py:50](../../src/modelfoundry/recipe/canonical.py#L50)) **into** `_SPARSE_PLUGIN_FIELDS`
  ([canonical.py:68](../../src/modelfoundry/recipe/canonical.py#L68)), mirroring `WindowAggregation`:
  present ⇒ merged, `None` ⇒ omitted. **Byte-neutral confirmed:** an authoring recipe still merges
  the same `{"op": …}` sub-doc and JSON is `sort_keys=True`, so the plugin-segment bytes are
  identical to today; only a *new* omitting recipe differs (its own identity). A **canonical-hash
  pin test** on a representative discriminative fixture guards the invariant.
- `recipe/sections.py:67-68` — `iter_op_sections` guards: yield `Loss` / `Optimizer` /
  `Optimizer.schedule` **only when the section is not `None`**. Checks **3** and **17** read
  `resolve_sections`'s output, so they skip `None` sections automatically once the iterator guards
  — no per-check edit needed.
- `recipe/validator.py:237-238` — `_check_6_monitor_metrics_produced` guards
  `recipe.Optimizer is not None and recipe.Optimizer.schedule is not None`. (`early_stopping` is on
  `Training`, which **stays required** — no change.)
- **Consumers that assume presence** (mypy + invariant): `plugins/pytorch/trainer.py:116-124,330,357,370`
  and `plugins/sklearn/plugin.py:214-217` read `recipe.Loss`/`recipe.Optimizer` unconditionally.
  Both are discriminative paths that **require** the sections; add an explicit guard at entry
  (raise `PluginError("plugin <x> requires Loss/Optimizer")`) so the `| None` narrows for mypy and
  the invariant is documented. The generative plugin never enters the trainer (it has no gradient
  loop), so no None-handling is needed there.
- **Scaffolder + fixtures** — the `init` scaffolder emits `Loss`/`Optimizer` **only for plugins
  that have the concept** (pytorch/sklearn); generative recipes omit them. Existing discriminative
  fixtures are unchanged (byte-identical).

**(c) Seeding (determinism, four invariants).**
- **GMM:** `GaussianMixture(random_state=derive_seed(seed, "weight_init") & _U32, …)` — the exact
  32-bit-masked pattern the MLP baseline already uses ([sklearn/plugin.py:209](../../src/modelfoundry/plugins/sklearn/plugin.py#L209)).
  The same derived `random_state` is shared across the per-class fits (each fit is deterministic on
  its own class data; per-class scope derivation is unnecessary). `prepare_for_build` is a **no-op**
  (RNG is seeded at fit, mirroring the sklearn plugin).
- **HMM:** the I.aa spike's load-bearing question — confirm `hmmlearn` Baum-Welch reproduces
  byte-identically under a seeded `random_state` and runs offline before I.ae commits.
- **N/A invariants:** no DataLoader (`num_workers` irrelevant), no Optuna (`run_optimization` stays
  `NotImplementedError`), no AMP. Offline is trivial (pure CPU numpy/sklearn).
- **Training artifact:** GMM EM exposes no per-iteration loss curve, so `history.parquet` records a
  generative-appropriate trace — per-class converged `lower_bound_` + `n_iter_` — rather than a
  faux loss curve.
- **Byte-identity + disk round-trip** asserted on the generative path in **I.af** (parity with I.p).
