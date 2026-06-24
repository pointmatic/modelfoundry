# Consumer Gap Analysis 2 — ModelFoundry (and the DataRefinery → ModelFoundry seam)

A running log of friction met while taking a real consumer project through the intended
happy path: **recipe-writing → data-preparation (DataRefinery) → model-building
(ModelFoundry)**. Anything that needed *more* than authoring a recipe and running the two
tools is logged here — each gap as symptom → affected contract → diagnosis → recommended
fix → verification, plus the **workaround** used to keep delivery moving. Entries are
consumer-sanitized for hand-off into the public dependency repos.

This is **round 2**, succeeding [`consumer-gap-analysis.md`](consumer-gap-analysis.md)
(round 1, whose audio-consumption gap was resolved by the `0.18.0` feature-array loader).
It covers the **ModelFoundry** side and the **DR → MF hand-off seam**; DataRefinery-internal
round-2 friction, if any surfaces, goes in a sibling `datarefinery/consumer-gap-analysis2.md`.
"Intuition gaps" (the behavior is *implemented* correctly but a competent consumer cannot
predict the wiring from the docs/recipe surface) are logged here too.

## Gap index

| # | Gap | Surface | Severity | Status |
|---|-----|---------|----------|--------|
| 1 | `Evaluation.comparison.baseline_model_id` validates but is **silently skipped** at materialize — declared benchmark comparison never runs | MF evaluation (baseline resolver deferred) | declared comparison non-functional (workaround exists) | **fix in progress** (FR-12 sklearn-fit resolver + scoring + check-13 xfail flip); workaround applied meanwhile |
| 2 | No **generative-probabilistic** backend — all shipped plugins (`pytorch`/`sklearn`/`random`) are discriminative classifiers; a per-class GMM/HMM model can't be authored | MF plugin/backend set | feature gap — blocks a *pure-probabilistic* (classical) model; backup option only | backup option / deferred (would need a non-PyTorch generative backend) |

---

## Gap 1 — declared baseline/benchmark comparison validates but is skipped at materialize

| Field | Value |
|-------|-------|
| Surface | MF `Evaluation` stage — `ComparisonSpec.baseline_model_id` |
| Related contract | `Evaluation.comparison.baseline_model_id` (recipe `ComparisonSpec`); `modelfoundry/plugins/pytorch/evaluation.py` `_baseline_comparison_warning` |
| Sanitized | yes |
| First hit | 2026-06-23 |
| Status note | Fix in progress upstream: FR-12 baseline-comparison design pass + sklearn-fit resolver + scoring, flipping the check-13 `xfail`. When it ships, a declared `baseline_model_id` (incl. a sklearn baseline) resolves and scores natively, retiring the workaround below. |

### Symptom

A consumer reaches the optimization / benchmarking step and wants to evaluate the trained
model **against a baseline** — the documented mechanism is
`Evaluation.comparison.baseline_model_id: <other-model-instance>`. The recipe `validate`
passes (a dedicated check confirms the `baseline_model_id` *format*), and `materialize`
runs to completion — but the evaluation stage emits only a warning and produces **no
comparison output**:

```
baseline comparison against '<id>' is not yet resolvable
(deferred to the C.m baseline resolver); skipped
```

So a consumer who declares the comparison in good faith — and sees `validate` go green —
gets a materialized instance with **no baseline delta**: the benchmark evaluation they
asked for silently did not happen.

### Affected contract / abstraction

