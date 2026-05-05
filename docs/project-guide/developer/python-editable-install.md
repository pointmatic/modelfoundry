# Python Editable Installs — Developer Guide

This guide explains how to set up editable installs for Python projects so that test runners and CLI tools resolve to your local source. It covers both general Python patterns and pyve-specific conventions.

---

## What Is an Editable Install?

`pip install -e .` installs a package in *editable* mode: instead of copying source files into `site-packages`, pip registers the source directory itself. Any change to the source is immediately visible to code that imports the package — no reinstall needed.

---

## The Two Approaches

There are two ways to make your source tree importable by pytest without copying files:

### Approach 1 — `pythonpath` in pytest config (recommended for library projects)

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
pythonpath = ["."]   # or ["src"] for src layout
```

pytest prepends the listed path to `sys.path` before running. Your package is importable without any `pip install -e .`.

**Pros:**
- Zero installation step — works in a fresh virtual environment
- No risk of version skew between the main venv and a second editable install
- Works with any virtualenv tool, including pyve

**Cons:**
- Does **not** register console scripts or entry points
- Tests that invoke CLI entry points by name (e.g. `subprocess.run(["my-tool", ...])`) will not find the command

### Approach 2 — Editable install in the test environment

```bash
pip install -e .
pip install -r requirements-dev.txt
```

Installs the package as editable into the active virtualenv, registering both imports and entry points.

**Pros:**
- Fully realistic — entry points, console scripts, and imports all work
- Matches what end users install from PyPI

**Cons:**
- Requires a reinstall after renaming entry points or changing `pyproject.toml` scripts
- In two-environment setups (see pyve section below), you may need to install in both envs

---

## Decision Guide

| Project type | Recommended approach |
|---|---|
| Library / importable package, no CLI tests | `pythonpath = ["."]` |
| CLI tool, tests invoke entry points | Editable install in test env |
| CLI tool, tests import the package only (no subprocess calls) | Either — `pythonpath` is simpler |

---

## Pyve Projects

pyve maintains **two separate environments**: the main `.venv/` (runtime) and a testenv at `.pyve/testenv/venv/` (dev tools + test runner). This separation keeps test dependencies out of the runtime environment.

### When to install where

**Main environment** — install if you use the package interactively (REPL, scripts, `pyve run <entry-point>`):

```bash
pyve run pip install -e .
```

**Testenv** — install if your tests invoke CLI entry points (console scripts). `pythonpath` alone does not register entry points:

```bash
pyve testenv run pip install -e .
pyve testenv --install -r requirements-dev.txt
```

**Preferred pattern for most pyve projects** — install editable in the main env only, then use `pythonpath` so the testenv picks up the source tree without a second install:

```toml
# pyproject.toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

```bash
pyve run pip install -e .        # main env — for interactive use
pyve testenv --install -r requirements-dev.txt   # testenv — dev tools only
```

This avoids maintaining two editable installs with potentially diverging dependency resolution.

### Surviving a pyve purge

When `pyve` purges and reinitialises the main environment (`.venv/`), the testenv at `.pyve/testenv/venv/` is **not touched** — it survives the purge. After a purge, restore the main-env editable install with:

```bash
pyve run pip install -e .
```

The testenv editable install (if you have one) remains intact and does not need reinstalling.

### Checking which env is active

```bash
pyve run pip show <package-name>   # main env
pyve testenv run pip show <package-name>   # testenv
```

If the package is missing from one env, install it there as shown above.

---

## Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `pip install -e ".[dev]"` into main venv | Test-only deps pollute the runtime env | Use `pyve testenv --install -r requirements-dev.txt` instead |
| `pyve run pytest` instead of `pyve test` | pytest not found — it lives in testenv | Use `pyve test [args]` |
| No editable install or `pythonpath`, but tests import the package | `ModuleNotFoundError` at test time | Add `pythonpath = ["."]` to pytest config or `pyve testenv run pip install -e .` |
| Editable install in testenv but entry point not found | `FileNotFoundError` running the CLI | Also install editable in main env, or invoke via `python -m <module>` |
