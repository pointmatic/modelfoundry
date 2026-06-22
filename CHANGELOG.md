# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.14.0] - 2026-06-21

Minor — **MC-dropout aggregation, uncertainty persistence & the `ModelInstance` accessor** (Story H.n,
R2.2 / R2.3): a recipe declaring `Inference: {mode: mc_dropout, mc_samples: T}` now materializes with the
**MC-aggregated mean as the deployed prediction** and **per-record predictive uncertainty** persisted
into `evaluation/predictions.parquet`, reconstructable from disk via `ModelInstance.uncertainty`. This
wires H.m's seeded T-pass mechanism into the evaluation stage. Default single-pass (point-estimate)
recipes are byte-unchanged — the uncertainty columns are additive and MC-only.

### Added

- **MC aggregation** (`plugins/pytorch/stochastic.py`) — `mc_aggregate((T,N,C)) -> MCAggregate` returns the mean class probabilities (point prediction), `predictive_entropy` (entropy of the mean distribution), and `mc_variance` (population variance across passes, averaged over classes) (R2.2). `mc_pass_seed` centralizes the per-pass dropout-salt seed convention.
- **Per-record uncertainty persistence** — on the `mc_dropout` path the evaluation stage runs `mc_samples` seeded active-dropout passes per split, deploys the mean as the prediction, and adds `predictive_entropy` / `mc_variance` columns to `evaluation/predictions.parquet` (R2.3). Deterministic across runs (R2.4).
- **`ModelInstance.uncertainty`** — reconstructs the per-record `[split, record_id, predictive_entropy, mc_variance]` from the persisted instance with no external config (criterion 3); `None` for a single-pass instance.

### Changed

- `Plugin.run_evaluation` gains additive keyword-only `inference` / `seed` parameters (default single-pass when omitted); the runner threads `recipe.Inference` + the master seed. The sklearn/random baselines accept and ignore them (no dropout).

## [0.13.0] - 2026-06-21

Minor — the **MC-dropout stochastic-inference surface** (Story H.m, R2.1 / R2.4): a recipe can declare
`Inference: {mode: mc_dropout, mc_samples: T}` to request **T** seeded active-dropout forward passes,
the foundation for predictive uncertainty (aggregation + persistence land in H.n). Default single-pass
`predict()` / `predict_proba()` point-estimate semantics are unchanged for recipes that omit the block.
**Cache-invalidating:** the new `Inference` recipe field shifts the canonical bytes of every recipe that
omits it — re-materialize existing instances (pre-production OR-9: release-note only; no `schema_version`
bump).

### Added

- **`Inference` recipe block** (`mode: point | mc_dropout`, `mc_samples`) — `point` (the default, and the shape applied when the block is absent) is single-pass with dropout inactive; `mc_dropout` requires an author-declared `mc_samples` (T, target 20-50) (R2.1).
- **MC-dropout mechanism** (`plugins/pytorch/stochastic.py`) — `enable_mc_dropout` keeps only `Dropout`-family modules active under `.eval()`; `mc_forward_proba` runs T forward passes, each seeded from `derive_seed(master_seed, "dropout", pass_index)` so the T-pass sequence reproduces byte-for-byte (R2.4), preserving the four determinism invariants.

### Changed

- Adding the `Inference` field perturbs the recipe canonical bytes; existing cached ModelInstances are stale and must be re-materialized (pre-production OR-9).

## [0.12.0] - 2026-06-21

Minor — activate **`LoRA` adapters** for the pretrained-encoder path and their serialization (Story
H.k, R1.2): `Encoder -> LoRA -> Pooling -> Head` now composes, fine-tunes parameter-efficiently, and
round-trips from disk. **Persistence-format change for the (brand-new) pretrained-encoder path only:**
encoder composites now persist base-from-cache + trainable deltas instead of a full `state_dict.pt` —
re-materialize any v0.11.0 `Encoder` instances (pre-production OR-9: release-note only; baseline
recipes are byte-unchanged; no `schema_version` bump; recipe canonical bytes unaffected).

### Added

- **`LoRA` op** (`rank`, `alpha`, `dropout`, `target_modules`) — peft injects trainable low-rank adapters into the encoder's named modules while the base stays frozen (R1.2). `target_modules` names the encoder's attention linears (e.g. transformers-5.x ViT `q_proj`/`v_proj`, per the H.i spike).
- **Composite serialization (Q3 decision, H.i/H.k)** — `save_model`/`load_model` persist the pretrained-encoder composite as the trainable head/pooling + (when LoRA) the peft adapter deltas (`weights/composite.pt`, ~hundreds of KB), with the base encoder re-fetched from the offline warm cache via `architecture.json`'s `Encoder.id`. `ModelInstance.load(path).predict(X)` reproduces a LoRA instance's predictions from disk with no external config (criterion 9).

### Changed

- Pretrained-encoder composites (both frozen-encoder and LoRA) no longer re-persist the base encoder weights into `state_dict.pt`; they use the new `composite.pt` format. Baseline (`type:`) recipes are unaffected — they keep the full-`state_dict` path byte-for-byte.

## [0.11.1] - 2026-06-21

Patch — add the DR↔MF input-shape/preprocessing contract as FR-2 **validator check 21** (Story H.j.3),
so a data↔model input mismatch fails at `validate()` with an actionable message instead of a deep
materialize-time crash (or silent degradation). Not cache-invalidating (a validate-time check changes
no materialized bytes); no `schema_version` bump.

### Added

- **FR-2 check 21 (`architecture_input_compat`)** with two guards of the same data↔model interface family the Story H.a normalization-units bug belonged to:
  - **Input shape** — a pretrained `Encoder`'s fixed input resolution + channel count (introspected offline from the encoder config via `AutoConfig`, config-only, no weights) must match the bound DataRefinery instance's produced image shape (`record_schema`). Per R1.4 this guard **no-ops when `transformers` is absent** so `validate()` still succeeds without the `[huggingface]` extra.
  - **Normalization scale** — the PyTorch adapter applies fitted `normalize` stats in **0-255 pixel units** (Story H.a); fitted means that look `[0,1]`-scale are flagged as a units mismatch. Encoder-independent and torch/transformers-free, so it runs for **every** recipe — closing the Story H.c-filed "validate-time normalization sanity check" follow-up.

### Changed

- The synthetic DataRefinery test fixtures (`build_dr_instance`, the cifar10-smoke builder, and the two CLI-test local builders) now emit **realistic 0-255-scale** normalize statistics, matching how DataRefinery fits on raw pixels and how the adapter applies them — `[0,1]`-scale fixtures would (correctly) trip check 21.

## [0.11.0] - 2026-06-21

Minor — activate the pretrained-encoder architecture path (Story H.j.1, R1.1/R1.3/R1.4/R1.5): the
PyTorch plugin now composes a HuggingFace `Encoder` → `Pooling` → `Head` into a trainable classifier
behind the `[huggingface]` extra. Additive; existing recipes' canonical bytes and materialized output
are unchanged (the ops were already in the registered vocabulary; no field defaults changed) — no
cache impact, no `schema_version` bump. **LoRA is not yet active** (Story H.k).

### Added

