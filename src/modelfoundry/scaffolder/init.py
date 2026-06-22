# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Deterministic recipe scaffolder (FR-21, Story D.i).

`scaffold_recipe` resolves the bound DataRefinery instance, reads its shape
(class count, input channels, available splits), and writes a baseline
ModelFoundry recipe shaped to the dataset — a ready-to-edit starting point, not
an optimized model. The PyTorch baseline is a `resnet20` image classifier (the
project's documented baseline, C.r); the sklearn baseline is an `mlp_classifier`.

The recipe is stamped with the Apache-2.0 / Pointmatic header as a YAML comment.
`scaffold_recipe` is deterministic: the same bound instance always yields the
same recipe bytes.

**Signature note.** FR-21's `scaffold_recipe(recipe_path, datarefinery_recipe_path,
*, plugin, force)` is extended with a keyword `config` because resolving the
DataRefinery instance needs the data-cache root; the CLI threads its
`RuntimeConfig`. `config=None` falls back to `RuntimeConfig()` (env / defaults).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import RecipeError
from modelfoundry.pipeline.data_binding import resolve_data_instance
from modelfoundry.recipe.models import DataSpec

_HEADER = (
    "# Copyright (c) 2026 Pointmatic\n"
    "# SPDX-License-Identifier: Apache-2.0\n"
    "#\n"
    "# Baseline ModelFoundry recipe scaffolded by `modelfoundry init` (FR-21).\n"
    "# A ready-to-edit starting point shaped to the bound DataRefinery instance —\n"
    "# tune the architecture, optimizer, training budget, and expectations to taste.\n"
)

_DEFAULT_SEED = 0
_BASELINE_EPOCHS = 30
_BASELINE_BATCH_SIZE = 64


def scaffold_recipe(
    recipe_path: str | Path,
    datarefinery_recipe_path: str | Path,
    *,
    plugin: str = "pytorch",
    force: bool = False,
    config: RuntimeConfig | None = None,
) -> Path:
    """Write a baseline recipe for `datarefinery_recipe_path` to `recipe_path`; return it."""
    recipe_path = Path(recipe_path)
    if recipe_path.exists() and not force:
        raise RecipeError(
            f"refusing to overwrite existing recipe {recipe_path}; pass --force to replace it",
            recipe_path=recipe_path,
        )

    config = config or RuntimeConfig()
    data_recipe = Path(datarefinery_recipe_path)
    instance = resolve_data_instance(DataSpec(recipe=data_recipe), config)

    num_classes = instance.instance_num_classes()
    splits = list(instance.splits)
    eval_split = "test" if "test" in splits else ("val" if "val" in splits else splits[0])
    has_val = "val" in splits

    recipe = _baseline_recipe(
        plugin=plugin,
        data_recipe=data_recipe,
        num_classes=num_classes,
        in_channels=_in_channels(instance),
        eval_split=eval_split,
        has_val=has_val,
    )

    recipe_path.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(recipe, sort_keys=False)
    recipe_path.write_text(_HEADER + "\n" + body, encoding="utf-8")
    return recipe_path


def _baseline_recipe(
    *,
    plugin: str,
    data_recipe: Path,
    num_classes: int,
    in_channels: int,
    eval_split: str,
    has_val: bool,
) -> dict[str, Any]:
    # No-implicit-defaults (Story I.e.2): the scaffolder is the value-emitter — it
    # writes every behavior-affecting field explicitly (= the current model
    # defaults) so the recipe text is self-contained and audit-visible, and the
    # interpreting code supplies nothing implicitly.
    training: dict[str, Any] = {
        "max_epochs": _BASELINE_EPOCHS,
        "batch_size": _BASELINE_BATCH_SIZE,
        "device": "auto",
        "precision": "fp32",
        "checkpoint_cadence": 1,
    }
    if has_val:
        # `val_loss` is the validator-recognized per-epoch monitor (FR-2 check 6);
        # `val_accuracy` is produced by the trainer but not in the validator's
        # produced-metric vocabulary, so it would fail static validation.
        training["early_stopping"] = {"monitor": "val_loss", "mode": "min", "patience": 5}

    recipe: dict[str, Any] = {
        "schema_version": 1,
        "plugin": plugin,
        "seed": _DEFAULT_SEED,
        "Data": {"recipe": str(data_recipe)},
        "Architecture": _architecture(plugin, num_classes, in_channels),
        "Loss": {"op": "cross_entropy"},
        "Optimizer": {"op": "adamw", "learning_rate": 0.001},
        "Training": training,
        "Evaluation": {
            "splits": [eval_split],
            "primary_metric": "accuracy",
            # Imbalance-aware by default (R3.1): per-class precision/recall/F1 and
            # the confusion matrix surface minority-class performance, not accuracy
            # alone. Trim to taste for a balanced dataset.
            "metrics": [
                "accuracy",
                "macro_f1",
                "per_class_f1",
                "per_class_precision",
                "per_class_recall",
                "confusion_matrix",
            ],
            "calibration_bins": 10,
        },
        # A modest better-than-chance baseline assertion; tighten it once you have
        # a trained model. `round(...)` keeps the recipe bytes deterministic.
        "OutputExpectations": [
            {
                "metric": "accuracy",
                "split": eval_split,
                "op": "gte",
                "value": round(1.0 / num_classes, 4),
            }
        ],
    }
    return recipe


def _architecture(plugin: str, num_classes: int, in_channels: int) -> dict[str, Any]:
    if plugin == "sklearn":
        return {"type": "mlp_classifier", "hidden_layer_sizes": [128], "max_iter": 200}
    return {"type": "resnet20", "num_classes": num_classes, "in_channels": in_channels}


def _in_channels(instance: Any, default: int = 3) -> int:
    """Channel count from the DataRefinery record schema's image-field shape (HWC).

    The image record-schema entry declares `shape: [H, W, C]`; the last axis is
    the channel count. Falls back to `default` (RGB) when no such field is found.
    """
    for field_schema in instance.record_schema.values():
        shape = field_schema.get("shape") if isinstance(field_schema, dict) else None
        if isinstance(shape, list | tuple) and len(shape) >= 3:
            return int(shape[-1])
    return default
