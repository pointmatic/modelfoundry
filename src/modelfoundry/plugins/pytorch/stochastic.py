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

from dataclasses import dataclass

import torch
from torch import nn

from modelfoundry.pipeline.seeding import derive_seed


def mc_pass_seed(master_seed: int, pass_index: int) -> int:
    """Seed for MC-dropout pass `pass_index` — the dropout salt convention (R2.4).

    `derive_seed(master_seed, "dropout", pass_index)` — the established
    seeded-dropout scope (`trainer.py`) extended with a per-pass salt. Centralized
    here so every stochastic call site (the per-batch `mc_forward_proba`, the
    evaluation T-pass loop) derives the seed identically.
    """
    return derive_seed(master_seed, "dropout", pass_index.to_bytes(4, "big", signed=False))


@dataclass(frozen=True)
class MCAggregate:
    """Aggregation of T MC-dropout passes (R2.2).

    `mean` is the `(N, C)` mean class-probability distribution — the deployed
    point prediction. `predictive_entropy` is the `(N,)` Shannon entropy of that
    mean distribution (total predictive uncertainty). `mc_variance` is the `(N,)`
    population variance of the per-class probabilities across passes, averaged
    over classes (a spread-across-passes uncertainty signal).
    """

    mean: torch.Tensor
    predictive_entropy: torch.Tensor
    mc_variance: torch.Tensor


def mc_aggregate(passes: torch.Tensor) -> MCAggregate:
    """Aggregate a `(T, N, C)` stack of per-pass probabilities into `MCAggregate`."""
    mean = passes.mean(dim=0)
    safe = mean.clamp_min(torch.finfo(mean.dtype).tiny)
    predictive_entropy = -(mean * safe.log()).sum(dim=1)
    mc_variance = passes.var(dim=0, unbiased=False).mean(dim=1)
    return MCAggregate(mean=mean, predictive_entropy=predictive_entropy, mc_variance=mc_variance)


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
            torch.manual_seed(mc_pass_seed(master_seed, t))
            logits = model(batch)
            passes.append(torch.softmax(logits, dim=1).cpu())
    return torch.stack(passes)
