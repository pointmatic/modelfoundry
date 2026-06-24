# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the clip-level window-aggregation engine (Story I.o.2).

Exercises the pure-torch aggregation math in `plugins.pytorch.aggregation`:
ordered grouping of window-level predictions by `source_record_id`, the three
recipe-declared policies (`mean` / `logit_average` / `majority_vote`) each
producing a clip-level `(C,)` probability vector, and the dangling-key integrity
refusal (a window whose `record_id` does not decompose into its declared
`source_record_id` + `window_index`).
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from torch import Tensor  # noqa: E402

from modelfoundry.core.errors import DataBindingError  # noqa: E402
from modelfoundry.plugins.pytorch.aggregation import (  # noqa: E402
    aggregate_windows,
    group_windows,
    verify_window_integrity,
)

# --- grouping ---


def test_group_windows_preserves_clip_first_appearance_order() -> None:
    source_ids = ["a/clip_0", "a/clip_0", "b/clip_1", "b/clip_1"]
    window_idx = [0, 1, 0, 1]
    clip_ids, members = group_windows(source_ids, window_idx)
    assert clip_ids == ["a/clip_0", "b/clip_1"]
    assert members == [[0, 1], [2, 3]]


def test_group_windows_orders_members_by_window_index() -> None:
    # Windows may appear out of order in the JSONL; members are sorted by window_index
    # so order-sensitive policies see a stable sequence.
    source_ids = ["c/clip_0", "c/clip_0", "c/clip_0"]
    window_idx = [2, 0, 1]
    clip_ids, members = group_windows(source_ids, window_idx)
    assert clip_ids == ["c/clip_0"]
    assert members == [[1, 2, 0]]  # original indices ordered by window_index 0,1,2


# --- policies ---


def _probs() -> Tensor:
    # Two clips x two windows x two classes.
    probs: Tensor = torch.tensor(
        [
            [0.8, 0.2],  # clip_0 / w0
            [0.6, 0.4],  # clip_0 / w1
            [0.3, 0.7],  # clip_1 / w0
            [0.1, 0.9],  # clip_1 / w1
        ]
    )
    return probs


def _ids() -> tuple[list[str], list[str], list[int]]:
    record_ids = ["k/0__w0000", "k/0__w0001", "k/1__w0000", "k/1__w0001"]
    source_ids = ["k/0", "k/0", "k/1", "k/1"]
    window_idx = [0, 1, 0, 1]
    return record_ids, source_ids, window_idx


def test_mean_policy_averages_per_class_probabilities() -> None:
    record_ids, source_ids, window_idx = _ids()
    agg = aggregate_windows(_probs(), record_ids, source_ids, window_idx, "mean")
    assert agg.clip_ids == ["k/0", "k/1"]
    expected = torch.tensor([[0.7, 0.3], [0.2, 0.8]])
    assert torch.allclose(agg.probs, expected, atol=1e-6)


def test_logit_average_policy_is_renormalized_geometric_mean() -> None:
    record_ids, source_ids, window_idx = _ids()
    probs = _probs()
    agg = aggregate_windows(probs, record_ids, source_ids, window_idx, "logit_average")
    # Reference: softmax of the per-class mean log-probability (geometric mean, renormalized).
    ref = torch.stack(
        [
            torch.softmax(probs[[0, 1]].log().mean(dim=0), dim=0),
            torch.softmax(probs[[2, 3]].log().mean(dim=0), dim=0),
        ]
    )
    assert torch.allclose(agg.probs, ref, atol=1e-6)
    assert torch.allclose(agg.probs.sum(dim=1), torch.ones(2), atol=1e-6)


def test_majority_vote_policy_is_normalized_argmax_histogram() -> None:
    # clip_0: both windows vote class 0 → [1.0, 0.0]; a split-vote clip → [0.5, 0.5].
    probs = torch.tensor(
        [
            [0.8, 0.2],  # vote 0
            [0.6, 0.4],  # vote 0
            [0.7, 0.3],  # vote 0
            [0.2, 0.8],  # vote 1
        ]
    )
    record_ids = ["k/0__w0000", "k/0__w0001", "k/1__w0000", "k/1__w0001"]
    source_ids = ["k/0", "k/0", "k/1", "k/1"]
    agg = aggregate_windows(probs, record_ids, source_ids, [0, 1, 0, 1], "majority_vote")
    expected = torch.tensor([[1.0, 0.0], [0.5, 0.5]])
    assert torch.allclose(agg.probs, expected, atol=1e-6)


# --- dangling-key integrity refusal ---


def test_verify_window_integrity_accepts_well_formed_windows() -> None:
    verify_window_integrity(["k/0__w0000", "k/0__w0001"], ["k/0", "k/0"], [0, 1])


def test_dangling_source_record_id_is_refused() -> None:
    # The I.l dangling fixture's shape: record_id does not decompose into its declared
    # source_record_id + window_index — a corruption signal, not a groupable window.
    with pytest.raises(DataBindingError, match="source_record_id"):
        verify_window_integrity(["__orphan__/clip_x__w0000"], ["__ghost_clip__"], [0])


def test_missing_source_record_id_is_refused() -> None:
    with pytest.raises(DataBindingError, match="source_record_id"):
        verify_window_integrity(["k/0__w0000"], [None], [0])


def test_aggregate_windows_refuses_before_grouping_on_dangling_key() -> None:
    with pytest.raises(DataBindingError, match="source_record_id"):
        aggregate_windows(
            torch.tensor([[0.5, 0.5]]),
            ["__orphan__/clip_x__w0000"],
            ["__ghost_clip__"],
            [0],
            "mean",
        )
