# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-25 deterministic seeding contract.

`derive_seed(master_seed, scope, *salts)` produces a stable 64-bit seed for
every per-stage RNG (weight_init, data_shuffle, optuna_sampler, dropout,
`augmentation:<op_id>`). `worker_init_fn_factory(master_seed)` returns a
DataLoader `worker_init_fn` that seeds NumPy + Python `random` + (if installed)
PyTorch deterministically per worker, so output bytes are independent of
`num_workers` — the same property DataRefinery's `pipeline.workers` contract
guarantees.

**Do not weaken this contract.** See `project-essentials.md` § Determinism
contract is foundational. The byte-identity reproducibility guarantee depends on
these seeds being reproducible across runs and across worker counts.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable

import numpy as np

_NUMPY_SEED_MASK = (1 << 32) - 1  # NumPy's legacy seed API takes a 32-bit unsigned int.


def derive_seed(master_seed: int, scope: str, *salts: bytes) -> int:
    """Return a deterministic 64-bit seed derived from `(master_seed, scope, salts)`.

    Algorithm: `sha256(master_seed.to_bytes(8) + scope.encode() + b"".join(salts))`,
    take the first 8 bytes, interpret big-endian as an unsigned int.
    """
    digest = hashlib.sha256(
        master_seed.to_bytes(8, "big", signed=False)
        + scope.encode("utf-8")
        + b"".join(salts)
    ).digest()
    return int.from_bytes(digest[:8], "big")


def worker_init_fn_factory(master_seed: int) -> Callable[[int], None]:
    """Return a DataLoader `worker_init_fn` that seeds NumPy + Python `random` + Torch.

    The returned callable derives a per-worker seed from
    `(master_seed, "data_shuffle", worker_id_bytes)`, so output bytes are
    independent of `num_workers`. Torch seeding is best-effort: when the
    `[pytorch]` extra is not installed, the Torch step is skipped silently.
    """

    def _worker_init_fn(worker_id: int) -> None:
        seed = derive_seed(
            master_seed, "data_shuffle", worker_id.to_bytes(4, "big", signed=False)
        )
        random.seed(seed)
        np.random.seed(seed & _NUMPY_SEED_MASK)
        try:
            import torch  # type: ignore[import-not-found, unused-ignore]
        except ImportError:
            return
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    return _worker_init_fn
