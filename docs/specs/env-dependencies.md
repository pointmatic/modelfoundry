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

**Repo shape (orienting):** `modelfoundry` is a **library / CLI consumed by other applications** (it ships as the `ml-modelfoundry` wheel and is imported, e.g. inside nbfoundry lifecycle templates). The repo itself has **no production "run" surface** — its only purpose is development and testing. It therefore runs a **venv multi-env layout** declared in `pyve.toml` (`pyve_schema = "3.0"`): a `utility` **root** (the env you land in to instantiate a `ModelFoundry` and run scripts ad hoc), a light `default = true` **`testenv`** (ruff / mypy / pytest tooling — lint and format run here), and a set of **lazy** `test` envs carrying the heavyweight framework closures — **`smoke-pytorch`** (the full PyTorch stack, where the real test suite runs), **`smoke-tensorflow`** / **`smoke-huggingface`** (forward placeholders for the deferred framework smokes), and **`typecheck`** (the full type closure for `mypy --strict`). Every env uses `backend = venv`: on macOS arm64 every dependency is a pip wheel (torch MPS, Apple tf-macos/tf-metal, the HF stack), so conda buys nothing, and keeping the framework smokes isolated dodges the Metal SIGFAULT that co-resident native GPU stacks trigger in one process. See §4.

---

## 1. Document Metadata

| Field | Value |
|-------|-------|
| **Repo name** | `modelfoundry` (PyPI distribution `ml-modelfoundry`) |
| **Primary language(s)** | Python 3.12.13 (`requires-python = ">=3.12,<3.14"`) |
| **Pyve version** | `3.0.6` |
| **Doc status** | `Draft` |
| **Last updated** | `2026-06-15` |
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
  necessarily the app or the tests. **In this repo the root is a venv `utility` env**
  carrying the editable package + its runtime closure, so a contributor (or LLM) can
  instantiate a `ModelFoundry` and run scripts ad hoc; the dev/test tooling lives in
  `testenv` and the framework test stacks in the lazy smoke envs (see §5.0).
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
  - **Test-only repo** — the repo has no `run` (production) surface; it runs a venv multi-env
    layout — a `utility` **root** (editable package + runtime closure, for ad-hoc instantiation
    and scripts), a light `default` **`testenv`** (lint / format / type tooling), and lazy
    framework smokes (**`smoke-pytorch`** owns the real test suite; **`typecheck`** owns
    `mypy --strict`). See §4.
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

This repo uses the default **`venv`** backend for **every** materialized env — the `utility`
root, the light `testenv`, and the lazy `smoke-pytorch` / `smoke-tensorflow` /
`smoke-huggingface` / `typecheck` envs. No advisory backends and no container backends are in
use. The `none`, `micromamba`, and Node rows are retained as the closed-vocabulary reference.
See §8.

**Default-backend assumption:** any environment may benefit from the `venv` backend, and here
every env takes it. The reason **not** to use `micromamba` is concrete: on macOS arm64 (the
primary surface) every dependency — `torch` (MPS), Apple `tensorflow-macos` /
`tensorflow-metal`, and the HuggingFace stack — ships as a pip wheel, so a conda layer buys no
reproducibility the pip pins don't already provide, while keeping the framework smokes in
**separate venvs** is what prevents the Metal SIGFAULT that co-resident native GPU stacks
trigger in one process.

