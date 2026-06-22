# tech_spec.md — Pyve (Bash)

This document defines **how** the `pyve` project is built -- architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns.

For requirements and behavior, see [`features.md`](features.md). For the implementation plan, see [`stories.md`](stories.md). For project-specific must-know facts (workflow rules, architecture quirks, hidden coupling), see [`project-essentials.md`](project-essentials.md) — `plan_tech_spec` populates it after this document is approved. For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Runtime & Tooling

| Item | Value |
|------|-------|
| **Language** | Bash (4.x+) |
| **Shell mode** | `set -euo pipefail` |
| **Platforms** | macOS (zsh default shell, BSD userland), Linux (Ubuntu, GNU userland) |
| **Package manager** | N/A (single script + sourced libraries, no package registry) |
| **Linter** | ShellCheck |
| **Test runners** | Bats (unit), pytest (integration) |
| **CI** | GitHub Actions |
| **Coverage** | Codecov (via pytest-cov) |

---

## Dependencies

### Runtime Dependencies (must be pre-installed)

| Dependency | Purpose | Required? |
|------------|---------|-----------|
| Bash 4.x+ | Script execution | Yes |
| asdf **or** pyenv | Python version management | One required |
| direnv | Auto-activation of environments | Required for `--init` (skip with `--no-direnv`) |
| micromamba | Conda-compatible environment backend | Only for micromamba backend |
| grep, sed, awk, mktemp, mv | Standard POSIX utilities | Yes |

### Development Dependencies (`requirements-dev.txt`)

| Package | Purpose |
|---------|---------|
| pytest | Integration test runner |
| pytest-cov | Coverage reporting |
| pytest-xdist | Parallel test execution |
| bats-core | Unit test runner (installed via brew/apt) |
| shellcheck | Shell script linter (installed via brew/apt) |
| black | Python code formatter (lint check) |
| flake8 | Python style checker (lint check) |

---

## Package Structure

```
pyve/
├── pyve.sh                          # Thin entry point — globals, sourcing, top-level dispatcher, legacy/unknown flag catches, main()
├── lib/
│   ├── utils.sh                     # Logging, prompts, .gitignore management, config parsing, validation
│   ├── ui/
│   │   ├── core.sh                  # Core module of the extractable lib/ui/ library: colors, symbols, prompts, run_cmd, banners, is_verbose() gate
│   │   ├── run.sh                   # Quiet-replay-on-failure subprocess wrapper (run_quiet, run_quiet_with_label); honors PYVE_VERBOSE
│   │   ├── progress.sh              # Step counter (step_begin/_end_ok/_end_fail), backgrounded spinner, ASCII progress bar; honors PYVE_VERBOSE and TTY
│   │   └── select.sh                # Arrow-key single/multi-select prompts (ui_select / ui_multi_select); numbered TTY-fallback for non-interactive callers
│   ├── env_detect.sh                # Shell profile sourcing, version manager detection (asdf/pyenv), is_asdf_active gate, direnv check
│   ├── backend_detect.sh            # Backend auto-detection from project files, backend validation
│   ├── micromamba_core.sh           # Micromamba binary detection, version, location
│   ├── micromamba_env.sh            # Environment file parsing, naming, creation, lock file validation
│   ├── micromamba_bootstrap.sh      # Micromamba download and installation (interactive + auto)
│   ├── version.sh                   # Version comparison, installation validation, config writing
│   ├── testenvs.sh                  # Named-testenv config foundation (M.g): read [tool.pyve.testenvs], predicates, path resolver
│   ├── pyve_testenvs_helper.py      # Python tomllib helper for lib/testenvs.sh (V3 bash-array-literal wire format)
│   └── commands/                    # One file per top-level command; each defines a function with the same name as the file
│       ├── init.sh                  # init() — full project initialization (both backends)
│       ├── purge.sh                 # purge() — removal of pyve artifacts
│       ├── update.sh                # update() — non-destructive upgrade (config + managed files + project-guide)
│       ├── check.sh                 # check() — diagnostics with 0/1/2 exit codes
│       ├── status.sh                # status() — read-only project state dashboard
│       ├── lock.sh                  # lock() — conda-lock wrapper (micromamba only)
│       ├── run.sh                   # run() — execute command in project environment
│       ├── test.sh                  # test() — pytest in dev/test environment
│       ├── testenv.sh               # testenv() dispatcher + testenv_init/install/purge/run
│       ├── python.sh                # python() dispatcher + python_set/python_show
│       └── self.sh                  # self() dispatcher + self_install/self_uninstall
├── tests/
│   ├── unit/                        # Bats unit tests (white-box, one file per lib module)
│   │   ├── test_utils.bats
│   │   ├── test_backend_detect.bats
│   │   ├── test_config_parse.bats
│   │   ├── test_env_naming.bats
│   │   ├── test_lock_validation.bats
│   │   ├── test_micromamba_bootstrap.bats
│   │   ├── test_micromamba_core.bats
│   │   ├── test_reinit.bats
│   │   ├── test_testenvs.bats       # M.g: lib/testenvs.sh foundation tests
│   │   ├── test_testenvs_state.bats  # M.h.1: .state read/write helpers
│   │   ├── test_testenvs_migration.bats # M.h.2: legacy-layout migration helper
│   │   ├── test_testenvs_activate.bats  # M.h.3: resolver fallback + sweep guard
│   │   ├── test_testenv_install_lock.bats  # M.j: mkdir-based install lock + --no-wait
│   │   ├── test_testenv_conda.bats     # M.k: conda backend init/install + inherit resolution
│   │   ├── test_testenv_venv_manifest.bats # M.l: venv source dispatch (requirements/extra/fallback)
│   │   ├── test_test_env_resolver.bats # M.m: pyve test --env <name> resolver + .state last-used touch
│   │   ├── test_test_env_lazy_autoprovision.bats # M.n: lazy auto-provisioning + PYVE_NO_AUTO_PROVISION opt-out
│   │   ├── test_test_env_advisory.bats     # M.o: generalized silent-skip advisory (root + all declared envs)
│   │   ├── test_testenv_list_prune.bats    # M.p: testenv list (table) + testenv prune (orphan/--unused-since/--all)
│   │   ├── test_lock_per_env.bats          # M.q: pyve lock --env <name> + --all (per-testenv conda-lock dispatch)
│   │   ├── test_test_env_matrix.bats       # M.r: pyve test --env a,b,c matrix (serial, exit aggregation, headers)
│   │   └── test_version.bats
│   ├── integration/                 # pytest integration tests (black-box, one file per workflow)
│   │   ├── conftest.py              # Shared fixtures (temp dirs, pyve runner)
│   │   ├── test_venv_workflow.py
│   │   ├── test_micromamba_workflow.py
│   │   ├── test_auto_detection.py
│   │   ├── test_bootstrap.py
│   │   ├── test_cross_platform.py
│   │   ├── test_reinit.py
│   │   ├── test_run_command.py
│   │   └── test_testenv.py
│   ├── helpers/
│   │   ├── test_helper.bash         # Bats helper (setup, teardown, assertions, sources all lib modules)
│   │   └── pyve_test_helpers.py     # pytest helper (PyveRunner, temp project scaffolding)
│   └── fixtures/                    # Test data (sample environment.yml, conda-lock.yml, etc.)
├── docs/
│   ├── guides/
│   │   └── project_guide.md         # LLM-assisted project creation workflow
│   └── specs/
│       ├── features.md              # Requirements (what)
│       ├── tech_spec.md             # Architecture (how) — this file
│       ├── stories.md               # Implementation plan (when)
│       ├── testing_spec.md          # Testing strategy details
│       └── pyve-run-examples.md     # Usage examples for pyve run
├── .github/workflows/
│   └── test.yml                     # CI pipeline (unit, integration, micromamba, lint, coverage)
├── Makefile                         # Convenience targets (test, test-unit, test-integration, coverage)
├── pytest.ini                       # pytest configuration (markers, coverage, output)
├── requirements-dev.txt             # Python dev dependencies
├── LICENSE                          # Apache-2.0
├── README.md                        # User documentation
└── CONTRIBUTING.md                  # Contribution guidelines
```

---

## Key Component Design

### `pyve.sh` — Thin Entry Point

`pyve.sh` is the dispatcher and process-wide concern manager (~500–650 lines post-K.l, was ~3,500 pre-K). It owns process-wide concerns and command routing; it does **not** own command implementations. Top-level command logic lives in `lib/commands/<name>.sh` (see next subsection).

The line-count floor is set by the explicit-sourcing rule (project-essentials): 8 lib + 11 lib/commands source blocks at 4 lines each ≈ 95–130 lines. Plus header/license/config (~70), `main()` dispatcher (~230 lines for 11 commands + 9 legacy-flag catches + 3 universal flags), `legacy_flag_error` / `unknown_flag_error` (~50), and the three universal-flag implementation functions (`show_help` / `show_version` / `show_config`, ~150). The original 200–300 target predates the explicit-sourcing rule and was revised in K.m once the structural floor was empirically clear.

**What lives in `pyve.sh`:**

- Shebang, copyright/SPDX header, `set -euo pipefail`.
- Process-wide globals (see table below).
- The library sourcing block (helpers first, then commands).
- Universal flag handling: `--help` / `-h`, `--version` / `-v`, `--config` / `-c`. Implementations: `show_help()` (top-level man-page-style help describing all 11 commands and universal flags), `show_version()` (single-line `pyve version X.Y.Z`), `show_config()` (current detected config: VERSION, defaults, configured backend, micromamba availability, env file detection).
- The top-level `case`-block dispatcher that maps a subcommand name to its `lib/commands/*.sh` function.
- `legacy_flag_error()` — the Category B hard-error catcher for renamed/removed flags and subcommands. Three lines per catch arm; emits a precise migration error and exits non-zero.
- `unknown_flag_error()` — closest-match suggestion for typos within a valid subcommand (uses `_edit_distance()` from `lib/ui/core.sh`).
- `main()` — entry point that drives universal-flag handling, legacy/unknown-flag catches, and dispatcher invocation in that order.

**What does NOT live in `pyve.sh`:**

- Command implementations (`init`, `purge`, `update`, `check`, `status`, `lock`, `run`, `test`, `testenv`, `python`, `self`) — these live in `lib/commands/<name>.sh`.
- Cross-command helpers (`.gitignore` writing, config parsing, backend detection, etc.) — these live in their existing `lib/<helper>.sh` modules.

**Key globals:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `VERSION` | `"3.0.0"` | Current Pyve version |
| `DEFAULT_PYTHON_VERSION` | `"3.14.5"` | Default Python version for new environments (also keys the toolchain venv) |
| `DEFAULT_VENV_DIR` | `".venv"` | Default venv directory name |
| `ENV_FILE_NAME` | `".env"` | Environment variables filename |
| `TESTENV_DIR_NAME` | `"testenv"` | Legacy back-compat constant for the reserved `testenv` name; v3 state lives at `.pyve/envs/<name>/` |

**Library sourcing order (helpers first, then commands).** Helpers: `utils.sh` → `ui/core.sh` → `ui/run.sh` → `ui/progress.sh` → `ui/select.sh` → `env_detect.sh` → `backend_detect.sh` → `micromamba_core.sh` → `micromamba_env.sh` → `micromamba_bootstrap.sh` → `version.sh`. `ui/core.sh` is sourced early so later modules can use its color/symbol constants, banner helpers, and `is_verbose()` gate; `ui/run.sh`, `ui/progress.sh`, and `ui/select.sh` follow because they depend on those. Commands are sourced after all helpers, in alphabetical order: `commands/check.sh` → `commands/init.sh` → `commands/lock.sh` → `commands/purge.sh` → `commands/python.sh` → `commands/run.sh` → `commands/self.sh` → `commands/status.sh` → `commands/test.sh` → `commands/testenv.sh` → `commands/update.sh`. Sourcing is **explicit**, not glob-based, so dependency ordering is auditable. (The Phase-H-era `deprecation_warn` helper was removed in Story J.d when the last Category A delegation paths were ripped; see the Category B `legacy_flag_error` pattern above for the remaining hard-error form.)

Each library and command file guards against direct execution and is designed to be sourced only.

---

### `lib/commands/<name>.sh` — Command Implementations

> **v3.0 file-layout note.** The per-command function tables in this subsection describe each command's **behavior and signatures**, which remain accurate. Their **file locations have moved**: in v3.0 the Python lifecycle/runtime command bodies (`init` / `purge` / `update` / `check` / `status` / `run` / `test` and the `python` namespace) were relocated into [lib/plugins/python/plugin.sh](../../lib/plugins/python/plugin.sh) behind the plugin contract (see [Plugin layer](#plugin-layer)); the composed cross-plugin surfaces live in the `lib/*_composer.sh` modules. `lib/commands/` now holds only `env.sh` (the `env` namespace, formerly `testenv`), `lock.sh`, `package.sh`, and `self.sh`. Read the tables below for *what each command does*; read the Plugin layer for *where it now lives and how it is dispatched*.

One file per top-level command. Each file owns the implementation of its command and follows a uniform contract.

**File-to-function contract:**

- `lib/commands/<name>.sh` defines a top-level function named `<name>` that takes the subcommand's positional + flag arguments. The dispatcher in `pyve.sh` calls it with `"$@"` after stripping the subcommand token.
- **Namespace commands** (`testenv`, `python`, `self`) define the namespace dispatcher *and* the leaf functions in the same file. Leaf functions use the `<namespace>_<leaf>` naming convention:
  - `lib/commands/testenv.sh` → `testenv()`, `testenv_init()`, `testenv_install()`, `testenv_purge()`, `testenv_run()`
  - `lib/commands/python.sh` → `python()`, `python_set()`, `python_show()`
  - `lib/commands/self.sh` → `self()`, `self_install()`, `self_uninstall()`
- **Command-private helpers** stay inside the command file with a `_<command>_` prefix (e.g., `_init_write_envrc()`, `_check_run_diagnostics()`). They are not callable from other commands.
- **Cross-command helpers** (used by two or more commands) live in their existing `lib/<helper>.sh` home — they do NOT migrate into `lib/commands/`. Examples: `write_gitignore_template()` in `lib/utils.sh`, `is_asdf_active()` in `lib/env_detect.sh`, `get_backend_priority()` in `lib/backend_detect.sh`, `header_box()` in `lib/ui/core.sh`.

**Direct-execution guard.** Each command file ends (or begins) with the same guard the helper modules use, so a stray `bash lib/commands/init.sh` exits non-zero rather than running unsourced.

**Per-command function tables** are documented in this section as the extraction phase progresses — each story that extracts a command appends its function-signature table here, mirroring the `lib/utils.sh` / `lib/ui/core.sh` pattern.

#### `run` — `run_command`

| Function | Signature | Description |
|---|---|---|
| `run_command` | `(<command> [args...])` | Execute the target command inside the active project environment. Auto-detects backend by probing `.pyve/envs/*` (micromamba) then `$DEFAULT_VENV_DIR` (venv); errors out if neither exists. Pass-through args via `exec` (preserves exit codes). Story J.c: when `is_asdf_active`, exports `ASDF_PYTHON_PLUGIN_DISABLE_RESHIM=1` before exec to prevent asdf reshim under `--no-direnv` / CI. Venv backend prefers `<venv>/bin/<cmd>` and falls back to `$PATH` after exporting `VIRTUAL_ENV` and prepending `<venv>/bin` to `PATH`. Micromamba backend uses `micromamba run -p <env_path>`. |

No private helpers — `run_command` is self-contained and calls only cross-command helpers (`source_shell_profiles`, `detect_version_manager`, `is_asdf_active`, `get_micromamba_path`, `log_error`).

#### `lock` — `lock_environment` (in `lib/commands/lock.sh`)

