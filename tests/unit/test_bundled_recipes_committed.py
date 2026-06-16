# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Guard: the recipes the suite + README bind to ship in the repo (Story G.c).

A clean checkout (CI) only has what git tracks. `recipes/cifar10-base.yaml` — the
DataRefinery base recipe the CLI + integration tests, the README quickstart, and
the `cifar10_resnet20` deliverable all reference — was silently caught by a
`recipes/cifar10*.yaml` .gitignore pattern, so CI's first run hit
FileNotFoundError. These pin that the bundled recipes exist, are not ignored, and
are tracked, so a fresh clone reproduces the test suite.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Recipes a fresh checkout must carry: bound by tests / README / the deliverable.
BUNDLED_RECIPES = ("recipes/cifar10-base.yaml", "recipes/cifar10_resnet20.yml")


def _git() -> str:
    git = shutil.which("git")
    if git is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("git unavailable or not a git checkout")
    return git


@pytest.mark.parametrize("recipe", BUNDLED_RECIPES)
def test_bundled_recipe_exists_on_disk(recipe: str) -> None:
    assert (REPO_ROOT / recipe).is_file(), f"{recipe} missing from the working tree"


@pytest.mark.parametrize("recipe", BUNDLED_RECIPES)
def test_bundled_recipe_is_not_gitignored(recipe: str) -> None:
    # `git check-ignore -q` exits 0 when the path matches an ignore rule, 1 when
    # it does not. A bundled recipe must NOT be ignored — else a clean clone lacks it.
    result = subprocess.run([_git(), "check-ignore", "-q", recipe], cwd=REPO_ROOT, check=False)
    assert result.returncode == 1, f"{recipe} is git-ignored — it won't reach a clean checkout"


@pytest.mark.parametrize("recipe", BUNDLED_RECIPES)
def test_bundled_recipe_is_tracked(recipe: str) -> None:
    # `git ls-files --error-unmatch` exits 0 only when the path is tracked.
    result = subprocess.run(
        [_git(), "ls-files", "--error-unmatch", recipe],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, f"{recipe} is untracked — run `git add {recipe}`"
