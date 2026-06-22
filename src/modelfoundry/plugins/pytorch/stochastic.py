# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""MC-dropout stochastic inference (R2.1 / R2.4, Story H.m).

The default inference path (`persistence._forward_proba`, `evaluation._infer`)
runs a single `.eval()` forward pass with `Dropout` inactive — point estimates.
This module is the **stochastic** path requested by a recipe's
`Inference: {mode: mc_dropout, mc_samples: T}` block: `Dropout` is kept active
and the model runs **T** forward passes, so the spread across passes carries the
predictive uncertainty (aggregated + persisted in Story H.n).

Determinism (R2.4): each pass is seeded from
`derive_seed(master_seed, "dropout", pass_index_bytes)` — the existing seeded-
dropout discipline (`trainer.py` uses `derive_seed(seed, "dropout")` for the
training loop), extended with a per-pass salt so the whole T-pass sequence is
reproducible independently of prior RNG state. Same `(recipe, data, seed,
variant)` → byte-identical per-pass outputs, subject to the documented
determinism caveats. See `project-essentials.md` § Determinism contract.

`torch` is imported at the top — loaded at inference time, not during plugin
discovery; the plugin delegates here lazily.
"""

from __future__ import annotations

import torch
from torch import nn

from modelfoundry.pipeline.seeding import derive_seed


def enable_mc_dropout(model: nn.Module) -> None:
    """Put `model` in eval mode but keep every `Dropout`-family module active.

    This is the MC-dropout idiom: BatchNorm and the like use their frozen
    running statistics (eval), while dropout continues to sample — the only
    source of inter-pass variation. Mutates `model` in place.
    """
    model.eval()
    for module in model.modules():
        if isinstance(module, nn.modules.dropout._DropoutNd):
            module.train()


def mc_forward_proba(
    model: nn.Module,
    batch: torch.Tensor,
    *,
    n_samples: int,
    master_seed: int,
) -> torch.Tensor:
    """Run `n_samples` active-dropout forward passes over `batch`.

    Returns a `(T, N, C)` tensor of per-pass class probabilities (softmax over
    the logits), where `T == n_samples`. Each pass `t` seeds the global torch RNG
    from `derive_seed(master_seed, "dropout", t)` before the forward, so the
    sequence reproduces byte-for-byte across runs (R2.4). Aggregation of the
    passes is deferred to Story H.n.
    """
    enable_mc_dropout(model)
    device = next(model.parameters()).device
    batch = batch.to(device)
    passes: list[torch.Tensor] = []
    with torch.no_grad():
        for t in range(n_samples):
            salt = t.to_bytes(4, "big", signed=False)
            torch.manual_seed(derive_seed(master_seed, "dropout", salt))
            logits = model(batch)
            passes.append(torch.softmax(logits, dim=1).cpu())
    return torch.stack(passes)
