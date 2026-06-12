# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Story C.a architectural spike — deterministic PyTorch training loop (THROWAWAY).

Validates the most uncertain architectural assumption before the production
PyTorch plugin lands: does

    torch.use_deterministic_algorithms(True)
  + CUBLAS_WORKSPACE_CONFIG=:4096:8
  + the worker_init_fn_factory from `modelfoundry.pipeline.seeding` (B.j)

produce a **byte-identical** `model.state_dict()` across two runs of a minimal
CNN training loop on a synthetic image dataset, CPU-only, independent of
`num_workers ∈ {1, 2, 4}`?

Run:  micromamba run -p .pyve/envs/testenv/conda python scripts/spike_pytorch_determinism.py
      (or `pyve run python ...` once Pyve v3.0.6 lands the conda `env run` fix)

This is a spike: it writes nothing to disk, prints a findings summary, and exits
0 when byte-identity holds. The deliverable is
docs/spikes/C.a-pytorch-determinism.md, not this script.
"""

from __future__ import annotations

import hashlib
import os

# CUBLAS_WORKSPACE_CONFIG must be set before the first CUDA context; harmless on
# CPU but we set it here to mirror the production determinism module (C.e).
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import functools
import pickle
import random

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from modelfoundry.pipeline.seeding import derive_seed, worker_init_fn_factory

MASTER_SEED = 20260611
NUM_CLASSES = 4
DEVICE = torch.device("cpu")  # CPU-only: macOS-MPS is sidestepped (see outcome doc).
_I64 = (1 << 63) - 1  # torch.Generator.manual_seed wants a signed-int64-range value.


class TinyCNN(nn.Module):
    """Minimal 2-conv CNN → global average pool → linear head."""

    def __init__(self, num_classes: int = NUM_CLASSES) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(3, 8, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(8, 16, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Linear(16, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = self.pool(x).flatten(1)
        return self.fc(x)


class SyntheticImages(Dataset[tuple[torch.Tensor, int]]):
    """32 synthetic 3x8x8 images.

    `__getitem__` seeds a *per-record* generator from `(MASTER_SEED, idx)` — never
    from worker-local RNG state — so the produced pixels are identical regardless
    of which worker (or how many workers) materialize the record. This is the
    per-record-seed pattern DataRefinery's `pipeline.workers` contract uses; the
    loader's `worker_init_fn` additionally pins any incidental worker RNG.
    """

    def __init__(self, n: int = 32, num_classes: int = NUM_CLASSES) -> None:
        self.n = n
        self.num_classes = num_classes

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        seed = derive_seed(MASTER_SEED, "augmentation:synthetic", idx.to_bytes(4, "big")) & _I64
        gen = torch.Generator().manual_seed(seed)
        img = torch.rand(3, 8, 8, generator=gen)
        label = idx % self.num_classes
        return img, label


def _seed_worker(master_seed: int, worker_id: int) -> None:
    """Picklable, module-level equivalent of B.j's `worker_init_fn`.

    B.j's `worker_init_fn_factory` returns a *closure*, which the macOS `spawn`
    start method cannot pickle (it crashes `DataLoader(num_workers>0)`). A
    module-level function bound to its `master_seed` via `functools.partial` is
    picklable and survives `spawn` — the fix the production data adapter (C.f)
    and trainer (C.h) must adopt. See the outcome doc.
    """
    seed = derive_seed(master_seed, "data_shuffle", worker_id.to_bytes(4, "big", signed=False))
    random.seed(seed)
    np.random.seed(seed & ((1 << 32) - 1))
    torch.manual_seed(seed & _I64)


def _setup_determinism(deterministic: bool) -> None:
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.use_deterministic_algorithms(deterministic)
    random.seed(MASTER_SEED)
    np.random.seed(MASTER_SEED & ((1 << 32) - 1))
    torch.manual_seed(MASTER_SEED)


def _state_dict_hash(model: nn.Module) -> str:
    """SHA-256 over every parameter/buffer's raw bytes in sorted-key order."""
    h = hashlib.sha256()
    sd = model.state_dict()
    for key in sorted(sd):
        tensor = sd[key].detach().cpu().contiguous()
        h.update(key.encode("utf-8"))
        h.update(tensor.numpy().tobytes())
    return h.hexdigest()


