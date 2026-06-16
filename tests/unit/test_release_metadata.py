# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Release-hygiene guards: the version, CHANGELOG, and packaging metadata agree (Story F.c).

These pin the cross-file invariants that quietly drift at release time — the
CHANGELOG's newest entry must name the shipped `__version__`, and the
`pyproject.toml` license metadata must stay in the modern PEP 639 form (an SPDX
`license` expression, *not* a deprecated `License ::` classifier that `twine
check` would reject alongside it).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import modelfoundry

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

_VERSION_HEADER = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\]", re.MULTILINE)


def _latest_changelog_version() -> str:
    m = _VERSION_HEADER.search(CHANGELOG.read_text(encoding="utf-8"))
    assert m, "no '## [X.Y.Z]' version header found in CHANGELOG.md"
    return m.group("version")


def test_changelog_top_version_matches_package_version() -> None:
    """The newest CHANGELOG entry documents the version the package reports."""
    assert _latest_changelog_version() == modelfoundry.__version__


def test_license_metadata_is_spdx_not_classifier() -> None:
    """`pyproject.toml` uses the PEP 639 SPDX `license` field, no `License ::` classifier."""
    meta = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert meta.get("license") == "Apache-2.0", 'expected SPDX `license = "Apache-2.0"`'
    offenders = [c for c in meta.get("classifiers", []) if c.startswith("License ::")]
    assert not offenders, f"drop the deprecated License classifier(s): {offenders}"
