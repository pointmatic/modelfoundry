# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-5 atomic temp-then-promote, `FAILED` marker, and `--overwrite` trashing.

The cache must only ever contain complete, valid ModelInstances. Every pipeline
write targets a per-run temp directory under `instances/.tmp/<run-id>/`; on clean
exit the temp dir is swapped into its final location in a single `os.replace`
(`materialize_temp_dir`). On failure the temp dir is left in place with a
`FAILED` JSON marker for diagnosis, and the final path is never touched.

**Same-filesystem requirement.** `os.replace` is atomic only within one
filesystem; a cross-device rename raises `EXDEV`. The temp dir lives under the
cache root precisely so the rename stays intra-filesystem. The cross-device
guard below surfaces a clear message instead of a deep `EXDEV`.

**Concurrency (OR-10).** Pre-production, `materialize` is serialized externally
by the user. If a final instance directory already exists at promote time
(a concurrent run won the race, or a stale instance is present without
`--overwrite`), promotion fails cleanly with `ModelArtifactExistsError` rather
than clobbering. The post-production file-lock protocol is a future upgrade.
"""

from __future__ import annotations

import contextlib
import json
import os
import traceback
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from modelfoundry.cache.identity import CacheKey
from modelfoundry.cache.layout import CachePaths
from modelfoundry.core.errors import CacheError, MaterializeError, ModelArtifactExistsError

FAILED_MARKER = "FAILED"


def _device_id(path: Path) -> int:
    """Return `st_dev` for `path` (wrapped so the cross-device guard is patchable)."""
    return os.stat(path).st_dev


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%fZ")


@contextlib.contextmanager
def materialize_temp_dir(
    cache_root: str | Path,
    cache_key: CacheKey,
    *,
    run_id: str | None = None,
) -> Iterator[Path]:
    """Yield a fresh temp dir; promote it to the final instance path on clean exit.

    On any exception raised inside the `with` block, a `FAILED` marker is written
    into the temp dir (capturing the failing stage, error class, and message) and
    the temp dir is left intact for diagnosis; the exception propagates unchanged.
    """
    paths = CachePaths(cache_root, cache_key)
    run_id = run_id or uuid.uuid4().hex
    temp_dir = paths.tmp_dir(run_id)
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        yield temp_dir
    except BaseException as exc:
        _write_failed_marker(temp_dir, exc, stage=getattr(exc, "stage", None))
        raise

    _promote(temp_dir, paths.instance_dir)


def _promote(temp_dir: Path, final_dir: Path) -> None:
    if not temp_dir.is_dir():
        raise MaterializeError(f"temp dir does not exist, cannot promote: {temp_dir}")

    if final_dir.exists():
        raise ModelArtifactExistsError(
            f"instance already exists at {final_dir}; re-run with overwrite to replace it",
            detail={"instance_dir": str(final_dir)},
        )

    final_parent = final_dir.parent
    final_parent.mkdir(parents=True, exist_ok=True)

    temp_dev = _device_id(temp_dir.parent)
    final_dev = _device_id(final_parent)
    if temp_dev != final_dev:
        raise MaterializeError(
            f"cannot atomically promote across filesystems: "
            f"temp_dir={temp_dir} (st_dev={temp_dev}), "
            f"final_dir={final_dir} (st_dev={final_dev}). The cache root and its "
            f"temp dir must share a filesystem; configure --cache-root accordingly."
        )

    try:
        os.replace(temp_dir, final_dir)
    except OSError as exc:
        raise MaterializeError(
            f"atomic promote failed for {temp_dir} -> {final_dir}: {exc}"
        ) from exc


def _write_failed_marker(temp_dir: Path, exc: BaseException, stage: str | None) -> None:
    """Write the `FAILED` JSON marker into `temp_dir`; no-op if the dir is gone."""
    if not temp_dir.is_dir():
        return
    payload = {
        "stage": stage,
        "error_class": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
        "marked_at": _utc_stamp(),
    }
    (temp_dir / FAILED_MARKER).write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def trash_existing(cache_root: str | Path, key: CacheKey) -> Path:
    """Move the existing instance for `key` into `.trash/<timestamp>/...` and return the path.

    Used by `--overwrite`: the displaced instance is *moved*, not deleted, so a
    later `clean` can age it out. Raises `CacheError` if no instance exists.
    """
    paths = CachePaths(cache_root, key)
    instance_dir = paths.instance_dir
    if not instance_dir.exists():
        raise CacheError(
            f"no instance to trash at {instance_dir}",
            detail={"instance_dir": str(instance_dir)},
        )

    dest = (
        paths.trash_dir(_utc_stamp())
        / key.recipe_hash16
        / key.data_instance_hash16
        / str(key.seed)
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(instance_dir, dest)
    except OSError as exc:
        raise CacheError(
            f"failed to trash {instance_dir} -> {dest}: {exc}",
            detail={"instance_dir": str(instance_dir), "trash_dir": str(dest)},
        ) from exc
    return dest
