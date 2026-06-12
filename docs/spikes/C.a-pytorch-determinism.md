# Spike C.a — Deterministic PyTorch training loop

**Story:** C.a (Subphase C-1) · **Type:** architectural spike · **Status:** complete, PASS
**Script:** [`scripts/spike_pytorch_determinism.py`](../../scripts/spike_pytorch_determinism.py) (throwaway)
**Env:** ml-modelfoundry conda testenv — torch 2.12.0, CPU, macOS (Apple Silicon), Python 3.12.13

---

## Question

Before the production PyTorch plugin (C.b–C.p) lands, validate the determinism
spine: does

```
torch.use_deterministic_algorithms(True)
+ CUBLAS_WORKSPACE_CONFIG=:4096:8
+ a per-worker DataLoader seed (B.j worker_init_fn pattern)
```

produce a **byte-identical** `model.state_dict()` across a minimal CNN training
loop, **independent of `num_workers ∈ {1, 2, 4}`** and **reproducible run-to-run**,
on CPU? This is the QR-3 / FR-25 guarantee the whole cache-identity contract rests
on (`project-essentials.md` § "Determinism contract is foundational").

## Setup

- **Model:** `TinyCNN` — 2× `Conv2d` (bias) → `ReLU` → `AdaptiveAvgPool2d(1)` →
  `Linear`. Exercises conv forward/backward + adaptive-pool backward under the
  deterministic-algorithm guard.
- **Data:** 32 synthetic 3×8×8 images. `__getitem__` seeds a **per-record**
  `torch.Generator` from `derive_seed(MASTER_SEED, "augmentation:synthetic", idx)`
  — never from worker-local RNG — so pixels are identical regardless of worker
  count. This mirrors DataRefinery's `pipeline.workers` per-record-seed contract.
- **Loader:** `batch_size=8`, `shuffle=True` with a seeded `generator` (shuffle
  order owned by the main process), `worker_init_fn` bound to the master seed.
- **Training:** 2 epochs, `SGD(lr=0.1)`, `CrossEntropyLoss`.
- **Hash:** SHA-256 over every state-dict tensor's raw bytes in sorted-key order
  (robustly byte-deterministic; avoids `torch.save` pickle-ordering noise).
- Seeds: `weight_init` and `data_shuffle` are derived via
  `modelfoundry.pipeline.seeding.derive_seed`; weight init is seeded
  **independently** of the global RNG so it can't drift with loader RNG use.

## What was confirmed

| Check | Result |
|-------|--------|
| Byte-identical state-dict across `num_workers ∈ {1, 2, 4}` (deterministic ON) | ✅ all three hashes equal |
| Run-to-run reproducibility (repeat `num_workers=2`) | ✅ identical |
| Any op hard-errors under `use_deterministic_algorithms(True)` on CPU | ❌ none — `Conv2d` and `AdaptiveAvgPool2d` backward are deterministic on CPU |
| `CUBLAS_WORKSPACE_CONFIG=:4096:8` set before first torch use | ✅ (no-op on CPU, set anyway to mirror C.e) |

Representative state-dict hash (this env): `a688ea41e4e778f2…b26d9`. The hash is
environment-bound (torch/BLAS build), **not** a golden to pin across machines —
the invariant under test is *equality across worker counts and repeats*, not the
literal digest.

## Surprises / integration risks to carry into C.e / C.f / C.h

1. **B.j's `worker_init_fn_factory` returns an unpicklable closure → crashes
   `DataLoader(num_workers>0)` under macOS `spawn`.** This is the spike's most
   important finding. The factory's inner `_worker_init_fn` is a local closure;
   `pickle.dumps(...)` raises `AttributeError: Can't get local object
   'worker_init_fn_factory.<locals>._worker_init_fn'`, and the macOS default
   start method (`spawn`) pickles the `worker_init_fn` to ship it to each worker.
   **The minimal CNN cannot train with workers using B.j as-written on macOS.**
   - **Fix the production path must adopt (C.f data adapter / C.h trainer):** make
     the worker-init a **module-level** function bound to its master seed via
     `functools.partial(_seed_worker, master_seed)` (partials of module-level
     functions are picklable and spawn-safe). The spike demonstrates exactly this.
   - **Recommended follow-up for B.j:** rework `worker_init_fn_factory` to return a
     `functools.partial` over a module-level helper instead of a closure (a small,
     behavior-preserving change; its unit tests exercise the seeding effect, not
     the object identity). Tracking note left for the C.f/C.h implementer — not
     fixed here (spike scope is documentation, and B.j is already `[Done]`).
2. **CPU is already byte-deterministic without the guard here.** With identical
   seeds, `deterministic=False` produced the *same* hash as `deterministic=True`.
   That's expected: the ops in this loop have no nondeterministic CPU kernels. The
   guard's value is on **CUDA** (atomic-scatter / cuDNN autotune paths) and as a
   **hard-error tripwire** that surfaces a nondeterministic op at dev time rather
   than letting it silently break byte-identity. Keep the guard ON by default
   (C.e) regardless — its cost on CPU is nil and it protects the GPU path.
3. **MPS sidestepped.** The spike is CPU-only by construction (`device("cpu")`),
   matching the Subphase C-1 CPU budget. MPS determinism + the per-device
   `manifest.byte_identity_guaranteed` story is deferred to the future
   `testenv-mps` env (`env-dependencies.md` §4.1 / §8); not exercised here.

## Pattern locked for C.e / C.f / C.h

- **C.e `determinism.py`:** set `CUBLAS_WORKSPACE_CONFIG` if unset → call
  `torch.use_deterministic_algorithms(True)` → seed `torch.manual_seed` (+ cuda /
  mps as applicable) **before model construction**. Idempotent. CPU path
  hard-errors on no ops in the C-1 vocabulary; keep the documented-hard-error list
  empty for CPU and populate it if a future op trips the guard.
- **C.f `data.py` / C.h `trainer.py`:** seed weight-init independently of loader
  RNG; own shuffle order via a seeded `generator`; attach a **picklable**
  (`functools.partial` of a module-level fn) `worker_init_fn`; rely on per-record
  seeding for worker-count-independent sample bytes.
- **Verification harness (C.h integration test):** assert byte-identity of the
  state-dict across `num_workers ∈ {1, 2}` and across two repeats — the property
  this spike validated — rather than pinning a cross-machine golden hash.

## How to re-run

```bash
# Conda testenv (pyve test / pyve run are parked on the Pyve v3.0.6 conda fix; use
# the env interpreter directly until then):
PYTHONPATH=src .pyve/envs/testenv/conda/bin/python scripts/spike_pytorch_determinism.py
# Exits 0 and prints "RESULT: PASS" when byte-identity holds.
```
