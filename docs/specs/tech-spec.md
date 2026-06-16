# tech-spec.md -- ModelFoundry (Python 3.12.x)

This document defines **how** the `ModelFoundry` project is built -- architecture, module layout, dependencies, data models, API signatures, and cross-cutting concerns.

For requirements and behavior, see [`features.md`](features.md). For motivation and scope, see [`concept.md`](concept.md). For the implementation plan, see [`stories.md`](stories.md). For project-specific must-know facts (workflow rules, architecture quirks, hidden coupling), see [`project-essentials.md`](project-essentials.md) — `plan_tech_spec` populates it after this document is approved. For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

For the upstream contract ModelFoundry consumes (DataRefinery as vendor), see [`datarefinery/vendor-dependency-spec.md`](datarefinery/vendor-dependency-spec.md). For the downstream contract ModelFoundry honors when consumed indirectly through nbfoundry lifecycle templates, see [`nbfoundry/consumer-dependency-spec.md`](nbfoundry/consumer-dependency-spec.md).

---

## Runtime & Tooling

| Concern | Choice | Notes |
|---|---|---|
| **Language** | Python 3.12.x | Pinned via `asdf` / `pyve`. Use `python`, never `python3`, to honor the `asdf` shim. |
| **`requires-python`** (pyproject.toml) | `>=3.12,<3.14` | PyPI-friendly range. The exact `python 3.12.13` pin lives in `.tool-versions` (asdf; env reproducibility). The `3.14` ceiling protects against ML-stack incompatibilities seen in adjacent projects. |
| **Environment manager** | `pyve` (venv backend) | A venv multi-env layout in `pyve.toml` (schema 3.0): a `purpose = "utility"` **root** (`.pyve/envs/root/venv`, ad-hoc runs / scripts), a light `default = true` **`testenv`** (ruff / mypy / pytest tooling — lint + format), and lazy **`smoke-pytorch`** (the full torch closure, where the suite runs), **`smoke-tensorflow`** / **`smoke-huggingface`** (declared placeholders), and **`typecheck`** (`mypy --strict` closure). All `backend = venv`. See [`env-dependencies.md`](env-dependencies.md) for the authoritative env spec and `project-essentials.md` § Pyve Essentials. |
| **Build backend** | `hatchling` | Configured via `pyproject.toml`; no `setup.py`. |
| **Package layout** | `src/` layout (`src/modelfoundry/...`) | Forces tests against the *installed* package, surfaces packaging bugs that flat layout hides. Mirrors DataRefinery and nbfoundry. |
| **Linter / formatter** | `ruff` (check + format) | Single tool covers lint + format. Default rule set + `B`, `I`, `UP`, `SIM`, `RUF`. |
| **Type checker** | `mypy --strict` over the **whole package** | Per `features.md` QR-6; pydantic v2 mypy plugin auto-loaded; `py.typed` marker ships in the wheel. |
| **Test runner** | `pytest` + `pytest-cov` + `hypothesis` | Run via `pyve test --env smoke-pytorch` (the full closure); never bare `pytest`. Plain `pyve test` targets the light `testenv`. See § Two-environment install below. |
| **CLI framework** | `typer` | Mirrors DataRefinery and nbfoundry. Built on click; migration path stays open. |
| **Editable install** | Testenv editable install required | Tests exercise CLI entry points; `pythonpath` alone does not register console scripts. |
| **Pre-commit hooks** | **Not used in the pre-production series**; CI gates only | Vendored hook envs drift from project Python; revisit if drift becomes painful. |
| **Versioning** | Semver — start at `0.1.0`; large minor versions allowed (`0.11.x`, `0.167.x`); `1.0.0` reserved for stable, production-quality, feature-complete release | Matches nbfoundry's policy. The `1.0.0` event is the production-release transition referenced by `features.md` CR-1 / OR-8 / OR-9 / OR-10. |
| **License** | Apache-2.0 (SPDX `Apache-2.0`); copyright Pointmatic | `features.md` SC-1; header on every new source file (see `project-essentials.md` § File header conventions). |

**Canonical command forms** (developer-facing — the LLM uses `pyve run` wrappers when invoking from the Bash tool, see `project-essentials.md`):

```bash
project-guide mode plan_stories                       # change mode after this spec is approved
pyve test --env smoke-pytorch                         # run the full test suite (torch closure)
pyve env run testenv -- ruff check src tests
pyve env run testenv -- ruff format --check src tests
pyve env run typecheck -- mypy src tests
```

### Multi-environment install

A venv multi-env layout is declared in `pyve.toml` (schema 3.0) — see [`env-dependencies.md`](env-dependencies.md) for the authoritative spec. The `utility` **root** carries the editable package for ad-hoc runs; the light `default` **`testenv`** holds the lint/format tooling; lazy **`smoke-pytorch`** carries the package + PyTorch plugin and owns the suite; lazy **`typecheck`** carries the full type closure for `mypy --strict`. Because this project ships a **CLI** (`modelfoundry`), `smoke-pytorch` does an editable install so its console-script entry points resolve. (Each env is `backend = venv`; provisioning runs through `pyve env run` per its `requirements` file.)

```bash
pyve env init root                                                # utility root: .pyve/envs/root/venv
pyve run pip install -e ".[pytorch]"                             # editable package + runtime closure (root)
pyve env init testenv                                             # light test env: .pyve/envs/testenv/venv
pyve env run testenv -- pip install -r requirements-dev.txt       # lint/format/test tooling
pyve env init smoke-pytorch                                       # suite env (lazy): .pyve/envs/smoke-pytorch/venv
pyve env run smoke-pytorch -- pip install -r tests/integration/env/pytorch.txt  # editable pkg + torch closure
pyve env init typecheck                                           # type-check env (lazy): .pyve/envs/typecheck/venv
pyve env run typecheck -- pip install -r requirements-typecheck.txt             # full mypy closure
```

### Invocation rules (LLM-internal vs. developer-facing)

Per `docs/project-guide/go.md` § Pyve Essentials, the LLM wraps its own Bash-tool commands with `pyve run` (e.g. `pyve run python -m modelfoundry.cli ...`); developer-facing command quotations use the bare form (e.g. `modelfoundry materialize ...`). Always `python`, never `python3`.

---

## Dependencies

### Runtime (declared in `pyproject.toml [project] dependencies`)

| Package | Purpose |
|---|---|
| `numpy` | Numerical primitives (predictions, confusion matrices, metric inputs). |
| `pandas` | Tabular surfaces (training history, optimization trials, predictions DataFrame). |
| `pyarrow` | Parquet I/O for `training/history.parquet`, `optimization/trials.parquet`, `evaluation/predictions.parquet`, `evaluation/calibration.parquet`. |
| `pyyaml` | Recipe parsing (`yaml.safe_load`). |
| `pydantic` (`>=2`) | Recipe model, manifest, runtime config; provides canonical-form intermediate via `model_dump(mode="json")` for cache identity (FR-4). |
| `rich` | User-facing CLI output: per-epoch tables, per-trial progress bars, summary panels. |
| `typer` | CLI framework. |
| `matplotlib` | Reporting-mode visualizations (`training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid`). Stays in core because reporting visualizations run at materialize time; gating behind an extra would surprise users whose recipes declare a visualization. |
| `scikit-learn` | Metric implementations shared across plugins (`f1_score`, `confusion_matrix`, `calibration_curve`); also the implementation library for the sklearn stub plugin. |
| `optuna` | Hyperparameter-search backend. Recipes never name Optuna; the plugin's Optimization-trial harness uses `TPESampler` / `RandomSampler` / `GridSampler` and `MedianPruner` internally. |
| `pillow` | Image decoding for the PyTorch plugin's `DataRefineryDataset` adapter (reads `path` / `image_path` from DataRefinery's JSONL records). |
| `ml-datarefinery` | Vendor library. ModelFoundry imports `datarefinery` to resolve the bound `Data:` block (FR-6) — DataRefinery's library API gives canonical-hash resolution, manifest reading, and split / label-schema introspection. |

