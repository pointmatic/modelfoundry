# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Forward-extensible checkpoint schema (Q16 foundation).

Pre-production writes a weights-only checkpoint per the developer directive Q16:
the on-disk format is a dict with `epoch`, `weights`, `metric_value`,
`recipe_hash16`, and `schema_version`. Future continued-training adds
`optimizer_state`, `scheduler_state`, and `rng_state` as **additive keys**
without a public-API change — `model_config = ConfigDict(extra="allow")` on
`Checkpoint` plus a structure-preserving pickle persistence guarantee that a
current loader reading a forward-extended file sees the present-and-relevant
keys without erroring on the new ones.

Persistence is `pickle` so arbitrary Python values (PyTorch tensor state_dicts,
NumPy arrays, plain dicts) round-trip. `torch.save` is itself pickle-based; a
PyTorch plugin can stack `torch.save(checkpoint.model_dump(), path)` on top
without changing the schema contract.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class Checkpoint(BaseModel):
    """The pre-production checkpoint dict — schema only; persistence is pickle."""

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    epoch: int
    weights: Any
    metric_value: float
    recipe_hash16: str
    schema_version: int = 1

    def save(self, path: str | Path) -> None:
        """Pickle the checkpoint (including any forward-extended keys) at `path`."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(self.model_dump(), fh)

    @classmethod
    def load(cls, path: str | Path) -> Checkpoint:
        """Read a checkpoint pickle, preserving any unknown future keys.

        The schema validates the present required keys; future-added keys
        survive as `model_extra` so a current loader reading a forward-extended
        checkpoint can pass them through untouched.
        """
        with Path(path).open("rb") as fh:
            payload = pickle.load(fh)
        return cls.model_validate(payload)
