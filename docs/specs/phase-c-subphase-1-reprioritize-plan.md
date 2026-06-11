# Phase C Plan — Subphase C-1: Reprioritize to Client Requirements

> Status: **DRAFT for approval** (plan_phase Step 4/5). Nothing is written to
> `stories.md` until the developer approves this plan. Going forward this is the
> **Phase C plan**: it reprioritizes Phase C (PyTorch Plugin + Materialize
> Orchestrator) so the client vertical — declaratively build, tune, train, and
> summarize a ResNet-20 on a CIFAR-10 instance, CPU-only, readable in a notebook —
> is delivered first.
>
> **Structure decision (developer, 2026-06-11).** Don't relocate the existing
> Phase C stories. Instead: (a) new work with **no blocking Phase C dependency**
> stays in **Phase B**, appended sequentially; (b) new work that **depends on
> Phase C** lands in **Phase C under a new `## Subphase C-1` heading** (the moved
> reprioritization description), either by extending an existing `[Planned]`
> Phase C story body or as a new Phase C story.
>
> **Cross-repo contract status (2026-06-11): converged.** The DataRefinery
> ↔ ModelFoundry `vendor-dependency-spec.md` round-trip is complete. Normalization
> is settled as **Option B** (DR persists per-channel stats; the consumer applies
> them); the fitted-stats consumer surface is **ratified**; three further surfaces
> (`label_classes`, `sample/`, the geometry-transform apply-boundary) are
> **forward-declared to DataRefinery v0.20.0** with documented interim paths. The
> remaining work is ModelFoundry-side — see §4 and §8.

## 1. Context and goal

A client engagement requires ModelFoundry to deliver, end to end, the
declarative construction-through-evaluation path for a **residual CNN
(ResNet-20 family) over a materialized CIFAR-10 DataRefinery instance**, run
**CPU-only within a per-step time budget**, tuned with **Optuna**, and fully
**readable from a notebook** — including a generated **model summary** that
reports layer types, output shapes, and parameter counts.

This reprioritizes Phase C: the PyTorch vertical (C.a–C.p) is the spine, and this
subphase adds the few features the brief needs that the roadmap lacks
(`resnet20`, a torchinfo model summary, a tunable batch-size/patience search
space, a working sklearn baseline) plus the deliverable recipe. The remaining
breadth of Phases D–G stays where it is.

The deliverable for ModelFoundry is **tested library/CLI functionality**, not the
client's downstream artifacts (the notebook itself, its HTML/PDF export, and the
written curriculum prose are produced by sibling tooling and by the client —
see §6, Out of scope).

## 2. Requirements derived from the client brief (sanitized)

| ID | Requirement | Primary surface |
|----|-------------|-----------------|
| R1 | Declaratively construct a residual CNN (ResNet-20 family) bound to a materialized CIFAR-10 instance | recipe `Architecture` block + PyTorch architecture vocabulary |
| R2 | Generate a **model summary** reporting per-layer **type**, **output shape**, **parameter count**, **mult-adds**, and network **totals** (incl. trainable vs non-trainable) | torchinfo-backed summary feature |
| R3 | Summary is legible as a layer inventory — conv / pooling / dense plus supporting BatchNorm / ReLU — with counts | summary surface (same as R2) |
| R4 | Total-parameter / capacity reasoning is readable from the summary (the numbers, not the prose) | summary totals (same as R2) |
| R5 | Hyperparameter optimization via Optuna **TPE + median pruning**, **random-search fallback**, over **learning rate, optimizer (AdamW / SGD+momentum), weight decay, LR schedule, batch size, early-stopping patience**; best config persisted and auto-applied at final training | Optuna optimization + search-space mechanism |
| R6 | PyTorch emits **logits**; softmax folded into **CrossEntropyLoss** | losses vocabulary |
| R7 | **CPU-only** execution within a per-step time budget | `Training.device` (done, B.n) + recipe calibration |
| R8 | Objective is **validation accuracy** on class-balanced splits | evaluation metrics |
| R9 | Everything above is readable substrate-neutrally **in a notebook** | `ModelInstance` accessors |

The brief also frames an sklearn `MLPClassifier` as an earlier "ceiling baseline"
and reuses the declarative model for Keras 3.x later in the curriculum. Per the
scope decisions (§6): the **sklearn baseline is in scope** (working, not stub);
**Keras stays Future**.

## 3. Gap analysis — planned vs. needed

Most of R1, R5–R9 are already designed across **Phase C** and the **Phase E**
CIFAR-10 smoke. This plan **extends** the relevant Phase C stories and adds two
new ones, rather than re-authoring the vertical.

### 3.1 Already covered by existing `[Planned]` Phase C / done stories

