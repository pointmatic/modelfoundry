# Spike A.c — DataRefinery instance binding

> **Type:** integration spike (will external systems connect?).
> **Status:** complete. **Deliverable:** this document. The script
> `scripts/spike_datarefinery_binding.py` is throwaway evidence, not
> production code.
> **Date:** 2026-05-28. **Verified against:** `ml-datarefinery==0.17.0`.

## Question

Before the production binding modules land (B.i `pipeline.data_binding`,
C.f `plugins.pytorch.data`), can ModelFoundry read a **real** materialized
DataRefinery instance — parse `manifest.json`, iterate `dataset/<split>.jsonl`,
resolve a record's pixels per the vendor-dependency-spec, decode to a numpy
array — and produce DataLoader-ready samples? And does the on-disk reality
match `docs/specs/datarefinery/vendor-dependency-spec.md`?

## Decision: spike against real DataRefinery, not a mock

`ml-datarefinery==0.17.0` is installed in the base venv and is importable
(`datarefinery.Instance`, `datarefinery.materialize`,
`datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS`). The spike materializes
a real instance from a synthetic 2-class ImageFolder via the bundled
`scaffolder.init.scaffold_image_classification` + `datarefinery.materialize(...)`,
then binds to it both ways: the library API (`Instance.load`) and the raw
file contract (`manifest.json`, `dataset/train.jsonl`, sidecar PNGs). No mock
was needed for the lazy/source-resolution path.

The one exception (aggressive-variant sidecars) is documented below — the real
producer could not be driven to emit them on 0.17.0, so the **consumer-side**
resolution was validated against a hand-rolled, spec-conformant fixture.

## What was confirmed

The `tech-spec.md` § `plugins.pytorch.data` `DataRefineryDataset` adapter
pattern holds. Specifically, against a real instance:

1. **Directory layout matches the spec exactly.** The instance lands at
   `<cache-root>/instances/<recipe-hash16>/<input-hash16>/<seed>/` (e.g.
   `.../instances/2ad08508350b637c/19e08a19264d44d0/1234`).
2. **`Instance.load(path)` round-trips** and self-verifies the persisted
   `recipe.json` canonicalizes to `manifest.recipe_hash` (raises
   `MaterializeError` otherwise — DataRefinery already enforces the stale-instance
   guard the vendor-dep-spec § Failure modes asks consumers to detect).
3. **Manifest carries the required fields** ModelFoundry binds against:
   `plugin` (`"image_classification"`), `plugin_version` (`"1"`, a **string**),
   `recipe_hash`, `record_counts` (`{"train": 11, "val": 2, "test": 3}`), `seed`.
4. **Source-resolution records** (lazy / no aggressive ops) carry exactly
   `record_id`, `label`, `path`. The `image` numpy field is dropped at
   serialization as the spec promises — pixels resolve from `path`.
5. **Decode pipeline works:** `Image.open(path).convert("RGB")` → `np.float32`
   `/255.0` → CHW transpose yields a `(3, H, W)` float32 array; a 4-sample batch
   stacks to `(4, 3, H, W)` — the shape `torch`'s default collate produces.
6. **Schema-version coordination is checkable:** the bound recipe's
   `schema_version` (1) is comparable against
   `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS` (`{1}`). B.i's check 19
   / the validator can import that set directly.

## Surprises / deviations to carry into B.i and C.f

1. **`label` is a string class name, not an integer index.** Records carry
   `label: "class_0"`, not `label: 0`. The `DataRefineryDataset` adapter (C.f)
   **must** build a deterministic `label -> index` map (sorted class names →
   contiguous ints) before feeding a model. The class count for the
   architecture's `num_classes` check (C.c) comes from the distinct label set /
   the instance's label schema, and the ordering must be stable (sort the class
   names) so the mapping is reproducible across runs and machines.

2. **`record_id` is a path-like string** (`"train/class_0/img_0_02.png"`), not
   a flat token. This is benign for reading, but it interacts badly with
   aggressive sidecar writes on the producer side (see next point), and means
   any code that uses `record_id` to build a filesystem path must treat it as
   containing separators.

3. **DataRefinery 0.17.0 cannot materialize an aggressive-augmentation instance
   from a scaffolded recipe.** Adding an `Augmentations` op with
   `materialization: aggressive, expansion: 2` makes `materialize()` raise
   `FileNotFoundError` deep in `pipeline/runner.py::_prepare_record_for_persistence`:
   the sidecar target is
   `dataset/train/images/<record_id>__v000.png` and, because `record_id` contains
   `/`, the nested parent dirs (`dataset/train/images/train/class_0/`) are never
   created before `PIL.Image.save`. This is a **producer-side DataRefinery bug**,
   not a ModelFoundry issue.
   - **Risk for B.i / C.f:** we cannot yet validate the aggressive sidecar /
     `image_path` consumer path against a *real* instance. Options when B.i lands:
     (a) pin/upgrade to a DataRefinery release that fixes the path-like-record_id
     sidecar bug, (b) build aggressive instances in tests from a fixture whose
     source filenames are flat (no class subdirs) so `record_id` has no slashes,
     or (c) keep a hand-rolled spec-conformant fixture for the aggressive path.
     **Recommend filing the sidecar bug upstream** at
     https://github.com/pointmatic/datarefinery and noting the workaround in B.i.

4. **Consumer-side aggressive resolution is validated (via fixture).** A
   hand-rolled record matching the vendor-dep-spec § Aggressive-mode variants —
   `image_path`, `source_record_id`, `variant_index`, `<op>_seed` stamp — resolves
   correctly: `image_path` (relative to `dataset/`) wins over `path`, decodes to
   the expected CHW shape, and a missing sidecar raises (the spec's "refuse to
   consume" failure mode). So the ModelFoundry-owned logic is sound; only the
   real-producer end-to-end is blocked by the 0.17.0 bug.

## Binding pattern locked for B.i / C.f

- **Bind via the library API.** `datarefinery.Instance.load(path)` is the
  entry point (it already gives the stale-instance guard for free). Read
  `manifest.json` / `dataset/*.jsonl` / sidecars directly only where the wrapper
  doesn't expose what we need.
- **Track `datarefinery.recipe.loader.SUPPORTED_SCHEMA_VERSIONS`** for validator
  check 19; hard-error when a bound recipe's `schema_version` exceeds our max.
- **Pixel resolution precedence:** `image_path` (sidecar, relative to `dataset/`)
  when present, else `path` (absolute source path). Decode with Pillow,
  `convert("RGB")`, normalize to float32 `/255.0`, transpose HWC→CHW.
- **Build a sorted `label -> index` map** in the adapter; never assume integer
  labels.
- **Failure modes to enforce** (vendor-dep-spec § Failure modes): missing
  manifest, partial instance (`is_partial` / FAILED marker), missing required
  manifest fields, schema-version too high, missing aggressive sidecar.

## How to re-run

```bash
pyve run python scripts/spike_datarefinery_binding.py
```

Writes only to a self-cleaning temp dir; prints a findings summary; exits 0.
