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

**Finding the instance.** ModelFoundry does **not** re-derive DataRefinery's
cache identity — that is forbidden by the vendor-dependency-spec § "Resolving a
materialized instance" (a hand-rolled key silently breaks after any canonical-
bytes change). It calls DataRefinery's blessed resolver,
`datarefinery.resolve_instance(recipe_path, cache_root=…, seed=…, overlays=…)`,
which returns a `StatusReport` (`cache_status` hit/miss/corrupt + `instance_path`
+ `manifest`). The resolver hashes the recipe's declared inputs, so the source
inputs must be present on the resolving host (vendor-spec § Host portability).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import datarefinery as _dr
import datarefinery.recipe.loader as _dr_loader

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
    cache_root = Path(
        data_spec.cache_root if data_spec.cache_root is not None else runtime_config.data_cache_root
    ).resolve()

    report = _resolve_via_library(recipe_path, cache_root, data_spec.seed, data_spec.variant)
    instance_path = report.instance_path
    if report.cache_status == "miss":
        raise DataBindingError(
            f"no materialized DataRefinery instance for recipe {recipe_path}; "
            f"expected at {instance_path} — run `datarefinery materialize` first",
            detail={"recipe": str(recipe_path), "expected": str(instance_path)},
        )
    if report.cache_status == "corrupt":
        raise DataBindingError(
            f"DataRefinery instance at {instance_path} is corrupt: {report.note}",
            detail={"instance": str(instance_path), "note": report.note},
        )

    _refuse_partial(instance_path)
    dr_instance = _load_via_library(instance_path)
    _gate_dr_schema_version(dr_instance.recipe, recipe_path)
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


def _resolve_via_library(
    recipe_path: Path, cache_root: Path, seed: int | None, variant: str | None
) -> Any:
    """Resolve the instance via DataRefinery's blessed `resolve_instance`.

    No cache-key re-derivation (vendor-dep-spec § "Resolving a materialized
    instance"). `resolve_instance` composes `DataRefinery.status()` and hashes the
    recipe's declared inputs, so the source inputs must be present on this host.
    """
    try:
        # DataRefinery v0.23 widened its boundary kwarg `variant: str` to an
        # ordered `overlays: Sequence[str]` (Story I.j.1 RC-B interim bridge).
        # ModelFoundry's own single-`variant` surface is unchanged here; I.j.2
        # renames it to a real `overlays` list that flows straight through.
        return _dr.resolve_instance(
            recipe_path,
            cache_root=cache_root,
            seed=seed,
            overlays=[variant] if variant else None,
        )
    except Exception as exc:
        raise DataBindingError(
            f"could not resolve DataRefinery instance for recipe {recipe_path}: {exc}",
            detail={"recipe": str(recipe_path)},
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
