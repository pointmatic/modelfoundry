# DataRefinery ↔ ModelFoundry dependency contract

> **Status:** authoritative cross-repo contract (Story H.s, v0.15.0).
> Pre-production: this document may evolve as ModelFoundry adoption
> surfaces gaps. Post-production: it becomes a stability contract —
> changes follow the schema-version-bump + migration ceremony in
> `docs/specs/project-essentials.md` § "Cache identity is the
> reproducibility contract."
>
> **DataRefinery counter-proposal 2026-06-11.** The 2026-06-11
> ModelFoundry-side revision was reviewed against current DataRefinery
> source. **Accepted:** the new § "Fitted statistics ModelFoundry binds
> against", the instance-level on-disk tree, the explicit
> `LATEST_SCHEMA_VERSION = 2` coordination note, and the "missing
> required fitted statistics" failure mode. **Corrected:** the
> persisted recipe file is `recipe.json` (not `recipe.yaml`); the
> dropped `manifest.class_balance` row + shape subsection are restored
> (DR still emits the field, v0.18.0+); the schema v1→v2 migration
> detail subsection is restored under § Cache-identity contract; the
> stage-aware viz dispatch clarification is restored under § Report
> subsections; the `normalize` "std may be absent" claim is corrected —
> DR's `normalize` always emits both `mean` and `std`, mean-only
> behavior is the separate `mean_subtract` op (different `op_id`
> directory, no `std.parquet`). **Forward-declared by DR:** the
> `manifest.sample` row + shape subsection and the instance-tree
> `sample/` block, targeting Phase J Story J.a (v0.20.0). Full
> coordination on Phase J surfaces happens when J.a lands.
>
> **Round 2 additions 2026-06-11.** ModelFoundry clarifying questions
> surfaced three further contract gaps. **Pinned** in this round: the
> `normalize` parquet internal shape and channel ordering (single
> `value` column, `C` rows, RGB axis order for the v1
> image_classification plugin); the **zero-variance std guard** as an
> explicit consumer obligation (exact `std == 0` substitution to `1.0`,
> no tolerance) so consumer-applied normalization matches DR's apply
> semantics on every channel; the `manifest.class_balance` per-class-
> counts and chained fit-on-train ordering notes; and the fact that the
> original authored YAML is **not** persisted in the instance (only the
> canonical `recipe.json` is). **Forward-declared** in this round:
> `manifest.label_classes` (Phase J Story J.f, target v0.20.0) closes
> the class-set enumeration gap so consumers stop deriving
> sorted-from-train independently. **New § Consumer-applied
> transformations vs. baked transformations** (Phase J Story J.g,
> target v0.20.0) draws the apply-boundary explicitly and identifies
> the lazy-mode geometry-transform gap (`path` points at source while
> `Transformations` are not reflected in JSONL pixels).

## Overview

This document is the **cross-repo contract surface** between DataRefinery (data-pipeline producer) and ModelFoundry (downstream training consumer), and is the authoritative reference for any downstream tool that binds against a materialized DataRefinery instance.

It enumerates exactly what DataRefinery emits — recipe-side fields, on-disk dataset layout, manifest keys, report subsections — that external consumers depend on, and the rules by which those surfaces may change. The intent is to let DataRefinery and ModelFoundry evolve on independent schedules: DataRefinery ships forward-declared contracts at release time; ModelFoundry adopts on its own schedule without requiring DataRefinery to wait.

Out of scope here: ModelFoundry's training-time APIs (those live in ModelFoundry's repo) and DataRefinery's internal implementation details (those live in `tech-spec.md` and `features.md`).

## Recipe-side contract

A recipe is a YAML document validated by `Recipe.model_validate(...)` in `src/datarefinery/recipe/models.py`. The full schema is documented in `tech-spec.md` § Data Models; this section calls out the augmentation surface (Story H.p–H.r.2) that ModelFoundry consumes directly.

### `Augmentations` section

The `Augmentations:` top-level list contains zero or more `AugmentationOp` entries. Each entry has the following fields:

| Field             | Type                                                              | Default       | Notes |
|-------------------|-------------------------------------------------------------------|---------------|-------|
| `name`            | `str`                                                             | required      | Human-readable instance label; unique within the section. |
| `op`              | `str`                                                             | required      | Op name (`horizontal_flip`, `random_crop`, `color_jitter`, `random_erasing`). |
| `params`          | `dict[str, Any]`                                                  | `{}`          | Op-specific parameters; see per-op param schemas below. |
| `splits`          | `list[str]`                                                       | `["train"]`   | Validator check 5 rejects non-train splits. |
| `seed`            | `int | None`                                                      | `None`        | Per-op seed; combined with the global seed during realization. |
| `materialization` | `Literal["lazy", "aggressive"]`                                   | `"lazy"`      | See § Materialization modes below. |
| `expansion`       | `int`                                                             | `1`           | Number of variants produced per input record in aggressive mode. Must be `>= 1`; `expansion > 1` requires `materialization == "aggressive"` (model validator). |

