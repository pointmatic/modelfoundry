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

# Fit-on-train ops the consumer applies from persisted stats; any other
# (Transformation) op is pixel-altering (baked) and triggers the geometry guard.
# `audio_normalize` is the Featurizations-section audio analogue (Subphase I-1).
_FIT_ON_TRAIN_OPS = frozenset({"normalize", "mean_subtract", "audio_normalize"})

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
        self._audio_norm_steps = self._resolve_audio_normalization_steps()
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

    def _resolve_audio_normalization_steps(
        self,
    ) -> list[tuple[str, torch.Tensor, torch.Tensor]]:
        # Audio analogue of `_resolve_normalization_steps` (Story I.n): scan the
        # recipe's `Featurizations` section for `audio_normalize` and read its
        # per-mel-bin `mean`/`std` (length `n_mels`). The broadcast axis differs from
        # the image CHW path — for the `(1, n_mels, n_frames)` feature tensor the mel
        # bins live on axis 1, so stats reshape to `(1, n_mels, 1)` (per-mel-bin over
        # the frame axis), NOT `(-1, 1, 1)`. Stats are read `float64` (Q3) so the apply
        # promotes the `float32` mel array; `Featurizations` is read tolerantly (image
        # recipes omit the section / leave it empty).
        steps: list[tuple[str, torch.Tensor, torch.Tensor]] = []
        for op in getattr(self.instance.recipe, "Featurizations", None) or []:
            if op.op == "audio_normalize":
                mean = self._read_vector(op.name, "mean", dtype=torch.float64)
                std = self._read_vector(op.name, "std", dtype=torch.float64)
                # Same exact zero-variance guard as the image path (std == 0 -> 1.0 at
                # apply; the persisted std is left unmodified).
                std_guarded = torch.where(std == 0.0, torch.ones_like(std), std)
                steps.append(("audio_normalize", mean.view(1, -1, 1), std_guarded.view(1, -1, 1)))
        return steps

    def _read_vector(
        self, op_id: str, name: str, *, dtype: torch.dtype = torch.float32
    ) -> torch.Tensor:
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
        # Per the vendor spec: single `value` column, rows in axis order (RGB channels
        # for image normalize; mel bins for audio_normalize).
        values = table.column("value").to_pylist()
        return torch.tensor(values, dtype=dtype)

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

    def record_ids(self) -> list[str]:
        """The split's `record_id`s in iteration order (for predictions alignment).

        With `shuffle=False` + `num_workers=0`, an evaluation pass visits records
        in this order, so the i-th prediction belongs to `record_ids()[i]`.
        """
        return [str(rec.get("record_id", idx)) for idx, rec in enumerate(self._records)]

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
        if "feature_path" in record:
            # Audio feature-array branch (Subphase I-1): a prepared (n_mels, n_frames)
            # float32 mel array, loaded raw. `feature_path` is authoritative over a
            # stray `path` (Q6). Image augmentations / image-normalize do not apply.
            features = self._decode_features(record)
            # Per-mel-bin `audio_normalize` (Story I.n): apply the train-fitted stats on
            # the mel axis. float64 stats promote the float32 mel; restore float32 after.
            for _kind, mel_mean, mel_std in self._audio_norm_steps:
                features = ((features - mel_mean) / mel_std).to(torch.float32)
            return features, self._label_for(record)
        image = self._decode(record)  # 0-255 pixel units — the units DR fit stats in
        if self.augmentations is not None:
            # Augment on the [0,1] image BEFORE normalization (H.d), then restore 0-255 for
            # the fitted-stat normalize below. Color augmentations (brightness/contrast/
            # saturation/hue) assume [0,1]/uint8 semantics; applied to the *standardized*
            # tensor they corrupt the train distribution so val_loss explodes and the CNN
            # generalizes at chance. Geometry ops (crop/flip) are range-invariant.
            image = self.augmentations(image / 255.0) * 255.0
        if self._norm_steps:
            # DataRefinery fits `normalize` / `mean_subtract` on the uint8 PNG pixels
            # (promoted to float64), i.e. in 0-255 units, and persists the stats for the
            # consumer to apply. Per vendor-dependency-spec § "Normalization is applied by
            # the consumer" the contract is: decode the uint8 image, convert to float, apply
            # (x - mean) / std — with NO [0,1] rescale. Dividing by 255 first (the pre-H.a
            # bug) collapses every pixel to ~-1.9 / std ~0.13 and the model can't learn.
            for kind, mean, std in self._norm_steps:
                if kind == "normalize":
                    assert std is not None
                    image = (image - mean) / std
                else:  # mean_subtract
                    image = image - mean
        else:
            # No fit-on-train normalization declared: scale to [0,1] so a bare CNN still
            # receives sensibly-ranged inputs.
            image = image / 255.0
        return image, self._label_for(record)

    def _label_for(self, record: dict[str, object]) -> int:
        label_value = record.get(self._label_field) if self._label_field else None
        return self.label_to_index[label_value] if label_value is not None else -1

    def _decode(self, record: dict[str, object]) -> torch.Tensor:
        path = self._resolve_image_path(record)
        with Image.open(path) as handle:
            # Keep raw 0-255 pixels — the units DataRefinery fit normalize/mean_subtract
            # stats in. `__getitem__` standardizes (or, with no fit-on-train op, scales
            # to [0,1]). HWC float32.
            array = np.asarray(handle.convert("RGB"), dtype=np.float32)
        return torch.from_numpy(array).permute(2, 0, 1).contiguous()  # -> CHW, 0-255

    def _resolve_image_path(self, record: dict[str, object]) -> Path:
        # Pixel-resolution precedence: an aggressive sidecar (`image_path`, relative
        # to `dataset/`) wins over the source `path` (A.c spike). A bare `path` is
        # either an ABSOLUTE source path (normal flow — used as-is) or an
        # INSTANCE-relative string written by DataRefinery's `png_per_record` sink
        # (e.g. `images/<split>/<Class>/<id>.png`). The instance-relative case MUST
        # anchor to the instance root, never the process CWD (Gap 1) — a bare
        # `Path(...)` would silently resolve against CWD and die mid-training.
        relative = record.get("image_path")
        if relative:
            return self._dataset_dir / str(relative)
        bare = Path(str(record["path"]))
        return bare if bare.is_absolute() else self.instance.path / bare

    def _decode_features(self, record: dict[str, object]) -> torch.Tensor:
        # Audio feature-array load (Subphase I-1, vendor-spec § Audio feature-array
        # persistence). The raw float32 mel array is preserved verbatim — no [0,1]
        # rescale, no normalize here (Story I.n applies `audio_normalize`).
        path = self._resolve_feature_path(record)
        array = np.load(path)
        if array.ndim != 2:  # Q4: mono decode ⇒ always rank-2 (n_mels, n_frames)
            raise DataBindingError(
                f"audio feature array at {path} has ndim={array.ndim}; expected 2-D "
                f"(n_mels, n_frames) per vendor-spec Q4",
                detail={"feature_path": str(path), "ndim": int(array.ndim)},
            )
        contiguous = np.ascontiguousarray(array, dtype=np.float32)
        # Consumer owns the channel-dim insertion (Q4) → (1, n_mels, n_frames).
        return torch.from_numpy(contiguous).unsqueeze(0)

    def _resolve_feature_path(self, record: dict[str, object]) -> Path:
        # Q1: `feature_path` is INSTANCE-root-relative (a sibling of `dataset/`, the
        # I.k sink-`path` bucket) — NOT `dataset/`-relative like `image_path`. Q5: it
        # may be nested (`features/<split>/<clip>/<id>.npy`); join the POSIX string
        # onto the instance root verbatim.
        return self.instance.path / str(record["feature_path"])


def build_dataloader(
    dataset: DataRefineryDataset,
    training_spec: TrainingSpec,
    master_seed: int,
    *,
    num_workers: int = 0,
    shuffle: bool = True,
) -> DataLoader[tuple[torch.Tensor, int]]:
    """Build a deterministic `DataLoader` over `dataset`.

    Shuffle order is owned by a seeded `generator` (main process); each worker is
    seeded by the spawn-safe `worker_init_fn_factory` (B.j / C.a.1), so output
    bytes are independent of `num_workers`. `num_workers` is execution context
    (Story I.e.1, from `RuntimeConfig`), not a recipe field. `pin_memory` engages
    only for CUDA.
    """
    generator = torch.Generator()
    generator.manual_seed(derive_seed(master_seed, "data_shuffle") & _I64)
    return DataLoader(
        dataset,
        batch_size=training_spec.batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        worker_init_fn=worker_init_fn_factory(master_seed),
        generator=generator,
        pin_memory=torch.cuda.is_available(),
    )