def run_once(num_workers: int, *, deterministic: bool = True) -> str:
    """Train the CNN for 2 epochs and return the state-dict hash."""
    _setup_determinism(deterministic)

    # Weight init is seeded independently of the global RNG so it cannot drift
    # with data-loader RNG consumption.
    torch.manual_seed(derive_seed(MASTER_SEED, "weight_init") & _I64)
    model = TinyCNN().to(DEVICE)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    loss_fn = nn.CrossEntropyLoss()

    dataset = SyntheticImages()
    shuffle_gen = torch.Generator().manual_seed(derive_seed(MASTER_SEED, "data_shuffle") & _I64)
    loader = DataLoader(
        dataset,
        batch_size=8,
        shuffle=True,
        num_workers=num_workers,
        worker_init_fn=functools.partial(_seed_worker, MASTER_SEED),
        generator=shuffle_gen,
    )

    model.train()
    for _epoch in range(2):
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(xb.to(DEVICE)), yb.to(DEVICE))
            loss.backward()
            optimizer.step()

    return _state_dict_hash(model)


def main() -> int:
    print(f"torch {torch.__version__} | device {DEVICE} | master_seed {MASTER_SEED}")
    print(f"CUBLAS_WORKSPACE_CONFIG={os.environ.get('CUBLAS_WORKSPACE_CONFIG')!r}")
    print(f"multiprocessing start method: {torch.multiprocessing.get_start_method()}\n")

    # 0. Integration finding: is B.j's worker_init_fn closure picklable (spawn-safe)?
    print("[0] B.j worker_init_fn_factory picklability (spawn requirement)")
    try:
        pickle.dumps(worker_init_fn_factory(MASTER_SEED))
        print("    → picklable: True")
    except (pickle.PicklingError, AttributeError, TypeError) as exc:
        print(f"    → picklable: False — {type(exc).__name__}: {exc}")
        print("    → spike uses functools.partial(_seed_worker, MASTER_SEED) instead "
              "(the fix C.f/C.h must adopt).\n")

    # 1. Byte-identity across worker counts, deterministic mode ON.
    print("[1] deterministic=True, num_workers ∈ {1, 2, 4}")
    by_workers = {nw: run_once(nw, deterministic=True) for nw in (1, 2, 4)}
    for nw, digest in by_workers.items():
        print(f"    num_workers={nw}: {digest}")
    worker_invariant = len(set(by_workers.values())) == 1
    print(f"    → byte-identical across worker counts: {worker_invariant}\n")

    # 2. Run-to-run reproducibility (repeat num_workers=2).
    print("[2] reproducibility: repeat num_workers=2")
    repeat = run_once(2, deterministic=True)
    reproducible = repeat == by_workers[2]
    print(f"    repeat: {repeat}\n    → reproducible: {reproducible}\n")

    # 3. Contrast: deterministic mode OFF (documents CPU behaviour).
    print("[3] contrast: deterministic=False, num_workers=2 (x2)")
    nondet_a = run_once(2, deterministic=False)
    nondet_b = run_once(2, deterministic=False)
    print(f"    run A: {nondet_a}\n    run B: {nondet_b}")
    print(f"    → equal without the guard (CPU): {nondet_a == nondet_b}")
    print(f"    → matches deterministic-mode hash: {nondet_a == by_workers[2]}\n")

    ok = worker_invariant and reproducible
    print(f"RESULT: {'PASS' if ok else 'FAIL'} — "
          f"byte-identity {'holds' if ok else 'BROKEN'} under deterministic mode + worker_init_fn")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