### Optional extras

| Extra | Pulls In | Purpose |
|---|---|---|
| `[pytorch]` | `torch>=2.5`, `torchvision>=0.20`, `torchmetrics>=1.4` | The default plugin. CIFAR-10 baseline architecture vocabulary (`Conv2d`, `BatchNorm2d`, `Linear`, `MLP`, `ConvBlock`, `ResidualBlock`, `simple_cnn`, `resnet8`, `resnet20`), Training loop, Evaluation metric implementations, Visualization rendering. The first pre-production release ships this extra end-to-end. |
| `[sklearn]` | (already in base) | The stub plugin; registers the full `OperationSpec` set against shared sklearn metric implementations but raises `PluginError` at `materialize()` (FR-24). The extra is documented for symmetry but installs nothing extra. |
| `[huggingface]` | `transformers>=4.40`, `peft>=0.10`, `evaluate>=0.4` | **Deferred** — close follow-on cycle, not the first pre-production release. The recipe shape's optional pretrained-encoder + LoRA path (FR-7) references this. |
| `[keras]` | `tensorflow>=2.16`, `keras>=3.0` | **Deferred** — close follow-on cycle. Keras 3 ships bundled with TF 2.16+ via `tf.keras`. |
| `[llm]` | `lmentry` | **Deferred** — close follow-on cycle. Reserved for a future LLM-enhancement layer in the `init` scaffolder (FR-21) covering interpretive judgments like baseline-model recommendation. Namespace claimed for forward compatibility; no implementation in the pre-production series. The deterministic init path covers all pre-production scaffolding needs. |
| `[notebook-smokes]` | `nbclient`, `ipykernel` | Dev-time only; powers the Jupyter substrate-neutral smoke (TR-8). Not part of the runtime contract. |

### Development (`requirements-dev.txt`, installed into testenv only)

| Package | Purpose |
|---|---|
| `ruff` | Lint + format. |
| `mypy` | Strict type checking. |
| `pytest` | Test runner. |
| `pytest-cov` | Coverage measurement; fail-under 95 on core invariant modules (TR-15). |
| `hypothesis` | Property-based tests for cache-identity invariants, semantic-equivalence between lazy and aggressive augmentation realizers (Q4 from plan_tech_spec). |
| `nbclient` | Jupyter substrate-neutral smoke (TR-8). |
| `ipykernel` | Jupyter kernel for the above. |
| `types-pyyaml` | mypy stubs. |
| `build` | `python -m build` for sdist + wheel. |

### System

None beyond Python 3.12.x and a POSIX-compatible filesystem (macOS first-class pre-production; Linux best-effort pre-production, first-class post-production; Windows via WSL2). `os.replace` cross-device-rename limitation is documented in FR-5.

---

## Package Structure

Source layout, with one-line descriptions per file:

```
modelfoundry/                                       # repo root
├── pyproject.toml                                  # build backend (hatchling), deps, console script, ruff/mypy/pytest config
├── pyve.toml                                        # pyve 3.0 env spec: [env.root] utility + light [env.testenv] + lazy [env.smoke-*] / [env.typecheck] (all venv)
├── requirements-dev.txt                            # dev tools for the light testenv (ruff, mypy, pytest, pytest-cov, hypothesis, nbclient, ipykernel, types-pyyaml, build)
├── requirements-typecheck.txt                      # full mypy --strict closure for [env.typecheck] (-e .[pytorch] + requirements-dev.txt)
├── tests/integration/env/pytorch.txt               # [env.smoke-pytorch] deps: editable pkg + torch closure + pytest (the real suite env)
├── README.md                                       # quickstart: install, CIFAR-10 walkthrough, library + CLI usage
├── LICENSE                                         # Apache-2.0
├── .github/
│   └── workflows/
│       ├── ci.yml                                  # ruff + mypy --strict (typecheck) + pyve test --env smoke-pytorch (incl. CIFAR-10 smoke) on PRs and main (macOS primary, Linux stretch)
│       └── publish.yml                             # PyPI Trusted Publishing on tagged releases (v*.*.*)
├── src/
│   └── modelfoundry/
│       ├── __init__.py                             # public API re-exports: ModelFoundry, ModelInstance, materialize, ModelfoundryError, __version__
│       ├── __main__.py                             # `python -m modelfoundry` -> cli.app:app
│       ├── _version.py                             # single source of truth for the version string
│       ├── py.typed                                # PEP 561 marker (ships in wheel)
│       ├── logging.py                              # JsonFormatter + get_logger("modelfoundry") helper
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── app.py                              # root typer.Typer instance, shared options, exit-code mapping
│       │   └── commands/
│       │       ├── __init__.py
│       │       ├── init_cmd.py                     # `init` verb (FR-21)
│       │       ├── validate_cmd.py                 # `validate` verb (FR-2)
│       │       ├── check_cmd.py                    # `check` verb (FR-19)
│       │       ├── status_cmd.py                   # `status` verb (FR-16)
│       │       ├── materialize_cmd.py              # `materialize` verb (FR-3)
│       │       ├── report_cmd.py                   # `report` verb (FR-18)
│       │       ├── inspect_cmd.py                  # `inspect` verb (FR-17)
│       │       └── clean_cmd.py                    # `clean` verb (FR-20)
│       ├── core/
│       │   ├── __init__.py
│       │   ├── modelfoundry.py                     # ModelFoundry class (entry-point class for library callers)
│       │   ├── instance.py                         # ModelInstance frozen dataclass + notebook-shaped accessors (FR-22)
│       │   ├── config.py                           # RuntimeConfig (cache_root, data_cache_root, log_level, plugin_path, variant, seed)
│       │   ├── manifest.py                         # Manifest pydantic model + JSON I/O
│       │   └── errors.py                           # ModelfoundryError hierarchy (FR-feature-map: BR-10 from consumer-dep-spec)
│       ├── recipe/
│       │   ├── __init__.py
│       │   ├── models.py                           # pydantic v2 ModelRecipe + per-section sub-models
│       │   ├── loader.py                           # FR-1 load + schema-version gate
│       │   ├── validator.py                        # FR-2 enumerated checks 1–19
│       │   ├── canonical.py                        # JSON-canonical bytes for cache identity (FR-4)
│       │   ├── variants.py                         # FR-14 variant overlay
│       │   └── search_space.py                     # FR-11 Optimization.search_space resolution + recipe-path injection
│       ├── cache/
│       │   ├── __init__.py
│       │   ├── identity.py                         # FR-4 cache key: SHA-256 over canonical recipe + bound DataRefinery instance hash + seed
│       │   ├── layout.py                           # CachePaths helpers under <cache-root>
│       │   ├── atomic.py                           # FR-5 temp-then-promote (os.replace), FAILED marker, trash on --overwrite
│       │   └── cleaner.py                          # FR-20 selectors, listing, removal
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── runner.py                           # MaterializeRunner: stage sequencing (Architecture → Optimization → Training → Evaluation → Expectations → Visualizations → manifest → promote)
│       │   ├── data_binding.py                     # FR-6 DataRefinery instance resolution + cross-validation against the recipe
│       │   ├── expectations.py                     # FR-15 OutputExpectations evaluator
│       │   ├── seeding.py                          # FR-25 master seed → per-stage seeds (Optuna sampler seed, DataLoader worker seeds, dropout RNG)
│       │   └── checkpoint.py                       # plugin-agnostic Checkpoint I/O (forward-extensible dict-based format; see § Checkpoint format below)
│       ├── plugins/
│       │   ├── __init__.py
│       │   ├── base.py                             # Plugin protocol + OperationSpec + Trainer / Evaluator / Optimizer protocols
│       │   ├── discovery.py                        # entry-point + plugin-path discovery
│       │   ├── pytorch/
│       │   │   ├── __init__.py
│       │   │   ├── plugin.py                       # end-to-end PyTorch plugin (CIFAR-10 image-classification scope)
│       │   │   ├── architecture.py                 # CNN primitives + composite + baseline architectures (FR-ARCH-1)
│       │   │   ├── losses.py                       # cross_entropy / cross_entropy_class_weighted / bce_with_logits (FR-LOSS-1)
│       │   │   ├── optimizers.py                   # adamw / sgd / adam (FR-OPT-1)
│       │   │   ├── schedules.py                    # reduce_on_plateau / cosine / linear_warmup (FR-OPT-2)
│       │   │   ├── trainer.py                      # Training-loop implementation; honors deterministic-algorithm mode + worker_init_fn (QR-3)
│       │   │   ├── optimization.py                 # Optuna-backed Optimization stage; baseline_trial enqueue; n_jobs=1
│       │   │   ├── evaluation.py                   # metric implementations via torchmetrics; baseline-model resolution
│       │   │   ├── visualizations.py               # matplotlib renderers for the v0.x viz vocabulary
│       │   │   ├── data.py                         # DataRefineryDataset adapter (reads JSONL + sidecar PNG; lazy-augmentation realization via torchvision.transforms.v2)
│       │   │   ├── augmentations.py                # Lazy augmentation realizers (random_crop, horizontal_flip, color_jitter, random_erasing) over torchvision.transforms.v2
│       │   │   ├── persistence.py                  # state_dict + architecture.json round-trip (FR-23)
│       │   │   └── determinism.py                  # torch.use_deterministic_algorithms + CUBLAS_WORKSPACE_CONFIG + worker_init_fn
│       │   └── sklearn/
│       │       ├── __init__.py
│       │       ├── plugin.py                       # stub plugin: registers OperationSpec set; raises PluginError at materialize() (FR-24)
│       │       └── metrics.py                      # shared sklearn-based metric implementations consumed by other plugins (per FR-12)
│       ├── reporting/
│       │   ├── __init__.py
│       │   ├── report.py                           # report.md renderer (FR-18)
│       │   └── visualizations.py                   # reporting-mode renderer (writes to <instance>/report/visualizations/)
│       └── scaffolder/
│           ├── __init__.py
│           └── init.py                             # FR-21 deterministic scaffolder; reads bound DataRefinery instance manifest. (`llm.py` reserved for a future close-follow-on cycle per the `[llm]` extra — no implementation in the pre-production series.)
├── tests/
│   ├── conftest.py                                 # shared fixtures: tmp cache roots, minimal DataRefinery fixture, sample recipes
│   ├── unit/
│   │   ├── test_recipe_loader.py                   # FR-1: schema-version gate, plugin resolution, variant overlay, canonicalization byte-stability
│   │   ├── test_recipe_validator.py                # FR-2: every check 1..19 has a test
│   │   ├── test_cache_identity.py                  # FR-4: cosmetic-edit invariance, semantic-edit perturbation, loose-coupling rule
│   │   ├── test_atomic_promote.py                  # FR-5: failure at every materialize stage leaves FAILED marker
│   │   ├── test_manifest.py                        # FR-3 manifest shape; round-trip
│   │   ├── test_seeding.py                         # FR-25: master seed → deterministic per-stage seeds
│   │   ├── test_checkpoint.py                      # forward-extensible dict format; pre-prod writes weights-only; future-key tolerance
│   │   ├── test_data_binding.py                    # FR-6: DataRefinery instance resolution + cross-validation
│   │   ├── test_plugin_discovery.py                # entry-point + plugin-path
│   │   ├── test_pytorch_metrics.py                 # TR-9: each v0.x metric vs hand-computed golden
│   │   ├── test_pytorch_architecture.py            # FR-7: every architecture op resolves and instantiates
│   │   ├── test_pytorch_persistence.py             # TR-6: architecture.json round-trip
│   │   ├── test_pytorch_augmentations.py           # Hypothesis semantic-equivalence: torchvision-v2 lazy vs DataRefinery aggressive (visual semantics, not bytes)
│   │   ├── test_output_expectations.py             # TR-11: passing + failing assertions; FAILED marker
│   │   └── test_errors.py                          # exception hierarchy mapping (consumer-dep-spec BR-10)
│   ├── integration/
│   │   ├── test_materialize_e2e.py                 # FR-3: full materialize on a synthetic 100-record DataRefinery fixture; tiny model; PyTorch plugin
│   │   ├── test_determinism.py                     # TR-5: byte-identical instance contents across reruns (excluding wall-clock)
│   │   ├── test_loose_coupling.py                  # TR-7: re-materialize DataRefinery upstream; assert ModelFoundry cache unchanged
│   │   ├── test_optimization_e2e.py                # TR-10: TPE/Random/Grid deterministic trial sequences; baseline_trial; best-params merge
│   │   ├── test_round_trip.py                      # TR-6: load(path).predict(X) succeeds without external config
│   │   └── test_cifar10_smoke.py                   # TR-12 / AC-2: CIFAR-10 end-to-end on CPU (downsized for CI)
│   ├── cli/
│   │   ├── test_cli_init.py                        # init verb smoke
│   │   ├── test_cli_validate.py                    # validate verb smoke
│   │   ├── test_cli_check.py                       # check verb smoke
│   │   ├── test_cli_status.py                      # status verb smoke
│   │   ├── test_cli_materialize.py                 # materialize verb smoke
│   │   ├── test_cli_report.py                      # report verb smoke
│   │   ├── test_cli_inspect.py                     # inspect verb smoke
│   │   └── test_cli_clean.py                       # clean verb smoke
│   ├── notebook/
│   │   └── test_jupyter_smoke.py                   # TR-8: ModelInstance accessors render correctly in a nbclient-driven Jupyter cell
│   ├── plugin_contract/
│   │   ├── test_pytorch_contract.py                # Plugin Protocol assertions for the PyTorch plugin
│   │   └── test_sklearn_stub_contract.py           # sklearn stub registers the full OperationSpec set; raises PluginError at materialize
│   └── fixtures/
│       ├── recipes/
│       │   ├── minimal_pytorch.yml                 # smallest passing recipe
│       │   ├── pytorch_with_optimization.yml       # Optimization stage exercise
│       │   ├── pytorch_with_variants.yml           # variant overlay exercise
│       │   ├── pytorch_failing_expectations.yml    # OutputExpectations failure smoke
│       │   ├── sklearn_stub.yml                    # exercises plugin=sklearn rejection
│       │   └── invalid_*.yml                       # one fixture per validator rejection
│       ├── datarefinery_instances/
│       │   ├── synthetic_100_records/              # generated by the conftest builder; mimics DataRefinery's on-disk layout
│       │   └── cifar10_smoke/                      # downsized CIFAR-10 produced by the smoke fixture builder
│       └── golden/
│           ├── manifest_minimal.json               # byte-stable manifest goldens
│           ├── architecture_simple_cnn.json        # round-trip golden for FR-23
│           └── trials_minimal.parquet              # Optuna trial-history golden
└── docs/                                           # already-present specs and project-guide
```

---

## Filename Conventions

| File Type | Convention | Examples |
|-----------|------------|----------|
| Documentation (Markdown) | Hyphens | `tech-spec.md`, `project-essentials.md` |
| Workflow files | Hyphens | `ci.yml`, `publish.yml` |
| Python modules | Underscores (PEP 8) | `data_binding.py`, `pytorch/persistence.py` |
| Python packages | Underscores (PEP 8) | `modelfoundry/`, `pytorch/` |
| Configuration files | Hyphens or dots | `pyproject.toml`, `requirements-dev.txt`, `.gitignore` |

CLI command modules use a `_cmd.py` suffix (`materialize_cmd.py`) so verb names like `materialize` do not collide with the Python keyword-adjacent identifiers and stay readable in import paths. Matches DataRefinery's convention.

---

## Key Component Design

### `ModelFoundry` (core/modelfoundry.py)

Library entry point. Construction loads + validates the recipe and resolves the bound DataRefinery instance once; verbs are methods that share that state. CLI commands are thin typer wrappers.

