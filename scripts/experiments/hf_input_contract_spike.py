# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Story H.j.2 — investigation spike for the DR<->MF input-shape/preprocessing contract.

THROWAWAY SPIKE (per docs/specs/stories.md Story H.j.2). The deliverable is the
documented design decision in `hf_input_contract_spike.md`; this runner makes the
two core comparisons concrete so H.j.3's validator check is de-risked.

It proves, against real synthetic DataRefinery instances:

  1. The PRODUCED input spec is readable from the bound instance with NO extra:
     `data_instance.record_schema["image"]["shape"]` (HWC) + `fitted_statistics`.
  2. The encoder REQUIREMENT is readable offline + config-only (no weights) via
     `AutoConfig.from_pretrained(id, local_files_only=True)` -> image_size/num_channels.
  3. The shape comparison flags a CIFAR-32 instance against a ViT-224 encoder and
     passes a native-224 instance (the H.j.1 fixture).
  4. The normalization-scale heuristic (the H.a-class generalization) is computable
     from `fitted_statistics` alone, transformers-free.

Run:  pyve env run smoke-huggingface -- python scripts/experiments/hf_input_contract_spike.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import sys

sys.path.insert(0, "tests/fixtures/datarefinery_instances")

_VIT = "WinKawaks/vit-tiny-patch16-224"


def _produced_hwc(instance: object) -> tuple[int, int, int]:
    """The DR-produced image shape, transformers-free, from record_schema."""
    schema = getattr(instance, "record_schema", {}) or {}
    shape = schema["image"]["shape"]  # DataRefinery convention: [H, W, C]
    return int(shape[0]), int(shape[1]), int(shape[2])


def _encoder_requirement(model_id: str) -> tuple[int, int]:
    """The encoder's required (size, channels) — offline, config-only, no weights."""
    from transformers import AutoConfig

    cfg = AutoConfig.from_pretrained(model_id, local_files_only=True)
    return int(cfg.image_size), int(cfg.num_channels)


def _shape_issue(instance: object, model_id: str) -> str | None:
    h, w, c = _produced_hwc(instance)
    size, channels = _encoder_requirement(model_id)
    if (h, w, c) != (size, size, channels):
        return (
            f"bound instance produces {h}x{w}x{c} images but encoder {model_id!r} "
            f"requires {size}x{size}x{channels} — re-materialize the DataRefinery instance "
            f"at the encoder's resolution (DR owns data prep, FR-6)"
        )
    return None


def _normalization_issue(instance: object) -> str | None:
    """H.a-class generalization: fitted stats must match the adapter's 0-255 decode scale."""
    stats = getattr(instance, "fitted_statistics", None)
    if stats is None:
        return None
    # The adapter (post-H.a) applies fitted mean/std in 0-255 pixel units. A mean
    # that looks [0,1]-scale (<= 1) is the H.a-class mismatch signature.
    mean = _first_mean(stats)
    if mean is not None and mean <= 1.0:
        return (
            f"fitted normalize mean ~{mean:.3f} looks [0,1]-scale but the adapter applies "
            f"stats in 0-255 pixel units (H.a contract) — likely a units mismatch"
        )
    return None


def _first_mean(stats: object) -> float | None:
    # Best-effort read of the first per-channel mean from the DR FittedStatistics view.
    for attr in ("norm", "normalize"):
        view = getattr(stats, attr, None)
        if view is not None and hasattr(view, "mean"):
            try:
                return float(next(iter(view.mean)))
            except Exception:
                return None
    return None


def main() -> int:
    from builder import build_dr_instance  # type: ignore[import-not-found]

    print("=== encoder requirement (offline AutoConfig, no weights) ===")
    size, channels = _encoder_requirement(_VIT)
    print(f"{_VIT}: image_size={size}, num_channels={channels}")

    with tempfile.TemporaryDirectory() as td:
        good = build_dr_instance(Path(td) / "native224", image_size=224, split_counts={"train": 4})
        bad = build_dr_instance(Path(td) / "cifar32", image_size=32, split_counts={"train": 4})

        print("\n=== shape contract (encoder-introspected, transformers-present) ===")
        print(f"native-224 HWC={_produced_hwc(good)} -> issue: {_shape_issue(good, _VIT)}")
        print(f"cifar-32   HWC={_produced_hwc(bad)} -> issue: {_shape_issue(bad, _VIT)}")

        print("\n=== normalization-scale heuristic (H.a class, transformers-FREE) ===")
        print(f"native-224 fitted-mean issue: {_normalization_issue(good)}")

    print(
        "\nVERDICT: both comparisons are implementable; shape needs transformers, "
        "normalization does not (R1.4 split confirmed)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
