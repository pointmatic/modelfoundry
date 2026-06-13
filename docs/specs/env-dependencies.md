<!-- Vendored from Pyve env-dependencies-template.md at spec_version "3.0". Closed vocabulary is Pyve-owned; project-guide refreshes via a dedicated story when Pyve bumps. See docs/specs/project-essentials.md → "Pyve env-spec vendored-template contract" for the protocol. -->

# env-dependencies.md -- modelfoundry (Python 3.12.13)

This document formally enumerates the **named environments** the `modelfoundry` repo needs:

1. The **root development environment** required to develop the repo (the environment a contributor or LLM must stand up before doing anything else).
2. One or more **named test environments** (the first defaults to `testenv`) required to *efficiently, effectively, and completely* test the codebase.

A secondary purpose is to surface **environment requirements Pyve does not yet materialize** (advisory backends) and **mechanisms missing from the closed vocabulary entirely** (Pyve change-requests), so the Pyve-owned backend vocabulary can grow over time. See [§3 Backend Catalog](#3-backend-catalog) and [§8 Backend Gaps & Pyve Change-Requests](#8-backend-gaps--pyve-change-requests).

> **Related docs**
> - `concept.md` — why the project exists (problem and solution space).
> - `features.md` — what the project does (scope, requirements, behavior).
> - `tech-spec.md` — how the project is built (architecture, dependencies, testing strategy).
> - `docs/project-guide/go.md` — workflow steps tailored to the current mode (cycle steps, approval gates, conventions).
> - Pyve backends reference: <https://pointmatic.github.io/pyve/backends/>

**Repo shape (orienting):** `modelfoundry` is a **library / CLI consumed by other applications** (it ships as the `ml-modelfoundry` wheel and is imported, e.g. inside nbfoundry lifecycle templates). The repo itself has **no production "run" surface** — its only purpose is development and testing. It therefore runs **two micromamba environments**: a `utility` **root** (the env you land in to instantiate a `ModelFoundry` and run scripts ad hoc) and a `test` **`testenv`** (the editable package, the PyTorch plugin, and the dev/test tooling — where every test category executes). The bare-OS `none` backend is reserved for languages with no managed-env concept (Rust/C++/Ruby); for a first-class Python+micromamba combo there is no reason to give up the reproducibility/isolation a managed env provides. See §4.

---

## 1. Document Metadata

| Field | Value |
|-------|-------|
| **Repo name** | `modelfoundry` (PyPI distribution `ml-modelfoundry`) |
| **Primary language(s)** | Python 3.12.13 (`requires-python = ">=3.12,<3.14"`) |
| **Pyve version** | `3.0.6` |
| **Doc status** | `Draft` |
| **Last updated** | `2026-06-12` |
| **Author / maintainer** | Michael Smith |

---

## 2. Conventions & Terminology

- **Environment** — a named, isolated dependency space materialized by a backend. Every
  environment has exactly one **purpose** (surface), one **backend**, and a structured
  attribute set (`app_type`, `frameworks`, `languages`, `packaging`). Environments are
  enumerated machine-readably in [§4.0](#40-environment-surface-enumeration).
- **Purpose (surface)** — the single role an environment serves. Exactly one of:

  | `purpose` | Meaning |
  |-----------|---------|
  | `run` | The deployable/executable artifact's **runtime** — "the thing that ships or executes in production." Its dependency closure is the app's runtime deps, not dev/test tooling. This is the surface `pyve package` / `pyve deploy` (future) operate on. *Disambiguator:* if you would ship or execute it in production, it is `run`; if it only supports development, it is `utility`. |
  | `test` | Hosts **test runners and test-only dependencies**; the env where a class of tests executes. `pyve test --env <name>` gates on `purpose == test`. *Disambiguator:* pytest / vitest / bats and their fixtures live here, never in `run`. |
  | `utility` | Hosts **development / orchestration tooling that is neither the app nor its tests** — formatters, linters, codegen, the `project-guide` host, LLM CLIs. The `root` env defaults to `utility`. *Disambiguator:* it makes development easier but never ships and is not a test surface. *Intended lifecycle (not yet wired):* survives `pyve purge` — it is your tooling, not the project's materialized output. |
  | `temp` | A **declared, reproducible, disposable** workspace that is part of a defined workflow (e.g. the `mktemp -d` sandbox a test harness spins up per run). Concretely: contents are **volatile**, the env is **safe to delete at any time**, and pyve may **prune** it. *The line is declared-vs-ad-hoc:* a reproducible part of a defined workflow → model it as `temp` and enumerate it; a one-off "hello world" poke → do **not** model it at all. *Intended lifecycle (not yet wired):* auto-prune. Today `temp` carries no special runtime behavior — it is a recognized value awaiting its lifecycle. |

  One environment = one purpose. If a single backing directory genuinely serves two
  purposes, declare two environments. (Lists are intentionally **not** supported — forcing
  a single choice keeps each environment's intent unambiguous.)
- **Root development environment** — the environment activated at the repo root (pyve's
  primary environment). Its purpose is typically `utility` — it hosts tooling, not
  necessarily the app or the tests. **In this repo the root is a micromamba `utility` env**
  carrying the editable package + its runtime closure, so a contributor (or LLM) can
  instantiate a `ModelFoundry` and run scripts ad hoc; the dev/test tooling lives in
  `testenv` (see §5.0).
- **Named test environment** — a `purpose: test` environment. The first/default is named
  `testenv`. Additional environments use distinct names (e.g. `testenv-mps`,
  `testenv-cuda`). Each maps to exactly one backend.
- **Backend** — the environment-management mechanism pyve uses to materialize an
  environment. Values are a **closed, Pyve-owned set** of specific mechanism names, never
  generic categories, falling into three categories: *project-virtualized* (`venv`,
  `micromamba`, `pnpm`, `npm`, `yarn`, `uv`, `poetry`, `conda`, `bun`, `deno`),
  *cache-backed* (`cargo`, `go`, `bundler`, `swiftpm`, `xcode`, `android_sdk`, `gradle`,
  `maven`, `sbt`, `dotnet`, `conan`, `cmake`), and *check-only* (`homebrew`, `apt`,
  `docker`, `podman`). Closely-related mechanisms with leaky behavioral differences are kept
  as **separate flavored values** so each flavor's quirks are codified once. The special
  value **`none`** means there is no formal configuration mechanism — the bare OS, the
  implicit default for any surface pyve does not materialize. See [§3](#3-backend-catalog).
- **Structured attributes** — fixed-vocabulary descriptors recorded per environment. Each is
  a **closed set** (Pyve-owned, versioned); a value outside it is a spec violation. Values are
  either *implemented* (pyve acts on them today) or *advisory* (recorded + surfaced, never
  materialized):

  | Attribute | Closed vocabulary (use `none` when not applicable) |
  |-----------|----------------------------------------------------|
  | `app_type` | `api`, `cli`, `service`, `library`, `desktop`, `mobile`, `embedded`, `script`, `web`, `none` |
  | `packaging` | `container`, `static`, `server`, `serverless`, `package`, `binary`, `mobile_app`, `lock_bundle`, `none` |
  | `frameworks` (kind: app) | `sveltekit`, `flask`, `fastapi`, `django`, `react`, `vue`, `jupyter`, `marimo`, `spring`, `j2ee`, `kotlin_multiplatform`, `rails`, `sinatra`, `swiftui`, `uikit`, `none` |
  | `frameworks` (kind: test) | `pytest`, `vitest`, `jest`, `mocha`, `playwright`, `cypress`, `bats`, `rspec`, `minitest`, `xctest`, `junit` |
  | `frameworks` (kind: lint) | `ruff`, `mypy`, `black`, `isort`, `flake8`, `pylint`, `eslint`, `prettier`, `shellcheck`, `shfmt`, `ktlint`, `detekt`, `scalafmt`, `scalafix`, `google_java_format`, `rustfmt`, `clippy`, `gofmt`, `golangci_lint`, `rubocop`, `swiftlint`, `swiftformat`, `clang_format`, `clang_tidy` |
  | `languages` | `python`, `javascript`, `typescript`, `bash`, `c`, `cpp`, `c_sharp`, `java`, `kotlin`, `scala`, `go`, `swift`, `objective_c`, `rust`, `ruby` |

  Each framework's `kind` (app/test/lint) is *intrinsic* — looked up, not an authoring choice;
  one env's `frameworks` list may mix kinds. Two **advisory** fields may also appear per
  environment: **`require_min_version`** (un-installable-toolchain pins) and **`manual_steps`**
  (human-only seams pyve cannot drive). Both are surfaced in `pyve check` / `status`, never
  materialized.
- **Value class — *implemented* vs *advisory*.** Every value in every closed vocabulary is
  exactly one of two classes. **Implemented** = pyve has a real integration that acts on it
  today. **Advisory** = recognized in the vocabulary but pyve takes no materializing action —
  it is *recorded* in `pyve.toml` and *surfaced* in `pyve check` / `pyve status`, never built,
  never an error. An **unknown** value — outside the closed set — is a spec violation that
  hard-errors.
- **Dependency source class** — where a dependency comes from and how it is installed
  (a single environment may mix several):

  | Class | Examples | Manifest / install mechanism |
  |-------|----------|------------------------------|
  | `pip` (PyPI) | `pytest`, `ruff`, `mypy`, `torch` | `pyproject.toml` extras / `requirements-dev.txt` |
  | `conda` (conda-forge) | `python`, `pip` | `environment.yml` → `conda-lock.yml` |
  | `system` (OS / Homebrew / apt) | `git`, `direnv`, `asdf` | `brew install` / `apt-get install` |
  | `vendored` (git-clone / submodule) | (none) | `git clone` into a known path |
  | `runtime` (language interpreter) | `python` | `.tool-versions` (asdf) / micromamba |

- **Canonical backend** — a backend pyve materializes today (the *implemented* class).
  Currently `venv` (default) and `micromamba` (Python plugin), plus `pnpm` / `npm` / `yarn`
  (Node plugin). Every other value in the closed vocabulary is *advisory*. The special value
  `none` materializes nothing by definition (bare OS).
- **Repo-specific terms:**
  - **Test-only repo** — the repo has no `run` (production) surface; it runs two micromamba
    envs — a `utility` **root** (editable package + runtime closure, for ad-hoc instantiation
    and scripts) and a `test` **`testenv`** (the editable package, the PyTorch plugin, and the
    dev/test tooling). See §4.
  - **Bound DataRefinery instance (vendor)** — a read-only, already-materialized upstream
    data directory consumed at runtime via the `ml-datarefinery` library (FR-6). It is an
    *input artifact*, **not** an environment, and is never materialized by pyve.

---

## 3. Backend Catalog

| Backend | Status | Env location | Dependency manifest | Lock artifact | Init command |
|---------|--------|--------------|---------------------|---------------|--------------|
| `none` | **implemented** (bare OS) | n/a — no materialized dir | n/a (`.tool-versions` for the interpreter) | n/a | none — host provides interpreter + tooling |
| `micromamba` | **canonical** | `.pyve/envs/<name>/conda/` | `environment.yml` | `conda-lock.yml` (`pyve lock`) | `pyve testenv init --backend micromamba` |
| `venv` | **canonical (default)** | `.pyve/envs/<name>/venv/` | `requirements.txt` | `requirements.txt` w/ `--hash` (pip-tools) | `pyve init` / `pyve testenv init` |
| `pnpm` / `npm` / `yarn` | **canonical** (Node plugin) | `node_modules/` (+ store) | `package.json` | `pnpm-lock.yaml` / `package-lock.json` / `yarn.lock` | `pyve init` (Node-detected) |

This repo uses **`micromamba`** for both materialized envs — the `utility` root and the
`test` `testenv`. No advisory backends and no container backends are in use. The `none`,
`venv`, and Node rows are retained as the closed-vocabulary reference. See §8.

**Default-backend assumption:** any environment may benefit from the `venv` backend. A
non-`venv` backend is chosen only with a stated reason (recorded per environment in §5). Both
envs' `micromamba` choice is justified in §5 (they inherit the conda-forge-pinned
`python=3.12.13` from `environment.yml`, and the ML stack resolves cleanly on conda-forge).

**Env-location & config note (pyve 3.0.6):** pyve 3.0.6 materializes environments under
`.pyve/envs/<name>/<backend>/` and reads the env spec from **`pyve.toml`** (`pyve_schema =
"3.0"`) via `[env.<name>]` tables — the `[tool.pyve.testenvs]` table in `pyproject.toml` is the
**superseded v2.8 location** and is removed. The two micromamba envs are declared in `pyve.toml`:
`[env.root]` (`purpose = "utility"`) materializes at `.pyve/envs/root/conda/` and `[env.testenv]`
(`purpose = "test"`, `default = true`, `manifest = "environment.yml"`) at
`.pyve/envs/testenv/conda/`. `environment.yml` is the shared conda manifest (pins
`python=3.12.13` + `pip`; the package + extras install via pip per `pyproject.toml`). The
pyve-managed `.envrc` activates the root env, which is correct under this topology. (Pre-3.0
prose in `tech-spec.md` still describes the older `.venv/` + `.pyve/testenvs/<name>/` two-env
layout; flagged for reconciliation in Story B.p. Note: `pyve testenv …` is a deprecated alias
for `pyve env …` under 3.0.6, removed in v4.0.)

---

## 4. Environment Inventory

### 4.0 Environment Surface Enumeration

```yaml
spec_version: "3.0"                 # Pyve-owned; matches the template version
project: modelfoundry
description: Compile a YAML recipe into a reproducible, framework-agnostic trained-model instance. Library/CLI; test-only repo.
envs:
  root:
    purpose: utility                # ad-hoc dev host: instantiate a ModelFoundry, run scripts
    backend: micromamba             # managed env (python=3.12.13 from environment.yml, conda-forge)
    default: false
    path: "."
    languages: [python]
    frameworks: [none]              # not a test surface; no test/lint frameworks
    packaging: none
    app_type: none                  # carries the importable library for ad-hoc runs, ships nothing
  testenv:
    purpose: test
    backend: micromamba             # inherits python=3.12.13 from environment.yml (conda-forge)
    default: true                   # the default/first (and only) test env
    path: "."
    languages: [python]
    frameworks: [pytest, ruff, mypy]
    packaging: none
    app_type: none
```

### 4.1 Inventory Table

| # | Environment name | Purpose | Backend | Default? | App type | Frameworks | Languages |
|---|------------------|---------|---------|----------|----------|------------|-----------|
| 0 | `root` (repo root) | `utility` | `micromamba` | no | `none` | `none` | `python` |
| 1 | `testenv` | `test` | `micromamba` | yes | `none` | `pytest`, `ruff`, `mypy` | `python` |

**Why this many test environments:** **One.** The pre-production release ships only the
PyTorch plugin and is **CPU-first** (the CIFAR-10 smoke is explicitly CPU-sized for free-tier
CI), so a single CPU `testenv` owns every test category — unit, integration, CLI, notebook
smoke, plugin-contract, property-based, lint, type-check, formatting, coverage, and the
packaging build-check. The **accelerator axis is real but deferred**: `Training.device`
participates in the canonical recipe bytes, so CPU / MPS / CUDA yield *distinct* ModelInstances
and the determinism contract is per-device — yet validating MPS/CUDA waits on the GPU CI it
requires, and the `[keras]` / `[huggingface]` **library axes are deferred extras** that no env
materializes today. Those become additional `test` envs (`testenv-mps`, `testenv-cuda`, a
keras/HF env, …) in a future env-spec revision when the feature or CI surface actually lands —
modeling them now would enumerate surfaces pyve cannot materialize. **Temp environments**
(templated, disposable per-run test sandboxes) are likewise deferred until a concrete,
declared workflow exists to enumerate (see §8).

---

## 5. Environment Specifications

### 5.0 Environment: `root` (purpose: `utility`)

- **Purpose (surface):** `utility` — the ad-hoc development host. A micromamba env carrying the
  editable `ml-modelfoundry` package + its runtime closure (incl. the PyTorch plugin) so a
  contributor or LLM can instantiate a `ModelFoundry` and run scripts (`pyve run python …`)
  without standing up the test env. It hosts **no test/dev tooling** (pytest / ruff / mypy) —
  that lives in `testenv`. Host orchestration tooling (`pyve`, `project-guide`, `git`,
  `direnv`, `asdf`) stays global.
- **Attributes:** app_type `none`; frameworks `none`; languages `python`; packaging `none`.
- **Backend & rationale:** `micromamba` — `environment.yml` pins `python=3.12.13` from
  conda-forge; using the same managed backend as `testenv` keeps the interpreter + ML stack
  consistent across both envs. (`none` is reserved for languages with no managed-env concept;
  Python has micromamba, so the root is a managed env, not bare OS.)
- **Language runtime / pins:** Python `3.12.13` — source: `environment.yml` (conda-forge);
  consistent with `.tool-versions`.
- **Bootstrap (one-time):**
  ```bash
  pyve env init --env root --backend micromamba   # .pyve/envs/root/conda from environment.yml
  pyve run pip install -e ".[pytorch]"             # editable package + runtime closure (CPU) for ad-hoc runs
  ```
- **Install dependencies:** the editable package + its runtime closure (no dev/test tooling).
- **Managed dependencies (`pip` / `conda`):**

  | Package | Version pin | Source class | Purpose |
  |---------|-------------|--------------|---------|
  | `python` | `==3.12.13` | `conda` | Interpreter (conda-forge, `environment.yml`). |
  | `pip` | (latest) | `conda` | In-env installer for the editable package + PyPI deps. |
  | `ml-modelfoundry[pytorch]` | editable (`-e .`) | `pip` (`pyproject.toml`) | Importable package + runtime closure for ad-hoc instantiation / scripts (no test/dev tooling). |

- **System / external dependencies (`system` / `vendored` / `runtime`):**

  | Dependency | Version | Source class | Install method | Why not in the managed env |
  |------------|---------|--------------|----------------|----------------------------|
  | `pyve` | `3.0.6` | `system` | global (pipx/brew) | Orchestration tool; manages the envs, isn't one. |
  | `project-guide` | (current) | `system` | global | Workflow host; not a project dependency. |
  | `direnv`, `git` | (current) | `system` | brew / apt | Shell + VCS plumbing. |

- **Lock / reproducibility strategy:** `environment.yml` pins the interpreter (`pyve lock` →
  `conda-lock.yml`); host tooling versions are developer-global, not project-locked.
- **Verification (smoke test):**
  ```bash
  pyve run python --version        # → Python 3.12.13
  pyve run modelfoundry --version  # → modelfoundry <version>
  pyve --version                   # → pyve version 3.0.6
  ```
- **CI parity notes:** CI exercises the gates in `testenv`; the root utility env is a developer
  convenience and contributes no CI step of its own.

---

### 5.1 Environment: `testenv` (purpose: `test`)

- **Purpose (surface):** `test` — the single materialized environment; the default test env.
  Holds the editable `modelfoundry` package, the PyTorch plugin (CPU), and the dev/test
  tooling. Every test category executes here.
- **Attributes:** app_type `none`; frameworks `pytest`, `ruff`, `mypy`; languages `python`;
  packaging `none`.
- **Backend & rationale:** `micromamba` — `environment.yml` pins `python=3.12.13` from
  conda-forge for a byte-reproducible interpreter, and the ML stack (`torch` / `torchvision`)
  resolves cleanly on conda-forge across macOS (Apple Silicon, first-class) and Linux.
  `environment.yml` is its manifest, declared via `pyve.toml [env.testenv] manifest` (see §3
  config note).
- **Test categories covered:** unit, integration, CLI, notebook smoke, plugin-contract,
  Hypothesis property tests, lint, type-check, formatting, coverage, packaging build-check
  (CPU; see §6).
- **Language runtime / pins:** Python `3.12.13` — source: `environment.yml` (conda-forge);
  consistent with `.tool-versions`.
- **Bootstrap (one-time):**
  ```bash
  pyve env init testenv                          # .pyve/envs/testenv/conda from environment.yml
  ```
  `environment.yml` is wired as the testenv manifest via `pyve.toml` (`pyve_schema = "3.0"`):
  ```toml
  [env.testenv]
  purpose  = "test"
  default  = true
  backend  = "micromamba"
  manifest = "environment.yml"
  ```
- **Install dependencies:** `pyve env install` skips conda-backed envs in 3.0.6 (provisioning
  lands in a later pyve milestone), so pip installs run through `pyve env run`:
  ```bash
  pyve env run testenv -- pip install -e ".[pytorch]"   # editable package + base runtime + PyTorch plugin (CPU)
  pyve env run testenv -- pip install -r requirements-dev.txt   # dev/test tooling
  ```
- **Managed dependencies (`pip` / `conda`):**

  | Package | Version pin | Source class | Purpose |
  |---------|-------------|--------------|---------|
  | `python` | `==3.12.13` | `conda` | Interpreter (conda-forge, `environment.yml`). |
  | `pip` | (latest) | `conda` | In-env installer for the editable package + PyPI deps. |
  | `ml-modelfoundry[pytorch]` | editable (`-e .`) | `pip` (`pyproject.toml`) | Package under test + full runtime closure: `numpy`, `pandas`, `pyarrow`, `pyyaml`, `pydantic>=2`, `rich`, `typer`, `matplotlib`, `scikit-learn`, `optuna`, `pillow`, `ml-datarefinery`, plus `torch>=2.5` / `torchvision>=0.20` / `torchmetrics>=1.4` (CPU). Registers the `modelfoundry` console script. |
  | `ruff` | (unpinned) | `pip` (`requirements-dev.txt`) | Lint + format. |
  | `mypy` | (unpinned) | `pip` (`requirements-dev.txt`) | Strict type checking over `src` + `tests`. |
  | `pytest` | (unpinned) | `pip` (`requirements-dev.txt`) | Test runner (`pyve test`). |
  | `pytest-cov` | (unpinned) | `pip` (`requirements-dev.txt`) | Coverage; ≥95% on core invariant modules (TR-15). |
  | `hypothesis` | (unpinned) | `pip` (`requirements-dev.txt`) | Property tests: cache-identity invariants, augmentation semantic equivalence. |
  | `nbclient` | (unpinned) | `pip` (`requirements-dev.txt`) | Jupyter substrate-neutral smoke (TR-8). |
  | `ipykernel` | (unpinned) | `pip` (`requirements-dev.txt`) | Jupyter kernel for the notebook smoke. |
  | `types-pyyaml` | (unpinned) | `pip` (`requirements-dev.txt`) | mypy stubs for PyYAML. |
  | `build` | (unpinned) | `pip` (`requirements-dev.txt`) | `python -m build` sdist + wheel verification. |

- **System / external dependencies (`system` / `vendored` / `runtime`):**

  | Dependency | Version | Source class | Install method | Why not in the managed env |
  |------------|---------|--------------|----------------|----------------------------|
  | POSIX filesystem | n/a | `system` | OS | Atomic `os.replace` promote requires same-filesystem temp + final (FR-5). |
  | Synthesized DataRefinery fixtures | n/a | `vendored` (test fixture) | built by `tests/conftest.py` at test time | Generated in-process to mimic the vendor on-disk layout; not a provisioned dependency. |

- **Lock / reproducibility strategy:** `environment.yml` pins the interpreter and `pyve lock`
  produces `conda-lock.yml` for the conda layer; runtime PyPI deps are declared (ranges
  authoritative) in `pyproject.toml`; `requirements-dev.txt` enumerates the dev toolset
  (currently version-floating, acceptable pre-production per `tech-spec.md`). Pinning PyPI deps
  via pip-tools `--hash` is the post-production hardening path.
- **How to run the tests this env owns:**
  ```bash
  pyve test                                      # full pytest suite (unit + integration + cli + notebook + contract)
  pyve env run testenv -- ruff check src tests
  pyve env run testenv -- ruff format --check src tests
  pyve env run testenv -- mypy src tests
  ```
- **Verification (smoke test):**
  ```bash
  pyve env run testenv -- pytest --version && pyve env run testenv -- ruff --version && pyve env run testenv -- mypy --version
  pyve env run testenv -- modelfoundry --version
  ```
- **CI parity notes:** `.github/workflows/ci.yml` (planned per `tech-spec.md` § CI/CD) stands
  up this env and runs `ruff check` + `ruff format --check` + `mypy --strict` + `pyve test` +
  the CIFAR-10 smoke (TR-12) on every PR and push to `main`, on macOS (Apple Silicon) primary
  with Linux as a stretch matrix entry — all CPU.

---

## 6. Test Coverage Matrix

| Test category | Tooling | Owning environment | Covered? | Notes |
|---------------|---------|--------------------|----------|-------|
| Static analysis / lint | `ruff check` | `testenv` | yes | Rule set `E,F,B,I,UP,SIM,RUF`. |
| Type checking | `mypy --strict` | `testenv` | yes | Whole package; pydantic v2 plugin (QR-6). |
| Formatting | `ruff format --check` | `testenv` | yes | Single-tool lint+format. |
| Unit tests | `pytest` | `testenv` | yes | `tests/unit/` — recipe/cache/seeding/plugin invariants. |
| Integration tests | `pytest` | `testenv` | yes | `tests/integration/` — e2e materialize, determinism, loose-coupling, CIFAR-10 smoke (TR-12), CPU. |
| CLI tests | `pytest` (editable install) | `testenv` | yes | `tests/cli/` — per-verb smoke against console script. |
| Notebook smoke | `pytest` + `nbclient` / `ipykernel` | `testenv` | yes | `tests/notebook/` — substrate-neutral accessor check (TR-8). |
| Plugin-contract tests | `pytest` | `testenv` | yes | `tests/plugin_contract/` — Protocol exhaustiveness. |
| Property-based tests | `pytest` + `hypothesis` | `testenv` | yes | Cache-identity invariants; augmentation semantic equivalence. |
| Coverage | `pytest-cov` | `testenv` | yes | `coverage.xml` + terminal; Codecov upload deferred. |
| Packaging / distribution | `python -m build` (`build`) | `testenv` | yes | sdist + wheel build check; `build` ships in `requirements-dev.txt`. |
| GPU-accelerated tests (MPS / CUDA) | `pytest` (per-device) | *(future env)* | N-A | Deferred — needs GPU CI and `testenv-mps` / `testenv-cuda`; device participates in cache identity, so each is its own `test` env. |

**Completeness statement:** every test category the pre-production codebase requires is owned
by exactly one environment (`testenv`); no category is split across redundant environments and
none is missing. The `root` env (micromamba `utility`) owns no test category — it is the
ad-hoc development host. GPU-accelerated and alternate-library (keras/HF) categories are
out-of-scope-today and map to future `test` envs, not to a gap in the current set.

---

## 7. Reproducibility & Bootstrapping

```bash
# Fresh-clone → fully testable, from the repo root. Both envs are micromamba,
# declared in pyve.toml ([env.root] utility, [env.testenv] test).

# 1. Utility root (micromamba): the ad-hoc env to instantiate a ModelFoundry / run scripts.
pyve env init root                              # .pyve/envs/root/conda from environment.yml (python=3.12.13)
pyve run pip install -e ".[pytorch]"            # editable package + runtime closure (CPU)
#   (pyve, project-guide, direnv, git installed globally — not pyve-managed)

# 2. Test env (micromamba): the default test env, full dep + tool stack.
pyve env init testenv                           # .pyve/envs/testenv/conda from environment.yml
pyve env run testenv -- pip install -e ".[pytorch]"          # editable package + PyTorch plugin (CPU)
pyve env run testenv -- pip install -r requirements-dev.txt  # dev/test tooling
pyve lock                                        # freeze conda-lock.yml (conda layer)

# 3. System/vendored deps: none beyond Python 3.12.13 + a POSIX filesystem.
#    (DataRefinery test fixtures are synthesized by tests/conftest.py at test time.)

# 4. Verification smoke tests:
pyve test
pyve env run testenv -- ruff check src tests
pyve env run testenv -- mypy src tests
pyve run modelfoundry --version
```

- **Files that must be committed for reproducibility:** `pyproject.toml`, `pyve.toml` (the
  `[env.<name>]` env spec), `environment.yml`, `conda-lock.yml` (once generated by `pyve lock`),
  `requirements-dev.txt`, `.tool-versions`.
- **Files that must NOT be committed:** `.pyve/envs/`, `.env`, build artifacts
  (`dist/`, `build/`, `*.egg-info/`), and the materialized cache roots (`./models/`,
  `./data/`).

---

## 8. Backend Gaps & Pyve Change-Requests

| Need | In closed vocab? | Status today | Action |
|------|------------------|--------------|--------|
| micromamba utility root | yes (`micromamba`) | **implemented** | Materialized by pyve; no action. |
| micromamba test env | yes | **implemented** | Materialized by pyve; no action. |
| Per-accelerator test envs (MPS / CUDA) | yes (`test` + distinct dep closures) | **not modeled yet** | Add `testenv-mps` / `testenv-cuda` in a future env-spec revision when GPU CI lands. No vocab gap — device is expressed via the env's dependency closure (torch build) + advisory `manual_steps` / `require_min_version`, not a new backend. |
| Templated disposable test sandboxes | yes (`temp`) | **not modeled yet** | Enumerate a `temp` env once a concrete, declared, reproducible workflow exists (the `temp` purpose carries no materializing behavior today regardless). |

**None — the closed vocabulary covers all needs.** The backend in use (`micromamba`, both
envs) is implemented; the deferred surfaces above are expressible within the existing closed
vocabulary and need no Pyve change-request.

---

## 9. Change Log & Approval

| Date | Version | Author | Change | Status |
|------|---------|--------|--------|--------|
| `2026-06-11` | `0.1` | Michael Smith | Initial draft | `Draft` |
| `2026-06-12` | `0.2` | Michael Smith | Re-scoped root from bare-OS `none` to a micromamba `utility` env (two micromamba envs); pyve 3.0.6 / `pyve.toml` schema-3.0 mechanism; `pyve testenv`→`pyve env` (Story B.o) | `Draft` |
