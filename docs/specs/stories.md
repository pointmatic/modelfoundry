# stories.md -- modelfoundry (python)

This document breaks the `modelfoundry` project into an ordered sequence of small, independently completable stories grouped into phases. Each story has a checklist of concrete tasks. Stories are organized by phase and reference modules defined in `tech-spec.md`.

Put **`vX.Y.Z` in the story title only when that story ships the package version bump** for that release. Doc-only or polish stories **omit the version from the title** (they share the release with the preceding code story, or use your project’s doc-release policy). **One semver bump per owning story** — extra tasks on the *same* story share that bump; see `project-essentials.md`. Semantic versioning applies to the package. Stories are marked with `[Planned]` initially and changed to `[Done]` when completed.

For a high-level concept (why), see [`concept.md`](concept.md). For requirements and behavior (what), see [`features.md`](features.md). For implementation details (how), see [`tech-spec.md`](tech-spec.md). For project-specific must-know facts, see [`project-essentials.md`](project-essentials.md) (`plan_phase` appends new facts per phase). For the workflow steps tailored to the current mode (cycle steps, approval gates, conventions), see [`docs/project-guide/go.md`](../project-guide/go.md) — re-read it whenever the mode changes or after context compaction.

---

## Version Cadence

Standard semantic versioning, with these conventions:

- **Every story belongs to a phase.** Bugfix stories included. No orphan stories.
- **Per-story bumping** (when a story owns its own release):
  - Bugfix or trivial change → **patch** (`vX.Y.Z+1`)
  - Feature or improvement → **minor** (`vX.Y+1.0`)
  - Breaking change → **major** (`vX+1.0.0`). Post-1.0 only, and only via the `plan_production_phase` mode, which negotiates with the developer about whether the breakage is substantively user-facing or technically-but-trivially breaking (example: a log-format change is technically breaking, but if logs aren't a core consumer capability, the developer may judge it minor or even patch).
- **Phase-bundling option:** a phase can run unversioned during work and ship a single release/tag at end-of-phase. Stories within the phase carry no version in their title; the phase's last story owns the bump (magnitude determined by the highest-impact change in the bundle).
- **No out-of-order implementation.** Story order in this file is the order of execution. If work order needs to change, **reorganize/renumber here first** — don't skip ahead and create version-number gaps.
- **Pre-1.0:** standard semver applies; version starts at `v0.1.0` (Story A.a).
- **Post-1.0:** every phase must go through `plan_production_phase` (the lighter `plan_phase` is pre-1.0 only). Major bumps only happen through that mode's negotiation step.

This is the authoritative cadence rule. **Do not extrapolate the bump magnitude from `pyproject.toml`'s current version** — re-read this section whenever you're about to assign a version to a story.

---

## Phase H: Implementation Improvements, UX Refinements, Bug Fixes

Now that the core functionality is in place, we can focus on improving the implementation, refining the UX, and fixing any bugs that have been discovered.

---

> **Release cadence for Phase H.** Per-story bumps (the G.c–G.e precedent), not an end-of-phase bundle — so each fix ships when it's ready. Bugfix stories take a **patch**; the one **feature** in the phase (H.a.2, `ModelFoundry.summary()`) takes a **minor** per the Version Cadence, which is why versions run `H.a` v0.8.4 → `H.a.2` v0.9.0 → `H.b` v0.9.1 (monotonic across execution order). Execution / priority order: H.a (model trains to chance) → H.a.1 (canonical example, no bump) → H.a.2 (summary surface) → H.b (flagship recipe can't materialize on macOS) → H.c (examples cleanup).

### Story H.a: v0.8.4 Fix normalization units mismatch in `DataRefineryDataset` — model trains to chance [Done]

