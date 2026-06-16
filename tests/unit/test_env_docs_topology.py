# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Guard the env-topology docs against the superseded micromamba layout (Story F.b.1).

The repo's Pyve environments are a venv multi-env layout (`root` / `testenv` +
lazy `smoke-pytorch` / `smoke-tensorflow` / `smoke-huggingface` / `typecheck`),
declared in `pyve.toml`. This supersedes the earlier two-micromamba design
(B.o / B.p). The first-party current-state docs must describe the live layout and
not the obsolete one; the B.o / B.p story bodies stay as historical record but
must be marked superseded so a reader does not mistake them for current state.

Scoping notes:
- `env-dependencies.md` vendors Pyve's Pyve-owned backend-vocabulary reference
  (§2/§3), which legitimately names `micromamba` and the deprecated `pyve testenv`
  init command as catalog entries — left to the vendored-template refresh per B.o.
  So those two terms are checked only in the pure-prose docs (`tech-spec.md`,
  `concept.md`), never in `env-dependencies.md`.
- A doc's trailing Change Log section is historical by nature and is excluded from
  the obsolete-marker scan.

These are doc-structure guards, not behavioral tests; they keep the env docs from
silently drifting back to the retired topology.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "docs" / "specs"

CURRENT_STATE_DOCS = ("env-dependencies.md", "tech-spec.md", "concept.md")
PURE_PROSE_DOCS = ("tech-spec.md", "concept.md")

# Unambiguous markers of the retired layout — these never appear in Pyve's own
# closed-vocabulary reference, so they flag only stale repo-state prose.
REPO_OBSOLETE_MARKERS = (
    "two micromamba envs",
    ".pyve/testenvs",
    'manifest = "environment.yml"',
)

# Pure-prose docs carry no Pyve backend vocabulary, so they must name neither the
# micromamba backend nor the deprecated `pyve testenv` verb at all.
PURE_PROSE_MARKERS = ("micromamba", "pyve testenv ")


def _read(name: str) -> str:
    return (SPECS_DIR / name).read_text(encoding="utf-8")


def _current_state_slice(name: str) -> str:
    """Doc text excluding any trailing historical Change Log section."""
    text = _read(name)
    for heading in ("## 9. Change Log", "## Change Log"):
        idx = text.find(heading)
        if idx != -1:
            return text[:idx]
    return text


def test_no_repo_obsolete_topology_markers() -> None:
    """No current-state doc prose names the retired two-micromamba layout."""
    failures = [
        f"{doc}: {marker!r}"
        for doc in CURRENT_STATE_DOCS
        for marker in REPO_OBSOLETE_MARKERS
        if marker in _current_state_slice(doc)
    ]
    assert not failures, "obsolete env-topology markers found:\n" + "\n".join(failures)


def test_pure_prose_docs_have_no_micromamba_or_deprecated_verb() -> None:
    """`tech-spec.md` / `concept.md` carry no micromamba or `pyve testenv` references."""
    failures = [
        f"{doc}: {marker!r}"
        for doc in PURE_PROSE_DOCS
        for marker in PURE_PROSE_MARKERS
        if marker in _read(doc)
    ]
    assert not failures, "stale env references in pure-prose docs:\n" + "\n".join(failures)


def test_env_dependencies_describes_venv_multi_env() -> None:
    """`env-dependencies.md` names the live venv multi-env layout."""
    text = _read("env-dependencies.md")
    for expected in ("smoke-pytorch", "typecheck", "backend = venv", "pyve test --env"):
        assert expected in text, f"env-dependencies.md missing live-topology marker {expected!r}"


def test_testenv_is_described_as_the_framework_agnostic_test_runner() -> None:
    """`testenv` owns the framework-agnostic suite (not lint-only) in the §6 coverage matrix.

    `testenv` carries the base runtime closure and runs every test that doesn't need
    a framework extra; the torch tests run in `smoke-pytorch`. The coverage matrix must
    reflect that by attributing the framework-agnostic unit tests to `testenv`.
    """
    text = _read("env-dependencies.md")
    row = re.search(r"^\| Unit tests \|[^\n]*$", text, re.MULTILINE)
    assert row, "no 'Unit tests' row found in env-dependencies.md coverage matrix"
    assert "`testenv`" in row.group(0), (
        f"framework-agnostic unit tests should run in `testenv`, got: {row.group(0)}"
    )


def test_bo_bp_stories_marked_superseded() -> None:
    """The B.o / B.p story bodies are flagged as superseded by F.b.1 (historical record)."""
    stories = _read("stories.md")
    for story_id in ("B.o", "B.p"):
        m = re.search(
            rf"### Story {re.escape(story_id)}:.*?(?=\n### Story |\n## )",
            stories,
            re.DOTALL,
        )
        assert m, f"could not locate Story {story_id} body in stories.md"
        body = m.group(0)
        assert "F.b.1" in body and "superseded" in body.lower(), (
            f"Story {story_id} body is not marked superseded by F.b.1"
        )
