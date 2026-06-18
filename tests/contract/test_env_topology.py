# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Env-topology contract: pin the live venv multi-env layout in `pyve.toml` (Story H.g).

The build depends on the Pyve environment topology declared in `pyve.toml`: a
`venv` multi-env layout — a `root` utility env, a default `testenv` test env, and
lazy per-framework smoke envs (`smoke-pytorch`, …) plus a `typecheck` env. This
supersedes the retired two-micromamba design (B.o / B.p, migrated in F.b.1).

`pyve.toml` is the *source of truth* for that topology — config the build reads,
not design-doc prose. This contract pins it directly, the way
`tests/plugin_contract/` pins the registered plugin surface. It replaces the
former `tests/unit/test_env_docs_topology.py`, which asserted on `docs/specs`
prose (an inverted downstream→upstream dependency that a docs reorg reddened);
this version never reads `docs/specs`, so it survives any reorganization there.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

# Repo root is two levels up from this file: tests/contract/<file>.
REPO_ROOT = Path(__file__).resolve().parents[2]
PYVE_TOML = REPO_ROOT / "pyve.toml"


def _envs() -> dict[str, dict[str, Any]]:
    """The `[env.*]` tables declared in `pyve.toml`, keyed by env name."""
    config = tomllib.loads(PYVE_TOML.read_text(encoding="utf-8"))
    envs: dict[str, dict[str, Any]] = config.get("env", {})
    return envs


def test_pyve_toml_declares_the_expected_env_topology() -> None:
    """`pyve.toml` declares the live venv multi-env layout the build depends on."""
    envs = _envs()
    # root: utility env carrying the runtime package.
    assert envs.get("root", {}).get("purpose") == "utility"
    # testenv: the default framework-agnostic test runner.
    assert envs.get("testenv", {}).get("purpose") == "test"
    assert envs.get("testenv", {}).get("default") is True
    # smoke-pytorch: a lazy, per-framework hardware-smoke env.
    assert envs.get("smoke-pytorch", {}).get("purpose") == "test"
    assert envs.get("smoke-pytorch", {}).get("lazy") is True
    # typecheck: a lazy, full-type-closure env.
    assert envs.get("typecheck", {}).get("purpose") == "test"
    assert envs.get("typecheck", {}).get("lazy") is True


def test_every_declared_env_uses_the_venv_backend() -> None:
    """Topology is venv multi-env — no env regresses to the retired micromamba/conda backend."""
    envs = _envs()
    assert envs, f"no [env.*] tables declared in {PYVE_TOML}"
    offenders = {
        name: env.get("backend") for name, env in envs.items() if env.get("backend") != "venv"
    }
    assert not offenders, f"non-venv backends found (retired micromamba layout?): {offenders}"
