# DataRefinery ↔ ModelFoundry dependency contract

## Revision Log

If you reference document paths, since there are two repos involved, prefix the revision log entry or document path with `DR:` or `MF:`, to indicate the log author or which repo the path is relative to. Example `DR:docs/specs/project-essentials.md`

* DR: signal DataRefinery-driven edits or document path relative to DataRefinery repo. 
* MF: signal ModelFoundry-driven edits or document path relative to ModelFoundry repo.

> **Status:** authoritative cross-repo contract (Story H.s, v0.15.0). Pre-production: this document may evolve as ModelFoundry adoption surfaces gaps. Post-production: it becomes a stability contract — changes follow the schema-version-bump + migration ceremony in `DR:docs/specs/project-essentials.md` § "Cache identity is the reproducibility contract."
>
> **DR: counter-proposal 2026-06-11.** The 2026-06-11 ModelFoundry-side revision was reviewed against current DataRefinery source. **Accepted:** the new § "Fitted statistics ModelFoundry binds against", the instance-level on-disk tree, the explicit `LATEST_SCHEMA_VERSION = 2` coordination note, and the "missing required fitted statistics" failure mode. **Corrected:** the persisted recipe file is `recipe.json` (not `recipe.yaml`); the dropped `manifest.class_balance` row + shape subsection are restored (DR still emits the field, v0.18.0+); the schema v1→v2 migration detail subsection is restored under § Cache-identity contract; the stage-aware viz dispatch clarification is restored under § Report subsections; the `normalize` "std may be absent" claim is corrected — DR's `normalize` always emits both `mean` and `std`, mean-only behavior is the separate `mean_subtract` op (different `op_id` directory, no `std.parquet`). **Forward-declared by DR:** the `manifest.sample` row + shape subsection and the instance-tree `sample/` block, targeting Phase J Story J.a (v0.20.0). Full coordination on Phase J surfaces happens when J.a lands.
>
> **MF: Round 2 additions 2026-06-11.** ModelFoundry clarifying questions surfaced three further contract gaps. **Pinned** in this round: the `normalize` parquet internal shape and channel ordering (single `value` column, `C` rows, RGB axis order for the v1 image_classification plugin); the **zero-variance std guard** as an explicit consumer obligation (exact `std == 0` substitution to `1.0`, no tolerance) so consumer-applied normalization matches DR's apply semantics on every channel; the `manifest.class_balance` per-class-counts and chained fit-on-train ordering notes; and the fact that the original authored YAML is **not** persisted in the instance (only the canonical `recipe.json` is). **Forward-declared** in this round: `manifest.label_classes` (Phase J Story J.f, target v0.20.0) closes the class-set enumeration gap so consumers stop deriving sorted-from-train independently. **New § Consumer-applied transformations vs. baked transformations** (Phase J Story J.g, target v0.20.0) draws the apply-boundary explicitly and identifies the lazy-mode geometry-transform gap (`path` points at source while `Transformations` are not reflected in JSONL pixels).
>
> **DR: J.g ratified 2026-06-12 (v0.20.0).** The lazy-mode geometry-transform gap above is now **closed**, not forward-declared. The closed set of pixel-altering Transformation ops (today: `resize`) is enforced by validator **check 26**: a recipe with a pixel-altering Transformation on any lazily-serialized split MUST declare a qualifying image sink (`format: png_per_record`, `field: image`, a post-Transformations stage) covering those splits, and DataRefinery rewrites each affected record's JSONL `path` to that sink's per-record output (instance-relative). The § "Consumer-applied transformations vs. baked transformations" subsection below is updated accordingly. Additive — no `schema_version` bump (canonical recipe bytes unchanged); the on-disk `path` value changes for affected recipes → pre-prod re-materialize event.
>
> **DR: Round 3 additions 2026-06-12 (Story J.k).** Absorbs four documentation-only clarifications surfaced by the [J.d MF integration spike](../phase-j-mf-integration-friction.md) (no code or shape change): **F8** — the consumer-side runtime deps a downstream tool needs beyond stdlib (`numpy` / `Pillow` / `pyarrow`), added to § Overview; **F6** — every top-level recipe section persists in `recipe.json` as its model default whether declared or not, added to § Recipe-side contract; **F3** — the non-aggressive `path` field is host-bound, with the two portability workarounds (`Sinks` rewrite / ship the source), added to § Source-resolution path; **F5** — `recipe.schema_version` (`2`) and `manifest.schema_version` (`1`) are independent counters, disambiguated in § Schema-version coordination policy. Each absorption site carries an inline "*(Fn, pinned in Round 3)*" provenance marker. *(F4 — the disk-loader vs. library-records Featurization asymmetry — lands in the NbF spec, which owns the library-records path.)*
>
> **DR: 2026-06-13 (Story J.l).** Added § "Resolving a materialized instance": names `datarefinery.resolve_instance(...)` / `DataRefinery.status()` as the **one** blessed way to locate an instance, documents the `StatusReport` shape + hit/miss/corrupt contract, and **forbids** consumers recomputing the cache key / instance path themselves (a hand-rolled key silently breaks after any canonical-bytes change). Closes the gap that led a consumer to reimplement the instance-ID math. Additive library facade (`resolve_instance` composes `status()`); no recipe/manifest/on-disk shape change, no `schema_version` bump.
>
> **DR: Phase J audio-seam additions 2026-06-22 (Stories J.n.8, J.q, J.s, J.t, J.u).** The `audio_classification` cross-repo surfaces were pinned across five same-day commits; each additive (pre-prod doc-evolution, no `schema_version` bump). **J.n.8** — § Segment-scoped recipe shape + per-segment versioning (J.n.7): recipe model partitioned into independently-versioned identity segments (`core` / `plugin:<name>` / `overlays` / `extensions`). **J.q** — new § Audio window records: the `window` Generation op (`replace_input_records: true`) replaces each clip with fixed-length window records carrying `source_record_id` (parent clip) + `window_index`; `__w####` vs FR-11 `__v###` disambiguation. **J.s** — in-pipeline `feature` (log-mel spectrogram) field, `(n_mels, n_frames)` librosa-native orientation, NOT serialized to JSONL. **J.t** — `audio_normalize` fit-on-train Featurization + new § `audio_normalize` statistics: per-mel-bin `mean`/`std` under `fitted_statistics/<op_id>/`, same parquet shape / zero-variance guard / `stats_from_instance` parity as image `normalize`, axis = mel (axis 0). **J.u** — § Aggregation contract (R7): `source_record_id` is DR's clip↔window grouping key (DR owns the key, consumer owns the aggregation math; no DR aggregation op) + dangling-grouping-key failure mode.
>
> **DR: 2026-06-23 — audio feature-array persistence seam (forward-declared).** Captures the shared agreement from the paired consumer-gap solutions (DR [`consumer-gap-solutions.md`](../consumer-gap-solutions.md) Gap 3 / MF [`modelfoundry/consumer-gap-solutions.md`](consumer-gap-solutions.md) Gap 3). New **forward-declared** § "Audio feature-array persistence — `npy_per_record` + `feature_path`": DR will add an additive `npy_per_record` sink that persists the raw `mel` float array per record at `features/<split>/<record_id>.npy` (`(n_mels, n_frames)` on disk → consumer tensor `(1|C, n_mels, n_frames)`) and rewrites a per-record `feature_path`; the consumer applies persisted per-mel-bin `audio_normalize` stats and reads the array **read-only**. The uint8 spectrogram-as-image (PNG) route is **rejected** (lossy, not round-trippable). Additive — **no `schema_version` bump** (this refines the older "float on-disk format ⇒ schema bump" note under § "Normalization is applied by the consumer"). Pending the paired plan (DR `plan_phase` sink + MF `plan_features` loader); re-ratified to shipped when both land. *(Reminder, the unrelated MF "fixed pretrained-encoder stats" question is already answered by the existing § `normalize` statistics: pinned `mean`/`std` params are persisted as-is; absent ⇒ fit-from-train — no change needed.)* **MF review round (same day):** the § now carries pinned answers Q1–Q6. The two load-bearing resolutions — **Q1** `feature_path` is **instance-root-relative** (`<instance>/<feature_path>`, the J.g sink-`path` bucket, *not* `image_path`'s `dataset/`-relative anchor) and **Q2** the sink persists the **raw `mel`** (pre-normalize) with the consumer applying `audio_normalize` at load (no double-normalize) — plus Q3 dtype (`float32` array / `float64` stats), Q4 rank (always 2-D mono in v1), Q5 nested-POSIX `feature_path`, Q6 `feature_path` authoritative over a stray `path`.

> **DR: v0.25.0 ratified — forward-declared surfaces now shipped (reconciled 2026-06-23, verified against installed DR 0.25.0).** Several surfaces previously carried as forward-declared are **shipped** and re-ratified here; each was confirmed against the installed package, not just relabeled: (1) **Audio feature-array persistence** — the `npy_per_record` sink + `feature_path` rewrite (DR Stories K.c/K.d, v0.24.0–v0.25.0; `SinkOp.format` is now `Literal['png_per_record','npy_per_record']`), with MF's consuming half landed in Subphase I-1 (Stories I.m/I.n) and **verified end-to-end against a real DR materialize** in Story I.m.1; (2) the **`SampleData` runtime** + `sample/` on-disk block + `manifest.sample` (Phase J Story J.a; `Recipe.SampleData` + `Manifest.sample`/`SampleManifestEntry` present); (3) **`manifest.label_classes`** (Phase J Story J.f; present); (4) the **`audio_classification` plugin** + `AudioSource` (present). **Still deferred:** the `parquet` sink format (only `npy_per_record` shipped); MF's *consumption* of `class_balance` (DR emits the field since v0.18.0; MF honors it at training time — not yet built). The `join_stable` byte-format divergence (project-essentials.md governance) is unchanged in 0.25.0 (DR still uses `_JOIN_SEP=\x1f`) and remains a cross-repo coordination item, not an in-tree fix.

## Overview

This document is the **cross-repo contract surface** between DataRefinery (data-pipeline producer) and ModelFoundry (downstream training consumer), and is the authoritative reference for any downstream tool that binds against a materialized DataRefinery instance.

It enumerates exactly what DataRefinery emits — recipe-side fields, on-disk dataset layout, manifest keys, report subsections — that external consumers depend on, and the rules by which those surfaces may change. The intent is to let DataRefinery and ModelFoundry evolve on independent schedules: DataRefinery ships forward-declared contracts at release time; ModelFoundry adopts on its own schedule without requiring DataRefinery to wait.

Out of scope here: ModelFoundry's training-time APIs (those live in ModelFoundry's repo) and DataRefinery's internal implementation details (those live in `tech-spec.md` and `features.md`).

