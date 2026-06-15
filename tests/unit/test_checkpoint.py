# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for `pipeline.checkpoint`."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from modelfoundry.pipeline.checkpoint import Checkpoint


def _present_keys() -> dict[str, Any]:
    return {
        "epoch": 4,
        "weights": {"layer1.weight": [0.1, 0.2], "layer1.bias": [0.0]},
        "metric_value": 0.83,
        "recipe_hash16": "aaaa1111bbbb2222",
        "schema_version": 1,
    }


def test_present_keys_round_trip(tmp_path: Path) -> None:
    ck = Checkpoint(**_present_keys())
    path = tmp_path / "ckpt.pt"
    ck.save(path)
    loaded = Checkpoint.load(path)
    assert loaded.epoch == 4
    assert loaded.metric_value == 0.83
    assert loaded.recipe_hash16 == "aaaa1111bbbb2222"
    assert loaded.schema_version == 1
    assert loaded.weights == {"layer1.weight": [0.1, 0.2], "layer1.bias": [0.0]}


def test_unknown_future_keys_are_preserved(tmp_path: Path) -> None:
    # Simulate a forward-extended checkpoint written by a future version that
    # added optimizer_state / scheduler_state / rng_state.
    forward = _present_keys() | {
        "optimizer_state": {"momentum": 0.9, "step": 123},
        "scheduler_state": {"last_lr": [0.001]},
        "rng_state": b"\x00\x01\x02\x03",
    }
    path = tmp_path / "forward.pt"
    with path.open("wb") as fh:
        pickle.dump(forward, fh)

    loaded = Checkpoint.load(path)
    assert loaded.epoch == 4  # present keys still validate
    assert loaded.model_extra == {
        "optimizer_state": {"momentum": 0.9, "step": 123},
        "scheduler_state": {"last_lr": [0.001]},
        "rng_state": b"\x00\x01\x02\x03",
    }


def test_extras_survive_round_trip(tmp_path: Path) -> None:
    # Constructing with extras then save+load must keep them intact.
    ck = Checkpoint(
        **_present_keys(),
        optimizer_state={"momentum": 0.9},
    )
    path = tmp_path / "ckpt.pt"
    ck.save(path)
    loaded = Checkpoint.load(path)
    assert loaded.model_extra == {"optimizer_state": {"momentum": 0.9}}


def test_missing_required_key_raises(tmp_path: Path) -> None:
    bad = _present_keys()
    del bad["epoch"]
    path = tmp_path / "bad.pt"
    with path.open("wb") as fh:
        pickle.dump(bad, fh)
    with pytest.raises(ValidationError):
        Checkpoint.load(path)


def test_schema_version_defaults_to_one() -> None:
    keys = _present_keys()
    del keys["schema_version"]
    ck = Checkpoint(**keys)
    assert ck.schema_version == 1


def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "ckpt.pt"
    Checkpoint(**_present_keys()).save(nested)
    assert nested.is_file()


# --- E.d: per-required-key rejection + persistence byte-stability ---


@pytest.mark.parametrize("missing", ["epoch", "weights", "metric_value", "recipe_hash16"])
def test_each_required_key_missing_raises(tmp_path: Path, missing: str) -> None:
    # schema_version has a default (covered by test_schema_version_defaults_to_one);
    # every other field is required, so dropping any one fails validation on load.
    payload = _present_keys()
    del payload[missing]
    path = tmp_path / "bad.pt"
    with path.open("wb") as fh:
        pickle.dump(payload, fh)
    with pytest.raises(ValidationError):
        Checkpoint.load(path)


def test_persistence_is_byte_stable(tmp_path: Path) -> None:
    # B.k persists via pickle (NOT parquet — pickle round-trips arbitrary tensor
    # state_dicts, which a columnar format cannot). Persisting the same checkpoint
    # twice is byte-identical, and a save -> load -> save cycle reproduces the
    # original bytes.
    ck = Checkpoint(**_present_keys(), optimizer_state={"momentum": 0.9})
    first, second = tmp_path / "a.pt", tmp_path / "b.pt"
    ck.save(first)
    ck.save(second)
    assert first.read_bytes() == second.read_bytes()

    round_tripped = tmp_path / "c.pt"
    Checkpoint.load(first).save(round_tripped)
    assert round_tripped.read_bytes() == first.read_bytes()
