# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `pipeline.seeding`."""

from __future__ import annotations

import hashlib
import importlib
import random

import numpy as np
import pytest

from modelfoundry.pipeline.seeding import derive_seed, worker_init_fn_factory

# --- derive_seed ---


def test_derive_seed_is_deterministic() -> None:
    assert derive_seed(7, "weight_init") == derive_seed(7, "weight_init")


def test_derive_seed_is_64_bit_unsigned() -> None:
    seed = derive_seed(7, "weight_init")
    assert 0 <= seed < (1 << 64)


def test_different_scopes_yield_different_seeds() -> None:
    a = derive_seed(7, "weight_init")
    b = derive_seed(7, "data_shuffle")
    c = derive_seed(7, "optuna_sampler")
    assert len({a, b, c}) == 3


def test_different_master_seeds_yield_different_seeds() -> None:
    assert derive_seed(1, "weight_init") != derive_seed(2, "weight_init")


def test_different_salts_yield_different_seeds() -> None:
    a = derive_seed(7, "augmentation", b"flip")
    b = derive_seed(7, "augmentation", b"crop")
    assert a != b


def test_salts_concatenate_in_order() -> None:
    # b"ab" as one salt must equal b"a", b"b" as two salts.
    assert derive_seed(7, "x", b"ab") == derive_seed(7, "x", b"a", b"b")


def test_explicit_algorithm() -> None:
    # Pin the documented algorithm against an external sha256 invocation.
    master = 1234
    scope = "augmentation:flip"
    salt = b"\x00\x00\x00\x05"
    expected = int.from_bytes(
        hashlib.sha256(master.to_bytes(8, "big") + scope.encode("utf-8") + salt).digest()[:8],
        "big",
    )
    assert derive_seed(master, scope, salt) == expected


# --- worker_init_fn_factory ---


def test_worker_init_fn_seeds_numpy_and_random_reproducibly() -> None:
    init = worker_init_fn_factory(master_seed=42)
    init(0)
    rnd_0_a, np_0_a = random.random(), np.random.rand()
    init(0)
    rnd_0_b, np_0_b = random.random(), np.random.rand()
    assert (rnd_0_a, np_0_a) == (rnd_0_b, np_0_b)


def test_worker_init_fn_different_workers_yield_different_streams() -> None:
    init = worker_init_fn_factory(master_seed=42)
    init(0)
    stream_0 = (random.random(), np.random.rand())
    init(1)
    stream_1 = (random.random(), np.random.rand())
    assert stream_0 != stream_1


def test_worker_init_fn_independent_of_master_seed_when_constant() -> None:
    init = worker_init_fn_factory(master_seed=99)
    init(0)
    expect_rnd = random.random()
    init(0)
    assert random.random() == expect_rnd


def test_worker_init_fn_seeds_torch_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Inject a fake `torch` module so the optional-torch branch is exercised
    # without requiring the [pytorch] extra at test time.
    import sys
    import types

    seen: dict[str, int] = {}

    fake_torch = types.ModuleType("torch")

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return False

    fake_torch.cuda = _Cuda  # type: ignore[attr-defined]
    fake_torch.manual_seed = lambda s: seen.__setitem__("manual_seed", s)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    # Force the lazy `import torch` inside the worker_init_fn to pick up the fake.
    importlib.invalidate_caches()
    worker_init_fn_factory(master_seed=7)(3)
    assert "manual_seed" in seen
    assert isinstance(seen["manual_seed"], int)