```python
class ModelFoundry:
    @classmethod
    def from_recipe(
        cls,
        recipe_path: pathlib.Path,
        *,
        data: DataRefineryInstance,           # required, eager binding (concept Open Q1)
        config: RuntimeConfig | None = None,
        variant: str | None = None,
        seed: int | None = None,
    ) -> "ModelFoundry": ...

    def validate(self) -> ValidationReport: ...        # FR-2
    def materialize(self, *, overwrite: bool = False) -> ModelInstance: ...  # FR-3
    def status(self) -> StatusReport: ...              # FR-16
    def inspect(self, view: str | None = None) -> InspectionView: ...  # FR-17
    def report(self) -> ModelInstance: ...             # FR-18 re-render
    def clean(self, selector: CleanSelector) -> CleanReport: ...  # FR-20
    @staticmethod
    def check(config: RuntimeConfig | None = None) -> CheckReport: ...  # FR-19

    @property
    def recipe(self) -> ModelRecipe: ...
    @property
    def cache_key(self) -> CacheKey: ...
    @property
    def data_instance(self) -> DataRefineryInstance: ...
```

Top-level convenience:

```python
def materialize(
    recipe_path: pathlib.Path,
    *,
    data: DataRefineryInstance,
    config: RuntimeConfig | None = None,
    variant: str | None = None,
    seed: int | None = None,
    overwrite: bool = False,
) -> ModelInstance:
    return ModelFoundry.from_recipe(
        recipe_path, data=data, config=config, variant=variant, seed=seed
    ).materialize(overwrite=overwrite)
```

### `ModelInstance` (core/instance.py)

Loaded materialized artifacts. Frozen dataclass (not pydantic) since it represents on-disk state. Notebook-shaped accessors per FR-22.

```python
@dataclasses.dataclass(frozen=True)
class ModelInstance:
    path: pathlib.Path                         # the instance directory
    manifest: Manifest                         # parsed manifest.json (manifest.is_partial flags a partial read)
    plugin: Plugin                             # resolved from manifest.plugin at load time (FR-23)

    # --- Notebook-shaped properties (computed lazily; cached after first access) ---
    @cached_property
    def evaluation(self) -> dict[str, dict[str, Any]]: ...   # evaluation/metrics.json
    @cached_property
    def metrics(self) -> dict[str, dict[str, Any]]: ...      # alias for evaluation (not per-epoch history)
    @cached_property
    def confusion_matrix(self) -> dict[str, numpy.ndarray]: ...  # evaluation/confusion_matrix.npz
    @cached_property
    def calibration(self) -> pandas.DataFrame | None: ...    # evaluation/calibration.parquet
    @cached_property
    def predictions(self) -> pandas.DataFrame | None: ...    # evaluation/predictions.parquet
    @cached_property
    def trials(self) -> pandas.DataFrame | None: ...         # optimization/trials.parquet
    @cached_property
    def best_params(self) -> dict[str, Any] | None: ...      # optimization/best-params.json
    @cached_property
    def figures(self) -> dict[str, bytes]: ...               # report/visualizations/*.png (PNG bytes)
    @cached_property
    def summary(self) -> dict[str, Any] | None: ...          # model/summary.json (FR-27)
    @cached_property
    def summary_text(self) -> str | None: ...                # model/summary.txt (FR-27)

    # --- Inference (substrate-neutral I/O) ---
    def predict(self, X: PredictInput) -> numpy.ndarray | pandas.Series: ...
    def predict_proba(self, X: PredictInput) -> numpy.ndarray | pandas.DataFrame: ...

    @classmethod
    def load(cls, path: str | pathlib.Path, *, plugin: Plugin | None = None) -> "ModelInstance": ...
    def render_report(self) -> str: ...        # re-renders report/ and returns the Markdown
```

Where `PredictInput` is a plugin-defined union; the PyTorch plugin accepts `pd.DataFrame` (record-schema), `list[pathlib.Path]` (image paths), or `numpy.ndarray` of shape `(N, H, W, C)`.

### `recipe.loader` (FR-1)

```python
SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})  # grows over time

def load_recipe(
    path: pathlib.Path,
    *,
    variant: str | None = None,
    seed: int | None = None,
) -> ModelRecipe:
    """Parse YAML, gate on schema_version, apply variant overlay, canonicalize."""
```

Raises `RecipeError` on schema-version mismatch, malformed YAML, unknown plugin, unknown variant. Unknown top-level keys are rejected (`extra="forbid"` on the pydantic root model).

### `recipe.validator` (FR-2)

```python
class ValidationCheck(pydantic.BaseModel):
    id: str                  # "check_05_fit_on_train_discipline"
    name: str
    status: Literal["pass", "fail"]
    detail: str | None = None
    offending_path: str | None = None  # e.g. "Loss.weight_source"

class ValidationReport(pydantic.BaseModel):
    checks: list[ValidationCheck]

    @property
    def ok(self) -> bool:
        return all(c.status == "pass" for c in self.checks)

def validate(
    recipe: ModelRecipe,
    data: DataRefineryInstance,
    plugin: Plugin,
) -> ValidationReport:
    """Run FR-2 checks 1..19. Never short-circuits."""
```

### `recipe.canonical` (FR-4)

```python
def canonical_bytes(recipe: ModelRecipe) -> bytes:
    """JSON-canonical bytes for cache identity.

    Steps:
      1. recipe.model_dump(mode="json")  -> dict[str, Any]
      2. json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)
      3. .encode("utf-8")

    Every pydantic field default participates. A new default value or
    field-name change perturbs the canonical bytes — that is the deliberate
    invalidation lever, gated by SUPPORTED_SCHEMA_VERSIONS bumps.
    """

def recipe_hash(recipe: ModelRecipe) -> str:
    """SHA-256 hex digest over canonical_bytes (full 64-hex; truncate at the
    layout layer for the directory component)."""
```

### `cache.identity` (FR-4)

```python
def cache_key(
    recipe: ModelRecipe,
    data: DataRefineryInstance,
    seed: int,
) -> CacheKey:
    """Return the cache key triple:
        recipe_hash16: str               # 16 hex chars (canonical recipe)
        data_instance_hash16: str        # 16 hex chars (XOR of DataRefinery's
                                          # recipe_hash + input_hash + seed)
        seed: int                        # the ModelFoundry-side seed
    """
```

Loose-coupling (CR-15): the bound DataRefinery instance's `recipe_hash` participates in the **data instance identity**, but the consuming ModelFoundry recipe's cache identity treats the DataRefinery instance as a single hashed unit — re-materializing upstream changes the data_instance_hash16 only when the DataRefinery cache directory itself moves (new variant, new seed, new recipe shape, new input bytes). Re-materializing upstream into the same DataRefinery cache directory is a no-op for ModelFoundry's cache identity. This is intentional per FR-4 and the consumer-dep-spec's loose-coupling rule.

### `cache.atomic` (FR-5)

```python
@contextlib.contextmanager
def materialize_temp_dir(cache_root: pathlib.Path, cache_key: CacheKey) -> Iterator[pathlib.Path]:
    """Yield <cache-root>/instances/.tmp/<run-id>/. On clean exit, atomically
    promote to <cache-root>/instances/<key>/. On any exception, write FAILED
    marker and leave the temp dir for diagnosis."""

def trash_existing(cache_root: pathlib.Path, key: CacheKey) -> pathlib.Path:
    """Move an existing instance to <cache-root>/.trash/<timestamp>/<key>/
    for --overwrite. Returns the trash path."""
```

Cross-device limitation documented inline: `os.replace` requires temp and final paths to share a filesystem.

### `pipeline.runner.MaterializeRunner` (FR-3)

The orchestrator. Sequences stages per FR-3 step 4:

