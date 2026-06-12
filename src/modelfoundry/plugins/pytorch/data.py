# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch `DataRefineryDataset` adapter (Story C.f).

Binds a materialized DataRefinery instance to a `torch.utils.data.Dataset`,
following the A.c spike outcome (`docs/spikes/A.c-datarefinery-binding.md`) and
the vendor-dependency-spec § "Fitted statistics ModelFoundry binds against" /
§ "Consumer-applied transformations".

Per the contract, **DataRefinery owns the statistics; the consumer owns the
application**: the materialized PNGs stay uint8, and this adapter applies the
train-fitted `normalize` / `mean_subtract` stats — in `Transformations` order,
RGB channel axis, with DataRefinery's exact `std == 0 -> 1.0` zero-variance
guard — to every split.

This module imports `torch` at the top: unlike the registry modules, it is not
loaded during plugin discovery (the trainer imports it at materialize time), so
the import-safe-without-`[pytorch]` rule does not apply here.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

from modelfoundry.core.errors import DataBindingError
from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.pipeline.seeding import derive_seed, worker_init_fn_factory
from modelfoundry.recipe.models import TrainingSpec

# Fit-on-train Transformation ops the consumer applies from persisted stats; any
# other Transformation op is pixel-altering (baked) and triggers the geometry guard.
_FIT_ON_TRAIN_OPS = frozenset({"normalize", "mean_subtract"})

_I64 = (1 << 63) - 1


