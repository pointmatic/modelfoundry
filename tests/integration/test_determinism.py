# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Determinism integration tests — TR-5 / FR-25 / QR-3.

Materializing the same `(recipe, data_instance, seed, variant)` twice produces a
**byte-identical** ModelInstance, excluding only the wall-clock metadata
(`manifest.created_at` / `manifest.elapsed_seconds`, and the human-readable
`report.md`, which renders those same wall-clock stage timings by design). And
the output bytes are independent of DataLoader `num_workers` — the per-record
seeding contract from B.j's `worker_init_fn`. See `project-essentials.md` §
Determinism contract is foundational.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

from modelfoundry.core.config import RuntimeConfig

torch = pytest.importorskip("torch")

_IMAGE_SIZE = 4
_NUM_CLASSES = 3


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    # The PyTorch plugin flips on deterministic-algorithm mode during materialize;
    # restore the process default so other tests are unaffected.
    yield
    torch.use_deterministic_algorithms(False)


def _recipe_dict(num_workers: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plugin": "pytorch",
        "seed": 7,
        "Data": {"recipe": "dr_recipe.yml"},
        "Architecture": {
            "num_classes": _NUM_CLASSES,
            "layers": [
                {"op": "Flatten"},
                {
                    "op": "Linear",
                    "in_features": _IMAGE_SIZE * _IMAGE_SIZE * 3,
                    "out_features": _NUM_CLASSES,
                },
            ],
        },
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.01},
        "Training": {
            "max_epochs": 1,
            "batch_size": 4,
            "num_workers": num_workers,
            "device": "cpu",
        },
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1"],
        },
    }


def _instance_fingerprint(instance_dir: Path) -> dict[str, str]:
    """SHA-256 every file under the instance dir, modulo wall-clock metadata.

    `manifest.json` is normalized to drop `created_at` / `elapsed_seconds`;
    `report.md` is skipped entirely (it renders wall-clock stage timings). Every
    other byte must be reproducible from `(recipe, data, seed)`.
    """
    fp: dict[str, str] = {}
    for path in sorted(instance_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(instance_dir).as_posix()
        if rel.endswith("report.md"):
            continue
        data = path.read_bytes()
        if rel == "manifest.json":
            manifest = json.loads(data)
            for wallclock in ("created_at", "elapsed_seconds"):
                manifest.pop(wallclock, None)
            data = json.dumps(manifest, sort_keys=True).encode("utf-8")
        fp[rel] = hashlib.sha256(data).hexdigest()
    return fp


def _materialize(tmp_path: Path, data: Any, *, tag: str, num_workers: int) -> Path:
    from modelfoundry import ModelFoundry

    recipe_path = tmp_path / f"recipe_{tag}.yml"
    recipe_path.write_text(yaml.safe_dump(_recipe_dict(num_workers)), encoding="utf-8")
    config = RuntimeConfig(cache_root=tmp_path / f"cache_{tag}")
    return Path(ModelFoundry.from_recipe(recipe_path, data=data, config=config).materialize().path)


# The determinism-critical training outputs. `num_workers` is a recipe field, so
# it legitimately perturbs recipe.yml / manifest.recipe_hash / the checkpoint's
# embedded recipe_hash16 across worker counts — the B.j `worker_init_fn` contract
# guarantees only that the trained *output* is worker-count-independent, so the
# num_workers test compares these artifacts rather than the whole instance.
_OUTPUT_ARTIFACTS = (
    "model/weights/state_dict.pt",
    "evaluation/predictions.parquet",
    "evaluation/metrics.json",
    "training/history.parquet",
)


def _output_bytes(instance_dir: Path) -> dict[str, bytes]:
    out = {rel: (instance_dir / rel).read_bytes() for rel in _OUTPUT_ARTIFACTS}
    assert out, "no output artifacts found"
    return out


def test_repeated_materialize_is_byte_identical(tmp_path: Path) -> None:
    data = build_dr_instance(
        tmp_path / "dr", split_counts={"train": 16, "val": 8}, image_size=_IMAGE_SIZE
    )
    first = _instance_fingerprint(_materialize(tmp_path, data, tag="a", num_workers=0))
    second = _instance_fingerprint(_materialize(tmp_path, data, tag="b", num_workers=0))
    assert first == second


def test_output_bytes_independent_of_num_workers(tmp_path: Path) -> None:
    data = build_dr_instance(
        tmp_path / "dr", split_counts={"train": 32, "val": 8}, image_size=_IMAGE_SIZE
    )
    outputs = {
        nw: _output_bytes(_materialize(tmp_path, data, tag=f"nw{nw}", num_workers=nw))
        for nw in (1, 2, 4)
    }
    assert outputs[1] == outputs[2] == outputs[4]
