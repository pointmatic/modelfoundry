# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Runtime (execution-context) configuration.

`RuntimeConfig` carries the non-recipe knobs ModelFoundry needs at run time:
the two cache roots, the operator-log level/target, the plugin search path, and
the per-invocation overrides (`variant`, `seed`, `overwrite`). Precedence is
recipe (semantic) > CLI flags (execution context) > env vars > built-in
defaults; this module owns the env-vars → defaults rungs. CLI flags and recipe
overrides are applied by their respective callers on top of the value built
here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

ENV_PREFIX = "MODELFOUNDRY_"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_root: Path = Path("./models")
    data_cache_root: Path = Path("./data")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_target: str = "stderr"
    plugin_path: tuple[Path, ...] = ()
    variant: str | None = None
    seed: int | None = None
    overwrite: bool = False
    # DataLoader worker count (Story I.e.1, Option A): execution context, not a
    # recipe field. Output-neutral by the E.e `worker_init_fn` contract; default 0
    # is PyTorch-portable (single-process, no spawn surprises) — tune per machine
    # via `--num-workers` / `MODELFOUNDRY_NUM_WORKERS`.
    num_workers: int = 0

    @classmethod
    def from_env(cls, prefix: str = ENV_PREFIX, **overrides: Any) -> RuntimeConfig:
        """Build a `RuntimeConfig` from environment variables, then `overrides`.

        Reads `<prefix>CACHE_ROOT`, `<prefix>DATA_CACHE_ROOT`, `<prefix>LOG_LEVEL`,
        `<prefix>LOG_TARGET`, `<prefix>PLUGIN_PATH` (comma-separated → tuple), and
        `<prefix>NUM_WORKERS` (int).
        Unset vars fall back to field defaults. Explicit `overrides` (e.g. parsed
        CLI flags) win over env-derived values.
        """
        env = os.environ
        values: dict[str, Any] = {}
        if raw := env.get(f"{prefix}CACHE_ROOT"):
            values["cache_root"] = Path(raw)
        if raw := env.get(f"{prefix}DATA_CACHE_ROOT"):
            values["data_cache_root"] = Path(raw)
        if raw := env.get(f"{prefix}LOG_LEVEL"):
            values["log_level"] = raw
        if raw := env.get(f"{prefix}LOG_TARGET"):
            values["log_target"] = raw
        if raw := env.get(f"{prefix}PLUGIN_PATH"):
            values["plugin_path"] = tuple(Path(p) for p in raw.split(",") if p)
        if raw := env.get(f"{prefix}NUM_WORKERS"):
            values["num_workers"] = int(raw)
        values.update(overrides)
        return cls(**values)