```python
class MaterializeRunner:
    def __init__(
        self,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        plugin: Plugin,
        seed: int,
        temp_dir: pathlib.Path,
        config: RuntimeConfig,
    ): ...

    def run(self) -> Manifest:
        """Run stages in canonical order:
           1. Architecture (plugin.build_model)
           2. Optimization (plugin.run_optimization) — if declared
           3. Training (plugin.run_training) — with merged best-params
           4. Evaluation (plugin.run_evaluation) — writes predictions.parquet
           5. OutputExpectations (expectations.evaluate)
           6. Reporting visualizations (plugin.render_visualization for mode=reporting)
           7. Persistence (plugin.save_model + architecture.json)
           8. Report (reporting.report.render)
           9. Manifest (manifest.write)
           Returns the assembled Manifest. Errors propagate to materialize()
           which writes the FAILED marker and re-raises.
        """
```

Stages skipped by omission (`Optimization` absent, `Evaluation.splits` empty) are recorded in the manifest as `null`.

### `pipeline.checkpoint` — forward-extensible checkpoint format (FR-25 foundation for continued-training)

Per developer direction: the pre-production release does not persist optimizer state (Q16 — not yet a feature), **but** the checkpoint format is laid out so adding it later is a pure additive change with no public-API rework.

```python
class Checkpoint(pydantic.BaseModel):
    """Forward-extensible checkpoint dict.

    Pre-production keys (always present, written by every plugin):
      - epoch: int
      - weights: pathlib.Path           # relative path to weights blob under model/
      - metric_value: float
      - recipe_hash16: str              # for cross-instance integrity check
      - schema_version: int             # checkpoint schema, separate from recipe schema

    Forward-extensible keys (absent today, may appear in future releases;
    loaders MUST log-and-continue when encountering unknown keys):
      - optimizer_state: pathlib.Path | None    # future: continued-training FR
      - scheduler_state: pathlib.Path | None    # future: continued-training FR
      - rng_state: pathlib.Path | None          # future: bit-exact resumption
      - training_step: int | None               # future: step-based resumption
    """
    model_config = ConfigDict(extra="allow")  # tolerate future keys

    epoch: int
    weights: pathlib.Path
    metric_value: float
    recipe_hash16: str
    schema_version: int = 1
```

The `Trainer` protocol's `save_checkpoint(epoch, state: dict[str, Any], path)` and `load_checkpoint(path) -> dict[str, Any]` interface accepts arbitrary state items. The PyTorch plugin's pre-production implementation writes `{epoch, weights_path, metric_value}` only. Adding `optimizer_state` later requires (a) extending the plugin's `save_checkpoint` to write `optimizer_state.pt`, (b) extending `load_checkpoint` to read it, (c) adding a `Training.persist_optimizer_state: bool = false` recipe field gated by a `schema_version` bump. **No** public API change.

### `pipeline.seeding` (FR-25)

```python
def derive_seed(master_seed: int, scope: str, *salts: bytes) -> int:
    """Deterministic per-scope seed derivation:
       sha256(master_seed.to_bytes(8) + scope.encode() + b"".join(salts))[:8]
       -> int

    Standard scopes:
      - "weight_init"             — model.init weights
      - "data_shuffle"            — DataLoader generator
      - "optuna_sampler"          — Optuna TPE/Random sampler seed
      - "augmentation:<op_id>"    — lazy augmentation realizers
      - "dropout"                 — model dropout RNG (PyTorch-managed)
    """

def worker_init_fn_factory(master_seed: int) -> Callable[[int], None]:
    """Returns a worker_init_fn that seeds each DataLoader worker
    deterministically from (master_seed, worker_id). Output bytes are
    independent of num_workers — same property DataRefinery's
    pipeline.workers contract guarantees."""
```

### `plugins.base` (FR-24)

The Plugin Protocol — abstract over Trainer / Evaluator / Optimizer / Visualization handles. Each concrete plugin (`pytorch`, `sklearn`) implements this Protocol.

```python
class OperationSpec(pydantic.BaseModel):
    """Plugin-side schema for one operation. Used by FR-2 check 17."""
    op_name: str
    param_model: type[pydantic.BaseModel]
    applies_to: Literal["architecture", "loss", "optimizer", "schedule",
                        "training", "optimization", "evaluation", "visualization"]
    requires_extras: tuple[str, ...] = ()  # e.g. ("huggingface",) — lazy-import check

@runtime_checkable
class Plugin(Protocol):
    name: str
    version: str
    operations: dict[str, OperationSpec]

    def health_check(self) -> CheckReport: ...                       # FR-19
    def build_model(self, arch: ArchitectureSpec) -> Any: ...         # FR-7
    def run_optimization(
        self, opt: OptimizationSpec, recipe: ModelRecipe,
        data: DataRefineryInstance, seed: int, temp_dir: pathlib.Path,
    ) -> OptimizationResult: ...                                      # FR-11
    def run_training(
        self, training: TrainingSpec, model: Any, recipe: ModelRecipe,
        data: DataRefineryInstance, seed: int, temp_dir: pathlib.Path,
    ) -> TrainingResult: ...                                          # FR-10
    def run_evaluation(
        self, evaluation: EvaluationSpec, model: Any,
        data: DataRefineryInstance, temp_dir: pathlib.Path,
    ) -> EvaluationResult: ...                                        # FR-12
    def render_visualization(
        self, viz: VisualizationSpec, instance_artifacts: InstanceArtifacts,
    ) -> bytes | None: ...                                            # FR-13
    def save_model(self, model: Any, path: pathlib.Path) -> None: ... # FR-23
    def load_model(self, path: pathlib.Path) -> Any: ...              # FR-23
    def predict(self, model: Any, X: Any) -> numpy.ndarray | pandas.Series: ...
    def predict_proba(self, model: Any, X: Any) -> numpy.ndarray | pandas.DataFrame: ...
```

### `plugins.pytorch` (PyTorch plugin, end-to-end)

Implements the Plugin Protocol against PyTorch. Key sub-modules:

- `architecture.py` — registers CIFAR-10-scale CNN primitives, composites, and baseline architectures (FR-ARCH-1). Each op is a `nn.Module` subclass + a pydantic `OperationSpec` param model. The plugin composes them via a recursive builder that reads the canonical `Architecture` block.
- `data.py` — `DataRefineryDataset(torch.utils.data.Dataset)` adapter. Reads the bound instance's `dataset/<split>.jsonl`; resolves `path` / `image_path` per the vendor-dep-spec; decodes with Pillow; applies the recipe's lazy `Augmentations` block at iteration time. Per-record-seed stamps from DataRefinery's vendor-dep-spec (`<AugmentationOp.name>_seed`) are honored for aggressive variants (read directly from the JSONL record); lazy augmentations realize via `torchvision.transforms.v2` against the seeding contract from `pipeline.seeding`.
- `augmentations.py` — torchvision-v2 realizers for `random_crop`, `horizontal_flip`, `color_jitter`, `random_erasing`. Visual semantics match DataRefinery's Pillow-based aggressive realizers, verified by a hypothesis property-based test on a fixture set (semantic equivalence, not byte-equivalence — the two paths are fundamentally different code).
- `trainer.py` — Training-loop implementation honoring `Training.max_epochs`, `Training.batch_size`, `Training.early_stopping`, `Training.checkpoint_cadence`. (Weight-init seeding happens earlier, via the runner's `prepare_for_build` hook before `build_model`; the trainer re-asserts `determinism.enable_deterministic_algorithms()` for the loop and seeds dropout.) Uses `pipeline.seeding.worker_init_fn_factory` for DataLoaders. Periodic checkpoints are persisted with `torch.save(Checkpoint(...).model_dump(), path)` — `torch.save` is byte-stable across equal tensors, whereas raw-pickling tensors is not (required for the FR-25 byte-identity contract).
- `optimization.py` — Optuna-backed Optimization stage. `RDBStorage` with `sqlite:///<temp-dir>/optimization/study.db`; sampler seeded via `derive_seed(master_seed, "optuna_sampler")`; `n_jobs=1` enforced. `baseline_trial: enqueue_recipe_defaults` calls `study.enqueue_trial(recipe.optimizer.params | recipe.training.params | …)` before `study.optimize(...)`. Best-trial params are merged back into the recipe via `recipe.search_space.apply_params(...)` and the Training stage proceeds with the merged recipe.
- `evaluation.py` — Metric implementations via `torchmetrics` (`MulticlassF1Score`, `MulticlassConfusionMatrix`, `CalibrationError`). ECE via torchmetrics' `CalibrationError`; calibration_curve via sklearn helpers. Baseline-model resolution (FR-12) attempts HuggingFace download lazily; failures emit a warning and continue (the rest of evaluation succeeds).
- `visualizations.py` — Matplotlib renderers for `training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid`. Each visualization op takes `InstanceArtifacts` and returns PNG bytes (single PNG) or `None` (skipped, e.g. `optimization_history` without an Optimization stage and `mode: reporting` declared — emits a placeholder PNG so the manifest's `visualizations` record is consistent).
- `persistence.py` — `save_model(model, model_dir)` writes:
  - `model/weights/state_dict.pt` — `torch.save(model.state_dict(), ...)`.
  - `model/architecture.json` — the canonical post-variant-overlay, post-Optimization-merge `Architecture` block, serialized with the same JSON-canonical bytes recipe canonicalization uses.
  - `model/checkpoints/checkpoint-best.pt` — the pre-production checkpoint dict (FR-25 foundation; ready to grow optimizer_state later without a public-API change).
  `load_model(path)` reads `model/architecture.json`, rebuilds the `nn.Module` via the recursive builder, then `load_state_dict` from `model/weights/state_dict.pt`. No external config object required (TR-6 round-trip guarantee).
- `determinism.py` — wraps `torch.use_deterministic_algorithms(True)` + sets `CUBLAS_WORKSPACE_CONFIG=:4096:8` in the environment; documents which ops hard-error under deterministic mode. The plugin's `health_check()` (FR-19) reports whether deterministic mode can be enabled on the installed backend.
- `summary.py` — `torchinfo`-backed model summary (FR-27). `summarize(model, input_size) -> (ModelSummary, str)` runs `torchinfo.summary` once (eval-mode probe, training flag restored — no side effect on the persisted model) and returns the structured `ModelSummary` (ordered per-layer rows of `type` / `output_shape` / `param_count` / `trainable_params` / `mult_adds`, plus network totals `total_params` / `trainable_params` / `non_trainable_params` / `total_mult_adds`) and the text render. `write_summary(model, input_size, model_dir)` writes the byte-deterministic `model/summary.txt` + `model/summary.json` (no timestamps; canonical-sorted JSON). `derive_input_size(data_instance)` reads the bound instance's record-schema image shape (HWC → `(1, C, H, W)`), decoding one record through `data.py` as a fallback. The plugin's `write_model_summary(model, data, model_dir)` (an **optional** capability the materialize runner calls after Persistence by duck-typing) delegates here; plugins without it skip the step.

### `plugins.sklearn` (sklearn stub)

Registers the `OperationSpec` set for every section but contributes only the shared metric implementations consumed by other plugins. `materialize()` against `plugin: sklearn` raises:

```
PluginError(
    "plugin 'sklearn' has no working Training implementation in the "
    "pre-production release; use 'pytorch'. The sklearn stub exists to "
    "validate the plugin Protocol is honest. See the close follow-on "
    "cycle for a working sklearn implementation."
)
```

The shared sklearn metric implementations live in `plugins/sklearn/metrics.py` and are imported by the PyTorch plugin for `calibration_curve` (which sklearn handles directly) and used by the future sklearn / Keras / HuggingFace plugins for `f1`, `precision`, `recall`, `accuracy`, `confusion_matrix`.

---

## Data Models

### `ModelRecipe` (recipe/models.py)

Top-level pydantic v2 model. Per-section sub-models live alongside.

```python
class ModelRecipe(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int                    # gated by SUPPORTED_SCHEMA_VERSIONS
    plugin: str                            # "pytorch" | "sklearn" (pre-prod)
    seed: int                              # master seed
    Data: DataSpec
    Architecture: ArchitectureSpec         # plugin-specific shape, validated via OperationSpec
    Loss: LossSpec
    Optimizer: OptimizerSpec
    Training: TrainingSpec
    Optimization: OptimizationSpec | None = None
    Evaluation: EvaluationSpec
    Visualizations: list[VisualizationSpec] = []
    OutputExpectations: list[ExpectationSpec] = []
    variants: dict[str, dict[str, Any]] = {}   # name -> partial overlay
```

```python
class DataSpec(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: pathlib.Path                   # DataRefinery recipe path
    variant: str | None = None
    seed: int | None = None
    cache_root: pathlib.Path | None = None # override DataRefinery cache root for this binding
```

```python
class TrainingSpec(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_epochs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    num_workers: int = Field(ge=0, default=2)
    precision: Literal["fp32", "amp"] = "fp32"  # AMP off by default per QR-3
    checkpoint_cadence: int = Field(gt=0, default=1)
    early_stopping: EarlyStoppingSpec | None = None
    # Applies to Training + Evaluation + inference (eval and predict inherit);
    # resolved by the plugin's health_check-reported availability at materialize
    # time. "auto" picks the best available accelerator. Validator check 20
    # rejects an explicit device the plugin reports unavailable. Distinct values
    # produce distinct canonical recipe bytes (CPU-bench and MPS runs are
    # separate ModelInstances by design — no silent cross-device cache collision).
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    # Forward-extensibility hook (Q16 foundation; see § Checkpoint format above):
    # persist_optimizer_state: bool = False  # absent in pre-prod; added by future continued-training FR
```

```python
class OptimizationSpec(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid")
    sampler: Literal["tpe", "random", "grid"] = "tpe"
    pruner: Literal["median", "none"] = "median"
    n_trials: int = Field(gt=0)
    n_jobs: Literal[1] = 1                  # locked to 1 per QR-3 (FR-2 check 10)
    baseline_trial: Literal["enqueue_recipe_defaults"] | None = "enqueue_recipe_defaults"
    objective_metric: str | None = None     # defaults to Evaluation.primary_metric on val
    max_epochs_per_trial: int | None = None # caps Training.max_epochs per trial
    search_space: dict[str, SearchSpaceSpec]  # keyed by recipe path
```

```python
class EvaluationSpec(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid")
    splits: list[str]
    primary_metric: str
    metrics: list[str]                      # validated against the v0.x metric vocabulary at check 11
    comparison: ComparisonSpec | None = None
    calibration_bins: int = Field(gt=0, default=10)
```

```python
class ExpectationSpec(pydantic.BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: str
    split: str
    op: Literal["gte", "lte", "eq", "within"]
    value: float | tuple[float, float]      # tuple required for op="within"
```

Per-plugin specs (`ArchitectureSpec`, plugin-specific sub-models under `Loss` / `Optimizer` / `Visualizations`) are loaded by the plugin's `OperationSpec.param_model` and attached to the recipe object after `OperationSpec` resolution. Recipe-level `extra="forbid"` plus plugin-level `param_model` resolution covers FR-2 checks 3 and 17.

### `Manifest` (core/manifest.py)

Pydantic model written to `manifest.json` at promote time.

```python
class Manifest(pydantic.BaseModel):
    schema_version: int                    # manifest schema, separate from recipe schema
    plugin: str
    plugin_version: str
    recipe_hash: str                       # full SHA-256 hex (64 chars)
    data_instance_hash: str                # 16 hex chars — the bound DataRefinery instance triple
    bound_data_instance: pathlib.Path      # resolved absolute path for inspect()/status() lineage
    seed: int
    variant: str | None
    created_at: datetime                   # UTC ISO 8601
    elapsed_seconds: float
    warnings: list[ManifestWarning] = []
    is_partial: bool = False
    failed_stage: str | None = None
    epoch_history: int                     # rows in training/history.parquet
    optimization: OptimizationManifest | None = None
    evaluation: dict[str, dict[str, Any]]  # mirrors evaluation/metrics.json
    output_expectations: list[ExpectationOutcome]
    byte_identity_guaranteed: bool = True  # False when Training.precision = "amp"
    metric_tolerance: float | None = None  # populated when byte_identity_guaranteed is False
```

### `RuntimeConfig` (core/config.py)

```python
class RuntimeConfig(pydantic.BaseModel):
    cache_root: pathlib.Path = Path("./models")
    data_cache_root: pathlib.Path = Path("./data")   # DataRefinery cache root for Data: lookup
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_target: str = "stderr"                       # file path or "stderr" / "stdout"
    plugin_path: tuple[pathlib.Path, ...] = ()
    variant: str | None = None
    seed: int | None = None                          # CLI override; participates in cache identity
    overwrite: bool = False
```

Precedence: recipe (semantic) > CLI flags (execution context) > env vars > built-in defaults.

### Exception hierarchy (core/errors.py)

```
ModelfoundryError                    # base
├── RecipeError                      # FR-1 load / parse / schema-version
├── ValidationError                  # FR-2 check failures
├── PluginError                      # plugin discovery, duplicate names, missing extras
├── DataBindingError                 # FR-6 DataRefinery instance incompatibility
├── MaterializeError                 # FR-3/FR-10/FR-11/FR-12 stage failures, atomic-promote failures
├── ModelArtifactExistsError         # FR-5 instance directory exists; overwrite=False
├── OptimizationError                # FR-11 study cannot be created/resumed/completed
├── ExpectationError                 # FR-15 OutputExpectations failure
├── CacheError                       # FR-4/FR-5/FR-20 cache key, layout, clean problems
├── InspectionError                  # FR-17 view unavailable
└── InstanceError                    # FR-22 corrupt / partial instance read errors
```

CLI exit codes (mirrors DataRefinery's mapping): `0` success, `1` user/recipe/contract error, `2` system/plugin error, `130` SIGINT.

---

## Configuration

**Precedence (high to low):**

1. Recipe file (authoritative for model-build semantics).
2. CLI flags (execution context only).
3. Environment variables (defaults for execution context).
4. Built-in defaults.

**CLI flags / env vars:**

| CLI flag | Env var | Default | Purpose |
|---|---|---|---|
| `--cache-root` | `MODELFOUNDRY_CACHE_ROOT` | `./models/` | ModelFoundry cache root. |
| `--data-cache-root` | `MODELFOUNDRY_DATA_CACHE_ROOT` | `./data/` | DataRefinery cache root for `Data:` lookup. |
| `--log-level` | `MODELFOUNDRY_LOG_LEVEL` | `INFO` | Operational log level. |
| `--log-target` | `MODELFOUNDRY_LOG_TARGET` | `stderr` | JSON-lines log sink. |
| `--plugin-path` | `MODELFOUNDRY_PLUGIN_PATH` | (empty) | Extra plugin discovery paths. |
| `--variant` | (none) | (none) | Variant overlay name. |
| `--seed` | (none) | (recipe) | Ad-hoc seed override; changes cache identity. |
| `--overwrite` | (none) | `false` | Re-materialize even on cache hit. |

No `modelfoundry.toml` per-project config in the pre-production series — the recipe is authoritative; CLI flags + env vars cover execution context.

---

## CLI Design

Root command: `modelfoundry`. Subcommands:

| Subcommand | Purpose | FR |
|---|---|---|
| `init <recipe-path> --data <dr-recipe>` | Scaffold a starter recipe | FR-21 |
| `validate <recipe>` | Run static checks | FR-2 |
| `check` | Environment + plugin health | FR-19 |
| `status <recipe>` | Summarize lifecycle / cache state | FR-16 |
| `materialize <recipe>` | Train + optimize + evaluate end-to-end | FR-3 |
| `report <instance-path>` | Re-render `report.md` + reporting visualizations | FR-18 |
| `inspect <instance-path> [--view <name>]` | Render an exploration-mode view | FR-17 |
| `clean [--recipe-hash | --older-than | --failed | --orphans]` | Cache management | FR-20 |

**Shared flags** (apply to every subcommand): `--cache-root`, `--data-cache-root`, `--log-level`, `--log-target`, `--plugin-path`, `--verbose`, `--quiet`.

**Subcommand-local flags**: `--variant`, `--seed`, `--overwrite` (`materialize` only); `--view` (`inspect` only); `--dry-run` (`clean`).

**Exit codes**: `0` success, `1` user/recipe/contract error, `2` system/plugin error, `130` SIGINT.

---

## Cross-Cutting Concerns

### Logging and User Output

This project uses two-channel output discipline (template baseline applies):

- **User-facing output** — `rich`. Per-epoch tables (Training), per-trial progress bars (Optimization), cache hit/miss summary, final "instance materialized at …" message, structured tables for `status` / `inspect` / `validate`.
- **Operator logs** — stdlib `logging` (with `modelfoundry.logging.JsonFormatter`). Stage starts/ends, op-ids, warnings, error context, timing. JSON lines on the configured `--log-target`.

Library callers get a logger named `modelfoundry`; ModelFoundry never hijacks the root logger. Progress is opt-in via a `progress: bool` argument; suppressed inside Optuna trials > 0 per the sentiment-poc precedent — **file-descriptor-level redirect** (`os.dup2` against fd 1/2 inside a context manager) for backends that write directly to fd 1/2, not just `sys.stdout`. Trial 0 prints normally so the user can verify the recipe-defaults baseline trains correctly.

See `docs/project-guide/developer/best-practices-guide.md` for full rationale.

### Additional Cross-Cutting Concerns

**Atomic writes.** All writes inside the instance directory target the materialize temp dir (`<cache-root>/instances/.tmp/<run-id>/`) until promote. The `os.replace` rename is the single atomic step. Same-filesystem-only requirement (cross-device-rename limitation) is documented in FR-5 and surfaced by `check`.

**Determinism plumbing.** Before each `build_model` of the to-be-trained model (the `architecture` stage, and the post-Optimization rebuild), the materialize runner calls the plugin's `prepare_for_build(seed)` hook — the runner is plugin-agnostic, so RNG seeding is delegated. For the PyTorch plugin that hook enables deterministic-algorithm mode and seeds the weight-init RNG (`derive_seed(seed, "weight_init")`), so weight initialization is reproducible across runs (FR-25); for sklearn it is a no-op (the estimator's `random_state` is seeded at `fit` time). `CUBLAS_WORKSPACE_CONFIG` is set in `os.environ` if not already present. The `worker_init_fn` derived from `pipeline.seeding` is passed to every `DataLoader`. AMP is off unless the recipe sets `Training.precision: "amp"`; AMP recipes are stamped with `manifest.byte_identity_guaranteed: false` and `manifest.metric_tolerance` from the plugin's documented tolerance table.

**Device resolution.** `Training.device` (`Literal["auto", "cpu", "cuda", "mps"]`, default `"auto"`) drives every model-execution stage in the plugin: Training, the inner trainings of Optuna Optimization, Evaluation, `predict`, and `predict_proba`. Eval and inference resolve the device implicitly from the field — there is no separate `Evaluation.device` knob. `"auto"` lets the plugin pick the best accelerator its `health_check` reports available (MPS > CUDA > CPU in the PyTorch plugin's preference order); explicit values force the choice and are validated against `health_check.accelerators` (FR-2 check 20). Because `device` participates in canonical recipe bytes, distinct device choices produce distinct cache entries — a CPU-benchmark run and an MPS run on the same recipe materialize into separate `ModelInstance` directories rather than colliding on a shared key. Plugins that have not yet wired an `accelerators` field into their `health_check` report are tolerated: the validator records a skip message instead of failing, so honest in-progress plugins are not blocked.

**Schema-version coordination with DataRefinery.** Per the vendor-dependency-spec § Schema-version coordination policy, ModelFoundry tracks DataRefinery's `SUPPORTED_SCHEMA_VERSIONS` (imported as `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS`). A bound DataRefinery instance whose manifest declares a recipe `schema_version` higher than ModelFoundry's known max is rejected at validate time (FR-2 check 19). Lower versions are accepted (DataRefinery's forward-migrations already normalized the shape).

**Optimization sub-process suppression.** Optuna trial > 0 stdout/stderr is suppressed via fd-level `os.dup2` redirect inside a context manager, restored after the trial completes. This handles backends (e.g. some torch C++ extensions) that write directly to fd 1/2, which `contextlib.redirect_stdout` does not catch.

**Plugin lazy imports.** Plugins must be discoverable without requiring their extras to be installed. `OperationSpec.requires_extras` declares the extras a plugin op needs at execution time; the plugin's module-level imports are restricted to the base set. `materialize()` calls into the plugin trigger lazy imports of extras-gated modules with a clear `ImportError` and install pointer when missing. Mirrors DataRefinery's `[corruptions]` extras pattern.

**Cache-root resolution.** The ModelFoundry cache root is `RuntimeConfig.cache_root` (`./models/` default). The DataRefinery cache root used to resolve `Data:` is a separate config field `RuntimeConfig.data_cache_root` (`./data/` default) — overrides come from `Data.cache_root` in the recipe (per-recipe override) or `--data-cache-root` / `MODELFOUNDRY_DATA_CACHE_ROOT` (execution-time override). Recipe-level override wins because the recipe is authoritative.

**Trash directory for `--overwrite`.** Existing instances displaced by `--overwrite` are moved to `<cache-root>/.trash/<timestamp>/<key>/` rather than deleted in place. `clean --older-than <duration>` covers the trash directory under the same age threshold. Mirrors a common safety pattern; protects against accidental destruction.

**Loose-coupling honesty.** The consumer-dep-spec's BR-9 (loose-coupled DataRefinery binding) is enforced by the cache-identity computation refusing to mix in the upstream `recipe_hash`. A future tight-coupling upgrade (FR-26) will require both a `schema_version` bump and a documented migration of existing cached ModelInstances. The pre-production release explicitly does not lay tight-coupling foundation — the loose-coupling rule is the foundation.

---

## Performance Implementation

Per `features.md` PE-1, the pre-production release commits to no throughput / latency / memory targets. Concrete defaults that flow from determinism caveats and the locked architecture:

- **`Training.num_workers`**: default `2`. Seeded via `pipeline.seeding.worker_init_fn_factory`. Output bytes are independent of `num_workers` (per FR-25). Recipes may override.
- **`Optimization.n_jobs`**: locked to `1` (FR-2 check 10). Parallel trials are a deferred upgrade.
- **`Training.precision`**: `"fp32"` default. AMP relaxes the byte-identity guarantee per QR-3.
- **Optuna `RDBStorage` SQLite**: file-backed sqlite under the materialize temp dir; opaque to consumers. SQLite handles the trial volumes seen in pre-production (`n_trials ≤ 100` typical).
- **Cache hits are constant-time** (PE-2): compute key + `path.exists()` + load manifest. No deep introspection of the cached instance.
- **CIFAR-10 smoke (PE-3)** sized for CPU under a free-tier CI runner's per-job budget: a 3-epoch, batch-size-32, `simple_cnn` recipe; 2-trial Optimization with 1-epoch trials. Documented floor for `val_macro_f1` calibrated against the CI environment.

No concurrency / connection-pooling / batching strategy beyond the above — the determinism contract takes precedence over throughput optimization in the pre-production series.

---

## Testing Strategy

Mirrors features.md TR-1..TR-16 with the tests/ layout above. Categories:

**Unit tests** (`tests/unit/`): Pure-function tests for the recipe loader / validator / canonical bytes / cache identity / atomic promote / manifest / seeding / checkpoint / data binding / plugin discovery / PyTorch metric implementations / architecture op resolution / persistence round-trip / lazy-augmentation semantic equivalence (Hypothesis) / OutputExpectations evaluation / error hierarchy. Coverage target ≥ 95% on these modules per TR-15.

**Integration tests** (`tests/integration/`): End-to-end materialize on a synthesized DataRefinery fixture (100 records, two splits, three classes, deterministic byte-shape); determinism (rerun byte-identity across 1/2/4 workers); loose-coupling (re-materialize upstream → ModelFoundry cache unchanged); optimization end-to-end (TPE/Random/Grid deterministic; baseline_trial; best-params merge); round-trip (`load(path).predict(X)` without external config); CIFAR-10 smoke (TR-12 / AC-2, CPU-runnable under free-tier CI).

**CLI tests** (`tests/cli/`): Per-verb smoke. Each verb runs against the same synthesized DataRefinery fixture + a minimal model recipe; assertions cover exit codes, structured `rich` output, JSON-lines log content on the configured log target.

**Notebook smoke** (`tests/notebook/`): A `nbclient`-driven Jupyter cell exercises the `ModelInstance` accessor surface against a cached fixture instance; substrate-neutral sanity check per TR-8. Marimo headless smoke and IPython REPL smoke are deferred.

**Plugin contract tests** (`tests/plugin_contract/`): Each plugin asserts its declared `OperationSpec` set is exhaustive (every op listed in features matches), the Plugin Protocol assertions pass (mypy + runtime `isinstance` against `runtime_checkable`), and the `health_check()` returns the expected shape.

**Fixtures** (`tests/fixtures/`): Recipe fixtures (one per validator rejection + the happy paths); a synthesized DataRefinery instance builder (`conftest.py`) that mimics the vendor-dependency-spec's on-disk layout; a downsized CIFAR-10 builder for the smoke; golden files (manifest, architecture.json, trials.parquet) for byte-stable round-trip assertions.

**Hypothesis property tests**: Cache-identity invariants (cosmetic edits leave hash unchanged; semantic edits perturb hash); lazy-augmentation semantic equivalence between torchvision-v2 and DataRefinery's Pillow realizers on a fixture image set.

**Coverage**:
- ≥ 95% line coverage on TR-1, TR-2, TR-4, TR-6, TR-7 modules (recipe loader, cache identity, atomic promote, persistence round-trip, loose-coupling).
- Every FR exercised by at least a smoke (any release).
- ≥ 85% overall line coverage post-production (relaxed pre-production).

**Coverage reporting**: `pytest-cov` produces `coverage.xml` and a terminal report. Codecov / Coveralls upload is **deferred** for the pre-production series (per the CI section below).

---

## Packaging and Distribution

| Concern | Value |
|---|---|
| **Python package** | `modelfoundry` (import name + console script) |
| **PyPI distribution** | `ml-modelfoundry` (matches DataRefinery's `ml-datarefinery` precedent; the bare `modelfoundry` name is not available on PyPI) |
| **Build backend** | `hatchling` |
| **Wheel + sdist** | `python -m build` |
| **Console scripts** | `modelfoundry = modelfoundry.cli.app:main` |
| **Package data** | `py.typed` marker; no shipped templates beyond `init` scaffolds (which live under `src/modelfoundry/scaffolder/templates/`) |
| **Install (default)** | `pip install ml-modelfoundry` — installs the base; recipes need a plugin extra |
| **Install (PyTorch)** | `pip install ml-modelfoundry[pytorch]` — the pre-production release path |
| **Install (with notebook smokes)** | `pip install ml-modelfoundry[pytorch,notebook-smokes]` — dev convenience |
| **Versioning source** | `src/modelfoundry/_version.py` — single source of truth; `__init__.py` re-exports |
| **Pre-1.0 stability** | Per CR-1 / OR-8 / OR-9 / OR-10: API and CLI surface, cache layout, materialize concurrency may change between minor versions in the `0.x.y` series. `1.0.0` is the production-release event. |

---

## CI/CD Automation

GitHub Actions: `ci.yml` runs `ruff check` + `ruff format --check` (testenv) + `mypy --strict` (typecheck) + `pyve test --env smoke-pytorch` + the CIFAR-10 smoke (TR-12) on every PR and push to `main` on macOS (Apple Silicon) primary with Linux as a stretch matrix entry; `publish.yml` performs PyPI Trusted Publishing on tagged commits (`v*.*.*`); GitHub branch protection and Codecov / Coveralls coverage upload are explicitly out of scope for the pre-production series per CR-1, with coverage produced locally by the `smoke-pytorch` run (`--cov` is enabled by default) as the in-repo report.
