# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Loose-coupling guarantee — TR-7.

Pins the contract documented in `project-essentials.md` § "Loose-coupled
DataRefinery binding": ModelFoundry consumes a materialized DataRefinery
instance as a single hashed unit, and the binding is loose-coupled in both
directions:

1. **Re-materializing DataRefinery into the same cache directory is a no-op for
   ModelFoundry's cache identity.** A fresh DataRefinery instance built with the
   same shape + seed reproduces the same `(recipe_hash, input_hash, seed)`
   triple, so ModelFoundry's `data_instance_hash16` — and therefore the whole
   ModelInstance directory — is unchanged. The user re-materializes ModelFoundry
   explicitly when they want to pick up upstream changes; ModelFoundry never
   auto-detects them. Changing the DataRefinery seed perturbs the triple and so
   *does* land in a different ModelInstance directory (a correct cache miss).
2. **ModelFoundry never writes into DataRefinery's cache tree.** The vendor
   instance is consumed read-only; every byte ModelFoundry produces lives under
   ModelFoundry's own cache root.

Cache-hit semantics in the pre-production model: there is no "skip and return
the existing instance" short-circuit (OR-10 / `cache.atomic`). When the cache
identity is unchanged, the existing ModelInstance is recognized at the same key
and a re-`materialize()` without `--overwrite` is *refused* with
`ModelArtifactExistsError` rather than silently recomputed — that refusal, plus
`status()` reporting the instance already materialized at the same directory, is
how the "cache hit" guarantee surfaces here.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import ModelArtifactExistsError

torch = pytest.importorskip("torch")

_IMAGE_SIZE = 4
_NUM_CLASSES = 3
_SPLIT_COUNTS = {"train": 16, "val": 8}


@pytest.fixture(autouse=True)
def _restore_determinism() -> Iterator[None]:
    # The PyTorch plugin flips on deterministic-algorithm mode during materialize;
    # restore the process default so other tests are unaffected.
    yield
    torch.use_deterministic_algorithms(False)


def _recipe_dict() -> dict[str, Any]:
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
        "Training": {"max_epochs": 1, "batch_size": 4, "num_workers": 0, "device": "cpu"},
        "Evaluation": {
            "splits": ["val"],
            "primary_metric": "accuracy",
            "metrics": ["accuracy", "macro_f1"],
        },
    }


def _write_recipe(tmp_path: Path) -> Path:
    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(yaml.safe_dump(_recipe_dict()), encoding="utf-8")
    return recipe_path


def _fingerprint(root: Path) -> dict[str, str]:
    """SHA-256 every file under `root`, keyed by posix-relative path."""
    fp: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            fp[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return fp


def _foundry(recipe_path: Path, data: Any, config: RuntimeConfig) -> Any:
    from modelfoundry import ModelFoundry

    return ModelFoundry.from_recipe(recipe_path, data=data, config=config)


def test_rebuilt_same_seed_datarefinery_preserves_cache_identity(tmp_path: Path) -> None:
    """Same shape + same DR seed → unchanged triple → unchanged ModelInstance (cache hit)."""
    recipe_path = _write_recipe(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")

    data_a = build_dr_instance(
        tmp_path / "dr_a", split_counts=_SPLIT_COUNTS, image_size=_IMAGE_SIZE, seed=1
    )
    mf_a = _foundry(recipe_path, data_a, config)
    instance = mf_a.materialize()
    before = _fingerprint(Path(instance.path))

    # Re-materialize DataRefinery into a *different* directory with the same shape
    # and seed: the on-disk bytes differ (new path), but the canonical
    # (recipe_hash, input_hash, seed) triple is identical.
    data_b = build_dr_instance(
        tmp_path / "dr_b", split_counts=_SPLIT_COUNTS, image_size=_IMAGE_SIZE, seed=1
    )
    mf_b = _foundry(recipe_path, data_b, config)

    # Loose coupling: upstream re-materialization does not perturb the cache key.
    assert mf_b.key == mf_a.key
    assert mf_b.key.data_instance_hash16 == mf_a.key.data_instance_hash16
    assert mf_b.paths.instance_dir == mf_a.paths.instance_dir

    # The existing ModelInstance is recognized at the unchanged key (the cache hit).
    status = mf_b.status()
    assert status["materialized"] is True
    assert status["instance_dir"] == str(mf_a.paths.instance_dir)

    # Pre-production cache-hit guardrail: a re-materialize without --overwrite is
    # refused rather than recomputed, and the promoted instance is left untouched.
    with pytest.raises(ModelArtifactExistsError):
        mf_b.materialize()
    assert _fingerprint(Path(instance.path)) == before


def test_changed_datarefinery_seed_is_cache_miss(tmp_path: Path) -> None:
    """Changing the DR seed changes the triple → different `data_instance_hash16`."""
    recipe_path = _write_recipe(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")

    data_a = build_dr_instance(
        tmp_path / "dr_a", split_counts=_SPLIT_COUNTS, image_size=_IMAGE_SIZE, seed=1
    )
    data_b = build_dr_instance(
        tmp_path / "dr_b", split_counts=_SPLIT_COUNTS, image_size=_IMAGE_SIZE, seed=2
    )
    mf_a = _foundry(recipe_path, data_a, config)
    mf_b = _foundry(recipe_path, data_b, config)

    assert mf_b.key.data_instance_hash16 != mf_a.key.data_instance_hash16
    assert mf_b.key != mf_a.key
    assert mf_b.paths.instance_dir != mf_a.paths.instance_dir

    # The miss is real, not just a key difference: both materialize into their own
    # distinct directories without colliding.
    inst_a = mf_a.materialize()
    inst_b = mf_b.materialize()
    assert Path(inst_a.path) != Path(inst_b.path)
    assert mf_b.status()["materialized"] is True


def test_materialize_never_writes_to_datarefinery_cache(tmp_path: Path) -> None:
    """The bound DataRefinery instance is consumed read-only (loose coupling, direction 2)."""
    recipe_path = _write_recipe(tmp_path)
    config = RuntimeConfig(cache_root=tmp_path / "mf_cache")

    dr_root = tmp_path / "dr"
    data = build_dr_instance(dr_root, split_counts=_SPLIT_COUNTS, image_size=_IMAGE_SIZE, seed=1)
    dr_before = _fingerprint(dr_root)

    mf = _foundry(recipe_path, data, config)
    instance = mf.materialize()

    # DataRefinery's tree is byte-for-byte unchanged: no derived bytes, no
    # predicted-label columns, nothing written back into the vendor instance.
    assert _fingerprint(dr_root) == dr_before

    # Every ModelFoundry byte lives under ModelFoundry's own cache root, never
    # under the DataRefinery cache tree.
    instance_dir = Path(instance.path).resolve()
    assert config.cache_root.resolve() in instance_dir.parents
    assert dr_root.resolve() not in instance_dir.parents
    assert not instance_dir.is_relative_to(dr_root.resolve())