| Requirement | Covered by | Notes |
|-------------|------------|-------|
| R1 construction | **C.b** (plugin scaffold), **C.c** (architecture vocab — has `ResidualBlock` + `resnet8`), **C.o** (orchestrator), **C.p** (`ModelFoundry`/`ModelInstance` API) | C.c **extended** with `resnet20` — §5 |
| R5 optimization | **C.d** (losses/optimizers/schedules), **C.i** (Optuna TPE/median-pruner, baseline-trial enqueue, best-params merge), **B.m** validator checks 7–10 | C.i **extended** with batch_size/patience — §5 |
| R6 logits/CE | **C.d** (`cross_entropy`) | covered |
| R7 CPU budget | **B.n** (`Training.device`, **Done**) + plugin device resolution in C.b/C.e/C.h/C.j/C.l | recipe calibration is new — C.r |
| R8 val accuracy | **C.j** (`MulticlassAccuracy`) | covered |
| R9 notebook readability | **C.p** (accessors), **E.k** (Jupyter smoke) | the *summary* accessor is new — C.q |
| determinism | **C.a** (spike), **C.e** (module), **B.j** (seeding, **Done**) | covered |
| data adapter | **C.f** (`DataRefineryDataset`), **C.g** (augmentations), **B.i** (binding, **Done**) | C.f **extended** with normalization + interim label scan — §5 |
| persistence/round-trip | **C.l** | covered |
| end-to-end smoke | **E.l** (CIFAR-10 smoke, 500/100/100) | real-shape deliverable is new — C.r |

### 3.2 Genuine new work

- **G1 — Model summary (torchinfo).** Nothing in the roadmap; the spine of
  R2–R4. New Phase C story **C.q**.
- **G2 — `resnet20` baseline.** C.c plans `resnet8`; the brief anchors on
  canonical ResNet-20 (~272k params). **Extends C.c.**
- **G3 — Deliverable recipe + CPU-budget calibration.** Real-shape
  (1,700/300/1,000) recipe + measured budget + e2e test, distinct from the E.l CI
  smoke. New Phase C story **C.r**.
- **G4 — `batch_size` / `early_stopping.patience` tunable.** **Extends C.i.**
- **G5 — Working sklearn baseline.** Promote the C.m stub to a real
  `MLPClassifier` (Q3 = yes). **Promotes C.m.**
- **G6 — DataRefinery v0.19.0 adoption.** Dependency bump + schema-v2 tracking +
  B.i re-validation. **No Phase C dependency → Phase B story B.q.**

## 4. Conflicts and concerns

- **C1 — Summary surface. ✅ DECIDED: materialize-time artifact** (Q2). C.q writes
  `model/summary.txt` + structured `model/summary.json` at materialize time, plus
  a `ModelInstance.summary` accessor and `inspect --view model_summary`.
  Reproducible, diffable, readable from disk alone (FR-23 discipline). The summary
  is *output bytes* (byte-deterministic), not recipe bytes — it does not enter the
  cache key, but per `project-essentials.md` it must be byte-stable.
- **C5 — CPU budget vs. 20–30 trials (calibration risk).** Full ResNet-20 on CPU
  across 20–30 trials can exceed the per-step budget. C.r must reconcile via
  capped epochs-per-trial, median pruning, and/or fewer trials — **measured**, not
  assumed.
- **C6 — Cache invalidation.** Adding `resnet20` and any pydantic-default touches
  perturb canonical bytes for affected recipes; pre-prod acceptable with a
  release-notes callout per `project-essentials.md`. The summary artifact is
  output-only (no cache-key impact).
- **C7 — Notebook authoring/export is a sibling-tool boundary.** ModelFoundry
  stops at substrate-neutral accessors (including the summary); rendering/exporting
  is the notebook/curriculum tooling's job.
- **C8 — Normalization. ✅ RESOLVED: Option B** (ratified in the vendor-spec). DR
  persists per-channel `mean`/`std`; the C.f adapter applies them. The spec pins
  the parquet shape (single `value` column, `C` rows, **RGB** order) and makes the
  **zero-variance guard a consumer obligation** (exact `std == 0 → 1.0`, no
  tolerance). Both become C.f obligations (§5).
- **C9/C11 — DataRefinery v0.19.0 adoption.** Installed `ml-datarefinery` is
  **0.17.0**; A.c/B.i were built against it. The ratified contract is v0.19.0
  (schema v2, `recipe.json` not `recipe.yaml`, `class_balance` 0.18.0+). Binding a
  v2 instance on a v1-only ModelFoundry hard-errors. → Phase B story **B.q**: bump
  to `>= 0.19.0`, track schema v2, re-validate B.i.