| Function | Signature | Description |
|---|---|---|
| `lock_environment` | `([--check] [--env <name>] [--all])` | Dispatcher. Default mode (no flags): main env via `_lock_main_env`. `--env <name>`: lock the named conda-backed testenv via `_lock_one_env`. `--all`: main env (via subshell so its `exit` doesn't kill the iteration) + every conda-backed testenv via `_lock_all_conda_testenvs`. `--check` applies only to the main env (per-env `--check` is out of scope for M.q). Pre-M.q this function held the main-env body inline; M.q factored it into `_lock_main_env` so `--all` can reuse it. |
| `_lock_main_env` | `()` | The pre-M.q main-env locking body. Reads `check_mode` via dynamic scoping from `lock_environment`. `--check`: pure mtime comparison via `is_lock_file_stale`, never invokes `conda-lock`. Otherwise: invokes `conda-lock -f environment.yml -p <platform>`, filters the misleading "conda-lock install" post-run message, detects "spec hash already locked" → "already up to date", otherwise emits success + `pyve init --force` rebuild hint. Three guards run before `conda-lock`: (1) refuses venv backend, (2) requires `environment.yml`, (3) requires `conda-lock` on `$PATH`. |
| `_lock_one_env` | `(<name>)` → 0/1 | Story M.q. Lock a single conda-backed testenv. Loads `read_testenv_config` (idempotent). Hard-errors for `root` (with a "use `pyve lock` no-args" hint), undeclared names (with a `[tool.pyve.testenvs]` hint), non-micromamba backends (after `_testenv_resolve_backend` so `inherit` resolves to the main backend), missing `manifest` declaration, and missing manifest file on disk. Resolves the output path via `_lock_env_lock_path`, invokes `conda-lock -f <manifest> -p <platform> --lockfile <out>`. Uses `return` (not `exit`) so callers can iterate. |
| `_lock_env_lock_path` | `(<manifest>)` → string | Story M.q. Derive the sibling lock-file path: `tests/env.yml` → `tests/env-lock.yml`. Strips `.yaml`/`.yml` extension, appends `-lock.yml`. Preserves the manifest's directory; bare `<base>.yml` → `<base>-lock.yml`. |
| `_lock_all_conda_testenvs` | `()` → 0/1 | Story M.q. Iterate `PYVE_TESTENVS_NAMES`, skip non-`micromamba` backends, call `_lock_one_env` per env. Per-env failures `warn` and accumulate into a non-zero return; iteration always completes. |

**Cross-command helpers called:** `config_file_exists`, `read_config_value`, `unknown_flag_error`, `log_error`, `log_info`, `warn`, `success`, `is_lock_file_stale`, `get_conda_platform`. Story M.q adds calls to `read_testenv_config`, `is_testenv_declared`, `_testenv_resolve_backend`, `_testenv_manifest_of` (all in `lib/testenvs.sh`, sourced before commands in `pyve.sh`).

**Renamed from `run_lock`** in K.c. Final name `lock_environment()` adopted in the K.f follow-up under the project-essentials "Function naming convention: `<verb>_<operand>`" rule — `pyve lock` operates on the environment's dependency graph (`environment.yml` → `conda-lock.yml`). The K.c interim name `lock()` was a rule violation (no operand suffix) and was retired alongside K.e's `self()`. No external callers — only the dispatcher arm referenced the function name.

#### `python` namespace — `python_command` / `python_set` / `python_show`

First namespace extraction. Single-file convention per project-essentials F-9: dispatcher + leaves all live in `lib/commands/python.sh`.

| Function | Signature | Description |
|---|---|---|
| `python_command` | `(<sub> [args...])` | Namespace dispatcher. Sub-commands: `set`, `show`. Empty arg or unknown sub-command exits 1 with an actionable usage message. The `--help` intercept happens in `pyve.sh`'s case dispatcher (calls `show_python_help`); this function never sees `--help`. |
| `python_set` | `(<version>)` | Pin the Python version via the active version manager. Validates format (`X.Y.Z`); detects asdf/pyenv via `detect_version_manager`; ensures the version is installed (may invoke an asdf/pyenv install); writes to `.tool-versions` (asdf) or `.python-version` (pyenv) via `set_local_python_version`. Header/footer-boxed UI. |
| `python_show` | `()` | Read-only. Resolves the pinned version from (in priority order) `.tool-versions`, `.python-version`, `.pyve/config:python.version`. Prints `Python <ver> (from <source>)` or a "not pinned" message. Never installs or modifies anything. The `python show <extra-args>` rejection happens in the dispatcher, not here. |

**Renamed from `set_python_version_only` / `show_python_version`** in K.d so leaf names follow the `<namespace>_<leaf>` convention. The dispatcher **stays `python_command`** (NOT renamed to `python`) because `python` is the bare interpreter binary that pyve invokes internally for venv creation (`python -m venv .venv`, `python -c 'import sys; ...'`). A bash function named `python` would shadow the binary at those callsites — discovered the hard way during K.d's first attempt; the revert and the resulting "Function-name collision rule" in `project-essentials.md` are mandatory reading before naming any future top-level dispatcher (notably K.f, where `test_command` similarly stays unchanged to avoid shadowing the bash builtin).

#### `self` namespace — `self_command` + leaves (in `lib/commands/self.sh`)

Single-file namespace per project-essentials F-9. Largest extraction so far (~458 lines) but every function is self-namespace-private — no cross-command coupling, no helpers move to `lib/utils.sh`. Resolves K.a.3 audit finding F-5: `install_prompt_hook` (and its `uninstall_prompt_hook` sibling) are **self-private**, not init-private; both move with K.e.

| Function | Signature | Description |
|---|---|---|
| `self_command` | `(<sub> [args...])` | Namespace dispatcher. Sub-commands: `install`, `uninstall`. No-arg invocation prints `show_self_help` and returns 0. Each sub-command honors `--help` (calls the matching help block) and `PYVE_DISPATCH_TRACE` (prints `DISPATCH:self-<sub>` and returns) before delegating to the leaf. Unknown sub-commands exit 1 after printing the namespace help. |
| `self_install` | `()` | Install pyve to `~/.local/bin`. Homebrew-managed installs short-circuit with brew-specific guidance (exit 0). Reinstall from the installed location re-execs the source pyve.sh to avoid rewriting the running script. Steps: copy `pyve.sh`, `lib/*.sh`, `lib/commands/*.sh` (Phase K), `lib/completion/*`; record `~/.local/.pyve_source`; create `~/.local/bin/pyve` symlink; wire PATH (`_self_install_update_path`); install prompt hook (`_self_install_prompt_hook`); create `~/.local/.env` template (`_self_install_local_env_template`). Idempotent (re-install is safe). |
| `self_uninstall` | `()` | Reverse of `self_install`. Homebrew-managed installs short-circuit. Removes the symlink, script, `lib/`, the source-dir record file. Preserves a non-empty `~/.local/.env` (warn-and-skip); removes it when empty. Calls `_self_uninstall_prompt_hook`, `_self_uninstall_clean_path`, `_self_uninstall_project_guide_completion` to clean rc files. |
| `_self_install_update_path` | `()` | Append the `export PATH="$HOME/.local/bin:$PATH" # Added by pyve installer` line to `~/.zprofile` (zsh) or `~/.bash_profile` (bash). No-ops if `~/.local/bin` is already on `$PATH` or the marker comment is already present in the profile. |
| `_self_install_prompt_hook` | `()` | Write `~/.local/.pyve_prompt.sh` (a zsh/bash-aware prompt customizer that honors `$PYVE_PROMPT_PREFIX`) and source it from `~/.zshrc` (zsh) or `~/.bashrc` (bash) via the SDKMan-aware insertion helper. Idempotent — strips any prior `source` line for the same hook file before re-inserting, so re-installs don't accumulate duplicates. |
| `_self_install_local_env_template` | `()` | Create an empty `~/.local/.env` with `chmod 600` if it doesn't exist. No-op if the file is already present (preserves user data). |
| `_self_uninstall_prompt_hook` | `()` | Strip the `source $PROMPT_HOOK_FILE` line from both `~/.zshrc` and `~/.bashrc` (covers users who switched shells post-install) using portable `sed -i` (macOS-vs-Linux dialect via `uname` check). Removes the prompt-hook file itself last. |
| `_self_uninstall_clean_path` | `()` | Strip the `# Added by pyve installer` PATH line from both `~/.zprofile` and `~/.bash_profile` using portable `sed -i`. |
| `_self_uninstall_project_guide_completion` | `()` | Remove the project-guide completion sentinel block from both `~/.zshrc` and `~/.bashrc` via the shared `remove_project_guide_completion` helper. Safe no-op when the block is absent. |

**Renames in K.e** (audit-recommended, all callsites internal to the namespace):
- `install_self` → `self_install`, `uninstall_self` → `self_uninstall` (matches `<namespace>_<leaf>` convention).
- `self_command` was briefly renamed to `self()` in the K.e initial pass; **reverted back to `self_command()` in the K.f follow-up** under the project-essentials "Function naming convention: `<verb>_<operand>`" rule (namespace dispatchers use `<namespace>_command` because the operand is the sub-command name).
- 6 private helpers gain the `_self_` prefix per project-essentials F: `install_update_path`, `install_prompt_hook`, `install_local_env_template`, `uninstall_project_guide_completion`, `uninstall_clean_path`, `uninstall_prompt_hook` → `_self_install_*` / `_self_uninstall_*`.

**F-9 update (post-K.l):** the three help blocks (`show_self_help`, `show_self_install_help`, `show_self_uninstall_help`) **moved into this file** during K.l's help-block migration. The dispatcher in `pyve.sh` and `self_command()` here both call them by name; bash resolves them through the global function table at call time. See the `Help-block move` subsection at the end of `lib/commands/<name>.sh` for the K.l rationale.

#### `test` — `test_tests`

| Function | Signature | Description |
|---|---|---|
| `test_tests` | `([--env <name>[,<name>...]] [pytest args...])` | Run pytest. Parses the pyve-owned `--env` selector (`--env <val>` and `--env=<val>` forms) out of the arg list — everything else passes through to pytest verbatim via a bash-3.2-safe `args[]` array (read with `"${args[@]+"${args[@]}"}"`). **Story M.r: comma-separated values** (`--env a,b,c`) trigger the matrix path; one-element values (no comma) take the single-env path. Both paths delegate to `_test_run_one_env`. Matrix: each name runs in its own subshell sequentially with `=== Env: <name> ===` printed before each invocation; the M.o silent-skip advisory is suppressed inside matrix subshells (`PYVE_NO_TESTENV_ADVISORY=1` exported per-iteration) since the user has explicitly named multiple envs; exit code is the worst-case aggregate (highest failing rc); iteration always completes (a failing env does not halt the loop). Single-env: calls `_test_run_one_env` directly, preserving the pre-M.r exec contract verbatim. |
| `_test_run_one_env` | `(<name> <explicit> [pytest args...])` | Story M.r. Per-env worker extracted from `test_tests` so the matrix loop can call it inside a subshell without losing the M.m exec behavior on the single-env path. `<explicit>` is `1` when `--env` was passed (always `1` from the matrix loop; `0` only when the single-env path had no `--env` at all). Behavior: **`--env main`** hard-errors with a precise rename hint (Category-B catch, Story M.e v2.7.1) — no silent delegation. **`--env root`**: delegates to `run_command python -m pytest <args>` (Story M.c; value renamed from `main` in M.e), reusing run_command's backend detection + asdf reshim guard + exec; returns immediately (run_command execs). **Story M.m: `<name>` accepts any name declared in `[tool.pyve.testenvs]`.** Loads `read_testenv_config` (idempotent), defaults `<name>` to `${PYVE_TESTENVS_DEFAULT:-testenv}` when `<explicit>` is `0`, hard-errors on undeclared names with a list of valid choices (`root`, `testenv`, plus declared names). Conda-backed envs are rejected via `assert_testenv_venv_backend` (same gate as `pyve testenv run` — run is venv-only). Lazy envs that have not been provisioned yet **auto-provision (Story M.n)**: `ensure_testenv_exists <name>` creates the env, then `_testenv_install_with_lock <name> <path> "" wait` installs per the declared sources. The whole path is gated by `PYVE_NO_AUTO_PROVISION=1` for strict CI — when set, the M.m hard-error returns (with a `pyve testenv install <name>` hint). For the resolved venv path, auto-creates via `ensure_testenv_exists <name>` if missing; if pytest isn't yet installed, in CI / `PYVE_TEST_AUTO_INSTALL_PYTEST=1` mode auto-installs it, on a TTY prompts y/N (declining exits 1), non-TTY without auto-install errors with the `pyve testenv install -r requirements-dev.txt` next-step. Before exec, the silent-skip advisory (Stories M.c, M.o) scans `root` + every declared env with `_test_env_has_pytest`, skipping the target itself; if any candidate has pytest importable, prints a one-line `warn` listing them as alternatives (e.g. `--env root, --env smoke`). Suppressible via `PYVE_NO_TESTENV_ADVISORY=1` (which matrix mode sets automatically). Touches `.state`'s `last_used_at` via `state_touch_last_used <name>` (best-effort; silent no-op when `.state` is missing) so M.p's `pyve testenv list` / `prune` can report active envs. Finally `exec`s `<env>/bin/python -m pytest <args>` so pytest's exit code propagates verbatim. |
| `_test_env_has_pytest` | `(<name>)` → 0/1 | Story M.o (renamed from `_test_main_env_has_pytest` in M.c). Probe whether the env named `<name>` has pytest importable. `<name> == "root"` resolves the main project env (first `.pyve/envs/*/bin/python`, else `$DEFAULT_VENV_DIR/bin/python`); any other name resolves via `resolve_testenv_path <name>` and probes its `bin/python`. Returns 1 if the env doesn't exist on disk, pytest is absent, or the probe fails. Invokes the env's python directly (no `micromamba run`) to keep the probe cheap. Drives the generalized silent-skip advisory in `test_tests`. |
| `_test_has_pytest` | `(<testenv_venv>)` → 0/1 | Probe whether the testenv at `<testenv_venv>` has pytest installed. Returns 1 if `bin/python` is missing, otherwise 0/1 from `python -c 'import pytest'`. |
| `_test_install_pytest_into_testenv` | `(<testenv_venv>)` | Pip-install pytest (or `requirements-dev.txt` if present) into the testenv via `<testenv_venv>/bin/python -m pip install ...`. |

**`--env root` reuses `run_command` (Story M.c; value renamed from `main` in M.e v2.7.1).** Rather than re-implement backend detection + the asdf reshim guard, `test_tests --env root` calls `run_command python -m pytest <args>` directly — a standard intra-`lib/commands/` cross-file call resolved at runtime via the global function table. This makes the documented `pyve run python -m pytest` workaround for the micromamba-testenv trap (see `docs/specs/.archive/phase-m-pyve-micromamba-testenv-trap.md`) a first-class flag without duplicating run_command's logic.

**Story N.d: purpose gate.** `_test_run_one_env` calls `manifest_load` (when `pyve.toml` is present) and then `manifest_resolve_purpose <env_target>` immediately after name validation and before the conda gate. If the resolved purpose is not `test`, the selector hard-errors with a precise hint at `pyve env run <name> -- <cmd>`. The gate sits AFTER the `--env root` short-circuit (line 210-ish), so `--env root` is never subject to it — `root` defaults to `purpose = "utility"` but its delegation to `run_command` makes the gate irrelevant. v2-source-only paths (no `pyve.toml`, named non-`testenv` envs in `[tool.pyve.testenvs.*]`) currently hit the gate as `purpose = "utility"` by name-based default rule — Story N.i's read-compat shim closes the gap by propagating `purpose = "test"` for every v2 testenv block; until N.i lands, the affected bats coverage carries `N.i-pending` skip markers, documented as deliberate technical debt to be retired by N.i's close-out.

**Category-B catch for legacy `--env main` (Story M.e v2.7.1).** Per the *Deprecation removal policy* in [`project-essentials.md`](project-essentials.md), the rename ships with a hard-error catch — three lines inside `_test_parse_args` validation: match `--env main`, print `pyve test --env main: renamed to --env root. Run 'pyve test --env root' instead.`, exit non-zero. The catch lives in `lib/commands/test.sh` (not in `pyve.sh`'s top-level dispatcher) because `--env` is a *value* parsed inside `test_tests` — `pyve.sh` never sees it. No Category-A silent delegation.

**Function name `test_tests` (NOT `test` or `test_command`)** — applies the project-essentials "Function naming convention: `<verb>_<operand>`" rule: `pyve test [args]` operates on tests (whether the args explicitly select a subset or are absent, in which case the implicit operand is "all tests"). This naming also avoids the F-11 `test` shadowing trap (`test` is a bash builtin / `/usr/bin/test`); the K.f initial extraction used `test_command()` (also F-11-safe) but was renamed in the same K.f follow-up that aligned `lock_environment()` and reverted `self_command()`.

**Cross-file call (post-K.g):** `test_tests` calls `ensure_testenv_exists`, which lives in `lib/utils.sh` (moved there by K.g per audit F-8). Bash resolves the call at runtime via the global function table.

**F-8 correction:** the K.f story's "Temporary cross-file call to `testenv_run`" caveat is stale — there is no `testenv_run` function in `pyve.sh`. `test_command` does NOT call `testenv_run`; it calls `ensure_testenv_exists`, the test-private helpers, and ends with `exec ... pytest`. The `testenv` namespace handles its own `run` action inline in the namespace dispatcher (see K.g).

#### `env` namespace — `env_command` + leaves (in `lib/commands/env.sh`; formerly `testenv`)

Largest namespace command — 4 leaves: `init`, `install`, `purge`, `run`. The K.g extraction also refactored the previous inline `case "$action" in` arms into named leaf functions per project-essentials F-9 (one function per sub-command, leaf names follow `<namespace>_<leaf>`).

| Function | Signature | Description |
|---|---|---|
| `testenv_command` | `(<sub> [args...])` | Namespace dispatcher. Sub-commands: `init [<name>]`, `install [<name>] [-r <file>] [--no-wait]`, `purge [<name>] [--force]`, `run [<name> --] <cmd> [args...]`. Pre-parses each sub-command's flags + the optional positional `<name>` (Stories M.i.1–M.i.4), then calls the matching leaf. Loads `read_testenv_config` once before action dispatch (idempotent if already populated). The `run` action skips the `header_box`/`footer_box` wrapper because exec replaces the shell — the called command owns the rest of the terminal. Captures leaf return codes (M.i.2) so the dispatcher does not mask failures with `footer_box`'s 0 exit. `--help` and unknown-flag/unknown-action paths exit before the leaf is reached. |
| `testenv_init` | `([<name>])` | Story M.i.2 + M.k. Calls `ensure_testenv_exists` (in `lib/utils.sh`), which now dispatches on `_testenv_resolve_backend`: venv → `python -m venv <path>`; micromamba → `_testenv_init_conda` (`micromamba create -p <path> -f <manifest> -y`). |
| `_testenv_install_venv` | `(<name> <env_path> <cli_req_file?>)` | Story M.l (renamed from `testenv_install` for symmetry with `_testenv_install_conda`). Pip-install into a venv testenv with five-stage source dispatch: (1) CLI `-r <file>` always wins; (2) declared `requirements = [...]` → `pip install -r a -r b`; (3) declared `extra = "<n>"` → resolve `[project.optional-dependencies].<n>` via the Python helper's `--resolve-extra` mode, install package list; (4) auto-detected `requirements-dev.txt` in CWD → `-r requirements-dev.txt`; (5) bare `pytest` fallback. Exits 1 if the env doesn't exist, the CLI/declared file is missing, or the helper's extra-resolution fails. **Conda-backed envs do NOT call this leaf** — backend dispatch in `_testenv_install_with_lock` routes them to `_testenv_install_conda` instead. |
| `_testenv_resolve_extra_packages` | `(<extra_name> <out_var>)` | Story M.l. Invoke the Python helper's `--resolve-extra <pyproject> <extra_name>` mode and populate the caller-named array `<out_var>` with the resolved package list. Honors `${PYVE_PYPROJECT:-pyproject.toml}` for the pyproject path. Returns the helper's exit code (2 for missing pyproject / missing extra / malformed extra; helper's stderr surfaces the precise error). |
| `testenv_purge` | `([<name>])` | Story M.i.4. Thin wrapper around `purge_testenv_dir` (in `lib/utils.sh`), passing through the optional `<name>` (defaults to `testenv`). Backend-agnostic — `rm -rf` covers both venv and conda layouts. |
| `testenv_run` | `(<testenv_venv> [<cmd> args...])` | `exec` a command inside the testenv. Prefers `<testenv_venv>/bin/<cmd>` when present; otherwise falls back to `$PATH` after exporting `VIRTUAL_ENV` and prepending `<testenv_venv>/bin` to `PATH`. **Venv-only** (Story M.k): dispatcher gates with `assert_testenv_venv_backend` before invocation; conda-backed envs hard-error with a `micromamba run -p <path> <cmd>` workaround hint. Errors with exit 1 if no command is provided or the testenv doesn't exist. |
| `_testenv_install_lock_dir` / `_testenv_acquire_install_lock` / `_testenv_release_install_lock` | M.j | `mkdir`-based atomic install lock at `.pyve/testenvs/<name>/.lock/` with `pid` file. Acquire is wait+retry by default (1-second sleep, 10-minute cap); `no-wait` mode fast-fails with a "(pid N)" message. Stale-lock reclamation via `kill -0 <pid>`. Release only removes the lock when the caller's `$$` matches the recorded pid. |
| `_testenv_install_with_lock` | M.j + M.k | Wraps a per-env install with lock acquire/release + a `trap EXIT INT TERM` that releases the lock on any exit path (including `testenv_install`'s `exit 1` hard-errors). Dispatches on `_testenv_resolve_backend`: micromamba → `_testenv_install_conda`; else → `testenv_install`. |
| `_testenv_init_conda` / `_testenv_install_conda` | M.k | Conda-backed init/install via `micromamba create -p <path> -f <manifest> -y` / `micromamba install -p <path> -f <manifest> -y`. Both require `manifest` declared in `[tool.pyve.testenvs.<name>]`; both error cleanly when the manifest file is missing. `_init_conda` is idempotent (info+skip if `conda-meta` already exists); `_install_conda` requires the env to exist (errors with a `pyve testenv init <name>` hint otherwise). See *Conda backend dispatch (Story M.k)* under `lib/testenvs.sh` for the wider design. |
| `_testenv_install_all_nonlazy` | M.i.3 + M.k | Iteration loop for no-arg `install`. Iterates `PYVE_TESTENVS_NAMES`, skips lazy envs, calls `_testenv_install_with_lock` for each remaining env. Conda envs are no longer skipped post-M.k — backend dispatch is uniform across iteration and single-env paths. |
| `_testenv_purge_all_with_confirm` | M.i.4 | Iteration loop for no-arg `purge`. TTY-aware `y/N` confirmation (`--force` skips; `PYVE_FORCE_PROMPT=1` forces). |
| `testenv_list` | M.p | Walk the union of declared (`PYVE_TESTENVS_NAMES`) and on-disk (`.pyve/testenvs/*/`) env names; print a header (`NAME BACKEND SIZE LAST-USED STATE`) followed by one row per env via `_testenv_list_one_row`. Read-mostly; no mutations. |
| `_testenv_list_all_names` / `_testenv_list_one_row` | M.p | `_all_names` emits the union of declared + on-disk names, deduped via bash-3.2-safe string-membership (no `declare -A`). `_one_row` resolves backend (declared → `_testenv_resolve_backend`; orphaned → infer from on-disk shape), runs `du -sh`, reads `.state.last_used_at` (`never` for `0`, ISO date otherwise via `_testenv_format_epoch`), and assigns `STATE` (`ready` / `lazy` / `not provisioned` / `orphaned`). |
| `testenv_prune` | M.p | Three modes: default (orphans, declared-name guard + reserved-`testenv` guard), `--unused-since <ISO-date>` (compares `.state.last_used_at` against the parsed epoch; preserves `last_used=0` "never used" entries), `--all` (every on-disk env, disk-driven — distinct from `testenv purge` no-arg's config-driven walk). Bad date format hard-errors before walking. Confirmation gating mirrors `_testenv_purge_all_with_confirm` (`--force` / `PYVE_FORCE_PROMPT=1` / TTY). Calls `purge_testenv_dir` per candidate; accumulates the worst exit. |
| `_testenv_format_epoch` / `_testenv_parse_iso_date` | M.p | Cross-platform date helpers — BSD `date -r`/`date -j -f` on Darwin, GNU `date -d @…`/`date -d <iso>` elsewhere. Both fail closed (`?` / non-zero return) on bad input. |

**F-7 / F-8 helper moves (K.g performs):** `purge_testenv_dir`, `ensure_testenv_exists`, and `testenv_paths` move from `pyve.sh` to `lib/utils.sh` because they are each shared by 2+ commands (per project-essentials cross-command-helper rule):

- `ensure_testenv_exists` — used by `init` (still in pyve.sh), `testenv_init`, and `test_tests` (in `lib/commands/test.sh`).
- `purge_testenv_dir` — used by `purge` (still in pyve.sh) and `testenv_purge`.
- `testenv_paths` — only called by `ensure_testenv_exists`; moves alongside it as an implementation dependency.

After K.g, `lib/commands/test.sh::test_tests` no longer makes a cross-file call back into `pyve.sh` — the call to `ensure_testenv_exists` resolves through `lib/utils.sh` (already sourced by `pyve.sh` before the per-command files).

**Function name `testenv_command`** — applies the project-essentials "Function naming convention" rule: namespace dispatchers use `<namespace>_command` because the operand is the sub-command name that follows. No K.e-style `testenv()` rename — the rule was tightened during K.f follow-up.

#### `status` — `show_status`

Read-only state dashboard. Three sections (Project / Environment / Integrations) plus a non-project fallback. By contract, never returns a non-zero exit code based on findings — that's `pyve check`'s job; `status` reports reality, where "not a pyve project" is also a valid reality. The orchestrator and 9 status-private helpers all move together.

| Function | Signature | Description |
|---|---|---|
| `show_status` | `()` | Orchestrator. Validates no flags / no positional args (errors out otherwise), prints title + divider, then either the non-project fallback or the three sections. Always returns 0 on a valid invocation. |
| `_status_row` | `(<label> <value>)` | Print one key/value row with a 17-char label column (matches the widest label `environment.yml:`) so all sections align visually. |
| `_status_header` | `(<text>)` | Print a BOLD section header. |
| `_status_section_project` | `()` | Project section: path, backend, recorded `pyve_version` (with drift comparison vs. running `$VERSION` via `compare_versions`), and configured Python. |
| `_status_configured_python` | `()` → string | Resolve and format the configured Python version source — `.tool-versions via asdf`, `.python-version via pyenv`, or `.pyve/config`. Returns `"not pinned"` when none are present. |
| `_status_section_environment` | `()` | Environment section header + dispatch to `_status_env_venv` or `_status_env_micromamba` based on configured backend. |
| `_status_env_venv` | `()` | Venv-backend rows: path, Python version, package count (via `_status_venv_package_count`). |
| `_status_venv_package_count` | `(<venv_dir>)` → string | Count `*.dist-info` directories under `<venv_dir>/lib/python*/site-packages/`; returns "N installed" or "unknown". `find`-pipefail safe. |
| `_status_env_micromamba` | `()` | Micromamba-backend rows: name, path, Python, package count via `conda-meta`, `environment.yml` presence, `conda-lock.yml` freshness via `is_lock_file_stale`. |
| `_status_section_integrations` | `()` | Integrations section: `.envrc` presence, `.env` (with empty/non-empty distinction), `project-guide` (probes `<env>/bin/project-guide --version`), `testenv` (probes `<testenv>/bin/python -c 'import pytest'`). |

**Function name `show_status` (NOT `status_command`)** — applies the project-essentials "Function naming convention: `<verb>_<operand>`" rule. `status` is a noun, not a verb; the operation is "show the status". Semantic alignment trumps spelling alignment here.

**No private-helper rename** — all 9 helpers already follow the `_status_*` prefix convention from when they were inlined in `pyve.sh` (Story H.e.4). They stay named exactly as-is; only the orchestrator was renamed.

**Cross-command helpers (lib/) used:** `config_file_exists`, `read_config_value`, `is_file_empty` (lib/utils.sh); `compare_versions` (lib/version.sh); `is_lock_file_stale` (lib/micromamba_env.sh); `unknown_flag_error`, `log_error` (pyve.sh / lib/utils.sh). Reads `BOLD`, `DIM`, `RESET` color globals (defined in lib/ui/core.sh).

#### `check` — `check_environment`

Read-only diagnostics. Severity ladder: `info` (no effect) → `pass` (✓) → `warn` (⚠, exit 2) → `error` (✗, exit 1). Escalation is one-way — an error later in the run cannot be downgraded; a warning cannot downgrade an error. Replaces the legacy `pyve validate` (CI exit-code semantics) and most of the legacy `pyve doctor` (per-problem findings with one actionable next-step).

| Function | Signature | Description |
|---|---|---|
| `check_environment` | `()` | Orchestrator. Validates no flags / no positional args, prints title + divider, runs Check 1 (`.pyve/config`), Check 3 (`backend` configured), Check 2 (`pyve_version` drift via `compare_versions`), the per-backend block via `_check_venv_backend` or `_check_micromamba_backend`, then Checks 9/10 (`.envrc`, `.env`) and Check 16 (testenv conditional). Calls `_check_summary_and_exit` to print the count line and exit with the accumulated severity. Defines three nested closures (`_check_pass`, `_check_warn`, `_check_fail`) that bump local counters via dynamic scoping. |
| `_check_venv_backend` | `(<venv_dir>)` | Venv-backend Checks 5/7/13/14 — directory + `bin/python` exist, Python version, `doctor_check_venv_path` (relocated project), `doctor_check_duplicate_dist_info`, `doctor_check_collision_artifacts`. Calls the three closures from `check_environment`'s scope to escalate findings. |
| `_check_micromamba_backend` | `(<env_path> <env_name>)` | Micromamba-backend Checks 4/5/11/12/13/14/15 — micromamba binary present, `environment.yml` present, `conda-lock.yml` present + fresh, env directory + Python, dup-dist-info, collision-artifacts, native-lib-conflict warning. Calls the three closures from `check_environment`'s scope. |
| `_check_summary_and_exit` | `()` | Print the `N passed, N warnings, N errors` count line and `exit "$exit_code"`. Reads the four counter locals from `check_environment` via dynamic scoping. |

**Function name `check_environment` (NOT `check_command`)** — applies the project-essentials "Function naming convention: `<verb>_<operand>`" rule. `pyve check` operates on the project's environment (venv / micromamba env, .envrc, .env, testenv, lock file).

**Closure pattern preserved.** `check_environment` defines `_check_pass`, `_check_warn`, `_check_fail` inline as nested function definitions. The two per-backend helpers and `_check_summary_and_exit` are top-level in the file (NOT nested inside `check_environment`), but they reference the closures and the four counter locals (`errors`, `warnings`, `passed`, `exit_code`) — bash dynamic scoping resolves these up the call stack at call time. **Do not refactor to file-scope counters** — the structure is intentional and tested by `test_check.bats` exit-code escalation tests. `_check_pass` / `_check_warn` / `_check_fail` are NOT visible to direct invocations of the helpers from outside `check_environment` (they don't exist in the function table until the orchestrator runs).

**`doctor_check_*` helpers stay in `lib/utils.sh`** per the cross-command-helper rule. They're called from `_check_venv_backend` / `_check_micromamba_backend` here, but may grow more callers in future (notably the deferred `pyve check --fix` story).

#### `update` — `update_project`

Non-destructive upgrade — refreshes managed files (`.pyve/config`, `.gitignore`, `.vscode/settings.json`, project-guide scaffolding) without rebuilding the venv or touching user state. Single self-contained function; no private helpers.

| Function | Signature | Description |
|---|---|---|
| `update_project` | `([--no-project-guide])` | Five-step refresh: (1) bump `pyve_version` in `.pyve/config` via `update_config_version` (idempotent — writes even when already current); (2) refresh `.gitignore` Pyve-managed sections via `write_gitignore_template`; (3) refresh `.vscode/settings.json` via `write_vscode_settings` (only if it already exists AND backend is micromamba); (4) ensure `.pyve/` exists; (5) refresh project-guide scaffolding via `run_project_guide_update_in_env` (only if `.project-guide.yml` is present and `--no-project-guide` not passed). Errors out with exit 1 if `.pyve/config` is missing or has no `backend` key. Never prompts. Never changes the recorded backend. Never creates `.vscode/settings.json` or `.envrc` or `.env` if absent. |

**Function name `update_project` (NOT `update_command`)** — applies the project-essentials "Function naming convention: `<verb>_<operand>`" rule. `pyve update` operates on the project (config + .gitignore + .vscode/settings.json + project-guide scaffolding — all project-level concerns).

**Cross-command helpers (lib/) used:** `config_file_exists`, `read_config_value`, `update_config_version` (lib/utils.sh + lib/version.sh); `write_gitignore_template`, `write_vscode_settings` (lib/utils.sh); `run_project_guide_update_in_env` (lib/utils.sh); `unknown_flag_error`, `log_error`, `log_info`, `log_success`, `log_warning` (lib/utils.sh).

**No private helpers** — the function is fully self-contained at HEAD and didn't need any helpers when it was inlined in pyve.sh either. The K.j story task to "decide helper placement between init and update" was moot per the K.a.3 audit: there are no `pyve.sh`-internal helpers shared between `init` and `update_project` — every cross-command helper they share already lives in `lib/utils.sh`.

#### `purge` — `purge_project`

Remove pyve-managed environment artifacts. Optionally preserves `.pyve/testenv` via `--keep-testenv` (used by `init --force` to avoid rebuilding the dev/test runner across re-inits). Orchestrator + 6 purge-private helpers.

| Function | Signature | Description |
|---|---|---|
| `purge_project` | `([<dir>] [--keep-testenv] [--yes\|-y])` | Orchestrator. Parses flags, prompts y/N for confirmation (skipped on `--yes`/`-y` / `CI=1` / `PYVE_FORCE_YES=1`), sources shell profiles, and calls each helper in sequence: `_purge_version_file`, `_purge_venv`, `_purge_pyve_dir` + `purge_testenv_dir` (or the `--keep-testenv` branch that preserves `.pyve/testenv`), `_purge_envrc`, `_purge_dotenv`, `_purge_gitignore`. The venv directory defaults to `$DEFAULT_VENV_DIR`, but if no positional arg is given AND `.pyve/config` exists, `venv.directory` from config wins. Always exits 0 on success or user-aborted prompt. |
| `_purge_version_file` | `()` | Remove `.tool-versions` AND `.python-version` if present. |
| `_purge_venv` | `(<venv_dir>)` | Remove the venv directory; emits an info line if absent. |
| `_purge_pyve_dir` | `()` | Remove `.pyve/`. If `.pyve/envs/` exists and micromamba is available, attempts a clean `micromamba env remove` first (named, then prefix-based fallback) before the directory `rm -rf`. Safe no-op when `.pyve/` doesn't exist. |
| `_purge_envrc` | `()` | Remove `.envrc` if present. |
| `_purge_dotenv` | `()` | v0.6.0 smart purge: removes `$ENV_FILE_NAME` only if empty; otherwise warn-and-preserve (the user's data takes precedence). |
| `_purge_gitignore` | `(<venv_dir>)` | Strip the three pyve-managed patterns (`<venv_dir>`, `$ENV_FILE_NAME`, `.envrc`) from `.gitignore`. Safe no-op when `.gitignore` doesn't exist. |

**Function name `purge_project` (NOT `purge`)** — applies the project-essentials "Function naming convention: `<verb>_<operand>`" rule. `pyve purge` operates on the project (removes every Pyve-managed artifact across venv/conda env, version manager files, rc files, `.gitignore` sections, `.pyve/` directory).

**Cross-command callsites** (resolved at runtime via global function table):
- `init_project` (in `lib/commands/init.sh` post-K.l) calls `purge_project --keep-testenv --yes` from its `--force` pre-flight and from the interactive option-2 (purge-and-rebuild) path. Standard intra-`lib/commands/` cross-file call resolved at runtime via the global function table.

**F-7 settled in K.g** — `purge_testenv_dir` already lives in `lib/utils.sh` and is called from both `purge_project` (here) and `testenv_purge` (in `lib/commands/testenv.sh`).

**Cross-command helpers (lib/) used:** `unknown_flag_error`, `log_error`, `header_box`, `footer_box`, `warn`, `info`, `success`, `ask_yn` (lib/utils.sh + lib/ui/core.sh); `source_shell_profiles`, `detect_version_manager` (lib/env_detect.sh); `config_file_exists`, `read_config_value` (lib/utils.sh); `get_micromamba_path` (lib/micromamba_core.sh); `is_file_empty`, `remove_pattern_from_gitignore` (lib/utils.sh); `purge_testenv_dir` (lib/utils.sh, F-7).

#### `init` — `init_project`

Largest extraction in the phase. The orchestrator (`init_project`, ~545 lines) plus 7 init-private helpers — every single-caller `init_*` and `run_project_guide_hooks` get the `_init_` prefix and move to this file.

| Function | Signature | Description |
|---|---|---|
| `init_project` | `([<dir>] [options...])` | Orchestrator. Parses ~17 flags + the optional `<dir>` positional. Detects re-init state (existing `.pyve/config`); on `--force`, runs the pre-flight (scaffold starter `environment.yml` for fresh micromamba dirs, `validate_lock_file_status`, prompt-then-`purge_project --keep-testenv --yes`). Without `--force`: interactive 3-way menu (update / purge-and-rebuild / cancel). Then runs the main flow: source profiles, detect version manager, ensure direnv (unless `--no-direnv`), ensure Python version installed, create venv (`_init_venv`) or micromamba env (`create_micromamba_env`), configure direnv (`_init_direnv_venv` / `_init_direnv_micromamba`), create `.env` (`_init_dotenv`), update `.gitignore` (`_init_gitignore` for venv; `write_gitignore_template` for micromamba), write `.pyve/config`, write `.vscode/settings.json` (micromamba), `ensure_testenv_exists` (venv), prompt pip-deps install, run `_init_run_project_guide_hooks`. |
| `_init_python_version` | `(<version>)` | Write `.tool-versions` or `.python-version` (via `set_local_python_version`). No-op if file already exists. |
| `_init_venv` | `(<venv_dir>)` | `python -m venv <venv_dir>` if directory absent. |
| `_init_direnv_venv` | `(<venv_dir>)` | Wrapper around `write_envrc_template` with `VIRTUAL_ENV` sentinel. |
| `_init_direnv_micromamba` | `(<env_name> <env_path>)` | Wrapper around `write_envrc_template` with `CONDA_PREFIX` sentinel. |
| `_init_dotenv` | `(<use_local_env>)` | Create `.env` (empty or copied from `~/.local/.env` template), `chmod 600`. No-op if `.env` already exists. |
| `_init_gitignore` | `(<venv_dir>)` | Rebuild `.gitignore`: `write_gitignore_template` followed by `insert_pattern_in_gitignore_section "$venv_dir"`. |
| `_init_run_project_guide_hooks` | `(<backend> <env_path> <pg_mode> <comp_mode>)` | The three-step project-guide post-init hook: (1) `pip install --upgrade project-guide`, (2) `project-guide init --no-input` OR `project-guide update --no-input` based on `.project-guide.yml` presence, (3) shell-completion wiring in `~/.zshrc` / `~/.bashrc`. Tri-state mode args (empty / "yes" / "no") resolved from `--project-guide` / `--no-project-guide` / `--project-guide-completion` / `--no-project-guide-completion` flags. Auto-skip safety: if `project-guide` is already declared as a project dependency (`pyproject.toml` / `requirements.txt` / `environment.yml`), the hook short-circuits to avoid version conflicts. |

**Function name `init_project` (NOT `init`)** — applies the project-essentials "Function naming convention: `<verb>_<operand>`" rule. `pyve init` operates on the project (creates venv, writes `.pyve/config`, configures direnv, etc.).

**F-3 callsite update (test_asdf_compat.bats):** the J.b/J.c tests use `source_pyve_fn` to extract function bodies for in-process testing. After K.l: callsites pass `"$PYVE_ROOT/lib/commands/init.sh"` (instead of the default pyve.sh) AND the new function names `_init_direnv_venv` / `_init_direnv_micromamba`. The `source_pyve_fn` signature update (added in K.b) made this a clean drop-in.

**F-10 settled** — `run_project_guide_hooks` was init-private (called only twice, both inside `init()`). Moves with K.l as `_init_run_project_guide_hooks`.

**Cross-command callsites resolved at runtime:**
- `init_project --force` calls `purge_project --keep-testenv --yes` (in `lib/commands/purge.sh`) twice — once in the `--force` pre-flight ([lib/commands/init.sh:706](../../lib/commands/init.sh) area) and once in the interactive option-2 path ([lib/commands/init.sh:774](../../lib/commands/init.sh) area). Bash resolves the call at runtime via the global function table.

**Per-command help block** — `show_init_help` was moved from `pyve.sh` to `lib/commands/init.sh` in K.l, alongside the orchestrator. See the "Help-block move" subsection below for the rationale.

#### Per-command help blocks

K.l moved 9 per-command help blocks (`show_init_help`, `show_purge_help`, `show_status_help`, `show_check_help`, `show_update_help`, `show_python_help`, `show_self_install_help`, `show_self_uninstall_help`, `show_self_help`) from `pyve.sh` into their respective `lib/commands/*.sh` files. The K.a.3 audit's F-9 entry kept them in `pyve.sh` "for v2.4.0" with K.m re-evaluation; K.l honored the K.l acceptance criterion (line count target) by doing the move now.

Reason: each help block is tightly coupled to one command. Co-locating help with the command it documents (a) puts the maintenance burden in the right place, (b) the `pyve <cmd> --help` dispatch arm in `main()` already calls into the per-command function table, so the location is invisible at call time, (c) bumps `pyve.sh` from ~870 → ~595 lines (closer to the K.m target).

The three top-level commands' help blocks (`show_help`, `show_version`, `show_config`) stay in `pyve.sh` — they describe the CLI as a whole, not any single command.

---

### `lib/utils.sh` — Core Utilities

Logging, user prompts, `.gitignore` management, config file parsing, and input validation.

| Function | Signature | Description |
|----------|-----------|-------------|
| `log_info` | `(message)` | Print `INFO: <message>` to stdout |
| `log_warning` | `(message)` | Print `WARNING: <message>` to stderr |
| `log_error` | `(message)` | Print `ERROR: <message>` to stderr |
| `log_success` | `(message)` | Print `✓ <message>` to stdout |
| `prompt_yes_no` | `(prompt)` → 0/1 | Prompt user for y/n confirmation |
| `prompt_install_pip_dependencies` | `(backend?, env_path)` → 0/1 | Prompt to install pip dependencies from `pyproject.toml` or `requirements.txt`. `env_path` is required for both backends: venv uses `$env_path/bin/pip`; micromamba uses `micromamba run -p $env_path pip`. Returns 1 if `env_path` is missing or pip is not found. |
| `gitignore_has_pattern` | `(pattern)` → 0/1 | Check if exact line exists in `.gitignore` |
| `append_pattern_to_gitignore` | `(pattern)` | Append pattern if not already present |
| `insert_pattern_in_gitignore_section` | `(pattern, section_comment)` | Insert pattern after section comment; falls back to append |
| `remove_pattern_from_gitignore` | `(pattern)` | Remove exact line match from `.gitignore` |
| `write_gitignore_template` | `()` | Rebuild Pyve-managed template section, preserving user entries |
| `write_envrc_template` | `(rel_bin_dir, sentinel_var, rel_env_root, backend_name, env_name)` | Emit the uniform v2.3.2 `.envrc` template shared by every backend (v2.3.2 / Story K.a.2). Skips the write when `.envrc` already exists; always tops up the asdf reshim guard when `is_asdf_active`. See "Uniform `.envrc` template" under Cross-Cutting Concerns. |
| `read_config_value` | `(key)` → string | Read value from `.pyve/config` (supports dotted keys) |
| `config_file_exists` | `()` → 0/1 | Check if `.pyve/config` exists |
| `validate_venv_dir_name` | `(dirname)` → 0/1 | Reject empty, reserved names, invalid characters |
| `validate_python_version` | `(version)` → 0/1 | Validate `#.#.#` semver format |
| `is_file_empty` | `(filename)` → 0/1 | Returns 0 if file is empty or missing |
| `check_cloud_sync_path` | `()` | Hard fail if `$PWD` is inside a known cloud-synced directory; bypassed by `PYVE_ALLOW_SYNCED_DIR=1` |
| `write_vscode_settings` | `(env_name)` | Write `.vscode/settings.json` with interpreter path and IDE isolation settings; skips if exists unless `PYVE_REINIT_MODE=force` |
| `doctor_check_duplicate_dist_info` | `(env_path)` | Scan `site-packages` for duplicate `.dist-info` dirs; reports conflicting versions with mtimes. (Name retained for backport continuity; reused by `check_environment`.) |
| `doctor_check_collision_artifacts` | `(env_path)` | Scan environment tree for files/dirs with ` 2` suffix (iCloud Drive collision artifacts). Reused by `check_environment`. |
| `doctor_check_native_lib_conflicts` | `(env_path)` | Detect conda/pip OpenMP conflicts: pip-bundled libs (torch/tf/jax) + conda-linked libs (numpy/scipy) + missing `libomp.dylib`/`libgomp.so`. Reused by `check_environment`. |
| `doctor_check_venv_path` | `(env_path)` | Detect relocated venv: compare `pyvenv.cfg` creation path against actual venv location; warn with remediation if mismatched. Reused by `check_environment`. |

**`.gitignore` template structure:**
```
# macOS only
.DS_Store

# Python build and test artifacts
__pycache__
*.egg-info
.coverage
coverage.xml
htmlcov/
.pytest_cache/

# Pyve virtual environment
<dynamically inserted entries: .venv, .env, .envrc, .pyve/testenv, .pyve/envs, .vscode/settings.json>
```

The template is written via heredoc. User entries below the template are preserved. Deduplication prevents template lines from appearing in the user section.

---

### `lib/env_detect.sh` — Environment Detection

Version manager detection, Python version management, and direnv checks.

| Function | Signature | Description |
|----------|-----------|-------------|
| `source_shell_profiles` | `()` | Initialize asdf/pyenv in non-interactive shells |
| `detect_version_manager` | `()` → sets `VERSION_MANAGER` | Detect asdf (preferred) or pyenv; sets global |
| `is_python_version_installed` | `(version)` → 0/1 | Check if version is installed via current manager |
| `is_python_version_available` | `(version)` → 0/1 | Check if version is available to install |
| `install_python_version` | `(version)` → 0/1 | Install Python version via asdf or pyenv |
| `ensure_python_version_installed` | `(version)` → 0/1 | Install if not present, verify after |
| `set_local_python_version` | `(version)` → 0/1 | Write `.tool-versions` (asdf) or `.python-version` (pyenv) |
| `get_version_file_name` | `()` → string | Returns `.tool-versions` or `.python-version` |
| `check_direnv_installed` | `()` → 0/1 | Check if direnv is in PATH |

> **Boundary (`BOUNDARY` marker in source):** `assert_python_resolvable` in this file guards the **project** python (the developer's interpreter for `pyve run python`, version-manager activation, the project venv). It deliberately stays on `${PYVE_PYTHON:-python}` and is **not** routed through `pyve_toolchain_python` — see `lib/toolchain_python.sh` below for the distinction.

---

### `lib/toolchain_python.sh` — Pyve-owned Toolchain Python

Resolves and provisions **Pyve's own** Python interpreter — the one that runs Pyve's Python helpers (`lib/pyve_toml_helper.py`, the testenvs helper), independent of the developer's environment. Introduced because every internal callsite previously borrowed the developer's PATH `python` (`${PYVE_PYTHON:-python}`), which fails on a clean non-Python stack (a version-manager shim with no pinned version) and silently degrades manifest parsing — surfaced by the N.at composed-init spike.

**Hidden venv:** `${XDG_DATA_HOME:-$HOME/.local/share}/pyve/toolchain/<DEFAULT_PYTHON_VERSION>/venv` — XDG *data* (durable), **version-keyed** so a `DEFAULT_PYTHON_VERSION` bump lands a fresh tree (the old one is GC-able and pruned on the next `self install`). Provisioned by `pyve self install`, removed by `pyve self uninstall` (see `lib/commands/self.sh`).

**Resolution order:** `PYVE_PYTHON` (explicit override) → the hidden toolchain venv (when provisioned) → bare `python` (legacy fallback).

| Function | Signature | Description |
|----------|-----------|-------------|
| `pyve_toolchain_root` | `()` → path | `${XDG_DATA_HOME:-$HOME/.local/share}/pyve/toolchain` |
| `pyve_toolchain_venv_dir` | `()` → path | Version-keyed venv dir for the current `DEFAULT_PYTHON_VERSION` |
| `pyve_toolchain_python` | `()` → path | Resolve the interpreter (the three-step order above); always prints something |
| `pyve_toolchain_python_ensure` | `()` → 0/1 | Idempotent build/refresh of the hidden venv; 0 when present, non-zero + stderr on build failure |
| `_pyve_toolchain_build` | `(venv_dir)` → 0/1 | Build seam (stubbable in tests) — resolves a bootstrap interpreter, `python -m venv` |
| `_pyve_toolchain_bootstrap_python` | `(version)` → path | Prefers the version manager's **exact-version** interpreter (`asdf where` / `pyenv prefix`), else a PATH `python3`/`python` |

The three internal callsites that consume the resolver: `manifest_load` (`lib/manifest.sh`), `read_env_config` (`lib/envs.sh`), `_env_resolve_extra_packages` (`lib/commands/env.sh`). Each uses `py="$(pyve_toolchain_python 2>/dev/null)" || py="${PYVE_PYTHON:-python}"` so it stays self-sufficient when the module isn't sourced (piecemeal test subshells) while honoring the override.

---

### `lib/backend_detect.sh` — Backend Detection

Determine which environment backend to use based on CLI flags, config, and project files.

| Function | Signature | Description |
|----------|-----------|-------------|
| `detect_backend_from_files` | `()` → string | Returns `"venv"`, `"micromamba"`, or `"none"` from project files |
| `get_backend_priority` | `(cli_backend, skip_config?)` → string | Resolve backend using priority chain: CLI > config (skipped when `skip_config=true`) > files > default; prompts interactively in ambiguous cases (both conda and Python files present) |
| `validate_backend` | `(backend)` → 0/1 | Validate backend value is `venv`, `micromamba`, or `auto` |
| `validate_config_file` | `()` → 0/1 | Validate `.pyve/config` structure |

---

### `lib/micromamba_core.sh` — Micromamba Binary Management

Locate and query the micromamba binary.

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_micromamba_path` | `()` → string | Search: `.pyve/bin/` > `~/.pyve/bin/` > system PATH |
| `check_micromamba_available` | `()` → 0/1 | Check if micromamba is found anywhere |
| `get_micromamba_version` | `()` → string | Return version string (e.g., `"1.5.3"`) |
| `get_micromamba_location` | `()` → string | Return `"project"`, `"user"`, `"system"`, or `"not_found"` |
| `error_micromamba_not_found` | `(context)` | Print error with installation instructions |

---

### `lib/micromamba_env.sh` — Micromamba Environment Management

Environment file parsing, naming resolution, environment creation, and lock file validation.

| Function | Signature | Description |
|----------|-----------|-------------|
| `detect_environment_file` | `()` → string | Return `conda-lock.yml` or `environment.yml` path |
| `parse_environment_name` | `(env_file?)` → string | Extract `name:` field from environment.yml |
| `parse_environment_channels` | `(env_file?)` → string | Extract channels list |
| `validate_environment_file` | `()` → 0/1 | Check environment file exists and is readable |
| `is_lock_file_stale` | `()` → 0/1 | Compare mtimes of environment.yml vs conda-lock.yml |
| `validate_lock_file_status` | `(strict_mode)` → 0/1 | Lock-status gate (declarative model, Story N.bf.9). Case 1 (both files): staleness check — strict errors, interactive warns. Case 2 (only `environment.yml`): `--no-lock`/`PYVE_NO_LOCK` → proceed (beats strict); else `is_conda_lock_declared` decides — undeclared → proceed silently (no lock expected), declared + `--strict` → bark (hard error naming `pyve lock` + opt-outs), declared + non-strict → proceed (the end-of-init `_init_lock_nudge` handles messaging). Cases 3/4 (lock-only / neither) unchanged. |
| `is_conda_lock_declared` | `(env_file?)` → 0/1 | Story N.bf.8. The declarative lock signal: is `conda-lock` a dependency in `environment.yml`? Grep-based, matches bare / version-pinned / `pip:`-nested forms; excludes longer names (`conda-lock-foo`); 1 when no env file. |
| `sanitize_environment_name` | `(raw_name)` → string | Lowercase, replace special chars, trim hyphens |
| `is_reserved_environment_name` | `(name)` → 0/1 | Check against reserved names list |
| `validate_environment_name` | `(name)` → 0/1 | Full name validation |
| `resolve_environment_name` | `(cli_name?)` → string | Priority: CLI > config > env file > directory basename |
| `scaffold_starter_environment_yml` | `(python_version, env_name_flag?, strict_mode, include_conda_lock?)` → 0/1 | Write starter `environment.yml` when the current dir has neither an `environment.yml` nor a `conda-lock.yml` and `strict_mode` is `false`. Returns 0 on write, 1 on refusal (strict / env.yml already present / conda-lock.yml present). Called from `init()` before `check_micromamba_available` so the fresh-project path gets a scaffold-then-proceed flow instead of the H.f.6 hard-error. Template content: `name: <sanitized-basename or env_name_flag>`, `channels: [conda-forge]`, `dependencies: [python=<ver>, pip]`. **Story N.bf.11:** 4th arg `include_conda_lock` (default `"true"`) appends `- conda-lock` so the env can run `pyve lock` out of the box; the caller resolves it via `_init_resolve_scaffold_conda_lock` (`--no-lock` → omit; interactive `[Y/n]` default-yes; non-interactive → include). H.f.7. |
| `check_micromamba_env_exists` | `(env_name)` → 0/1 | Check if `.pyve/envs/<name>` exists |
| `create_micromamba_env` | `(env_name, env_file?)` → 0/1 | Create environment from file |
| `verify_micromamba_env` | `(env_name)` → 0/1 | Verify environment is functional |
| `is_interactive` | `()` → 0/1 | Detect interactive vs CI/batch mode |

---

### `lib/micromamba_bootstrap.sh` — Micromamba Installation

Download and install micromamba binary.

| Function | Signature | Description |
|----------|-----------|-------------|
| `get_micromamba_download_url` | `()` → string | Platform-specific download URL |
| `bootstrap_install_micromamba` | `(location)` → 0/1 | Download and install to `"project"` or `"user"` sandbox |
| `bootstrap_micromamba_interactive` | `(context?)` → 0/1 | Interactive prompt with 4 installation options |
| `bootstrap_micromamba_auto` | `(location?)` → 0/1 | Non-interactive install (default: user) |

---

### `lib/distutils_shim.sh` — retired

The Python 3.12+ `sitecustomize.py` distutils shim (and its forced `pip install setuptools wheel`) was retired: distutils was removed in CPython 3.12 (PEP 632), `SETUPTOOLS_USE_DISTUTILS=local` is now the setuptools default, and modern build backends use PEP 517 build isolation. Fresh environments keep `pip` but no longer carry the shim or a forced setuptools/wheel. See FR-13 in `features.md` for the manual fallback. A regression sentinel ([tests/unit/test_distutils_shim_retired.bats](../../tests/unit/test_distutils_shim_retired.bats)) fails the build if any retired shim function reappears.

---

### `lib/version.sh` — Version Tracking & Validation

Version comparison, installation validation, and config file management.

| Function | Signature | Description |
|----------|-----------|-------------|
| `compare_versions` | `(v1, v2)` → string | Return `"equal"`, `"greater"`, or `"less"` |
| `validate_pyve_version` | `()` → 0/1 | Compare recorded version with current |
| `validate_installation_structure` | `()` → 0/1 | Check `.pyve/` directory and config |
| `validate_venv_structure` | `()` → 0/1 | Check venv directory exists |
| `validate_micromamba_structure` | `()` → 0/1 | Check environment.yml and env directory |
| `write_config_with_version` | `()` | Create `.pyve/config` with current version |
| `update_config_version` | `()` | Update version in existing config |

**Note:** `run_full_validation()` was removed along with the `pyve validate` command; its 0/1/2 exit-code semantics live on in `check_environment` (see [phase-h-check-status-design.md §3.2](.archive/phase-h-check-status-design.md)).

---

### `lib/envs.sh` — Named-environment config foundation (formerly `lib/testenvs.sh`)

Reads `[tool.pyve.testenvs]` from a project's `pyproject.toml` and exposes a flat predicate/accessor surface for the bundle's downstream consumers (`pyve testenv` namespace, `pyve test --env <name>`, `pyve lock --env <name>`). This is **the canonical TOML reader for pyve** — future pyve consumers that need to read TOML reuse this helper, they do not write an ad-hoc bash parser. Spike that fixed the design: [spike-m-f-testenvs-config.md](.archive/phase-m-spike-f-testenvs-config.md).

| Function | Signature | Description |
|----------|-----------|-------------|
| `read_testenv_config` | `([<pyproject.toml path>])` | Invoke the Python tomllib helper and populate the V3 parallel-indexed-array state in the calling shell. Default path: `./pyproject.toml`. Missing file or missing `[tool.pyve.testenvs]` block synthesizes the implicit default (single venv `testenv`). Validation errors propagate via non-zero exit + stderr. |
| `resolve_testenv_path` | `(<name>)` → string | Print the on-disk path the env should live at: `root` → `.venv`; venv-backed `<name>` → `.pyve/testenvs/<name>/venv`; conda-backed `<name>` → `.pyve/testenvs/<name>/conda`. Does **not** check existence — that is the caller's responsibility. **Backend dispatch (M.k):** routes through `_testenv_resolve_backend` so `inherit` produces a venv-shaped path when main is venv and a conda-shaped path when main is micromamba. **Side effect (M.h.3):** when `<name> == "testenv"` and only the legacy `.pyve/testenv/venv/` layout exists, calls `migrate_legacy_testenv_layout` before returning. Other names short-circuit. |
| `_testenv_resolve_backend` | `(<name>)` → string | Story M.k. Resolve `<name>`'s effective backend to a concrete literal (`venv` or `micromamba` — never `inherit`). For `inherit`, reads main env's backend via `read_config_value backend` (from `.pyve/config`); falls back to `venv` if no config (bash-only / greenfield project case). For undeclared names, returns `venv`. Used by `resolve_testenv_path` (for path shape), `ensure_testenv_exists` and `_testenv_install_with_lock` (for init/install dispatch), and `assert_testenv_venv_backend` (so the run-only gate sees the *resolved* backend). |
| `assert_testenv_venv_backend` | `(<name>)` → 0/1 | Story M.i.1 / M.k. Venv-only gate for `pyve testenv run`. 0 when `_testenv_resolve_backend` returns `venv`; 1 (with a stderr error pointing at the `micromamba run -p <path> <cmd>` workaround) for `micromamba` and `inherit` resolving to micromamba. M.k landed conda init/install but kept `run` venv-only because PATH-only activation does not set `CONDA_PREFIX` / `CONDA_PYTHON_EXE`. |
| `migrate_legacy_testenv_layout` | `()` → 0 | Story M.h.2. Move `.pyve/testenv/venv/` → `.pyve/testenvs/testenv/venv/`, write initial `.state`, log a one-line `info()`. Idempotent across all four state cases (legacy-only / new-only / both / neither). Invoked by `pyve update` (via the `_update_migrate_legacy_layout` wrapper in `lib/commands/update.sh`) and by `resolve_testenv_path testenv`'s opportunistic-migration fallback. See the *Legacy-layout migration* subsection below. |
| `state_path` / `state_write` / `state_read` / `state_touch_last_used` | per row | Story M.h.1. `.state` per-env state file helpers (path, write/overwrite, read into `PYVE_TESTENV_STATE_*` vars, touch-last-used). Full schema + signatures in the *`.state` per-env state file* subsection below. |
| `validate_testenv_decl` | `(<name>)` → 0/1 | 0 if `<name>` is reserved (`root`, `testenv`) or declared in the read state; 1 (with a stderr error) otherwise. Schema-level validation already happened in the Python helper at read time; this function is the name-legality guard. |
| `is_testenv_declared` | `(<name>)` → 0/1 | 0 if `<name>` appears in `PYVE_TESTENVS_NAMES`. **Note:** `root` is reserved-but-not-declared (never in `NAMES`), so `is_testenv_declared root` returns 1. |
| `is_testenv_reserved` | `(<name>)` → 0/1 | 0 if `<name>` is `root` or `testenv`. |
| `is_testenv_lazy` | `(<name>)` → 0/1 | 0 if `<name>` is declared with `lazy = true`, 1 otherwise (including: not declared at all). |
| `list_testenv_names` | `()` → stdout | Print declared env names + `root` (reserved), one per line. |
| `_testenvs_name_to_index` | `(<name>)` → int via stdout | Private: 0-based index of `<name>` in `PYVE_TESTENVS_NAMES`, or return 1. |
| `_testenv_backend_of` / `_testenv_extra_of` / `_testenv_manifest_of` | `(<name>)` → string | Private accessors: print the named field, or return 1 if name is unknown. |
| `_testenv_requirements_of` | `(<name> <out_var>)` | Private: populate the caller-named array with the env's requirements list (uses `eval` against `PYVE_TESTENV_REQUIREMENTS_Q[i]`'s shell-quoted form). |

**Companion helper:** [`lib/pyve_testenvs_helper.py`](../../lib/pyve_testenvs_helper.py) — the Python tomllib reader, invoked via `${PYVE_PYTHON:-python} lib/pyve_testenvs_helper.py <pyproject.toml>`. Emits plain bash-assignment syntax (no `declare`) to land assignments in the calling function's global scope under bash 3.2 — see the inline comment for the rationale.

**Wire format (V3 — bash-array-literal, plain assignment).** Populated by `read_testenv_config`:

```bash
PYVE_TESTENVS_DEFAULT="testenv"
PYVE_TESTENVS_NAMES=("testenv" "hardware")
PYVE_TESTENV_BACKEND=("venv" "micromamba")
PYVE_TESTENV_LAZY=("0" "1")
PYVE_TESTENV_EXTRA=("" "")
PYVE_TESTENV_MANIFEST=("" "src/templates/environment.yml")
PYVE_TESTENV_REQUIREMENTS_Q=("requirements-dev.txt" "")
```

Parallel indexed arrays keyed by position in `PYVE_TESTENVS_NAMES`. Bash-3.2-safe (no `declare -A`). Spike decision rationale (`jq` vs `key=value` vs array-literal): [spike-m-f-testenvs-config.md §Decision 3](.archive/phase-m-spike-f-testenvs-config.md).

**Caching policy: none.** The Python helper is invoked at most once per `pyve` command. Cold-start measured ~60 ms (Python startup alone is ~44 ms — the 30 ms threshold floated in the spike was below pyve's existing baseline). Caching's complexity (invalidation, concurrency, stale-cache support) was judged a worse trade than the marginal 16 ms. Decision recorded in [spike-m-f-testenvs-config.md §Decision 2](.archive/phase-m-spike-f-testenvs-config.md).

**Validation locus: the Python helper, at read time.** Cross-rule checks (`requirements ⊕ extra ⊕ manifest`, `manifest requires conda backend`, reserved-name violations, unknown backend) live in `validate()` in `pyve_testenvs_helper.py`. Errors are batched, printed to stderr with the prefix `error: pyve.testenvs.<env>[.<key>]: <message>`, exit status **2** (distinct from operation-failed exit 1). Filesystem existence checks (does `requirements-dev.txt` actually exist on disk) are **deferred to consumers** — `pyve testenv install` is the right surface for "manifest not found" errors. Spike: [§Decision 4](.archive/phase-m-spike-f-testenvs-config.md).

**Side mode: `--resolve-extra <pyproject> <extra_name>` (Story M.l).** The same Python helper, invoked with `--resolve-extra <pyproject_path> <extra_name>` as its first three argv entries, emits the resolved package list from `[project.optional-dependencies].<extra_name>` — one package spec per line. Used by `_testenv_install_venv` to expand a declared `extra = "<n>"` into a concrete `pip install` argument list. Errors with exit **2** + stderr message when pyproject.toml is missing, the extra is not declared (lists available extras), or the extra is not a list. Reusing the same helper file (instead of a new `pyve_extra_helper.py`) keeps every pyproject-reading concern in one auditable place.

**Reserved-name semantics.** `root` is the project's main `.venv/` (or conda env) — selection-only, **cannot** be redeclared in `[tool.pyve.testenvs]`. `testenv` is the well-known default at `.pyve/testenvs/testenv/...` — **may** be redeclared to override its defaults. Both names are excluded from any user-declared name space.

**Python interpreter resolution.** `read_testenv_config` honors `${PYVE_PYTHON:-python}`. Useful for bats tests (which cwd into temp dirs that break relative PATH entries via the asdf shim) and for any caller that needs to pin a specific interpreter. The default `python` works in any pyve-activated shell.

**Consumers (out of scope for M.g, landing in later stories):**

- M.h.1–M.h.4 (this bundle): `.state` schema + helpers, legacy-layout migration helper, opportunistic-fallback wiring + consumer sweep, docs sweep.
- M.i: `testenv` namespace leaves (`testenv_init`, `_install`, `_purge`, `_run`) accept the optional `<name>` argument.
- M.j: per-env install lock at `.pyve/testenvs/<name>/.lock` (`mkdir`-based portable lock; pid file inside; `--no-wait` fast-fails on collision; stale-lock reclamation via `kill -0`; landed).
- M.k: conda backend plumbing — `_testenv_init_conda` / `_testenv_install_conda` in `lib/commands/testenv.sh`, `inherit` resolution via `_testenv_resolve_backend`, single-env + iteration install paths dispatch on resolved backend (landed). `pyve testenv run` for conda envs is **not** in M.k — kept venv-only via `assert_testenv_venv_backend` because PATH-only activation does not set `CONDA_PREFIX` / `CONDA_PYTHON_EXE`. See the *Conda backend dispatch* subsection below.
- M.l: venv manifest sources — `_testenv_install_venv` (renamed from `testenv_install` for symmetry with M.k's `_testenv_install_conda`) dispatches on declared `requirements = [...]` / `extra = "<n>"` with a CLI `-r <file>` override and an auto-detect `requirements-dev.txt` / bare-pytest fallback chain (landed). The Python helper grew a `--resolve-extra` side mode to expand declared extras into a concrete package list.
- M.m: `pyve test --env <name>` resolver extension — accepts any declared name, defaults to `[tool.pyve.testenvs].default`, hard-errors on undeclared names (lists valid choices), hard-errors on conda-backed envs (run is venv-only), hard-errors on unprovisioned lazy envs with an install hint, touches `.state.last_used_at` on the success path. `ensure_testenv_exists` and `_testenv_init_conda` write initial `.state` on env creation so the touch has something to update (landed).
- M.n: lazy provisioning — `pyve test --env <lazy-name>` auto-provisions on first targeted use via `ensure_testenv_exists` + `_testenv_install_with_lock`; `PYVE_NO_AUTO_PROVISION=1` opt-out restores the M.m hard-error for strict CI (landed).
- M.o: silent-skip advisory generalization — `_test_main_env_has_pytest` → `_test_env_has_pytest <name>`; advisory in `test_tests` now scans `root` + every declared env and lists every alternative that has pytest importable (landed).
- M.p: `pyve testenv list` / `pyve testenv prune` — `list` prints a table (name / backend / size / last-used / state) over the union of declared + on-disk envs; `prune` has three modes (orphans default, `--unused-since <ISO-date>`, `--all`) with the standard `--force` / TTY confirmation. Consumes the `.state.last_used_at` field M.m started writing (landed).
- M.q: `pyve lock --env <name>` / `pyve lock --all` — extends `lock_environment` (factored: `_lock_main_env` + `_lock_one_env` + `_lock_all_conda_testenvs`). Output lock-file path follows `_lock_env_lock_path` (`tests/env.yml` → `tests/env-lock.yml`). Venv-backed envs, undeclared names, missing manifest declarations / files, and `--env root` all hard-error with precise messages (landed).
- M.n: M.c silent-skip advisory generalized to every named env.
- M.o: `pyve test --env <name>` resolver extension.
- M.p: `pyve testenv list` / `prune`.
- M.q: `pyve lock --env <name>` / `--all`.
- M.r: matrix execution via comma-separated `--env` — `test_tests` factored into a thin CSV dispatcher + per-env worker `_test_run_one_env`; matrix path runs each name in a subshell (sequential), prints `=== Env: <name> ===` per env, suppresses the M.o silent-skip advisory inside the matrix (user explicitly named multiple envs), aggregates exit codes worst-case, and never halts iteration on a failing env (landed).

#### `.state` per-env state file

Each named testenv has a sibling `.state` file at `.pyve/testenvs/<name>/.state` (next to `venv/` or `conda/`). Plain `key=value` lines, sourceable; written via `state_write`, read via `state_read`. Schema:

| Field | Meaning | Example |
|---|---|---|
| `backend` | The backend used to provision this env. One of `venv`, `micromamba`, `inherit`. | `backend=micromamba` |
| `manifest` | Relative path to the manifest source (requirements.txt, environment.yml, or empty for an implicit-default env). | `manifest=tests/env.yml` |
| `manifest_sha256` | SHA-256 of the manifest contents at provisioning time. Empty when no manifest. Drives M.p's "stale" indicator. | `manifest_sha256=abc123…` |
| `provisioned_at` | Unix epoch seconds when the env was first built. | `provisioned_at=1700000000` |
| `last_used_at` | Unix epoch seconds of the most recent `pyve test --env <name>`. Touched by M.o; consumed by M.p's `prune --unused-since`. `0` until first use. | `last_used_at=0` |

**Helpers in [`lib/testenvs.sh`](../../lib/testenvs.sh):**

| Function | Behavior |
|---|---|
| `state_path <name>` | Print `.pyve/testenvs/<name>/.state`. |
| `state_write <name> <backend> [manifest=<path>] [manifest_sha256=<hex>] [provisioned_at=<epoch>] [last_used_at=<epoch>]` | Write/overwrite. Required positional `<name> <backend>`; optional keyword args parsed by splitting on the first `=` (so manifest paths with embedded `=` survive). Missing optional fields default to empty / current epoch / `0`. Unknown keyword keys hard-error. |
| `state_read <name>` | Populate `PYVE_TESTENV_STATE_{BACKEND,MANIFEST,MANIFEST_SHA256,PROVISIONED_AT,LAST_USED_AT}` in the calling shell. Returns 1 (no shell mutation) if the file is missing. **Parses via `IFS= read` loop, NOT `source`** — a malformed `.state` cannot inject arbitrary shell. |
| `state_touch_last_used <name>` | Read + rewrite, updating only `last_used_at` to the current epoch. Returns 1 if `.state` is missing. |

#### Legacy-layout migration

**The v2.7→v2.8 structural boundary.** v2.7 and earlier hard-coded a single testenv at `.pyve/testenv/venv/` (singular `testenv`, driven by the `TESTENV_DIR_NAME` global in `pyve.sh`). v2.8 generalizes to `.pyve/testenvs/<name>/{venv,conda}/` (plural, name-keyed). The reserved `testenv` resolves to `.pyve/testenvs/testenv/venv/`.

**`migrate_legacy_testenv_layout` in [`lib/testenvs.sh`](../../lib/testenvs.sh)** is the one-shot mover. Four outcome cases:

| State | Action |
|---|---|
| `.pyve/testenvs/testenv/venv/` exists (new layout already in place) | No-op (idempotent). |
| `.pyve/testenv/venv/` exists; new layout absent | `mkdir -p .pyve/testenvs/testenv`, `mv .pyve/testenv/venv .pyve/testenvs/testenv/venv`, write initial `.state` via M.h.1's `state_write` (`backend=venv`, `provisioned_at=<legacy mtime>`, defaults elsewhere), `rmdir .pyve/testenv` if empty, log a one-line `info()` so the user sees what happened. |
| Both legacy and new exist | No-op (preserve new; leave legacy alone — silent deletion of user state is the wrong default). |
| Neither exists (greenfield) | No-op. |

**Two call sites wired in M.h.3:**

1. **`pyve update`** — `update_project` in [`lib/commands/update.sh`](../../lib/commands/update.sh) calls a thin private wrapper `_update_migrate_legacy_layout` as a pre-step (after the config sanity check, before `header_box`). The wrapper exists so the wiring is grep-visible from `update.sh` for source-level audit; a regression test asserts the call by name.
2. **Opportunistic-migration fallback in `resolve_testenv_path testenv`** — when only the legacy layout exists, the resolver runs the migration as a side effect before returning the new path. Means `pyve test` / `pyve testenv …` / `pyve check` / `pyve status` work even on a v2.7-era project that hasn't yet run `pyve update`. Only the reserved `testenv` name triggers migration; `root` and user-declared named envs short-circuit.

**Consumer sweep (M.h.3).** Every reference to `.pyve/$TESTENV_DIR_NAME/venv` or hard-coded `.pyve/testenv/venv` was replaced with `resolve_testenv_path testenv` (or via `testenv_paths` in [`lib/utils.sh`](../../lib/utils.sh), which derives from it). Files swept: `lib/utils.sh`, `lib/commands/{test,testenv,check,status,purge}.sh`. A bats test in [`tests/unit/test_testenvs_activate.bats`](../../tests/unit/test_testenvs_activate.bats) greps the production files and fails if a legacy literal is ever re-introduced.

**`--keep-testenv` semantic expansion.** `pyve purge --keep-testenv` previously preserved the singleton `.pyve/testenv/`; it now preserves the whole `.pyve/testenvs/` tree, covering the default `testenv` plus any user-declared named envs from `[tool.pyve.testenvs]`. The single-env preservation behavior was the pre-named-envs equivalent of the same intent.

**Gitignore template.** [`lib/utils.sh`](../../lib/utils.sh)'s Pyve-managed `.gitignore` section emits `.pyve/testenvs` (was `.pyve/testenv`) — covers the new layout for fresh `pyve init` runs.

**`TESTENV_DIR_NAME` global** in `pyve.sh` is retained as a back-compat constant pointing at `testenv` (the reserved name). No internal code reads it post-M.h.3; the constant exists only so any external script referencing it doesn't break. Deprecation-removal can be a later cleanup story.

#### v2 → v3 state-directory boundary

**The v2.8 → v3.0 structural boundary.** Phase N consolidates state under a single root: `.pyve/envs/<name>/<backend>/`. The same nested shape that v2.8 used for testenvs (`.pyve/testenvs/<name>/{venv,conda}/`) now applies to *every* declared env from `pyve.toml` — run / test / utility / temp. One root, one shape, plugin-friendly: each backend plugin (venv, micromamba, future Node, future Go) owns its subdirectory under `<name>/`.

**v3 on-disk layout:**

```
.pyve/
  envs/
    root/             ← [env.root]    (purpose = "utility")
      venv/             venv-backed
      # or conda/       micromamba-backed (one level deeper than v2)
    testenv/          ← [env.testenv] (purpose = "test")
      venv/
    smoke/            ← [env.smoke]   (custom test env)
      venv/
```

**v2 → v3 path mapping:**

| v2 location | v3 location | Migration owner |
|---|---|---|
| `.pyve/testenv/venv/` (v2.7 singular) | `.pyve/envs/testenv/venv/` | `migrate_legacy_env_layout` (opportunistic, fired by `resolve_env_path testenv` and `pyve update`) |
| `.pyve/testenvs/<name>/venv/` (v2.8 plural, venv-backed) | `.pyve/envs/<name>/venv/` | `migrate_legacy_env_layout` (opportunistic) |
| `.pyve/testenvs/<name>/conda/` (v2.8 plural, conda-backed) | `.pyve/envs/<name>/conda/` | `migrate_legacy_env_layout` (opportunistic) |
| `.pyve/testenvs/<name>/.state` (v2.8 state sibling) | `.pyve/envs/<name>/.state` | `migrate_legacy_env_layout` (opportunistic) |
| `.pyve/envs/<configured_name>/` (v2.x micromamba main env) | `.pyve/envs/root/conda/` | `pyve self migrate` (Story N.g, deterministic) |

**Path-construction helpers (post-N.f).** `state_path` and `resolve_env_path` in [`lib/envs.sh`](../../lib/envs.sh) produce v3 paths. Production code must route through these helpers; hard-coded `.pyve/testenvs/...` literals are forbidden and caught by the regression sweep in [`tests/unit/test_testenvs_activate.bats`](../../tests/unit/test_testenvs_activate.bats).

**Why N.f handles only the testenv-side rename, not the micromamba main-env move.** The micromamba main-env relocation (`.pyve/envs/<old_name>/` → `.pyve/envs/root/conda/`) is a rename + restructure at once: the env loses its user-chosen name and gains a backend-subdir. That cutover ships with `pyve self migrate` (Story N.g) where the user gets full `.pyve/.v2-legacy/` backup and rollback. N.f's scope is the flat parent swap (`testenvs` → `envs`) — same name, same shape, opportunistically migrated so pre-N.g code paths don't silently lose envs.

#### v3.0-only read-compat layer — removed in Subphase N-10

`manifest_load` in [`lib/manifest.sh`](../../lib/manifest.sh) **synthesizes** the v3 array shape from legacy v2 sources when `pyve.toml` is absent. This is the **deprecation-window** mechanism that lets v2.7/v2.8 projects continue to operate against v3.0 binaries *without* having to run `pyve self migrate` first.

**Triggering condition.** Synthesis fires only when `pyve.toml` is missing AND at least one v2 **config** source exists — `.pyve/config` (the YAML main-env declaration) or `[tool.pyve.testenvs.*]` (the v2.8 named-testenv declarations in `pyproject.toml`). Bare `.pyve/testenvs/` on disk is state, not configuration; it does not trigger synthesis (the N.h banner still fires for the user-visible nudge, but the manifest stays empty for that pathological case).

**Synthesis mapping** mirrors what `pyve self migrate` (Story N.g) writes to `pyve.toml` — but populates the `PYVE_*` arrays directly instead of going through TOML text:

- Always emits `[env.root]` (`purpose = "utility"`, `backend` from `.pyve/config:backend` or empty).
- Each declared testenv → `[env.<name>]` (`purpose = "test"`, plus `backend` / `lazy` / `extra` / `manifest` / `requirements` carried over from the v2 declaration).
- The env named `testenv` (or, if none, the first declared) gets `default = "1"`.
- When `.pyve/config` exists but `pyproject.toml` has no testenvs block, `read_env_config`'s implicit-default "testenv" entry is included so v2 projects relying on it keep working.

**One-shot deprecation warning per (session, cwd).** Each synthesis emits a single `warning: pyve is reading legacy v2 sources …` line to stderr, memoized via a sentinel under `${XDG_STATE_HOME:-$HOME/.local/state}/pyve/legacy-read-warn-<session>-<cksum-of-cwd>`. The session key reuses the N.h banner's `PYVE_V2_BANNER_SESSION` override seam so test harnesses (and explicit user override) work identically across both surfaces.

**N-10 cleanup is mechanical.** Every read-compat code path in `lib/manifest.sh` is tagged with the literal comment `v3.0-only: remove in N-10`. A unit test in [`tests/unit/test_n_i_read_compat.bats`](../../tests/unit/test_n_i_read_compat.bats) asserts the marker exists. The N-10 sweep removes:

1. The `_manifest_has_legacy_sources` / `_manifest_synthesize_from_legacy` / `_manifest_deprecation_warn_legacy` helpers.
2. The fallback branch in `manifest_load` that calls them.
3. The N.h soft banner (per Subphase N-10's plan — replaced by the hard interactive gate).
4. The corresponding regression tests.

After N-10, `manifest_load` on a missing-pyve.toml project returns the empty-config baseline unconditionally; v2-configured projects must run `pyve self migrate` to function.

#### Conda backend dispatch

`pyve testenv init/install` now supports conda-backed envs declared as `backend = "micromamba"` or `backend = "inherit"` in `[tool.pyve.testenvs.<name>]`. The plumbing reuses `lib/micromamba_core.sh::get_micromamba_path` (binary resolution: project sandbox → user sandbox → system PATH) — no new bootstrap path is introduced. Conda envs land at `.pyve/testenvs/<name>/conda/` (the resolver shape); no `.envrc` is ever emitted for testenvs (testenvs are activated through their wrapper commands, not direnv).

| Function | Signature | Description |
|---|---|---|
| `_testenv_init_conda` | `(<name> <env_path> <manifest>)` | Idempotent create. If `<env_path>/conda-meta` already exists → info+skip. Else: validate `<manifest>` is non-empty and the file exists, then `micromamba create -p <env_path> -f <manifest> -y`. Conda's `create` both creates and installs packages in one shot — there is no "empty env" intermediate state for the conda backend, in contrast to venv's `python -m venv` (empty) + later `pip install`. |
| `_testenv_install_conda` | `(<name> <env_path> <manifest>)` | Sync an existing conda env to its manifest via `micromamba install -p <env_path> -f <manifest> -y`. If the env directory is missing (`conda-meta` absent), errors with a `pyve testenv init <name>` hint instead of silently creating — keeps the verbs aligned with venv (`init` creates; `install` populates). |
| `_testenv_install_with_lock` | `(<name> <env_path> <req_file> <lock_mode>)` | Story M.j wrapper, extended in M.k. Acquires the per-env install lock, dispatches on `_testenv_resolve_backend`: `micromamba` → `_testenv_install_conda` (`manifest` from declaration); else → `testenv_install` (pip). Trap covers both branches' exit-1 paths and SIGINT. |

**Manifest declaration is required.** A conda-backed env with no `manifest` declared in `[tool.pyve.testenvs.<name>]` hard-errors at init/install time with a stderr hint pointing at the canonical declaration. The Python helper does not enforce this at validation time (M.g's batched errors only cover `requirements ⊕ extra ⊕ manifest` and `manifest requires conda backend`); the runtime catch in `_testenv_init_conda` / `_testenv_install_conda` is the surface where the user sees it.

**`backend = "inherit"` resolves at runtime via `.pyve/config`.** `_testenv_resolve_backend` returns the literal `venv` or `micromamba` based on the main env's recorded backend; the on-disk path slot from `resolve_testenv_path` follows the same resolution, so a project that switches main backend then re-runs `pyve testenv init <inherited-name>` provisions at the correct layout shape. The resolver and the dispatch are the single source of truth — neither inlines the `read_config_value backend` check.

**`pyve testenv run` is venv-only.** `testenv_run` exports `VIRTUAL_ENV` and prepends `<env>/bin` to `PATH`, then `exec`s. For conda envs this is insufficient — `CONDA_PREFIX` / `CONDA_PYTHON_EXE` are not set, so Python tools that introspect their interpreter via conda's env vars misbehave. M.k keeps the venv-only gate via `assert_testenv_venv_backend`; the error message points at the manual workaround `micromamba run -p .pyve/testenvs/<name>/conda <command>`. Conda `run` support is a future-story candidate, not in M.k's scope.

**Iteration includes conda envs (M.k).** `_testenv_install_all_nonlazy` no longer skips conda-backed envs with a "see Story M.k" line. Each non-lazy declared env (venv or conda) is iterated through `_testenv_install_with_lock`, which dispatches on resolved backend. Lazy envs are still skipped (M.m wires the auto-provision path on first targeted use).

---

### `lib/manifest.sh` — v3.0 Canonical Manifest Reader

Reads `pyve.toml` — the v3.0 root-level canonical declarative manifest introduced by Phase N — via the Python `tomllib` helper [`lib/pyve_toml_helper.py`](../../lib/pyve_toml_helper.py) and exposes a flat accessor surface for downstream consumers. **`pyve.toml` is the single canonical declaration in v3.0+**; it supersedes both `.pyve/config` (YAML, v2.x main env) and `[tool.pyve.testenvs.*]` (pyproject.toml, Phase M testenvs). After v3.0, `.pyve/` holds materialized state only — never declaration. Foundation laid in Story N.a; CLI wiring (`pyve init` write path, dispatcher) lands in later N-1 stories.

**`pyve.toml` schema (v3.0):**

```toml
# Schema-version key — top-level, required (defaults to "3.0" if absent).
pyve_schema = "3.0"

[project]
name = "demo"

# Each [env.<name>] declares one project environment surface.
# Every field is optional; the helper applies the documented defaults.
[env.root]
purpose  = "utility"     # one of: run | test | utility | temp
backend  = "venv"        # plugin-registered backend name (free-form string)
path     = "."           # working/detection root (monorepo support)
default  = false         # at most one env may set true
lazy     = false         # opt-in lazy provisioning

# Structured attributes (optional; intended for plugin consumption)
app_type   = "library"
frameworks = ["sveltekit"]
languages  = ["python"]

# Backend-source attributes (carried over from Phase M [tool.pyve.testenvs]).
# `requirements`, `extra`, `manifest` are mutually exclusive.
requirements = ["requirements-dev.txt"]
extra        = "dev"
manifest     = "tests/env.yml"

[env.testenv]
purpose = "test"
default = true
```

**Field semantics:**

| Field | Type | Default | Notes |
|---|---|---|---|
| `pyve_schema` | string (top-level) | `"3.0"` | Schema-version key. v3.0-only valid value; other versions hard-error at parse time. R8 (per-env / per-plugin schema versioning) generalizes this. |
| `[project].name` | string | `""` | Display name. |
| `[env.<name>].purpose` | enum string | `""` (raw); default rules applied in Story N.d | One of `run`, `test`, `utility`, `temp`. Story N.d wires the default-purpose rules (`testenv` → `test`; `root` → `utility`; else → `utility`) and the `pyve test --env <name>` selector. |
| `[env.<name>].backend` | string | `""` (raw) | Plugin-registered backend identifier. v3.0 ships `venv`, `micromamba`, `inherit` (Python plugin, N-2) and `pnpm`/`npm`/`yarn` (Node plugin, N-3). N.a accepts any non-empty string — plugin enforcement lands in N-2's contract. |
| `[env.<name>].path` | string | `"."` | Working/detection root (monorepo / sub-surface support per R10). |
| `[env.<name>].default` | bool | `false` | At most one env per manifest may declare `default = true`. |
| `[env.<name>].lazy` | bool | `false` | Carried over from Phase M; opt-in lazy provisioning (consumer = N.d/N.e). |
| `[env.<name>].app_type` | string | `""` | Structured attribute (free-form for N.a; plugin-defined vocabularies in later stories). |
| `[env.<name>].frameworks` | string list | `[]` | Structured attribute. |
| `[env.<name>].languages` | string list | `[]` | Structured attribute. |
| `[env.<name>].requirements` | string list | `[]` | Phase M carryover; mutex with `extra` / `manifest`. |
| `[env.<name>].extra` | string | `""` | Phase M carryover; mutex with `requirements` / `manifest`. |
| `[env.<name>].manifest` | string | `""` | Phase M carryover; mutex with `requirements` / `extra`. |

**Validation rules (enforced by the Python helper at read time, stderr-prefixed `error: pyve.<key>: ...`, exit 2):**

1. `pyve_schema` must equal `"3.0"` (absent → defaulted; any other literal → error).
2. Each env's `purpose`, if non-empty, must be one of the four valid values.
3. At most one env may declare `default = true`.
4. Per env, at most one of `requirements` / `extra` / `manifest` may be declared.

**`lib/manifest.sh` accessor surface:**

| Function | Signature | Description |
|---|---|---|
| `manifest_load` | `([<pyve.toml path>])` | Invoke the Python helper and populate the v3 parallel-indexed-array state in the calling shell. Default path: `./pyve.toml`. Missing file → empty config (`PYVE_ENV_NAMES=()`, schema `"3.0"`). Validation errors propagate via non-zero exit + stderr. |
| `manifest_list_envs` | `()` → stdout | Print declared env names, one per line. Empty when no envs declared. |
| `manifest_get_env` | `(<name>)` → 0/1 | Predicate: 0 if `<name>` appears in `PYVE_ENV_NAMES`, 1 otherwise. |
| `manifest_get_purpose` | `(<name>)` → string | Print the env's `purpose` (raw — empty if unset). Returns 1 if name is unknown. |
| `manifest_get_backend` | `(<name>)` → string | Print the env's `backend` (raw — empty if unset). Returns 1 if name is unknown. |
| `manifest_get_path` | `(<name>)` → string | Print the env's `path` (defaults to `"."`). Returns 1 if name is unknown. |
| `manifest_get_app_type` | `(<name>)` → string | Print the env's `app_type` (empty if unset). Returns 1 if name is unknown. |
| `manifest_resolve_purpose` | `(<name>)` → string | **Story N.d.** Resolve `<name>` to one of `run | test | utility | temp` (always returns one of the four; never fails, never empty). If `<name>` is in `PYVE_ENV_NAMES` with a non-empty declared `purpose`, returns the declared value. Else applies the name-based default rule: `testenv` → `test`; `root` → `utility`; otherwise → `utility`. Works even when `manifest_load` has not been called (PYVE_ENV_NAMES unset is treated as "no declared envs"). Canonical resolver for purpose-gating selectors (e.g. `pyve test --env <name>` in [lib/commands/test.sh](../../lib/commands/test.sh)). |
| `manifest_is_default` | `(<name>)` → 0/1 | 0 if env has `default = true`, 1 otherwise. |
| `manifest_is_lazy` | `(<name>)` → 0/1 | 0 if env has `lazy = true`, 1 otherwise. |
| `manifest_get_frameworks` | `(<name> <out_var>)` | Populate caller-named array with the env's `frameworks` list (uses `eval` against shell-quoted form). |
| `manifest_get_languages` | `(<name> <out_var>)` | Populate caller-named array with the env's `languages` list. |
| `manifest_get_requirements` | `(<name> <out_var>)` | Populate caller-named array with the env's `requirements` list. |
| `_manifest_name_to_index` | `(<name>)` → int via stdout | Private: 0-based index in `PYVE_ENV_NAMES`, or return 1. Bash-3.2-safe under `set -u`. |

**Companion helper:** [`lib/pyve_toml_helper.py`](../../lib/pyve_toml_helper.py) — Python `tomllib` reader, invoked via `${PYVE_PYTHON:-python} lib/pyve_toml_helper.py <pyve.toml>`. Emits plain bash-assignment syntax (no `declare`) to land assignments in the calling function's global scope under bash 3.2.

**Wire format.** Populated by `manifest_load`:

```bash
PYVE_SCHEMA_VERSION="3.0"
PYVE_PROJECT_NAME="demo"
PYVE_ENV_NAMES=("root" "testenv")
PYVE_ENV_PURPOSE=("utility" "test")
PYVE_ENV_BACKEND=("venv" "venv")
PYVE_ENV_PATH=("." ".")
PYVE_ENV_DEFAULT=("0" "1")
PYVE_ENV_LAZY=("0" "0")
PYVE_ENV_EXTRA=("" "")
PYVE_ENV_MANIFEST=("" "")
PYVE_ENV_APP_TYPE=("" "")
PYVE_ENV_REQUIREMENTS_Q=("" "")
PYVE_ENV_FRAMEWORKS_Q=("" "")
PYVE_ENV_LANGUAGES_Q=("" "")
```

Parallel indexed arrays keyed by position in `PYVE_ENV_NAMES`. Bash-3.2-safe (no `declare -A`). List-valued fields (`_REQUIREMENTS_Q`, `_FRAMEWORKS_Q`, `_LANGUAGES_Q`) carry one shell-quoted joined string per env; consumers expand with `eval "out=( $val )"` — same wire shape Story M.g uses for `PYVE_TESTENV_REQUIREMENTS_Q`.

**Subphase N-1 consumer roadmap (not in scope for N.a):**

- **N.b:** rename `lib/testenvs.sh` → `lib/envs.sh` and `lib/commands/testenv.sh` → `lib/commands/env.sh` (the v2 helper rename — independent of this v3 manifest reader).
- **N.c:** register `pyve env <sub>` dispatcher; `pyve testenv <sub>` becomes Category A legacy sugar.
- **N.d:** `purpose:` default rules + `pyve test --env <name>` selector semantics layered on top of `manifest_get_purpose`.
- **N.e:** `pyve init` writes `pyve.toml` on fresh projects.
- **N.f:** decide the final v3 state-directory path.
- **N.g:** `pyve self migrate` consumes both this manifest helper (write path) and the legacy testenvs helper (read path) to produce a fresh `pyve.toml` from v2 sources.
- **N.h:** soft migration banner detects "v2 sources present AND `pyve.toml` absent."
- **N.i:** read-compat layer — when `pyve.toml` is absent but legacy sources exist, parse them and emit a synthesized in-memory v3 shape so the rest of pyve sees a uniform model.

**No sourcing in `pyve.sh` yet.** Per Story N.a's "no CLI dispatcher changes," `lib/manifest.sh` is not added to `pyve.sh`'s explicit source block in this story. Sourcing lands when the first command consumes the helper (Story N.e — `pyve init` write path — is the canonical first consumer).

---

### `lib/ui/core.sh` — Unified UI Helpers

Core module of the extractable `lib/ui/` library: the shared terminal UX primitives used across every pyve command. The module contains **no pyve-specific identifiers** (no `pyve_`-prefixed names, no references to backends, `pyve.toml`, or any other pyve concept) — pyve-specific logic lives in the callers, not the helpers. Every module under `lib/ui/` follows the same discipline, so the directory can eventually be extracted as a standalone UX library.

| Item | Signature | Description |
|------|-----------|-------------|
| Color constants | `R` `G` `Y` `B` `C` `M` `DIM` `BOLD` `RESET` | ANSI color codes; empty under `NO_COLOR=1` |
| Symbols | `CHECK` `CROSS` `ARROW` `WARN` | Pre-colorized status glyphs (`✔` `✘` `▸` `⚠`); plain glyphs under `NO_COLOR=1` |
| `banner` | `(title)` | Section banner in blue + bold |
| `info` | `(msg)` | Dimmed cyan-arrow line |
| `success` | `(msg)` | Green-check line |
| `warn` | `(msg)` | Yellow-warn line |
| `fail` | `(msg)` | Red-cross line; exits 1 |
| `confirm` | `(prompt)` → 0 on yes | `[Y/n]` prompt, default yes; clean-exits 0 on abort |
| `ask_yn` | `(prompt)` → 0/1 | `[y/N]` prompt, default no |
| `divider` | `()` | Dimmed horizontal rule |
| `run_cmd` | `(cmd args…)` | Echoes `$ cmd args…` dimmed, then executes; propagates exit code |
| `header_box` | `(title)` | Rounded-box cyan + bold header |
| `footer_box` | `()` | Rounded-box green + bold "✓ All done." footer |
| `_edit_distance` | `(s1, s2)` → int | Levenshtein distance on stdout. Consumer: `unknown_flag_error()` in `pyve.sh`. bash-3.2-safe flat-array DP. |

**Sourcing.** `pyve.sh` sources `lib/ui/core.sh` (and its `lib/ui/` siblings `run.sh` / `progress.sh` / `select.sh`) before any command dispatcher runs. Sourcing is explicit — one `source` line per module.

**bash-3.2 compatibility guard.** `lib/ui/core.sh` must source cleanly under macOS's system `/bin/bash` (3.2.57): no `declare -A`, no `${var^^}` / `${var,,}` case operators, no `readarray`. Locked in by the regression tests at [tests/unit/test_ui.bats](../../tests/unit/test_ui.bats) (a "no `declare -A`" grep + a `/bin/bash` sourcing test). The "no pyve-specific identifiers" invariant is enforced by a sibling grep test in the same file.

**Delegation from `log_*`.** The `log_info` / `log_warning` / `log_error` / `log_success` helpers in `lib/utils.sh` emit the unified glyph palette (`▸` / `⚠` / `✘` / `✔`, two-space indent, stderr-vs-stdout routing preserved). They do **not** delegate to `info` / `warn` / `fail` / `success` directly — `log_error` keeps its non-exiting contract (calling `fail` would change exit semantics for its many callers), and bats tests that source `lib/utils.sh` standalone (without `lib/ui/core.sh`) rely on the `${CHECK:-✔}` / `${WARN:-⚠}` / `${CROSS:-✘}` / `${ARROW:-▸}` fallbacks.

---

## Plugin layer

The plugin layer is the seam through which Pyve materializes language-specific environments behind a uniform contract. Python and Node ship as reference plugins in v3.0; the contract is designed to generalize to any future ecosystem (Rust, Go, mobile toolchains, …) without changing the dispatcher.

The env-spec **vocabulary** this layer consumes — the closed `purpose` set, the backend categories, and the `[env.<name>]` / `[plugins.<name>]` attribute grammar — is owned and versioned by the env-spec contract. It is referenced here by pointer rather than re-enumerated: see [`wizard-env-contract.md` § "Closed vocabulary (spec_version 3.0)"](project-guide-requests/wizard-env-contract.md) and [`env-dependencies-template.md` § 2 "Conventions & Terminology"](project-guide-requests/env-dependencies-template.md). The worked design rationale (the env-model spike's S1–S11 conclusions) lives in [`phase-n-2-spike-env-model-worked-examples.md`](.archive/phase-n-2-spike-env-model-worked-examples.md).

Three coordinated registries split the responsibilities: the **plugin registry** ([lib/plugins/registry.sh](../../lib/plugins/registry.sh)) tracks which plugins are active; the **contract default-hooks** ([lib/plugins/contract.sh](../../lib/plugins/contract.sh)) provide silent no-op fallbacks for every documented hook; the **backend-provider registry** ([lib/plugins/backend_registry.sh](../../lib/plugins/backend_registry.sh)) tracks which backends each plugin owns, their category, and routes backend-specific calls through a uniform dispatcher.

### Architecture & the contract

**The 14 contract hooks.** Every plugin may implement any subset; unimplemented hooks fall through to the silent no-op defaults in `contract.sh`. The hooks group as:

| Group | Hooks | When called |
|---|---|---|
| Identity | `manifest_namespace` | At registration; returns the plugin's `[plugins.<name>]` key. |
| Backend setup | `register_backends` | Eagerly at source-time; registers the plugin's backend providers via `bp_register`. |
| Detection | `detect` | Scaffold-time from `pyve init`; auto-selects the backend for fresh projects. |
| Lifecycle (×7) | `init`, `purge`, `update`, `check`, `status`, `run`, `test` | One per `pyve <command>` user surface; routed via `plugin_dispatch`. |
| Activation | `activate` | From `pyve init`'s direnv-emission path; composes the plugin's `.envrc` snippet through PC-1 validation, then delegates the write to the backend-provider activate hook. |
| Diagnostics | `diagnostics` | Reserved for plugin-internal health checks surfaced through `pyve check`. v3.0 ships no implementations. |
| File-management (×2) | `gitignore_entries`, `purge_inventory` | From the gitignore composer and `pyve purge`; the plugin declares the patterns / created-vs-authored paths it owns. |

Total: 1 + 1 + 1 + 7 + 1 + 1 + 2 = 14. The 7 lifecycle hooks and the activation hook are the load-bearing surface for v3.0; `diagnostics` is forward-looking.

**Two dispatch layers.** `plugin_dispatch` and `bp_dispatch` route different concerns:

- **`plugin_dispatch <plugin> <hook> [args...]`** — calls `<plugin>_pyve_plugin_<hook>` if defined, else the no-op default. Owns cross-plugin routing; invoked from `pyve.sh`'s case dispatcher as the public entry boundary.
- **`bp_dispatch <backend> <hook> [args...]`** — calls `<backend>_pyve_bp_<hook>`, dispatched by registered backend name (not plugin name). Owns within-plugin backend-specific shape (venv-vs-micromamba activation paths, for instance); invoked from inside a plugin's hook implementations.

A typical call chain (Python's `activate` hook through both dispatchers):

```
pyve init                                       ← pyve.sh case arm
  plugin_dispatch python init <args>            ← cross-plugin routing
    python_pyve_plugin_init                     ← plugin lifecycle hook
      init_project <args>                       ← Python plugin's implementation
        plugin_dispatch python activate ...     ← re-enters the cross-plugin layer
          python_pyve_plugin_activate           ← plugin's activate hook (PC-1 gate)
            _python_pyve_plugin_envrc_snippet   ← plugin-owned snippet
            validate_envrc_snippet              ← PC-1 validation
            bp_dispatch <backend> activate ...  ← within-plugin backend routing
              {venv,micromamba}_pyve_bp_activate  ← backend shim
                write_envrc_template            ← composer (lib/utils.sh)
```

**Three backend categories.** Each registered backend declares one of `virtualized` / `cache-backed` / `check-only` at `bp_register` time; the category drives `init` / `purge` / `activate` semantics:

- `virtualized` — per-project env dir; PATH activation required for project-pinned binaries. v3.0 ships `venv`, `micromamba` (Python) and `pnpm`, `npm`, `yarn` (Node).
- `cache-backed` — shared user-level dep cache + project lockfile. Designed-in for v3.0; no implementations (first candidates: Rust, Go).
- `check-only` — Pyve verifies presence and version; no install action. Designed-in for v3.0; no implementations (first candidates: mobile toolchains, Docker, Homebrew).

**Implicit-Python rule.** A project with no `[plugins.*]` declarations in `pyve.toml` gets `python` implicitly registered at `path = "."`. This is the migration shape for every v2-vintage project (which had no `[plugins.*]` blocks). Explicit declarations override the implicit expansion; an explicit `[plugins.node]` (with no `[plugins.python]`) does **not** additionally register Python — implicit-Python fires only when `[plugins.*]` is absent entirely.

**Cardinality.** At most one plugin may resolve to `path = "."`. Two declarations both claiming the project root is a manifest error; the registry's load step returns non-zero with a precise diagnostic. The check applies after both explicit registration and implicit-Python expansion.

**PC-1 input safety.** Plugin-emitted content bound for shell-evaluated files (`.envrc`) or git-evaluated files (`.gitignore`) passes through [lib/envrc_safety.sh](../../lib/envrc_safety.sh)'s line-oriented allow-list validators before write. A failing snippet aborts the write; a pre-existing file is left byte-identical. Infrastructure lines emitted by the composer itself (header comments, dotenv conditional, macOS `.DS_Store`) are never validated — they are not plugin-emitted.

---

### Registries — plugin & backend-provider

**`lib/plugins/contract.sh` — the no-op defaults.** Defines `pyve_plugin_default_<hook>()` for every documented hook (the 14 listed above). A plugin that implements only a subset of hooks relies on these defaults; the dispatcher never errors on a missing implementation. Each default is silent: prints nothing, returns 0.

**`lib/plugins/registry.sh` — registration + dispatch.** Maintains `PYVE_PLUGIN_REGISTERED[]` (an indexed array of active plugin names, registration-ordered) and exposes:

| Function | Purpose |
|---|---|
| `plugin_register <name>` | Add a plugin to the active list. Idempotent. |
| `plugin_list_active` | Print active plugin names, one per line, in registration order. |
| `plugin_load_all_from_manifest` | Read `[plugins.*]` from `pyve.toml` via the manifest accessors; register each declared plugin; apply the implicit-Python rule when no plugins are declared; enforce the `path = "."` cardinality check. |
| `plugin_dispatch <name> <hook> [args...]` | Call `<name>_pyve_plugin_<hook>` if defined; else `pyve_plugin_default_<hook>`. Args forwarded. |
| `plugin_registry_reset` | Clear the registered list. Used by tests; not called from production code. |

A plugin becomes active two ways: an explicit `[plugins.<name>]` block in `pyve.toml` (default `path = "."`; provider-private attributes preserved verbatim), or the implicit-Python expansion when `[plugins.*]` is absent entirely. The only core key on a `[plugins.<name>]` block is `path` (default `"."`); every other key is provider-private and preserved verbatim for the plugin to interpret. There is no `role` field — the spatial owner is inferred from `path`.

```toml
[plugins.python]
path = "."

[plugins.svelte]
path = "frontend"
app_type = "spa"     # provider-private; available via manifest_get_plugin_attr
```

**`lib/plugins/backend_registry.sh` — the backend-provider registry.** Where the plugin registry tracks *which plugins are active*, the backend registry tracks *which backends are registered, who owns them, and what category they belong to* — and routes backend-specific operations through a uniform dispatcher. Backends are first-class registered providers inside their plugin (the three categories are described above; v3.0 ships only `virtualized`, with `cache-backed` / `check-only` designed-in but unexercised).

| Function | Purpose |
|---|---|
| `bp_register <plugin> <backend_name> <category>` | Record the (plugin, backend, category) triple. Idempotent for identical re-registration; errors on conflicting re-registration (different plugin or category) or unknown category. |
| `bp_lookup <backend_name>` | Print the owning plugin name. Exit 1 (no output) if unknown. |
| `bp_category <backend_name>` | Print the registered category. Exit 1 if unknown. |
| `bp_list` | Print all registered backend names, one per line, in registration order. |
| `bp_dispatch <backend_name> <hook> [args...]` | Call `<backend>_pyve_bp_<hook>` if defined; else `pyve_bp_default_<cat_sanitized>_<hook>` (category default, hyphens → underscores); else silent return 0. |
| `bp_registry_reset` | Clear all registrations. Used by tests. |

**Internal state:** parallel indexed arrays `PYVE_BP_NAMES[]`, `PYVE_BP_PLUGINS[]`, `PYVE_BP_CATEGORIES[]` (bash 3.2-safe; no associative arrays). Each plugin's `register_backends` hook fires eagerly at source-time, so `bp_register` lands on every invocation regardless of whether `plugin_load_all_from_manifest` has run yet — Python registers `venv` and `micromamba`; Node registers `pnpm` / `npm` / `yarn`.

**Sourcing order** (in `pyve.sh`, explicit — no glob): after `lib/manifest.sh` (the registries read the `PYVE_*` manifest arrays) and before per-command modules (commands dispatch hooks).

---

### Input safety (PC-1) — `lib/envrc_safety.sh`

Pure validators that guard the boundary between plugin-emitted text and pyve's composed `.envrc` / `.gitignore` files. PC-1 (the security risk that a malicious or buggy plugin could smuggle arbitrary shell into a file that direnv later sources) is closed by restricting plugin contributions to two narrow allow-lists.

**`validate_envrc_snippet <text>`** — direnv-stdlib allow-list:

| Accept (per line) | Notes |
|---|---|
| Blank line (whitespace only) | Including indented blanks |
| Comment line | `^[[:space:]]*#.*` — anything after `#` is opaque |
| `PATH_add "<value>"` | Value is double-quoted; no `$(` or backticks anywhere on the line |
| `export VAR="<value>"` | VAR is a shell identifier (`[A-Za-z_][A-Za-z_0-9]*`); value double-quoted; no `$(` or backticks |

Inside the double-quoted value, parameter expansions (`$VAR`, `${VAR}`) are allowed — they're parsed by the shell from inside double quotes, not command substitution. Everything else (unquoted values, `dotenv`/`source` directives, shell control flow, raw commands) is rejected.

**`validate_gitignore_snippet <text>`** — simple-pattern allow-list:

| Accept (per line) | Notes |
|---|---|
| Blank line | |
| Comment line | `^[[:space:]]*#.*` |
| Plain glob pattern | Anything that isn't a blank/comment and contains no `$` (param expansion or command sub) and no backticks |

`.gitignore` patterns never legitimately need a literal `$` — over-rejection is the safe tradeoff against any downstream tool that might shell-interpret a `.gitignore` line.

**Failure mode.** Both validators are line-oriented: one bad line invalidates the whole snippet. The offending line is echoed to stderr (`envrc_safety: rejected line: ...`) so the composer can surface where the violation came from.

**Composer integration.** The activation composer runs `validate_envrc_snippet` over each plugin's `.envrc` contribution before write; the gitignore composer runs `validate_gitignore_snippet` over each plugin's pattern contribution. Composer-owned infrastructure lines (macOS `.DS_Store`, the Pyve-managed state block) are appended after validation.

**Test corpus.** [tests/unit/test_n_m_envrc_safety.bats](../../tests/unit/test_n_m_envrc_safety.bats) groups "accept" and "reject" subsets for each validator. Every smuggling pattern considered (command substitution outside quotes, command substitution inside quotes, backticks, unquoted parameter expansion, non-allow-listed direnv directives, raw shell commands, control flow, identifier-illegal names, mixed-valid-with-one-bad-line) has its own regression test.

---

### Python plugin

The first reference plugin behind the contract, owning the Python ecosystem: backend registrations, file-signal detection, the seven lifecycle/runtime hooks, the activate hook, and the gitignore / purge-inventory data hooks. The command bodies these hooks delegate to — `init_project`, `purge_project`, `update_project`, `check_environment`, `show_status`, `run_command`, `test_tests`, plus the `pyve python set` / `show` leaves and the `python_command` dispatcher — all live in [lib/plugins/python/plugin.sh](../../lib/plugins/python/plugin.sh) (relocated from the v2 `lib/commands/{init,purge,update,check,status,run,test,python}.sh` files, which are deleted). Bash's global function table resolves dispatcher→leaf and cross-command calls regardless of file.

**Identity, registration & detection.**

| Hook | Behavior |
|---|---|
| `python_pyve_plugin_manifest_namespace` | Returns `"python"`. |
| `python_pyve_plugin_register_backends` | `bp_register python venv virtualized` + `bp_register python micromamba virtualized`. Idempotent; fired eagerly at source-time from `pyve.sh`. |
| `python_pyve_plugin_detect` | Scaffold-time file-signal scan; returns `venv` / `micromamba` / `ambiguous` / `none`. |

The detect hook probes the project root for **Python signals** (`pyproject.toml` | `requirements*.txt` | `setup.py` | `*.py`) and **conda signals** (`environment*.yml` | `conda-lock.yml`), then maps: both classes present → `ambiguous`; only conda → `micromamba`; only Python → `venv`; neither → `none`. `detect_backend_from_files` in `lib/backend_detect.sh` is a thin wrapper over `plugin_dispatch python detect`.

The backend-provider activate shims `venv_pyve_bp_activate <env_path> <env_name>` and `micromamba_pyve_bp_activate <env_path> <env_name>` forward to `_init_direnv_venv` / `_init_direnv_micromamba` (which call `write_envrc_template`). At `main()` time, `manifest_load` and `plugin_load_all_from_manifest` are invoked with errors silenced (`2>/dev/null || true`) so a malformed `pyve.toml` — or an unresolvable Python interpreter — never breaks informational commands like `--version` / `--help`; commands that require a valid manifest re-invoke `manifest_load` and report errors at their own level.

#### Lifecycle hooks — init / purge / update

| Hook | Behavior |
|---|---|
| `python_pyve_plugin_init` | Runs `python_pyve_plugin_validate_env_blocks`, runs the `languages` advisory read, then calls `init_project "$@"`. |
| `python_pyve_plugin_purge` | Calls `purge_project "$@"`. No env-block validation — purge runs against the state directory, not the manifest. |
| `python_pyve_plugin_update` | Calls `update_project "$@"`. Manifest validation is deferred to the next `init` cycle. |

`pyve.sh` routes `init` / `purge` / `update` through `plugin_dispatch python <hook> "$@"`, with the `--help` / `PYVE_DISPATCH_TRACE` short-circuits above the dispatch call.

**Env-block validation.** `python_pyve_plugin_validate_env_blocks` iterates `PYVE_ENV_NAMES[]` and checks `purpose ∈ {run, test, utility, temp}` when non-empty (defense-in-depth against synthesized v2 read-compat shapes — the Python helper already rejects unknown purposes at parse time) and `backend ∈` registered backend-provider names via `bp_lookup` when non-empty (an unregistered backend produces a precise error naming the offending env and backend). Empty `purpose` / `backend` are both allowed — `manifest_resolve_purpose` and the per-command default-backend logic handle them.

#### Runtime hooks — check / status / run / test

| Hook | Behavior |
|---|---|
| `python_pyve_plugin_check` | Renders advisories, then calls `check_environment "$@"`. |
| `python_pyve_plugin_status` | Renders advisories, then calls `show_status "$@"`. |
| `python_pyve_plugin_run` | Pure forwarder to `run_command "$@"`. |
| `python_pyve_plugin_test` | Pure forwarder to `test_tests "$@"`. |

`run` and `test` are execution paths, not diagnostic surfaces, so they skip advisory rendering. `check`/`status` must render advisories **before** delegating because `check_environment` (via `_check_summary_and_exit`) and `show_status` are terminal — rendering first also puts setup context above the diagnostic body.

**`manual_steps` schema extension + advisory rendering.** `[env.<name>]` carries an optional `manual_steps` list (parsed by `_normalize_env` in [lib/pyve_toml_helper.py](../../lib/pyve_toml_helper.py); accessor `manifest_get_manual_steps <env> <out_array>` in [lib/manifest.sh](../../lib/manifest.sh), defensive against the unset array on the v2 read-compat path):

```toml
[env.root]
manual_steps = [
    "Open Xcode and accept license",
    "Configure signing identity",
]
```

`_python_pyve_plugin_render_advisories` iterates `PYVE_ENV_NAMES[]` and (1) prints any env's `manual_steps` under a one-time "Manual steps (advisory — pyve does not run these):" header, and (2) warns when an env declares `languages` without `"python"` (`env '<name>' declares languages = [<list>] without 'python' — the Python plugin manages this env`). It is silent when nothing triggers, never affects exit code, and is a no-op when `PYVE_ENV_NAMES` is unset (better to miss advisories than crash). The `languages` rule is conservative — declared-without-`python` only; `["python"]`, `["python","rust"]`, and an absent field are all silent.

**`pyve python set` / `show`** are plugin-private functions (not contract hooks) for Python-version management, alongside the `python_command` dispatcher — all inside the plugin file.

#### Activate hook with PC-1 validation gate

The plugin's `activate` hook composes the plugin-owned `.envrc` snippet, runs it through `validate_envrc_snippet`, and only then delegates the file write — so a malicious or buggy emission cannot reach disk.

```
init_project (in lib/plugins/python/plugin.sh)
    plugin_dispatch python activate <backend> <env_path> <env_name>
        python_pyve_plugin_activate                     ← PC-1 gate
            _python_pyve_plugin_envrc_snippet  ── PC-1 ─→ validate_envrc_snippet
            bp_dispatch <backend> activate              ← backend shape
                {venv,micromamba}_pyve_bp_activate
                    _init_direnv_{venv,micromamba}      ← write_envrc_template
```

The strict allow-list applies only to the **5 plugin-emitted lines** the Python plugin contributes:

```
PATH_add "$rel_bin_dir"
export $sentinel_var="$env_root_expr"
export PYVE_BACKEND="$backend"
export PYVE_ENV_NAME="$env_name"
export PYVE_PROMPT_PREFIX="($backend:$env_name) "
```

Infrastructure lines around them (the header comment, the `if [[ -f ".env" ]]; then dotenv; fi` block, the asdf compat block) are composer-owned and emitted by `write_envrc_template` directly — never validated, because they are not plugin-emitted. The strict allow-list is thus usable for plugins without retroactively rewriting the existing template; `.envrc` output stays byte-equivalent for every existing fixture. On validation failure the hook logs the error, the validator prints the offending line on stderr, the `bp_dispatch` call never fires, no file is written, and any pre-existing `.envrc` is left byte-identical.

#### `.gitignore` + smart-purge hooks

Both ship as data — the plugin returns lists; the composer decides what to do with them.

**`python_pyve_plugin_gitignore_entries`** — language-ecosystem patterns the Python plugin contributes to `.gitignore`:

```
# Python build and test artifacts
__pycache__
*.pyc
*.pyo
*.pyd
*.egg-info
*.egg
.coverage
coverage.xml
htmlcov/
.pytest_cache/
dist/
build/

# Jupyter notebooks
.ipynb_checkpoints/
*.ipynb_checkpoints
```

Output flows through `validate_gitignore_snippet` (the PC-1 gate) before `write_gitignore_template` writes it. On validation failure the plugin contribution is silently dropped (the file still gets composer-owned lines — macOS `.DS_Store`, Pyve infrastructure — so `.gitignore` is never absent).

**`python_pyve_plugin_purge_inventory`** — declares Pyve-created and user-authored paths:

```
created .venv
created .pyve/envs
created .envrc
authored pyproject.toml
authored requirements*.txt
authored setup.py
authored environment.yml
```

Line format: `<class> <path>` where class is `created` (safe to remove on purge) or `authored` (never touch on purge).

**Plugin-vs-composer boundary (same as the `.envrc` activate hook).** The gitignore composer splits the file into composer-owned sections + one plugin-owned section per active plugin:

```
# macOS only                                  ← composer
.DS_Store
                                              ← blank
<python_pyve_plugin_gitignore_entries>        ← plugin (PC-1-validated)
                                              ← blank
# Pyve virtual environment                    ← composer
.pyve/envs
.pyve/testenvs
.envrc
.env
.vscode/settings.json
```

The dynamic venv directory line (`.venv` or the user's `--venv-dir`) is appended by the deduplication pass at the bottom. The legacy `.pyve/testenvs` line is retained so projects mid-migration keep ignoring their pre-v3 state tree. `.gitignore` output stays byte-equivalent for every existing fixture.

**Purge inventory as a data interface.** `purge_project` reads the inventory via `plugin_dispatch python purge_inventory` and surfaces it under `--verbose`:

```
$ pyve --verbose purge --yes
…
Plugin purge inventory:
  created .venv
  created .pyve/envs
  created .envrc
  authored pyproject.toml
  authored requirements*.txt
  …
```

The actual removal calls (`_purge_venv`, `_purge_pyve_dir`, `_purge_envrc`, `_purge_dotenv`, `_purge_gitignore`) stay direct. The data interface is the seam: each plugin declares its own creation/authorship surface, and the purge composer (below) drives cross-plugin removal decisions — a path declared `authored` by any plugin is never removed.

---

### Node plugin

The **second reference plugin** behind the contract — the proof that it generalizes beyond Python. Unlike the Python plugin (whose bodies were *relocated* into the plugin file), the Node plugin was authored fresh against the contract; its hooks mirror the Python plugin's signatures so the two plugin files diff side-by-side. The hooks live in [lib/plugins/node/plugin.sh](../../lib/plugins/node/plugin.sh); runtime-version detection lives in the sibling [lib/plugins/node/runtime_detect.sh](../../lib/plugins/node/runtime_detect.sh).

**Path-awareness (root vs visitor).** Every Node hook takes a leading `<path>` so the plugin works both as the project's root ecosystem (`path = "."`, pure-Node) and as a *visitor* at a sub-tree (`path = "src/frontend"`, the polyglot Python+Node monorepo). Sub-path hooks confine all reads/writes to that sub-tree and emit **project-root-relative** paths (so direnv resolves absolute dirs from where `.envrc` lives, not from the sub-tree).

**Detection + framework.**

| Hook | Behavior |
|---|---|
| `node_pyve_plugin_manifest_namespace` | Returns `"node"`. |
| `node_pyve_plugin_detect [path]` | Prints `"node"` when `package.json` exists at `<path>`, else `"none"`. Scaffold-time only — once `pyve.toml` declares `[plugins.node]`, the manifest is the runtime source of truth. |
| `node_detect_framework [path]` | Prints `"sveltekit"` when `package.json` + `@sveltejs/kit` (or `svelte.config.js`) are present, else `"none"`. |

For a polyglot project, `pyve init` consults the detect hook **advisory-only** — a root-level `package.json` next to a Python project surfaces a "Node project detected" advisory; the composed multi-plugin scaffold (below) owns the `pyve.toml` write. The `frameworks` structured attribute on `[env.<name>]` is surfaced advisory-only in `check` / `status` via `manifest_get_frameworks` — SvelteKit is recognized, not specially provisioned. (Worked rationale: [phase-n-2-spike-env-model-worked-examples.md](.archive/phase-n-2-spike-env-model-worked-examples.md) § "N-3 evidence".)

**Backend-providers — `pnpm` / `npm` / `yarn`.** Three `virtualized` providers registered via `bp_register node <pm> virtualized` (fired eagerly at source-time from [pyve.sh](../../pyve.sh), mirroring Python's venv/micromamba). Per-tool differences live in pure string-maps so the lifecycle hooks consume one place:

| Helper | pnpm | npm | yarn |
|---|---|---|---|
| `node_provider_install` | `pnpm install` | `npm install` | `yarn install` |
| `node_provider_lockfile` | `pnpm-lock.yaml` | `package-lock.json` | `yarn.lock` |
| `node_provider_test` | `pnpm test` | `npm test` | `yarn test` |

`node_provider_detect [declared_backend] [path]`: an explicit `backend = "pnpm"` (or `npm`/`yarn`) wins over any lockfile; otherwise infer from lockfile presence; with no lockfile, default to `pnpm`.

**Runtime-resolution precedence (Story N.v).** Node's version-manager precedence per spike S10 (revised), implemented in [lib/plugins/node/runtime_detect.sh](../../lib/plugins/node/runtime_detect.sh):

```
nvm  >  fnm  >  volta  >  asdf  >  Homebrew / system PATH
```

- `node_runtime_manager()` — the precedence walk; prints the governing manager, or `path` when none is active (the bare-`command -v node` fallback).
- `node_runtime_resolve()` — prints the resolved `node` path (every manager shims `node` onto PATH when active, so `command -v node` is the resolution); fails loudly with "no Node runtime detected; install via Homebrew or your preferred manager" when no node is reachable.
- Each detector (`is_nvm_active` / `is_fnm_active` / `is_volta_active`) has its own `PYVE_NO_{NVM,FNM,VOLTA}_COMPAT` opt-out, mirroring the `is_asdf_active()` contract. The asdf tier uses a Node-specific private `_is_asdf_node_active()` (asdf has a *nodejs* plugin) honoring the shared `PYVE_NO_ASDF_COMPAT` — deliberately **not** the Python-context `is_asdf_active()`, which gates on `VERSION_MANAGER == "asdf"` and would never fire for a Node-only project. These helpers live with the Node plugin, never in the Python/asdf-oriented `lib/env_detect.sh`.

**Lifecycle hooks — init / purge / update.**

| Hook | Behavior |
|---|---|
| `node_pyve_plugin_init <path> [<backend>]` | Detects the provider (`node_provider_detect`), resolves the Node runtime (`node_runtime_resolve`, fails loudly when absent) **before** invoking the package manager, then runs the install in `<path>`. Runs `node_pyve_plugin_validate_env_blocks` first. |
| `node_pyve_plugin_purge <path>` | Smart-purge: removes `node_modules/`, `.svelte-kit/`, `dist/`, `build/`, `.next/` from `<path>` (only those present); never touches `package.json`, lockfiles, or source. `${path:?}`-guarded against an empty-path `rm`. |
| `node_pyve_plugin_update <path> [<backend>]` | CI-aware refresh: `pnpm install --frozen-lockfile` / `npm ci` / `yarn install --frozen-lockfile` when `CI` is set; plain `<pm> install` otherwise. |

Install/purge logic lives in parameterized workers (`_node_provider_run_install`, `_node_purge_at`) so it's testable hermetically apart from manifest wiring. `node_pyve_plugin_validate_env_blocks` checks `purpose ∈ {run,test,utility,temp}` and that a non-empty `backend` is a registered provider; provider-private fields (`languages`, `frameworks`, future `node_version`) pass through untouched.

**Runtime hooks — check / status / run / test.**

| Hook | Behavior |
|---|---|
| `node_pyve_plugin_check <path>` | Verifies Node runtime resolves, `package.json` present, `node_modules/` present + non-empty (these drive the exit code). **TypeScript advisory:** when an env declares `languages` including `typescript` but `package.json` has no `typescript` dep, warn (advisory only — no failure exit). Surfaces the env's `frameworks`. |
| `node_pyve_plugin_status <path> [<backend>]` | Backend/provider, lockfile state, `node_modules` state, `package.json` mtime (portable `_node_mtime`), plus advisories. |
| `node_pyve_plugin_run <path> <cmd> [args...]` | Passthrough: prepends `<path>/node_modules/.bin` to PATH, then runs `<cmd>`. |
| `node_pyve_plugin_test <path> [<backend>]` | Honest delegation to `<provider> test` — the user's `package.json` `test` script defines what "test" means (vitest, jest, playwright, …). |

`manual_steps` and the framework/TypeScript advisories surface through the shared `_node_pyve_plugin_render_advisories`, mirroring the Python plugin's renderer.

**Activation hook — `node_modules/.bin` PATH_add.** `node_pyve_plugin_activate <path>` composes a single sentinel-wrapped `.envrc` section, runs it through `validate_envrc_snippet` (the PC-1 gate), and emits it to stdout (the composer assembles each plugin's section into one `.envrc`):

```
# >>> pyve:plugin:node:activate >>>
PATH_add "node_modules/.bin"            ← root; or "src/frontend/node_modules/.bin" for a visitor
# <<< pyve:plugin:node:activate <<<
```

Unlike the Python plugin (venv→`VIRTUAL_ENV` vs micromamba→`CONDA_PREFIX`), Node activation is **uniform across providers** — just the `node_modules/.bin` PATH_add, no per-provider branch. Uses direnv's `PATH_add` primitive, never a hand-rolled `export PATH=` (the Uniform `.envrc` template rule). A Python root section and a Node visitor section concatenate into one `.envrc` body with no interference.

**`.gitignore` + smart-purge hooks.** Both ship as data interfaces (like the Python plugin's), and both are **path-aware** — a sub-path plugin prefixes each pattern / path token with its `path`, while comment and blank lines are never prefixed.

- `node_pyve_plugin_gitignore_entries [path]` → `node_modules/`, `.svelte-kit/`, `dist/`, `build/`, `.next/`, `*.tsbuildinfo`, `.turbo/`, `.parcel-cache/`, `*-debug.log*`. Flows through `validate_gitignore_snippet` (PC-1) at the composer.
- `node_pyve_plugin_purge_inventory [path]` → `created` set (`node_modules`, `.svelte-kit`, `dist`, `build`, `.next`, `.turbo`, `*.tsbuildinfo`) kept consistent with `_node_purge_at`'s remover; `authored` set (`package.json`, the three lockfiles, `tsconfig.json`, `svelte.config.js`) never touched on purge.

---

### Composition layer

The plugin contract and the two reference plugins prove that a single plugin can own a command and that the contract generalizes. The composition layer is the seam that fans one `pyve <cmd>` across *every* active plugin and composes the results into one coherent artifact or report. Each composer module owns one composed surface, all driven off `plugin_list_active` (the no-Python-noise seam, below):

| Module | Entry points | Composed surface |
|---|---|---|
| [lib/envrc_composer.sh](../../lib/envrc_composer.sh) | `_compose_envrc_body` → `compose_envrc <path>` → `compose_project_envrc <path>` | `.envrc` — each plugin's `pyve_plugin_activate` snippet assembled into one managed section |
| [lib/gitignore_composer.sh](../../lib/gitignore_composer.sh) | `_compose_gitignore_body` → `compose_gitignore <path>` → `compose_project_gitignore <path>` | `.gitignore` — each plugin's `pyve_plugin_gitignore_entries`, deduped, in one managed section |
| [lib/init_composer.sh](../../lib/init_composer.sh) | `compose_init [args]` | `pyve init` — materializes the root plugin's env, then fans secondary-plugin materialization across the rest (handles the Node-only and polyglot scaffolds) |
| [lib/check_composer.sh](../../lib/check_composer.sh) | `compose_check [args]` | `pyve check` — per-plugin `pyve_plugin_check` sections + worst-severity roll-up |
| [lib/status_composer.sh](../../lib/status_composer.sh) | `compose_status [args]` | `pyve status` — per-plugin `pyve_plugin_status` sections (always exit 0) |
| [lib/purge_composer.sh](../../lib/purge_composer.sh) | `compose_purge_inventory` / `compose_purge_removals` / `compose_purge [args]` | `pyve purge` — composed inventory + authored guard + delegated removal |

**CLI wiring** ([pyve.sh](../../pyve.sh) dispatcher): `check` → `compose_check`, `status` → `compose_status`, `purge` → `compose_purge`. The two file composers are reached through the **`compose_project_*` reload entry points**, called from inside the Python plugin's `init` / `update` hooks (and the gitignore self-heal): `compose_project_envrc` / `compose_project_gitignore` reload the manifest + registry first, then iterate *every* active plugin — so even though `pyve init` enters via `plugin_dispatch python init`, the resulting `.envrc` / `.gitignore` carry all plugins' sections. The `_compose_*_body` halves are pure assembly (stdout, no write) for hermetic testing; the `compose_*` halves add the atomic writer.

**Severity ladder (`pyve check`).** Each plugin's check hook returns a code; the composer maps it to a severity ordinal and takes the **worst across all plugins**:

| Hook rc | Severity | Process exit (roll-up) |
|---|---|---|
| `0` | pass (clean) | `0` |
| `2` | warn (advisory — version drift, missing `.env`) | `0` (advisory text, non-failing) |
| `1` / other nonzero | error (env broken for run/test) | `2` (CI fails the build) |

This preserves `check_environment`'s historical 0/1/2 internal codes and the Node plugin's 0/1 convention without rewriting either hook. `pyve status` has **no** ladder — it reports reality and always exits 0 (a broken reading is `check`'s job).

**PC-2 — atomic-write safety** (`compose_envrc` / `compose_gitignore`). Composition writes are crash-safe and non-destructive:

1. Compose the new body to `<path>.tmp`.
2. If composition fails (e.g. a plugin emits an unsafe snippet that trips the PC-1 validator), **leave the existing file untouched** — no half-written `.tmp`, no spurious `.prev`, nonzero exit.
3. Back the current file up to `<path>.prev`.
4. Promote with `mv -f` (atomic rename).

User-authored content round-trips verbatim: `.envrc` preserves everything below the `# <<< pyve:managed:end <<<` marker; `.gitignore` preserves content both above and below its managed envelope. A legacy file with no markers is replaced by the managed section but backed up to `.prev` for recovery. One-step rollback is documented as `mv -f <path>.prev <path>`.

**Managed-section sentinels.** `.envrc`: `# >>> pyve:managed:start >>>` … `# <<< pyve:managed:end <<<`, with each plugin's contribution wrapped in its own `# >>> pyve:plugin:<name>:activate >>>` … `<<<` block. `.gitignore`: `# >>> pyve:managed:gitignore >>>` … `# <<< pyve:managed:gitignore <<<`. All plugin contributions pass through the PC-1 validators ([lib/envrc_safety.sh](../../lib/envrc_safety.sh) — `validate_envrc_snippet` / `validate_gitignore_snippet`) before they reach the file; composer-owned infrastructure lines (macOS `.DS_Store`, the `# Pyve-managed` state block) are appended after validation.

**Path-aware labels.** Visitor plugins (manifest `path != "."`) are path-prefixed for monorepo disambiguation — `[node @ src/frontend]` in `check` / `status` sections, `src/frontend/node_modules/` in `.gitignore`, `src/frontend/node_modules/.bin` in `.envrc`. Root plugins (`path = "."`) get a bare label.

**PC-4 invariants.**

- **PC-4a — no-Python noise gate.** All composers dispatch only plugins in `plugin_list_active`, and the Python plugin's check/status hooks short-circuit to a silent no-op when `python_plugin_is_active_in_project` ([lib/plugins/python/plugin.sh](../../lib/plugins/python/plugin.sh)) returns inactive. Pyve defaults to Python (a bare directory keeps the "run `pyve init`" nudge), so the gate suppresses the Python section **only** when there is no Python signal anywhere *and* a competing non-Python stack (e.g. `package.json`) is present — so a Node-only project produces zero Python output, while a polyglot or project-guide-bearing project keeps it.
- **PC-4b — per-plugin latency budget.** Each plugin's `activate` stays within **≤ 50ms p95** — the composed `.envrc` re-evaluates on every shell / direnv reload, so a slow plugin degrades every prompt. The `compose_envrc` body emits optional `# pyve:bench:<plugin>:activate_ms=` lines under `PYVE_LATENCY_BENCH=1` (helpers `_pyve_bench_mark` / `_pyve_bench_now_ms`); the budget is enforced for all three matrix fixtures in [tests/perf/test_plugin_activation_latency.bats](../../tests/perf/test_plugin_activation_latency.bats).

**`pyve purge` composition (Option B).** `compose_purge` owns the inventory, the authored guard, and the grouped confirmation; the per-plugin `pyve_plugin_purge` hooks remain the authoritative removers so their smart-purge nuance (`.env`-if-empty, `.gitignore`-section-only, `--keep-testenv` surgery) survives. `compose_purge_inventory` aggregates each plugin's `created` / `authored` declarations keyed by `(plugin, path)`; `compose_purge_removals` is the created set minus authored-guard matches (a path declared `authored` by *any* plugin — even cross-plugin, even via glob — is never removed). Removal is delete-only and convergent, so the composer dispatches **all** plugins even if one fails, reports the failures, notes that re-running `pyve purge` is safe, and exits nonzero.

**Matrix verification.** The full composition layer is swept against all three project shapes (pure-Python, Node-only, polyglot) in [tests/unit/test_n_am_polyglot_matrix.bats](../../tests/unit/test_n_am_polyglot_matrix.bats) — composed `check`/`status`/`purge` + composed `.envrc`/`.gitignore` + PC-2 + PC-4a, with PC-4b owned by the perf suite.

---

## Configuration

### `pyve.toml` — the canonical declaration

From v3.0, every project's declaration lives in a root-level `pyve.toml` (`pyve_schema`, `[project]`, `[env.<name>]`, `[plugins.<name>]`), read through [`lib/manifest.sh`](#libmanifestsh--v30-canonical-manifest-reader). It supersedes both the v2 `.pyve/config` (YAML main-env declaration) and `[tool.pyve.testenvs.*]` (pyproject.toml). The full schema, field semantics, validation rules, and accessor surface are documented under `lib/manifest.sh` above; the env-spec vocabulary is owned by the [env-spec contract](project-guide-requests/wizard-env-contract.md). **Everything under `.pyve/` is materialized state** (envs, locks, sentinels, the `.v2-legacy/` backup tree) — never configuration.

During the v3.0 deprecation window, a project that still has only v2 sources (`.pyve/config` / `[tool.pyve.testenvs.*]`) and no `pyve.toml` keeps working via the read-compat synthesis layer (above); `pyve self migrate` writes a fresh `pyve.toml` from those sources.

### Precedence

1. CLI flags
2. `pyve.toml` (`[env.<name>]` / `[plugins.<name>]`)
3. Project files (`environment.yml`, `pyproject.toml`, `package.json`, etc.)
4. Hardcoded defaults in `pyve.sh` (`DEFAULT_PYTHON_VERSION`, `DEFAULT_VENV_DIR`, …)

---

## CLI Design

Pyve uses a subcommand-style CLI consistent with modern developer tooling (`git`, `cargo`, `kubectl`, `gh`): every verb has one canonical subcommand form, and legacy flag forms hard-error via `legacy_flag_error` (a precise migration hint). Universal flags (`--help`, `--version`, `--config`) remain as flags per CLI convention.

### Commands (v3.0 surface)

| Command | Description |
|---------|-------------|
| `pyve init [dir]` | Initialize the project's environment(s) — interactive wizard; composed across active plugins |
| `pyve purge [dir]` | Remove Pyve-managed environment artifacts, composed across active plugins |
| `pyve lock [--check] [--env <name>] [--all]` | Generate/update `conda-lock.yml` for the current platform (micromamba-backed envs) |
| `pyve run <cmd> [args]` | Execute a command in the project environment |
| `pyve test [--env <name>[,…]] [args]` | Run tests in a `test`-purpose environment (matrix via comma-separated `--env`) |
| `pyve env init [<name>]` | Create a named environment |
| `pyve env install [<name>] [-r <file>]` | Install dependencies into a named environment |
| `pyve env purge [<name>]` | Remove a named environment |
| `pyve env run [<name> --] <cmd>` | Execute a command in a named environment |
| `pyve env list` / `pyve env prune` | List named environments / prune orphaned or unused ones |
| `pyve package` | Reserved artifact-materialization verb — prints a clean advisory until a packaging provider ships |
| `pyve check` | Diagnose problems, composed across active plugins (CI-safe 0/1/2 exit codes) |
| `pyve status` | Read-only project-state dashboard, composed across active plugins (always exit 0) |
| `pyve update` | Non-destructive upgrade: refresh config + managed files + project-guide; never rebuilds an env |
| `pyve python set <ver>` / `pyve python show` | Pin / print the project Python version + its source |
| `pyve self install` / `uninstall` | Install / remove pyve (provisions / removes the toolchain venv) |
| `pyve self provision` / `unprovision` | Provision / remove Pyve-managed global tooling (e.g. hosted project-guide) |
| `pyve self migrate` | Write `pyve.toml` from v2 sources, back legacy files into `.pyve/.v2-legacy/`, rebuild envs |
| `pyve self` | Show `self` namespace help (no subcommand → namespace help only) |

`pyve testenv <sub>` is the **deprecated v2 spelling** of `pyve env <sub>`; it re-dispatches to `env_command` with a one-shot deprecation warning (removal scheduled for v4.0).

**Check vs. status — invariant.** `check` and `status` are intentionally disjoint: `check` surfaces problems with severity-bearing exit codes (0/1/2) and emits one actionable remediation per failure; `status` is a read-only snapshot with always-zero exit (unless pyve itself errors). Each command's `--help` text mirrors this invariant verbatim — the help output is the user-facing contract. If a diagnostic would surface "something looks wrong", it belongs in `check`; if the answer is "what is this project?", it belongs in `status`. See [phase-h-check-status-design.md §2](.archive/phase-h-check-status-design.md) for the canonical statement.

**Removed subcommands.** `pyve doctor` and `pyve validate` hard-error with a migration hint pointing at `pyve check`; the legacy `pyve testenv --init|--install|--purge` and `pyve python-version <ver>` flag forms fall through to the standard unknown-flag / unknown-command paths.

### Universal Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--help` | `-h` | Show help |
| `--version` | `-v` | Show version |
| `--config` | `-c` | Show configuration |

### Per-Subcommand Help

Every renamed subcommand responds to `--help` / `-h` with a focused, man-page-style help block:

```
pyve init --help
pyve purge --help
pyve check --help
pyve status --help
pyve update --help
pyve python --help
pyve python set --help
pyve self --help
pyve self install --help
pyve self uninstall --help
pyve testenv --help
pyve lock --help
```

The `--help` intercept fires **before** the real handler runs, so help is always fast and side-effect-free. `pyve --help` is reorganized into four categories: *Environment*, *Execution*, *Diagnostics*, *Self management*. Legacy `pyve doctor --help` / `pyve validate --help` error out like any other attempt to invoke the removed commands.

### `self` Namespace

The `self` subcommand namespace (Decision D4) groups commands that manage Pyve's own installation, mirroring `git remote` / `kubectl config`:

- `pyve self install` — copy script + lib to `~/.local/bin`, create symlink, add to PATH, create `~/.local/.env` template. Idempotent.
- `pyve self uninstall` — remove script, symlink, lib/, PATH entry. Preserve `~/.local/.env` if non-empty.
- `pyve self` (no subcommand) — print the namespace help only. Does **not** fall through to top-level help.

### Modifier Flags

All modifier flags keep their names from pre-v1.11.0 and attach to their renamed subcommands.

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--backend <type>` | `pyve init` | Force backend selection |
| `--env-name <name>` | `pyve init` | Micromamba environment name |
| `--local-env` | `pyve init` | Copy `~/.local/.env` template |
| `--no-direnv` | `pyve init` | Skip `.envrc` creation |
| `--force` | `pyve init` | Purge and re-initialize |
| `--auto-bootstrap` | `pyve init` | Auto-install micromamba |
| `--bootstrap-to <loc>` | `pyve init` | Bootstrap location (project/user) |
| `--strict` | `pyve init` | Bark on a declared-but-missing/stale lock; also opts out of scaffolding/inference |
| `--no-lock` | `pyve init` | Don't use a lock this run (resolve from `environment.yml`, ignore any present lock without deleting it); skip the requirement (beats `--strict`); omit `conda-lock` from a fresh scaffold |
| `--allow-synced-dir` | `pyve init` | Bypass cloud-synced directory check |
| `--keep-testenv` | `pyve purge` | Preserve dev/test environment |
| `--project-guide` | `pyve init` | Force project-guide hook (overrides auto-skip) |
| `--no-project-guide` | `pyve init` | Skip the project-guide hook |
| `--project-guide-completion` | `pyve init` | Force shell completion wiring |
| `--no-project-guide-completion` | `pyve init` | Skip shell completion wiring |

### Interactive `pyve init` wizard

When `pyve init` is invoked, an interactive wizard walks the user through three prompts: **backend → Python version pin → project-guide install**. Strong repo signals make the happy path highlight the strongest choice so the user can press enter through those choices. Any explicit flag (e.g., `--backend`, `--python-version`, `--project-guide`) on the same invocation skips its corresponding prompt, displaying the flag's value in the wizard flow, and wins over detection-based defaults; flag-driven invocations therefore remain fully non-interactive (for that parameter).

#### Flag inventory and wizard mapping

`pyve init` accepts fifteen flags plus an optional `<dir>` positional. Three become interactive prompts; twelve stay flag-only (advanced / CI-shaped / sub-decisions of a primary prompt).

| Flag | Wizard treatment |
|------|-----------------|
| `--backend <type>` | **Prompt** — backend selection |
| `--python-version <ver>` | **Prompt** — Python version pin (venv backend only) |
| `--project-guide` / `--no-project-guide` | **Prompt** — project-guide install |
| `--project-guide-completion` / `--no-project-guide-completion` | Flag-only (sub-decision; consulted only when project-guide is being installed) |
| `--env-name <name>` | Flag-only (advanced; defaults from project name) |
| `--local-env` | Flag-only (advanced) |
| `--no-direnv` | Flag-only (CI-shaped) |
| `--auto-bootstrap` | Flag-only (sub-decision of micromamba backend) |
| `--bootstrap-to <loc>` | Flag-only (sub-decision of `--auto-bootstrap`) |
| `--strict` | Flag-only (CI-shaped) |
| `--no-lock` | Flag-only (CI-shaped) |
| `--allow-synced-dir` | Flag-only (escape hatch) |
| `--force` | Flag-only — bypasses the destructive-safeguard on an existing virtual environment **only**; does **not** skip prompts. `pyve init --force` with no other flags still walks the wizard. |

#### Prompt 1 — backend

Default-resolution rules (first match wins):

1. `environment.yml` exists in the target dir → default `micromamba`.
2. `.python-version` or `.tool-versions` exists in the target dir → default `venv`.
3. Otherwise → default `venv`.

Prompt presents both options regardless of detection; the user can override the suggested default. When `--backend <type>` is supplied, the prompt renders non-interactively — the wizard flow shows a single line with the flag-resolved value (so the user sees what's locked in) and moves to the next prompt without reading stdin.

#### Prompt 2 — Python version pin (backend-aware)

The pin's mechanics differ between backends — venv pins via asdf/pyenv writing `.tool-versions` / `.python-version`; micromamba pins via the `python=X` line in `environment.yml`. Prompt 2 reflects this split.

**venv branch.** Up to three layers:

1. **Version-manager picker.** Present `[asdf, pyenv]` with **asdf as default**. Skipped when only one of the two is installed (auto-pick that one). Hard-fail when neither is installed: error names both managers as the supported set and points the user at their respective install docs. This wizard prompt overrides the existing implicit precedence in `detect_version_manager()` — when both are installed and the user explicitly picks `pyenv`, the wizard records `pyenv` even though the implicit ranking would have chosen `asdf`.
2. **Pick from installed.** List manager-reported installed Python versions filtered to `^3\.`. Source: `asdf list python` (strip leading `*` and whitespace) or `pyenv versions --bare`. Final list option is `more...`.
3. **`more...` secondary prompt.** Re-prompt with the full available version list filtered to `^3\.`. Source: `asdf list all python` or `pyenv install --list`. (Filtering to `^3\.` keeps oddities like `2.1.3`, `activepython-2.7.14`, and `stackless-3.7.5` out of the menu while still surfacing every released `3.x.y`.)

The venv branch also offers a **skip** option that preserves current no-pin behavior (no `.tool-versions` / `.python-version` written; system Python resolves at activation time). On selection, the wizard writes the appropriate pin file: `.tool-versions` for asdf, `.python-version` for pyenv. When `--python-version <ver>` is supplied, all three interactive layers and the picker are bypassed; the wizard flow shows a single line with the flag-resolved version (and the manager it pins via — asdf when both are installed, else whichever is installed).

**micromamba branch.** No manager picker — micromamba doesn't use asdf/pyenv to pin; it uses the `- python=<version>` line in `environment.yml` and conda-forge supplies any 3.x version. Three sub-cases:

1. **`environment.yml` already exists** → skip entirely; render `Python: managed via environment.yml`. The existing pin in env.yml owns it; the wizard does not edit env.yml mid-flow.
2. **`environment.yml` absent + `--python-version <ver>` supplied** → render `Python: <ver> (--python-version, will be written to environment.yml)`. The existing `scaffold_starter_environment_yml` ([lib/micromamba_env.sh:422](../../lib/micromamba_env.sh#L422)) writes the pin into the scaffolded env.yml later in the init flow; the wizard just makes the choice visible.
3. **`environment.yml` absent + no flag** → render `Python: <DEFAULT_PYTHON_VERSION> (default, will be written to environment.yml)`. `DEFAULT_PYTHON_VERSION` (defined in `pyve.sh`) is the wizard's effective choice; future polish may add an interactive "type a version" sub-prompt for this case, but the explicit override path (`--python-version`) is fully supported today and is sufficient for L.k.4.

The micromamba branch never invokes asdf/pyenv. The wizard's no-managers hard-fail (venv branch) does not apply to micromamba.

#### Prompt 3 — project-guide install

Default-resolution rules:

1. **Already present** — if `.project-guide.yml` exists in the target dir, **skip the prompt entirely** and run `project-guide update` via the existing `run_project_guide_update_in_env` wrapper. The safe refresh path: never replaces, never destroys local edits. `.project-guide.yml` is the canonical "project-guide is installed here" marker — it records `installed_version`, `target_dir`, `current_mode`, etc.; `pyve update` already uses this single signal (lib/commands/update.sh:123) and L.k.5 aligns with that.
2. **Not present** — prompt with default `no`. On `yes`, route through the existing `install_project_guide` + embedded-init path.

When `--project-guide` or `--no-project-guide` is supplied, the prompt renders non-interactively — the wizard flow shows a single line with the flag-resolved decision (and, for the install case, whether detection found an existing install that will be refreshed vs. a fresh install). `--project-guide` always installs/updates regardless of detection; `--no-project-guide` always skips. The shell-completion sub-decision (`--project-guide-completion` / `--no-project-guide-completion`) is consulted only inside the install path and is not surfaced as a wizard prompt — its existing env-var / interactive-fallback logic in `_init_run_project_guide_hooks` handles it.

#### TTY policy

The wizard always runs on `pyve init`; flags suppress the *interactive* part of individual prompts but never the wizard itself. When at least one prompt would read from stdin (i.e. at least one of the three prompt-bearing parameters is not flag-supplied) **and** stdin is not a TTY, `pyve init` exits non-zero before printing the welcome banner. Error message names the specific flags that would short-circuit each missing prompt (`--backend`, `--python-version`, `--project-guide` / `--no-project-guide`). `lib/ui/select.sh`'s per-prompt numbered-stdin fallback is intentionally not used here — a multi-prompt wizard driven by piped numeric input is too brittle for CI use, and supplying the relevant flags is exactly the supported non-interactive path.

When all three prompt-bearing parameters are flag-supplied, the wizard still runs and renders all three values non-interactively; no stdin read occurs, so the TTY check is moot.

**Bypass env var.** `PYVE_INIT_NONINTERACTIVE=1` bypasses the TTY guard regardless of flag state. This exists for the bats test harness (which invokes `pyve init` with various flag subsets pre-dating the wizard, all from non-TTY stdin) and for advanced users who want to invoke the wizard from a non-TTY context with explicit awareness that any prompt that needs to read stdin will likely fail anyway. `setup_pyve_env()` in `tests/helpers/test_helper.bash` exports this var by default; new wizard tests unset it locally.

#### Welcome banner

Rendered with `header_box` from `lib/ui/core.sh`. Tone-matched to <https://pointmatic.github.io/pyve>. Always printed at the start of the wizard flow — even when all three prompts render non-interactively from flags — because the wizard always runs.

#### Out of scope for the wizard

Testenv creation prompt, `--bootstrap-to`, `--auto-bootstrap`, `--force`, `--env-name`, `--local-env`, `--no-direnv`, `--strict`, `--no-lock`, `--allow-synced-dir` — all stay flag-only. Future revisits may surface a subset of these (e.g. micromamba-bootstrap auto-prompt when micromamba is selected and not installed), but each is its own decision and is not bundled into Phase L's wizard rollout.

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (missing dependency, invalid input, operation failure) |
| 2 | Warnings only (validation) |
| 127 | Command not found (`pyve run`) |

---

## Cross-Cutting Concerns

### project-guide rc-file Sentinel

The `pyve init --project-guide-completion` hook inserts a sentinel-bracketed eval block into the user's `~/.zshrc` or `~/.bashrc`:

```bash
# >>> project-guide completion (added by pyve) >>>
command -v project-guide >/dev/null 2>&1 && \
  eval "$(_PROJECT_GUIDE_COMPLETE=zsh_source project-guide)"
# <<< project-guide completion <<<
```

The opening sentinel comment (`# >>> project-guide completion (added by pyve) >>>`) is the source of truth for idempotent insertion and removal:

- **Insertion** (`add_project_guide_completion` in `lib/utils.sh`): no-op if the sentinel is already present. Builds the eval block via an unquoted heredoc (a doubled `\\` followed by a real newline produces a proper shell line continuation in the output — see Story G.e for the v1.12.0 bug where a literal `\n` was emitted instead). Delegates the actual rc-file insertion to `insert_text_before_sdkman_marker_or_append`. Creates the rc file if missing.
- **SDKMan-aware insertion** (`insert_text_before_sdkman_marker_or_append` in `lib/utils.sh`, v1.13.1+, Story G.e): if the SDKMan end-of-file marker `#THIS MUST BE AT THE END OF THE FILE FOR SDKMAN TO WORK!!!` is present in the rc file, the new block is inserted *immediately above* it via awk so SDKMan retains its required last-position. Otherwise the block is appended to the end. Always emits a leading blank line before the inserted block (unless the file is empty in the SDKMan-absent case), which gives `remove_project_guide_completion` a stable preceding-blank to consume and guarantees byte-identical add → remove round-trips. The same helper is used by `install_prompt_hook` (currently in `pyve.sh`; moves alongside `init`/project-guide integration during the command-module extraction phase) so the prompt hook and the completion block share one SDKMan-aware code path.
- **Removal** (`remove_project_guide_completion` in `lib/utils.sh`): removes only the sentinel-bracketed block plus one immediately-preceding blank line (so add → remove round-trips cleanly). Awk-based, BSD/GNU compatible.
- **Detection** (`is_project_guide_completion_present` in `lib/utils.sh`): a single `grep -qF` against the opening sentinel.

The sentinels must not change without a migration plan. Users who installed the block with an older sentinel would end up with orphaned blocks on uninstall.

`pyve self uninstall` calls `remove_project_guide_completion()` for both `~/.zshrc` and `~/.bashrc` to cover users who switched shells after installing the block.

### project-guide Helper Functions

The following helpers in `lib/utils.sh` implement the three-step project-guide hook (FR-16):

| Function | Purpose |
|---|---|
| `prompt_install_project_guide` | Y/n prompt with default Y; honors `PYVE_PROJECT_GUIDE` / `PYVE_NO_PROJECT_GUIDE` / `CI` / `PYVE_FORCE_YES`. CI default = install. |
| `prompt_install_project_guide_completion` | Y/n prompt with default Y; honors `PYVE_PROJECT_GUIDE_COMPLETION` / `PYVE_NO_PROJECT_GUIDE_COMPLETION`. **CI default = SKIP** (deliberate asymmetry — editing rc files in CI is surprising). |
| `is_project_guide_installed(backend, env_path)` | Probes `<env_python> -c 'import project_guide'`. ~50ms. Returns 0 if importable. |
| `install_project_guide(backend, env_path)` | Step 1: runs `pip install --upgrade project-guide` against the project env. Always uses `--upgrade`. Failure-non-fatal. |
| `run_project_guide_init_in_env(backend, env_path)` | Step 2 (first-time): runs `<env>/bin/project-guide init --no-input`. Invoked by the orchestrator when `.project-guide.yml` is absent. Requires project-guide >= 2.2.3. Failure-non-fatal. |
| `run_project_guide_update_in_env(backend, env_path)` | Step 2 (reinit, v1.14.0+): runs `<env>/bin/project-guide update --no-input`. Invoked by the orchestrator when `.project-guide.yml` is present. Content-aware: hash-compares, skips matches, creates `.bak.<timestamp>` siblings for modified managed files, preserves `.project-guide.yml` state. Requires project-guide >= 2.4.0. Failure-non-fatal (including a future `SchemaVersionError`). |
| `project_guide_in_project_deps()` | Auto-skip safety: returns 0 if `project-guide` is declared in `pyproject.toml`, `requirements.txt`, or `environment.yml`. Word-boundary regex to avoid false matches with similar names like `project-guide-extras`. |
| `detect_user_shell()` | Reads `$SHELL`, prints `zsh` / `bash` / `unknown`. |
| `get_shell_rc_path(shell)` | Maps `zsh` → `$HOME/.zshrc`, `bash` → `$HOME/.bashrc`, anything else → empty string. |
| `is_project_guide_completion_present(rc_path)` | Detects the sentinel block. |
| `add_project_guide_completion(rc_path, shell)` | Step 3: builds the sentinel-bracketed block via heredoc and delegates insertion to `insert_text_before_sdkman_marker_or_append`. Idempotent. Creates rc file if missing. |
| `remove_project_guide_completion(rc_path)` | Removes the sentinel block. Safe no-op if absent. |
| `insert_text_before_sdkman_marker_or_append(rc_path, content)` | (v1.13.1+, Story G.e) Shared SDKMan-aware rc-file insertion. If `#THIS MUST BE AT THE END OF THE FILE FOR SDKMAN TO WORK!!!` is present, inserts `content` immediately above it; otherwise appends. Always emits a leading blank line for round-trip symmetry with `remove_project_guide_completion`. Used by both `add_project_guide_completion` and `install_prompt_hook` (the latter currently in `pyve.sh`; moves with the `init` extraction). |

The orchestrator `run_project_guide_hooks(backend, env_path, pg_mode, comp_mode)` (currently in `pyve.sh`; moves to `lib/commands/init.sh` as a private `_init_run_project_guide_hooks` during the extraction phase, since `init()` is its only caller) calls these in priority order. Tri-state mode arguments (`""` / `"yes"` / `"no"`) come from CLI flag parsing in `init()`. The auto-skip safety mechanism fires between explicit flag overrides and the prompt/CI default path.

For step 2, the orchestrator branches on `.project-guide.yml` presence (v1.14.0+, Story G.h): when present, it calls `run_project_guide_update_in_env` (reinit refresh); when absent, it calls `run_project_guide_init_in_env` (first-time scaffold). Pyve never auto-runs `project-guide init --force` — that is destructive (wipes config state, no backups) and must remain user-initiated.

### Legacy-Flag Error Catch (kept indefinitely)

When a user invokes a removed legacy flag or subcommand form, the dispatcher in `main()` catches it and prints a precise migration error, then exits non-zero:

```
ERROR: 'pyve --init' is no longer supported. Use 'pyve init' instead.
ERROR: See: pyve --help
```

**Catches as of v2.0:**

| Tier | Added | Catches | Target |
|---|---|---|---|
| Flag forms | v1.11.0 (G.b.1) | `--init`, `--purge`, `--validate`, `--python-version`, `--install`, `--uninstall` | `init`, `purge`, `check`, `python set <ver>`, `self install`, `self uninstall` |
| Short aliases | v1.11.0 (D1) | `-i`, `-p` | `init`, `purge` |
| Subcommand forms | v2.0 (H.e.8a) | `doctor`, `validate` | `check` |
| v2.0 flag forms | v2.0 (H.e.9) | `--update`, `--doctor`, `--status` | `update`, `check`, `status` |
| `init --update` | v2.0 (H.e.9) | `init --update` | `update` (the separate subcommand) |

**Why kept forever:** Three lines of code per catch, great error message, zero cost. Users coming from old README snippets, blog posts, third-party tutorials, and LLM training data will hit them for years and get a precise hint instead of an opaque "unknown command" error. Implemented via `legacy_flag_error()` helper in `pyve.sh`, called from the top-level dispatcher `case` block before any subcommand dispatch runs.

**Unknown-flag closest-match (H.e.9d).** Distinct from the legacy-flag catches: when a user typos a flag *within* a valid subcommand (`pyve init --forse`), `unknown_flag_error()` in `pyve.sh` suggests the closest valid flag via `_edit_distance()` in `lib/ui.sh`. Suggestion fires only when edit distance ≤ 3; beyond that the error lists the valid-flag set without a "did you mean" line to avoid unrelated hints.

**No compat shim, no silent translation.** The legacy-flag catch list is always an immediate error — silent translation would hide the rename from users and build long-term tech debt. (The Category A delegate-with-warning paths — `testenv --init|--install|--purge`, `python-version <ver>` — shipped in Phase H were removed in Story J.d / v2.3.0.)

### Uniform `.envrc` template

Every backend emits the same four-line shape via `write_envrc_template` in [lib/utils.sh](../../lib/utils.sh). `init_direnv_venv` and `init_direnv_micromamba` in [pyve.sh](../../pyve.sh) are thin wrappers that just fill in backend-specific arguments.

```bash
PATH_add "<rel_bin_dir>"                      # direnv stdlib: resolves relative → absolute
export <BACKEND_SENTINEL>="$PWD/<rel_env_root>"  # VIRTUAL_ENV (venv) or CONDA_PREFIX (conda-like)
export PYVE_BACKEND="<backend_name>"
export PYVE_ENV_NAME="<env_name>"
export PYVE_PROMPT_PREFIX="(<backend_name>:<env_name>) "
```

**Key properties.**

- **`PATH_add` is the only path-mutating primitive.** Hand-rolled `export PATH="$ENV_PATH/bin:$PATH"` is forbidden — relative entries stay relative in PATH, which resolves against the caller's cwd and silently breaks rc-file completion guards like `command -v project-guide` when the shell starts outside the project directory (the v2.3.2 bug).
- **Project-directory independence.** Relative paths are written literally in the file; `$PWD` in the sentinel export expands when direnv sources the `.envrc`, yielding the correct absolute path regardless of what the outer shell's cwd was at startup.
- **Backend-native sentinel** (`VIRTUAL_ENV` for venv/pip-derived backends, `CONDA_PREFIX` for micromamba/conda-like backends) is set explicitly instead of by `source`-ing an activate script. Tools that probe these env vars (pip, poetry, IDEs) continue to work.
- **Future backends** (uv, poetry) plug in by filling in `<rel_bin_dir> <sentinel_var> <rel_env_root> <backend_name> <env_name>` — no new activation machinery needed.
- Applies only to the direnv path. `--no-direnv` generates no `.envrc` and is unaffected.

### asdf/direnv Coexistence

Implements FR-18. When pyve is run under asdf-managed Python, asdf's Python plugin reshims on `direnv allow`, so venv-installed CLIs resolve through `~/.asdf/shims/` instead of `.venv/bin/`. See [phase-j-pyve-asdf-reshim-bug-brief.md](.archive/phase-j-pyve-asdf-reshim-bug-brief.md) for the original repro and root-cause analysis. The fix sets `ASDF_PYTHON_PLUGIN_DISABLE_RESHIM=1` at two layers:

- **`.envrc` block** (emitted by `write_envrc_template` in [lib/utils.sh](../../lib/utils.sh), invoked from `init_direnv_venv` / `init_direnv_micromamba` in [pyve.sh](../../pyve.sh)): appends a three-line heredoc — sentinel comment `# Prevent asdf Python plugin from reshimming venv-installed CLIs.`, an override note referring to `PYVE_NO_ASDF_COMPAT=1`, and `export ASDF_PYTHON_PLUGIN_DISABLE_RESHIM=1`. Guarded by `is_asdf_active && ! grep -qF <sentinel> "$envrc_file"` so (a) the block only fires when asdf is the active version manager and the user hasn't opted out, and (b) re-appending is impossible. Also fires on pre-existing `.envrc` files from pyve < v2.3.0, so the guard migrates onto legacy installs without `pyve init --force`.
- **`pyve run` wrapper** (`run_command` in [pyve.sh](../../pyve.sh)): probes the version manager silently (`source_shell_profiles >/dev/null 2>&1 || true; detect_version_manager >/dev/null 2>&1 || true`), then `export`s `ASDF_PYTHON_PLUGIN_DISABLE_RESHIM=1` once before the three backend-specific exec sites (venv-bin, venv-PATH-fallback, micromamba). Silent defense-in-depth — no info line per invocation.

**Helper.** `is_asdf_active()` in [lib/env_detect.sh](../../lib/env_detect.sh) is the single source of truth. Returns 0 iff `$VERSION_MANAGER == "asdf"` AND `PYVE_NO_ASDF_COMPAT` is unset/empty. Both call sites (`.envrc` generator + `pyve run`) use the same helper so the opt-out is consistent.

**Opt-out rationale.** `PYVE_NO_ASDF_COMPAT=1` exists for users who run pyve under asdf but install CLIs globally via `pip install --user`; those CLIs legitimately need asdf's default reshim. The env-var form is intentional — a CLI flag would commit to a permanent surface for a narrow defense-in-depth feature. `PYVE_ASDF_COMPAT=1` is reserved for symmetry but has no distinct behavior (the default state when asdf is detected).

### Platform Portability

- **macOS vs Linux `sed`**: All `sed` operations use portable shell loops with temp files instead of `sed -i` (which has incompatible syntax between BSD and GNU). See v1.1.2/v1.1.3 for history.
- **Shell profiles**: `source_shell_profiles()` initializes asdf/pyenv directly rather than sourcing full shell profiles (which may contain interactive elements).
- **`.DS_Store`**: Auto-added to `.gitignore` template for macOS.

### Atomic File Operations

- `.gitignore` writes use `mktemp` + `mv` to avoid partial writes.
- Config file updates use temp files with atomic `mv`.

### Idempotency

- `write_gitignore_template()` rebuilds the template section from scratch on every call, deduplicating against existing content.
- `insert_pattern_in_gitignore_section()` checks `gitignore_has_pattern()` before inserting.
- `--init` detects existing installations and offers update/force paths.

### Security

- `.env` files: `chmod 600` on creation.
- `.env` always added to `.gitignore`.
- Non-empty `.env` preserved during purge/uninstall.

### Logging

All user-facing output uses the `log_*` functions from `utils.sh`:
- `log_success` → `✓` prefix
- `log_warning` → `WARNING:` to stderr
- `log_error` → `ERROR:` to stderr
- `log_info` → `INFO:` to stdout

Deprecated at v2.0 in favor of `lib/ui.sh` helpers (see below). Removal scheduled for a future major release.

### UI Helper Policy

Once `lib/ui.sh` lands (H.e first sub-story), every user-facing output line in pyve commands **must** go through a `lib/ui.sh` helper. Raw `echo` / `printf` for user-facing text is a policy violation.

**Exceptions — do not route through `lib/ui.sh`:**

- Internal debug logs gated by `PYVE_DEBUG=1`.
- Test-fixture helpers in `tests/helpers/`.
- Pass-through of subprocess stdout/stderr (`pip install`, `micromamba create`, etc.). That stream is not pyve's own voice, so it keeps its upstream formatting. Policy locked in H.f.4: full pass-through, not `--quiet`; `run_cmd`'s dimmed `$ cmd` echo is the only pyve-owned line around a subprocess invocation.
- Subcommands emitting structured output intended for shell parsing (e.g. a future `pyve status --format json`) — these emit on stdout without UI chrome.
- Read-only `show` commands (`pyve python show`) — no `header_box` / `footer_box` wrapper; match `git status` / `gitbetter status` convention of quiet machine-friendly output.

**Why this matters.** Visual consistency is the user-facing contract H.e and H.f establish. A single `echo "WARNING: foo"` slipped into a new command regresses the contract silently. Visual-regression captures in H.f encode the expected output for each command; CI can be extended to enforce this if drift becomes a real problem.

**Backport discipline.** When modifying `lib/ui.sh`, preserve the "no pyve identifiers" invariant. If a helper needs something pyve-specific (e.g. a path into `.pyve/`), that logic goes in the calling command, not in the helper. Any signature or palette change requires a coordinated update to `gitbetter`'s copy of the module.

### Command Module Extraction Pattern

When extracting a top-level command from `pyve.sh` into `lib/commands/<name>.sh`, every extraction story follows the same five-step pattern. This is the contract for keeping `pyve.sh`'s decomposition safe.

1. **Inventory functionality.** List the command's responsibilities (what it does), the cross-command helpers it calls (which `lib/*.sh` functions), and any process-wide state it touches (env vars, globals, files in `.pyve/`).
2. **Audit existing test coverage.** Enumerate every integration test (pytest) and unit test (bats) that exercises the command. Note which behaviors from step 1 are *not* covered.
3. **Backfill characterization tests** against the current (pre-refactor) `pyve.sh`. These should pass immediately — they pin existing behavior, not aspirational behavior. If a backfill test is unexpectedly red, you have found a latent bug; carve it off into its own fix story before continuing the extraction.
4. **Extract** the command function (and any command-private helpers) to `lib/commands/<name>.sh`. Update the dispatcher in `pyve.sh` to source the new file and route to the extracted function. No behavior change.
5. **Re-run the full test suite.** Must be green with zero diff in observable behavior. Any user-visible change is a regression and blocks the story.

**Why this pattern matters.** The refactor's only safety net is test coverage of pre-refactor behavior. Coverage gaps discovered *after* the move can no longer distinguish "this never worked" from "the move broke it." Steps 2–3 close the gap before step 4 disturbs anything.

**Per-extraction-story structure.** Each story in the extraction phase carries the same task-list scaffolding: an inventory section, a coverage-audit table, a backfill-tests subtask, the extraction subtask, and a green-suite verification subtask. Boilerplate, but the discipline is the point.

---

## Testing Strategy

### Unit Tests (Bats)

White-box tests that source individual `lib/*.sh` (and `lib/plugins/**`) modules and exercise functions directly. The suite (130+ files under `tests/unit/`) groups into families:

- **Per-module** — `test_utils.bats`, `test_backend_detect.bats`, `test_env_detect.bats`, `test_micromamba_*.bats`, `test_version.bats`, `test_manifest.bats`, `test_env_*.bats`.
- **Plugin contract & registries** — `test_backend_registry.bats`, the plugin-registry / contract tests, the Python- and Node-plugin hook tests.
- **Composers** — `test_*_composer.bats` (envrc / gitignore / check / status / purge) plus the `test_composed_init_*` and `test_n_am_polyglot_matrix.bats` matrix sweeps.
- **`env` namespace & purpose model** — `test_env_dispatcher.bats`, `test_env_purpose_gate.bats`, `test_env_vocabulary*.bats`, `test_env_sync*.bats`.
- **Regression sentinels** — `test_bash32_compat.bats` (fails on any bash-4+ construct across `pyve.sh` + `lib/`), `test_distutils_shim_retired.bats`, `test_doctor_validate_removed.bats`, the PC-1 envrc-safety corpus, and the SIGPIPE / empty-array regressions.

### Integration Tests (pytest)

Black-box tests under `tests/integration/` that invoke `pyve.sh` as a subprocess and verify outcomes.

| Test File | Workflow Tested |
|-----------|-----------------|
| `test_venv_workflow.py` | Full venv lifecycle (init, run, purge, .gitignore) |
| `test_micromamba_workflow.py` | Full micromamba lifecycle |
| `test_auto_detection.py` / `test_node_detection.py` | Backend / Node auto-detection from project files |
| `test_init_wizard.py` / `test_init_next_steps.py` | Interactive `pyve init` wizard + post-init guidance |
| `test_envrc_composition.py` / `test_envrc_template.py` | Composed `.envrc` output across plugins |
| `test_force_ambiguous_prompt.py` / `test_force_backend_detection.py` | Backend prompt + detection during `--force` re-init |
| `test_lock_command.py` | `pyve lock` (backend guard, prerequisite, platform detection, output filtering) |
| `test_run_command.py` | `pyve run` for both backends |
| `test_testenv.py` | Named environments (the `env` namespace via its legacy `testenv` spelling) |
| `test_project_guide_integration.py` | project-guide hosting + refresh on reinit |
| `test_subcommand_cli.py` / `test_cross_platform.py` / `test_reinit.py` / `test_pip_upgrade.py` / `test_bootstrap.py` | CLI dispatch, platform behavior, reinit, pip upgrade, micromamba bootstrap |

**Markers**: `venv`, `micromamba`, `requires_micromamba`, `requires_asdf`, `requires_direnv`, `macos`, `linux`, `slow`

### Performance Tests (Bats)

[tests/perf/test_plugin_activation_latency.bats](../../tests/perf/test_plugin_activation_latency.bats) enforces the **PC-4b** per-plugin activation budget (≤ 50ms p95) across the pure-Python / Node-only / polyglot fixtures. Runs via `make test-perf` and as part of `make test`.

### Testing the project's own envs — the named-environment model

Pyve dogfoods its own model: dependencies split across declared `[env.<name>]` environments by `purpose`. The default two-env shape is the **main env** (`root`, purpose `utility`/`run`) plus a **`testenv`** (purpose `test`) holding the test toolchain (pytest, ruff, mypy). `pyve test [--env <name>]` runs in a `test`-purpose env — the purpose gate hard-errors a non-test target — and additional named test envs (e.g. a separate `lint` env) are declared alongside and selected with `--env`, including comma-separated matrices. See [`project-essentials.md`](project-essentials.md) for the canonical invocation forms.

### CI Pipeline (`.github/workflows/test.yml`)

| Job | Runner | Matrix | What it runs |
|-----|--------|--------|-------------|
| Unit Tests | ubuntu + macos | — | `make test-unit` (Bats) + `make test-perf` |
| Integration Tests | ubuntu + macos | Python 3.12, 3.14 | pytest venv tests |
| Micromamba Tests | ubuntu + macos | Python 3.12 | pytest micromamba tests |
| Lint | ubuntu | — | ShellCheck, black, flake8 (on `tests/`) |
| Bash Coverage (kcov) | ubuntu | — | Line coverage of `lib/*.sh` and `pyve.sh` via kcov; uploads to Codecov |
| Test Summary | ubuntu | — | Gate: fail if unit or integration fail |
