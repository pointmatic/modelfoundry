# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Structural guards for the GitHub Actions ``publish.yml`` workflow (Story G.b).

Stand-in for ``actionlint`` in the framework-agnostic suite: assert the publish
workflow parses, fires on ``v*.*.*`` tags, builds an sdist + wheel, and uploads
via PyPI Trusted Publishing (OIDC ``id-token: write`` + the official PyPA
action, *no* API token in secrets). Guards behavior of the CI config so a future
edit cannot silently reintroduce a token credential or drop the OIDC grant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PUBLISH_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "publish.yml"


def _load() -> dict[Any, Any]:
    # dict[Any, Any]: PyYAML parses the bare key `on:` as the boolean True.
    doc = yaml.safe_load(PUBLISH_WORKFLOW.read_text())
    assert isinstance(doc, dict), "publish.yml did not parse to a mapping"
    return doc


def _jobs() -> dict[str, Any]:
    jobs = _load()["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _all_steps() -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for job in _jobs().values():
        assert isinstance(job, dict)
        for step in job.get("steps", []):
            assert isinstance(step, dict)
            steps.append(step)
    return steps


def test_publish_workflow_is_valid_yaml() -> None:
    assert PUBLISH_WORKFLOW.is_file(), f"{PUBLISH_WORKFLOW} does not exist"
    assert _load().get("jobs"), "workflow declares no jobs"


def test_publish_triggers_on_version_tag_push() -> None:
    doc = _load()
    triggers = doc.get("on", doc.get(True))
    assert triggers is not None, "workflow declares no triggers"
    tags = triggers["push"]["tags"]
    assert any("v" in t and "*" in t for t in tags), f"expected a v*.*.* tag, got {tags}"


def test_publish_builds_sdist_and_wheel() -> None:
    runs = "\n".join(step.get("run", "") for step in _all_steps())
    assert "python -m build" in runs


def test_publish_uses_trusted_publishing_without_a_token() -> None:
    job = next(iter(_jobs().values()))
    # OIDC: the job must request the short-lived id-token PyPI exchanges for an
    # upload credential.
    assert job.get("permissions", {}).get("id-token") == "write"
    # Upload goes through the official PyPA action ...
    uses = [step.get("uses", "") for step in _all_steps()]
    assert any("pypa/gh-action-pypi-publish" in u for u in uses)
    # ... and no API token / password is threaded — that is the point of OIDC.
    raw = PUBLISH_WORKFLOW.read_text()
    assert "password:" not in raw
    assert "PYPI_API_TOKEN" not in raw


def test_publish_runs_in_the_pypi_environment() -> None:
    # A GitHub `environment: pypi` lets deployment protection rules gate the
    # publish; its name must match the PyPI trusted-publisher config.
    job = next(iter(_jobs().values()))
    environment = job["environment"]
    name = environment["name"] if isinstance(environment, dict) else environment
    assert name == "pypi"