`features.md` CR-16 / FR-3 / FR-22 / QR-1. The PyTorch data adapter destroys the input signal, so the flagship CIFAR-10 / ResNet-20 deliverable (Story C.r) trains to **chance** — measured `test` accuracy `0.1000` on `recipes/cifar10_resnet20.yml` (2026-06-16). [data.py](../../src/modelfoundry/plugins/pytorch/data.py) decodes pixels to `[0,1]` (`np.asarray(...) / 255.0`) and then applies DataRefinery's per-channel `normalize` statistics, which DR fitted in **0–255 pixel units** (mean ≈ `[125.6, 123.6, 114.6]`, std ≈ `[63.7, 63.1, 67.4]`). Every pixel collapses to ≈ −1.9 with std ≈ 0.13 (range `[−1.97, −1.69]`) — three near-flat channels: `train_loss` sticks at ln(10) ≈ 2.305, eval BatchNorm running-stats explode (`val_loss` → 1e28), nothing is learned. Cache-invalidating (materialized output bytes change) but **not** a `schema_version` bump — the recipe's canonical bytes are unaffected, only the adapter's runtime behavior; acceptable pre-production per OR-9 / `project-essentials.md` § cache identity (release-note + re-materialize). Owns **v0.8.4** (bugfix patch).

- [x] **Failing unit test first** — added to [tests/unit/test_pytorch_data_adapter.py](../../tests/unit/test_pytorch_data_adapter.py) (the existing adapter test module, not a new `test_pytorch_data.py`): `test_normalized_output_is_standardized` (content-rich image whose pixels ~ N(mean, std) → asserts per-channel output mean ≈ 0 / std ≈ 1) and `test_normalize_applies_in_datarefinery_pixel_units` (deterministic pixel-space equality). **Root cause of why the suite missed it:** the existing fixtures used unrealistic `[0,1]`-scale stats `(0.5, 0.3, 0.1)`, which masked the bug — updated `_build_instance` + the two value-asserting tests to realistic **0–255** stats. Confirmed **red** (mean ≈ −2.24) → **green**.
- [x] Confirmed the units contract in [vendor-dependency-spec.md](../../docs/specs/datarefinery/vendor-dependency-spec.md) § "Normalization is applied by the consumer" (steps 1–2–4: decode the uint8 image, convert to float, apply `(x - mean) / std` — **no** `[0,1]` rescale; `mean_subtract` → `x - mean` only; uint8 PNGs on disk). Cited the exact section in the [data.py](../../src/modelfoundry/plugins/pytorch/data.py) code comment.
- [x] Fixed `DataRefineryDataset` ([data.py](../../src/modelfoundry/plugins/pytorch/data.py)): `_decode` now keeps raw 0–255 pixels (dropped the spurious `/ 255.0`); `__getitem__` applies the fitted stats in 0–255 space when a fit-on-train op is present (the `std==0` guard preserved; `mean_subtract` handled by the same pixel-space path), and falls back to `/255` → `[0,1]` only when **no** normalization is declared (so a bare CNN still gets sane inputs). (`_resolve_normalization_steps` left unchanged — it reads the 0–255 stats correctly; the bug was solely the pre-apply rescale.)
- [x] **Learning-floor regression guard** — added to [test_cifar10_resnet20.py](../../tests/integration/test_cifar10_resnet20.py): reads the materialized `training/history.parquet` and asserts `train_loss.min() < 2.2` (below the ln(10) ≈ 2.303 chance floor the bug pinned it at). **Implemented as a `train_loss`-drop guard rather than the drafted test-accuracy floor:** a real 25-epoch run post-fix measured `train_loss` 2.17 → 0.44 (model learns) but `test` accuracy only 0.134 — generalization on the 1,700-image subset is confounded by overfitting **and** a separate augmentation-after-normalization issue (see follow-up below), so a `>0.20` accuracy floor would be unreliable. The `train_loss` drop is the precise inverse of the bug signature, reuses the existing materialize (no extra cost), and skips cleanly when DR-1 is absent.
- [x] Bump version to v0.8.4 in [_version.py](../../src/modelfoundry/_version.py) (`0.8.3 → 0.8.4`; `modelfoundry.__version__` → `0.8.4`).
- [x] Update CHANGELOG.md (`## [0.8.4]` under Fixed: normalization units; cache-invalidation note → re-materialize). Release-metadata guard `tests/unit/test_release_metadata.py` green against `__version__`.
- [x] Verify: the new unit + floor assertions are red before the fix, green after; `tests/unit` + `tests/plugin_contract` → **490 passed** (the only 2 failures — `test_docs_crosslinks` / `test_env_docs_topology` — are pre-existing, from the uncommitted `stories.md` archival, not this change); `tests/integration` + `tests/cli` + `tests/notebook` → **175 passed**; the e2e deliverable `test_cifar10_resnet20.py` → **3 passed** incl. the floor; `ruff check` + `ruff format --check` + `mypy src tests` (144 files) clean.