- **C10 — `class_balance` ↔ `weight_source` ownership. Out of scope for C-1,
  tracked.** The vendor-spec's `manifest.class_balance` is a forward-declared
  training-time hint the consumer must honor (`WeightedRandomSampler` /
  per-class weights), overlapping our own `cross_entropy_class_weighted`
  `weight_source` (C.d) — double-application risk. **Moot for balanced CIFAR-10**
  (`class_balance` is `null`), so deferred — but a real recipe-as-truth ownership
  decision for C.d + the validator; tracked so it is not lost.

## 5. Composition

Story letters continue monotonically. **Phase B** last story is **B.p** → new
Phase B work begins at **B.q**. **Phase C** last story is **C.p** → new Phase C
stories begin at **C.q**, grouped under a new `## Subphase C-1` heading.

### 5.1 Phase B — one new story (no Phase C dependency, lands now)

- **B.q — DataRefinery v0.19.0 adoption.** Bump `ml-datarefinery` **0.17.0 →
  >= 0.19.0**; update the tracked `SUPPORTED_SCHEMA_VERSIONS` to include **v2**;
  re-validate **B.i** binding + **B.m/B.n** validator checks 19/20 against the v2
  / `recipe.json` shapes (incl. reading `recipe.json`, not `recipe.yaml`). Touches
  only done Phase B modules — independent of Phase C, so it lands in Phase B and
  before the C.r deliverable that binds the v2 instance. Addresses **G6, C9/C11**.

### 5.2 Phase C / Subphase C-1 — extensions to existing `[Planned]` stories

Edit the story bodies in place (they are `[Planned]`, not done — go.md permits
editing existing story bodies). No renumbering.

- **C.c (+ `resnet20`).** Add the ResNet-20 baseline: stem → 3 stages at 16/32/64
  channels → global average pool → linear head, with **option-B projection
  shortcuts** (1×1 conv on the two downsampling blocks), **bias-free convs**
  (BatchNorm follows each), **strided-conv downsampling** (not max-pool). Test
  pins the canonical layer inventory and total parameter count (~272k). Update
  `features.md` FR-ARCH-1 + `tech-spec.md` `[pytorch]` vocabulary line. **G2.**
- **C.f (+ normalization, + interim label scan, + geometry guard).** Apply the
  fitted per-channel `mean`/`std` via `Instance.fitted_statistics` at
  `__getitem__`: line up the **RGB** channel order, `(x - mean) / std` with the
  **exact `std == 0 → 1.0` guard** (no tolerance), honoring **chained fit-on-train
  op order** from `recipe.json`. Derive the class set from **all labeled splits +
  sort ascending** (interim until DR v0.20.0 `manifest.label_classes`), not
  train-only. **Refuse lazy-mode geometry transforms** (no `resize` baked) per the
  vendor-spec J.g interim guidance — a guard, not a feature (CIFAR-10 has none).
  **C8, C9/C11.**
- **C.i (+ `batch_size` / `early_stopping.patience` search space).** Extend the
  search-space mechanism to tune both; ensure validator check 7 accepts the paths;
  test a study that varies them. **G4.**
- **C.m (promote stub → working sklearn `MLPClassifier`).** Replace the
  refuse-to-materialize stub with a real baseline: feature-flatten adapter,
  sklearn train/eval path, usable as `Evaluation.comparison.baseline_model_id`.
  Keep the shared `plugins/sklearn/metrics.py` (already a C.j dependency). **G5.**

### 5.3 Phase C / Subphase C-1 — new stories

- **C.q — Model summary (torchinfo).** Add `torchinfo` to the `[pytorch]` extra;
  a plugin capability producing per-layer type/shape/params + mult-adds + totals
  (incl. trainable/non-trainable split); the **materialize-time artifact**
  `model/summary.{txt,json}` (C1); a `ModelInstance.summary` accessor; an
  `inspect --view model_summary` view (FR-17); a new **FR-27** in `features.md` +
  a `tech-spec.md` section; a determinism test on the summary bytes. **G1,
  R2–R4.**
- **C.r — Deliverable CIFAR-10 / ResNet-20 recipe + CPU-budget calibration +
  e2e.** A real-shape recipe (1,700/300/1,000) with the R5 search space,
  calibrated to the CPU per-step budget (**measured**), materialized end-to-end;
  tests assert the summary is produced and readable, the study runs and persists
  best-params, final training applies them, and validation accuracy is computed.
  Distinct from E.l's downsized CI smoke. **Hard upstream dependency** on the
  DataRefinery CIFAR-10 instance (DR-1, §8) and on **B.q** (v0.19.0 adoption).
  **G3, R1/R7/R8/R9.**

### 5.4 Sequencing note (finalize at stories.md write time)

