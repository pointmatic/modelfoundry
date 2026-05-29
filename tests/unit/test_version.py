# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Smoke test: the package version is importable and consistent."""

import modelfoundry
from modelfoundry import _version


def test_version_reexport_matches_source() -> None:
    assert modelfoundry.__version__ == _version.__version__


def test_version_is_nonempty_string() -> None:
    assert isinstance(modelfoundry.__version__, str)
    assert modelfoundry.__version__