**Follow-up surfaced (recommend a new Phase H story):** post-fix, the model learns on `train` but generalizes poorly (`val_loss` explodes to ~15, val/test accuracy ~0.13). Lazy `Augmentations` are applied **after** normalization ([data.py](../../src/modelfoundry/plugins/pytorch/data.py) `__getitem__`: `color_jitter` etc. run on the standardized tensor), a likely train/eval-distribution skew distinct from H.a's units bug. Worth its own debug story before the CIFAR-10 deliverable can claim a real accuracy number.

### Story H.a.1: Canonical example reimplementation — `test_models_resnet20_fix.py` + architecture-summary surface gap [Done]

`features.md` CR-11 / UR-1 / FR-27. Reimplements [scripts/examples/test_models_resnet20.py](../../scripts/examples/test_models_resnet20.py) as [test_models_resnet20_fix.py](../../scripts/examples/test_models_resnet20_fix.py) through ModelFoundry's **public, backend-agnostic surface only** — `from modelfoundry import ModelFoundry`, no `import torch`, no reach into `plugins.*` / `recipe.*` internals (the original imported `plugins.pytorch.architecture.build_model` + `torch` directly, and pointed at the non-existent `models/resnet20.yaml` + `./cache`). The canonical script doubles as a **strict-xfail red/green spec** for the one surface the canonical path is missing. Examples-only (lives outside `testpaths=["tests"]`) → **no version bump**.

- [x] Add [scripts/examples/test_models_resnet20_fix.py](../../scripts/examples/test_models_resnet20_fix.py): construct via `ModelFoundry.from_recipe("recipes/cifar10_resnet20.yml", data="./data")`; Pointmatic/Apache-2.0 header.
- [x] **Green** (canonical surface that exists today): `validate().passed` (FR-2), recipe access `mf.recipe.plugin` / `mf.recipe.Architecture` (framework-agnostic state), data binding `mf.data.instance_num_classes() == 10`.
- [x] **Red** (`xfail(strict=True)` — the gap): param count + output shape via a proposed `ModelFoundry.summary()`. There is **no public pre-materialize architecture summary** — FR-27's `ModelSummary` is reachable only *after* `materialize()` (`ModelInstance.summary`), or by importing the `plugins.pytorch` internals the contract forbids. The markers flip to a hard failure (strict XPASS) the moment the surface lands, prompting their removal.
- [x] Verify: `pyve test --env smoke-pytorch scripts/examples/test_models_resnet20_fix.py` → **3 passed, 2 xfailed**; `ruff check` + `ruff format --check` clean. Skips cleanly without torch or the `./data` instance; the xfails never gate `pyve test` (outside `testpaths`).

**Resolved by Story H.a.2 (next):** the proposed `ModelFoundry.summary()` was implemented immediately, so the two strict-xfail markers here are now plain green tests. The remaining secondary friction (a recipe-only, data-binding-free summary path; a `summary` CLI verb) is recorded under H.a.2's out-of-scope. This also lets Story **H.c** simply retire the broken original example rather than repair it.

