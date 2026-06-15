# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Shared pytest fixtures (Story E.a).

Provides the temp cache roots + a wired `RuntimeConfig`, and a synthesized
DataRefinery instance via the `tests/fixtures/datarefinery_instances/builder.py`
module. `tests/` is not an importable package, so that fixtures directory is put
on `sys.path` here, letting both this conftest and tests import the builder as
`datarefinery_instances.builder`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from modelfoundry.core.config import RuntimeConfig

_FIXTURES = Path(__file__).parent / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))


@pytest.fixture
def tmp_cache_root(tmp_path: Path) -> Path:
    """The ModelFoundry cache root for a test (under pytest's `tmp_path`)."""
    return tmp_path / "mf_cache"


@pytest.fixture
def tmp_data_cache_root(tmp_path: Path) -> Path:
    """The DataRefinery (upstream) cache root for a test."""
    return tmp_path / "dr_cache"


@pytest.fixture
def runtime_config(tmp_cache_root: Path, tmp_data_cache_root: Path) -> RuntimeConfig:
    """A `RuntimeConfig` with both cache roots wired to per-test temp dirs."""
    return RuntimeConfig(cache_root=tmp_cache_root, data_cache_root=tmp_data_cache_root)


@pytest.fixture
def dr_instance(tmp_path: Path) -> Any:
    """A synthesized 100-record / 3-class / 2-split DataRefinery instance."""
    from datarefinery_instances.builder import build_dr_instance  # type: ignore[import-not-found]

    return build_dr_instance(tmp_path / "dr")