**Env-location & config note (pyve 3.0.6):** pyve 3.0.6 materializes environments under
`.pyve/envs/<name>/<backend>/` and reads the env spec from **`pyve.toml`** (`pyve_schema =
"3.0"`) via `[env.<name>]` tables; the v2.8 `[tool.pyve.testenvs]` table in `pyproject.toml` is
removed (superseded by `[env.<name>]`). Every env here is `backend = venv`, so each materializes
at `.pyve/envs/<name>/venv/`. `pyve.toml` declares six envs: `[env.root]` (`purpose =
"utility"`), the `default = true` `[env.testenv]` (`requirements = ["requirements-dev.txt"]`),
and the `lazy = true` `[env.smoke-pytorch]` / `[env.smoke-tensorflow]` /
`[env.smoke-huggingface]` / `[env.typecheck]`, each pointing at its own `requirements = [...]`
file (see §5). A **lazy** env materializes on first use rather than at `pyve init` time, so the
heavy framework closures are built only when a smoke actually runs. The pyve-managed `.envrc`
activates the root env.

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
    backend: venv
    default: false
    lazy: false
    path: "."
    languages: [python]
    frameworks: [none]              # not a test surface; no test/lint frameworks
    packaging: none
    app_type: none                  # carries the importable library for ad-hoc runs, ships nothing
  testenv:
    purpose: test                   # light default: lint + format (ruff); tooling from requirements-dev.txt
    backend: venv
    default: true                   # the default env for `pyve test` / `pyve env run testenv`
    lazy: false
    path: "."
    languages: [python]
    frameworks: [ruff, mypy, pytest]
    packaging: none
    app_type: none
  smoke-pytorch:
    purpose: test                   # the real test suite (+ notebook smoke); full torch closure
    backend: venv
    default: false
    lazy: true                      # materialized on first use, not at pyve init
    path: "."
    languages: [python]
    frameworks: [pytest]
    packaging: none
    app_type: none
  smoke-tensorflow:
    purpose: test                   # forward placeholder: deferred TF (F.c) / Keras (F.e) smokes
    backend: venv
    default: false
    lazy: true
    path: "."
    languages: [python]
    frameworks: [pytest]
    packaging: none
    app_type: none
  smoke-huggingface:
    purpose: test                   # forward placeholder: deferred HuggingFace smoke
    backend: venv
    default: false
    lazy: true
    path: "."
    languages: [python]
    frameworks: [pytest]
    packaging: none
    app_type: none
  typecheck:
    purpose: test                   # mypy --strict over src + tests; full type closure
    backend: venv
    default: false
    lazy: true
    path: "."
    languages: [python]
    frameworks: [mypy]
    packaging: none
    app_type: none
