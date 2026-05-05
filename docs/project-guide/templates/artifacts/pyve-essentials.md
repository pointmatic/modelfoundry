#### Workflow rules — pyve environment conventions

This project uses `pyve` with **two separate environments**. Picking the wrong invocation form often "works" but leads to subtle drift. Use the canonical forms below:

- **Runtime code (the package itself):** `pyve run python ...` or `pyve run <entry-point> ...`.
- **Tests:** `pyve test [pytest args]` — **not** `pyve run pytest`. Pytest is not installed in the main `.venv/`; it lives in the dev testenv at `.pyve/testenv/venv/`.
- **Dev tools (ruff, mypy, pytest):** `pyve testenv run ruff check ...`, `pyve testenv run mypy ...`.
- **Install dev tools:** `pyve testenv --install -r requirements-dev.txt`. **Do not** run `pip install -e ".[dev]"` into the main venv — that pollutes the runtime environment with test-only dependencies and breaks the two-env isolation.

If `pytest` fails with "not found" that is the signal to use `pyve test`, not to `pip install pytest` into the wrong venv.

#### LLM-internal vs. developer-facing invocation

`pyve run` is for the LLM's own Bash-tool invocations; developer-facing command suggestions use the bare form verbatim from the mode template.

- ✅ Developer-facing: `project-guide mode plan_phase`
- ❌ Developer-facing: `pyve run project-guide mode plan_phase`
- ✅ LLM Bash-tool: `pyve run project-guide mode plan_phase`

**Why:** the LLM's Bash-tool shell does not auto-activate `.venv/`, so the LLM must wrap its own commands with `pyve run`. The developer's shell is typically already pyve/direnv-activated, so the bare form resolves correctly and matches the commands quoted throughout mode templates and documentation.

**How to apply:** never prepend environment wrappers (`pyve run`, `poetry run`, `uv run`, etc.) to commands you quote back to the developer from a mode template. Use the wrapper only when you execute the command yourself through the Bash tool.

#### Python invocation rule

Always use `python`, never `python3`. The `python3` command bypasses `asdf` version shims and may resolve to the system interpreter rather than the project-pinned version, leading to subtle version mismatches.

#### `requirements-dev.txt` story-writing rule

Any story that introduces dev tooling (ruff, mypy, pytest, types-* stubs) **must** include a task to create or update `requirements-dev.txt` so that `pyve testenv --install -r requirements-dev.txt` reproduces the full dev environment in one step. This keeps the dev environment reproducible and prevents "it works on my machine" drift.

#### Editable install and testenv dependency management

LLMs often get confused about *where* to install an editable package when using pyve's two-environment model. The wrong choice "works" but creates subtle drift.

**Main environment only (preferred for library projects):**
```bash
pyve run pip install -e .
```
Then configure pytest to find the source tree without a second editable install:
```toml
# pyproject.toml
[tool.pytest.ini_options]
pythonpath = ["."]   # or ["src"] for src layout
```
`pythonpath` handles import discovery cleanly and avoids maintaining two editable installs with potentially diverging dependency resolution.

**Testenv editable install (required for CLI projects):**
```bash
pyve testenv run pip install -e .
pyve testenv --install -r requirements-dev.txt
```
Use this when tests invoke CLI entry points (console scripts), because `pythonpath` only handles imports — it does not register entry points.

**Rule of thumb:** use `pythonpath` for library/package projects; use editable install in testenv for projects whose tests exercise CLI entry points.

**Important:** When `pyve` purges and reinitialises the main environment, the testenv remains intact and the testenv editable install survives. Re-running `pyve run pip install -e .` restores the main-environment editable install. See `developer/python-editable-install.md` for the full decision guide.