The `## Subphase C-1: Reprioritize to Client Requirements` heading carries the
reprioritization description (moved from the former Subphase B-1). The mechanical
question of exactly where the heading sits and how C.q/C.r interleave with C.a–C.p
in execution order is a stories.md-writing detail to settle on approval — the
intent is that the CIFAR-10/ResNet-20 client vertical is the first thing Phase C
delivers.

## 6. Out of scope (confirmed)

- **`[keras]` plugin** — stays in `## Future` (the curriculum's later Keras module
  depends on it, but it is not needed for this deliverable).
- **Notebook authoring + HTML/PDF export** — sibling-tool / client responsibility.
- **Per-class evaluation metrics** — deferred to a later evaluation concern; this
  subphase's objective is validation accuracy (R8). C.j still *registers* the
  per-class metric vocabulary.
- **`class_balance` ↔ `weight_source` ownership rule** — tracked (C10); moot for
  balanced CIFAR-10; a future C.d/validator decision.
- **Continued training / optimizer-state checkpoints** — B.k foundation exists;
  populating it stays in `## Future`.
- **Tight-coupled DataRefinery binding (FR-26)** — unchanged; loose coupling holds.
- **`sample/` fast-iteration binding** — blocked until DataRefinery v0.20.0 (DR-4,
  §8); C.r calibrates against the full instance or a downsized recipe.
- **B.o / B.p (pyve 3.0 env reconfig + doc reconcile)** — independent infra/doc
  Phase B stories; not prerequisites. Sequence at the developer's discretion.

**In scope (confirmed this round):** the **working sklearn baseline** (C.m
promotion, G5) — the brief's "ceiling baseline" is materialized through
ModelFoundry, not left as a stub.

## 7. Decisions (resolved 2026-06-11)

1. **Structure** — not a relocation. Phase-C-dependent work → Phase C / Subphase
   C-1 (extend C.c/C.f/C.i, promote C.m, add C.q/C.r); independent dep-bump →
   Phase B (B.q). This file is the Phase C plan.
2. **Summary surface (C1)** — materialize-time artifact (`model/summary.{txt,json}`)
   + accessor + inspect view.
3. **sklearn baseline (G5)** — in scope; promote C.m to a working `MLPClassifier`.
4. **Granularity (G2/G4)** — fold into the existing Phase C stories they extend
   (C.c, C.i); no separate stories for those.
5. **Normalization (C8)** — Option B (settled by the contract round-trip).

Still tracked (not blocking C-1): **C10** (`class_balance`/`weight_source`
ownership, future C.d decision); **`label_classes`** adoption when DR v0.20.0 is
taken up (interim all-splits scan until then).

## 8. DataRefinery upstream dependencies (owner: DataRefinery)

Not ModelFoundry stories — upstream work/contract the deliverable binds against.
C.r cannot be proven end-to-end until DR-1 is ready. (Refs: `docs/specs/datarefinery/`.)

- **DR-1 — CIFAR-10 base data instance.** A DataRefinery recipe + materialized
  instance with the **1,700 / 300 / 1,000** balanced splits, declaring at minimum:
  a fit-on-train **`normalize`** (per-channel, `fit_source: train`); the
  **`Augmentations`** policy (`random_crop` with reflect padding,
  `horizontal_flip`, `color_jitter`) as lazy manifest-bound policy; balanced-split
  production. ModelFoundry consumes read-only.
- **DR-2 — Fitted-statistics consumer contract. ✅ DONE / ratified.** The
  vendor-spec now carries § "Fitted statistics ModelFoundry binds against": layout,
  `mean`/`std` convention (single `value` column, `C` rows, RGB), the
  consumer-applied boundary, and the zero-variance guard. Option B is ratified.
- **DR-3 — Determinism of the prepared instance.** DataRefinery's existing
  contract (seeded ops via `recipe.seeds`/`derive_seed`, byte-identical
  re-materialization); re-confirm against the real CIFAR-10 recipe. No new work
  expected.
- **DR-4 (optional) — `sample/` subset. Blocked until DR v0.20.0.** Consumers
  SHOULD NOT bind pre-J.a; C.r uses the full instance or a downsized recipe.
- **DR scheduling confirmation (one open question for DataRefinery).** Can DR-1 be
  produced **now at v0.19.0**? It needs only `normalize` + the augmentation policy
  (both available); `label_classes` / `sample/` / the J.g fix are v0.20.0 but
  **none are required** for our flow (interim all-splits label scan). Expected
  answer: yes, not gated on v0.20.0 — to confirm.

**ModelFoundry-side counterparts (in this plan):** the C.f adapter obligations
(§5.2: RGB normalize + exact zero-var guard + chained-op order + geometry guard +
interim label scan) and **B.q** (v0.19.0 adoption). `class_balance` handling is
out of scope (C10).
