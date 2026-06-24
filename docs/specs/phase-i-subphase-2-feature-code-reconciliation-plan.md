# Subphase I-2 Plan — Feature-Code Reconciliation

> **Mode:** `plan_phase` (pre-1.0). **Structure:** Subphase **I-2** under the existing
> `## Phase I: Segmented Recipe Architecture`. Stories continue monotonically from
> the phase's last story **I.r** → **I.s, I.t, …** (story letters reset only at a
> phase boundary, never a subphase boundary).
>
> **Multi-release exception.** Phase I already shipped (v0.16.0 → v0.18.0 across
> Subphase I-1). Subphase I-2 is a follow-on subphase that ships its own release tag
> (**→ v0.19.0**, a minor — new additive capability + spec-conformance fixes). This is
> the documented Version-Cadence multi-release exception (`_phase-letters.md`
> § Subphases): the subphase's last code story owns the bump.

This subphase closes a **features-vs-code gap**: behaviors promised in
[`features.md`](features.md) (and [`concept.md`](concept.md)) that are **not** yet
implemented and were **not** explicitly deferred to the `## Future` backlog. It is a
deliberate reconciliation pass — bring the shipped code up to its own written contract,
and bring the contract back in line with what shipped — so the spec is once again an
honest description of the system.

The audit that produced this inventory cross-checked every FR (FR-1…FR-27, FR-AUDIO-1/2/3),
the FR-2 validator-check enumeration, and the `concept.md` Goals / Value Criteria against
`src/`. The explicitly-deferred backlog (`## Future` in `stories.md`: tight-coupled DR
binding / FR-26, `[llm]` extra, `[keras]` plugin, additional sklearn baselines, continued
training/resume, configurable best-weights, parallel Optuna trials, search-space op-choice
dims, robustness/CIFAR-10-C eval, true-paper benchmark, Marimo/IPython smokes,
`modelfoundry.toml`, cross-platform Linux, codecov, branch protection, production ceremony,
optional `Loss`/`Optimizer` baseline sections) is **excluded by design** — those are
already on the roadmap and out of this subphase's scope.

---

## 1. Gap analysis — what's promised vs. what's coded

Every row below is a **promised, non-deferred** behavior. Status verified directly against
the source (file:line) during the audit.

### Code gaps — missing or partial implementation

