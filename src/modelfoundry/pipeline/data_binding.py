# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-6 DataRefinery instance binding.

Resolves the recipe's `Data:` block to a materialized DataRefinery instance and
returns a `DataRefineryInstance` wrapper carrying the path, manifest, recipe,
splits, label schema, and record schema. Implements the failure modes called
out by the vendor-dep-spec § "Failure modes ModelFoundry SHOULD detect":
instance not on disk, partial (`FAILED` marker or `manifest.is_partial`),
missing required manifest fields, schema-version too high, and aggressive
variant sidecar missing.

**A.c spike outcome locks the pattern.** ModelFoundry binds via DataRefinery's
library API (`datarefinery.Instance.load`) — it self-verifies the manifest's
`recipe_hash` against the persisted `recipe.json` (the stale-instance guard the
vendor-dep-spec asks consumers to enforce). The pre-production binding is loose
per `project-essentials.md` § Loose-coupled DataRefinery binding.

**Finding the instance.** ModelFoundry doesn't re-run DataRefinery's input
hasher (that would require reading source bytes); instead, it computes the
DataRefinery recipe's canonical hash from the recipe YAML and scans
`<data-cache-root>/instances/<recipe-hash16>/` for matching seed directories.
Exactly one match is required; zero raises "not materialized", multiple raises
"ambiguous — re-materialize".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import datarefinery as _dr
import datarefinery.recipe.canonical as _dr_canonical
import datarefinery.recipe.loader as _dr_loader
import datarefinery.recipe.variants as _dr_variants

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import DataBindingError
from modelfoundry.recipe.models import DataSpec

# DataRefinery's set of accepted recipe schema versions; we refuse anything higher.
DR_SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset(_dr_loader.SUPPORTED_SCHEMA_VERSIONS)


@dataclass(frozen=True)
class DataRefineryInstance:
    """ModelFoundry's view of a bound DataRefinery instance."""

    path: Path
    manifest: Any  # datarefinery.pipeline.manifest.Manifest
    recipe: Any  # datarefinery.recipe.models.Recipe
    splits: tuple[str, ...]
    label_schema: dict[str, Any]
    record_schema: dict[str, Any]
    # datarefinery FittedStatistics view — C.f reads the fit-on-train normalize stats.
    fitted_statistics: Any = None

    def instance_provides_splits(self, splits: list[str]) -> bool:
        """True iff every requested split is present in the materialized instance."""
        return all(s in self.splits for s in splits)

    def instance_schema_version(self) -> int:
        """The DataRefinery recipe `schema_version` of the bound instance."""
        return int(self.recipe.schema_version)

    def instance_num_classes(self) -> int:
        """Unique non-null label count, scanned from the train split.

        DataRefinery doesn't enumerate the class inventory in its manifest (the
        labels are derived from data), so we read `dataset/train.jsonl` and count
        distinct values of the recipe-declared label field.
        """
        train_jsonl = self.path / "dataset" / "train.jsonl"
        if not train_jsonl.is_file():
            raise DataBindingError(
                f"cannot enumerate classes: no train split at {train_jsonl}",
                detail={"train_jsonl": str(train_jsonl)},
            )
        label_field = self.label_schema.get("field")
        if not label_field:
            raise DataBindingError(
                "cannot enumerate classes: DataRefinery recipe's Labels.field is empty"
            )
        labels: set[Any] = set()
        for line in train_jsonl.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            value = record.get(label_field)
            if value is not None:
                labels.add(value)
        return len(labels)


def resolve_data_instance(
    data_spec: DataSpec, runtime_config: RuntimeConfig
) -> DataRefineryInstance:
    """Resolve `data_spec` to a `DataRefineryInstance`; raise `DataBindingError` on any failure."""
    recipe_path = _resolve_recipe_path(data_spec)
    dr_recipe = _load_dr_recipe(recipe_path, data_spec.variant)
    _gate_dr_schema_version(dr_recipe, recipe_path)

    recipe_hash = hashlib.sha256(_dr_canonical.to_canonical_bytes(dr_recipe)).hexdigest()
    seed = data_spec.seed if data_spec.seed is not None else int(dr_recipe.seed)
    cache_root = (
        data_spec.cache_root
        if data_spec.cache_root is not None
        else runtime_config.data_cache_root
    )
    cache_root = Path(cache_root).resolve()

    instance_path = _find_instance(cache_root, recipe_hash[:16], seed, recipe_path)
    _refuse_partial(instance_path)
    dr_instance = _load_via_library(instance_path)
    _verify_aggressive_sidecars(instance_path)

    return DataRefineryInstance(
        path=instance_path,
        manifest=dr_instance.manifest,
        recipe=dr_instance.recipe,
        splits=tuple(dr_instance.manifest.record_counts.keys()),
        label_schema=dr_instance.recipe.Labels.model_dump(),
        record_schema={
            k: v.model_dump() for k, v in dr_instance.recipe.Output.record_schema.items()
        },
        fitted_statistics=getattr(dr_instance, "fitted_statistics", None),
    )