`Evaluation.comparison` (`ComparisonSpec.baseline_model_id`). The recipe surface **accepts
and format-validates** the field, but the PyTorch evaluation stage's cross-instance
baseline resolution is **deferred** (`_baseline_comparison_warning` — "deferred to the C.m
baseline resolver"). The per-split metrics + the in-study recipe-defaults baseline trial
work; the *cross-instance* baseline-vs-model comparison declared on `Evaluation.comparison`
does not.

### Diagnosis

A validate/materialize asymmetry (the same shape as round-1 DataRefinery Gap 1): the cheap
gate green-lights a capability the run then skips, surfacing only a mid-materialize warning.
Cross-instance baseline resolution simply isn't implemented yet. For a consumer whose
deliverable requires "identify a benchmark and evaluate the model against it," the declared
contract can't carry that comparison today, and nothing at `validate` time says so.

### Recommended fix

- **Implement the baseline resolver** so `baseline_model_id` resolves a sibling
  `ModelInstance` and computes a comparison (the delta on the shared held-out metrics),
  persisted alongside `evaluation/metrics.json`.
- **Until then, surface the limitation at the cheap gate:** have `validate` warn (or hard-error
  with an opt-out) that a declared `comparison` will be **skipped**, so the consumer learns
  it before a long `materialize` rather than from a mid-run log line.

### Workaround applied

Obtain the benchmark comparison **outside** the `comparison` contract: use the Optuna
`Optimization` block's `baseline_trial: enqueue_recipe_defaults` (the recipe-defaults config
is run as an in-study baseline trial), so the optimized-vs-default delta is recorded in
`optimization/trials.parquet`; and document the **prior trained-model numbers** (the
pre-optimization results of each model) plus the relevant published-leaderboard / chance
floor as the external benchmark in the write-up. The `Evaluation.comparison` block is
**omitted** from the recipe to avoid emitting a misleading skipped-comparison warning.

### Verification

- With the resolver shipped, a recipe declaring `Evaluation.comparison.baseline_model_id`
  produces a persisted baseline-vs-model comparison on the held-out split, **with no skip
  warning**.
- Independently of the resolver, the optimized model's improvement over the recipe-defaults
  baseline trial is recorded in `optimization/trials.parquet` and reproducible across a
  seeded re-run.

---

## Gap 2 — no generative-probabilistic backend (per-class GMM / HMM) for a *pure-probabilistic* model

| Field | Value |
|-------|-------|
| Surface | MF plugin/backend set (`pytorch`, `sklearn`, `random`) |
| Related contract | `Plugin` protocol + `Architecture` op vocabulary; the shipped backends are all **discriminative** classifiers (PyTorch nets, sklearn `MLPClassifier`/`dummy`, `random`) |
| Sanitized | yes |
| First hit | 2026-06-23 |
| Kind | feature gap / **backup option** (not blocking — the primary probabilistic model is the MC-dropout BNN) |

### Symptom

The consumer's audio classifier has two candidate "probabilistic" framings (settled during
model selection). The **primary** is a *discriminative* Bayesian neural network — a
spectrogram CNN with Monte-Carlo dropout (approximate posterior over weights; uncertainty
from T stochastic passes). The documented **backup** is a *pure / classical generative*
probabilistic model: a **per-class Gaussian Mixture Model (GMM)**, or a **Hidden Markov
Model (HMM)** for temporal structure, fit over MFCC-style frame features and classified by
**maximum likelihood under Bayes' rule**.

There is no way to author the backup in ModelFoundry: every shipped backend is a
discriminative classifier. The `sklearn` plugin exposes `mlp_classifier` / `dummy_classifier`
(scikit-learn's *classifier* API), not a generative density model — and `GaussianMixture`
isn't a classifier (it has no `predict` over class labels; the "one GMM per class, argmax
log-likelihood" construction is a custom estimator), while an HMM needs a sequence backend
(`hmmlearn`) MF doesn't ship. So the recipe-as-truth path simply has no `Architecture` to
name for a generative-probabilistic model.

### The audio use case we had in mind, and how it would be used

- **Model.** Fit one class-conditional density per species over the clip's MFCC frame
  sequence: a **GMM** (full/diagonal covariance, K components) treating frames as i.i.d., or
  an **HMM** (left-to-right / ergodic) that additionally models the **temporal structure of
  birdsong syllables** (frame order, transitions). Training is generative — fit `p(frames |
  species)` per class on that class's training clips only.
- **Inference.** Score a clip's frames under every class model (sum frame log-likelihoods, or
  the HMM forward log-likelihood), add log class priors, and pick the argmax — a textbook
  **Bayes-rule generative classifier**. Softmax over the per-class log-likelihoods yields
  posterior class probabilities, and the **per-frame / per-clip likelihood is itself the
  uncertainty signal** (no sampling needed).