**Consumer-side runtime dependencies.** Reading a materialized instance beyond pure stdlib requires `numpy` (image bytes and record arrays), `Pillow` (PNG decode for aggressive-variant sidecars and any image-bytes reads), and `pyarrow` (parquet decode for `fitted_statistics/`). A consumer that only reads `manifest.json` / `recipe.json` / `report/*.json` (no pixels, no fitted stats) needs none of these. *(F8, pinned in Round 3 — see header.)*

## Recipe-side contract

A recipe is a YAML document validated by `Recipe.model_validate(...)` in `src/datarefinery/recipe/models.py`. The full schema is documented in `tech-spec.md` § Data Models; this section calls out the augmentation surface (Story H.p–H.r.2) that ModelFoundry consumes directly.

**Every top-level recipe section persists in `recipe.json`, declared or not.** The persisted `recipe.json` is the canonical `model_dump(mode="json")` of the full `Recipe` model, so **all** top-level sections are present whether or not the author wrote them — an undeclared section materializes as its model default: `[]` for list sections (`InputContracts`, `Filters`, `Generation`, `Transformations`, `Augmentations`, `Featurizations`, `OutputExpectations`, `Visualizations`, `Sinks`), `null` for optional object sections (`SampleData`), and the section's own default object where one exists. Consumers SHOULD treat an empty-list / `null` section as "not declared" rather than inferring a special meaning. *(F6, pinned in Round 3 — see header.)*

### Segment-scoped recipe shape (Phase J Recipe Architecture bundle, v0.22.0)

The recipe stays **flat on disk** — the v0.22.0 bundle did **not** reshape `recipe.json` (Option 1: segmentation is an *internal* partition that drives hashing, per-segment versioning, and validation dispatch, not author-facing nesting). Consumers binding to recipe-model fields need no structural change. But the bundle binds every field to exactly one of **four identity segments**, and that mapping is now a cross-repo contract surface (it governs which changes invalidate which caches — see § Cache-identity contract):

| Segment | Fields | Notes |
|---|---|---|
| `core` | `schema_version`, `plugin`, `seed`, `Input`, `Output`, `Labels`, `SampleData`, `InputContracts`, `Splits`, `OutputExpectations` | The structural sections + identity/version stamps. |
| `plugin` | `Filters`, `Generation`, `Transformations`, `Augmentations`, `Featurizations`, `Visualizations`, `Sinks` | The op-list sections whose op vocabulary the plugin defines. Versioned per plugin family (`plugin:image` / `plugin:audio`) so an audio-surface change never moves an image recipe's identity (Finding A). |
| `overlays` | `overlays` | Overlay *definitions*; always stripped to `{}` before hashing, so they never enter identity (see § Cache-identity contract). |
| `extensions` | `extensions` | The J.n.6 experimental-parameter namespace (below). |

**`extensions` namespace (Story J.n.6).** A new optional top-level `extensions: {<namespace>: {<key>: <value>}}` block carries experimental, plugin-consumed parameters; pydantic's `extra="forbid"` is relaxed *only inside* a namespace. It enters cache identity only when non-empty (an empty/absent block hashes to the empty-segment marker — additive, no invalidation). Plugins declare which keys they consume; DataRefinery's validator refuses any undeclared namespace/key. Extensions are **declarative parameters only** — they do not activate code. ModelFoundry consumers generally ignore `extensions` unless a shared plugin defines keys MF also reads.

**No implicit defaults (Story J.n.4).** Op `ParameterSpec`s no longer carry code-supplied defaults: a parameter is either `required` (the author/scaffolder writes a value) or a **mode-selecting optional** (absence is itself the documented behavior, e.g. `normalize` with no `mean`/`std` ⇒ fit-from-train). The canonical `recipe.json` therefore contains *exactly what the author wrote* for op params — there is no longer a "code-supplied default silently in the bytes" layer for op parameters. Recommended starting values live in the scaffolder (`Plugin.recommended_params`), emitted into recipe text. (Structural section defaults — empty-list sections, `SampleData: null` — are unchanged; the no-defaults rule is about op `params`.)

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