```

### 4.1 Inventory Table

| # | Environment name | Purpose | Backend | Default? | Lazy? | App type | Frameworks | Languages |
|---|------------------|---------|---------|----------|-------|----------|------------|-----------|
| 0 | `root` (repo root) | `utility` | `venv` | no | no | `none` | `none` | `python` |
| 1 | `testenv` | `test` | `venv` | yes | no | `none` | `ruff`, `mypy`, `pytest` | `python` |
| 2 | `smoke-pytorch` | `test` | `venv` | no | yes | `none` | `pytest` | `python` |
| 3 | `smoke-tensorflow` | `test` | `venv` | no | yes | `none` | `pytest` | `python` |
| 4 | `smoke-huggingface` | `test` | `venv` | no | yes | `none` | `pytest` | `python` |
| 5 | `typecheck` | `test` | `venv` | no | yes | `none` | `mypy` | `python` |

**Why this many environments:** **Six** (one `utility` + five `test`), split by *tool* and by
*framework closure* so each stays minimal and the native GPU stacks never co-reside:

- **`testenv`** (default, eager) is deliberately light — just the `requirements-dev.txt` tooling
  (ruff / mypy / pytest), so `pyve env run testenv -- ruff …` and `ruff format --check` run fast
  without building a framework stack. It carries no runtime closure, so the package's own test
  suite runs in `smoke-pytorch`, not here.
- **`smoke-pytorch`** (lazy) carries the full PyTorch + ModelFoundry runtime closure and is where
  the real suite runs (unit + integration + CLI + plugin-contract + property + notebook smoke +
  the CIFAR-10 capstone): `pyve test --env smoke-pytorch`.
- **`smoke-tensorflow`** / **`smoke-huggingface`** (lazy) are **declared placeholders** — their
  requirement files (`tests/integration/env/{tensorflow,huggingface}.txt`) are intentionally empty
  today and populate when the deferred TF (F.c) / Keras (F.e) / HuggingFace framework smokes land.
  They exist now so the topology is stable and a contributor sees where those stacks will live.
- **`typecheck`** (lazy) holds the full type closure (`-e .[pytorch]` + `requirements-dev.txt`) so
  `mypy --strict` resolves every import across `src` + `tests`; mypy *reads* (never runs) these
  deps, so torch and a future Keras/HF stack coexist here safely — unlike the runtime smokes that
  must stay isolated.

The **accelerator axis is real but deferred**: `Training.device` participates in the canonical
recipe bytes, so CPU / MPS / CUDA yield *distinct* ModelInstances and the determinism contract is
per-device — yet validating MPS/CUDA waits on the GPU CI it requires. Those become additional
`test` envs (`smoke-pytorch-mps`, `smoke-pytorch-cuda`, …) in a future env-spec revision when the
CI surface actually lands. **Temp environments** (templated, disposable per-run test sandboxes)
are likewise deferred until a concrete, declared workflow exists to enumerate (see §8).

---

## 5. Environment Specifications

### 5.0 Environment: `root` (purpose: `utility`)

- **Purpose (surface):** `utility` — the ad-hoc development host. A venv carrying the editable
  `ml-modelfoundry` package + its runtime closure (incl. the PyTorch plugin) so a contributor or
  LLM can instantiate a `ModelFoundry` and run scripts (`pyve run python …`) without standing up a
  test env. It hosts **no test/dev tooling** (pytest / ruff / mypy) — that lives in `testenv` and
  the smoke envs. Host orchestration tooling (`pyve`, `project-guide`, `git`, `direnv`, `asdf`)
  stays global.
- **Attributes:** app_type `none`; frameworks `none`; languages `python`; packaging `none`.
- **Backend & rationale:** `venv` (the default backend) — every dependency is a pip wheel on
  macOS arm64, so a conda layer would add nothing; `.tool-versions` pins the interpreter
  (`python 3.12.13`) and pip installs the editable package + extras per `pyproject.toml`.
- **Language runtime / pins:** Python `3.12.13` — source: `.tool-versions` (asdf), within the
  `requires-python = ">=3.12,<3.14"` range.
- **Bootstrap (one-time):**
  ```bash
  pyve env init root                   # .pyve/envs/root/venv (venv on the .tool-versions interpreter)
  pyve run pip install -e ".[pytorch]" # editable package + runtime closure (CPU) for ad-hoc runs
  ```
- **Install dependencies:** the editable package + its runtime closure (no dev/test tooling).
- **Managed dependencies (`pip`):**

  | Package | Version pin | Source class | Purpose |
  |---------|-------------|--------------|---------|
  | `ml-modelfoundry[pytorch]` | editable (`-e .`) | `pip` (`pyproject.toml`) | Importable package + runtime closure for ad-hoc instantiation / scripts (no test/dev tooling). |

- **System / external dependencies (`system` / `vendored` / `runtime`):**

  | Dependency | Version | Source class | Install method | Why not in the managed env |
  |------------|---------|--------------|----------------|----------------------------|
  | `python` | `3.12.13` | `runtime` | `asdf` (`.tool-versions`) | Interpreter the venv is built on. |
  | `pyve` | `3.0.6` | `system` | global (pipx/brew) | Orchestration tool; manages the envs, isn't one. |
  | `project-guide` | (current) | `system` | global | Workflow host; not a project dependency. |
  | `direnv`, `git` | (current) | `system` | brew / apt | Shell + VCS plumbing. |

- **Lock / reproducibility strategy:** `.tool-versions` pins the interpreter; runtime PyPI deps
  are declared (ranges authoritative) in `pyproject.toml`. Host tooling versions are
  developer-global, not project-locked.
- **Verification (smoke test):**
  ```bash
  pyve run python --version        # → Python 3.12.13
  pyve run modelfoundry --version  # → modelfoundry <version>
  pyve --version                   # → pyve version 3.0.6
  ```
- **CI parity notes:** CI exercises the gates in `testenv` (lint), `typecheck` (mypy), and
  `smoke-pytorch` (the suite); the root utility env is a developer convenience and contributes no
  CI step of its own.

---

### 5.1 Environment: `testenv` (purpose: `test`, default)

- **Purpose (surface):** `test` — the light, eager default env. Holds only the
  `requirements-dev.txt` tooling (ruff / mypy / pytest); **lint and format run here**. It carries
  no runtime closure (no torch, not even the editable package), so the package's own test suite
  runs in `smoke-pytorch` and `mypy --strict` runs in `typecheck`.
- **Attributes:** app_type `none`; frameworks `ruff`, `mypy`, `pytest`; languages `python`;
  packaging `none`.
- **Backend & rationale:** `venv` (default) — the dev tools are pure pip wheels; keeping this env
  free of the framework closure makes `pyve env run testenv -- ruff …` fast.
- **Test categories covered:** static analysis / lint (`ruff check`), formatting
  (`ruff format --check`). The runtime-dependent categories (unit / integration / CLI / notebook /
  contract / property / coverage / packaging) run in `smoke-pytorch`; strict type-checking runs in
  `typecheck` (see §6).
- **Language runtime / pins:** Python `3.12.13` — source: `.tool-versions` (asdf).
- **Bootstrap (one-time):**
  ```bash
  pyve env init testenv                                        # .pyve/envs/testenv/venv
  pyve env run testenv -- pip install -r requirements-dev.txt  # dev/test tooling
  ```
  Declared in `pyve.toml` (`pyve_schema = "3.0"`):
  ```toml
  [env.testenv]
  purpose      = "test"
  backend      = "venv"
  default      = true
  requirements = ["requirements-dev.txt"]
  ```
- **Managed dependencies (`pip`, from `requirements-dev.txt`):**

  | Package | Version pin | Source class | Purpose |
  |---------|-------------|--------------|---------|
  | `ruff` | (unpinned) | `pip` (`requirements-dev.txt`) | Lint + format (the categories this env owns). |
  | `mypy` | (unpinned) | `pip` (`requirements-dev.txt`) | Present here; the strict whole-repo run lives in `typecheck`. |
  | `pytest` | (unpinned) | `pip` (`requirements-dev.txt`) | Test-runner tooling (the framework suite runs in `smoke-pytorch`). |
  | `pytest-cov` | (unpinned) | `pip` (`requirements-dev.txt`) | Coverage plugin (`pyproject` addopts enables `--cov`). |
  | `hypothesis` | (unpinned) | `pip` (`requirements-dev.txt`) | Property-test tooling. |
  | `nbclient`, `ipykernel` | (unpinned) | `pip` (`requirements-dev.txt`) | Notebook-smoke tooling (the smoke itself runs in `smoke-pytorch`). |
  | `types-pyyaml` | (unpinned) | `pip` (`requirements-dev.txt`) | mypy stubs for PyYAML. |
  | `build` | (unpinned) | `pip` (`requirements-dev.txt`) | `python -m build` sdist + wheel verification. |

- **Lock / reproducibility strategy:** `requirements-dev.txt` enumerates the dev toolset (currently
  version-floating, acceptable pre-production per `tech-spec.md`); pinning via pip-tools `--hash`
  is the post-production hardening path.
- **How to run what this env owns:**
  ```bash
  pyve env run testenv -- ruff check src tests
  pyve env run testenv -- ruff format --check src tests
  ```
- **Verification (smoke test):**
  ```bash
  pyve env run testenv -- ruff --version && pyve env run testenv -- pytest --version
  ```
- **CI parity notes:** `.github/workflows/ci.yml` (planned per `tech-spec.md` § CI/CD) runs
  `ruff check` + `ruff format --check` here, `mypy --strict` in `typecheck`, and
  `pyve test --env smoke-pytorch` + the CIFAR-10 smoke (TR-12) in `smoke-pytorch`, on every PR and
  push to `main`, on macOS (Apple Silicon) primary with Linux as a stretch matrix entry — all CPU.

---

### 5.2 Environment: `smoke-pytorch` (purpose: `test`, lazy)

- **Purpose (surface):** `test` — the env where the **real test suite runs**: the editable package
  + the full PyTorch runtime closure + the test runner. Lazy, so it materializes on first use.
- **Attributes:** app_type `none`; frameworks `pytest`; languages `python`; packaging `none`.
- **Backend & rationale:** `venv` — `torch` / `torchvision` / `torchmetrics` (and the MPS build on
  Apple Silicon) are pip wheels; isolating the torch closure in its own venv keeps it off the
  other framework smokes (Metal SIGFAULT avoidance).
- **Test categories covered:** unit, integration, CLI, notebook smoke (TR-8), plugin-contract,
  Hypothesis property tests, coverage, and the CIFAR-10 capstone (TR-12) — all CPU (see §6).
- **Bootstrap (one-time):**
  ```bash
  pyve env init smoke-pytorch                                    # .pyve/envs/smoke-pytorch/venv
  pyve env run smoke-pytorch -- pip install -r tests/integration/env/pytorch.txt
  ```
  Declared in `pyve.toml`:
  ```toml
  [env.smoke-pytorch]
  purpose      = "test"
  backend      = "venv"
  requirements = ["tests/integration/env/pytorch.txt"]
  lazy         = true
  ```
- **Managed dependencies (`pip`, from `tests/integration/env/pytorch.txt`):**

  | Package | Version pin | Source class | Purpose |
  |---------|-------------|--------------|---------|
  | `ml-modelfoundry[pytorch,notebook-smokes]` | editable (`-e .`) | `pip` (`pyproject.toml`) | Package under test + full runtime closure (`numpy`, `pandas`, `pyarrow`, `pyyaml`, `pydantic>=2`, `rich`, `typer`, `matplotlib`, `scikit-learn`, `optuna`, `pillow`, `ml-datarefinery`, `torch` / `torchvision` / `torchmetrics` / `torchinfo`) + the notebook-smoke extra (`nbclient` / `ipykernel`). Registers the `modelfoundry` console script. |
  | `pytest`, `pytest-cov`, `hypothesis` | (unpinned) | `pip` | Test runner + coverage + property tests (`pytest-cov` is required because `pyproject` addopts enables `--cov`). |

- **System / external dependencies (`system` / `vendored` / `runtime`):**

  | Dependency | Version | Source class | Install method | Why not in the managed env |
  |------------|---------|--------------|----------------|----------------------------|
  | POSIX filesystem | n/a | `system` | OS | Atomic `os.replace` promote requires same-filesystem temp + final (FR-5). |
  | Synthesized DataRefinery fixtures | n/a | `vendored` (test fixture) | built by `tests/conftest.py` at test time | Generated in-process to mimic the vendor on-disk layout; not a provisioned dependency. |

- **How to run the tests this env owns:**
  ```bash
  pyve test --env smoke-pytorch                  # the real suite (plain `pyve test` targets the light testenv)
  pyve test --env smoke-pytorch tests/integration/test_cifar10_smoke.py
  ```
- **Verification (smoke test):**
  ```bash
  pyve env run smoke-pytorch -- python -c "import torch, modelfoundry; print(torch.__version__, modelfoundry.__version__)"
  ```

---

### 5.3 Environment: `smoke-tensorflow` (purpose: `test`, lazy) — declared placeholder

- **Purpose (surface):** `test` — the home for the **deferred** TensorFlow / Keras framework smoke
  (serves F.c's TF and F.e's bundled Keras work). **Declared but empty today:** its requirements
  file `tests/integration/env/tensorflow.txt` is an intentional placeholder, so nothing
  materializes until that work lands.
- **Attributes:** app_type `none`; frameworks `pytest`; languages `python`; packaging `none`.
- **Backend & rationale:** `venv` — Apple `tensorflow-macos` / `tensorflow-metal` are pip wheels;
  the env stays isolated so the Metal TF stack never co-resides with the Metal torch stack.
- **Bootstrap:** deferred — populate `tests/integration/env/tensorflow.txt` (`-e .[keras]` + test
  runner) when the TF/Keras smoke is implemented, then `pyve env init smoke-tensorflow`.
- **Declared in `pyve.toml`:** `[env.smoke-tensorflow]` (`backend = venv`, `requirements =
  ["tests/integration/env/tensorflow.txt"]`, `lazy = true`).

---

### 5.4 Environment: `smoke-huggingface` (purpose: `test`, lazy) — declared placeholder

- **Purpose (surface):** `test` — the home for the **deferred** HuggingFace framework smoke.
  **Declared but empty today:** `tests/integration/env/huggingface.txt` is an intentional
  placeholder.
- **Attributes:** app_type `none`; frameworks `pytest`; languages `python`; packaging `none`.
- **Backend & rationale:** `venv` — the transformers / datasets / peft / torch stack is pip-wheel
  installable; isolation keeps it off the other smokes.
- **Bootstrap:** deferred — populate `tests/integration/env/huggingface.txt` (`-e .[huggingface]` +
  test runner) when the HF smoke is implemented, then `pyve env init smoke-huggingface`.
- **Declared in `pyve.toml`:** `[env.smoke-huggingface]` (`backend = venv`, `requirements =
  ["tests/integration/env/huggingface.txt"]`, `lazy = true`).

---

### 5.5 Environment: `typecheck` (purpose: `test`, lazy)

- **Purpose (surface):** `test` — the **full type closure** for `mypy --strict` over `src` +
  `tests`. Lazy; materialized on first type-check.
- **Attributes:** app_type `none`; frameworks `mypy`; languages `python`; packaging `none`.
- **Backend & rationale:** `venv` — combines `-e .[pytorch]` (the only framework imported at module
  scope today; add `.[…,huggingface,keras]` as those plugins land) with `requirements-dev.txt`
  (mypy + stubs + the tooling whose imports `tests/` use). mypy **reads** (never runs) these deps,
  so torch and a future Keras/HF stack coexist here safely — unlike the runtime smokes.
- **Bootstrap (one-time):**
  ```bash
  pyve env init typecheck                                       # .pyve/envs/typecheck/venv
  pyve env run typecheck -- pip install -r requirements-typecheck.txt
  ```
  Declared in `pyve.toml`: `[env.typecheck]` (`backend = venv`, `requirements =
  ["requirements-typecheck.txt"]`, `lazy = true`).
- **Managed dependencies (`pip`, from `requirements-typecheck.txt`):** `-e .[pytorch]` +
  `-r requirements-dev.txt` (the full import closure mypy must resolve).
- **How to run what this env owns:**
  ```bash
  pyve env run typecheck -- mypy src tests
  ```
- **Verification (smoke test):**
  ```bash
  pyve env run typecheck -- mypy --version
  ```

---

## 6. Test Coverage Matrix

| Test category | Tooling | Owning environment | Covered? | Notes |
|---------------|---------|--------------------|----------|-------|
| Static analysis / lint | `ruff check` | `testenv` | yes | Rule set `E,F,B,I,UP,SIM,RUF,D`. |
| Formatting | `ruff format --check` | `testenv` | yes | Single-tool lint+format. |
| Type checking | `mypy --strict` | `typecheck` | yes | Whole package; pydantic v2 plugin (QR-6); full type closure. |
| Unit tests | `pytest` | `smoke-pytorch` | yes | `tests/unit/` — recipe/cache/seeding/plugin invariants. |
| Integration tests | `pytest` | `smoke-pytorch` | yes | `tests/integration/` — e2e materialize, determinism, loose-coupling, CIFAR-10 smoke (TR-12), CPU. |
| CLI tests | `pytest` (editable install) | `smoke-pytorch` | yes | `tests/cli/` — per-verb smoke against console script. |
| Notebook smoke | `pytest` + `nbclient` / `ipykernel` | `smoke-pytorch` | yes | `tests/notebook/` — substrate-neutral accessor check (TR-8). |
| Plugin-contract tests | `pytest` | `smoke-pytorch` | yes | `tests/plugin_contract/` — Protocol exhaustiveness. |
| Property-based tests | `pytest` + `hypothesis` | `smoke-pytorch` | yes | Cache-identity invariants; augmentation semantic equivalence. |
| Coverage | `pytest-cov` | `smoke-pytorch` | yes | `coverage.xml` + terminal; Codecov upload deferred. |
| Packaging / distribution | `python -m build` (`build`) | `testenv` | yes | sdist + wheel build check; `build` ships in `requirements-dev.txt`. |
| TF / Keras / HuggingFace smokes | `pytest` (per-framework) | `smoke-tensorflow` / `smoke-huggingface` | N-A | Declared placeholders; requirement files empty until the deferred F.c (TF) / F.e (Keras) / HF smokes land. |
| GPU-accelerated tests (MPS / CUDA) | `pytest` (per-device) | *(future env)* | N-A | Deferred — needs GPU CI and `smoke-pytorch-mps` / `smoke-pytorch-cuda`; device participates in cache identity, so each is its own `test` env. |

**Completeness statement:** every test category the pre-production codebase requires is owned
by exactly one environment — lint/format in `testenv`, strict typing in `typecheck`, and the
runtime-dependent categories in `smoke-pytorch`; no category is split across redundant
environments and none is missing. The `root` env (venv `utility`) owns no test category — it is
the ad-hoc development host. The TF/Keras/HF smokes (declared-but-empty `smoke-tensorflow` /
`smoke-huggingface`) and the GPU-accelerated categories are out-of-scope-today and map to those
already-declared (or future) `test` envs, not to a gap in the current set.

---

## 7. Reproducibility & Bootstrapping

```bash
# Fresh-clone → fully testable, from the repo root. All envs are venv,
# declared in pyve.toml ([env.root] utility; [env.testenv] test default;
# lazy [env.smoke-pytorch] / [env.smoke-tensorflow] / [env.smoke-huggingface] / [env.typecheck]).