| FR | Promised behavior | Reality today | Verdict |
|----|-------------------|---------------|---------|
| **FR-12** | `Evaluation.comparison.baseline_model_id` resolves + scores a baseline on the same held-out splits; baseline metrics land in `evaluation/metrics.json` under `baseline.<split>.<metric>` | Output contract + warn-and-skip path coded; **resolver missing** ([evaluation.py:421-426](../../src/modelfoundry/plugins/pytorch/evaluation.py#L421)); validator check 13 is **`xfail(strict=True)`** ([test_recipe_validator.py:795](../../tests/unit/test_recipe_validator.py#L795)); the `baseline_model_id` **grammar is undefined** | **Needs a design pass** — settle grammar + scope (I.s), then implement the self-contained sklearn-fit half (I.t) |
| **FR-3** | Behavior step 1: "Run `validate` (FR-2); fail fast on any failure" — *before* cache identity + pipeline | `materialize()` constructs `MaterializeRunner().run()` directly with **no `validate()` call** ([modelfoundry.py:189](../../src/modelfoundry/core/modelfoundry.py#L189)); the runner does not validate either | Implement-ready |
| **FR-10** | "Training diverges (loss becomes NaN) → hard error with a clear 'training diverged at epoch N' message; partial `training/history.parquet` preserved in temp dir; `FAILED` marker written" | **No `isnan`/`isfinite`/divergence check anywhere** in [trainer.py](../../src/modelfoundry/plugins/pytorch/trainer.py) | Implement-ready, well-specified |
| **FR-13** | `predictions_grid` params `n: int = 16`, `splits: list[str]`, `per_class: bool = False`; `confusion_matrix` & `calibration_curve` take `splits: list[str]` (one figure over many splits, default `Evaluation.splits`) | Code carries only `max_items: int = 16` and `split: str \| None` (**singular**) — no `splits`, no `per_class`, param named `max_items` not `n` ([visualization_specs.py:38-45](../../src/modelfoundry/plugins/pytorch/visualization_specs.py#L38)) | Implement-ready; one design call (singular→plural, done byte-neutrally) |
| **FR-9** | "`schedule.monitor` references a metric not produced → caught by FR-2 check 6 (**extended for schedule monitors**)" | check 6 validates only `Training.early_stopping.monitor`, not `Optimizer.schedule.monitor` ([validator.py:225-238](../../src/modelfoundry/recipe/validator.py#L225)) | Small, implement-ready |

### Doc/code divergences — the spec word and the code word disagree

These are literal features-vs-code gaps: the contract describes one thing, the shipped code
does another. The resolution is to make the **doc follow the code** (the code is newer and
already authored into the recipe corpus / scaffolder), not the reverse.

| # | Spec says | Code says | Resolution |
|---|-----------|-----------|------------|
| D1 | Visualization `mode: exploration \| reporting` (features.md lines 117, 227, 470-471, 539, 633; FR-2 check 15) | `mode: reporting \| interactive` — deliberately renamed in Story I.e.3 (no-implicit-defaults), authored across the corpus + scaffolder ([models.py:202](../../src/modelfoundry/recipe/models.py#L202), [validator.py:407](../../src/modelfoundry/recipe/validator.py#L407)) | Update features.md `exploration` → `interactive` (doc follows shipped code) |
| D2 | Per-class metrics = label-keyed nested dicts (features.md:613) | Index-ordered `list[float]` (`per_class_f1 == [0.5, 0.8, 0.66]`); correct + efficient | Doc fix — describe the list shape |
| D3 | — | The entire **`Inference` / MC-dropout** capability (`InferenceSpec`, shipped Phase H, documented all over `README.md`) has **no FR in features.md** (`grep Inference features.md` → 0 hits) | Add an FR documenting the shipped stochastic-inference surface |

---

## 2. The promises this subphase closes (verbatim contract anchors)

Load-bearing facts each story must honor, copied so the subphase is self-contained:

- **FR-3 step 1** — `validate` runs first and fails fast; **step 2** is cache identity.
  The fix must preserve the constant-time cache-hit path (decide: validate-then-hit-check,
  accepting a cheap static validation on hits, vs. hit-check-then-validate-on-miss — settle
  in I.u; FR-3's ordering text favors validate-first).
- **FR-10 edge case** — NaN divergence is a **hard error**, not a silent NaN-loss run; the
  message names the epoch; partial history survives in the temp dir; the existing atomic
  layer writes `FAILED` on the raised exception ([cache/atomic.py](../../src/modelfoundry/cache/atomic.py)).
- **FR-12** — baseline is scored on the **same held-out splits**, same metric set, into
  `baseline.<split>.<metric>`. Failure mode is **warn + omit baseline + report names it +
  main metrics proceed** (the already-coded skip path). `comparison` is a **kept
  mode-selecting optional** (`comparison=None` ⇒ no baseline); its absent⇒behavior mapping
  is part of the versioned segment contract and must not change.
- **FR-12 determinism** — a **fit-on-train** baseline is a **new stochastic source**; it
  must be seeded under the four-invariant contract (`derive_seed` for the estimator's
  `random_state`), or the byte-identity guarantee breaks for comparison-declaring recipes.
- **FR-13** — `confusion_matrix`/`calibration_curve` `splits` default to `Evaluation.splits`;
  `predictions_grid` thumbnails are best-effort (labels-only fallback when the bound DR
  instance exposes no per-record images — already handled).
- **Cache identity** — every change here is **additive** or **doc-only**. The only
  canonical-bytes surfaces are recipe fields *authored only when used* (`comparison`, the
  new viz params). No existing shipped recipe authors them, so **no existing instance is
  perturbed** (see §6).

---

## 3. Feature / fix requirements (mini-features.md)

Folded into `features.md` by the doc story (I.y). New/clarified requirements:

- **FR-12 (completed) — sklearn-estimator baseline comparison.** `Evaluation.comparison`
  resolves a **scikit-learn estimator class** baseline, fits it on the `train` split (seeded),
  scores it on every `Evaluation.splits` entry with the same metric set, and writes the
  results under `evaluation/metrics.json` `baseline.<split>.<metric>`. The `baseline_model_id`
  **grammar is defined** (settled in I.s) and **validator check 13 enforces it** (xfail flips
  to pass). The **HF-pretrained-model comparison** is explicitly **out of scope** (§5).
- **FR-3 (enforced) — validate-before-materialize.** `materialize()` (library *and* CLI)
  runs the FR-2 checks and fails fast before any pipeline work, per FR-3 step 1.
- **FR-10 (enforced) — divergence guard.** A NaN/non-finite training loss raises a hard
  `PluginError` naming the epoch; the partial run leaves a `FAILED` marker (no silent NaN run).
- **FR-13 (completed) — visualization params.** `predictions_grid` accepts `n` / `splits` /
  `per_class`; `confusion_matrix` / `calibration_curve` accept `splits: list[str]` — added
  **byte-neutrally** (see §6).
- **FR-9 (completed) — schedule-monitor validation.** FR-2 check 6 also validates
  `Optimizer.schedule.monitor` against produced metrics.
- **FR-INFERENCE (documented) — stochastic inference surface.** The shipped `Inference`
  block (`mode: point | mc_dropout`, `mc_samples`) + the `.uncertainty` accessor + the
  per-record `predictive_entropy` / `mc_variance` persistence get a first-class FR
  (closes divergence D3).

**Recipe-surface impact (no-implicit-defaults discipline).** No new **required** field is
added. `Evaluation.comparison` already exists (a kept mode-selecting optional). The new viz
params are **optional, authored-only-when-used** sub-fields under the `plugin` segment. None
of this introduces a silent code default.

---

## 4. Technical changes (mini-tech-spec) & story breakdown

Each story = one coherent unit → one commit. Sequence and IDs continue from **I.r**.
(Ordering note: the FR-12 design+impl leads because it is the headline and most likely to
surface scope; the small implement-ready fixes follow; doc+release closes. Order is
adjustable at the approval gate.)

### I.s — FR-12 baseline-comparison design pass *(low/zero code; deliverable = settled design)*
Settle the open forks the audit flagged, appended as a **Design Decisions** section to this
plan doc (or a short sibling note):
- **`baseline_model_id` grammar.** Define the string format for a scikit-learn estimator
  class (candidate: `sklearn:RandomForestClassifier` / a dotted import path — pick one,
  pin it, write the check-13 regex).
- **Mechanism = fit-on-train.** Resolve the class, instantiate with seeded `random_state`,
  fit on the `train` feature matrix (reuse the **C.f flattened-feature path** + the
  existing `plugins/sklearn/metrics.py` scorers), predict per split.
- **Label-space.** None of the HF alignment problem applies — the estimator learns the
  bound instance's labels directly. Record this as the reason the sklearn half is the
  self-contained slice.
- **Determinism + persistence.** Seed the fit via `derive_seed(seed, "baseline")`; decide
  the persistence surface (recommendation: persist baseline **metrics** into
  `metrics.json`/report only — *not* a round-trippable baseline `ModelInstance`).
- **Explicit deferral** of the HF-pretrained half (§5) recorded here.

### I.t — FR-12 sklearn-fit baseline resolver + scoring + check-13 *(code)*
Replace the warn-and-skip stub ([evaluation.py:421](../../src/modelfoundry/plugins/pytorch/evaluation.py#L421))
with the resolver from I.s: resolve grammar → fit-on-train (seeded) → score per split →
write `baseline.<split>.<metric>` into `evaluation/metrics.json`; the report's comparison
subsection names the baseline. Tighten **validator check 13** to enforce the grammar and
**flip the `xfail(strict=True)`** ([test_recipe_validator.py:795](../../tests/unit/test_recipe_validator.py#L795))
to a pass. Keep the failure mode (unresolvable id → warn + omit + main metrics proceed).
Tests: a comparison-declaring recipe produces baseline metrics; determinism (byte-identical
across two runs); malformed id trips check 13.

### I.u — FR-3 validate-before-materialize *(code)*
Call the FR-2 checks at the head of `materialize()` (library) so both the library and CLI
surfaces fail fast before cache/pipeline work; preserve the constant-time cache-hit path
(settle validate-vs-hit ordering per §2). Tests: an invalid recipe raises before any temp
dir is created; a valid recipe is unaffected; a cache hit still short-circuits.

### I.v — FR-10 NaN-divergence hard error *(code)*
Add a non-finite-loss guard in the training loop ([trainer.py](../../src/modelfoundry/plugins/pytorch/trainer.py)):
on `not torch.isfinite(loss)`, raise `PluginError("training diverged at epoch N")`; the
partial `training/history.parquet` is already in the temp dir and the atomic layer writes
`FAILED` on the raised exception. Tests: a recipe forced to diverge raises with the epoch in
the message and leaves a `FAILED` marker; a normal run is unaffected.

### I.w — FR-13 visualization params *(code)*
Extend the viz param models ([visualization_specs.py](../../src/modelfoundry/plugins/pytorch/visualization_specs.py)):
`predictions_grid` gains `n` (alias/rename of `max_items`) + `splits` + `per_class`;
`confusion_matrix`/`calibration_curve` gain `splits: list[str]` (default `Evaluation.splits`),
rendering one figure over the listed splits. **Byte-neutrality** is the design constraint
(§6): add the new params without perturbing the canonical bytes of any recipe that authors
the *current* `split`/`max_items` form (alias-preserve or migrate-the-corpus-and-justify —
settle in-story). Tests: multi-split render; `per_class` grouping; byte-stability check.

### I.x — FR-9 check-6 schedule-monitor extension *(code)*
Extend FR-2 check 6 ([validator.py:225](../../src/modelfoundry/recipe/validator.py#L225)) to
also validate `Optimizer.schedule.monitor` (when an `Optimizer.schedule` is present) against
produced metrics + builtins, mirroring the early-stopping-monitor logic. Add an invalid
fixture; assert check 6 trips.

### I.y — Doc sync, project-essentials append & release — **owns the bump (→ v0.19.0)**
- **features.md**: fold in FR-12 (completed sklearn half + HF deferral), FR-3/FR-10
  (enforced), FR-13/FR-9 (completed), and the new **FR-INFERENCE**; fix divergences **D1**
  (`exploration`→`interactive`, ×5 + check-15), **D2** (per-class list shape), **D3**
  (Inference FR).
- **tech-spec.md**: reflect the baseline resolver, the validate-first ordering, the
  divergence guard, and the viz-param surface.
- **concept.md / README.md**: touch only if scope wording shifts (baseline comparison is
  now real, not aspirational).
- **project-essentials.md**: append any new must-know facts (plan_phase Step 8) — candidate:
  the baseline-comparison determinism rule (a fit-on-train baseline is a seeded stochastic
  source) and the doc-follows-code reconciliation precedent.
- **Future backlog**: record the deferred HF-pretrained comparison half as its own story.
- **Release**: owns the single minor bump **→ v0.19.0**; `CHANGELOG.md` entry; full CI gate
  green (ruff + ruff format --check + mypy src tests + light + smoke-pytorch).

---

## 5. Out of scope (deferred) — *to be walked through at the approval gate*

1. **HF-pretrained-model comparison half of FR-12** — running a pretrained HuggingFace
   classifier as the baseline. Design-heavy (label-space alignment / head-swap / zero-shot
   policy) **and** leans on the deferred `[huggingface]` extra. Its own future story; aligns
   with the developer's own verdict that this is the design-heavy half. *(In the pre-prod
   PyTorch-only install, only the sklearn-class baseline can even run today.)*
2. **Persisting the baseline as a loadable `ModelInstance`** — the baseline is scored inline;
   only its **metrics** persist (into `metrics.json`/report). A round-trippable baseline
   model is not in scope.
3. **Multiple baselines per recipe** — the grammar resolves a single estimator class;
   a baseline *list* is future.
4. **Renaming `interactive`→`exploration` in the code** — **rejected**; the resolution for
   D1 is doc-follows-code (Story I.e.3 deliberately chose `interactive`; the corpus +
   scaffolder already author it). Reversing it would be a cache-invalidating recipe-schema
   churn for no gain.
5. **Restructuring per-class metrics into label-keyed dicts (D2)** — the index-ordered list
   is correct + efficient; we fix the doc, not the code.
6. **A standalone `plan_features` formal pass** — the FRs are captured in this plan and folded
   into `features.md` by I.y; a dedicated `plan_features` revision runs only if the FR-12
   grammar (I.s) proves larger than a single field + check.
7. **A spike** — *deliberately omitted.* The one real design fork (FR-12 grammar + mechanism)
   is bounded enough to settle inside I.s; there is no unproven integration boundary or
   uncertain fix path warranting a throwaway effort.

---

## 6. Cache-identity & contract-alignment checklist

- **Not cache-invalidating for any existing instance.** Every change is additive or
  doc-only. The only canonical-bytes surfaces are recipe fields authored *only when used* —
  `Evaluation.comparison` (a pre-existing kept optional) and the new viz params (I.w) — and
  **no shipped recipe authors them**, so no existing image/audio instance is perturbed.
  *Output*-additive for a comparison-declaring recipe (it gains `baseline.*` metrics where it
  previously warned-and-skipped), but no such recipe ships today. Minor bump (new feature),
  pre-prod, **no production ceremony**.
- **Byte-neutrality is an explicit story constraint for I.w** — the viz-param extension must
  not shift the canonical bytes of recipes authoring the current `split`/`max_items` form
  (alias-preserve, or migrate-the-corpus-with-justification; settled in-story).
- **Determinism contract preserved.** The new fit-on-train baseline (I.t) is seeded via
  `derive_seed(seed, "baseline")` under the four invariants; the FR-10 guard (I.v) only adds
  an error path (no effect on a converging run's bytes). I.t includes a byte-identity test.
- **Loose-coupling invariant untouched** — nothing here re-hashes the bound DR instance or
  writes into DR's cache tree.
- **No new implicit defaults** — no behavior-affecting field gains a value-`default=`; the
  baseline is mode-selecting-optional (`comparison=None`), the viz params are
  authored-only-when-used.

---

## 7. Design Decisions — FR-12 baseline comparison (Story I.s)

This section is **Story I.s's deliverable**: the settled, implement-ready design that
I.t codes against. Grounded in the current source — `ComparisonSpec`
([recipe/models.py:157](../../src/modelfoundry/recipe/models.py#L157)), the warn-and-skip
stub ([plugins/pytorch/evaluation.py:150-151,421-427](../../src/modelfoundry/plugins/pytorch/evaluation.py#L150)),
check 13 ([recipe/validator.py:361-372](../../src/modelfoundry/recipe/validator.py#L361)) and its
`xfail` ([test_recipe_validator.py:795-808](../../tests/unit/test_recipe_validator.py#L795)),
the C.f flattened-feature path ([plugins/sklearn/data.py](../../src/modelfoundry/plugins/sklearn/data.py)),
the shared scorers ([plugins/sklearn/metrics.py](../../src/modelfoundry/plugins/sklearn/metrics.py)),
and the existing seeded-`random_state` precedent
([plugins/sklearn/plugin.py:208-209](../../src/modelfoundry/plugins/sklearn/plugin.py#L208)).

### D-I.s.1 — `baseline_model_id` grammar: `sklearn:<EstimatorClassName>`

**Decision.** One grammar: a `sklearn:` prefix followed by a scikit-learn classifier
**class name** — e.g. `sklearn:RandomForestClassifier`. The class is resolved through a
**curated allowlist** (name → fully-qualified import), *not* a free dotted import path.

- **Regex (the check-13 format check):** `^sklearn:([A-Za-z_]\w*)$`. The capture group is the
  estimator class name.
- **Why a `sklearn:`-prefixed allowlist, not a dotted import path
  (`sklearn.ensemble.RandomForestClassifier`).** A dotted path invites an arbitrary
  `importlib.import_module` + `getattr` — an unbounded import surface (any importable
  callable, estimator or not) that is both a safety smell and impossible to validate
  statically. The prefixed-short-name + allowlist keeps the surface bounded, makes the id
  self-documenting, keeps the check-13 regex trivial, and means *malformed → fail-fast at
  validate* while *unknown-but-well-formed → warn-and-skip at runtime* (D-I.s.4) — a clean
  split that honors the kept FR-12 failure mode.
- **Initial allowlist** (extensible; every entry is a classifier that consumes the flat
  `(n_samples, n_features)` matrix and exposes `predict_proba`, so the full
  `Evaluation.metrics` set — including `ece` / `calibration_curve` — scores uniformly):

  | `baseline_model_id` | Resolves to | `random_state`? |
  |---|---|---|
  | `sklearn:RandomForestClassifier` | `sklearn.ensemble.RandomForestClassifier` | yes |
  | `sklearn:GradientBoostingClassifier` | `sklearn.ensemble.GradientBoostingClassifier` | yes |
  | `sklearn:LogisticRegression` | `sklearn.linear_model.LogisticRegression` | yes |
  | `sklearn:KNeighborsClassifier` | `sklearn.neighbors.KNeighborsClassifier` | no (deterministic) |
  | `sklearn:DummyClassifier` | `sklearn.dummy.DummyClassifier` | yes |

- **Check 13 enforces the *format* only** (the regex). It does **not** assert allowlist
  membership — a well-formed `sklearn:SomethingUnknown` passes validate and hits the
  runtime warn-and-skip path (D-I.s.4). This keeps validate fast/static and matches the
  "unresolvable id → warn + omit + main metrics proceed" contract verbatim. (The `xfail`
  fixture `invalid_baseline_model_id.yml` carries a non-empty *malformed* id, so tightening
  check 13 to the regex flips it to a pass without touching the fixture — confirmed against
  [test_recipe_validator.py:805-808](../../tests/unit/test_recipe_validator.py#L805).)

### D-I.s.2 — Mechanism: resolve → seeded instantiate → fit-on-`train` → score per split

**Decision.** The baseline runs **inline in the evaluation stage**, reusing the existing
sklearn machinery so there is no re-implemented feature/normalization/scoring path to drift:

1. **Resolve** the allowlisted class (D-I.s.1).
2. **Instantiate** with all-defaults **except** a seeded `random_state` (D-I.s.3), set only
   when the estimator accepts one (`"random_state" in cls().get_params()` — guards
   `KNeighborsClassifier`).
3. **Fit on `train`** via `sklearn.data.feature_matrix(data, "train")`
   ([plugins/sklearn/data.py:27](../../src/modelfoundry/plugins/sklearn/data.py#L27)) — the
   **C.f flattened-feature path**, which reuses the PyTorch `DataRefineryDataset`
   (same train-fitted normalization, same all-splits label→index scan).
4. **Score per `Evaluation.splits`** with the **same metric set** as the main model, via the
   shared `plugins/sklearn/metrics.py` scorers (`accuracy` / `f1_score` / `per_class_*` /
   `expected_calibration_error` / `calibration_curve` / `confusion_matrix`).
5. **Write** under `evaluation/metrics.json` at a top-level `baseline` key:
   `baseline.<split>.<metric>` (matching FR-12's stated path; the existing per-split metrics
   are `metrics[split][metric]`, so the baseline nests parallel as
   `metrics["baseline"][split][metric]`). The report's comparison subsection names the
   `baseline_model_id` and shows main-vs-baseline on the `primary_metric`.

- **Label space — why this is the self-contained half.** `feature_matrix` returns `y` in the
  bound instance's own index-ordered label space (shared with the main model's `class_names`),
  so the estimator **learns the dataset's labels directly**. None of the HF
  label-space-alignment / head-swap / zero-shot problem applies — that is exactly what makes
  the sklearn-class baseline shippable now and the HF-pretrained baseline the design-heavy,
  deferred half (D-I.s.4 / §5).
- **Code home (recommended, settle final placement in I.t).** A new small, torch-free module
  `plugins/sklearn/baseline.py` (or `plugins/baseline.py`) exposing
  `score_baseline(baseline_model_id, data, evaluation, seed) -> dict[str, dict[str, Any]]`,
  imported lazily at the call site
  ([plugins/pytorch/evaluation.py:150](../../src/modelfoundry/plugins/pytorch/evaluation.py#L150),
  replacing `_baseline_comparison_warning`). Recommend factoring the sklearn plugin's private
  `_split_metrics` ([plugins/sklearn/plugin.py:387](../../src/modelfoundry/plugins/sklearn/plugin.py#L387))
  into a public `metrics.score_split(...)` so the baseline and the sklearn evaluator share one
  scorer. The sklearn-plugin evaluator's own warn path
  ([plugins/sklearn/plugin.py:291-296](../../src/modelfoundry/plugins/sklearn/plugin.py#L291))
  may adopt the same helper or keep warning — **I.t's call** (out of I.s scope to mandate).

### D-I.s.3 — Determinism: a fit-on-train baseline is a new seeded stochastic source

**Decision.** Seed the estimator via `random_state = derive_seed(seed, "baseline") & _U32`
(the 32-bit mask mirrors the existing `derive_seed(seed, "weight_init") & _U32` pattern;
`sklearn` requires `random_state ∈ [0, 2³²−1]`). This is a **new stochastic source** and
**must** be seeded under the four-invariant determinism contract, or the byte-identity
guarantee breaks for comparison-declaring recipes. A distinct `"baseline"` scope keeps the
baseline RNG independent of weight-init / dropout / DataLoader streams. I.t carries a
**byte-identity test** (two runs of a comparison-declaring recipe → identical `baseline.*`).

### D-I.s.4 — Failure mode (kept) + persistence surface + HF deferral

- **Failure mode — kept verbatim.** `comparison=None ⇒ no baseline` (a kept mode-selecting
  optional; the absent⇒behavior mapping is part of the versioned segment contract — do not
  change it). A well-formed-but-unresolvable id (not in the allowlist, or import/fit raises)
  → **warn + omit the `baseline` block + the report names it + main metrics proceed**
  (the already-coded skip path, just re-pointed from "always skip" to "skip on failure").
  A *malformed* id is caught earlier by check 13 at validate and never reaches runtime.
- **Persistence surface.** Persist baseline **metrics only** — into
  `evaluation/metrics.json` (`baseline.<split>.<metric>`) and the report's comparison
  subsection. **No** round-trippable baseline `ModelInstance`, **no** baseline
  `predictions.parquet`, **no** fitted-estimator artifact on disk (§5 item 2). The baseline
  is a scored comparison number, not a deliverable model.
- **HF-pretrained half — explicitly deferred.** Running a pretrained HuggingFace classifier
  as the baseline (label-space alignment / head-swap / zero-shot policy + the deferred
  `[huggingface]` extra) is **out of scope** here and recorded as its own future story
  (§5 item 1; I.y files it into `## Future`). In the pre-prod PyTorch-only install, only the
  sklearn-class baseline can run today.

### Implement-ready handoff to I.t

- Tighten check 13 to the D-I.s.1 regex; flip the `xfail` to a pass (fixture unchanged).
- Add `plugins/sklearn/baseline.py::score_baseline` (resolver + seeded fit-on-train + per-split
  scoring), factor `metrics.score_split`, wire it into the pytorch evaluator replacing the
  warn stub; write `baseline.<split>.<metric>`; name the baseline in the report.
- Tests: comparison-declaring recipe produces `baseline.*`; byte-identical across two runs;
  malformed id trips check 13; well-formed-unknown id warns + omits + main metrics proceed.
- **Cache identity:** additive/output-only; `comparison` is a pre-existing kept optional and
  no shipped recipe authors it → **no existing instance perturbed** (§6).