**Incompatibility: dtype-altering Transformations + aggressive Augmentations (validator check 27, Story J.i).** The aggressive realizer reconstructs each variant image via `PIL.Image.fromarray`, which requires **uint8**. A *dtype-altering* Transformation op — one that leaves the image in a non-uint8 dtype (today `normalize` / `mean_subtract`, which emit float64; surfaced via `OperationSpec.dtype_altering`) — therefore cannot share a split with an aggressive Augmentation; the combination is **refused at validate time** (check 27). This is independent of the pixel-altering classification (check 26): `resize` is pixel-altering but uint8-preserving, so `resize` + aggressive is **allowed**. Authors who need both float normalization and aggressive augmentation should either keep normalization consumer-side (the recommended path — see § "Normalization is applied by the consumer") or use lazy-mode augmentation.

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
├── recipe.json                  # canonical v3-shape recipe (loader-migrated from v1/v2)
├── dataset/
│   ├── train.jsonl              # one record per line
│   ├── val.jsonl
│   ├── test.jsonl
│   └── <split>/
│       └── images/
│           └── <record_id>.png  # FR-11 aggressive-mode variants only (Story H.r.2)
├── fitted_statistics/           # fit-on-train stats; see § Fitted statistics ModelFoundry binds against
│   └── <op_id>/
├── sample/                      # DataRefinery SampleData runtime subset (shipped, DR Phase J Story J.a)
│   └── <split>.jsonl
└── report/                      # see § Report subsections
```

`recipe.json` is the canonical-form recipe — the full `model_dump` of the model whose segments are hashed for the cache key (see § Cache-identity contract). DataRefinery's loader applies any v1→v2→v3 migration before persisting, so consumers reading `recipe.json` always see the latest (v3) shape regardless of the recipe's authored version. The v3 shape is field-identical to v2 (the v2→v3 bootstrap stamps the version only); v3's substantive change is the segmented `recipe_hash`.

**The original authored YAML is NOT persisted in the instance.** The instance holds only the canonical JSON form (for reproducibility and cache identity). The authored YAML is the user's source artifact and lives in the user's repo, referenced by path. Consumers that need to display "what the user wrote" must retain the source path separately — pretty-printing `recipe.json` gives "what was materialized," which is post-migration and key-sorted and may diverge from the YAML the user actually authored.

The `sample/` block is **shipped** (DataRefinery's `SampleData` runtime, Phase J Story J.a — `Recipe.SampleData` present in DR 0.25.0). Recipes that omit `SampleData:` do not produce a `sample/` directory. The shape subsection (§ `manifest.sample`) is the binding contract.

### JSONL records

Each JSONL line is a single record dict, serialized with sorted keys for byte-stability. Non-JSON-native fields (numpy arrays, bytes, custom objects) are dropped at serialization.

**Common fields** present on every record:

- `record_id: str` — stable identifier for the record.
- `label`: any JSON-native type; absent on unlabeled-partition records (FR-22 / unlabeled support).

**Source-resolution path** (non-aggressive records):

- `path: str` — the source-image file path. Image bytes resolve via the source filesystem. **The `image` numpy field is dropped at serialization** — downstream consumers read pixels from `path`.

**Host portability.** For non-aggressive records with no pixel-altering Transformation, `path` is the **loader-stamped source path** (typically host-absolute, e.g. `/data/imagefolder/c0/img.png`) — it is **host-bound** and does NOT resolve on a different machine unless the source ImageFolder is present at the same path. Consumers operating across hosts (e.g. materialize on a workstation, train on a cluster) SHOULD either:

- **(a)** declare a `Sinks` block (`format: png_per_record`, `field: image`, a post-transform stage) so per-record images land **under the instance directory** and `path` is rewritten to an instance-relative location. This is exactly the Story J.g `path`-rewrite mechanism — *required* (validator check 26) for the pixel-altering subset, and *available* as a portability tool for the general case; or
- **(b)** ship the source ImageFolder alongside the instance and reconstruct the original `path` prefix on the consuming host.

Aggressive variants are already instance-relative via `image_path` (below) and need neither workaround. *(F3, pinned in Round 3 — see header. The pixel-altering subset is covered by § "Lazy-mode geometry / pixel-altering Transformations".)*

**Aggressive-mode variants** (Story H.r.2):

- `source_record_id: str` — record_id of the input that produced this variant.
- `variant_index: int` — zero-based index within the variant pack; range `[0, expansion)`.
- `image_path: str` — relative path under `dataset/` (e.g. `"train/images/img_001__v002.png"`) pointing at the sidecar PNG. ModelFoundry consumers MUST resolve variant pixels via `image_path`; the source `path` field, if present on a variant, is not authoritative. **`image_path` is exactly `"<split>/images/<record_id>.png"`** — when `record_id` contains `/` separators (the ImageFolder loader stamps `record_id` as `<source>/<class>/<file>`), `image_path` carries those separators verbatim and the sidecar lives in a correspondingly **nested** subtree under `<split>/images/` (e.g. `"train/images/imgs/c0/img_0001.png__v000.png"`). Consumers MUST join `image_path` onto the instance directory as a relative POSIX path rather than assuming a single flat `images/` directory (Story J.h).

**Per-record-seed stamps** (Story I.e):

- `<GenerationOp.name>_seed: int` — present on every record produced by a per-record-stochastic Generation op (today: `imagecorruptions_apply`). 8-byte unsigned integer, derived as `pipeline.workers.per_record_seed(GenerationOp.seed, input_record)`.
- `<AugmentationOp.name>_seed: int` — present on every variant produced by an `aggressive`-materialization Augmentation. 8-byte unsigned integer, derived as `pipeline.workers.per_record_variant_seed(global_seed, input_record, variant_index, op_id=AugmentationOp.op)`.

These seeds are the value used by the op's RNG. Consumers reconstructing stage output post-hoc (e.g., the future `datarefinery export` verb) replay the op with the recorded seed to reproduce the bytes the pipeline saw at that stage. Lazy-mode augmentations and ops whose stochasticity is op-level (`duplicate_minority_class`) do not stamp.

### Record-multiplication shape

A recipe declaring `expansion=N` aggressive op against the train split produces `len(train_records_pre_aug) * N` JSONL lines and exactly the same number of sidecar PNGs. Two aggressive ops chained compose multiplicatively (`expansion=a` then `expansion=b` → `N × a × b` records).

Variant `record_id`s are derived as `f"{source_record_id}__v{variant_index:03d}"` — unique, zero-padded for lex-order = numeric-order under standard sort. The `source_record_id` is the loader-stamped id verbatim, so an ImageFolder source contributes `/`-separated ids (`<source>/<class>/<file>`) and the variant id inherits them (e.g. `imgs/c0/img_0001.png__v000`). DataRefinery does **not** sanitize `record_id`; the sidecar path-writer creates the nested directories the separators imply (Story J.h).

#### Audio window records (Story J.q)

`source_record_id` is now used by **two** record-multiplying mechanisms — note the distinction when binding:

| Field | FR-11 aggressive image variants | Audio windowing (`window` Generation op) |
|---|---|---|
| `record_id` | `f"{source_record_id}__v{variant_index:03d}"` | `f"{source_record_id}__w{window_index:04d}"` |
| index field | `variant_index: int` (`[0, expansion)`) | `window_index: int` (`[0, n_windows)`) |
| `source_record_id` | the original image's id | the original **clip's** id |

The `audio_classification` plugin's `window` op runs at the **Generation** stage with `replace_input_records: true`, so each decoded clip is replaced by its fixed-length window records — `manifest.record_counts` reflects the post-windowing count, not the clip count (exactly as aggressive augmentation already does). Each window record carries `source_record_id` (the parent clip) and `window_index`; the trailing remainder is zero-padded or dropped per the recipe's `remainder` param. The `__w` vs `__v` suffix disambiguates the two; a record is never both (no aggressive audio augmentation in v1). Pre-prod doc-evolution addition — no `schema_version` bump.

**Aggregation contract (R7 — DR owns the key, the consumer owns the math).** `source_record_id` is DataRefinery's documented **clip↔window grouping key** for test-time window aggregation. The producer guarantee: every window record's `source_record_id` is the **verbatim `record_id` of the clip it was cut from** — every window of a clip shares one `source_record_id`, and (by the clip-level split discipline, R6/Story J.r) every window of a clip lands in exactly one split, so no clip's group straddles splits. The consumer obligation: group window-level outputs by `source_record_id` and apply its own aggregation policy (mean / max / logit-average / majority vote, etc.) to produce a clip-level result. **DataRefinery emits no aggregation policy and ships no aggregation op** — aggregation is purely a consumer concern, and `window_index` is available if the consumer needs window order within a clip. A window whose `source_record_id` resolves to no clip in the instance is a corruption signal (see § Failure modes ModelFoundry SHOULD detect).

> **MF consumer status — shipped (Subphase I-1, Story I.o.2).** ModelFoundry now implements this consumer obligation: the evaluation stage regroups window predictions by `source_record_id` and applies a recipe-declared `WindowAggregation.policy` (`mean` / `logit_average` / `majority_vote`) to produce clip-level results (`MF:src/modelfoundry/plugins/pytorch/aggregation.py`), with the dangling-grouping-key refusal (`verify_window_integrity`) and a `validate`-time cross-check (FR-2 check 23) that the bound records carry `source_record_id`. End-to-end clip-level MC-dropout reproducibility is asserted in Story I.p. The aggregation policy vocabulary is MF's own; DR still ships no aggregation op — this is purely a consumer annotation, not a change to the shared contract.

**Audio spectral features `mel` / `feature` (Stories J.s + J.t).** Audio featurization is a two-op chain at the **Featurizations** stage (run in recipe-declared order):

- `log_mel_spectrogram` (no fit, deterministic) writes a **raw** log-mel spectrogram `np.ndarray` of shape `(n_mels, n_frames)` in **librosa-native orientation** (mel bins on axis 0, time frames on axis 1). Convention: `output_field: mel`. One feature per input window; the stage does not change `record_counts`.
- `audio_normalize` (**fit-on-train**) reads `mel` and writes the **normalized** model-input feature. Convention: `output_field: feature`.

`audio_normalize` is a fit-on-train **Featurization**, *not* a Transformation: normalizing a derived feature must run after the feature exists, and DataRefinery runs `Transformations` before `Featurizations` (see the DataRefinery `tech-spec.md` § `pipeline.runner` stage-order rationale). Its per-mel-bin statistics **are persisted** under `fitted_statistics/<op_id>/` (see § `audio_normalize` statistics).

**Like `sample_array`, both `mel` and `feature` are array-valued in-pipeline representations and are NOT serialized into the dataset `<split>.jsonl`** (the JSONL writer drops non-JSON-native fields). Consumers do not read the feature arrays from the JSONL in v1; what crosses the boundary is the persisted `audio_normalize` statistics. The mel-axis orientation `(n_mels, n_frames)` is the cross-repo contract for any consumer that re-derives or re-normalizes features. **Persisting the feature array itself for downstream model consumption is the `npy_per_record` seam below (§ Audio feature-array persistence) — shipped in DR v0.25.0.** Pre-prod doc-evolution addition — no `schema_version` bump.

#### Audio feature-array persistence — `npy_per_record` + `feature_path` (shipped, DR v0.25.0)

> **Status: shipped (DR v0.25.0; MF Subphase I-1).** Both halves of the paired plan have landed. DataRefinery ships the `npy_per_record` sink + `feature_path` rewrite (DR Stories K.c/K.d, v0.24.0–v0.25.0); ModelFoundry ships the feature-array loader branch + per-mel-bin `audio_normalize` application (Subphase I-1, Stories I.m/I.n), **verified end-to-end against a real DR materialize** in Story I.m.1. The Q1–Q6 pins below are the **as-shipped** contract, confirmed against the installed DR. Sources: DR [`consumer-gap-solutions.md`](../consumer-gap-solutions.md) Gap 3 (`DR:docs/specs/consumer-gap-solutions.md`), MF [`modelfoundry/consumer-gap-solutions.md`](consumer-gap-solutions.md) Gap 3 (`MF:docs/specs/consumer-gap-solutions.md`), and the paired briefs [`datarefinery-audio-feature-persistence.md`](../datarefinery-audio-feature-persistence.md) (`DR:docs/specs/datarefinery-audio-feature-persistence.md` / `MF:docs/specs/datarefinery-audio-feature-persistence.md`) / [`modelfoundry-audio-feature-consumption.md`](../modelfoundry-audio-feature-consumption.md) (`MF:docs/specs/modelfoundry-audio-feature-consumption.md`).

**The gap today.** Because `mel` / `feature` are in-pipeline-only (above), only the `audio_normalize` *statistics* cross the boundary — a consumer cannot read the prepared feature arrays from a materialized audio instance, and the windowed `sample_array` is in-pipeline-only too (so it cannot be re-derived). The image-side mitigation (re-apply persisted stats over the uint8 sink) has no audio analogue.

**Agreed solution — additive float-array sink.** DataRefinery adds an **`npy_per_record`** sink `format` that persists a named float field per record at `features/<split>/<record_id>.npy` and rewrites a per-record **`feature_path`** into `<split>.jsonl`. This mirrors how `png_per_record` persists pixels and rewrites the JSONL `path`; the float array is a **sidecar**, never inlined into the JSONL — the "arrays are in-pipeline; persist via sidecar" convention holds.

**Pinned answers to the ModelFoundry review round (2026-06-23).** These six points are the binding contract MF builds the loader against; they resolve the two silent-correctness traps (Q1 anchor, Q2 double-normalize) and four cheaper pins.

- **Q1 — `feature_path` resolution anchor: instance-root-relative.** Resolve as `<instance>/<feature_path>` (e.g. `<instance>/features/train/<record_id>.npy`). This is the **same bucket as the J.g sink-rewritten `path`** (§ "Lazy-mode geometry…", "relative to the instance directory"), **NOT** the `image_path` bucket (which is `dataset/`-relative). The earlier "anchored exactly as `image_path` / sink-rewritten `path`" wording was self-contradictory — those two anchors differ; `feature_path` follows sink output, which lands at `<instance>/features/…` (a sibling of `dataset/`). MF's shipped Story I.k precedence already resolves bare/sink `path` against the instance root, so `feature_path` joins that branch. *(MF refs: `MF:docs/specs/stories.md` Story I.k; resolver `MF:src/modelfoundry/plugins/pytorch/data.py::_resolve_image_path`.)*
- **Q2 — which field is persisted: the raw `mel` (pre-normalize), and the consumer applies `audio_normalize` at load.** This is the audio analogue of the central rule *"normalization is applied by the consumer, not baked"* (§ "Normalization is applied by the consumer"): the sink's `field:` for the MF consumption path is **`mel`** (raw log-mel, output of `log_mel_spectrogram`), and the consumer applies the persisted per-mel-bin `audio_normalize` `mean`/`std` at load. **DataRefinery does not persist the already-normalized `feature` for this path** — doing so and then re-applying stats would double-normalize. (An author *may* technically sink any field, but the blessed, double-normalize-safe consumption contract is `mel` + consumer-applied `audio_normalize`; MF should consume `mel`.) *(MF read path: `MF:src/modelfoundry/plugins/pytorch/data.py::_resolve_normalization_steps` + `_FIT_ON_TRAIN_OPS`, to be extended to resolve `audio_normalize` from the recipe's `Featurizations` — tracked in MF's `plan_features` loader story.)*
- **Q3 — on-disk dtype: `float32`.** The persisted `.npy` is the `mel` array, written `librosa.power_to_db(...).astype(np.float32)`. The persisted `audio_normalize` `mean`/`std` are **`float64`** (same float64 promotion as image `normalize` stats). The consumer applies `(mel − mean) / std` with the usual promotion; byte-identity of the `.npy` is over the float32 array.
- **Q4 — on-disk rank: always 2-D `(n_mels, n_frames)` in v1.** Decode is mono (`librosa.load(..., mono=True)`), so the array is always rank-2. MF may assert `ndim == 2` and **owns the channel-dim insertion** (unsqueeze to `(1, n_mels, n_frames)`). The `(C, n_mels, n_frames)` multi-channel form is **future**, not v1.
- **Q5 — `feature_path` may be nested; join as a relative POSIX path.** Window `record_id` is `<clip_id>__w####` and `clip_id` may contain `/`, so `features/<split>/<record_id>.npy` is **not** guaranteed flat — it can carry a nested subtree exactly as `image_path` does (Story J.h). Treat `feature_path` as a relative POSIX path and join it onto the instance root verbatim; do not assume a single `features/<split>/` directory level.
- **Q6 — `feature_path` is authoritative over any stray `path`.** If a window record also carries a source `path` (the decoded `.ogg` clip), `feature_path` is authoritative for feature resolution and the consumer **ignores `path`** for that purpose — the same rule already given for `image_path` on aggressive variants.

