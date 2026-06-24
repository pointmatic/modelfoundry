# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Clip-level window aggregation (FR-AUDIO-2 / R7, Story I.o.2).

DataRefinery's `window` op slices a clip into fixed-length windows, each a
first-class record (`record_id = f"{source_record_id}__w{window_index:04d}"`).
ModelFoundry classifies *windows* (the loader feeds one feature array per
window), but the deployed unit of evaluation is the **clip**. This module owns
the consumer-side clip-level math (DataRefinery ships no aggregation op): it
regroups window-level predictions by `source_record_id` and applies the
recipe-declared `WindowAggregation.policy` to produce a clip-level `(C,)`
probability vector, over which clip-level metrics + uncertainty compute uniformly.

It layers over the already-built MC-dropout per-record outputs
(`plugins.pytorch.stochastic`): on the stochastic path the per-window `probs` are
the MC means, so aggregating them yields clip-level MC predictions for free.

`torch` is imported at the top — loaded at evaluation time, not during plugin
discovery; `evaluation.py` delegates here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import torch

from modelfoundry.core.errors import DataBindingError

Policy = Literal["mean", "logit_average", "majority_vote"]


@dataclass(frozen=True)
class ClipAggregate:
    """Clip-level aggregation of window-level predictions.

    `clip_ids` are the unique `source_record_id`s in first-appearance order;
    `probs` is the `(M, C)` clip-level probability matrix aligned with them;
    `members` carries, per clip, the original window row-indices ordered by
    `window_index` (so order-sensitive consumers and per-window uncertainty
    re-aggregation can address the source rows).
    """

    clip_ids: list[str]
    probs: torch.Tensor
    members: list[list[int]]


def verify_window_integrity(
    record_ids: Sequence[str],
    source_record_ids: Sequence[str | None],
    window_indices: Sequence[int | None],
) -> None:
    """Refuse a window whose id does not decompose into its declared parent (R7).

    DataRefinery guarantees `record_id == f"{source_record_id}__w{window_index:04d}"`
    for every window, so a missing `source_record_id` or a mismatch is a corruption
    signal (the window's grouping key is untrustworthy) — refuse before grouping
    rather than silently fold it into the wrong clip (or a ghost clip).
    """
    for record_id, source_id, window_index in zip(
        record_ids, source_record_ids, window_indices, strict=True
    ):
        if source_id is None or window_index is None:
            raise DataBindingError(
                f"window record {record_id!r} is missing source_record_id / window_index; "
                f"clip-level WindowAggregation requires every window to declare its parent "
                f"clip (vendor-spec § Audio window records / R7)",
                detail={"record_id": record_id},
            )
        expected = f"{source_id}__w{int(window_index):04d}"
        if record_id != expected:
            raise DataBindingError(
                f"window record_id {record_id!r} does not match its declared "
                f"source_record_id {source_id!r} + window_index {window_index} "
                f"(expected {expected!r}) — a dangling parent reference; refusing to "
                f"aggregate (vendor-spec § Failure modes)",
                detail={"record_id": record_id, "expected": expected},
            )


def group_windows(
    source_record_ids: Sequence[str | None],
    window_indices: Sequence[int | None],
) -> tuple[list[str], list[list[int]]]:
    """Group window row-indices by `source_record_id`, members ordered by `window_index`.

    Clips appear in first-appearance order (deterministic, input-order-driven);
    each clip's member rows are sorted by `window_index` so order-sensitive
    policies see a stable window sequence.
    """
    order: list[str] = []
    groups: dict[str, list[tuple[int, int]]] = {}
    for row, (source_id, window_index) in enumerate(
        zip(source_record_ids, window_indices, strict=True)
    ):
        key = str(source_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((int(window_index) if window_index is not None else row, row))
    members = [[row for _, row in sorted(groups[key])] for key in order]
    return order, members


def aggregate_probs(probs: torch.Tensor, members: list[list[int]], policy: Policy) -> torch.Tensor:
    """Reduce per-window `(N, C)` probabilities to clip-level `(M, C)` per `policy`."""
    rows = [_apply_policy(probs[member], policy) for member in members]
    return torch.stack(rows)


def aggregate_windows(
    probs: torch.Tensor,
    record_ids: Sequence[str],
    source_record_ids: Sequence[str | None],
    window_indices: Sequence[int | None],
    policy: Policy,
) -> ClipAggregate:
    """Integrity-check, group, and aggregate window predictions into clip-level results."""
    verify_window_integrity(record_ids, source_record_ids, window_indices)
    clip_ids, members = group_windows(source_record_ids, window_indices)
    return ClipAggregate(
        clip_ids=clip_ids, probs=aggregate_probs(probs, members, policy), members=members
    )


def _apply_policy(window_probs: torch.Tensor, policy: Policy) -> torch.Tensor:
    """One clip's `(W, C)` window probabilities → a `(C,)` clip probability vector."""
    if policy == "mean":
        return window_probs.mean(dim=0)
    if policy == "logit_average":
        # Geometric mean of the per-class probabilities, renormalized: the softmax of
        # the mean log-probability. Clamp away zeros so log() stays finite.
        safe = window_probs.clamp_min(torch.finfo(window_probs.dtype).tiny)
        return torch.softmax(safe.log().mean(dim=0), dim=0)
    if policy == "majority_vote":
        # Normalized histogram of per-window argmax votes → a (C,) vector summing to 1
        # (clip argmax = modal window class; ties broken by lowest index via argmax).
        num_classes = window_probs.shape[1]
        votes = window_probs.argmax(dim=1)
        histogram = torch.bincount(votes, minlength=num_classes).to(window_probs.dtype)
        return histogram / histogram.sum()
    raise ValueError(f"unknown window-aggregation policy {policy!r}")