- `Encoder` op (`source: huggingface`, `id`, `frozen`): instantiates a pretrained encoder by id from the **offline warm HF cache** (`local_files_only=True`; no run-time network), honoring `frozen` to freeze/unfreeze encoder weights (R1.1/R1.5).
- `Pooling` op (`mean` | `max` | `attention`) over the encoder's token sequence and a classification `Head` (`mlp`, `hidden_dims`, `num_classes`, `id2label`) composed over the pooled features (R1.3). The composite's `forward` runs the encoder on `pixel_values` (the R1 image modality), pools, then classifies.
- An `Encoder` + `Pooling` + `Head` recipe now materializes a `ModelInstance` end-to-end via `materialize()` when `[huggingface]` is installed, and reproduces offline across re-materializes (criteria 1–2). Weight-init/dropout for the fresh head/pool (and any HF-initialized submodule) is seeded by the existing `prepare_for_build(seed)` discipline, preserving the determinism invariants.

### Changed

- The deferred-path stub (`_require_huggingface`, which raised `NotImplementedError`) is replaced by the real composite build path. The extras gate is preserved (R1.4): without `[huggingface]`, a recipe referencing these ops fails at materialize time with the install pointer while recipe load/validate still succeed against the in-tree vocabulary.

## [0.10.2] - 2026-06-17

Patch — gate restore-best-weights on early stopping (Story H.f.10), correcting the over-applied
v0.10.1 restore. **Cache-invalidating** for recipes that train **without** early stopping:
materialized weights/evaluation change (the converged final model instead of an early best-monitor
epoch); re-materialize (pre-production OR-9; no `schema_version` bump). Early-stopping recipes are
byte-identical to v0.10.1.

### Fixed

- v0.10.1 restored the best-monitor weights into the model **unconditionally** at the end of `run_training`. That is correct *with* early stopping, but for a full-schedule (no-early-stopping) run it restored an early best-monitor epoch instead of the converged final model. The default monitor is `val_loss`, whose minimum under a cosine anneal lands very early (it then rises from overconfidence while `val_accuracy` keeps improving), so the canonical 160-epoch ResNet-20 benchmark shipped the epoch-8 model and scored test 0.7312 instead of the converged **0.7764**. Restore is now gated on `Training.early_stopping` being configured (restore_best_weights semantics); with no early stopping the converged final model is kept. Guarded by `test_final_weights_kept_when_no_early_stopping`.

## [0.10.1] - 2026-06-17

Patch — restore the best-monitor checkpoint into the evaluated/persisted model (Story H.f.8).
**Cache-invalidating** for recipes that early-stop with best ≠ final epoch: materialized
weights/evaluation change; re-materialize (pre-production OR-9; no `schema_version` bump).

### Fixed

- The trainer tracked and promoted the best-monitor weights, but the runner evaluated — and `save_model` persisted — the in-memory **final-epoch** model; `run_training` never restored the best weights. With early stopping the final epoch is `patience` epochs of non-improvement past the best, so every early-stopping run shipped a stale model (and the on-disk best checkpoint was overwritten with it). This disproportionately penalized models that early-stop aggressively (ResNet-20): post-fix, full-data `resnet20` recovers from 0.646 → 0.679, and the H.f.7 `simple_cnn`-edges-`resnet20` reversal flips back to the canonical ordering (`resnet20` 0.679 > `simple_cnn` 0.672). `run_training` now snapshots the best-monitor `state_dict` and restores it before returning. Guarded by `test_best_weights_are_restored_into_model_after_early_stop`.

## [0.10.0] - 2026-06-17

Minor — add a first-class **random/chance baseline plugin** (Story H.f.2): the comparison floor
every real model must beat, as a fully-baked, recipe-driven, reproducible ModelInstance. Additive;
no change to existing recipes' canonical bytes or materialized output; no cache impact.

### Added

- New `random` plugin (registered under the `modelfoundry.plugins` entry point), backed by scikit-learn's `DummyClassifier`. It implements the complete `Plugin` Protocol by subclassing the sklearn baseline — reusing its (estimator-agnostic) training / evaluation / persistence path — and overriding only `build_model` and the op set. A `dummy_classifier` architecture op (`strategy: stratified | uniform | prior | most_frequent`, default `stratified`) plus the recognized no-op `Loss` (`cross_entropy`) and `Optimizer` (`none`) ops its recipe declares, so the recipe validates end-to-end. Deterministic (the estimator's `random_state` is seeded from the master seed, FR-25). Supersedes the ad-hoc numpy chance computation in `scripts/examples/test_random_classifier.py`. Ships the teaching recipe `recipes/cifar10_random.yml`.

## [0.9.3] - 2026-06-17

Patch — make scikit-learn baseline recipes pass `validate()` and let their `Optimizer` block
drive the estimator (Story H.f.1). No change to existing materialized output; no cache impact.

### Fixed

- The `sklearn` baseline plugin registered **only** its `mlp_classifier` architecture op, so every `plugin: sklearn` recipe failed the documented `modelfoundry validate` step with `ops not registered by plugin 'sklearn': [('Loss', 'cross_entropy'), ('Optimizer', …)]` — even though `materialize()` (which does not gate on `validate()`) trained fine, leaving the breakage silent. The plugin now registers the `cross_entropy` loss op and `adam` / `sgd` optimizer ops its recipes declare, so they validate end-to-end through the public surface.

### Changed

- The sklearn baseline's `Optimizer` block is no longer decorative: `Optimizer.op` (`adam` / `sgd`) maps to the `MLPClassifier` `solver` and `Optimizer.learning_rate` maps to `learning_rate_init` at fit time (RNG still seeded deterministically from the master seed). Ships two minimal teaching recipes for the upcoming model-swap tutorial — `recipes/cifar10_mlp.yml` (sklearn) and `recipes/cifar10_cnn.yml` (PyTorch `simple_cnn`).

## [0.9.2] - 2026-06-17

Patch — apply lazy augmentations *before* normalization so the CNN can generalize (Story H.d).
**Cache-invalidating** for recipes whose bound instance declares a lazy `Augmentations` policy:
materialized training output changes; re-materialize (pre-production OR-9; no `schema_version` bump).

### Fixed

- The PyTorch `DataRefineryDataset` adapter applied lazy augmentations to the **already-normalized** (standardized) tensor. Color augmentations (`color_jitter` brightness/contrast/saturation/hue) assume `[0,1]`/uint8 image semantics, so applied to the ~`N(0,1)` tensor they produced a garbage train distribution that didn't match the clean (un-augmented) val/test — `val_loss` exploded (→ ~15) and ResNet-20 generalized at chance (test accuracy ~0.13, **below** a flattened-pixel sklearn MLP baseline at 0.34). The adapter now augments on the `[0,1]` image and normalizes afterward (standard pipeline order); the H.a normalization result is unchanged on the no-augmentation path. Guarded by a spy test asserting the augmentation receives a `[0,1]`-ranged image.

## [0.9.1] - 2026-06-17

Patch — make lazy augmentations spawn-safe so the flagship CIFAR-10 / ResNet-20 recipe can
materialize on macOS (Story H.b). No output-byte change for existing instances.

### Fixed

- Lazy augmentation realizers and the policy composer were Python **local closures** (`build_realizer.<locals>.crop`, `compose_augmentations.<locals>.apply`), which cannot be pickled. With `Training.num_workers >= 1` under the macOS `spawn` start method, `DataLoader` worker creation pickles the dataset (carrying its transform) and crashed with `AttributeError: Can't get local object …` — so `recipes/cifar10_resnet20.yml` (`num_workers: 2`) died on the first optimization trial and could not materialize on the first-class platform (QR-4). The realizers are now module-level picklable classes (`_HorizontalFlip` / `_RandomCrop` / `_ColorJitter` / `_RandomErasing`) and the composer a `_ComposedTransform` class; `torch` / `torchvision` stay lazily imported in `__call__`, and the seeding/visual semantics are unchanged (the Hypothesis equivalence tests still pass). Guarded by pickle round-trip tests and an augmentations × `num_workers ∈ {0, 2}` invariance test.

