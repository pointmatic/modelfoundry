# DataRefinery ↔ ModelFoundry dependency contract

> **Status:** authoritative cross-repo contract (Story H.s, v0.15.0).
> Pre-production: this document may evolve as ModelFoundry adoption
> surfaces gaps. Post-production: it becomes a stability contract —
> changes follow the schema-version-bump + migration ceremony in
> `docs/specs/project-essentials.md` § "Cache identity is the
> reproducibility contract."

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

A materialized instance lives under `<cache-root>/instances/<recipe-hash16>/<input-hash16>/<seed>/`. Within that directory, the dataset block has the following shape:

```text
dataset/
├── train.jsonl               # one record per line
├── val.jsonl
├── test.jsonl
└── <split>/
    └── images/
        └── <record_id>.png   # FR-11 aggressive-mode variants only (Story H.r.2)
```

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
| `schema_version`       | `int`                      | Manifest schema version; separate from recipe `schema_version`. |
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
| `sinks`                | `dict[str, SinkManifestEntry]` | Per-sink summary of disk-output artifacts captured at materialize time (Story I.d). Empty dict when the recipe declares no `Sinks` section. |
| `sinks_skipped`        | `dict[str, str]`           | Sinks declared on the recipe whose host stage was not reached under a partial `--stage` run (Story I.f.1). Maps sink name → declared stage. Empty on full materializes. |

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

## Report subsections

The `report/` directory holds the human-readable summary:

- **`report/report.md`** — markdown summary of the recipe, splits, operations applied (filters, generation, transformations, featurizations, augmentations, visualizations), fitted statistics, and warnings. Each augmentation op renders mode-aware:
  `op_name (\`op_kind\`, materialization=lazy)` or
  `op_name (\`op_kind\`, materialization=aggressive, expansion=N)`.
- **`report/drift.json`** — drift-relevant subsection of the report, emitted as structured JSON. **Pre-production its schema is unstable**; ModelFoundry consumers should treat it as informational until v1.0. See FR-15 in `features.md` for the current shape.
- **`report/visualizations/<viz_name>.png`** — persisted reporting-mode visualization images (FR-13).

## Cache-identity contract

The cache key (instance directory path) is `SHA-256(canonical_recipe_bytes) ⊕ SHA-256(raw_input_bytes) ⊕ seed`, truncated to 16 hex chars per component for the path (`<recipe-hash16>/<input-hash16>/<seed>`). The **full** digests live in `manifest.json` for audit.

The canonical bytes are produced by `pydantic_model.model_dump(mode="json")` followed by `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. **Every pydantic field default participates in canonical bytes** — adding a field with a default value, changing a default value, or reordering a field all perturb the canonical hash for recipes that overlap the change.

Bumping `schema_version` (in `src/datarefinery/recipe/loader.py`'s `SUPPORTED_SCHEMA_VERSIONS`) is the deliberate invalidation lever. Non-bumped DataRefinery releases preserve cache identity. Releases that DO invalidate carry a prominent CHANGELOG callout (see v0.15.0 for the H.p–H.r.2 example: adding `AugmentationOp.materialization` and `expansion` defaults perturbed canonical bytes for any recipe with `Augmentations`).

## Schema-version coordination policy

ModelFoundry SHOULD track DataRefinery's current `SUPPORTED_SCHEMA_VERSIONS` set (importable as `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS`). When consuming a recipe whose `schema_version` is **outside** ModelFoundry's known support range:

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