class DataRefineryDataset(Dataset[tuple[torch.Tensor, int]]):
    """A `torch` dataset over one split of a bound DataRefinery instance.

    `augmentations` is the optional lazy-augmentation callable (Story C.g) applied
    to the normalized CHW tensor; `None` is the no-augmentation (val/test/CIFAR
    train without aug) path.
    """

    def __init__(
        self,
        instance: DataRefineryInstance,
        split: str,
        *,
        augmentations: Callable[[torch.Tensor], torch.Tensor] | None = None,
    ) -> None:
        self.instance = instance
        self.split = split
        self.augmentations = augmentations
        self._dataset_dir = instance.path / "dataset"
        self._label_field = instance.label_schema.get("field")

        self._refuse_unbaked_geometry_transforms()
        self._norm_steps = self._resolve_normalization_steps()
        self.label_to_index = self._derive_label_index()
        self._records = self._read_split_records()

    # --- construction helpers ---

    def _refuse_unbaked_geometry_transforms(self) -> None:
        geometry_ops = [
            op.op for op in self.instance.recipe.Transformations if op.op not in _FIT_ON_TRAIN_OPS
        ]
        if not geometry_ops:
            return
        has_sidecars = any("image_path" in rec for rec in self._iter_split_records())
        has_sinks = bool(getattr(self.instance.manifest, "sinks", None) or {})
        if not (has_sidecars or has_sinks):
            raise DataBindingError(
                f"recipe declares pixel-altering Transformation(s) {geometry_ops} but the "
                f"instance has neither aggressive sidecars nor a sink; reading from `path` "
                f"would decode pre-transform pixels (vendor-spec § Consumer-applied "
                f"transformations). Use aggressive Augmentations or a Sink, or remove the op.",
                detail={"geometry_ops": geometry_ops},
            )

    def _resolve_normalization_steps(
        self,
    ) -> list[tuple[str, torch.Tensor, torch.Tensor | None]]:
        steps: list[tuple[str, torch.Tensor, torch.Tensor | None]] = []
        for op in self.instance.recipe.Transformations:
            if op.op == "normalize":
                mean = self._read_vector(op.name, "mean")
                std = self._read_vector(op.name, "std")
                # Exact zero-variance guard (== 0.0, not a tolerance) to match DR's apply.
                std_guarded = torch.where(std == 0.0, torch.ones_like(std), std)
                steps.append(("normalize", mean.view(-1, 1, 1), std_guarded.view(-1, 1, 1)))
            elif op.op == "mean_subtract":
                mean = self._read_vector(op.name, "mean")
                steps.append(("mean_subtract", mean.view(-1, 1, 1), None))
        return steps

    def _read_vector(self, op_id: str, name: str) -> torch.Tensor:
        fitted = self.instance.fitted_statistics
        if fitted is None:
            raise DataBindingError(
                f"bound instance exposes no fitted_statistics; cannot apply op {op_id!r}",
                detail={"op_id": op_id, "name": name},
            )
        try:
            table = fitted.get_vector(op_id, name)
        except Exception as exc:  # DR raises MaterializeError on a missing vector
            raise DataBindingError(
                f"missing fitted statistic {name!r} for op {op_id!r}: {exc}",
                detail={"op_id": op_id, "name": name},
            ) from exc
        # Per the vendor spec: single `value` column, C rows in RGB axis order.
        values = table.column("value").to_pylist()
        return torch.tensor(values, dtype=torch.float32)

    def _derive_label_index(self) -> dict[object, int]:
        # Interim (pre-DR-v0.20.0 manifest.label_classes): scan ALL labeled splits
        # and sort ascending — matches the future producer computation.
        if not self._label_field:
            return {}
        labels: set[object] = set()
        for split in self.instance.splits:
            for rec in self._iter_records(split):
                value = rec.get(self._label_field)
                if value is not None:
                    labels.add(value)
        return {label: idx for idx, label in enumerate(sorted(labels, key=str))}

    def _read_split_records(self) -> list[dict[str, object]]:
        return list(self._iter_split_records())

    def _iter_split_records(self) -> list[dict[str, object]]:
        return self._iter_records(self.split)

    def _iter_records(self, split: str) -> list[dict[str, object]]:
        jsonl = self._dataset_dir / f"{split}.jsonl"
        if not jsonl.is_file():
            return []
        records: list[dict[str, object]] = []
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            if line:
                records.append(json.loads(line))
        return records

    def class_counts(self) -> list[int]:
        """Per-class record counts for this split, indexed by `label_to_index`.

        Reads labels straight from the JSONL records (no image decode), so the
        trainer (C.h) can fit `cross_entropy_class_weighted` weights cheaply. The
        i-th entry is the count of the class whose index is `i`.
        """
        counts = [0] * len(self.label_to_index)
        for record in self._records:
            value = record.get(self._label_field) if self._label_field else None
            if value is not None:
                counts[self.label_to_index[value]] += 1
        return counts

    # --- Dataset protocol ---

    def __len__(self) -> int:
        return int(self.instance.manifest.record_counts[self.split])

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        record = self._records[idx]
        image = self._decode(record)
        for kind, mean, std in self._norm_steps:
            if kind == "normalize":
                assert std is not None
                image = (image - mean) / std
            else:  # mean_subtract
                image = image - mean
        if self.augmentations is not None:
            image = self.augmentations(image)
        label_value = record.get(self._label_field) if self._label_field else None
        label = self.label_to_index[label_value] if label_value is not None else -1
        return image, label

    def _decode(self, record: dict[str, object]) -> torch.Tensor:
        # Pixel-resolution precedence: aggressive sidecar (`image_path`, relative to
        # `dataset/`) wins over the source `path` (A.c spike).
        relative = record.get("image_path")
        path = self._dataset_dir / str(relative) if relative else Path(str(record["path"]))
        with Image.open(path) as handle:
            array = np.asarray(handle.convert("RGB"), dtype=np.float32) / 255.0  # HWC, [0,1]
        return torch.from_numpy(array).permute(2, 0, 1).contiguous()  # -> CHW


def build_dataloader(
    dataset: DataRefineryDataset,
    training_spec: TrainingSpec,
    master_seed: int,
    *,
    shuffle: bool = True,
) -> DataLoader[tuple[torch.Tensor, int]]:
    """Build a deterministic `DataLoader` over `dataset`.

    Shuffle order is owned by a seeded `generator` (main process); each worker is
    seeded by the spawn-safe `worker_init_fn_factory` (B.j / C.a.1), so output
    bytes are independent of `num_workers`. `pin_memory` engages only for CUDA.
    """
    generator = torch.Generator()
    generator.manual_seed(derive_seed(master_seed, "data_shuffle") & _I64)
    return DataLoader(
        dataset,
        batch_size=training_spec.batch_size,
        shuffle=shuffle,
        num_workers=training_spec.num_workers,
        worker_init_fn=worker_init_fn_factory(master_seed),
        generator=generator,
        pin_memory=torch.cuda.is_available(),
    )