def _resolve_recipe_path(data_spec: DataSpec) -> Path:
    path = data_spec.recipe
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.is_file():
        raise DataBindingError(
            f"DataRefinery recipe not found: {path}", detail={"recipe": str(path)}
        )
    return path


def _load_dr_recipe(recipe_path: Path, variant: str | None) -> Any:
    try:
        recipe = _dr_loader.load(recipe_path)
    except Exception as exc:
        raise DataBindingError(
            f"could not load DataRefinery recipe {recipe_path}: {exc}",
            detail={"recipe": str(recipe_path)},
        ) from exc
    if variant is None:
        return recipe
    try:
        return _dr_variants.apply_variant(recipe, variant)
    except Exception as exc:
        raise DataBindingError(
            f"could not apply variant {variant!r} to DataRefinery recipe {recipe_path}: {exc}",
            detail={"recipe": str(recipe_path), "variant": variant},
        ) from exc


def _gate_dr_schema_version(dr_recipe: Any, recipe_path: Path) -> None:
    sv = int(dr_recipe.schema_version)
    max_supported = max(DR_SUPPORTED_SCHEMA_VERSIONS)
    if sv > max_supported:
        raise DataBindingError(
            f"DataRefinery recipe {recipe_path} declares schema_version {sv}, "
            f"higher than ModelFoundry's known max ({max_supported}); upgrade ml-modelfoundry",
            detail={"got": sv, "max_supported": max_supported},
        )


def _find_instance(
    cache_root: Path, recipe_hash16: str, seed: int, recipe_path: Path
) -> Path:
    bucket = cache_root / "instances" / recipe_hash16
    if not bucket.is_dir():
        raise DataBindingError(
            f"no materialized DataRefinery instance for recipe {recipe_path}; "
            f"expected under {bucket} — run `datarefinery materialize` first",
            detail={"recipe": str(recipe_path), "expected_bucket": str(bucket)},
        )
    matches: list[Path] = []
    for input_dir in sorted(bucket.iterdir()):
        if not input_dir.is_dir():
            continue
        seed_dir = input_dir / str(seed)
        if seed_dir.is_dir():
            matches.append(seed_dir)
    if not matches:
        raise DataBindingError(
            f"no DataRefinery instance found under {bucket} with seed={seed}",
            detail={"recipe_hash16": recipe_hash16, "seed": seed},
        )
    if len(matches) > 1:
        raise DataBindingError(
            f"ambiguous bind: multiple DataRefinery instances match recipe+seed; "
            f"input bytes have changed across runs — re-materialize. Candidates: "
            f"{[str(m) for m in matches]}",
            detail={"matches": [str(m) for m in matches]},
        )
    return matches[0]


def _refuse_partial(instance_path: Path) -> None:
    if (instance_path / "FAILED").exists():
        raise DataBindingError(
            f"DataRefinery instance at {instance_path} carries a FAILED marker; "
            f"re-materialize before binding",
            detail={"instance": str(instance_path)},
        )


def _load_via_library(instance_path: Path) -> Any:
    try:
        instance = _dr.Instance.load(instance_path)
    except Exception as exc:
        raise DataBindingError(
            f"failed to load DataRefinery instance at {instance_path}: {exc}",
            detail={"instance": str(instance_path)},
        ) from exc
    if instance.is_partial:
        raise DataBindingError(
            f"DataRefinery instance at {instance_path} is marked partial in its manifest",
            detail={"instance": str(instance_path)},
        )
    return instance


def _verify_aggressive_sidecars(instance_path: Path) -> None:
    dataset_dir = instance_path / "dataset"
    if not dataset_dir.is_dir():
        return
    for jsonl_path in sorted(dataset_dir.glob("*.jsonl")):
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            record = json.loads(line)
            relative = record.get("image_path")
            if not relative:
                continue
            sidecar = dataset_dir / relative
            if not sidecar.is_file():
                raise DataBindingError(
                    f"aggressive variant sidecar missing: {sidecar} "
                    f"(referenced by {jsonl_path.name})",
                    detail={
                        "sidecar": str(sidecar),
                        "record_id": record.get("record_id"),
                    },
                )
