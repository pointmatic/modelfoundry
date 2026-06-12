# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- PyTorch lazy augmentations (Story C.g): `modelfoundry.plugins.pytorch.augmentations` realizes a DataRefinery *lazy* `Augmentations` policy on-the-fly via `torchvision.transforms.v2.functional`. `build_realizer(op, params, seed)` returns a deterministic transform for `horizontal_flip` / `random_crop` / `color_jitter` / `random_erasing` (params validated against vendor-spec-shaped models → `PluginError`), drawing all randomness from a **local `torch.Generator`** so the global RNG is never perturbed and the same `(op, params, seed)` reproduces byte-for-byte. `compose_augmentations(policy, master_seed)` threads each op a `derive_seed(master_seed, "augmentation:<name>", …)` seed and returns the composed callable that `DataRefineryDataset.__getitem__` applies (or `None` for an empty policy). Visual semantic-equivalence with DataRefinery's Pillow aggressive realizers is verified in Story E.g. Import-safe without the `[pytorch]` extra.

- PyTorch `DataRefineryDataset` adapter (Story C.f): `modelfoundry.plugins.pytorch.data` binds a materialized DataRefinery instance split to a `torch` dataset — decodes uint8 PNGs (sidecar `image_path` over source `path`), applies the train-fitted `normalize`/`mean_subtract` statistics in `Transformations` order (RGB axis, exact `std == 0 → 1.0` zero-variance guard) on every split, derives the label→index map by scanning all labeled splits, and refuses lazy-mode pixel-altering transforms (e.g. `resize`) that aren't baked via sidecars/sinks. `build_dataloader` wires a seeded shuffle `generator` + the spawn-safe `worker_init_fn`, with CUDA-only `pin_memory`. The B.i `DataRefineryInstance` wrapper gains a `fitted_statistics` field.

- PyTorch determinism module (Story C.e): `modelfoundry.plugins.pytorch.determinism.enable_deterministic_algorithms(seed)` sets `CUBLAS_WORKSPACE_CONFIG`, enables `torch.use_deterministic_algorithms(True)`, and seeds CPU/CUDA/MPS RNGs before model construction (idempotent), locking the C.a spike pattern. `documented_hard_error_ops` records ops that hard-error under the guard (empty for the CPU vocabulary). `PyTorchHealthReport` now exposes `documented_hard_error_ops` and sources `deterministic_algorithms_available` from this module.

- PyTorch losses / optimizers / schedules (Story C.d): `modelfoundry.plugins.pytorch.{losses,optimizers,schedules}` register `cross_entropy` / `cross_entropy_class_weighted` / `bce_with_logits`, `adamw` / `sgd` / `adam`, and `reduce_on_plateau` / `cosine` / `linear_warmup` as `OperationSpec`s on the plugin. `derive_class_weights` computes mean-normalized per-class weights (balanced / inverse-frequency / effective-number) from a train-split label distribution; `bce_with_logits` is refused for `num_classes > 2` at build time. All three modules are import-safe without the `[pytorch]` extra (lazy torch in the builders).

- PyTorch architecture vocabulary (Story C.c): `modelfoundry.plugins.pytorch.architecture` registers the CIFAR-10 baseline vocabulary — primitives (`Conv2d`, `BatchNorm2d`, `ReLU`, `MaxPool2d`, `AvgPool2d`, `AdaptiveAvgPool2d`, `Linear`, `Dropout`, `Flatten`), composites (`MLP`, `ConvBlock`, `ResidualBlock`), baselines (`simple_cnn`, `resnet8`, `resnet20` — the canonical 272,474-param CIFAR ResNet-20 with option-B projection shortcuts), and the deferred-but-contract-supported pretrained-encoder path (`Encoder`/`LoRA`/`Pooling`/`Head`, `requires_extras=("huggingface",)`). `build_model` composes a recipe `Architecture:` block (named baseline or explicit `layers`) into an `nn.Module`; the op registry is import-safe without the `[pytorch]` extra. **Cache note:** the new ops perturb canonical recipe bytes only for recipes that select them (acceptable pre-production per `project-essentials.md` § Cache identity); existing recipes are unaffected.

- PyTorch plugin scaffold + `health_check` + registration (Story C.b): `modelfoundry.plugins.pytorch` registers the `pytorch` plugin via the `modelfoundry.plugins` entry point with an (initially empty) `operations` map. `health_check` returns a `PyTorchHealthReport` (torch/torchvision/torchmetrics versions, available accelerators in `Training.device` terms — `cpu`/`cuda`/`mps`, and whether deterministic-algorithm mode is enable-able); every other `Plugin` method is a stub raising `NotImplementedError` until its owning Story (C.c–C.p). The module is import-safe without the `[pytorch]` extra (lazy torch import), so discovery works on sklearn-only installs.

### Fixed

- `worker_init_fn_factory` (`pipeline.seeding`) returned a nested closure that the macOS/Windows `spawn` start method cannot pickle, crashing `DataLoader(num_workers>0)` (Story C.a.1, latent defect surfaced by the C.a determinism spike). It now returns a picklable `functools.partial` over a module-level `_seed_worker`; public API and seeding behavior are unchanged, and a pickle round-trip regression test guards it.

### Changed

- DataRefinery v0.19.0 adoption (Story B.q): bumped the `ml-datarefinery` pin to `>= 0.19.0` and brought the binding contract up to DataRefinery **schema v2** — instances now persist `recipe.json` (not `recipe.yaml`), read via `datarefinery.Instance.load`. ModelFoundry's tracked DR schema set is derived dynamically from `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS` (`{1, 2}`), so the binding gate and validator check 19 picked up v2 with no code change. The new `manifest.class_balance` field (DataRefinery 0.18.0+) is read-and-ignored. Synthesized binding fixtures updated to the v2 / `recipe.json` shape. No package version bump (dependency/test-only change; shares the post-0.3.1 housekeeping release).