### Materialization modes

Two modes coexist per-op. A single `Augmentations:` block may mix lazy and aggressive ops.

- **`materialization: lazy`** (default). The op is captured as a manifest-bound `AugmentationPolicy` and emitted in the report's augmentation summary. The materialized dataset is **unchanged** — record count and image bytes are exactly what they would be without the op. ModelFoundry's framework adapter reads the policy and realizes augmented examples on-the-fly during training.

- **`materialization: aggressive`**. At materialization time, DataRefinery realizes `expansion` augmented variants per train record via the plugin-registered `Realizer`. Variants become **peer records** in the materialized dataset (record multiplication, see on-disk layout below). The variant's image bytes are persisted as per-record sidecar PNGs; ModelFoundry treats variants as first-class records and does not re-realize them.

### Per-op param schemas

Validated by the realizer's pydantic param model on first variant emission. The plugin's `OperationSpec` also enumerates the same parameters for the recipe validator's check 18.

- **`horizontal_flip`** (`HorizontalFlipParams`)
  - `p: float = 0.5` in `[0.0, 1.0]` — probability of flipping per variant.
- **`random_crop`** (`RandomCropParams`)
  - `size: int | tuple[int, int]` — required; positive.
  - `padding: int = 0` — non-negative.
  - `padding_mode: Literal["reflect", "replicate", "zero", "constant"] = "reflect"`.
- **`color_jitter`** (`ColorJitterParams`)
  - `brightness`, `contrast`, `saturation: float = 0.0` in `[0.0, 1.0]`.
  - `hue: float = 0.0` in `[0.0, 0.5]`.
  - Per-dimension offset drawn uniformly in `[-magnitude, +magnitude]`.
- **`random_erasing`** (`RandomErasingParams`)
  - `p: float = 0.5` in `[0.0, 1.0]`.
  - `scale: tuple[float, float] = (0.02, 0.33)` — erased-area fraction range.
  - `ratio: tuple[float, float] = (0.3, 3.3)` — aspect-ratio range; sampled log-uniformly.

## Materialized dataset on-disk layout

A materialized instance lives under `<cache-root>/instances/<recipe-hash16>/<input-hash16>/<seed>/`. Within that directory, the consumer-relevant blocks are:

```text
<instance>/
├── manifest.json
├── recipe.json                  # canonical v2-shape recipe (loader-migrated if authored as v1)
├── dataset/
│   ├── train.jsonl              # one record per line
│   ├── val.jsonl
│   ├── test.jsonl
│   └── <split>/
│       └── images/
│           └── <record_id>.png  # FR-11 aggressive-mode variants only (Story H.r.2)
├── fitted_statistics/           # fit-on-train stats; see § Fitted statistics ModelFoundry binds against
│   └── <op_id>/
├── sample/                      # DataRefinery SampleData runtime subset (forward-declared for Phase J / v0.20.0)
│   └── <split>.jsonl
└── report/                      # see § Report subsections
```

`recipe.json` is the canonical-form recipe — the same bytes hashed for the cache key (see § Cache-identity contract). DataRefinery's loader applies any v1→v2 migration before persisting, so consumers reading `recipe.json` always see the v2-shape regardless of the recipe's authored version.

**The original authored YAML is NOT persisted in the instance.** The instance holds only the canonical JSON form (for reproducibility and cache identity). The authored YAML is the user's source artifact and lives in the user's repo, referenced by path. Consumers that need to display "what the user wrote" must retain the source path separately — pretty-printing `recipe.json` gives "what was materialized," which is post-migration and key-sorted and may diverge from the YAML the user actually authored.

The `sample/` block is forward-declared: DataRefinery's `SampleData` runtime ships in Phase J (target v0.20.0, Story J.a). Recipes that omit `SampleData:` do not produce a `sample/` directory. The shape subsection (§ `manifest.sample`) is the binding contract once J.a lands; until then it is informational.

### JSONL records

Each JSONL line is a single record dict, serialized with sorted keys for byte-stability. Non-JSON-native fields (numpy arrays, bytes, custom objects) are dropped at serialization.

**Common fields** present on every record:

- `record_id: str` — stable identifier for the record.
- `label`: any JSON-native type; absent on unlabeled-partition records (FR-22 / unlabeled support).

**Source-resolution path** (non-aggressive records):

- `path: str` — the source-image file path. Image bytes resolve via the source filesystem. **The `image` numpy field is dropped at serialization** — downstream consumers read pixels from `path`.

**Aggressive-mode variants** (Story H.r.2):