# 1. Utility root (venv): the ad-hoc env to instantiate a ModelFoundry / run scripts.
pyve env init root                              # .pyve/envs/root/venv (python 3.12.13 from .tool-versions)
pyve run pip install -e ".[pytorch]"            # editable package + runtime closure (CPU)
#   (pyve, project-guide, direnv, git installed globally — not pyve-managed)

# 2. Light testenv (venv, eager default): lint + format tooling.
pyve env init testenv                           # .pyve/envs/testenv/venv
pyve env run testenv -- pip install -r requirements-dev.txt   # ruff / mypy / pytest tooling

# 3. smoke-pytorch (venv, lazy): the env the real test suite runs in.
pyve env init smoke-pytorch                      # .pyve/envs/smoke-pytorch/venv
pyve env run smoke-pytorch -- pip install -r tests/integration/env/pytorch.txt

# 4. typecheck (venv, lazy): full type closure for mypy --strict.
pyve env init typecheck                          # .pyve/envs/typecheck/venv
pyve env run typecheck -- pip install -r requirements-typecheck.txt
#   (smoke-tensorflow / smoke-huggingface are declared placeholders — their requirement
#    files are empty until the deferred TF / Keras / HF smokes land; nothing to init yet.)

# 5. System/vendored deps: none beyond Python 3.12.13 + a POSIX filesystem.
#    (DataRefinery test fixtures are synthesized by tests/conftest.py at test time.)

