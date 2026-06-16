# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Structural guards for the GitHub Actions ``ci.yml`` workflow (Story G.a).

These tests stand in for ``actionlint`` in the framework-agnostic suite: they
assert the workflow parses as YAML and that its required CI gates — ruff lint,
ruff format check, mypy, and the PyTorch smoke run — are present, so a future
edit cannot silently drop a gate. They guard *behavior of the CI config*, not
its exact formatting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _load() -> dict[Any, Any]:
    # dict[Any, Any] is the honest type: PyYAML parses the bare key `on:` as the
    # boolean True (YAML 1.1), so the top-level mapping is not purely str-keyed.
    doc = yaml.safe_load(CI_WORKFLOW.read_text())
    assert isinstance(doc, dict), "ci.yml did not parse to a mapping"
    return doc


def _jobs() -> dict[str, Any]:
    jobs = _load()["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _build_job() -> dict[str, Any]:
    """The single job that carries the lint/typecheck/smoke gate sequence."""
    for job in _jobs().values():
        assert isinstance(job, dict)
        runs = " ".join(step.get("run", "") for step in job.get("steps", []))
        if "pyve test" in runs:
            return job
    raise AssertionError("no job runs the pyve test gate")


def _all_run_commands() -> str:
    chunks: list[str] = []
    for job in _jobs().values():
        for step in job.get("steps", []):
            chunks.append(step.get("run", ""))
    return "\n".join(chunks)


def test_ci_workflow_is_valid_yaml() -> None:
    assert CI_WORKFLOW.is_file(), f"{CI_WORKFLOW} does not exist"
    doc = _load()
    assert isinstance(doc, dict)
    assert doc.get("jobs"), "workflow declares no jobs"


def test_ci_triggers_on_pull_request_and_push_to_main() -> None:
    doc = _load()
    # PyYAML parses the bare key `on:` as the boolean True (YAML 1.1), so accept
    # either spelling — GitHub itself reads it as the string "on".
    triggers = doc.get("on", doc.get(True))
    assert triggers is not None, "workflow declares no triggers"
    assert "pull_request" in triggers
    assert "push" in triggers
    assert "main" in triggers["push"]["branches"]


def test_ci_runs_lint_typecheck_and_pytorch_smoke_gates() -> None:
    commands = _all_run_commands()
    assert "ruff check src tests" in commands
    assert "ruff format --check src tests" in commands
    assert "mypy src tests" in commands
    assert "pyve test --env smoke-pytorch" in commands


def test_ci_matrix_has_macos_primary_and_linux_stretch() -> None:
    job = _build_job()
    include = job["strategy"]["matrix"]["include"]
    by_os = {entry["os"]: entry for entry in include}
    assert any("macos" in os_name for os_name in by_os), "no macOS runner in matrix"
    assert any("ubuntu" in os_name for os_name in by_os), "no Linux runner in matrix"

    macos = next(entry for os_name, entry in by_os.items() if "macos" in os_name)
    linux = next(entry for os_name, entry in by_os.items() if "ubuntu" in os_name)
    # Linux is the stretch entry: it must not block the run.
    assert macos["experimental"] is False
    assert linux["experimental"] is True
    assert "matrix.experimental" in job["continue-on-error"]


def test_ci_installs_pyve_cross_platform() -> None:
    # pyve is installed via `self install`, not Homebrew — `brew` is absent on
    # GitHub's ubuntu image and broke the Linux (stretch) runner (Story G.c).
    commands = _all_run_commands()
    assert "self install" in commands, "expected `pyve.sh self install` cross-platform install"
    assert "brew install" not in commands, "brew is unavailable on the Linux runner"