## [0.9.0] - 2026-06-16

Minor — add a public **pre-materialize architecture summary** to the library/CLI-equal surface
(Story H.a.2). Backend-agnostic; no new runtime dependency; no cache impact.

### Added

- `ModelFoundry.summary() -> dict[str, Any]` (FR-27 surface): builds the recipe's model via the plugin and returns its structured summary — `total_params` / `trainable_params` / `non_trainable_params` / per-layer `layers` rows + a top-level `output_shape` (the network's final output, e.g. `[1, 10]`) — **without** `materialize()` / training and **without** any framework import in caller code. The PyTorch plugin contributes the in-memory `summarize_model(model, data)` (the torchinfo sibling of `write_model_summary`); plugins without it raise `PluginError`. This closes the gap that previously forced architecture inspection through `plugins.pytorch.architecture.build_model` + a direct `torch` import (see `scripts/examples/test_models_resnet20_fix.py`, whose strict-xfail spec drove this feature).

## [0.8.4] - 2026-06-16

Patch — fix a normalization-units bug that prevented the PyTorch plugin's models from learning
(Story H.a). **Cache-invalidating:** materialized output bytes change; existing ModelInstances are
stale — re-materialize (pre-production OR-9; no `schema_version` bump, the recipe canonical bytes are
unaffected).

### Fixed

- The `DataRefineryDataset` adapter applied DataRefinery's `normalize` / `mean_subtract` statistics — fitted in **0–255 pixel units** — to a `[0,1]`-rescaled image, collapsing every pixel to ≈ −1.9 (std ≈ 0.13). Training was starved of signal: `train_loss` pinned at ln(10) ≈ 2.303 and the CIFAR-10 / ResNet-20 deliverable trained to chance (test accuracy 0.10). The adapter now decodes in DR's 0–255 pixel units and standardizes there (falling back to `[0,1]` only when no fit-on-train normalization is declared), so `train_loss` drops and the model learns. Regression-guarded by realistic-scale unit tests in `tests/unit/test_pytorch_data_adapter.py` (the prior fixtures used unrealistic `[0,1]`-scale stats, which is why the suite missed the bug) and a `train_loss` learning-floor assertion in `tests/integration/test_cifar10_resnet20.py`.

## [0.8.3] - 2026-06-16

Patch — adopt `ml-datarefinery` 0.21.0 as the minimum supported upstream. No runtime behavior
changed; ModelFoundry's full suite (framework-agnostic + PyTorch smoke, including the CIFAR-10
binding/integration pipeline) passes against 0.21.0 unchanged.

### Changed