- `source_record_id: str` — record_id of the input that produced this variant.
- `variant_index: int` — zero-based index within the variant pack; range `[0, expansion)`.
- `image_path: str` — relative path under `dataset/` (e.g. `"train/images/img_001__v002.png"`) pointing at the sidecar PNG. ModelFoundry consumers MUST resolve variant pixels via `image_path`; the source `path` field, if present on a variant, is not authoritative.

**Per-record-seed stamps** (Story I.e):

- `<GenerationOp.name>_seed: int` — present on every record produced by a per-record-stochastic Generation op (today: `imagecorruptions_apply`). 8-byte unsigned integer, derived as `pipeline.workers.per_record_seed(GenerationOp.seed, input_record)`.
- `<AugmentationOp.name>_seed: int` — present on every variant produced by an `aggressive`-materialization Augmentation. 8-byte unsigned integer, derived as `pipeline.workers.per_record_variant_seed(global_seed, input_record, variant_index, op_id=AugmentationOp.op)`.

These seeds are the value used by the op's RNG. Consumers reconstructing stage output post-hoc (e.g., the future `datarefinery export` verb) replay the op with the recorded seed to reproduce the bytes the pipeline saw at that stage. Lazy-mode augmentations and ops whose stochasticity is op-level (`duplicate_minority_class`) do not stamp.

### Record-multiplication shape

A recipe declaring `expansion=N` aggressive op against the train split produces `len(train_records_pre_aug) * N` JSONL lines and exactly the same number of sidecar PNGs. Two aggressive ops chained compose multiplicatively (`expansion=a` then `expansion=b` → `N × a × b` records).

Variant `record_id`s are derived as `f"{source_record_id}__v{variant_index:03d}"` — unique, zero-padded for lex-order = numeric-order under standard sort.

### Sidecar PNG encoding

Pillow `Image.save(path, format="PNG", optimize=False)`. Defaults verbatim — no quality/compression knobs. Determinism check: two runs of the same recipe + seed + inputs produce byte-identical sidecar files (validated by `tests/integration/test_runner.py` :: `test_aggressive_materialize_is_deterministic_across_runs`).

## Manifest fields ModelFoundry binds against

The `manifest.json` at the instance root is the authoritative metadata document. ModelFoundry-relevant fields:

| Field                  | Type                       | Meaning |
|------------------------|----------------------------|---------|
| `schema_version`       | `int`                      | Manifest schema version; separate from recipe `schema_version`. Currently `1`. |
| `plugin`               | `str`                      | Plugin name (e.g., `"image_classification"`). |
| `plugin_version`       | `str`                      | Plugin schema version, as string. |
| `recipe_hash`          | `str` (64-hex)             | Canonical recipe bytes' SHA-256 (full digest). |
| `input_hash`           | `str` (64-hex)             | Per-source input content hash. |
| `seed`                 | `int`                      | The seed used by this materialization (CLI `--seed` overrides the recipe's `seed`). |
| `variant`              | `str | null`               | Selected variant name (FR-14), or `null`. |
| `record_counts`        | `dict[str, int]`           | Per-split post-pipeline record count. **For aggressive splits, this is the post-augmentation count** (i.e. includes variant multiplication). |
| `created_at`           | `datetime` (UTC ISO 8601)  | Wall-clock timestamp of the run. |
| `elapsed_seconds`      | `float`                    | Total run wall time. |
| `warnings`             | `list[ManifestWarning]`    | Non-fatal issues raised during the run; each has `stage` + `message`. |
| `is_partial`           | `bool`                     | True when materialization stopped early via `--stop-after`. |
| `failed_stage`         | `str | null`               | Stage at which a partial run stopped. |
| `class_balance`        | `str | dict | null`        | Forward-declared class-imbalance hint copied verbatim from `Splits.class_balance` (Story I.s / G10, v0.18.0+). `null` when unset. **DataRefinery does not resample or emit weights** — ModelFoundry honors this at training time. See `manifest.class_balance` shape below. |
| `sinks`                | `dict[str, SinkManifestEntry]` | Per-sink summary of disk-output artifacts captured at materialize time (Story I.d). Empty dict when the recipe declares no `Sinks` section. |
| `sinks_skipped`        | `dict[str, str]`           | Sinks declared on the recipe whose host stage was not reached under a partial `--stage` run (Story I.f.1). Maps sink name → declared stage. Empty on full materializes. |
| `sample`               | `SampleManifestEntry | null` | Forward-declared (Phase J Story J.a, target v0.20.0). Per-split sample-subset record counts + selector echo; `null` when no `SampleData:` is declared. See `manifest.sample` shape below. |
| `label_classes`        | `list[<label-dtype>] | null` | Forward-declared (Phase J Story J.f, target v0.20.0). Canonical class set: distinct label values across all labeled records, sorted ascending. `null` when no labeled records exist (FR-22 fully-unlabeled case). See `manifest.label_classes` shape below. |

### `manifest.sinks` shape

Added in DataRefinery v0.17.0 alongside the `Sinks` recipe section. Each declared sink in the recipe contributes one entry to this map, keyed by the sink's `name`.

| Field                          | Type    | Meaning |
|--------------------------------|---------|---------|
| `stage`                        | `str`   | Pipeline stage whose output was captured (from the closed vocabulary documented in `recipe-authoring.md § Sinks`). |
| `format`                       | `str`   | Serialization format. v1: `"png_per_record"`. |
| `files_written`                | `int`   | Number of files the sink wrote. Matches the record count it visited (after the optional `splits` filter). |
| `bytes_total`                  | `int`   | Total bytes written by this sink. |
| `path_template_resolved_root`  | `str`   | Longest fixed prefix of the recipe's `path_template`, relative to the instance directory. Consumers point at this when locating the sink's output tree without walking the full recipe. |

Sink output lives under `<instance>/<path_template_resolved_root>/...` inside the same atomic temp-then-promote unit as `dataset/`, `fitted_statistics/`, and `report/`. The format vocabulary is extensible (additional formats are planned in Future); consumers SHOULD ignore unknown `format` values rather than fail.

`record_counts["train"]` reflects the **post-augmentation** count for aggressive recipes. ModelFoundry consumers reading the count to estimate training duration should not double-count by applying expansion themselves.

### `manifest.class_balance` shape

Added in DataRefinery v0.18.0 (Story I.s / G10). The field mirrors the recipe's `Splits.class_balance` verbatim and takes one of three forms:

- `null` — no class-imbalance handling declared.
- a bare **string** — a strategy name with no split scoping (legacy form, still accepted).
- a **dict** `{ "strategy": <str>, "applies_to": [<split>, …] }` — a strategy plus the splits it targets.

**Division of responsibility.** This is a *forward-declared training-time hint*. DataRefinery performs **no resampling and no weight emission** — `record_counts` and the materialized `dataset/` are unchanged by `class_balance`. ModelFoundry is responsible for honoring the strategy at training time using framework primitives (e.g. PyTorch `WeightedRandomSampler`, Keras `class_weight=`), scoped to the splits named in `applies_to`.

**Strategy vocabulary (v1, illustrative).** DataRefinery passes `strategy` through verbatim and does **not** enforce a closed set — the validator checks only the dict *shape*. ModelFoundry owns the meaning of each strategy name. Names in use:

- `oversample_minority_to_majority` — at training time, sample minority-class records more frequently so each class is seen at the majority class's effective rate.
- `emit_inverse_frequency_weights` — weight the loss per record by inverse class frequency.

Unknown strategy names SHOULD be treated as a configuration error by ModelFoundry (refuse rather than silently ignore), since the author declared an imbalance intent the consumer cannot honor.

**Per-class counts.** DataRefinery does **not** pre-compute per-class counts in the manifest. To honor `emit_inverse_frequency_weights` (or any other strategy requiring class frequencies), consumers scan the labeled JSONL records themselves and tally. Once `manifest.label_classes` lands (Phase J Story J.f), the class set is canonical; the counts remain consumer-derived.

### `manifest.sample` shape

Forward-declared for DataRefinery Phase J Story J.a (target v0.20.0). The field reflects the declarative subset produced by the SampleData runtime stage; `null` when no `SampleData:` section is declared in the recipe.

| Field           | Type                | Meaning |
|-----------------|---------------------|---------|
| `selector`      | `dict`              | Verbatim echo of `recipe.SampleData.selector` — `kind` (`uniform` \| `per_class`), `n` or `fraction`, optional `splits`. |
| `record_counts` | `dict[str, int]`    | Per-split record count in the sample subset. Keys are the splits the selector targeted; absent splits in the dict were not sampled. |

The sample subset is emitted under `<instance>/sample/<split>.jsonl` with the same per-line shape as `dataset/<split>.jsonl`, and shares the source records' `path`/`image_path` resolution rules. The `dataset/` block is unaffected — consumers wanting the full dataset read `dataset/`; consumers wanting the small fast-iteration subset read `sample/`. **DataRefinery treats `sample/` as informational** (not a stable on-disk contract) until Story J.a ships and this subsection is ratified; pre-J.a, consumers SHOULD NOT bind against it.

### `manifest.label_classes` shape

Forward-declared for DataRefinery Phase J Story J.f (target v0.20.0). The field enumerates the canonical class set used by all labeled records in the materialized instance — a single sorted list that consumers bind against for label→logit-index mapping, confusion-matrix axis ordering, and per-class column naming in predictions output.

- **Computation.** At materialize time, DataRefinery scans every labeled record across every split, takes the distinct union of label values, and sorts ascending (Python `sorted(...)` semantics for the underlying label dtype). Unlabeled records (FR-22) are excluded; if no labeled records exist, the field is `null`.
- **Type.** `list[<label-dtype>] | null`. Dtype matches the values observed in records — typically `str` (class name) but plugin-dependent.
- **Stability and cache identity.** The field lives in the manifest, not the recipe, so it does not perturb canonical recipe bytes and does not affect cache identity. Re-materializing the same recipe over the same inputs produces an identical list.

**Why this lives in the manifest, not in consumer code.** Without a producer-side canonical class list, every consumer scans JSONL and chooses a sort convention independently. Two consumers (or two binding flows in one consumer) can silently disagree on ordering, leading to prediction-column ↔ confusion-matrix-axis ↔ class-weight-vector misalignment that is operationally catastrophic and hard to debug. Centralizing the list in the manifest makes the ordering the producer's commitment.

**Pre-J.f consumer guidance.** Until Story J.f lands, the manifest does NOT carry `label_classes`. Consumers must derive the set themselves with these caveats:

1. Scanning `train.jsonl` alone is fragile — a class present only in `val`/`test` (or in an unlabeled-source variant) will be silently omitted, mismatching the data.
2. The recommended workaround is to scan every labeled split (`train` + `val` + `test`, skipping unlabeled records) and sort ascending — matching the J.f producer-side computation exactly.
3. Two consumers binding the same instance must agree on the same scan + sort convention out-of-band; DR does not yet enforce it.

## Fitted statistics ModelFoundry binds against

Fit-on-train Transformations (v1: `normalize`, `mean_subtract`) persist the statistics they fit on the train split under `fitted_statistics/<op_id>/`, where `<op_id>` is the op's `name` in the recipe's `Transformations` section. This is a **downstream binding surface**: a training consumer reads these statistics to apply the same transform its training data was prepared with, so that train/inference parity holds. It is distinct from the recipe-to-recipe `stats_from_instance` import (§ Recipe-side contract) — that mechanism is for *other DataRefinery recipes*; this section is for *downstream training consumers* such as ModelFoundry.

### On-disk layout

```text
fitted_statistics/
└── <op_id>/
    ├── scalars.json     # one JSON object: { "<name>": <number>, ... }
    └── <name>.parquet   # one parquet file per vector statistic
```

Statistics are always structured (JSON scalars + parquet vectors) — **never opaque pickles**. The `scalars.json` + `<name>.parquet` layout is the stable on-disk contract.

### `normalize` statistics

For the `normalize` op the fitted statistics are **per-channel vectors**:

| Name   | Type   | Shape              | Meaning |
|--------|--------|--------------------|---------|
| `mean` | vector | `[C]` (3 for RGB)  | Per-channel mean fit on the train split. |
| `std`  | vector | `[C]` (3 for RGB)  | Per-channel standard deviation fit on the train split. |

`normalize` **always emits both** `mean` and `std` — the recipe can pin either as params (in which case the pinned value is the persisted value) or omit them (in which case DR computes both from the train split). At apply time, channels with zero variance are guarded by substituting `std = 1.0` to avoid division-by-zero; the persisted `std` is the unmodified fit value.

**Parquet table shape.** Each vector is persisted as a `pyarrow.Table` with a single column named `value` and `C` rows — one row per channel, in axis-0 order. Reading is `table["value"].to_pylist() → [v_0, v_1, …, v_{C-1}]`. There is no second column and no row metadata.

**Channel order.** The `value` column's row order matches the source image's last-axis order at fit time. For the v1 `image_classification` plugin, source images are decoded via Pillow into RGB-mode numpy arrays of shape `(H, W, 3)`, so the channel order is **R, G, B**. Consumers applying `(x - mean) / std` MUST line up the decoded image's channel axis with this order; mismatches silently produce miscalibrated activations rather than an error.

### `mean_subtract` statistics

For consumers that may encounter the related fit-on-train op `mean_subtract`: the `<op_id>/` directory contains **only** a `mean.parquet` vector (no `std.parquet`). The apply behavior is `x - mean`. A consumer that finds `mean_subtract` in the recipe should not look for `std`.

### Read path

Via the in-repo library (the no-mediation case):

```python
from datarefinery import Instance

inst = Instance.load(instance_dir)
mean = inst.fitted_statistics.get_vector("<normalize_op_id>", "mean")  # pyarrow.Table
std  = inst.fitted_statistics.get_vector("<normalize_op_id>", "std")
```

`<normalize_op_id>` is the `name:` of the `normalize` entry in the recipe's `Transformations` section — consumers resolve it by reading the recipe (from `recipe.json`) and matching the op kind.

`get_vector(op_id, name) -> pyarrow.Table` and `get_scalar(op_id, name)` are the supported accessors. A consumer reading the files directly instead MUST honor the on-disk layout above.

**Chained fit-on-train ops.** A recipe may declare multiple fit-on-train ops in its `Transformations:` section (e.g., `mean_subtract` followed by `normalize`). Consumers MUST apply them in the order they appear in the recipe — the "resolve `op_id` by matching op kind" wording above is single-op shorthand only. Reading the full `Transformations:` list from `recipe.json` is the canonical way to recover ordering when multiple fit-on-train ops are present.

### Normalization is applied by the consumer, not baked into image bytes

The materialized dataset images remain **uint8 PNG** on disk (DataRefinery's sink writer and `post_Generation` path both operate on `uint8 H×W×C`). DataRefinery does **not** emit normalized float32 tensors. The downstream training consumer is responsible for:

1. Decoding the uint8 image from `path` / `image_path`.
2. Converting to float and applying `(x - mean) / std` using the **train-fitted** `mean`/`std` read above — for **every** split (train, val, test, and any unlabeled inference partition). Re-fitting normalization on a non-train split is a correctness bug, not an optimization.
3. **Replicating DataRefinery's zero-variance guard exactly**: for any channel `c` where `std[c] == 0` (exact equality, not a tolerance), substitute `1.0` for the divisor in that channel. DataRefinery's `apply` performs this guard internally while persisting the unmodified fit value, so a consumer that divides by the raw `std` will diverge from DR's semantics on zero-variance channels and produce `inf`/`nan` where DR produces a finite result. The substitution must use `==` against `0.0`, not a near-zero tolerance — using a tolerance would silently disagree with DR for tiny-but-nonzero channels.
4. For recipes using `mean_subtract` instead of `normalize`, applying `x - mean` only.

This keeps the contract honest: **DataRefinery owns the statistics; the consumer owns the application.** The alternative — DataRefinery emitting normalized float32 tensors as a new on-disk format — is **not supported in v1**; the sink writer ships only `png_per_record`/uint8. If that ever changes it will be a documented new on-disk format under a `schema_version` bump.

## Consumer-applied transformations vs. baked transformations

The previous section drew the consumer-application boundary for normalization. This section generalizes that boundary across DataRefinery's full transform vocabulary: which transformations are **baked** into the materialized image bytes (consumer reads the transformed pixels) vs. which the consumer must **re-apply** at training/inference time.

### Baked (consumer reads transformed pixels)

- **Aggressive-mode `Augmentations`.** The realized variant's pixels are written to `<split>/images/<record_id>.png` and the JSONL record carries `image_path:` pointing at the sidecar. Consumers MUST resolve variant pixels via `image_path`. This is the well-supported path-rewrite case in v1.
- **`Sinks` declarations.** Sinks write their captured stage output under `<instance>/<path_template_resolved_root>/...` (see `manifest.sinks`). **Pre-J.g caveat:** the JSONL records' `path` field is NOT yet rewritten to the sink output; consumers wanting sink-captured pixels must consult `manifest.sinks` separately.

### Consumer-applied (consumer re-applies the transform from persisted stats)

- **`normalize` / `mean_subtract`.** Fitted statistics are persisted; pixel bytes on disk remain uint8 PNG. Application is the consumer's job — see § "Normalization is applied by the consumer, not baked into image bytes" above. This is the intentional, stable case in v1.

### Unresolved boundary — lazy-mode geometry / pixel-altering Transformations

In DataRefinery v0.19.0 and earlier, the `path` field is set ONCE at input loading and is NEVER rewritten by Transformations or Sinks. A non-aggressive recipe declaring a pixel-altering Transformation op (e.g., `resize`) produces JSONL where:

1. The in-memory `image` numpy array IS transformed during the pipeline.
2. The `image` field IS dropped at serialization (see § JSONL records).
3. The `path` field still points at the **untransformed source image**.

A consumer reading pixels from `path` therefore decodes pre-transform geometry, silently diverging from the recipe's declared materialization. This is a real architectural gap, scoped as **Phase J Story J.g** (target v0.20.0). The recommended resolution shape:

- DR rewrites `path` to point at the transformed pixel form at materialize time. The mechanism: require a sink for lazy-mode recipes containing pixel-altering Transformations, and rewrite `path` to the sink's per-record output.
- An interim validator check refuses lazy-mode recipes that contain any pixel-altering Transformation op without a corresponding sink, so the silent-divergence case cannot be authored in the first place.

**Pre-J.g consumer guidance.**

- For recipes whose `Transformations:` contains only fit-on-train stats ops (`normalize`, `mean_subtract`), the contract holds: uint8 PNG on disk, consumer applies stats from `fitted_statistics/`.
- For recipes whose `Transformations:` contains `resize` or any other pixel-altering op, consumers MUST either (a) require the recipe to use aggressive `Augmentations` with sidecar PNGs (variant pixels via `image_path`), (b) require a `Sinks` declaration and resolve sink-output paths via `manifest.sinks`, or (c) refuse to consume.
- For the CIFAR-10 reference flow (no geometry transforms), the contract holds end-to-end without intervention. This is what makes the gap easy to overlook.

## Report subsections

The `report/` directory holds the human-readable summary:

- **`report/report.md`** — markdown summary of the recipe, splits, operations applied (filters, generation, transformations, featurizations, augmentations, visualizations), fitted statistics, and warnings. Each augmentation op renders mode-aware:
  `op_name (\`op_kind\`, materialization=lazy)` or
  `op_name (\`op_kind\`, materialization=aggressive, expansion=N)`.
- **`report/drift.json`** — drift-relevant subsection of the report, emitted as structured JSON. **Pre-production its schema is unstable**; ModelFoundry consumers should treat it as informational until v1.0. See FR-15 in `features.md` for the current shape.
- **`report/visualizations/<viz_name>.png`** — persisted reporting-mode visualization images (FR-13). Stage-aware dispatch (Story I.v / G7) is **internal** to the materialize-time pipeline: a viz op's `stage:` declaration selects which per-stage record snapshot the renderer reads, but the on-disk surface is unchanged — every reporting-mode viz still produces one PNG (named `<viz_name>.png` or `<viz_name>_<extra>.png` for multi-output ops) in this directory, and `report.md` does not gain per-stage subsections in v1. ModelFoundry consumers binding against the report surface see the same flat layout regardless of how many pipeline stages a recipe spans. Per-stage report subsections are tracked in [`stories.md § Future`](../stories.md).

## Cache-identity contract

The cache key (instance directory path) is `SHA-256(canonical_recipe_bytes) ⊕ SHA-256(raw_input_bytes) ⊕ seed`, truncated to 16 hex chars per component for the path (`<recipe-hash16>/<input-hash16>/<seed>`). The **full** digests live in `manifest.json` for audit.

The canonical bytes are produced by `pydantic_model.model_dump(mode="json")` followed by `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. **Every pydantic field default participates in canonical bytes** — adding a field with a default value, changing a default value, or reordering a field all perturb the canonical hash for recipes that overlap the change.

Bumping `schema_version` (in `src/datarefinery/recipe/loader.py`'s `SUPPORTED_SCHEMA_VERSIONS`) is the deliberate invalidation lever. Non-bumped DataRefinery releases preserve cache identity. Releases that DO invalidate carry a prominent CHANGELOG callout (see v0.15.0 for the H.p–H.r.2 example: adding `AugmentationOp.materialization` and `expansion` defaults perturbed canonical bytes for any recipe with `Augmentations`).

**Schema v1 → v2 (Phase I bundle 4, v0.19.0).** Three reshape stories (I.x.1 / G15 Filters, I.x.2 / G12 Generation, I.x.3 / G16a assertion naming) ship together as a `schema_version` bump. v1 recipes are auto-migrated by the loader (`recipe.migrations.v1_to_v2`); the cached `recipe.json` always reflects the v2 canonical shape. ModelFoundry consumers that bind against recipe-model fields directly need to track the v2 names — most notably:

- **`FilterOp`** (Story I.x.1 / G15): v1 nested `predicate: {op, ...rest, seed?}`; v2 lifts to top-level `{op, params, seed?}` (matches every other section). The migration is one-way; ModelFoundry should bind against the v2 shape and rely on the loader to migrate v1 recipes on read.
- **`GenerationOp`** (Story I.x.2 / G12): v1 left `op` implicit (the recipe's `name` doubled as the op lookup key), called the splits field `applies_at`, and required `output_schema` to be an explicit `dict[str, FieldSpec]`. v2 has explicit `op: str` at top level, renames `applies_at` → `splits`, and widens `output_schema` to accept the literal `"matches_input"` shorthand (resolved at materialize time to `Output.record_schema` plus declared tag fields). The migration handles all three reshapes and the documented v1 workaround pattern of stashing `op:` inside `params:`; ModelFoundry should bind against the v2 names and treat `output_schema: "matches_input"` as a possible value.
- **Assertion `kind` naming** (Story I.x.3 / G16a): three v1 bare-verb names rename to predicate-sentence form — `dtype` → `dtype_equals`, `range` → `value_range`, `record_count` → `record_count_in_range`. The mapping applies to both `InputContracts[*].assertion` and `OutputExpectations[*].assertion`. `required_field` and `distributional` are unchanged. v1 names are removed (not aliased) post-migration; ModelFoundry consumers reading the cached `recipe.json` will see the v2 names exclusively. The seven additional v2 kinds added in Story I.o (`split_record_counts`, `per_class_count_per_split`, `count_by_field`, `count_by_fields`, `shape_equals`, `value_in_set`, `per_class_count_equals`) were already predicate-sentence and are unaffected.

## Schema-version coordination policy

As of the current DataRefinery release the supported set is **`{1, 2}`** with **`LATEST_SCHEMA_VERSION = 2`** (importable as `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS` / `LATEST_SCHEMA_VERSION`). DataRefinery's loader applies the registered `(1, 2)` migration chain before validation, so a consumer using `Instance.load` always sees the **v2-shaped** recipe regardless of the on-disk recipe's authored version. A consumer that still pins its tracked set to `{1}` MUST update to include `2` before binding v2 instances, or it will hard-error per the rule below.

ModelFoundry SHOULD track DataRefinery's current `SUPPORTED_SCHEMA_VERSIONS` set. When consuming a recipe whose `schema_version` is **outside** ModelFoundry's known support range:

- If the recipe's `schema_version` is **higher** than anything ModelFoundry knows about → **hard error** on ModelFoundry's side, with an error message naming the recipe's version and ModelFoundry's highest-supported version. Do not attempt to coerce, downgrade, or guess.
- If the recipe's `schema_version` is **lower** than ModelFoundry's lowest known → ModelFoundry's choice (typically a forward-migration in DataRefinery's `recipe.loader.migrations` already handled the shape; ModelFoundry can rely on the loader-emitted shape).

ModelFoundry adopting a newer DataRefinery `schema_version` requires updating ModelFoundry's tracked set and re-running its own contract tests against the new manifest/recipe shapes.

## Forward-compatibility expectations

- **Unknown ops in `Augmentations`** (post-prod): ModelFoundry SHOULD detect any `AugmentationOp.op` it does not recognize and fail with a clear `"unknown augmentation op '<name>'; supported: [...]"` error. Silent fallback to a no-op augmentation is forbidden.
- **Unknown fields in `AugmentationOp`** (post-prod): ModelFoundry SHOULD reject recipes with unrecognized AugmentationOp fields. DataRefinery enforces `extra="forbid"` on its own side; ModelFoundry should mirror.
- **Unknown manifest keys** (pre-prod): ModelFoundry consumers SHOULD log-and-continue rather than hard-fail, to allow DataRefinery to add informational fields without breaking adopters mid-stream. Post-prod this softens further: unknown keys are stable forward-compat.

## Failure modes ModelFoundry SHOULD detect

A trained-but-broken handoff is worse than a refusal. ModelFoundry's adapter should detect at least these conditions before training begins:

- **Stale fitted statistics**: `manifest.recipe_hash` does not match the on-disk recipe's canonical hash → the instance was rendered against an older recipe shape; do not train on it. (`drift.json`'s `recipe_hash` field aligns with `manifest.recipe_hash`; mismatch is ipso facto a stale instance.)
- **Missing required fields**: a manifest absent any of `plugin`, `plugin_version`, `recipe_hash`, `record_counts`, or `seed` is malformed; refuse to consume.
- **Missing required fitted statistics**: a consumer that must apply a fit-on-train transform (e.g., `normalize`) but finds no `fitted_statistics/<op_id>/` for that op — or finds the directory but is missing a required vector such as `mean` or `std` — should refuse to train rather than silently skip normalization, naming the missing op_id / statistic in the error.
- **Schema-version mismatch**: see § Schema-version coordination policy.
- **Aggressive variant sidecar missing**: a JSONL line declares `image_path: "<rel>"` but the sidecar at `<rel>` doesn't exist on disk → instance is corrupt; refuse to consume.
- **Plugin missing**: `manifest.plugin` is not an installed plugin in ModelFoundry's environment → cannot resolve the plugin's runtime schema; refuse to consume.

## Versioning and adoption

- DataRefinery ships **forward-declared contracts** at release time: each release's CHANGELOG enumerates contract changes (recipe shape, manifest, report, on-disk layout). ModelFoundry tracks but does not block DataRefinery releases.
- ModelFoundry adopts **on its own schedule**. A DataRefinery consumer using the in-repo `datarefinery` library directly is the no-mediation case; ModelFoundry sits one degree away and benefits from forward-declaration.
- **Pre-production (v < 1.0)**: this document may change without a schema-version bump if no recipe/manifest/report bytes change. Documenting an existing surface in this file is not a contract change.
- **Post-production (v >= 1.0)**: this document becomes a stability contract. Changes to any contract surface go through the schema-version-bump + migration ceremony.

Cross-references:

- `docs/specs/features.md` — feature requirements (FR-11 augmentations, FR-15 reporting).
- `docs/specs/tech-spec.md` — full recipe model + manifest + instance directory tree.
- `docs/specs/project-essentials.md` — cache-identity / determinism / cross-repo coordination rules.