# 6. Verification smoke tests:
pyve test --env smoke-pytorch                   # the real suite (plain `pyve test` targets the light testenv)
pyve env run testenv -- ruff check src tests
pyve env run typecheck -- mypy src tests
pyve run modelfoundry --version
```

- **Files that must be committed for reproducibility:** `pyproject.toml`, `pyve.toml` (the
  `[env.<name>]` env spec), `requirements-dev.txt`, `requirements-typecheck.txt`,
  `tests/integration/env/*.txt`, `.tool-versions`.
- **Files that must NOT be committed:** `.pyve/envs/`, `.env`, build artifacts
  (`dist/`, `build/`, `*.egg-info/`), and the materialized cache roots (`./models/`,
  `./data/`).

---

## 8. Backend Gaps & Pyve Change-Requests

| Need | In closed vocab? | Status today | Action |
|------|------------------|--------------|--------|
| venv utility root | yes (`venv`) | **implemented** | Materialized by pyve; no action. |
| venv test envs (`testenv`, `smoke-pytorch`, `typecheck`) | yes (`venv`) | **implemented** | Materialized by pyve; the lazy ones build on first use; no action. |
| Lazy per-framework smokes (TF / Keras / HF) | yes (`test` + distinct dep closures) | **declared, empty** | `smoke-tensorflow` / `smoke-huggingface` are declared in `pyve.toml` with empty requirement files; populate them when the deferred F.c (TF) / F.e (Keras) / HF smokes land. No vocab gap. |
| Per-accelerator test envs (MPS / CUDA) | yes (`test` + distinct dep closures) | **not modeled yet** | Add `smoke-pytorch-mps` / `smoke-pytorch-cuda` in a future env-spec revision when GPU CI lands. No vocab gap — device is expressed via the env's dependency closure (torch build) + advisory `manual_steps` / `require_min_version`, not a new backend. |
| Templated disposable test sandboxes | yes (`temp`) | **not modeled yet** | Enumerate a `temp` env once a concrete, declared, reproducible workflow exists (the `temp` purpose carries no materializing behavior today regardless). |

**None — the closed vocabulary covers all needs.** The backend in use (`venv`, every env) is
implemented; the deferred surfaces above are expressible within the existing closed vocabulary
and need no Pyve change-request.

---

## 9. Change Log & Approval

| Date | Version | Author | Change | Status |
|------|---------|--------|--------|--------|
| `2026-06-11` | `0.1` | Michael Smith | Initial draft | `Draft` |
| `2026-06-12` | `0.2` | Michael Smith | Re-scoped root from bare-OS `none` to a micromamba `utility` env (two micromamba envs); pyve 3.0.6 / `pyve.toml` schema-3.0 mechanism; `pyve env` verb (Story B.o) | `Draft` |
| `2026-06-15` | `0.3` | Michael Smith | Reconciled to the **venv multi-env** layout — `root` / light `testenv` + lazy `smoke-pytorch` / `smoke-tensorflow` / `smoke-huggingface` / `typecheck` (all `backend = venv`); supersedes the B.o/B.p two-micromamba design (Story F.b.1) | `Draft` |
