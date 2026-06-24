# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Throwaway evidence for Spike I.aa — `hmmlearn` integration de-risk.

NOT production code. Run under a scratch venv with `hmmlearn` + `joblib`:

    python -m venv /tmp/hmm_spike_env
    /tmp/hmm_spike_env/bin/pip install hmmlearn joblib
    /tmp/hmm_spike_env/bin/python scripts/spike_hmmlearn.py

Probes the five load-bearing claims the HMM backend (Story I.ae) rides on:

  1. install + per-class fit on frame sequences (shape parity with the I-1
     audio fixture: frames of dim n_mels, n_frames per window);
  2. classification by forward log-likelihood + Bayes (`score` + log prior);
  3. joblib round-trip → identical scores;
  4. byte-identical fit under a seeded Baum-Welch (the four-invariant risk:
     `hmmlearn` must reproduce from `random_state` alone, NOT the numpy global RNG);
  5. offline (no network) — proven by hard-blocking `socket` during fit.

Exit 0 ⇒ all claims pass (go); nonzero ⇒ friction (the verdict records which).
"""

from __future__ import annotations

import hashlib
import io
import socket
import sys

import joblib
import numpy as np
from hmmlearn.hmm import GaussianHMM

# Shape parity with the I-1 audio fixture (builder.py: n_mels=64, n_frames=100).
N_MELS = 64
N_FRAMES = 100
CLASSES = ("c0", "c1", "c2")
TRAIN_CLIPS_PER_CLASS = 4
VAL_CLIPS_PER_CLASS = 2
N_STATES = 3
COVARIANCE_TYPE = "diag"
N_ITER = 20
SEED = 1234

_results: list[tuple[str, bool, str]] = []


def _claim(name: str, ok: bool, note: str = "") -> None:
    _results.append((name, ok, note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + note) if note else ''}")


def synth_class_sequences(
    rng: np.random.Generator, n_clips: int, offset: float
) -> list[np.ndarray]:
    """A list of (n_frames, n_mels) float32 frame sequences for one class.

    Each class is a different Gaussian mean offset so the per-class HMMs are
    separable enough for the Bayes classifier to be non-trivial.
    """
    seqs = []
    for _ in range(n_clips):
        base = rng.standard_normal((N_FRAMES, N_MELS)).astype(np.float32) + offset
        seqs.append(base)
    return seqs


def fit_per_class_hmms(
    train: dict[str, list[np.ndarray]], random_state: int
) -> dict[str, GaussianHMM]:
    models: dict[str, GaussianHMM] = {}
    for cls, seqs in train.items():
        X = np.concatenate(seqs, axis=0)
        lengths = [len(s) for s in seqs]
        model = GaussianHMM(
            n_components=N_STATES,
            covariance_type=COVARIANCE_TYPE,
            n_iter=N_ITER,
            random_state=random_state,  # the ONLY seeding lever the contract allows
            init_params="stmc",
            params="stmc",
        )
        model.fit(X, lengths)
        models[cls] = model
    return models


def classify(models: dict[str, GaussianHMM], log_priors: dict[str, float], seq: np.ndarray) -> str:
    # Bayes: argmax_c [ log P(seq | HMM_c)  +  log P(c) ].  score() = forward log-likelihood.
    best_cls, best_val = None, -np.inf
    for cls, model in models.items():
        val = float(model.score(seq)) + log_priors[cls]
        if val > best_val:
            best_cls, best_val = cls, val
    assert best_cls is not None
    return best_cls


def model_bytes(model: GaussianHMM) -> bytes:
    buf = io.BytesIO()
    joblib.dump(model, buf)
    return buf.getvalue()


def main() -> int:
    print("Spike I.aa — hmmlearn integration probe\n")

    rng = np.random.default_rng(SEED)
    train = {
        cls: synth_class_sequences(rng, TRAIN_CLIPS_PER_CLASS, offset=float(i))
        for i, cls in enumerate(CLASSES)
    }
    val = {
        cls: synth_class_sequences(rng, VAL_CLIPS_PER_CLASS, offset=float(i))
        for i, cls in enumerate(CLASSES)
    }
    n_train = sum(len(v) for v in train.values())
    log_priors = {cls: np.log(len(seqs) / n_train) for cls, seqs in train.items()}

    # --- Claim 1+5: fit per-class HMMs, with sockets hard-blocked (offline proof) ---
    real_socket = socket.socket

    def _blocked(*_a, **_k):
        raise AssertionError("network access during fit — NOT offline")

    socket.socket = _blocked  # type: ignore[assignment, misc]
    try:
        import hmmlearn

        models = fit_per_class_hmms(train, random_state=SEED)
        _claim("1. install + per-class Baum-Welch fit", True, f"hmmlearn {hmmlearn.__version__}")
        _claim("5. offline (sockets blocked during fit)", True, "no socket.socket() escaped")
    except AssertionError as exc:
        _claim("5. offline (sockets blocked during fit)", False, str(exc))
        socket.socket = real_socket  # type: ignore[assignment]
        return 1
    finally:
        socket.socket = real_socket  # type: ignore[assignment]

    # --- Claim 2: classification by forward log-likelihood + Bayes ---
    correct = total = 0
    for cls, seqs in val.items():
        for seq in seqs:
            total += 1
            correct += classify(models, log_priors, seq) == cls
    acc = correct / total
    _claim("2. forward-loglik + Bayes classify", acc > 0.5, f"acc={acc:.3f} ({correct}/{total})")

    # --- Claim 3: joblib round-trip → identical scores ---
    buf = io.BytesIO()
    joblib.dump(models, buf)
    buf.seek(0)
    reloaded = joblib.load(buf)
    sample = val[CLASSES[0]][0]
    before = [float(models[c].score(sample)) for c in CLASSES]
    after = [float(reloaded[c].score(sample)) for c in CLASSES]
    max_delta = max(abs(a - b) for a, b in zip(before, after, strict=True))
    _claim("3. joblib round-trip preserves scores", before == after, f"max|Δ|={max_delta:.2e}")

    # --- Claim 4: byte-identical fit under a seeded Baum-Welch (THE load-bearing risk) ---
    # Deliberately do NOT seed the numpy GLOBAL RNG before the second fit; if the
    # result is byte-identical anyway, `random_state` alone pins determinism (the
    # four-invariant requirement). Perturb the global RNG to make any leak visible.
    np.random.seed(999)
    _ = np.random.random(10_000)
    models_b = fit_per_class_hmms(train, random_state=SEED)
    digests_a = {c: hashlib.sha256(model_bytes(models[c])).hexdigest() for c in CLASSES}
    digests_b = {c: hashlib.sha256(model_bytes(models_b[c])).hexdigest() for c in CLASSES}
    byte_identical = digests_a == digests_b
    _claim(
        "4. byte-identical under seeded fit (random_state only)",
        byte_identical,
        "joblib digests match" if byte_identical else f"DIVERGED: {digests_a} vs {digests_b}",
    )
    # Also confirm the fitted parameter arrays themselves match (independent of pickle).
    params_match = all(
        np.array_equal(models[c].means_, models_b[c].means_)
        and np.array_equal(models[c].transmat_, models_b[c].transmat_)
        and np.array_equal(models[c].startprob_, models_b[c].startprob_)
        for c in CLASSES
    )
    _claim("4b. fitted params (means_/transmat_/startprob_) equal", params_match)

    print()
    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"VERDICT: {passed}/{len(_results)} claims pass")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())
