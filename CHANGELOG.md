# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