- **How it serves the deliverable.** Primarily as the **classical-vs-Bayesian contrasting
  benchmark** for the audio model: scored on the *same* held-out clips and clip-level
  aggregation as the MC-dropout CNN, contrasting a classical generative model against a
  modern discriminative BNN on **accuracy and calibration**. Secondarily, it is the **backup
  primary** probabilistic model had the BNN route been unavailable — it is unambiguously
  "probabilistic" in the classical generative sense (explicit likelihoods + Bayes' rule),
  which is a maximally defensible reading of the probabilistic-method requirement.
- **Inputs are already available.** Now that the data side persists the float `mel`/MFCC
  frames (the `feature_path` npy sidecar, round-1 Gap 3's fix), a GMM/HMM consumer could read
  the same per-window feature arrays the CNN consumes — only the MF backend is missing.

### Other use cases for a generative GMM/HMM probabilistic model

A generative-probabilistic backend earns its keep well beyond this one contrast:

- **Open-set rejection / "none of the above."** Abstain when the best class likelihood is low
  — no class density explains the input. A discriminative softmax always forces a class;
  a generative model can say "unknown."
- **Anomaly / novelty / out-of-distribution detection.** Likelihood thresholding flags inputs
  unlike any trained class (a non-bird sound, an unseen species, a corrupted clip) — a
  first-class capability the BNN lacks.
- **Sequence / temporal modeling (HMM).** Speech / phoneme recognition, syllable segmentation,
  gesture and gait recognition, and general state-structured time series — domains where
  frame order carries the signal.
- **Speaker / language / instrument identification.** The classic GMM-UBM family.
- **Low-data and streaming regimes.** Generative class models fit from far fewer examples per
  class than deep nets, and score frame-by-frame online.
- **Density estimation / unsupervised structure.** Clustering and soft assignment in the
  feature space (GMM) independent of labels.

### Affected contract / abstraction

The `Plugin` protocol and `Architecture` vocabulary admit only discriminative classifiers
today. A generative model breaks two implicit assumptions: training is **per-class density
fitting** (not a single cross-entropy-minimizing head over all classes), and the prediction
surface is **likelihood-based** (Bayes' rule), not a learned `logits → softmax` map. The
`Evaluation` metric set (accuracy, macro/per-class F1, ECE, calibration) and clip-level
`WindowAggregation` apply unchanged — only the model backend is missing.

### Recommended fix

Behavior-level options (implementation design is ModelFoundry's own tech-spec):

1. **Extend the `sklearn` plugin with a generative classifier** — e.g. a `gmm_classifier`
   architecture that fits one `sklearn.mixture.GaussianMixture` per class and classifies by
   max class-conditional log-likelihood + priors (covariance type, `n_components` as params).
   Smallest reuse of an existing backend; covers the GMM case.
2. **A dedicated sequence/generative backend** (e.g. an `hmmlearn`-backed plugin, gated behind
   an extra) for the HMM case where temporal structure matters — parallel to how the audio
   feature path is gated behind `[audio]`.
3. Either way, surface a **likelihood / log-evidence output** alongside the class posterior so
   the open-set / anomaly use cases above are reachable, and keep the existing `Evaluation` +
   `WindowAggregation` contracts intact so the model drops into the same comparison harness.

### Workaround applied

**None needed for the current deliverable** — the primary probabilistic model (MC-dropout
spectrogram CNN, Story C.c.2) is built and meets the probabilistic-method requirement; the
GMM/HMM model is a **documented backup / low-priority contrasting benchmark**, deliberately
not the primary. If pursued, it requires the backend above (a non-PyTorch generative path)
rather than a recipe-level workaround. Recorded here so the option — and its broader value —
is captured rather than lost.

### Verification

- With a `gmm_classifier` (or HMM) backend, a recipe binding the same materialized audio
  instance fits per-class densities, classifies a held-out clip by max likelihood (windows
  aggregated by `source_record_id`), and reports the existing metric set + calibration —
  scorable head-to-head against the MC-dropout CNN on identical splits.
- The generative model additionally exposes a per-clip likelihood usable for open-set
  rejection (a low-likelihood clip is flagged rather than force-classified).