**Pinned shape / orientation** (the obvious way a paired fix silently fails to line up): on disk `(n_mels, n_frames)` `float32` (librosa-native, mel bins on axis 0); the consumer `np.load`s it, unsqueezes to `(1, n_mels, n_frames)`, and applies the persisted per-mel-bin `audio_normalize` statistics through the existing fit-on-train read path.

**Rejected — spectrogram-as-image (uint8 PNG).** A uint8-quantization sink that routes the spectrogram through the existing `png_per_record` path is **not the contract.** It is lossy (high-dynamic-range `float32` → 256 levels + clipping), not round-trippable (breaks the byte-identical reproducibility contract), and carries wrong channel semantics (fake 3-channel RGB vs. true 1-channel) and wrong normalization semantics (image 0–255 vs. per-mel-bin). Both repos independently rejected it; the float-array path is the agreed solution.

**Cache identity & coupling.** The sink output is instance content → covered by `(recipe_hash, input_hash, seed)` cache identity exactly as `png_per_record` is (same recipe + inputs + seed ⇒ byte-identical `.npy`; a changed featurization param ⇒ different feature bytes). Consumption is **read-only**: the consumer never re-hashes the instance (loose-coupling invariant in `project-essentials.md`), so feature cache identity stays DataRefinery's responsibility.

**Versioning.** Additive — a new `SinkOp.format` enum value plus a new optional per-record `feature_path` field; existing recipes' canonical bytes are unchanged and the format is opt-in, so **no recipe `schema_version` bump**. (This supersedes the earlier "a float on-disk format would require a `schema_version` bump" note under § "Normalization is applied by the consumer".) As shipped (DR v0.25.0): `manifest.sinks[<name>].format` reports `npy_per_record`, and the `feature_path` field + the on-disk `features/<split>/` tree are bound shape surfaces. This section is **ratified shipped** — no longer forward-declared.

**Consumer branch selection.** Per-record field presence: `feature_path` ⇒ feature-array path; `image_path` / bare `path` ⇒ image path (composes with the instance-relative `path` resolution precedence). Clip-level evaluation still regroups windows by `source_record_id` (R7, above).

### Sidecar PNG encoding

Pillow `Image.save(path, format="PNG", optimize=False)`. Defaults verbatim — no quality/compression knobs. Determinism check: two runs of the same recipe + seed + inputs produce byte-identical sidecar files (validated by `tests/integration/test_runner.py` :: `test_aggressive_materialize_is_deterministic_across_runs`).