### Story H.a.2: v0.9.0 Public pre-materialize architecture summary — `ModelFoundry.summary()` [Done]

`features.md` CR-10 / CR-11 / FR-27 / UR-1. Implements the surface Story H.a.1 specced as strict xfails: a public, backend-agnostic way to inspect a recipe's architecture **without training it and without a framework import**. Before this, FR-27's `ModelSummary` was reachable only *after* `materialize()` (`ModelInstance.summary`), so the original example reached into `plugins.pytorch.architecture.build_model` + `torch`. Additive, no cache impact, no new runtime dep → **feature/minor** per the Version Cadence; owns **v0.9.0**.

- [x] **Failing tests first** — `tests/unit/test_pytorch_summary.py::test_plugin_summarize_model_returns_dict_with_totals_and_output_shape` and `tests/integration/test_cifar10_resnet20.py::test_summary_inspects_architecture_without_training`. Confirmed **red** (`AttributeError: 'ModelFoundry' object has no attribute 'summary'`) → **green**.
- [x] Add the PyTorch plugin's in-memory `summarize_model(model, data) -> dict` ([plugin.py](../../src/modelfoundry/plugins/pytorch/plugin.py)) — the torchinfo sibling of `write_model_summary` (reuses `summary.summarize` + `summary.derive_input_size`, no files written), adding a top-level `output_shape` (the depth-0 root module's output size).
- [x] Add `ModelFoundry.summary() -> dict[str, Any]` ([modelfoundry.py](../../src/modelfoundry/core/modelfoundry.py)): builds the model via `self.plugin.build_model(self.recipe.Architecture)` and delegates to the plugin's `summarize_model` (duck-typed like the runner's `write_model_summary`); raises `PluginError` for a plugin that doesn't implement it (e.g. the sklearn stub).
- [x] Resolve H.a.1's red spec: removed the two `xfail(strict=True)` markers in [test_models_resnet20_fix.py](../../scripts/examples/test_models_resnet20_fix.py) (now plain green) and updated its docstring; the example now exercises `summary()` through the public surface end-to-end (**5 passed**).
- [x] Bump version to v0.9.0 in [_version.py](../../src/modelfoundry/_version.py) (`0.8.4 → 0.9.0`).
- [x] Update CHANGELOG.md (`## [0.9.0]` under Added). Release-metadata guard green against `__version__`.
- [x] Verify: the new unit + integration tests red→green; `ruff check` + `ruff format --check` + `mypy src tests` (144 files) clean. (Full-suite rerun at the gate.)

**Out of scope (recommend `plan_features`):** a **recipe-only** (data-binding-free) summary path — `summary()` currently needs the bound DR instance for the input-probe shape, so a recipe's architecture still can't be inspected fully offline; and surfacing `summary()` as a CLI verb (`modelfoundry summary <recipe>`) to keep the library/CLI surfaces co-equal (CR-10).

### Story H.b: v0.9.1 Make the composed augmentation transform spawn-safe (picklable) [Done]

