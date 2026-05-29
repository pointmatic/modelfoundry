# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