## Manifest fields ModelFoundry binds against

The `manifest.json` at the instance root is the authoritative metadata document. ModelFoundry-relevant fields:

| Field                  | Type                       | Meaning |
|------------------------|----------------------------|---------|
| `schema_version`       | `int`                      | Manifest schema version; separate from recipe `schema_version`. Currently `2` (v2, Story J.n.5, renamed `variant` → `overlays`). |
| `plugin`               | `str`                      | Plugin name (e.g., `"image_classification"`). |
| `plugin_version`       | `str`                      | Plugin schema version, as string. |
| `recipe_hash`          | `str` (64-hex)             | Canonical recipe bytes' SHA-256 (full digest). |
| `input_hash`           | `str` (64-hex)             | Per-source input content hash. |
| `seed`                 | `int`                      | The seed used by this materialization (CLI `--seed` overrides the recipe's `seed`). |
| `overlays`             | `list[str]`                | Ordered list of applied overlay names (FR-14); empty `[]` when none selected. **Renamed from `variant: str \| null` in manifest v2 (Story J.n.5)** — overlays are now a repeatable, ordered selection. |
| `record_counts`        | `dict[str, int]`           | Per-split post-pipeline record count. **For aggressive splits, this is the post-augmentation count** (i.e. includes variant multiplication). |
| `created_at`           | `datetime` (UTC ISO 8601)  | Wall-clock timestamp of the run. |
| `elapsed_seconds`      | `float`                    | Total run wall time. |
| `warnings`             | `list[ManifestWarning]`    | Non-fatal issues raised during the run; each has `stage` + `message`. |
| `is_partial`           | `bool`                     | True when materialization stopped early via `--stop-after`. |
| `failed_stage`         | `str | null`               | Stage at which a partial run stopped. |
| `class_balance`        | `str | dict | null`        | Forward-declared class-imbalance hint copied verbatim from `Splits.class_balance` (Story I.s / G10, v0.18.0+). `null` when unset. **DataRefinery does not resample or emit weights** — ModelFoundry honors this at training time. See `manifest.class_balance` shape below. |
| `sinks`                | `dict[str, SinkManifestEntry]` | Per-sink summary of disk-output artifacts captured at materialize time (Story I.d). Empty dict when the recipe declares no `Sinks` section. |
| `sinks_skipped`        | `dict[str, str]`           | Sinks declared on the recipe whose host stage was not reached under a partial `--stage` run (Story I.f.1). Maps sink name → declared stage. Empty on full materializes. |
| `sample`               | `SampleManifestEntry | null` | Shipped (Phase J Story J.a; `Manifest.sample` present in DR 0.25.0). Per-split sample-subset record counts + selector echo; `null` when no `SampleData:` is declared. See `manifest.sample` shape below. |
| `label_classes`        | `list[<label-dtype>] | null` | Canonical class set: distinct label values across all labeled records, sorted ascending. `null` when no labeled records exist (FR-22 fully-unlabeled case). Shipped Phase J Story J.f, v0.20.0. See `manifest.label_classes` shape below. |

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

**Per-class counts.** DataRefinery does **not** pre-compute per-class counts in the manifest. To honor `emit_inverse_frequency_weights` (or any other strategy requiring class frequencies), consumers scan the labeled JSONL records themselves and tally. The class **set** is canonical via `manifest.label_classes` (Phase J Story J.f, v0.20.0); the **counts** remain consumer-derived.

### `manifest.sample` shape

Shipped (DataRefinery Phase J Story J.a; `Manifest.sample` / `SampleManifestEntry` present in DR 0.25.0). The field reflects the declarative subset produced by the SampleData runtime stage; `null` when no `SampleData:` section is declared in the recipe.

| Field           | Type                | Meaning |
|-----------------|---------------------|---------|
| `selector`      | `dict`              | Verbatim echo of `recipe.SampleData.selector` — `kind` (`uniform` \| `per_class`), `n` or `fraction`, optional `splits`. |
| `record_counts` | `dict[str, int]`    | Per-split record count in the sample subset. Keys are the splits the selector targeted; absent splits in the dict were not sampled. |

The sample subset is emitted under `<instance>/sample/<split>.jsonl` with the same per-line shape as `dataset/<split>.jsonl`, and shares the source records' `path`/`image_path` resolution rules. The `dataset/` block is unaffected — consumers wanting the full dataset read `dataset/`; consumers wanting the small fast-iteration subset read `sample/`. **DataRefinery treats `sample/` as informational** (not a stable on-disk contract) until Story J.a ships and this subsection is ratified; pre-J.a, consumers SHOULD NOT bind against it.

### `manifest.label_classes` shape

Shipped Phase J Story J.f, v0.20.0. The field enumerates the canonical class set used by all labeled records in the materialized instance — a single sorted list that consumers bind against for label→logit-index mapping, confusion-matrix axis ordering, and per-class column naming in predictions output.

- **Computation.** At materialize time, DataRefinery scans every labeled record across every split, takes the distinct union of label values, and sorts ascending (Python `sorted(...)` semantics for the underlying label dtype). Unlabeled records (FR-22) are excluded; if no labeled records exist, the field is `null`.
- **Type.** `list[<label-dtype>] | null`. Dtype matches the values observed in records — typically `str` (class name) but plugin-dependent.
- **Stability and cache identity.** The field lives in the manifest, not the recipe, so it does not perturb canonical recipe bytes and does not affect cache identity. Re-materializing the same recipe over the same inputs produces an identical list.
- **Producer commitment scope.** This is the **set**, not the **counts** — per-class frequencies remain consumer-derived from JSONL (see § `manifest.class_balance` shape § "Per-class counts").

**Why this lives in the manifest, not in consumer code.** Without a producer-side canonical class list, every consumer scans JSONL and chooses a sort convention independently. Two consumers (or two binding flows in one consumer) can silently disagree on ordering, leading to prediction-column ↔ confusion-matrix-axis ↔ class-weight-vector misalignment that is operationally catastrophic and hard to debug. Centralizing the list in the manifest makes the ordering the producer's commitment.

**Adoption migration.** Pre-v0.20.0 manifests do NOT carry `label_classes`. Consumers reading older instances SHOULD continue to derive the class set by scanning every labeled split (`train` + `val` + `test`, skipping unlabeled records) and sorting ascending — the same algorithm the producer now applies, so the derived set is byte-identical to what `manifest.label_classes` would have emitted. Scanning `train.jsonl` alone is fragile — a class present only in `val`/`test` (or in an unlabeled-source variant) will be silently omitted.

## Fitted statistics ModelFoundry binds against

Fit-on-train operations persist the statistics they fit on the train split under `fitted_statistics/<op_id>/`, where `<op_id>` is the op's `name` in its recipe section. Both fit-on-train **Transformations** (image `normalize`, `mean_subtract`) and fit-on-train **Featurizations** (image `categorical_encode` vocabularies; audio `audio_normalize` per-mel-bin stats) use the same `fitted_statistics/<op_id>/` mechanism. This is a **downstream binding surface**: a training consumer reads these statistics to apply the same transform its training data was prepared with, so that train/inference parity holds. It is distinct from the recipe-to-recipe `stats_from_instance` import (§ Recipe-side contract) — that mechanism is for *other DataRefinery recipes*; this section is for *downstream training consumers* such as ModelFoundry.

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

### `audio_normalize` statistics (Story J.t)

The `audio_classification` plugin's fit-on-train `audio_normalize` op (a **Featurization**, not a Transformation — see § Audio spectral features) persists the same `mean` / `std` vector pair as image `normalize`, with the **same parquet shape** (single `value` column, one row per element, axis-0 order), the **same zero-variance guard** (`std == 0 → 1.0` at apply, persisted `std` unmodified), and the **same `stats_from_instance` import** support. The only difference is the **statistics axis**:

| Op | Vector length | Axis the stat is per | Apply broadcast |
|---|---|---|---|
| image `normalize` | `C` (RGB channels) | last axis of `(H, W, C)` | over `H, W` |
| `audio_normalize` | `n_mels` | **mel axis (axis 0)** of `(n_mels, n_frames)` | over time frames |

So `mean`/`std` each have **`n_mels` rows** (not `C`), and a consumer re-applying them standardizes each mel bin across its time frames: `(feature - mean[:, None]) / std[:, None]`. The vectors correspond to the `mel` feature (`log_mel_spectrogram` output); the normalized result is the `feature` field. There is no channel-order concern (audio is mono in v1); the only alignment requirement is that the consumer's feature is in librosa-native `(n_mels, n_frames)` orientation.

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

This keeps the contract honest: **DataRefinery owns the statistics; the consumer owns the application.** For the **image** path this is the stable v1 contract — the sink writer ships only `png_per_record`/uint8 and DataRefinery does not emit normalized float32 image tensors. For **audio** features, persisting a float array **shipped** as an additive sink format (`npy_per_record` + `feature_path`, DR 0.25.0), not a `schema_version` bump — see § "Audio feature-array persistence" (ratified shipped). *(This refines the earlier blanket statement that any float on-disk format would require a `schema_version` bump: a new opt-in sink `format` is additive and leaves existing recipes' canonical bytes unchanged.)*

## Consumer-applied transformations vs. baked transformations

The previous section drew the consumer-application boundary for normalization. This section generalizes that boundary across DataRefinery's full transform vocabulary: which transformations are **baked** into the materialized image bytes (consumer reads the transformed pixels) vs. which the consumer must **re-apply** at training/inference time.

### Baked (consumer reads transformed pixels)

- **Aggressive-mode `Augmentations`.** The realized variant's pixels are written to `<split>/images/<record_id>.png` and the JSONL record carries `image_path:` pointing at the sidecar. Consumers MUST resolve variant pixels via `image_path`. This is the well-supported path-rewrite case in v1.
- **`Sinks` declarations.** Sinks write their captured stage output under `<instance>/<path_template_resolved_root>/...` (see `manifest.sinks`). For the pixel-altering-Transformation case (below), DataRefinery additionally rewrites the JSONL `path` to point at the qualifying sink's per-record output, so a consumer reading `path` lands on the transformed pixels directly. For sinks declared for other reasons (e.g. capturing a non-`image` field, or an earlier-stage snapshot), `path` is unaffected and consumers locate sink output via `manifest.sinks`.

### Consumer-applied (consumer re-applies the transform from persisted stats)

- **`normalize` / `mean_subtract`.** Fitted statistics are persisted; pixel bytes on disk remain uint8 PNG. Application is the consumer's job — see § "Normalization is applied by the consumer, not baked into image bytes" above. This is the intentional, stable case in v1.

### Lazy-mode geometry / pixel-altering Transformations (resolved — Story J.g, v0.20.0)

In DataRefinery v0.19.0 and earlier, the `path` field was set ONCE at input loading and NEVER rewritten by Transformations or Sinks. A non-aggressive recipe declaring a pixel-altering Transformation op (e.g., `resize`) produced JSONL where (1) the in-memory `image` numpy array WAS transformed, (2) the `image` field WAS dropped at serialization, and (3) `path` still pointed at the **untransformed source image** — so a consumer reading pixels from `path` silently decoded pre-transform geometry. Story J.g (v0.20.0) closes this gap.

**Closed pixel-altering-op set.** A Transformation op is *pixel-altering* when its `apply` changes the image array's bytes in a consumer-visible way that is NOT recoverable from persisted fitted statistics. Today the set is **`{resize}`** (geometry change). It is declared per-op on the plugin (`OperationSpec.pixel_altering`), so the set grows with the plugin, not by editing this doc. Explicitly NOT pixel-altering: `normalize` / `mean_subtract` (stat-based, consumer-applied — fitted stats persisted) and `cast` (parameter-deterministic numeric op, consumer-applied).

**Validator check 26.** A recipe with a pixel-altering Transformation applying to any lazily-serialized split MUST declare a qualifying image sink — `format: png_per_record`, `field: image`, `stage` in `{post_Transformations, post_Featurizations, post_Augmentations, post_OutputExpectations, post_Visualizations}` — covering those splits. Authoring the transform without such a sink is refused at validate time (the message names the offending op and the uncovered splits). Splits realized as aggressive variants are exempt (their pixels are already baked via `image_path`).

**Path-rewrite mechanism.** At dataset serialization, for each non-aggressive record in a covered split, DataRefinery rewrites `path` to the qualifying sink's per-record output, resolved from the sink's `path_template` and **relative to the instance directory** (e.g. `transformed/<split>/<record_id>.png`). The sink also writes the PNG, so the rewritten `path` resolves to a real file holding the transformed pixels. When multiple qualifying sinks cover a split, the first in recipe declaration order wins. This rewrite also applies to the `sample/` sidecar JSONL.

**Consumer guidance (v0.20.0+).**

- `path` is **instance-relative** for pixel-altering-Transformation recipes (resolve as `<instance>/<path>`); it remains the loader-stamped (possibly host-absolute) source path for recipes with no pixel-altering Transformations. Treat a `path` that is not absolute and does not exist on the source host as instance-relative. (Host-portability of the source-resolution `path` is covered in § "Source-resolution path".)
- For recipes whose `Transformations:` contains only fit-on-train stats ops (`normalize`, `mean_subtract`) or `cast`, the prior contract holds unchanged: uint8 PNG on disk via source `path`, consumer applies stats from `fitted_statistics/`.
- Aggressive `Augmentations` continue to expose realized variant pixels via `image_path`; that path is unchanged by Story J.g.
- For the CIFAR-10 reference flow (no geometry transforms), behavior is unchanged end-to-end.

## Report subsections

The `report/` directory holds the human-readable summary:

- **`report/report.md`** — markdown summary of the recipe, splits, operations applied (filters, generation, transformations, featurizations, augmentations, visualizations), fitted statistics, and warnings. Each augmentation op renders mode-aware:
  `op_name (\`op_kind\`, materialization=lazy)` or
  `op_name (\`op_kind\`, materialization=aggressive, expansion=N)`.
- **`report/drift.json`** — drift-relevant subsection of the report, emitted as structured JSON. **Pre-production its schema is unstable**; ModelFoundry consumers should treat it as informational until v1.0. See FR-15 in `features.md` for the current shape. **One stable field within it:** `drift.json.recipe_hash` (Story J.j) — the full 64-hex SHA-256 of the canonical recipe bytes, echoed from the cache key and **equal to `manifest.recipe_hash`** on every fresh instance. Consumers may read it directly to detect a stale fitted-statistics block (see § "Failure modes ModelFoundry SHOULD detect") without a second `manifest.json` read. Pre-J.j instances (v0.19.x and the early v0.20.0 dev line) omit the key — read it as `null`/absent and fall back to `manifest.recipe_hash`; pre-prod re-materialization populates it.
- **`report/visualizations/<viz_name>.png`** — persisted reporting-mode visualization images (FR-13). Stage-aware dispatch (Story I.v / G7) is **internal** to the materialize-time pipeline: a viz op's `stage:` declaration selects which per-stage record snapshot the renderer reads, but the on-disk surface is unchanged — every reporting-mode viz still produces one PNG (named `<viz_name>.png` or `<viz_name>_<extra>.png` for multi-output ops) in this directory, and `report.md` does not gain per-stage subsections in v1. ModelFoundry consumers binding against the report surface see the same flat layout regardless of how many pipeline stages a recipe spans. Per-stage report subsections are tracked in [`stories.md § Future`](../stories.md).

## Cache-identity contract

The cache key (instance directory path) is `SHA-256(canonical_recipe_bytes) ⊕ SHA-256(raw_input_bytes) ⊕ seed`, truncated to 16 hex chars per component for the path (`<recipe-hash16>/<input-hash16>/<seed>`). The **full** digests live in `manifest.json` for audit.

**`recipe_hash` is the *segmented* identity hash as of schema v3 (Story J.n.3).** It is no longer the flat `sha256(model_dump → json.dumps)`. The recipe is partitioned into four identity segments (`core`/`plugin`/`overlays`/`extensions`); each segment's sorted-compact-JSON is SHA-256'd, the digests are joined in fixed order (`b"\x1f".join`), and `recipe_hash = SHA-256(join)`. Per-segment digests are independent — a change to one segment cannot move another's digest (scoped invalidation). Every pydantic field default still participates *within its segment*; the takeaway for consumers is unchanged and strengthened: **`recipe_hash` is DataRefinery's to compute — never replicate it.** (The flat `to_canonical_bytes` still exists as the full-recipe dump but no longer defines identity.)

Bumping `schema_version` (in `src/datarefinery/recipe/loader.py`'s `SUPPORTED_SCHEMA_VERSIONS`) is the deliberate invalidation lever. Non-bumped DataRefinery releases preserve cache identity. Releases that DO invalidate carry a prominent CHANGELOG callout (see v0.15.0 for the H.p–H.r.2 example: adding `AugmentationOp.materialization` and `expansion` defaults perturbed canonical bytes for any recipe with `Augmentations`).

**Schema v1 → v2 (Phase I bundle 4, v0.19.0).** Three reshape stories (I.x.1 / G15 Filters, I.x.2 / G12 Generation, I.x.3 / G16a assertion naming) ship together as a `schema_version` bump. v1 recipes are auto-migrated by the loader (`recipe.migrations.v1_to_v2`); the cached `recipe.json` always reflects the v2 canonical shape. ModelFoundry consumers that bind against recipe-model fields directly need to track the v2 names — most notably:

- **`FilterOp`** (Story I.x.1 / G15): v1 nested `predicate: {op, ...rest, seed?}`; v2 lifts to top-level `{op, params, seed?}` (matches every other section). The migration is one-way; ModelFoundry should bind against the v2 shape and rely on the loader to migrate v1 recipes on read.
- **`GenerationOp`** (Story I.x.2 / G12): v1 left `op` implicit (the recipe's `name` doubled as the op lookup key), called the splits field `applies_at`, and required `output_schema` to be an explicit `dict[str, FieldSpec]`. v2 has explicit `op: str` at top level, renames `applies_at` → `splits`, and widens `output_schema` to accept the literal `"matches_input"` shorthand (resolved at materialize time to `Output.record_schema` plus declared tag fields). The migration handles all three reshapes and the documented v1 workaround pattern of stashing `op:` inside `params:`; ModelFoundry should bind against the v2 names and treat `output_schema: "matches_input"` as a possible value.
- **Assertion `kind` naming** (Story I.x.3 / G16a): three v1 bare-verb names rename to predicate-sentence form — `dtype` → `dtype_equals`, `range` → `value_range`, `record_count` → `record_count_in_range`. The mapping applies to both `InputContracts[*].assertion` and `OutputExpectations[*].assertion`. `required_field` and `distributional` are unchanged. v1 names are removed (not aliased) post-migration; ModelFoundry consumers reading the cached `recipe.json` will see the v2 names exclusively. The seven additional v2 kinds added in Story I.o (`split_record_counts`, `per_class_count_per_split`, `count_by_field`, `count_by_fields`, `shape_equals`, `value_in_set`, `per_class_count_equals`) were already predicate-sentence and are unaffected.

**Schema v2 → v3 (Phase J Recipe Architecture bundle, v0.22.0 — Story J.n.3).** The bump is a **canonical-form algorithm change**: identity moved to the segmented hash above. It is a **one-time pre-1.0 cache invalidation** — every existing instance re-materializes once. Two consumer-relevant points:

- **The recipe shape on disk is UNCHANGED.** Segmentation is an internal partition (Option 1), not an author-facing reshape — `recipe.json` stays flat with the same top-level sections and field names. Consumers binding to recipe-model fields need **no** changes for v3; the loader migrates v1/v2 recipes to v3 by stamping `schema_version: 3` (no field redistribution). Only `recipe_hash` (and therefore the instance path) changes — and consumers must not bind to that directly anyway (use the resolver).
- **`AudioSource` discriminated-union member (shipped, DR 0.25.0).** `InputSource` is the open base of a narrow union; an audio source carries `target_sample_rate: int` (selected presence-based; `type` stays a free `str`). Image sources are unaffected and structurally cannot carry audio-only fields. The `audio_classification` plugin proper has shipped (`AudioSource` + the plugin are present in DR 0.25.0; MF consumes its `npy_per_record` feature-array output in Subphase I-1). Consumers binding only to image recipes see no change.

### Per-segment versioning + migration registry (Story J.n.7)

The segmented identity above is governed by **per-segment versions — there is no global umbrella counter.** Each segment evolves on its own version axis (`core`, `plugin:image`, `plugin:audio`, `overlays`, `extensions`); a bump to one segment invalidates only that segment's scope. The architectural rationale is the DataRefinery Phase-J recipe-architecture spike memo (`DR:docs/specs/phase-j-recipe-architecture-spike.md` in the DR repo) — the **cross-tool-family standard** ModelFoundry adopts wholesale.

Mechanics relevant to consumers:

- **The flat `recipe.schema_version` stays the on-disk era marker.** DataRefinery keeps the recipe flat (Option 1), so there is **no on-disk `segment_versions` block** — per-segment versions live as DataRefinery build constants plus a structural era-detection table (`recipe.segments.SCHEMA_ERA_SEGMENT_VERSIONS`) keyed by the flat `schema_version`. Consumers continue to read the single flat `recipe.schema_version` (currently `3`); they do **not** need to parse a per-segment version block.
- **Per-segment migrations run on DataRefinery's read path.** A `(segment, from, to)`-keyed registry (`recipe.segments.SEGMENT_MIGRATIONS`) brings each segment up to the current build version when a recipe is loaded; the cached `recipe.json` always reflects the latest segmented shape. Today the registry is empty (no segment has bumped past v1) and the dispatch is an exact pass-through. When a segment first bumps, DataRefinery ships the migration with it.
- **Pin-test discipline guarantees scoped invalidation.** DataRefinery pins each segment's digest in CI (`tests/unit/test_segment_pin_hashes.py`); an unexpected move of any single segment's digest is a blocking failure forcing a conscious per-segment bump + migration. This is the enforcement behind the cross-repo promise that an audio-plugin change cannot silently invalidate an image recipe's cache (and vice-versa).

The consumer takeaway is unchanged and reinforced: **`recipe_hash` is DataRefinery's to compute — never replicate it**; bind to the resolver's `instance_path` / `cache_key`.

## Resolving a materialized instance

The previous section documents the cache-key derivation for **understanding and audit only**. Consumers MUST NOT reimplement it. DataRefinery exposes one blessed resolver; use whichever entry point fits.

```python
from datarefinery import resolve_instance     # top-level facade

report = resolve_instance("recipe.yaml", cache_root="./data", seed=None, variant=None)
```

```python
from datarefinery import DataRefinery        # equivalent, via the handle

report = DataRefinery.from_recipe("recipe.yaml", config=cfg, variant=v, seed=s).status()
```

`resolve_instance(...)` is a thin convenience that **delegates to `DataRefinery.status()`** and returns the identical `StatusReport` — the same relationship the top-level `materialize()` has to `DataRefinery.from_recipe(...).materialize()` (one resolution implementation, two ergonomic entry points). `seed=None` uses the recipe's `seed` (an int overrides it); `cache_root=None` uses `RuntimeConfig`'s default. Both forms hash the recipe's declared inputs (cache identity includes the input hash; see § Cache-identity contract), so the inputs must be present on the resolving host — a recipe needing a custom `plugin_path` should use the full handle.

**`StatusReport` shape** (`datarefinery.StatusReport`, a frozen dataclass):

| Field | Type | Meaning |
|---|---|---|
| `cache_status` | `"hit" \| "miss" \| "corrupt"` | `hit`: instance + parseable `manifest.json` present. `miss`: no instance for this recipe + inputs + seed (not an error). `corrupt`: directory present but `manifest.json` missing/unparseable. |
| `instance_path` | `Path` | The **deterministic** instance directory — populated even on a `miss` (where the instance *would* live). |
| `cache_key` | `CacheKey` | Full `recipe_hash` (64-hex), `input_hash` (64-hex), `seed`; `.short` is the 16-char path shard. |
| `manifest` | `Manifest \| None` | Parsed manifest on `hit`; `None` otherwise. |
| `note` | `str \| None` | Human-readable detail on `corrupt`. |

**Do NOT recompute the cache key or instance path yourself.** Cache identity is DataRefinery's contract, not a consumer-replicable formula. Per § Cache-identity contract, `recipe_hash` is the **segmented** hash (per-segment SHA-256 digests joined and re-hashed, as of v3), and **every pydantic field default participates within its segment** — so a DataRefinery release that adds a field, changes a default, or refines the canonical algorithm (as v3 itself did) shifts `recipe_hash` for overlapping recipes. A consumer that hand-rolls the key (or builds the `<recipe-hash16>/<input-hash16>/<seed>` path directly) will, after any such change, **silently resolve to the wrong or a stale directory with no error** — exactly the brittleness this resolver exists to absorb. Bind to `report.instance_path` and `report.cache_key`; never to a locally-computed equivalent. *(Pinned 2026-06-13, Story J.l — see header.)*

## Schema-version coordination policy

**Two independent `schema_version` counters — do not conflate them.** A materialized instance carries *two* fields named `schema_version`, governed by different rules:

| Field | Where | Current value | Source of truth |
|---|---|---|---|
| `recipe.schema_version` | `recipe.json` (top-level) | `3` | `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS` / `LATEST_SCHEMA_VERSION` |
| `manifest.schema_version` | `manifest.json` (top-level) | `2` | `datarefinery.pipeline.manifest.MANIFEST_SCHEMA_VERSION` |

`recipe.schema_version` versions the **recipe shape** (the loader migrates v1→v2→v3 on read); `manifest.schema_version` versions the **manifest document format** and advances on its own, unrelated cadence (now `2` after the Story J.n.5 `variant`→`overlays` rename). A consumer binding against the recipe-schema coordination logic below MUST read `recipe.schema_version` — reading `manifest.schema_version` (currently `2`) where the recipe version (currently `3`) is meant is a silent off-by-one that will mis-route the migration check. *(F5, pinned in Round 3 — see header.)*

As of the current DataRefinery release the supported set is **`{1, 2, 3}`** with **`LATEST_SCHEMA_VERSION = 3`** (importable as `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS` / `LATEST_SCHEMA_VERSION`). DataRefinery's loader applies the registered `(1, 2)` then `(2, 3)` migration chain before validation, so a consumer using `Instance.load` always sees the **v3-shaped** recipe regardless of the on-disk recipe's authored version. The v3 bootstrap is version-stamp-only (no field reshape — see § Cache-identity contract "Schema v2 → v3"), so the v3 recipe shape is field-identical to v2; the substantive v3 change is the segmented `recipe_hash`. A consumer that still pins its tracked set to `{1, 2}` MUST update to include `3` before binding v3 instances, or it will hard-error per the rule below.

ModelFoundry SHOULD track DataRefinery's current `SUPPORTED_SCHEMA_VERSIONS` set. When consuming a recipe whose `schema_version` is **outside** ModelFoundry's known support range:

- If the recipe's `schema_version` is **higher** than anything ModelFoundry knows about → **hard error** on ModelFoundry's side, with an error message naming the recipe's version and ModelFoundry's highest-supported version. Do not attempt to coerce, downgrade, or guess.
- If the recipe's `schema_version` is **lower** than ModelFoundry's lowest known → ModelFoundry's choice (typically a forward-migration in DataRefinery's `recipe.loader.migrations` already handled the shape; ModelFoundry can rely on the loader-emitted shape).

ModelFoundry adopting a newer DataRefinery `schema_version` requires updating ModelFoundry's tracked set and re-running its own contract tests against the new manifest/recipe shapes.

**Per-segment coordination (Story J.n.7).** Under the segmented architecture the *finer-grained* unit of evolution is the **per-segment version** (`core`, `plugin:image`, `plugin:audio`, `overlays`, `extensions`), not the flat counter. Because DataRefinery keeps the recipe flat (no on-disk segment-version block), the flat `recipe.schema_version` remains the **consumer-facing coordination counter** — a consumer tracks the flat `SUPPORTED_SCHEMA_VERSIONS` set exactly as above, and any per-segment bump that changes the recipe shape DataRefinery surfaces by also advancing the flat era marker. A consumer that wants segment-level granularity (e.g. "I only care about `plugin:audio` changes") MAY read DataRefinery's `recipe.segments.current_segment_versions()` / `SCHEMA_ERA_SEGMENT_VERSIONS`, but the **binding contract is still the flat `recipe.schema_version`**: track it, hard-error on an unknown-higher version, and re-run contract tests on adoption. The same per-segment standard applies symmetrically to ModelFoundry's own recipe model (MF adopts the horizontal mechanism wholesale; its vertical stage-reuse axis stays MF-owned).

## Forward-compatibility expectations

- **Unknown ops in `Augmentations`** (post-prod): ModelFoundry SHOULD detect any `AugmentationOp.op` it does not recognize and fail with a clear `"unknown augmentation op '<name>'; supported: [...]"` error. Silent fallback to a no-op augmentation is forbidden.
- **Unknown fields in `AugmentationOp`** (post-prod): ModelFoundry SHOULD reject recipes with unrecognized AugmentationOp fields. DataRefinery enforces `extra="forbid"` on its own side; ModelFoundry should mirror.
- **Unknown manifest keys** (pre-prod): ModelFoundry consumers SHOULD log-and-continue rather than hard-fail, to allow DataRefinery to add informational fields without breaking adopters mid-stream. Post-prod this softens further: unknown keys are stable forward-compat.

## Failure modes ModelFoundry SHOULD detect

A trained-but-broken handoff is worse than a refusal. ModelFoundry's adapter should detect at least these conditions before training begins:

- **Stale fitted statistics**: `manifest.recipe_hash` does not match the on-disk recipe's canonical hash → the instance was rendered against an older recipe shape; do not train on it. (`drift.json.recipe_hash` is emitted as of Story J.j and aligns with `manifest.recipe_hash`; a mismatch between the two — or against the recomputed canonical hash — is ipso facto a stale instance. On pre-J.j instances the key is absent; fall back to `manifest.recipe_hash`.)
- **Missing required fields**: a manifest absent any of `plugin`, `plugin_version`, `recipe_hash`, `record_counts`, or `seed` is malformed; refuse to consume.
- **Missing required fitted statistics**: a consumer that must apply a fit-on-train transform (e.g., `normalize`) but finds no `fitted_statistics/<op_id>/` for that op — or finds the directory but is missing a required vector such as `mean` or `std` — should refuse to train rather than silently skip normalization, naming the missing op_id / statistic in the error.
- **Schema-version mismatch**: see § Schema-version coordination policy.
- **Aggressive variant sidecar missing**: a JSONL line declares `image_path: "<rel>"` but the sidecar at `<rel>` doesn't exist on disk → instance is corrupt; refuse to consume.
- **Dangling audio window grouping key**: a window record's `source_record_id` (see § Audio window records) does not resolve to any clip-level identifier present in the instance → the clip↔window grouping is broken; refuse to consume rather than aggregate against a phantom clip. DataRefinery guarantees every window's `source_record_id` is the verbatim `record_id` of the clip it was cut from, so a non-resolving value signals a corrupt or mis-assembled instance.
- **Plugin missing**: `manifest.plugin` is not an installed plugin in ModelFoundry's environment → cannot resolve the plugin's runtime schema; refuse to consume.

## Versioning and adoption

- DataRefinery ships **forward-declared contracts** at release time: each release's CHANGELOG enumerates contract changes (recipe shape, manifest, report, on-disk layout). ModelFoundry tracks but does not block DataRefinery releases.
- ModelFoundry adopts **on its own schedule**. A DataRefinery consumer using the in-repo `datarefinery` library directly is the no-mediation case; ModelFoundry sits one degree away and benefits from forward-declaration.
- **Pre-production (v < 1.0)**: this document may change without a schema-version bump if no recipe/manifest/report bytes change. Documenting an existing surface in this file is not a contract change.
- **Post-production (v >= 1.0)**: this document becomes a stability contract. Changes to any contract surface go through the schema-version-bump + migration ceremony.

DataRefinery-side cross-references (vendor of this contract):

- `DR:docs/specs/features.md` — feature requirements (FR-11 augmentations, FR-15 reporting).
- `DR:docs/specs/tech-spec.md` — full recipe model + manifest + instance directory tree.
- `DR:docs/specs/project-essentials.md` — cache-identity / determinism / cross-repo coordination rules.

ModelFoundry-side counterparts (consumer of this contract):

- `MF:docs/specs/datarefinery/vendor-dependency-spec.md` — **this contract, as vendored into MF** (MF keeps DR-pushed docs + the shared contract under `docs/specs/datarefinery/`; this is the consumer-side copy of the file you are reading).
- `MF:docs/specs/consumer-gap-solutions.md` — MF gap verdicts/solutions (Gap 1 shipped, Gap 2 resolved, Gap 3 audio-feature plan + the pinned Q1–Q6).
- `MF:docs/specs/modelfoundry-audio-feature-consumption.md` — the MF consumption brief (paired with `DR:docs/specs/datarefinery-audio-feature-persistence.md`).
- `MF:src/modelfoundry/plugins/pytorch/data.py` — the consumer loader: `_resolve_image_path` (instance-relative `path`/`image_path` precedence, Story I.k) and `_resolve_normalization_steps` / `_FIT_ON_TRAIN_OPS` (fit-on-train stat application).
- `MF:src/modelfoundry/pipeline/data_binding.py` — `_verify_record_images_resolvable` (bind-time fail-fast resolvability gate).
- `MF:docs/specs/project-essentials.md` — MF's loose-coupling / read-only-consumption invariants (MF never re-hashes the DR instance).
- `MF:docs/specs/stories.md` — Story I.k (instance-relative `path` resolution fix).
