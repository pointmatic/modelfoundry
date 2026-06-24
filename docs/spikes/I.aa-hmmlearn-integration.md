# Spike I.aa — `hmmlearn` integration de-risk

> **Type:** integration spike (will the external system connect?).
> **Status:** complete. **Verdict: GO.** **Deliverable:** this document. The script
> [`scripts/spike_hmmlearn.py`](../../scripts/spike_hmmlearn.py) is throwaway evidence
> (6/6 claims pass), not production code.
> **Date:** 2026-06-24. **Gates:** Story I.ae (`hmm_classifier` backend).
> **Sources:** [`phase-i-subphase-3-generative-probabilistic-backend-plan.md`](../specs/phase-i-subphase-3-generative-probabilistic-backend-plan.md)
> §1/§2/§4 (I.aa), the I-1 audio fixture
> [`builder.py`](../../tests/fixtures/datarefinery_instances/audio_smoke/builder.py).

## The risk being de-risked

`hmmlearn` is a **new integration boundary** behind a future `[hmm]` packaging extra.
Before Story I.ae commits a per-class HMM backend, the spike confirms the library
clears the four-invariant **determinism contract** (`project-essentials.md` § "Determinism
contract is foundational") — specifically that a seeded Baum-Welch fit reproduces
**byte-identically**, the load-bearing unknown the plan flagged (`hmmlearn` historically
seeded via numpy/scipy RNG). A failure here would have meant a hand-rolled HMM fallback
or deferring HMM to a v0.21.0 follow-on.

## Probe setup

Scratch venv on the project's pinned Python (3.12.13), `hmmlearn` + `joblib` only — no
project-config change (the `[hmm]` extra is wired in I.ae, not the spike):

```
python -m venv /tmp/hmm_spike_env
/tmp/hmm_spike_env/bin/pip install hmmlearn joblib
/tmp/hmm_spike_env/bin/python scripts/spike_hmmlearn.py
```

Installed closure: **`hmmlearn 0.3.3`**, numpy 2.5.0, scipy 1.18.0, scikit-learn 1.9.0,
joblib 1.5.3 — all already inside ModelFoundry's dependency closure (`hmmlearn` is the
only genuinely new top-level dep; it pulls nothing exotic). Data is seeded synthetic frame
sequences at **shape parity with the I-1 audio fixture** (`n_mels=64`, `n_frames=100`,
3 classes), consumed **frame-sequence-wise** (`(n_frames, n_mels)` per window) — order
matters for an HMM, the distinction the plan draws from the GMM's frame-bag consumption.

## Claims & results (6/6 PASS)

| # | Claim | Result |
|---|-------|--------|
| 1 | `hmmlearn` installs; one `GaussianHMM` fits per class via Baum-Welch on concatenated frame sequences (`fit(X, lengths)`) | PASS — 3 HMMs fit |
| 2 | Classification by **forward log-likelihood + Bayes** (`argmax_c [ model_c.score(seq) + log P(c) ]`) | PASS — held-out acc 1.000 (6/6 on separable synthetic data) |
| 3 | Fitted models **round-trip via joblib** with identical scores | PASS — `max|Δ| = 0` |
| 4 | **Byte-identical fit under `random_state` alone**, with the numpy **global** RNG deliberately perturbed between fits | PASS — per-class joblib SHA-256 digests match; fitted `means_`/`transmat_`/`startprob_` arrays equal |
| 4-xproc | Byte-identity holds **across separate processes** (the real reproducibility surface) | PASS — identical dump SHA-256 across two process invocations |
| 5 | Runs **offline** — `socket.socket` hard-blocked during fit | PASS — no socket call escaped |

## The persistence / determinism pattern (carried into I.ae)

1. **Seeding lever — `random_state` is sufficient and necessary.** `GaussianHMM(random_state=<int>)`
   fully pins the fit: init (`init_params="stmc"` → startprob/transmat random init + KMeans
   means init) and Baum-Welch are deterministic from that int. Critically, the result is
   byte-identical **even when the numpy global RNG is perturbed between fits** — `hmmlearn`
   does **not** leak the process-global RNG. So the backend seeds exactly like the GMM
   (D-I.z.4): `random_state = derive_seed(seed, "weight_init") & _U32`, **no** global
   `np.random.seed` needed (and none should be relied on).
2. **Pin every behavior-affecting knob explicitly** (no-implicit-defaults / D-I.z.2): pass
   `n_components` (states), `covariance_type`, `n_iter`, `tol`, `init_params`, `params`
   explicitly — never fall through to the `hmmlearn` library default, which could shift across
   versions and silently change output bytes.
3. **Persistence is byte-stable via `joblib.dump`** of the fitted model (or the per-class dict /
   the Bayes wrapper of D-I.z.3) — fitted arrays pickle by value, so two seeded fits produce
   identical bytes (same property the GMM relies on; contrast the torch-tensor pickle hazard).
4. **Frame-sequence consumption** uses `fit(X, lengths)` with `X` the row-stacked frames and
   `lengths` the per-window frame counts; classification scores a single window's
   `(n_frames, n_mels)` array with `model.score(seq)`.
5. **Offline** is free — pure numpy/scipy CPU; no download path. The four invariants:
   `num_workers`/Optuna/AMP are N/A (no DataLoader, no HPO, no mixed precision).

## Verdict

**GO** — commit the `hmm_classifier` backend in Story I.ae behind the `[hmm]` extra. No
fallback (hand-rolled HMM) or v0.21.0 deferral needed; `hmmlearn 0.3.3` clears the
byte-identity bar under `random_state` alone, in-process and cross-process. The I.aa plan
param set (D-I.z.2: author-required `num_classes`/`n_states`/`class_prior`; defaulted
`covariance_type`/`n_iter`/`tol`) is confirmed implementable as written.