- Raised the `ml-datarefinery` floor `>=0.20.0` → `>=0.21.0` (Story G.e). Kept the `>=` lower-bound operator (idiomatic for a published library's runtime dependency). Verified against a real 0.21.0 install — the data-binding unit tests and the full CIFAR-10 integration pipeline (which bind a DataRefinery instance) pass with no code changes, confirming the loose-coupled binding (FR-6) holds across the bump.

## [0.8.2] - 2026-06-15

Patch — a third clean-environment CI fix, surfaced once the Linux runner (now installing pyve
cross-platform) ran the full suite. No runtime behavior changed.

### Fixed

- CLI no longer line-wraps printed file paths (Story G.d): the `report`, `init`, and `inspect` verbs printed `… → <path>` via rich, whose 80-column no-TTY fallback (CI) wrapped long paths mid-string — splitting `report.md` and breaking both copy-paste and the path assertion. The three call sites now pass `soft_wrap=True`. Guarded by a width-pinned regression test in `tests/cli/test_report_cmd.py`.

## [0.8.1] - 2026-06-15

Patch — clean-checkout reproducibility fixes surfaced by the new CI workflow on its first run.
Two files present in a working dev tree were absent from a fresh clone, failing five tests in CI
(four `FileNotFoundError`, one broken cross-link). No runtime behavior changed.

### Fixed

- Bundled base recipe reaches a clean checkout (Story G.c): `recipes/cifar10-base.yaml` — bound by the CLI + integration tests, the README quickstart, and the `cifar10_resnet20` deliverable — was swallowed by the `recipes/cifar10*.yaml` .gitignore pattern, so CI's clean checkout hit `FileNotFoundError`. The pattern now negates the bundled base recipe, and the file is tracked. Guarded by `tests/unit/test_bundled_recipes_committed.py` (exists / not-ignored / tracked).
- Cross-link guard tolerates install output (Story G.c): `tests/unit/test_docs_crosslinks.py` no longer flags spec links into `docs/project-guide/` — that tree is tool-generated install output (regenerated by `project-guide init`), intentionally uncommitted and absent from a clean checkout. Same exclusion model as the vendored sibling-project copies.
- Cross-platform pyve install in CI (Story G.c): `ci.yml` installs pyve via its own `self install` (clone `pointmatic/pyve` → `pyve.sh self install` → `~/.local/bin`) instead of Homebrew, which is unavailable on GitHub's ubuntu image and failed the Linux (stretch) runner at the install step. Guarded by `tests/unit/test_ci_workflow.py` (`self install` present, `brew install` absent).

## [0.8.0] - 2026-06-15

Phase G release — CI/CD automation and the first PyPI publish for `ml-modelfoundry`. A GitHub
Actions CI workflow runs lint + format + types + the PyTorch smoke suite (incl. the CIFAR-10
end-to-end smoke) on every PR and push to `main`; a tag-triggered publish workflow ships the
sdist + wheel to PyPI via Trusted Publishing (OIDC, no API token). The `src/` + `tests/`
formatting was normalized to a pinned ruff so the format gate is reproducible. No runtime
behavior changed.

### Added

- CI workflow (Story G.a, OR-12 / TR-16): `.github/workflows/ci.yml` — a single `build` job over a macOS-Apple-Silicon-primary / Linux-stretch matrix (`fail-fast: false`, Linux `continue-on-error`), provisioning the pyve `testenv` / `typecheck` / `smoke-pytorch` envs to run `ruff check`, `ruff format --check`, `mypy --strict`, and the full PyTorch smoke suite. Guarded by `tests/unit/test_ci_workflow.py`.
- Publish workflow (Story G.b, OR-11 / AC-13): `.github/workflows/publish.yml` — fires on `v*.*.*` tag pushes, builds the sdist + wheel and uploads to PyPI via Trusted Publishing (`id-token: write`, `pypa/gh-action-pypi-publish`; no token in secrets). Guarded by `tests/unit/test_publish_workflow.py`.

### Changed

- Pinned `ruff==0.15.17` (Story G.a) in `requirements-dev.txt` so the `ruff format --check` CI gate is reproducible across runners and ruff releases.
- Normalized the `src/` + `tests/` formatting backlog to the pinned ruff (Story F.d): 45 files reformatted (whitespace / line-wrap only) so the format gate is green; one stranded `# type: ignore[arg-type]` relocated to the line mypy reports. No behavior change.

## [0.7.0] - 2026-06-15

Phase F release — documentation polish and release prep. A release-ready README with the
CIFAR-10 quickstart, a public-API docstring pass backed by a permanent docstring-quality +
cross-link gate, a reconciliation of the env-topology docs (and the `testenv` itself) to the
live venv multi-env layout, and a CHANGELOG + `pyproject.toml` metadata audit. No runtime
behavior changed; the package is ready for its first tagged release (the PyPI publish lands in
Phase G).

### Added

- README quickstart + walkthrough (Story F.a, UR-6): replaced the A.a placeholder `README.md` with the release-ready document — install, the two-step CIFAR-10 quickstart over the bundled recipes, the `ModelFoundry.from_recipe(...).materialize()` library example, the eight-verb CLI surface, the notebook-substrate-neutral `IPython.display.Image(mi.figures[...])` example, and pointers into `docs/specs/`.
- Docstring-quality + cross-link gates (Story F.b): enabled ruff's pydocstyle (`D`) quality rules (`convention = "google"`, the `D1xx` missing-docstring mandates excluded) so the public-API docstrings are checked on every lint; new `tests/unit/test_docs_crosslinks.py` validates every relative link in the first-party `docs/specs/*.md` resolves (vendored sibling-project copies excluded).
- Env-topology + release-metadata guard tests (Stories F.b.1 / F.b.2 / F.c): `tests/unit/test_env_docs_topology.py` pins the docs to the live venv multi-env layout (and that `testenv` is described as the framework-agnostic test runner); `tests/unit/test_release_metadata.py` pins the CHANGELOG-top-version == `__version__` and the PEP 639 SPDX-license invariants.
- `requirements-test.txt` (Story F.b.2): the `[env.testenv]` dependency set — base `-e .` (no torch) + `-r requirements-dev.txt` — so plain `pyve test` runs the framework-agnostic suite (the torch tests skip via `importorskip` and run in `smoke-pytorch`).

### Changed

- Public-API docstrings tightened to release quality (Story F.b): full one-line-summary + Args/Returns/Raises (+ FR references) on `ModelFoundry`, `ModelInstance`, the top-level `materialize`, and the `InspectionView` accessors. Corrected the stale `ModelInstance` accessor contract across `concept.md` / `features.md` / `tech-spec.md` to the shipped shape — `.metrics` is an alias for `.evaluation` (a per-split dict, not a per-epoch DataFrame), `.figures` returns PNG `bytes` (not `matplotlib.figure.Figure`), and `.calibration` / `.predictions` are a single `DataFrame | None`.
- Env-topology docs reconciled to the venv multi-env layout (Story F.b.1, supersedes B.o / B.p): rewrote `docs/specs/env-dependencies.md` (and the env sections of `tech-spec.md` / `concept.md`) from the obsolete two-micromamba design to the `pyve.toml` venv layout — `root` / `testenv` + lazy `smoke-pytorch` / `smoke-tensorflow` / `smoke-huggingface` / `typecheck` (all `backend = venv`); the B.o / B.p story bodies are marked superseded.
- `testenv` re-described and re-wired as the framework-agnostic test runner (Story F.b.2): `[env.testenv]` now installs the base package closure (`requirements-test.txt`), so the default `pyve test` runs every test that doesn't need a framework extra; `smoke-pytorch` owns the torch tests. The coverage matrix and env specs were corrected accordingly.
- Release metadata audit (Story F.c): `pyproject.toml` classifiers add `Programming Language :: Python :: 3 :: Only`; `twine` added to `requirements-dev.txt` for the `twine check` release gate. **Owns the Phase F v0.7.0 bump.**

### Fixed

- Three torch-dependent CLI tests now skip cleanly in the torch-free `testenv` (Story F.b.2): `test_app.py::test_shared_flag_reaches_the_callback` and `test_validate_cmd.py::test_cli_validate_passing_recipe_exits_0` were failing (the `check` verb / pytorch-recipe validation need the pytorch plugin), and `::test_cli_validate_failing_recipe_exits_1` was passing for the wrong reason (a missing-plugin check 2 masking the intended check 12) — all three gained `pytest.importorskip("torch")`.
- Seven broken first-party cross-links in `stories.md` (Story F.b): repo-root-relative test/source links that 404 from `docs/specs/` were corrected to the established `../../` relative form.

## [0.6.0] - 2026-06-15

Phase E release — the complete test & quality suite, capped by the CIFAR-10
end-to-end smoke. Every contract surface now has dedicated coverage: the
loose-coupling guarantee, the PyTorch plugin (metric goldens, sampler
determinism, augmentation-equivalence property tests), OutputExpectations, the
plugin Protocol contract, the full CLI verb surface, the notebook-substrate
smoke, and a downsized CIFAR-10 capstone that exercises optimization → training →
evaluation → expectations → predictions → from-disk round-trip on a CPU budget.

### Added

- v0.6.0 CIFAR-10 end-to-end smoke (Story E.l, TR-12 / AC-2): `tests/integration/test_cifar10_smoke.py` materializes a downsized, CPU-budget CIFAR-10-shaped vertical (`simple_cnn`, a real 2-trial Optuna study + multi-epoch fit, eval on val/test) over the new synthesized `tests/fixtures/datarefinery_instances/cifar10_smoke/builder.py` instance (10 classes, 32x32 RGB, ~500/100/100, a 10-colour learnable palette) and `tests/fixtures/recipes/cifar10_smoke.yml`, asserting the val `macro_f1` floor, all OutputExpectations passing, the persisted `predictions.parquet` shape, and the FR-23 from-disk `predict` round-trip. **Owns the Phase E v0.6.0 bump.**
- Loose-coupling guarantee test (Story E.f, TR-7): `tests/integration/test_loose_coupling.py` pins that re-materializing DataRefinery with the same shape/seed leaves ModelFoundry's cache identity unchanged (a recognized cache hit), a changed DR seed is a correct cache miss, and ModelFoundry never writes into DataRefinery's cache tree.
- PyTorch plugin tests (Story E.g, TR-9 / TR-10): `tests/unit/test_pytorch_metrics.py` (hand-computed goldens for all eight metrics), expanded `tests/integration/test_pytorch_optimization.py` (Random + Grid sampler determinism, `n_jobs > 1` rejection), and expanded `tests/unit/test_pytorch_augmentations.py` (Hypothesis cross-realizer visual-semantic equivalence vs DataRefinery's aggressive realizers).
- OutputExpectations tests (Story E.h, TR-11): `tests/unit/test_output_expectations.py` (gate-level surfacing of every failure, validate-time catch of dangling metrics) + `tests/integration/test_failing_expectations.py` (a failing expectation aborts to a `FAILED` marker).
- Plugin contract tests (Story E.i): `tests/plugin_contract/` pins both plugins' exhaustive `OperationSpec` sets, runtime + static `Plugin` Protocol conformance, `health_check()` shape, and the sklearn `MLPClassifier` end-to-end.
- CLI smoke tests (Story E.j): `tests/cli/test_cli_<verb>.py` drive all eight verbs end-to-end through `CliRunner`, asserting exit codes, `rich` output, and the JSON-lines log channel.
- Notebook Jupyter smoke (Story E.k, TR-8): `tests/notebook/test_jupyter_smoke.py` executes a `materialize` in a real `nbclient`/`ipykernel` kernel and asserts the notebook-shaped accessors; the `smoke-pytorch` env carries the `[notebook-smokes]` extra.
- Test fixture foundation + property/round-trip/determinism suites (Stories E.a–E.e.1): shared `conftest`, the synthesized DataRefinery builder, validator-check tests, Hypothesis cache-identity properties, atomic-promote / checkpoint tests, and determinism + round-trip integration tests (including the E.e.1 weight-init-before-`build_model` determinism repair).

## [0.5.0] - 2026-06-15

Phase D release — the complete Typer-based CLI surface. All eight verbs
(`init` / `validate` / `check` / `status` / `materialize` / `report` /
`inspect` / `clean`) are now wired over the shared `ModelFoundry` /
`ModelInstance` library API, so the CLI and library stay co-equal. A developer
can scaffold a recipe, validate it, materialize it (with live per-stage /
per-epoch / per-trial progress), and report / inspect / clean the results
entirely from the shell against a real DataRefinery instance.

### Added

- v0.5.0 `init` deterministic scaffolder (Story D.i, FR-21): new `modelfoundry.scaffolder` package — `scaffolder.init.scaffold_recipe(recipe_path, datarefinery_recipe_path, *, plugin="pytorch", force=False, config=None) -> Path` resolves the bound DataRefinery instance and writes a dataset-shaped baseline recipe (PyTorch: a `resnet20` classifier with `num_classes` from `instance_num_classes()` and `in_channels` read from the DR record-schema image shape; sklearn: an `mlp_classifier`), plus a baseline `cross_entropy` loss, `adamw` optimizer, `Training` policy (early-stopping on `val_loss` when a val split exists), `accuracy` / `macro_f1` / `confusion_matrix` evaluation on the test/val split, and a better-than-chance `OutputExpectations` assertion. The recipe is stamped with the Apache-2.0 / Pointmatic header as a YAML comment and is deterministic. `modelfoundry init <recipe> --data <dr-recipe> [--plugin] [--force]` (`cli.commands.init_cmd`) drives it; `--force` is required to overwrite. Reserved `scaffolder.llm` placeholder marks the deferred `[llm]` natural-language path (not implemented pre-production). **Owns the Phase D v0.5.0 bump.**
- `clean` command (Story D.h, FR-20): new `modelfoundry.cache.cleaner` (`parse_duration`, `select_targets`, `remove_targets`) + `cli.commands.clean_cmd`. `modelfoundry clean` removes cached ModelInstances by composable selector — `--recipe-hash <hash>` (the whole recipe tree), `--older-than <dur>` (promoted instances by `manifest.created_at` + `.trash/` by mtime), `--failed` (temp dirs with a `FAILED` marker), `--orphans --older-than <dur>` (un-marked stale temp dirs) — with `--dry-run` reporting and descendant-pruning de-dup. No matches → exit 0 "nothing to clean"; a removal failure → exit 2 with the partial state reported.
- `inspect` command + `InspectionView` (Stories D.g / D.g.1, FR-17): `ModelInstance.inspect(view="<name>")` renders a single view on demand (PNG bytes via the plugin's `render_visualization`, or the `Manifest` for `view_manifest`); the no-arg `ModelInstance.inspect()` returns an `InspectionView` with the notebook-facing accessors `view_training_curves()`, `view_confusion_matrix(split)`, `view_calibration(split)`, `view_predictions(split, n)`, `view_trials()`, `view_manifest()` (each raising `InspectionError` when its stage is unfilled). `modelfoundry inspect <instance> --view <name>` (`cli.commands.inspect_cmd`) writes PNG views to a temp file and prints the path, or renders the manifest as a `rich` table.
- `report` command (Story D.f, FR-18): `modelfoundry report <instance>` (`cli.commands.report_cmd`) loads a materialized instance (plugin resolved from the manifest), atomically re-renders `report/` via `ModelInstance.render_report()`, and prints the report path.
- `materialize` command + progress (Stories D.e / D.e.1, FR-3): `modelfoundry materialize <recipe> [--variant] [--seed] [--overwrite] [--progress/--no-progress]` (`cli.commands.materialize_cmd`) runs the full pipeline and prints a `rich` summary panel. A `StageObserver` seam on `MaterializeRunner` (rendered by the CLI's `RichStageProgress`) streams per-stage progress; D.e.1 adds a `ProgressReporter` Protocol threaded to the plugins so the PyTorch trainer emits per-epoch rows and Optuna optimization emits per-trial events (wrapping trial > 0 in the reusable `pipeline.progress.suppress_fd_output` fd-level redirect; trial 0 prints normally).
- `status` command (Story D.d, FR-16): `modelfoundry status <recipe>` (`cli.commands.status_cmd`) resolves the cache key and reports whether the instance is materialized, rendering the manifest summary (plugin, hashes, seed, variant, timestamp, elapsed, primary metric, expectation pass/fail counts) when present, or the expected path when absent.
- `check` command (Story D.c, FR-19): `ModelFoundry.check_environment(config)` discovers every plugin and runs each `health_check()` (no recipe); `modelfoundry check` (`cli.commands.check_cmd`) renders Python / ModelFoundry versions + a per-plugin availability / accelerators / versions table, exiting non-zero when any discovered plugin is unavailable (its extras are missing). The `Plugin` Protocol's `CheckReport` forward stub is refined to a structural Protocol.
- `validate` CLI command (Story D.b, FR-2): `modelfoundry validate <recipe>` binds the recipe to its DataRefinery instance (the validator cross-checks splits / class count / schema version against the bound instance), runs `ModelFoundry.validate()`, renders the `ValidationReport` as a `rich` table (per-check id / name / ✓pass-✗fail / detail) with a pass/fail summary line, and exits `0` when every check passes, `1` otherwise. Lives in the new `modelfoundry.cli.commands` package (`validate_cmd.run` + `render_validation`), which the `app.py` verb delegates to via a `_config(ctx)` helper that reads the shared-option `RuntimeConfig` off the Typer context. Note: the check that a recipe's `Training.device` is an available accelerator (FR-2 check 20) depends on the plugin's `health_check`, so validating a `pytorch` recipe in an environment without `torch` installed honestly reports `device: cpu` as unavailable — run `validate` in an env carrying the `[pytorch]` extra. Unversioned — rides the Phase D release bundle.

- CLI scaffolding (Story D.a, `tech-spec.md` § CLI Design): `modelfoundry.cli.app` is now the real `typer` application backing the `modelfoundry` console script (replacing the A.b version-print placeholder). A root `typer.Typer()` with an `@app.callback()` that turns the **shared options** — `--cache-root`, `--data-cache-root`, `--log-level`, `--log-target`, `--plugin-path`, `--verbose` / `-v`, `--quiet` / `-q`, plus `--version` — into a per-invocation `RuntimeConfig` on the Typer context (precedence CLI > env > defaults via `RuntimeConfig.from_env`; `--verbose` / `--quiet` are `log_level` shorthands and conflict as a usage error). `exit_code_for(exc)` maps exceptions to the documented exit codes — `0` success, `1` user/recipe/contract error (`RecipeError` / `ValidationError` / `DataBindingError` / `ExpectationError` / `ModelArtifactExistsError` / `InstanceError`), `2` system/plugin error (`PluginError` / `MaterializeError` / `CacheError` / `OptimizationError` / `InspectionError`) and unexpected exceptions, `130` SIGINT — and `invoke` / `main` run the app with `standalone_mode=False` so the CLI (not click) owns error rendering + the process exit code. All eight verbs (`init` / `validate` / `check` / `status` / `materialize` / `report` / `inspect` / `clean`) are registered as stubs, each fleshed out by its own Phase D story. Unversioned — rides the Phase D release bundle.

## [0.4.0] - 2026-06-14

Phase C release — the end-to-end PyTorch plugin vertical: architecture vocabulary
+ `resnet20`, losses/optimizers/schedules, determinism, the `DataRefineryDataset`
adapter + lazy augmentations, the deterministic trainer, Optuna optimization,
evaluation, visualizations, persistence + from-disk round-trip, the torchinfo
model summary, a working sklearn `MLPClassifier` baseline, reporting, the
materialize orchestrator, the `ModelFoundry` / `ModelInstance` library API, and
the CIFAR-10 / ResNet-20 client deliverable.

### Added

- CIFAR-10 / ResNet-20 deliverable (Story C.r, FR-3 / FR-22): `recipes/cifar10_resnet20.yml` — the real-shape client deliverable. A ResNet-20 image classifier over the materialized DataRefinery DR-1 instance (1,700 / 300 / 1,000 balanced CIFAR-10), `Training.device: cpu`, with an Optuna **TPE + median-pruning** study over `Optimizer.learning_rate` (log-uniform 1e-4..1e-2), `Optimizer.weight_decay` (log-uniform 1e-5..1e-2), `Training.batch_size` (`{32, 64, 128}`), and `Training.early_stopping.patience` (5..15); the best config is auto-applied at final training. The R5 **AdamW vs SGD+momentum** and **reduce_on_plateau vs cosine** comparisons ship as `variants:` rather than search dimensions — the flat Optuna search space can't carry op-conditional params (cosine's required `T_max` collides with `reduce_on_plateau`'s `extra="forbid"`, and SGD's `momentum` breaks an AdamW trial) — alongside a `cpu_budget` quick-run variant and a documented `random`-sampler fallback. **CPU-budget calibration (measured):** ≈7 s/epoch over the 1,700-image train split on Apple-silicon CPU (≈10–12 s at `batch_size 32`); the full 20-trial study is minutes-scale, the `cpu_budget` variant ≈5–7 min. A downsized fixture (`tests/fixtures/recipes/cifar10_resnet20.yml`) drives the end-to-end test (`tests/integration/test_cifar10_resnet20.py`): materialize → `model/summary.json` pins ResNet-20's 272,474 params → the study persists `best-params.json` and final training applies them → val/test accuracy computed → FR-23 `ModelInstance.load().predict()` round-trip. The test binds the real instance via DataRefinery's `resolve_instance` and **skips cleanly** on hosts where DR-1 isn't materialized under `./data`. Owns the Phase C **v0.4.0** bump.

- PyTorch model summary (Story C.q, FR-27): new `modelfoundry.plugins.pytorch.summary` — `summarize(model, input_size)` runs `torchinfo` once (eval-mode probe, training flag restored, no side effect on the persisted model) and returns a structured `ModelSummary` (ordered per-layer rows of `type` / `output_shape` / `param_count` / `trainable_params` / `mult_adds` + network totals `total_params` / `trainable_params` / `non_trainable_params` / `total_mult_adds`) plus the text render; `write_summary` writes the byte-deterministic `model/summary.txt` + `model/summary.json` (no timestamps, canonical-sorted JSON); `derive_input_size` reads the bound instance's record-schema image shape (HWC → `(1, C, H, W)`, decoding one record as a fallback). The materialize runner writes the summary after Persistence via the **optional, duck-typed** `PyTorchPlugin.write_model_summary(model, data, model_dir)` capability — plugins without it (sklearn) skip the step cleanly, keeping the runner plugin-agnostic. `ModelInstance` gains `summary` (structured `summary.json`) and `summary_text` (`summary.txt`) cached-property accessors; the `inspect --view model_summary` CLI surface (FR-17) lands with the CLI in Story D.g and reads `summary_text`. `torchinfo>=1.8` added to the `[pytorch]` extra. `CachePaths` gains `summary_txt` / `summary_json`.

- `ModelFoundry` library API + `ModelInstance` (Story C.p): `modelfoundry.core.modelfoundry.ModelFoundry.from_recipe(recipe_path, *, data, config, variant, seed)` builds the shared binding (recipe + DataRefinery instance + plugin + cache key) and exposes the verbs `validate` / `materialize` / `status` / `inspect` / `report` / `clean` / `check`; the top-level `materialize(...)` is the one-call convenience. `modelfoundry.core.instance.ModelInstance` is the frozen, notebook-shaped result object with cached-property accessors (`metrics`, `evaluation`, `confusion_matrix`, `calibration`, `predictions`, `trials`, `best_params`, `figures`), plugin-delegated `predict` / `predict_proba`, a `load(path)` classmethod (resolves the plugin from the manifest — FR-23 from-disk), and `render_report()`. The materialize runner now persists `recipe.yml` into the instance so it is self-contained. `ModelFoundry`, `ModelInstance`, and `materialize` are re-exported from the top-level `modelfoundry` package.

- Materialize orchestrator (Story C.o): `modelfoundry.pipeline.runner.MaterializeRunner.run() -> Manifest` sequences the full FR-3 materialization atomically — Architecture → Optimization (best-params merge-back + model rebuild) → Training → Evaluation → OutputExpectations gate → Persistence → Report (+ reporting visualizations) → Manifest — all inside `cache.atomic.materialize_temp_dir` so the instance is promoted in one `os.replace` (or left as a `FAILED`-marked temp dir on any stage error). Each stage is timed and JSON-logged; total time flows into `Manifest.elapsed_seconds` and the per-stage `stage_timings` render as a `## Stages` section in the report. Stage skipping (no `Optimization`, empty `Evaluation.splits`), `--overwrite` trashing, and the `ModelArtifactExistsError` guard are wired. Non-domain exceptions are wrapped as `MaterializeError(stage=...)`; a failing OutputExpectation raises `ExpectationError`. The runner is plugin-agnostic (PyTorch + sklearn). `InstanceArtifacts` gains a `stage_timings` field.

- Reporting (Story C.n): new `modelfoundry.reporting` package. `render_report(artifacts) -> str` renders the Markdown ModelInstance summary (stable `## Recipe` / `## Metrics` / `## Optimization` / `## Expectations` / `## Warnings` headings; per-split scalar-metrics table; ✅/❌ expectation outcomes), degrading gracefully for partial instances. `render_reporting_visualizations` drives every `mode: reporting` op in the recipe's `Visualizations` block through the plugin's renderer to `report/visualizations/<name>.png`, and `rerender_report` rebuilds `report/` atomically (via a `report.tmp/` swap that preserves the existing report on any failure). `InstanceArtifacts` gains `recipe` + `manifest` fields so the snapshot carries what the report needs.

- sklearn `MLPClassifier` baseline (Story C.m): `modelfoundry.plugins.sklearn.plugin` promotes the sklearn plugin from a stub to a real, materializable baseline implementing the `Plugin` Protocol — `build_model` (an `mlp_classifier` Architecture block), `run_training` (seeds `random_state` from `derive_seed`, fits, persists `model/estimator.joblib` + `training/history.parquet`), `run_evaluation` (the C.j artifact shapes via the shared metrics), `save_model`/`load_model` (joblib round-trip), and `predict`/`predict_proba` over a flat feature matrix. The feature path (`plugins.sklearn.data.feature_matrix`) reuses the PyTorch C.f `DataRefineryDataset` so features + class ordering match the PyTorch path by construction (this couples the sklearn feature path to the `[pytorch]` extra in pre-production; discovery stays torch-free via lazy imports). The shared `plugins.sklearn.metrics` module gains `accuracy`, `f1_score`, `precision_score`, `recall_score`, `confusion_matrix`, and a hand-rolled `expected_calibration_error`. New `sklearn` entry point under `[project.entry-points."modelfoundry.plugins"]` — `discover_plugins()` now finds both `pytorch` and `sklearn`. `run_optimization` / `render_visualization` are unsupported on the fixed baseline (`NotImplementedError`).

- PyTorch persistence + from-disk round-trip (Story C.l): `modelfoundry.plugins.pytorch.persistence` implements the last four `Plugin` Protocol methods. `save_model` writes `weights/state_dict.pt`, the canonical `architecture.json`, and a `checkpoints/checkpoint-best.pt` provenance copy; `load_model` rebuilds the `nn.Module` from `architecture.json` + `state_dict.pt` **alone** (no external config) and returns it in `eval()`. `architecture.build_model` now attaches the source `Architecture` block to the module as `model.architecture_spec` so the bare `save_model(model, path)` can persist it (FR-23 self-describing model). `predict` / `predict_proba` accept a `pandas.DataFrame` (`path`/`image` column), a list of image paths, or a 4-D `(N, H, W, C)` ndarray, returning pandas types for DataFrame input and ndarrays otherwise. With this the `PyTorchPlugin` has no remaining `NotImplementedError` stubs.

- PyTorch visualizations (Story C.k): `modelfoundry.plugins.pytorch.visualizations.render_visualization` renders the registered viz ops — `training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid` — from an `InstanceArtifacts` snapshot to **byte-deterministic** PNG bytes (forced matplotlib Agg backend, pinned `Software` metadata, no timestamp). `optimization_history` renders a placeholder when no optimization stage ran (or all trials pruned); `predictions_grid` is a labels-only correctness grid. `InstanceArtifacts` is promoted from a `base.py` forward stub to a concrete frozen dataclass (`history`/`evaluation`/`predictions`/`trials`/`class_names`). The `PyTorchPlugin.render_visualization` stub now delegates here.

- PyTorch evaluation (Story C.j): `modelfoundry.plugins.pytorch.evaluation.run_evaluation` runs inference over each `Evaluation.split` and computes the pre-production metric vocabulary (`macro_f1`, `per_class_f1`, `per_class_precision`, `per_class_recall`, `accuracy`, `confusion_matrix`, `ece`, `calibration_curve`) via the `torchmetrics` functional API, on the model's existing device. Persists `evaluation/metrics.json` (the `{split: {metric: value}}` shape the OutputExpectations evaluator consumes), `confusion_matrix.npz`, `calibration.parquet`, and `predictions.parquet` (`split`, `record_id`, `true_label`, `pred_label`, `pred_proba_<class>`). A declared `Evaluation.comparison.baseline_model_id` records a warning and continues (resolver deferred to C.m/C.p). New shared `modelfoundry.plugins.sklearn.metrics.calibration_curve` (multiclass confidence-reliability curve) — the C.j slice of the shared metrics module that Story C.m extends. `DataRefineryDataset` gains an additive `record_ids()` accessor; the `PyTorchPlugin.run_evaluation` stub now delegates here.

- PyTorch Optuna optimization (Story C.i): `modelfoundry.plugins.pytorch.optimization.run_optimization` builds a deterministic Optuna `Study` (SQLite `RDBStorage` at `optimization/study.db`, sampler seeded from `derive_seed(seed, "optuna_sampler")` and masked to 32 bits, `n_jobs=1`, `MedianPruner` or none) over the recipe's `Optimization.search_space`. It enqueues the recipe-defaults baseline trial, runs short per-trial trainings (capped by `max_epochs_per_trial`) via a new additive `run_training(..., epoch_callback=)` hook that reports intermediate `val_*` values and prunes on `should_prune()`, scores each trial on `val_accuracy`/`val_loss` (objective metric / primary metric), and persists `trials.parquet` + `best-params.json`. Each trial seeds from `derive_seed(seed, "trial", <n>)`, so a study reruns identically. New `modelfoundry.recipe.search_space` provides `suggest_params` (`log_uniform`/`uniform`/`int`/`categorical`), `baseline_params`, and `apply_params` (deep-set the dotted recipe paths and rebuild the frozen `ModelRecipe`) — the auto-composition merge-back that makes tunable `Training.batch_size` and `Training.early_stopping.patience` take effect per trial. The `PyTorchPlugin.run_optimization` stub now delegates here.

- PyTorch trainer (Story C.h): `modelfoundry.plugins.pytorch.trainer.run_training` drives the deterministic per-epoch loop — builds the seeded train/val `DataLoader`s (C.f) with the lazy augmentation policy (C.g), fits + persists `training/class_weights.json` when the loss is class-weighted (C.d, via a new additive `DataRefineryDataset.class_counts()`), constructs the optimizer + schedule (C.d), runs forward/backward/step with a per-epoch validation pass, writes `training/history.parquet` and periodic `model/checkpoints/checkpoint-epoch-NNNN.pt`, and promotes the best-monitor-value weights to `model/weights/state_dict.pt` + `checkpoint-best.pt` (B.k). Early stopping / best tracking follow `Training.early_stopping` (falling back to `val_loss` then `train_loss`); `reduce_on_plateau` is stepped on its watched metric. Determinism mode is enabled and the training RNG seeded from the `"dropout"` scope, so reruns under a fixed seed are byte-identical. Returns a `TrainingResult` dataclass; the `PyTorchPlugin.run_training` stub now delegates here (lazy import keeps `plugin.py` torch-free at discovery).

- PyTorch lazy augmentations (Story C.g): `modelfoundry.plugins.pytorch.augmentations` realizes a DataRefinery *lazy* `Augmentations` policy on-the-fly via `torchvision.transforms.v2.functional`. `build_realizer(op, params, seed)` returns a deterministic transform for `horizontal_flip` / `random_crop` / `color_jitter` / `random_erasing` (params validated against vendor-spec-shaped models → `PluginError`), drawing all randomness from a **local `torch.Generator`** so the global RNG is never perturbed and the same `(op, params, seed)` reproduces byte-for-byte. `compose_augmentations(policy, master_seed)` threads each op a `derive_seed(master_seed, "augmentation:<name>", …)` seed and returns the composed callable that `DataRefineryDataset.__getitem__` applies (or `None` for an empty policy). Visual semantic-equivalence with DataRefinery's Pillow aggressive realizers is verified in Story E.g. Import-safe without the `[pytorch]` extra.

- PyTorch `DataRefineryDataset` adapter (Story C.f): `modelfoundry.plugins.pytorch.data` binds a materialized DataRefinery instance split to a `torch` dataset — decodes uint8 PNGs (sidecar `image_path` over source `path`), applies the train-fitted `normalize`/`mean_subtract` statistics in `Transformations` order (RGB axis, exact `std == 0 → 1.0` zero-variance guard) on every split, derives the label→index map by scanning all labeled splits, and refuses lazy-mode pixel-altering transforms (e.g. `resize`) that aren't baked via sidecars/sinks. `build_dataloader` wires a seeded shuffle `generator` + the spawn-safe `worker_init_fn`, with CUDA-only `pin_memory`. The B.i `DataRefineryInstance` wrapper gains a `fitted_statistics` field.

- PyTorch determinism module (Story C.e): `modelfoundry.plugins.pytorch.determinism.enable_deterministic_algorithms(seed)` sets `CUBLAS_WORKSPACE_CONFIG`, enables `torch.use_deterministic_algorithms(True)`, and seeds CPU/CUDA/MPS RNGs before model construction (idempotent), locking the C.a spike pattern. `documented_hard_error_ops` records ops that hard-error under the guard (empty for the CPU vocabulary). `PyTorchHealthReport` now exposes `documented_hard_error_ops` and sources `deterministic_algorithms_available` from this module.

- PyTorch losses / optimizers / schedules (Story C.d): `modelfoundry.plugins.pytorch.{losses,optimizers,schedules}` register `cross_entropy` / `cross_entropy_class_weighted` / `bce_with_logits`, `adamw` / `sgd` / `adam`, and `reduce_on_plateau` / `cosine` / `linear_warmup` as `OperationSpec`s on the plugin. `derive_class_weights` computes mean-normalized per-class weights (balanced / inverse-frequency / effective-number) from a train-split label distribution; `bce_with_logits` is refused for `num_classes > 2` at build time. All three modules are import-safe without the `[pytorch]` extra (lazy torch in the builders).

- PyTorch architecture vocabulary (Story C.c): `modelfoundry.plugins.pytorch.architecture` registers the CIFAR-10 baseline vocabulary — primitives (`Conv2d`, `BatchNorm2d`, `ReLU`, `MaxPool2d`, `AvgPool2d`, `AdaptiveAvgPool2d`, `Linear`, `Dropout`, `Flatten`), composites (`MLP`, `ConvBlock`, `ResidualBlock`), baselines (`simple_cnn`, `resnet8`, `resnet20` — the canonical 272,474-param CIFAR ResNet-20 with option-B projection shortcuts), and the deferred-but-contract-supported pretrained-encoder path (`Encoder`/`LoRA`/`Pooling`/`Head`, `requires_extras=("huggingface",)`). `build_model` composes a recipe `Architecture:` block (named baseline or explicit `layers`) into an `nn.Module`; the op registry is import-safe without the `[pytorch]` extra. **Cache note:** the new ops perturb canonical recipe bytes only for recipes that select them (acceptable pre-production per `project-essentials.md` § Cache identity); existing recipes are unaffected.

- PyTorch plugin scaffold + `health_check` + registration (Story C.b): `modelfoundry.plugins.pytorch` registers the `pytorch` plugin via the `modelfoundry.plugins` entry point with an (initially empty) `operations` map. `health_check` returns a `PyTorchHealthReport` (torch/torchvision/torchmetrics versions, available accelerators in `Training.device` terms — `cpu`/`cuda`/`mps`, and whether deterministic-algorithm mode is enable-able); every other `Plugin` method is a stub raising `NotImplementedError` until its owning Story (C.c–C.p). The module is import-safe without the `[pytorch]` extra (lazy torch import), so discovery works on sklearn-only installs.

### Fixed

- PyTorch visualization ops are now registered as operations (Story C.q.2): the five renderers (`training_curves`, `optimization_history`, `confusion_matrix`, `calibration_curve`, `predictions_grid`) were dispatched by `plugins.pytorch.visualizations` but never advertised as `OperationSpec`s on `PyTorchPlugin.operations`, so the FR-2 validator's check 3 (`section_ops_registered`) spuriously rejected any recipe declaring a `Visualizations:` section — even though `materialize()` (which skips the validator) rendered the figures fine. New matplotlib-free `plugins.pytorch.visualization_specs.VISUALIZATION_OPERATIONS` (deliberately **not** placed in the matplotlib-importing `visualizations.py`, so plugin discovery stays import-light) is wired into the plugin; check 3 and check 17 now accept declared visualizations, including `confusion_matrix {split}` / `predictions_grid {max_items}` params. A C.k omission surfaced while wiring the C.r deliverable recipe; rides the phase-bundled v0.4.0 release.

- DataRefinery instance resolution no longer re-derives the cache key (Story C.q.1): `pipeline.data_binding.resolve_data_instance` now locates a materialized instance via DataRefinery's blessed `datarefinery.resolve_instance(...)` (a `StatusReport` carrying `cache_status` + `instance_path`) instead of hand-computing `sha256(to_canonical_bytes(recipe))[:16]` and scanning the cache bucket. The hand-rolled key diverged from DataRefinery on any recipe with a `variants:` block — DataRefinery clears `variants` for the default instance's key, ModelFoundry didn't — so variants-bearing DR recipes (e.g. `cifar10-base.yaml`) could never be bound; now fixed and guarded by a `test_variants_recipe_binds` regression. The `_find_instance` scan and the consumer-side `apply_variant` dance are removed, and the ambiguous-bind failure mode is gone (an exact key can't multi-match). Behavioral change: resolution now hashes the recipe's declared inputs, so the source inputs must be present on the resolving host (vendor-dep-spec § "Resolving a materialized instance" / § Host portability). The `ml-datarefinery` pin moves to `>=0.20.0` (where `resolve_instance` ships), and the binding tests now materialize tiny real instances instead of faking the input hash.

- `worker_init_fn_factory` (`pipeline.seeding`) returned a nested closure that the macOS/Windows `spawn` start method cannot pickle, crashing `DataLoader(num_workers>0)` (Story C.a.1, latent defect surfaced by the C.a determinism spike). It now returns a picklable `functools.partial` over a module-level `_seed_worker`; public API and seeding behavior are unchanged, and a pickle round-trip regression test guards it.

### Changed

- Pyve 3.0 env reconfiguration — two micromamba envs (Story B.o): adopted Pyve v3.0.6's `pyve.toml` (`pyve_schema = "3.0"`) `[env.<name>]` env spec for **two micromamba environments** — a `purpose = "utility"` **root** (instantiate a `ModelFoundry` / run scripts ad hoc) and a `default = true` **`testenv`** (full dep + tool stack; `manifest = "environment.yml"`). Declared `[env.testenv] manifest` so `pyve test` resolves the conda-backed env (the canonical `pyve test` / `pyve run` / `pyve env run` workflow is now un-parked; the raw-conda-interpreter workaround used through Phase C retires). Removed the superseded `[tool.pyve.testenvs.testenv]` table from `pyproject.toml`. Rewrote `docs/specs/env-dependencies.md` §3–§5 from the earlier bare-OS-`none`-root design to this topology (the `none` backend is reserved for languages with no managed-env concept; Python uses micromamba). `environment.yml` reframed as the shared manifest for both envs. No package version bump (infra/doc; shares the post-B.n housekeeping release).

- Env-layout doc reconcile (Story B.p): rewrote `docs/specs/tech-spec.md`'s stale pre-3.0 env prose (the `.venv/` + `.pyve/testenvs/` "two-environment model") to match the B.o two-micromamba topology — the § Runtime & Tooling Environment-manager row, the § Two-environment install command sequence (now `pyve env init` / `pyve run` / `pyve env run testenv -- …`), the canonical-command block, the Package-Structure tree (added `pyve.toml`; reworded the `environment.yml` annotation), and cross-references to `env-dependencies.md`. The bundled `docs/project-guide/go.md` § Pyve Essentials is also stale (v2.8 `.pyve/testenvs/` + `pyve testenv`) but is project-guide install output — left unedited for an upstream `project-guide update`. Doc-only; no version bump.

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
