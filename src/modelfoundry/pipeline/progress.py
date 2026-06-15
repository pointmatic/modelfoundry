# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Materialize progress seam + fd-level output suppression (FR-3, Story D.e).

`StageObserver` is the rendering-agnostic hook the `MaterializeRunner` calls as
each pipeline stage starts / finishes / is skipped. The CLI attaches a
`rich`-based observer (`cli.commands.materialize_cmd.RichStageProgress`); the
library API stays free of any `rich` dependency. Stage-level granularity is the
D.e scope — per-epoch training tables and per-trial Optuna bars are deferred to
Story D.e.1.

`suppress_fd_output` is the reusable file-descriptor-level redirect
(`tech-spec.md` § Optimization sub-process suppression / Logging). It points
fds 1 and 2 at the null device for the duration of the context, catching output
that bypasses `sys.stdout` (e.g. torch C++ extensions writing straight to fd 1/2)
which `contextlib.redirect_stdout` does not. Story D.e.1 wires it around Optuna
trials > 0; it is landed (and tested) here as a standalone utility.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol, runtime_checkable


@runtime_checkable
class StageObserver(Protocol):
    """Lifecycle hooks the runner invokes around each materialization stage."""

    def on_stage_start(self, stage: str) -> None: ...

    def on_stage_done(self, stage: str, elapsed: float) -> None: ...

    def on_stage_skipped(self, stage: str) -> None: ...


@contextmanager
def suppress_fd_output() -> Iterator[None]:
    """Redirect fds 1 and 2 to the null device for the duration of the block.

    Flushes the Python-level streams first, dup-saves the real fds, points them
    at `os.devnull`, and restores them on exit (even on exception). Operates at
    the fd level so output that bypasses `sys.stdout`/`sys.stderr` is also caught.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    saved_fds = [os.dup(1), os.dup(2)]
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_fds[0], 1)
        os.dup2(saved_fds[1], 2)
        os.close(devnull)
        for fd in saved_fds:
            os.close(fd)
