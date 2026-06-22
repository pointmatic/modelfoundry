# features.md — Pyve (Bash)

This document defines **what** the `pyve` project does -- requirements, inputs, outputs, behavior -- without specifying **how** it is implemented. This is the source of truth for scope.

For a high-level concept (why), see [`concept.md`](concept.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For a breakdown of the implementation plan (step-by-step tasks), see [`stories.md`](stories.md). For project-specific must-know facts that future LLMs need to avoid blunders, see [`project-essentials.md`](project-essentials.md). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Project Goal

Pyve is a command-line tool that provides a single, declarative entry point for setting up and managing project environments across multiple language ecosystems on macOS and Linux. A root-level `pyve.toml` manifest names each environment and its purpose; language plugins (Python and Node / SvelteKit today, more through a stable contract) materialize those environments through their own backends and compose into one direnv-driven activation, one `.gitignore`, and one health report. It orchestrates existing tools rather than replacing them, and supports both interactive workflows (auto-activation) and non-interactive CI/CD pipelines (explicit execution via `pyve run`).

### Core Requirements

1. Initialize a complete project environment in one command (`pyve init`) — across one or more stacks — covering language-version selection, environment materialization, direnv configuration, `.env` setup, and `.gitignore` management.
2. Declare every environment in a root-level `pyve.toml` manifest: `[project]`, `[env.<name>]` (purpose, backend, plugin-private attributes), and `[plugins.<lang>]`.
3. Support named environments with purposes (`run`, `test`, `utility`, `temp`) and name-based defaults.
4. Provide a plugin + backend-provider contract so languages and backends plug into one composition layer; ship Python (venv / micromamba) and Node / SvelteKit (pnpm / npm / yarn) as reference plugins.
5. Compose lifecycle commands (`init` / `check` / `status` / `purge`) and generated files (`.envrc` / `.gitignore`) across every active plugin, including polyglot projects.
6. Manage language versions through each ecosystem's own version managers (Python: asdf / pyenv; Node: nvm / fnm / volta), without installing the version managers themselves.
7. Execute commands inside the correct environment without manual activation (`pyve run`, `pyve test`, `pyve env run`).
8. Diagnose environment health (`pyve check`, CI-safe 0/1/2 exit codes) and snapshot project state (`pyve status`).
9. Cleanly remove all Pyve-created artifacts (`pyve purge`), preserving user data (non-empty `.env` files, source, git history, `package.json`, lockfiles).
10. Migrate v2 projects to the v3 manifest deterministically and idempotently (`pyve self migrate`).
11. Install and uninstall the Pyve script itself, including a hidden, Pyve-owned toolchain Python (`pyve self install` / `pyve self uninstall`).

### Operational Requirements

1. **Error handling** — Check for prerequisites (version managers, direnv, micromamba) before operations and provide actionable error messages when dependencies are missing.
2. **Conflict detection** — Detect existing environments, version-manager files, and direnv configuration before initialization. Skip with informational messages rather than overwriting.
3. **Idempotency** — Running `pyve init` on an already-initialized project offers update-in-place or force re-initialization, rather than failing or silently overwriting.
4. **Smart re-initialization** — `pyve update` (non-destructive: refreshes managed files + manifest version + project-guide scaffolding) and `pyve init --force` (destructive: purges and re-creates the environments).
5. **Failure-safe composed writes** — `.envrc` and `.gitignore` are composed across all plugins atomically: Pyve writes to a temp file, backs the current file up to `.envrc.prev` / `.gitignore.prev`, and promotes with an atomic rename. If any plugin emits an unsafe snippet, the existing file is left untouched and the command exits non-zero.
6. **Logging** — Provide clear success (✓), warning (⚠), and error (✗) indicators for all operations.

### Quality Requirements

1. **Self-healing `.gitignore`** — Maintain a Pyve-managed section (composed across plugins) with each ecosystem's build/test artifacts and environment entries. Preserve user-authored content outside the managed markers verbatim. Rebuild the managed section on each init to restore accidentally deleted entries.
2. **Idempotent generated files** — Running init multiple times produces identical `.gitignore` / `.envrc` content (no duplicate entries, no accumulated blank lines).
3. **Lock-file validation (declarative)** — For micromamba environments, whether a lock is *required* is keyed on the project's own declaration: `conda-lock` present as a dependency in `environment.yml`. Declared-but-missing/stale → non-strict `init` nudges ("run `pyve lock`"), `--strict` hard-errors; not declared → silent. `--no-lock` opts out for the run (resolve from `environment.yml`, never deletes a committed lock) and beats `--strict`. `init` never auto-runs `pyve lock`.
4. **Secure file permissions** — `.env` files are created with `chmod 600` (owner read/write only).
5. **No noise on non-applicable stacks** — A project that does not use a given plugin produces zero output from that plugin in `check` / `status` (e.g. a Node-only project emits no Python diagnostics).
6. **Latency budget** — Each plugin's activation contribution stays within ≤ 50ms p95, enforced across single-stack and polyglot project shapes.

### Usability Requirements

1. **CLI tool** — Invoked as `pyve` (after install) or `./pyve.sh` (direct execution).
2. **Short flags** — Universal flags have short forms (`-h`, `-v`, `-c`).
3. **Interactive and non-interactive modes** — An interactive wizard for `pyve init`; non-interactive flags and environment variables for CI/CD.
4. **direnv integration** — For interactive use, environments auto-activate/deactivate on directory entry/exit. For CI/CD, `pyve run` provides explicit execution without direnv.
5. **Easy and pleasant UI/UX** — Beyond consistency, Pyve aims to be a delight to use (see [FR-20](#fr-20-easy-and-pleasant-uiux)).

### Non-goals

- Pyve does not replace the tools it orchestrates (asdf, pyenv, direnv, micromamba, nvm/fnm/volta, pnpm/npm/yarn).
- Pyve does not install version managers (asdf, pyenv, nvm, …) or `conda-lock` as standalone binaries.
- Pyve does not manage project dependencies (pip install, conda install, package add) beyond initial environment creation.
- Pyve does not provide a GUI or web interface.
- Pyve does not manage Docker containers or cloud environments. (A check-only Docker backend is roadmap, via the plugin contract — not shipped in v3.0.)
- Pyve does not support Windows.
- Pyve does not write a distutils compatibility shim — retired as obsolete now that setuptools makes `SETUPTOOLS_USE_DISTUTILS=local` the default and modern build backends use PEP 517 isolation.

---

## Inputs

### Required

- **Subcommand or universal flag** — One of:
  - Subcommands: `init`, `purge`, `update`, `check`, `status`, `run`, `test`, `env {init|install|purge|run|list|prune|sync}`, `lock`, `package`, `python {set|show}`, `self {install|uninstall|migrate|provision|unprovision}`.
  - Legacy sugar: `pyve testenv <sub>` is the deprecated alias for `pyve env <sub>` — it still works during the v3.x window (delegating to `pyve env`) and prints a one-time deprecation warning per shell. Hard-error replacement lands in v4.0.
  - Universal flags (CLI convention): `--help` / `-h`, `--version` / `-v`, `--config` / `-c`.

  **Legacy-flag hard-error catches.** Removed flag/subcommand forms print a precise migration error and exit non-zero rather than "unknown command": `--init`, `--purge`, `--validate`, `--update`, `--doctor`, `--status`, `--python-version`, `--install`, `--uninstall`, `-i`, `-p`, and the `doctor` / `validate` subcommands (all redirected at their v3 replacements).

### Optional

| Input | Description | Example |
|-------|-------------|---------|
| `--backend <type>` | Environment backend for the active plugin (`venv`, `micromamba`, `pnpm`, `npm`, `yarn`, `auto`) | `--backend micromamba` |
| `--python-version <ver>` | Python version in `#.#.#` format | `--python-version 3.14.5` |
| `--env-name <name>` | Name for the materialized environment | `--env-name myproject-dev` |
| `--node-path <path>` | Sub-tree path for the Node plugin in a polyglot scaffold | `--node-path src/frontend` |
| `--local-env` | Copy `~/.local/.env` template to project `.env` | `pyve init --local-env` |
| `--no-direnv` | Skip `.envrc` creation | `pyve init --no-direnv` |
| `--force` | Force re-initialization (purge + init) | `pyve init --force` |
| `--auto-bootstrap` | Auto-install micromamba without prompting | `pyve init --auto-bootstrap` |
| `--bootstrap-to <loc>` | Micromamba bootstrap location (`project` or `user`) | `pyve init --bootstrap-to project` |
| `--strict` | Enforce the lock requirement and opt out of scaffolding/inference | `pyve init --strict` |
| `--no-lock` | Resolve from `environment.yml`, ignore any present lock (never deletes it), skip the requirement (beats `--strict`), omit `conda-lock` from a fresh scaffold | `pyve init --no-lock` |
| `--allow-synced-dir` | Bypass the cloud-synced directory check | `pyve init --allow-synced-dir` |
| `--keep-testenv` | Preserve the other declared envs (test/utility/temp) during purge, to save a rebuild | `pyve purge --keep-testenv` |
| `--project-guide` / `--no-project-guide` | Force / skip the project-guide hook (overrides auto-detection) | `pyve init --no-project-guide` |
| `--project-guide-completion` / `--no-project-guide-completion` | Force / skip shell-completion wiring | `pyve init --project-guide-completion` |
| `--env <name>` | (test/lock/package) target a named environment | `pyve test --env smoke` |
| `--check` | (lock) verify lock freshness without regenerating | `pyve lock --check` |
| `--all` | (lock) lock the main env + every conda-backed env | `pyve lock --all` |
| `--dry-run` / `--no-rebuild` | (self migrate) preview or skip the env-rebuild step | `pyve self migrate --dry-run` |

### Project Files (Auto-Detection)

| File | Effect |
|------|--------|
| `pyve.toml` | The canonical manifest — declares envs, backends, and plugins (highest priority) |
| `environment.yml` / `conda-lock.yml` | Python plugin → micromamba backend |
| `pyproject.toml` / `requirements.txt` | Python plugin → venv backend |
| `package.json` + lockfile (`pnpm-lock.yaml` / `package-lock.json` / `yarn.lock`) | Node plugin → matching provider (`pnpm` / `npm` / `yarn`; defaults to `pnpm`) |

---

## Outputs

### Files created by `pyve init`

| File / Directory | Description |
|------------------|-------------|
| `pyve.toml` | The project manifest (written on fresh init) |
| `.pyve/envs/<name>/{venv\|conda}/` | Materialized per-project environments (the reserved `root` venv may live at `.venv`) |
| `.tool-versions` / `.python-version` | Python version pin (asdf / pyenv) |
| `node_modules/` | Node dependencies (Node plugin) |
| `.envrc` | Composed direnv activation across all plugins (unless `--no-direnv`) |
| `.env` | Environment-variables file (chmod 600) |
| `.gitignore` | Composed Pyve-managed section + preserved user content |
| `.vscode/settings.json` | IDE interpreter/isolation settings (micromamba) |
| `.pyve/` | Materialized state — environments, locks, sentinels, `.v2-legacy/` backups (never configuration) |

### Files created by `pyve self install`

| File / Directory | Description |
|------------------|-------------|
| `~/.local/bin/pyve.sh`, `~/.local/bin/lib/`, `~/.local/bin/pyve` (symlink) | The installed script |
| `~/.local/.env` | User-level environment template (chmod 600) |
| `~/.local/share/pyve/toolchain/<version>/venv` | Hidden, Pyve-owned toolchain Python for running Pyve's internal helpers |

---

## Functional Requirements

### FR-1: Environment Initialization (`pyve init`)

Initialize a complete project environment in the current directory, composing across every detected stack.

**Behavior:**
1. Detect each stack from project files (or honor an existing `pyve.toml`); write `pyve.toml` on a fresh project.
2. For each active plugin, set language versions via the ecosystem's version manager (auto-installing the requested version where the manager supports it) and materialize the environment via the resolved backend.
3. Prompt to install dependencies after environment creation (unless `--auto-install-deps` / `--no-install-deps`).
4. Compose every plugin's activation snippet into one `.envrc` (unless `--no-direnv`) and every plugin's ignore entries into one `.gitignore` section.
5. Create `.env` with secure permissions.
6. Run the project-guide hook ([FR-19](#fr-19-project-guide-integration)) as the final step before the success summary.
7. End with a single "Next steps:" block whose items appear conditionally (e.g. `direnv allow` unless `--no-direnv`; `pyve env install -r requirements-dev.txt` when `requirements-dev.txt` exists; `Read docs/project-guide/go.md` when `.project-guide.yml` exists).

**Interactive wizard.** Every `pyve init` runs through a wizard; flags suppress only the *interactive* part of a prompt while still rendering the resolved value. Prompts, in fixed order: **backend → language-version pin → project-guide**. When at least one prompt would read stdin and stdin is not a TTY, `pyve init` exits non-zero naming the missing flags; `PYVE_INIT_NONINTERACTIVE=1` bypasses the guard (degrading each prompt to its auto-detect default).

**Polyglot scaffold.** When `pyve init` detects both a Python signal and a `package.json` at the root, it writes a polyglot `pyve.toml` with `[plugins.python]` (root) and `[plugins.node]` at a distinct sub-path — two plugins cannot both own `.`. The Node path is chosen by a convention walk (`src/frontend`, `frontend`, `web`, `client`, `ui`), `--node-path`, or a prompt (default `src/frontend`); the chosen path is always announced.

**Edge cases:**
- Existing environment detected → offer update / force / cancel.
- Reserved environment directory names rejected (`.env`, `.git`, `.gitignore`, `.tool-versions`, `.python-version`, `.envrc`).
- Invalid version format rejected.
- A project python that cannot be resolved produces an actionable error (run `pyve init`, fix the pin) rather than a misleading "invalid manifest".

### FR-2: Declarative Manifest (`pyve.toml`)

A single root-level `pyve.toml` is the canonical declaration of a Pyve project. Everything under `.pyve/` is materialized state, never configuration.

**Behavior:**
- `pyve_schema` (top-level, defaults to `"3.0"`) records the manifest schema version.
- `[project]` holds project-level metadata.
- `[env.<name>]` declares one environment surface: `purpose`, `backend`, and structured/plugin-private attributes (`languages`, `manual_steps`, `packaging`, and backend-source attributes like `requirements` / `extra` / `manifest`). Every field is optional; the reader applies documented defaults.
- `[plugins.<lang>]` declares an active plugin and its root `path` (defaulting to `.`).
- The manifest is read through one helper (Pyve's toolchain Python) and exposed to the rest of Pyve through flat accessors; consumers never parse the TOML directly.

**Edge cases:**
- Missing `pyve.toml` on a v2-configured project → a read-compatibility layer synthesizes a v3-shaped manifest from legacy sources during the v3.0 window, so the project keeps working until migrated.
- Two plugins declaring the same `path` → a cardinality error at validation time.

### FR-3: Named Environments & Purposes

Every `[env.<name>]` carries a `purpose` from the closed set `{run, test, utility, temp}`. Purpose lets one mechanism host runtime, test, dev-tooling, and ephemeral environments without overloading "test".

**Behavior:**
- `run` — the executed/deployable runtime surface; `test` — test runners and test-only deps; `utility` — dev/orchestration tooling; `temp` — structured ephemeral space.
- When `purpose` is omitted, a name-based default applies: `testenv → test`, `root → utility`, otherwise `utility`. Explicit declaration always wins.
- The resolver is the single gate purpose-keyed selectors consult.

**What each purpose protects (durability model).** Durability is *not* a "survives `pyve purge`" ranking — an environment is a pure function of its declaration, so purging is lossy only to the degree rebuild is costly or unfaithful. *Irreproducibility is the bug: an env you are afraid to rebuild is a defect, not an asset.* Each purpose names which precious resource, if any, preservation protects:

| purpose | precious resource | consequence |
|---|---|---|
| `utility` | ~nothing (ad-hoc dev tooling: ruff/mypy/scratch) | freely disposable; rebuild is the model |
| `temp` | nothing (one-shot) | ephemeral; auto-pruned |
| `test` | mostly reconstruction **cost** + fast iteration | cacheable; reproducible; low drift stakes |
| `run` | upstream-churn insulation + **validated identity** | reproducibility mandate; lock + artifact-promotion target |

Preservation is therefore two independent levers, not a permanence flag: **recovery fidelity** (make rebuild always faithful — a complete declaration) and **recovery cost** (a cache with declaration-hash invalidation; `run`/`test` rank higher, `utility`/`temp` little or none). For `run`, the durable thing lives *outside* the fragile env directory as a lockfile + promoted artifact (built wheelhouse/image), because the most-preserved env is paradoxically the most rot-prone. *(The cache-with-invalidation and artifact-promotion mechanics are the Phase P direction, not shipped in v3.0; the `purpose` vocabulary and the `pyve test --env` gate ship today.)*

**Edge cases:**
- `pyve test --env <name>` restricts to `purpose = "test"` envs; selecting any other purpose hard-errors with a precise "use `pyve env run <name> -- <command>`" hint.
- `pyve test --env root` is handled before the gate (delegates to running pytest in the root env), preserving the route-to-root selector semantics.

### FR-4: Plugin & Backend-Provider Model

A plugin contract and a backend-provider registry let languages and backends plug into one composition layer.

**Behavior:**
- Every declared env is a **materialized dependency closure**; `purpose` labels what it's for, `backend` declares how it materializes.
- Three backend categories are recognized: **virtualized** (per-project env directory, PATH-activated — `venv`, `micromamba`, `pnpm`), **cache-backed** (shared user cache + project lockfile — designed-in, none ship in v3.0), and **check-only** (verify presence/version, no install — designed-in, none ship in v3.0).
- Each plugin registers its hooks (`init` / `purge` / `update` / `check` / `status` / `run` / `test` / `activate` / `.gitignore`) and the category of each backend; the framework routes lifecycle commands accordingly.
- Plugin-supplied snippets pass an input-safety validator before they are composed into `.envrc` / `.gitignore`.

**Advisory attributes (declared, not enforced in v3.0):**
- `languages` (string list) — declares the language flavors an env materializes. The only surfaced behavior is a conservative `pyve check` warning when `languages` is declared without `"python"` on a Python-managed env.
- `manual_steps` (string list) — one-time setup actions Pyve does not automate; rendered as an advisory header in `check` / `status`, never affecting exit code.

### FR-5: Python Plugin

The reference Python plugin brings venv- and micromamba-backed environments under the contract.

**Behavior:**
- Backends `venv` (pip-based) and `micromamba` (conda-compatible); auto-detected (`environment.yml` → micromamba; `pyproject.toml` / `requirements.txt` → venv) or via `--backend`.
- Python versions managed through asdf or pyenv (auto-install where supported); Pyve never installs the version managers.
- **`pyve python set <ver>`** writes the local pin (`.tool-versions` / `.python-version`), auto-installing if needed and refreshing shims; **`pyve python show`** reads the active pin and its source (pure read).
- Lifecycle hooks materialize/purge/update the env, emit the venv/conda activation snippet, contribute `.gitignore` entries, and run check/status/run/test.

**Edge cases:**
- Invalid version format (`#.#.#`) rejected.
- Micromamba env names are sanitized and reserved names (`base`, `root`, `default`, `conda`, `mamba`, `micromamba`) rejected.

### FR-6: Node / SvelteKit Plugin

The reference Node plugin proves the contract generalizes beyond Python.

**Behavior:**
- Backends `pnpm` / `npm` / `yarn` — explicit `backend` wins; otherwise inferred from the lockfile present, defaulting to `pnpm`.
- Runtime resolved by the precedence chain **nvm > fnm > volta > asdf > Homebrew / system PATH**, each tier honoring a `PYVE_NO_*_COMPAT` opt-out. Pyve does not install a Node runtime; it fails loudly when none is reachable.
- `init` installs into `node_modules/` via the resolved provider; `purge` smart-removes generated dirs (`node_modules/`, `.svelte-kit/`, `dist/`, `build/`, `.next/`) while never touching `package.json`, lockfiles, or source; `update` uses the CI-frozen install form when `CI` is set.
- Activation contributes a single `PATH_add "node_modules/.bin"` (path-prefixed for sub-tree projects).
- `test` is honest delegation — it runs the provider's `test` script; the user's `package.json` defines what "test" means.

**Edge cases:**
- SvelteKit (`@sveltejs/kit` / `svelte.config.js`) is recognized as advisory `frameworks` metadata in check/status — not specially provisioned.
- A `languages` list including `typescript` without a `typescript` dependency warns (advisory only).

### FR-7: Composition Layer

Turns one `pyve <cmd>` into a fan-out across every active plugin, composing the results into one coherent artifact or report.

**Behavior:**
- **Composed `.envrc` / `.gitignore`** — every active plugin's activation snippet and ignore entries are assembled into one managed section each, path-prefixed for sub-tree plugins; user-authored content outside the markers round-trips verbatim.
- **Failure-safe writes** — atomic and non-destructive (see Operational Requirement 5); one-step rollback is `mv -f .envrc.prev .envrc`.
- **Aggregated `pyve check`** — a per-plugin section (path-labelled, e.g. `[node @ src/frontend]`) rolled up to a single worst-severity exit; any plugin error → CI-failing exit, warnings advisory.
- **Aggregated `pyve status`** — a per-plugin read-only snapshot; always exits 0.
- **Aggregated `pyve purge`** — one confirmation lists what every plugin will remove, grouped by plugin; any path a plugin marks user-authored is never removed; removal is delete-only and resumable.
- **No-Python noise** — a Node-only project produces zero Python output from check/status, while bare directories and project-guide/polyglot projects still default to Python so the "run `pyve init`" nudge is never lost.

### FR-8: Command Execution (`pyve run`, `pyve test`, `pyve env run`)

Execute commands inside the right environment without manual activation.

**Behavior:**
- `pyve run <cmd>` runs in the project's run environment (venv directly, micromamba via `micromamba run -p <prefix>`, Node via the provider). Arguments pass through; the command's exit code propagates.
- `pyve test [--env <name>[,<name>…]]` runs tests in a `purpose = "test"` environment; the matrix form runs each named env sequentially with a per-env header, continuing past failures and returning the worst-case exit code. Lazy envs auto-provision on first targeted use (suppressible via `PYVE_NO_AUTO_PROVISION=1`). A silent-skip advisory warns when another candidate env has the test runner installed (suppressible via `PYVE_NO_TESTENV_ADVISORY=1`).
- `pyve env run <name> -- <cmd>` runs a command inside any named environment (the canonical path for `utility` / `temp` envs).

**Edge cases:**
- No environment found → error suggesting `pyve init`.
- Command not found → exit 127.
- Conda-backed envs are rejected by the venv-only `env run` path; use `--env root` or a manual `micromamba run`.

### FR-9: Diagnostics & Status (`pyve check`, `pyve status`)

**`pyve check`** diagnoses environment problems and suggests one actionable remediation per failure.
- Composed across plugins with a worst-severity roll-up. Exit codes: 0 (all pass) / 1 (errors — broken for `run`/`test`) / 2 (warnings only — drifting but working). Safe for CI gating.
- Every failure points at exactly one remediation command. Status indicators: ✓ / ⚠ / ✗ / plain info.
- Health checks probe runnability (executing the artifact), not just file existence — a dangling symlink or dead-shebang script is reported broken, never rubber-stamped.
- **Resolution reasoning (Phase P roadmap, not shipped in v3.0):** for each managed command, report *where* it resolves and *why* — PATH-slot order, a venv shadowing a version-manager pin, reachability under the active pin, venv↔pin interpreter drift — and classify runnability failures (dead interpreter, asdf "no version set", dangling symlink, missing command, version-manager-not-installed). See [FR-22](#fr-22-environment-resolution-reasoning--healing).

**`pyve status`** is a read-only "what is this project?" snapshot — sectioned Project / Environment(s) / Integrations, per-plugin. Always exits 0 unless Pyve itself errors. No remediation text.

### FR-10: Environment Purge (`pyve purge`)

Remove all Pyve-created artifacts from the current directory, composed across plugins.

**Behavior:**
- Each plugin smart-removes its generated environments and directories; version-manager pins and `.envrc` are removed; `.env` is removed only if empty (preserved with a warning if non-empty).
- The Pyve-managed `.gitignore` section is cleaned; committed artifacts (`conda-lock.yml`, `environment.yml`, `package.json`, lockfiles) are never removed.
- `--keep-testenv` preserves the project's other declared environments (test / utility / temp) so purging the run environment doesn't force a costly rebuild of the rest — a reconstruction-cost convenience, not a claim that those envs are precious (see [FR-3](#fr-3-named-environments--purposes)).

**Edge cases:**
- No environment found → informational message, no error.
- A failed purge is resumable (delete-only); re-running is safe.

### FR-11: Non-Destructive Upgrade (`pyve update`)

Project-level refresh that never rebuilds environments.

**Behavior:**
- Rewrites the manifest's recorded Pyve version; refreshes Pyve-managed sections of `.gitignore` and (when present) `.vscode/settings.json`; bootstraps missing `.pyve/` scaffolding paths.
- Runs project-guide's content-aware refresh ([FR-19](#fr-19-project-guide-integration), step 2) unless skipped.
- Never rebuilds the env, never creates a `.env` / `.envrc` that doesn't exist, never re-prompts for backend, never prompts interactively.

**Edge cases:**
- Exit 0 on success (including no-op); exit 1 on failure (unwritable/corrupt config).
- Use `pyve init --force` to rebuild a known-corrupt environment.

### FR-12: Backend Auto-Detection

Determine each plugin's backend from project files when `--backend` is not given.

**Behavior:**
- Priority: `pyve.toml` > project files (`environment.yml` / `conda-lock.yml` → micromamba; `pyproject.toml` / `requirements.txt` → venv; `package.json` + lockfile → Node provider) > default (venv for Python, pnpm for Node).
- Ambiguous Python cases (both conda and pip files) prompt interactively (default micromamba); `PYVE_FORCE_YES=1` or `CI=1` auto-defaults without prompting.

### FR-13: Lock Wrapper (`pyve lock`)

Generate or update `conda-lock.yml` for micromamba environments (declarative model).

**Behavior:**
- Backend guard: venv-backed projects fail with a clear "micromamba only" message.
- Prerequisite: when `conda-lock` is not on PATH, fail with instructions (declare it in `environment.yml`; rebuild). Fresh micromamba scaffolds declare `conda-lock` by default, so they reach `pyve lock` with the locker already installed.
- Detect the conda platform, run `conda-lock` for the current platform, and report up-to-date / success / error. `--check` verifies freshness without regenerating; `--env <name>` / `--all` lock named conda-backed envs.

### FR-14: Micromamba Bootstrap & Starter `environment.yml`

Install micromamba when required-but-absent, and scaffold a starter `environment.yml` on a fresh micromamba init.

**Behavior:**
- Interactive bootstrap prompts for a location (project sandbox, user sandbox, system package manager, manual); `--auto-bootstrap` + `--bootstrap-to` drive it non-interactively. Bootstrap downloads are verified against a published SHA-256 checksum.
- When `pyve init --backend micromamba` runs with neither `environment.yml` nor `conda-lock.yml` (and not `--strict`), Pyve writes a minimal starter `environment.yml` pinning Python on `conda-forge`, adding `pip`, and (by default) declaring `conda-lock` (omitted under `--no-lock` / wizard "n"), then proceeds with the normal bootstrap.

**Edge cases:**
- Does not scaffold when `conda-lock.yml` exists without `environment.yml` (inconsistent-state error), under `--strict`, or over an existing `environment.yml`.

### FR-15: Packaging Lifecycle Hook (`pyve package`) — reserved in v3.0

`pyve package [--env <name>]` is the artifact-materialization verb: it builds the packaging artifact an env declares, by dispatching to a registered packaging provider.

**Behavior:**
- An env declares its artifact kind via a core `packaging` attribute (e.g. `packaging = "docker"`) plus provider-private fields the core stores but never interprets.
- Target resolution is `--env <name>` or the default env; resolution is **not** purpose-gated.
- v3.0 ships the verb + contract + registry but registers **zero** providers. Live branches: `packaging` declared but no provider → clean advisory, exit 0 ("reserved for a future release"); `packaging` absent → informational, exit 0; provider registered → dispatched (test-stub only in v3.0).

**Roadmap (post-v3.0):** `docker` / `podman` / `lock_bundle` / `binary` providers; closed-vocabulary validation of the `packaging` value. A separate future `deploy` verb owns the ship step.

### FR-16: Migration & Deprecation Surface (`pyve self migrate`)

Move a v2-configured project onto the v3 manifest, deterministically.

**Behavior:**
- `pyve self migrate` writes `pyve.toml` from legacy sources, moves the old files into `.pyve/.v2-legacy/` for one release cycle, and rebuilds environments at the v3 state layout. Idempotent; `--dry-run` / `--no-rebuild` expose intermediate states.
- Three coordinated deprecation layers: the deterministic migrator (this command); a one-shot soft banner on `pyve <cmd>` in v2-configured projects (suppressible via `PYVE_QUIET=1`); and a read-compatibility layer that synthesizes a v3 shape from v2 sources so users can defer migration during the v3.0 window.

**Edge cases:**
- `.pyve/.v2-legacy/` is the single deterministic backup/rollback location.

### FR-17: Script Installation (`pyve self install` / `pyve self uninstall`)

Install or remove the Pyve script, under the `self` namespace.

**Behavior:**
- **Install** copies the script + `lib/` to `~/.local/bin`, creates the symlink and PATH entry, and seeds `~/.local/.env`. It also provisions **Pyve's own toolchain Python** — a hidden venv at `~/.local/share/pyve/toolchain/<version>/venv` used to run Pyve's internal Python helpers so manifest parsing works even on non-Python projects. Best-effort; never blocks the install; override the interpreter with `PYVE_PYTHON`.
- **Uninstall** removes the script, symlink, `lib/`, PATH entry, the toolchain tree, and the project-guide completion sentinel from `~/.zshrc` / `~/.bashrc`. Preserves a non-empty `~/.local/.env`.
- `pyve self provision` / `pyve self unprovision` (re)build or remove the toolchain + project-guide hosting independently of install.

### FR-18: Cloud-Synced Directory Detection

Refuse to initialize inside a known cloud-synced directory before any environment work begins.

**Behavior:**
- Path heuristic: hard-fail if `$PWD` descends from `~/Documents`, `~/Desktop`, `~/Library/Mobile Documents`, `~/Dropbox`, `~/Google Drive`, or `~/OneDrive`.
- macOS xattr secondary check for cloud provider markers.
- The error names the path, sync root, provider, a recommended `mv`, and the `--allow-synced-dir` override (or `PYVE_ALLOW_SYNCED_DIR=1`).
- **Rationale:** cloud-sync daemons race micromamba extraction and cause silent, non-recoverable corruption — a warning is insufficient.

### FR-19: project-guide Integration

Opt-out hook that wires [`project-guide`](https://pointmatic.github.io/project-guide/) into Pyve so the LLM-assisted workflow is available from the first command. project-guide is hosted once as a Pyve-managed global tool (in the toolchain venv, with a `~/.local/bin` shim), not installed per-project.

**Behavior:**
- On `pyve init` (fresh or `--force`): ensure project-guide hosting, then scaffold or refresh managed artifacts — `project-guide init --no-input` when `.project-guide.yml` is absent, `project-guide update --no-input` (content-aware, `.bak.<timestamp>` siblings, state-preserving) when present — and, optionally, wire shell completion.
- On `pyve update`: run the refresh step only.
- Trigger priority (first match wins): `--no-project-guide` / `--project-guide` flags → `PYVE_NO_PROJECT_GUIDE` / `PYVE_PROJECT_GUIDE` env vars → project-guide already in project deps (auto-skip) → non-interactive default (install, skip completion) → interactive prompt.

**Edge cases:**
- All steps are failure-non-fatal; `pyve init` still exits 0.
- `.project-guide.yml` is the canonical install marker and a load-bearing cross-repo contract; it no longer implies a project Python env.
- `pyve purge` never touches `.project-guide.yml` or `docs/project-guide/`.

### FR-20: Easy and Pleasant UI/UX

Pyve aims to be a delight to use — not merely consistent. Consistency is the floor; the goal is that the tool "just makes so much sense and is so easy."

- **UI is the skin.** Every command shares one polished terminal presentation: rounded-box headers/footers, a single color palette, `✔` / `✘` / `⚠` / `▸` status symbols, `[Y/n]` / `[y/N]` prompt conventions, and a dimmed `$ cmd args…` echo before each subprocess. It should look clean and be immediately legible and navigable (the bar is a modern, well-crafted CLI experience). ANSI degrades gracefully under `NO_COLOR=1`; the palette is shared with sibling Pointmatic tools so they feel identical in the same terminal.
- **UX is the holistic experience** — the aftertaste of coherent concept → intent → features → consistency. Defaults are safe and obvious, prompts state the resolved value even when flag-driven, every error names exactly one next action, and the same verbs/manifest shape work across every plugin so the user learns Pyve once. Read-only / machine-parseable output (e.g. `pyve python show`) stays unwrapped for scripting. Subprocess output passes through in full so real progress and errors stay visible. `--verbose` / `PYVE_VERBOSE=1` streams subprocess output live, gated through a single verbosity helper.

### FR-21: asdf / direnv Coexistence

When Pyve runs under asdf-managed Python, prevent asdf's Python plugin from reshimming venv-installed CLIs so `$(which <tool>)` resolves inside the project env, not the global asdf layer.

**Behavior:**
- Only when asdf is the active version manager and `PYVE_NO_ASDF_COMPAT=1` is not set, Pyve sets `ASDF_PYTHON_PLUGIN_DISABLE_RESHIM=1` at two layers: a sentinel-commented block appended to `.envrc`, and an export in `pyve run` (defense-in-depth for `--no-direnv` / CI). `PYVE_NO_ASDF_COMPAT=1` suppresses both.

### FR-22: Environment Resolution Reasoning & Healing

*Roadmap — Phase P, not shipped in v3.0.*

Make Pyve's own substrate bulletproof: explain *why* a command resolves the way it does, and repair broken Pyve-managed state instead of leaving the developer (or LLM) to hand-trace and hand-fix it. This is the "calm the chaos" mission applied to Pyve's own substrate.

**Behavior (roadmap):**
- **Resolution reasoning** extends `pyve check` ([FR-9](#fr-9-diagnostics--status-pyve-check-pyve-status)): for each managed command, narrate *where* it resolves and *why* — PATH-slot ordering, a venv shadowing a version-manager pin, reachability under the active pin, venv↔pin interpreter drift. The check should be able to say, unprompted: "`python` resolves from `.venv` (3.14.4), shadowing the asdf pin (3.12.13); `project-guide` falls through to the asdf shim under that pin, which has no project-guide → install it into 3.12.13 or repoint the pin."
- **Runnability classification** — probes execute the artifact and classify the failure: dead interpreter, asdf "no version set", dangling symlink, missing command, version-manager-not-installed. (The existence-≠-runnability principle is already in force for v3.0 health code; this generalizes it across hosting/health code.)
- **Healing (`pyve heal`, or `pyve check --fix`)** — safe, idempotent, **confirm-before-destroy** repairs for each detected failure class: rebuild a toolchain venv with a dead interpreter; re-link a dangling `~/.local/bin` shim; rebuild a `.venv` whose interpreter drifted from the pin (destructive → explicit confirmation); install a missing managed command into the *selected* interpreter. Reversible and re-runnable; never silently mutates without first surfacing what it will do.
- **Close the upstream cause** — the integration test harness must never mutate the developer's real `~/.asdf` / `~/.local` (the test-isolation leak that manufactured the triggering incident); provisioning tests run against a fully self-contained fake `$HOME` or stub provisioning entirely.

**Roadmap:** ships in the Phase P v3.x line; the exact release tag and the full story breakdown are deferred to the subphase plan. Builds on the v3.0 runnability override seam (`PYVE_PROJECT_GUIDE_BIN`) and the `pyve self provision --status` hosting-readiness contract.

---

## Configuration

### Precedence (highest to lowest)

1. CLI flags (`--backend`, `--python-version`, `--env-name`, …)
2. The `pyve.toml` manifest
3. Project files (`environment.yml`, `pyproject.toml`, `package.json`, …)
4. Defaults (Python: venv backend, `DEFAULT_PYTHON_VERSION` = 3.14.5; Node: pnpm)

### The `pyve.toml` manifest

```toml
pyve_schema = "3.0"

[project]
name = "myproject"

[plugins.python]
# path defaults to "."

[plugins.node]
path = "src/frontend"

[env.root]
purpose = "run"
backend = "venv"

[env.testenv]
purpose = "test"
backend = "venv"
requirements = ["requirements-dev.txt"]

[env.web]
purpose   = "run"
backend   = "pnpm"
languages = ["typescript", "javascript"]
```

`pyve.toml` is the only declaration file; everything under `.pyve/` is materialized state. Per-env backend-source attributes (`requirements` / `extra` / `manifest`) are mutually exclusive.

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `PYVE_PYTHON` | Absolute path to the interpreter Pyve uses to run its **own** helpers. Overrides the hidden toolchain venv. Does **not** affect your project's Python. |
| `PYVE_PROJECT_GUIDE_BIN` | Absolute path to a project-guide binary Pyve should use (honored ahead of the hosted shim; mirrors `PYVE_PYTHON`). |
| `PYVE_QUIET` | Suppress the v2→v3 soft migration banner. |
| `PYVE_VERBOSE` | Stream subprocess output live and suppress quiet-by-default decoration (equivalent to `--verbose`). Single source of truth for the verbosity gate. |
| `PYVE_INIT_NONINTERACTIVE` | Bypass the `pyve init` TTY guard (prompts degrade to auto-detect defaults). |
| `PYVE_NO_AUTO_PROVISION` | Suppress lazy auto-provisioning on `pyve test --env <lazy>`; restores the hard-error with an install hint. |
| `PYVE_NO_TESTENV_ADVISORY` | Suppress the `pyve test` silent-skip advisory. |
| `PYVE_AUTO_INSTALL_DEPS` / `PYVE_NO_INSTALL_DEPS` | Auto-install / skip the pip-deps prompt. |
| `PYVE_FORCE_YES` | Auto-default to micromamba in ambiguous Python backend cases. |
| `PYVE_NO_LOCK` | `--no-lock` semantics for the run. |
| `PYVE_ALLOW_SYNCED_DIR` | Bypass the cloud-synced directory check. |
| `PYVE_PROJECT_GUIDE` / `PYVE_NO_PROJECT_GUIDE` | Force / skip the project-guide hook. |
| `PYVE_PROJECT_GUIDE_COMPLETION` / `PYVE_NO_PROJECT_GUIDE_COMPLETION` | Force / skip shell-completion wiring. |
| `PYVE_NO_ASDF_COMPAT` | Suppress the asdf reshim guard ([FR-21](#fr-21-asdf--direnv-coexistence)). |
| `PYVE_NO_NVM_COMPAT` / `PYVE_NO_FNM_COMPAT` / `PYVE_NO_VOLTA_COMPAT` | Opt out of the corresponding Node runtime-manager tier. |
| `CI` | Enable non-interactive mode (auto-defaults, skip prompts). |

---

## Testing Requirements

- **Unit tests** (Bats): white-box testing of shell functions in `lib/*.sh`.
- **Integration tests** (pytest): black-box testing of full `pyve` workflows (init, purge, run, check, status, update, migrate) across Python (venv / micromamba), Node, and polyglot project shapes.
- **Two-environment model.** Pyve projects use separate environments per purpose: runtime code runs in the `run` env (`pyve run …`); tests run in a `purpose = "test"` env (`pyve test …`, not `pyve run pytest`); dev tooling runs via `pyve env run <name> -- …`. Named environments (`[env.<name>]`) let a project declare additional test/utility envs. This isolation is itself part of the contract the tests exercise.
- **Platform coverage**: macOS and Linux (Ubuntu) via CI matrix.
- **Python version matrix**: integration tests run against a lower bound and Pyve's `DEFAULT_PYTHON_VERSION` (3.14.5).

---

## Security and Compliance Notes

- `.env` files are created with `chmod 600` (owner read/write only) and added to `.gitignore`; non-empty `.env` files are never deleted by purge or uninstall.
- Micromamba bootstrap downloads are verified against a published SHA-256 checksum (no weaker-hash fallback).
- Pyve's internal Python helpers run in a hidden, Pyve-owned toolchain venv, isolated from the developer's environment.
- Plugin-supplied `.envrc` / `.gitignore` snippets pass an input-safety validator before composition; composed writes are atomic with `.prev` backups.

---

## Performance Expectations

- Pyve is a shell script with no background processes or daemons.
- Environment-creation time is dominated by language-version installation and dependency installation, not by Pyve itself.
- Each plugin's activation contribution stays within ≤ 50ms p95 across single-stack and polyglot shapes.
- `.gitignore` / `.envrc` composition uses temp files and atomic `mv` to avoid partial writes.

---

## Acceptance Criteria

1. `pyve init` creates fully functional environments — single-stack or polyglot (Python and/or Node) — in one command on both macOS and Linux, declared in `pyve.toml`.
2. Lifecycle commands (`init` / `check` / `status` / `purge`) and generated files (`.envrc` / `.gitignore`) compose correctly across every active plugin.
3. `pyve run` / `pyve test` / `pyve env run` execute in the correct environment without manual activation; `pyve test` is purpose-gated.
4. `pyve check` reports problems with CI-safe 0/1/2 exit codes; `pyve status` provides a read-only snapshot and always exits 0.
5. `pyve purge` cleanly removes Pyve artifacts without destroying user data.
6. `pyve self migrate` moves a v2 project onto the v3 manifest deterministically and idempotently.
7. All operations are idempotent — repeated runs produce the same result.
8. CI/CD workflows run without interactive prompts via the documented flags and environment variables.
9. Unit and integration tests pass on macOS and Linux across the Python version matrix.