## [0.3.1] - 2026-06-11

### Added

- Recipe amendment — `Training.device` execution knob (Story B.n): new `device: Literal["auto", "cpu", "cuda", "mps"] = "auto"` field on `TrainingSpec`. Drives every model-execution stage in the PyTorch plugin (Training, the inner trainings of Optuna Optimization, Evaluation, `predict` / `predict_proba`) — eval and inference implicitly inherit. Validator gains check 20: the requested device must be reported as available by the plugin's `health_check`, or be `"auto"`. Plugins that don't yet expose an `accelerators` field on their health-check result are tolerated with a skip-message.

### Changed

- Documented `Training.device` in [features.md](docs/specs/features.md) (extended QR-5 + new FR-2 check 20), [tech-spec.md](docs/specs/tech-spec.md) (updated `TrainingSpec` block + new "Device resolution" cross-cutting concern), and [README.md](README.md) ("Choosing an accelerator" subsection).
- **Cache invalidation:** the new `Training.device` field's default value participates in canonical recipe bytes, so every existing v0.3.0 ModelInstance is stale and must be re-materialized. This is the deliberate `SUPPORTED_SCHEMA_VERSIONS`-level invalidation that the cache-identity contract documents — explicit `device: cpu` and `device: mps` recipes also produce distinct cache entries by design (no silent collision of cross-device runs on the same key).

## [0.3.0] - 2026-05-30

### Added

- Recipe pydantic models + YAML loader + schema-version gate (Story B.a): `modelfoundry.recipe.models.ModelRecipe` (`frozen`, `extra="forbid"`) with framework-typed and plugin-permissive sub-models; `recipe.loader.load_recipe` wrapping every failure as `RecipeError`.
- Variant overlay (Story B.b): `recipe.variants.apply_variant` deep-merges named overlays and clears `variants` for cache-identity hygiene.
- Canonical bytes + recipe hash (Story B.c): `recipe.canonical` defines the cache-identity input — sort_keys/compact JSON, SHA-256 full digest.
- Cache identity (Story B.d): `cache.identity.CacheKey` and `cache_key()` with the loose-coupling rule; re-materializing DataRefinery into the same triple is a no-op.
- Cache layout (Story B.e): `cache.layout.CachePaths` exposes every instance-directory path with absolute, root-bound resolution.
- Atomic temp-then-promote (Story B.f): `cache.atomic.materialize_temp_dir` context manager + `trash_existing`; FAILED marker on exception, cross-device guard, `ModelArtifactExistsError` on race.
- Manifest model + JSON I/O (Story B.g): `core.manifest.Manifest` with `ManifestWarning`/`OptimizationManifest`/`ExpectationOutcome` sub-models; pretty, byte-stable `write`/`load`.
- Plugin Protocol + discovery (Story B.h): `plugins.base` (`OperationSpec`, `runtime_checkable Plugin`) and `plugins.discovery.discover_plugins` reading the `modelfoundry.plugins` entry-point group plus optional `extra_paths`.
- DataRefinery instance binding (Story B.i): `pipeline.data_binding.resolve_data_instance` locates a materialized DR instance by canonical hash + seed, validates failure modes per the vendor-dep-spec, and returns a `DataRefineryInstance` wrapper.
- Deterministic seeding (Story B.j): `pipeline.seeding.derive_seed` + `worker_init_fn_factory` — output bytes independent of `num_workers`.
- Forward-extensible checkpoint schema (Story B.k): `pipeline.checkpoint.Checkpoint` with pickle persistence; unknown future keys preserved on load.
- OutputExpectations evaluator (Story B.l): `pipeline.expectations.evaluate_expectations` returns one outcome per spec, never raises.
- Recipe validator (Story B.m): `recipe.validator.validate` runs all 19 FR-2 static logical checks against the recipe + bound DataRefinery instance + plugin, never short-circuits, returns a `ValidationReport`.

## [0.2.0] - 2026-05-28

### Added

- Hello World console entry point (Story A.b): `python -m modelfoundry` and the `modelfoundry` console script both print `modelfoundry <version>` via a placeholder `cli.app:main`.
- Integration spike outcome (Story A.c): validated DataRefinery instance binding against real `ml-datarefinery==0.17.0` (`scripts/spike_datarefinery_binding.py`, `docs/spikes/A.c-datarefinery-binding.md`). Locked the source-resolution binding pattern; flagged string-valued labels and a producer-side aggressive-sidecar bug for Story B.i.
- Logging foundation (Story A.d): `modelfoundry.logging` with `JsonFormatter` (one JSON object per line) and `get_logger(name, *, target, level)`; never hijacks the root logger.
- Runtime config (Story A.e): `modelfoundry.core.config.RuntimeConfig` pydantic model with `from_env()`; precedence is CLI > env > defaults.
- Exception hierarchy (Story A.f): `ModelfoundryError` base plus 11 domain subclasses, each carrying optional `recipe_path` / `stage` / `detail` context, re-exported from the package root.

## [0.1.0] - 2026-05-28

### Added

- Project scaffolded (Story A.a): `pyproject.toml` (hatchling, `ml-modelfoundry` distribution, base dependencies + optional extras, `modelfoundry` console script, ruff / mypy `--strict` / pytest config), `src/modelfoundry/` package skeleton (`__init__.py`, `_version.py`, `py.typed`), `tests/conftest.py` placeholder, `requirements-dev.txt`, `README.md`, this `CHANGELOG.md`, `.gitignore`, and the pyve `environment.yml` shell.
