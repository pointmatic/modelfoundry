# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Feature-flattening data path for the sklearn baseline (Story C.m).

`feature_matrix` turns one split of a bound DataRefinery instance into the flat
`(n_samples, n_features)` float32 matrix sklearn estimators expect. It **reuses
the PyTorch C.f `DataRefineryDataset`** — same train-fitted normalization (RGB
order, exact zero-variance guard) and same all-splits label→index scan — so the
sklearn baseline's features and class ordering match the PyTorch path exactly,
by construction (no re-implemented normalization to drift).

**Pre-production coupling:** reusing the C.f adapter means this path imports
`torch`, so materializing a `plugin: sklearn` recipe currently needs the
`[pytorch]` extra. That is the deliberate parity-over-decoupling trade for the
pre-production baseline; a torch-free normalization extraction is future work.
The import is lazy (inside `feature_matrix`), so sklearn-plugin *discovery* stays
torch-free.
"""

from __future__ import annotations

import numpy as np

from modelfoundry.pipeline.data_binding import DataRefineryInstance


def feature_matrix(
    data: DataRefineryInstance, split: str
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return `(X, y, class_names)` for `split`.

    `X` is `(n_samples, C*H*W)` float32 (the normalized CHW tensors flattened),
    `y` is the `(n_samples,)` int64 label indices, and `class_names` is the
    index-ordered class list (shared with the PyTorch path).
    """
    from modelfoundry.plugins.pytorch.data import DataRefineryDataset

    dataset = DataRefineryDataset(data, split)
    rows: list[np.ndarray] = []
    labels: list[int] = []
    for i in range(len(dataset)):
        tensor, label = dataset[i]
        rows.append(tensor.reshape(-1).numpy())
        labels.append(int(label))

    index_to_label = {idx: label for label, idx in dataset.label_to_index.items()}
    class_names = [str(index_to_label[i]) for i in range(len(index_to_label))]

    n_features = rows[0].shape[0] if rows else 0
    matrix = (
        np.stack(rows).astype(np.float32) if rows else np.empty((0, n_features), dtype=np.float32)
    )
    return matrix, np.asarray(labels, dtype=np.int64), class_names
