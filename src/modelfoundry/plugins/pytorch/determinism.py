# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch determinism plumbing (QR-3, Story C.e).

Locks the pattern validated by the C.a architectural spike
(`docs/spikes/C.a-pytorch-determinism.md`): set `CUBLAS_WORKSPACE_CONFIG` before
the first CUDA context, enable `torch.use_deterministic_algorithms(True)`, and
seed every backend RNG before model construction. See `project-essentials.md`
§ "Determinism contract is foundational" — do not weaken any of this.

Import-safe without `[pytorch]`: `documented_hard_error_ops` is a plain tuple and
`torch` is imported lazily inside the functions.
"""

from __future__ import annotations

import os

#: cuBLAS workspace config required for deterministic GEMMs on CUDA (no-op on CPU).
CUBLAS_WORKSPACE_CONFIG = ":4096:8"

#: Ops known to hard-error under `torch.use_deterministic_algorithms(True)`.
#:
#: Per the C.a spike, **no op in the Subphase C-1 CPU vocabulary trips the guard**,
#: so this is empty. It is the place to record a future offender (the canonical
#: GPU candidates are atomic `scatter` / `index_select` backward and cuDNN conv
#: autotune) so the trainer/validator can refuse it with a clear message rather
#: than surface a raw torch RuntimeError.
documented_hard_error_ops: tuple[str, ...] = ()


def deterministic_mode_supported() -> bool:
    """True when `torch.use_deterministic_algorithms` exists on the installed build."""
    try:
        import torch
    except ImportError:
        return False
    return hasattr(torch, "use_deterministic_algorithms")


def enable_deterministic_algorithms(seed: int | None = None) -> None:
    """Enable deterministic-algorithm mode and (optionally) seed every backend RNG.

    Idempotent: safe to call more than once. `CUBLAS_WORKSPACE_CONFIG` is set only
    if unset (it must be in place before the first CUDA context). When `seed` is
    given, seeds the CPU generator plus CUDA / MPS generators where available.
    Call **before** model construction so weight init is reproducible.
    """
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", CUBLAS_WORKSPACE_CONFIG)

    import torch

    torch.use_deterministic_algorithms(True)

    if seed is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        mps = getattr(torch, "mps", None)
        mps_backend = getattr(torch.backends, "mps", None)
        if mps is not None and mps_backend is not None and mps_backend.is_available():
            mps.manual_seed(seed)