`features.md` QR-3 / QR-4 (macOS is the first-class pre-production platform). `compose_augmentations` returned a **local closure** `apply` (pre-fix `augmentations.py:264`), attached as the train dataset's transform — **and each `build_realizer` output was itself a local closure** (`flip` / `crop` / `jitter` / `erase`), so the bug was deeper than the composer alone. With `num_workers ≥ 1` under the `spawn` start method (macOS default), the `DataLoader` must pickle the dataset and fails: `AttributeError: Can't get local object 'compose_augmentations.<locals>.apply'`. `recipes/cifar10_resnet20.yml` sets `num_workers: 2`, so the flagship recipe **could not materialize on macOS as written** — it died on optimization trial 0. The `worker_init_fn` was already spawn-safe (B.j); the transform was not. Owns **v0.9.1** (bugfix patch).

- [x] **Failing tests first** — `tests/unit/test_pytorch_augmentations.py::test_composed_transform_is_picklable_and_deterministic` + `::test_single_realizer_is_picklable` (platform-independent `pickle` round-trip), and `tests/unit/test_pytorch_data_adapter.py::test_iteration_invariant_to_num_workers_with_augmentations` (a `num_workers=2` `DataLoader` over an augmented dataset). Confirmed **red** with the exact signature `Can't get local object 'compose_augmentations.<locals>.apply'`.
- [x] Replace the closures with picklable, module-level **classes** — `_HorizontalFlip` / `_RandomCrop` / `_ColorJitter` / `_RandomErasing` (each a `_Realizer` subclass holding validated params + the masked seed) and a `_ComposedTransform` for the policy. Exact left-to-right op order and the per-op `derive_seed(master_seed, "augmentation:<name>", salt)` derivation preserved; `torch` / `torchvision` stay lazily imported in `__call__` (import-safe-without-`[pytorch]` rule held).
- [x] Each `build_realizer` output is now picklable (a class instance, no nested closures) — guarded by `test_single_realizer_is_picklable` and the composed round-trip (which preserves determinism: `transform(img) == restored(img)`). The Story E.g Hypothesis visual-equivalence tests still pass, confirming semantics are unchanged.
- [x] **Coverage for the seam** — added the augmentations × `num_workers ∈ {0, 2}` invariance test (asserts iterate-without-crash **and** output identity), the combination neither `test_determinism` (workers ≥ 1, no augmentations) nor `test_cifar10_resnet20` (augmentations, workers = 0) covered. (Implemented by passing the composed transform straight to `DataRefineryDataset(augmentations=…)` — the precise crash surface — rather than teaching the synthetic `build_dr_instance` to emit an `Augmentations` policy, which would only add indirection.)
- [x] Bump version to v0.9.1 in [_version.py](../../src/modelfoundry/_version.py) (`0.9.0 → 0.9.1`).
- [x] Update CHANGELOG.md (`## [0.9.1]` under Fixed). Release-metadata guard green.
- [x] Verify: new tests red→green; **end-to-end proof** — a `num_workers: 2` materialize over the augmented DR-1 (the configuration that crashed) now completes (25.8s, test accuracy 0.221 at 2 epochs, with H.a's fix the model learns). `tests/unit` + `tests/plugin_contract` **494 passed**; `tests/integration` + `tests/cli` + `tests/notebook` **176 passed**; `ruff check` + `ruff format --check` + `mypy src tests` (144 files) clean. (The only suite failures remain the 2 pre-existing `stories.md`-archival doc-guards, unrelated.)

### Story H.c: Repair the `scripts/examples/` smoke files [Planned]

The example smoke files are broken and contract-violating. [test_models_resnet20.py](../../scripts/examples/test_models_resnet20.py) targets non-existent paths (`models/resnet20.yaml`, `data="./cache"` — the real ones are `recipes/cifar10_resnet20.yml` and `./data`), reaches into plugin internals (`plugins.pytorch.architecture.build_model`) and imports `torch` directly — defeating the no-framework-imports promise (CR-11) — and carries a non-Pointmatic copyright header. Its siblings ([test_mlp_baseline.py](../../scripts/examples/test_mlp_baseline.py), [test_random_classifier.py](../../scripts/examples/test_random_classifier.py)) `import d802_deep_learning`, a different project. Examples-only (no wheel impact) → **no version bump**; shares the H.b release.

- [ ] Repoint [test_models_resnet20.py](../../scripts/examples/test_models_resnet20.py) to `recipes/cifar10_resnet20.yml` + `data="./data"`; fix the docstring env name (`smoke-pytorch`) and file path; stamp the `Copyright (c) 2026 Pointmatic` / Apache-2.0 header per `project-essentials.md`.
- [ ] Resolve the foreign-project examples — relocate to their owning repo or rewrite against ModelFoundry's public surface. Recommend removal from this repo.
- [ ] Verify: `pyve env run smoke-pytorch -- python -m pytest scripts/examples/` passes, or skips cleanly when `./data` is unmaterialized.

**Out of scope (recommended follow-ups — `plan_features` territory, not debug fixes):**

- **Public pre-materialize architecture surface** — a backend-agnostic `ModelFoundry.from_recipe(...).summary()` (param count + layer rows + forward shape) so structural checks need not import plugin internals + `torch`. This is *why* the example "needs so much code": FR-27's `ModelSummary` exists only **after** `materialize()`. Feature scope → `plan_features` + `## Future`.
- **`validate`-time normalization sanity check** — flag when a bound instance's `normalize` stats are out of range for the adapter's decode scale (would have caught H.a's class at `validate` time, before training). `plan_features`.

---

## Future

<!--
This section captures items intentionally deferred from the active phases above:
- Stories not yet planned in detail
- Phases beyond the current scope
- Project-level out-of-scope items
The `archive_stories` mode preserves this section verbatim when archiving stories.md.
-->

**Close follow-on cycles (deferred from the pre-production release):**

- **`[huggingface]` plugin end-to-end** — transformers + peft + evaluate-based plugin honouring the same `Plugin` Protocol. Architecture vocabulary extends with `Encoder` (HF model id), `LoRA` (peft), `Pooling`, `Head` per the optional pretrained-encoder path. Pretrained-weight cache management (`~/.cache/huggingface/` or `HF_HOME` override) lives in the plugin's docs, not in `project-essentials.md`.
- **`[keras]` plugin end-to-end** — TensorFlow + Keras 3 backend. Likely shares the metric implementations from `plugins/sklearn/metrics.py` for ECE / calibration_curve.
- **`[llm]` extra implementation** — `init --llm-assist` flag routed through `lmentry` for interpretive baseline-model recommendations. Namespace claimed in `pyproject.toml`; no implementation in the pre-production series. Lands as its own FR with its own acceptance criteria.
- **Additional sklearn baselines** — C.m ships a working `MLPClassifier` baseline (Subphase C-1); extend with RandomForest / GBM baselines for CIFAR-10 (reusing the C.f feature-flattening + normalization path).
- **Continued training** — `Training.persist_optimizer_state: bool = false` recipe field gated by a `schema_version` bump; the `Checkpoint` model's forward-extensible keys (`optimizer_state`, `scheduler_state`, `rng_state`, `training_step`) are populated; new `materialize --resume-from <checkpoint>` workflow. The Q16 foundation in B.k is what makes this a pure additive change with no public-API rework.
- **Tight-coupled DataRefinery binding (FR-26)** — `schema_version` bump that mixes the bound DataRefinery instance's `recipe_hash` into ModelFoundry's cache identity, so upstream re-materialization auto-invalidates downstream. Requires a documented migration of existing cached ModelInstances.
- **`num_workers` cache-identity reclassification** — `Training.num_workers` lives in `TrainingSpec`, so it participates in canonical recipe bytes and `recipe_hash`, yet it is **output-neutral** by the B.j `worker_init_fn` contract (now guarded by E.e's determinism test). Consequence: changing only `num_workers` forks the cache for byte-identical output, and the *same* recipe materialized with different worker counts across environments (e.g. CI `num_workers: 0` vs a dev laptop's `num_workers: 4`) will not share a cache entry. Surfaced by E.e.1. Two options, both cache-invalidating (pre-prod: release-note only; no literal pinned-hash golden exists today):
  - **Option A — reclassify as execution context (preferred in principle).** Move `num_workers` out of the recipe entirely into `RuntimeConfig` + a `--num-workers` CLI flag + `MODELFOUNDRY_NUM_WORKERS`, alongside the other execution knobs (`cache_root`, `log_level`, …). Keeps the recipe schema honest — `num_workers` is not recipe *semantics* — and avoids baking a tracked-but-ignored field into a schema that may scale to many recipes. **LOE: Large (~1–2 days).** `TrainingSpec` is `extra="forbid"`, so removing the field breaks every recipe that sets it (~20 fixtures + `recipes/cifar10_resnet20.yml` + the `init` scaffolder template + ~9 test modules); adds the `RuntimeConfig` / CLI / env surface; requires a `Plugin` Protocol signature change to thread `num_workers` to the trainer's DataLoader (it no longer rides on `TrainingSpec` into `run_training` / `run_optimization`); plus a loader migration (or documented hard break) for existing recipes.
  - **Option B — exclude `num_workers` from canonical bytes (keep the field).** An explicit, documented exclusion in `recipe.canonical` (e.g. an `_IDENTITY_EXCLUDED` set) drops `Training.num_workers` before hashing; the field stays in the recipe and in the persisted `recipe.yml`. **LOE: Small (~half a day).** One core change + a couple of `test_canonical` tests + two doc lines. The original soundness objection (a silent wrong cache hit if output-neutrality ever regressed) is now covered by E.e's determinism guard. Warts: it is a recipe field the cache deliberately ignores (the "crufty schema" concern), and a cache hit returns the first writer's `recipe.yml` (benign provenance cosmetic).

  Developer lean (2026-06-15): prefer **Option A** in principle — avoid a nonsensical recipe schema this early — but **deferred**; not blocking the PyPI publication path. Worth deciding before the `1.0.0` ceremony, since post-production this reclassification becomes a ceremonious cache-invalidating change.
- **Marimo + IPython substrate-neutral smokes** — the Jupyter smoke in E.k is the canonical substrate-neutral test; Marimo headless and IPython REPL smokes extend the contract.
- **Parallel Optuna trials** — `n_jobs > 1` with a deterministic trial-ordering protocol on top of the parallel harness. Requires the determinism contract to extend cleanly.
- **Search-space op-choice dimensions** — a grouped/conditional Optuna search-space mechanism so optimizer (AdamW / SGD+momentum) and LR schedule (`reduce_on_plateau` / `cosine`) can be **genuine search dimensions** rather than `variants:`. The current flat `recipe.search_space.suggest_params` + per-op `extra="forbid"` param models can't carry op-conditional params: a single `Optimizer.schedule` block can't validate for both ops (`cosine` *requires* `T_max`, which `reduce_on_plateau` rejects), and SGD's `momentum` breaks an AdamW trial the same way. Likely an `optimizer`/`schedule` group categorical that swaps the whole sub-block as a unit (plus a default for `CosineParams.T_max`). A `plugins.pytorch.optimization` + `recipe.search_space` enhancement touching the determinism-sensitive trial path. Surfaced by the C.r CIFAR-10/ResNet-20 deliverable (R5), which ships these comparisons as `variants:` instead. Sibling to **Parallel Optuna trials** above.
- **`modelfoundry.toml` per-project config** — currently no per-project config file (recipe + CLI flags + env vars cover execution context). If recurring patterns emerge, a project config lands as its own FR.
- **Cross-platform first-class Linux** — currently Linux is best-effort pre-production; post-production gates require first-class status.
- **Codecov / Coveralls coverage upload** — deferred from Phase G; coverage produced locally via `pyve test --cov`.
- **GitHub branch protection** — explicitly out of scope for the pre-production series per CR-1.
- **Production-release ceremony** — when ModelFoundry transitions from pre-production to production (the `1.0.0` event), every cache-invalidating change becomes ceremonious per `project-essentials.md`; `OR-8` / `OR-9` / `OR-10` stability guarantees activate; `plan_production_phase` replaces `plan_phase` for adding new work.

**Forward-declared dependency contracts:**

- `docs/specs/modelfoundry/vendor-dependency-spec.md` for downstream consumers (a future `modelmetrics`, `modelmachine`, replay harness) — authored at the pre-production release, mirroring DataRefinery's vendor-dependency-spec discipline. Captures the on-disk `ModelInstance` layout + the in-memory `ModelInstance` API + schema-version coordination policy.
