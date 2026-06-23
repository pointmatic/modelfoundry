# Copyright (c) 2026 Michael Smith
# SPDX-License-Identifier: Apache-2.0
"""Patch a DataRefinery instance so ModelFoundry can find sink-persisted images.

Workaround for the DR->MF hand-off documented in
``docs/specs/modelfoundry/consumer-gap-analysis.md`` (Gap 1): the DR ``png_per_record``
sink rewrites each record's ``path`` to an instance-relative string, but MF's loader
resolves a bare ``path`` relative to the *current working directory*. MF's instance-anchored
branch keys off an ``image_path`` field resolved relative to ``<instance>/dataset/``.

This adds that sidecar: for each record with a sink ``path`` of ``images/...`` (PNGs live at
``<instance>/images/...``, while ``dataset/`` is a sibling), ``image_path = ../images/...``,
so MF resolves ``<instance>/dataset/../images/... == <instance>/images/...``.

Idempotent. Caveat: it mutates a content-addressed instance, so re-run it after any
``clean`` + re-``materialize`` of the DR data.

    python scripts/add_mf_image_path_sidecar.py --instance data/instances/<r>/<i>/0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def patch_split(jsonl: Path) -> int:
    """Add `image_path` to each record missing it; return number patched."""
    records = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    patched = 0
    for rec in records:
        if "image_path" in rec or "path" not in rec:
            continue
        rec["image_path"] = "../" + str(rec["path"])
        patched += 1
    if patched:
        jsonl.write_text("".join(json.dumps(r) + "\n" for r in records))
    return patched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add the MF image_path sidecar to an instance.")
    parser.add_argument(
        "--instance",
        type=Path,
        help="instance dir <recipe>/<input>/<seed>; default: the sole dir under data/instances",
    )
    args = parser.parse_args(argv)

    instance = args.instance
    if instance is None:
        candidates = sorted(Path("data/instances").glob("*/*/*"))
        if len(candidates) != 1:
            parser.error(f"{len(candidates)} instances found; pass --instance to choose one")
        instance = candidates[0]

    dataset_dir = instance / "dataset"
    if not dataset_dir.is_dir():
        parser.error(f"no dataset/ under {instance}")

    total = 0
    for jsonl in sorted(dataset_dir.glob("*.jsonl")):
        n = patch_split(jsonl)
        total += n
        print(f"  {jsonl.name}: +{n} image_path")
    print(f"patched {total} record(s) under {instance}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
