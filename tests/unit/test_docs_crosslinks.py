# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Cross-link integrity for ModelFoundry's first-party spec docs (Story F.b).

Every relative markdown link in the project's own `docs/specs/*.md` must resolve
to a file that exists on disk, so the spec set stays internally navigable and a
release reader never hits a 404. The checker validates *file existence* of
relative links (the unambiguous, high-value failure mode); anchor-fragment
slugs are out of scope here and are swept by hand.

Vendored dependency-spec copies under `docs/specs/datarefinery/` and
`docs/specs/nbfoundry/` are excluded: their relative links are authored against
those sibling projects' own repository layouts and are correct *there*. Rewriting
them to resolve locally would corrupt the vendored copies and they would re-break
on the next vendor refresh.
"""

from __future__ import annotations

import re
from pathlib import Path

# Repo root is three levels up from this file: tests/unit/<file>.
REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "docs" / "specs"

# Vendored sibling-project specs — see module docstring.
VENDORED_SUBDIRS = ("datarefinery", "nbfoundry")

_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<target>[^)]+)\)")


def _first_party_specs() -> list[Path]:
    """First-party `docs/specs/*.md`, excluding vendored sibling-project copies."""
    out: list[Path] = []
    for md in sorted(SPECS_DIR.rglob("*.md")):
        rel = md.relative_to(SPECS_DIR)
        if rel.parts and rel.parts[0] in VENDORED_SUBDIRS:
            continue
        out.append(md)
    return out


def _broken_relative_links(md: Path) -> list[tuple[str, str]]:
    """Return `(label, target)` for each relative link in `md` whose file is missing."""
    broken: list[tuple[str, str]] = []
    for m in _LINK_RE.finditer(md.read_text(encoding="utf-8")):
        target = m.group("target")
        # External, anchor-only, and mailto links carry no local file to check.
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        if not (md.parent / path_part).resolve().exists():
            broken.append((m.group("label"), target))
    return broken


def test_first_party_specs_exist() -> None:
    """Guard against the glob silently matching nothing (e.g. a moved docs tree)."""
    specs = _first_party_specs()
    assert specs, f"no first-party spec docs found under {SPECS_DIR}"


def test_no_broken_relative_links_in_first_party_specs() -> None:
    """No relative markdown link in a first-party spec doc points at a missing file."""
    failures: dict[str, list[tuple[str, str]]] = {}
    for md in _first_party_specs():
        broken = _broken_relative_links(md)
        if broken:
            failures[str(md.relative_to(REPO_ROOT))] = broken
    assert not failures, "broken relative cross-links:\n" + "\n".join(
        f"  {doc}: [{label}]({target})"
        for doc, links in failures.items()
        for label, target in links
    )
