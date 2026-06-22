# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-2 recipe validator — the enumerated static logical checks (1..21).

`validate(recipe, data_instance, plugin, *, variants_block=None)` runs every
check; it never short-circuits, so a failing recipe surfaces *every* problem in
one pass. Each check produces a `ValidationCheck`; the `ValidationReport`
aggregates them with `passed` (all passed) and `failures` accessors.

Schema and type-shape checks that pydantic already enforces at construction
time are also re-asserted here as a sanity layer so the report is complete
without requiring callers to also surface pydantic errors separately.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from modelfoundry.pipeline.data_binding import (
    DR_SUPPORTED_SCHEMA_VERSIONS,
    DataRefineryInstance,
)
from modelfoundry.plugins.base import Plugin
from modelfoundry.recipe.loader import SUPPORTED_SCHEMA_VERSIONS
from modelfoundry.recipe.models import ModelRecipe
from modelfoundry.recipe.sections import ResolvedSection, resolve_sections

EVALUATION_METRIC_VOCABULARY: frozenset[str] = frozenset(
    {
        "macro_f1",
        "per_class_f1",
        "per_class_precision",
        "per_class_recall",
        "accuracy",
        "confusion_matrix",
        "ece",
        "calibration_curve",
        "predictive_entropy",
    }
)

_FIT_ON_TRAIN_ALLOWED: frozenset[str] = frozenset(
    {"train", "train_inverse_frequency", "effective_number"}
)


class ValidationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    passed: bool
    message: str | None = None
    detail: dict[str, Any] | None = None


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checks: list[ValidationCheck]

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[ValidationCheck]:
        return [c for c in self.checks if not c.passed]


def validate(
    recipe: ModelRecipe,
    data_instance: DataRefineryInstance,
    plugin: Plugin,
    *,
    variants_block: dict[str, Any] | None = None,
) -> ValidationReport:
    # F2 discriminated-union resolution (Story I.c): resolve every op-bearing
    # section once against the plugin registry; checks 3 + 17 each read one
    # failure mode off the shared result (op = discriminator, param_model =
    # variant — see `recipe/sections.py`).
    sections = resolve_sections(recipe, plugin)
    checks = [
        _check_1_schema_version(recipe),
        _check_2_plugin_match(recipe, plugin),
        _check_3_section_ops_registered(sections, plugin),
        _check_4_splits_exist(recipe, data_instance),
        _check_5_fit_on_train(recipe),
        _check_6_early_stopping_monitor(recipe),
        _check_7_search_space_paths(recipe),
        _check_8_baseline_categorical_defaults(recipe),
        _check_9_sampler_pruner(recipe),
        _check_10_n_jobs(recipe),
        _check_11_metric_vocabulary(recipe),
        _check_12_primary_metric_in_metrics(recipe),
        _check_13_baseline_model_id_format(recipe),
        _check_14_expectations_reference_evaluated(recipe),
        _check_15_visualization_mode_declared(recipe),
        _check_16_variants_keys_declared(recipe, variants_block),
        _check_17_op_params_match_spec(sections),
        _check_18_data_binding_compat(recipe, data_instance),
        _check_19_dr_schema_version(data_instance),
        _check_20_device_available(recipe, plugin),
        _check_21_architecture_input_compat(recipe, data_instance),
        _check_22_extensions_keys_claimed(recipe, plugin),
    ]
    return ValidationReport(checks=checks)


# --- Check 1 ---


def _check_1_schema_version(recipe: ModelRecipe) -> ValidationCheck:
    if recipe.schema_version in SUPPORTED_SCHEMA_VERSIONS:
        return _ok(1, "schema_version")
    return _fail(
        1,
        "schema_version",
        f"schema_version {recipe.schema_version} not in supported set "
        f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}",
    )


# --- Check 2 ---


def _check_2_plugin_match(recipe: ModelRecipe, plugin: Plugin) -> ValidationCheck:
    if recipe.plugin == plugin.name:
        return _ok(2, "plugin")
    return _fail(
        2,
        "plugin",
        f"recipe declares plugin {recipe.plugin!r} but discovered plugin is {plugin.name!r}",
        detail={"declared": recipe.plugin, "discovered": plugin.name},
    )


# --- Check 3 ---


def _check_3_section_ops_registered(
    sections: list[ResolvedSection], plugin: Plugin
) -> ValidationCheck:
    # F2 (Story I.c): an op must resolve to a registered variant *for its slot* —
    # an unknown op OR an op registered for a different section (`applies_to`
    # mismatch, e.g. an optimizer op in `Loss`) both fail here.
    failed = [s for s in sections if not s.registered]
    if not failed:
        return _ok(3, "section_ops_registered")
    bad = [(s.label, s.op) for s in failed]
    reasons = [s.registration_error for s in failed]
    return _fail(
        3,
        "section_ops_registered",
        f"ops not registered by plugin {plugin.name!r} for their section: {bad}",
        detail={"unregistered": bad, "reasons": reasons},
    )


# --- Check 4 ---


def _check_4_splits_exist(
    recipe: ModelRecipe, data_instance: DataRefineryInstance
) -> ValidationCheck:
    required = _required_splits(recipe)
    missing = sorted(required - set(data_instance.splits))
    if not missing:
        return _ok(4, "splits_exist")
    return _fail(
        4,
        "splits_exist",
        f"DataRefinery instance is missing splits {missing}; "
        f"available: {list(data_instance.splits)}",
        detail={"required": sorted(required), "available": list(data_instance.splits)},
    )


def _required_splits(recipe: ModelRecipe) -> set[str]:
    required = {"train", *recipe.Evaluation.splits}
    es = recipe.Training.early_stopping
    if es is not None and es.monitor.startswith("val"):
        required.add("val")
    return required


# --- Check 5 ---


def _check_5_fit_on_train(recipe: ModelRecipe) -> ValidationCheck:
    bad: list[tuple[str, Any]] = []

    def walk(node: Any, path: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                sub = f"{path}.{key}" if path else key
                if (
                    key in {"weight_source", "fit_source"}
                    and isinstance(value, str)
                    and value not in _FIT_ON_TRAIN_ALLOWED
                ):
                    bad.append((sub, value))
                walk(value, sub)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(recipe.model_dump())
    if not bad:
        return _ok(5, "fit_on_train")
    return _fail(
        5,
        "fit_on_train",
        f"non-train fit sources (must be one of {sorted(_FIT_ON_TRAIN_ALLOWED)}): {bad}",
        detail={"violations": bad},
    )


# --- Check 6 ---


def _check_6_early_stopping_monitor(recipe: ModelRecipe) -> ValidationCheck:
    es = recipe.Training.early_stopping
    if es is None:
        return _ok(6, "early_stopping_monitor")
    builtins = {"train_loss", "val_loss"}
    available = set(recipe.Evaluation.metrics) | builtins
    if es.monitor in available:
        return _ok(6, "early_stopping_monitor")
    return _fail(
        6,
        "early_stopping_monitor",
        f"monitor {es.monitor!r} not produced; available: {sorted(available)}",
        detail={"monitor": es.monitor, "available": sorted(available)},
    )


# --- Check 7 ---


def _check_7_search_space_paths(recipe: ModelRecipe) -> ValidationCheck:
    if recipe.Optimization is None:
        return _ok(7, "search_space_paths")
    dump = recipe.model_dump()
    bad = [p for p in recipe.Optimization.search_space if _get_path(dump, p) is _MISSING]
    if not bad:
        return _ok(7, "search_space_paths")
    return _fail(
        7,
        "search_space_paths",
        f"search_space keys reference unknown recipe paths: {bad}",
        detail={"unknown": bad},
    )


_MISSING = object()


def _get_path(node: Any, dotted: str) -> Any:
    cursor: Any = node
    for part in dotted.split("."):
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
        else:
            return _MISSING
    return cursor


# --- Check 8 ---


def _check_8_baseline_categorical_defaults(recipe: ModelRecipe) -> ValidationCheck:
    opt = recipe.Optimization
    if opt is None or opt.baseline_trial != "enqueue_recipe_defaults":
        return _ok(8, "baseline_categorical_defaults")
    dump = recipe.model_dump()
    bad: list[tuple[str, Any, list[Any]]] = []
    for path, distribution in opt.search_space.items():
        extra = distribution.model_extra or {}
        if "categorical" in extra:
            choices = list(extra["categorical"])
            current = _get_path(dump, path)
            if current is _MISSING or current not in choices:
                bad.append((path, current if current is not _MISSING else None, choices))
    if not bad:
        return _ok(8, "baseline_categorical_defaults")
    return _fail(
        8,
        "baseline_categorical_defaults",
        f"recipe-default values are not in declared categorical choices: {bad}",
        detail={"violations": bad},
    )


# --- Check 9 ---


def _check_9_sampler_pruner(recipe: ModelRecipe) -> ValidationCheck:
    opt = recipe.Optimization
    if opt is None:
        return _ok(9, "sampler_pruner")
    if opt.sampler in {"tpe", "random", "grid"} and opt.pruner in {"median", "none"}:
        return _ok(9, "sampler_pruner")
    return _fail(
        9,
        "sampler_pruner",
        f"sampler={opt.sampler!r} or pruner={opt.pruner!r} outside the pre-prod set",
    )


# --- Check 10 ---


def _check_10_n_jobs(recipe: ModelRecipe) -> ValidationCheck:
    opt = recipe.Optimization
    if opt is None or opt.n_jobs == 1:
        return _ok(10, "n_jobs")
    return _fail(
        10,
        "n_jobs",
        f"Optimization.n_jobs={opt.n_jobs}; pre-prod requires 1 (QR-3 / FR-2 check 10)",
    )


# --- Check 11 ---


def _check_11_metric_vocabulary(recipe: ModelRecipe) -> ValidationCheck:
    # Plugin-registered metrics: deferred — pre-prod uses the documented core vocabulary.
    bad = [m for m in recipe.Evaluation.metrics if m not in EVALUATION_METRIC_VOCABULARY]
    if not bad:
        return _ok(11, "metric_vocabulary")
    return _fail(
        11,
        "metric_vocabulary",
        f"unknown metrics {bad}; allowed: {sorted(EVALUATION_METRIC_VOCABULARY)}",
        detail={"unknown": bad},
    )


# --- Check 12 ---


def _check_12_primary_metric_in_metrics(recipe: ModelRecipe) -> ValidationCheck:
    if recipe.Evaluation.primary_metric in recipe.Evaluation.metrics:
        return _ok(12, "primary_metric_in_metrics")
    return _fail(
        12,
        "primary_metric_in_metrics",
        f"primary_metric {recipe.Evaluation.primary_metric!r} not in Evaluation.metrics "
        f"{recipe.Evaluation.metrics}",
    )


# --- Check 13 ---


def _check_13_baseline_model_id_format(recipe: ModelRecipe) -> ValidationCheck:
    comp = recipe.Evaluation.comparison
    if comp is None:
        return _ok(13, "baseline_model_id_format")
    mid = comp.baseline_model_id
    if isinstance(mid, str) and mid.strip():
        return _ok(13, "baseline_model_id_format")
    return _fail(
        13,
        "baseline_model_id_format",
        f"baseline_model_id must be a non-empty string, got {mid!r}",
    )


# --- Check 14 ---


def _check_14_expectations_reference_evaluated(recipe: ModelRecipe) -> ValidationCheck:
    bad: list[tuple[str, str, str]] = []
    metrics = set(recipe.Evaluation.metrics)
    splits = set(recipe.Evaluation.splits)
    for exp in recipe.OutputExpectations:
        if exp.metric not in metrics:
            bad.append(("metric not in Evaluation.metrics", exp.metric, exp.split))
        elif exp.split not in splits:
            bad.append(("split not in Evaluation.splits", exp.metric, exp.split))
    if not bad:
        return _ok(14, "expectations_reference_evaluated")
    return _fail(
        14,
        "expectations_reference_evaluated",
        f"OutputExpectations reference unproduced metric/split pairs: {bad}",
        detail={"violations": bad},
    )


# --- Check 15 ---


def _check_15_visualization_mode_declared(recipe: ModelRecipe) -> ValidationCheck:
    # The pydantic Literal default guarantees `mode` is always set; this is a
    # belt-and-braces report entry so the validator surface is complete.
    bad = [
        i
        for i, viz in enumerate(recipe.Visualizations)
        if viz.mode not in {"reporting", "interactive"}
    ]
    if not bad:
        return _ok(15, "visualization_mode_declared")
    return _fail(
        15,
        "visualization_mode_declared",
        f"Visualizations at indices {bad} missing or have unknown mode",
    )


# --- Check 16 ---


def _check_16_variants_keys_declared(
    recipe: ModelRecipe, variants_block: dict[str, Any] | None
) -> ValidationCheck:
    if variants_block is None:
        return ValidationCheck(
            id=16,
            name="variants_keys_declared",
            passed=True,
            message="variants_block not supplied to validate(); skipping check",
        )
    dump = recipe.model_dump()
    bad: list[tuple[str, str]] = []
    for vname, overlay in variants_block.items():
        if not isinstance(overlay, dict):
            bad.append((vname, "overlay is not a mapping"))
            continue
        for section_name in overlay:
            if section_name not in dump:
                bad.append((vname, f"section {section_name!r} not declared in recipe"))
    if not bad:
        return _ok(16, "variants_keys_declared")
    return _fail(
        16,
        "variants_keys_declared",
        f"variants reference undeclared sections/keys: {bad}",
        detail={"violations": bad},
    )


# --- Check 17 ---


def _check_17_op_params_match_spec(sections: list[ResolvedSection]) -> ValidationCheck:
    # F2 (Story I.c): for sections whose op resolved to its slot, the authored
    # params must validate against the variant's `param_model` (check 3 owns the
    # unregistered/wrong-slot reporting, so those are skipped here).
    bad = [
        (s.label, s.op, s.param_error)
        for s in sections
        if s.registered and s.param_error is not None
    ]
    if not bad:
        return _ok(17, "op_params_match_spec")
    return _fail(
        17,
        "op_params_match_spec",
        f"op param validation failures: {[(s, o) for s, o, _ in bad]}",
        detail={"errors": bad},
    )


# --- Check 18 ---


def _check_18_data_binding_compat(
    recipe: ModelRecipe, data_instance: DataRefineryInstance
) -> ValidationCheck:
    issues: list[str] = []
    required = _required_splits(recipe)
    if not data_instance.instance_provides_splits(sorted(required)):
        issues.append(
            f"required splits {sorted(required)} not all present in instance "
            f"{list(data_instance.splits)}"
        )
    declared_nc = (
        recipe.Architecture.get("num_classes") if isinstance(recipe.Architecture, dict) else None
    )
    if declared_nc is not None:
        try:
            actual = data_instance.instance_num_classes()
            if int(declared_nc) != actual:
                issues.append(
                    f"Architecture.num_classes={declared_nc} but DataRefinery "
                    f"instance has {actual} classes"
                )
        except Exception as exc:
            issues.append(f"could not enumerate instance classes: {exc}")
    if not data_instance.label_schema.get("field"):
        issues.append("DataRefinery instance label_schema has no 'field' — cannot bind labels")
    if not issues:
        return _ok(18, "data_binding_compat")
    return _fail(
        18,
        "data_binding_compat",
        "; ".join(issues),
        detail={"issues": issues},
    )


# --- Check 19 ---


def _check_19_dr_schema_version(data_instance: DataRefineryInstance) -> ValidationCheck:
    sv = data_instance.instance_schema_version()
    max_supported = max(DR_SUPPORTED_SCHEMA_VERSIONS)
    if sv <= max_supported:
        return _ok(19, "dr_schema_version_coordination")
    return _fail(
        19,
        "dr_schema_version_coordination",
        f"bound DataRefinery instance recipe schema_version {sv} > "
        f"ModelFoundry's known max {max_supported}",
        detail={"got": sv, "max_supported": max_supported},
    )


# --- Check 20 ---


def _check_20_device_available(recipe: ModelRecipe, plugin: Plugin) -> ValidationCheck:
    """`Training.device` is `"auto"` or an accelerator the plugin reports available."""
    device = recipe.Training.device
    if device == "auto":
        return _ok(20, "device_available")

    report = plugin.health_check()
    accelerators = _extract_accelerators(report)
    if accelerators is None:
        return ValidationCheck(
            id=20,
            name="device_available",
            passed=True,
            message=(
                f"plugin {plugin.name!r} health_check did not expose 'accelerators'; "
                f"skipping device-availability check for {device!r}"
            ),
        )
    if device in accelerators:
        return _ok(20, "device_available")
    return _fail(
        20,
        "device_available",
        f"Training.device={device!r} is not in plugin {plugin.name!r}'s "
        f"available accelerators {sorted(accelerators)}",
        detail={"requested": device, "available": sorted(accelerators)},
    )


def _extract_accelerators(report: Any) -> set[str] | None:
    """Pull an `accelerators` collection from a plugin's `health_check` report.

    Tolerant of dict-shaped or attribute-shaped reports; returns `None` when no
    `accelerators` field is exposed so the caller can skip-with-message rather
    than fail an honest plugin that simply hasn't wired the field yet.
    """
    if report is None:
        return None
    if isinstance(report, dict):
        accelerators = report.get("accelerators")
    else:
        accelerators = getattr(report, "accelerators", None)
    if accelerators is None:
        return None
    return {str(a) for a in accelerators}


# --- Check 21 ---


def _check_21_architecture_input_compat(
    recipe: ModelRecipe, data_instance: DataRefineryInstance
) -> ValidationCheck:
    """The bound instance's produced input must satisfy the architecture's contract.

    Two independent guards (Story H.j.3), each a member of the same data↔model
    interface family the H.a normalization-units bug belonged to:

    * **Input shape** — a pretrained `Encoder` has a *fixed* input resolution +
      channel count; the bound DataRefinery instance must produce matching images.
      The requirement is introspected from the encoder config, so this guard needs
      `[huggingface]`; per R1.4 `validate()` must succeed without the extra, so it
      **no-ops when `transformers` is absent** (a materialize attempt fails with the
      extras pointer regardless).
    * **Normalization scale** — the PyTorch adapter applies fitted `normalize` stats
      in **0-255 pixel units** (Story H.a). Fitted means that look `[0,1]`-scale are
      a units mismatch. This guard is encoder-independent and torch/transformers-free,
      so it runs for **every** recipe — closing the H.c-filed sanity-check follow-up.
    """
    issues: list[str] = []
    issues += _encoder_shape_issues(recipe, data_instance)
    issues += _normalization_scale_issues(data_instance)
    if not issues:
        return _ok(21, "architecture_input_compat")
    return _fail(21, "architecture_input_compat", "; ".join(issues), detail={"issues": issues})


def _encoder_op(recipe: ModelRecipe) -> dict[str, Any] | None:
    """The `Encoder` layer dict in an explicit-layers Architecture, or `None`."""
    arch = recipe.Architecture
    if not isinstance(arch, dict):
        return None
    layers = arch.get("layers")
    if not isinstance(layers, list):
        return None
    for layer in layers:
        if isinstance(layer, dict) and layer.get("op") == "Encoder":
            return layer
    return None


def _instance_image_hwc(data_instance: DataRefineryInstance) -> tuple[int, int, int] | None:
    schema = getattr(data_instance, "record_schema", None) or {}
    image = schema.get("image") if isinstance(schema, dict) else None
    shape = image.get("shape") if isinstance(image, dict) else None
    if not isinstance(shape, (list, tuple)) or len(shape) != 3:
        return None
    try:
        return int(shape[0]), int(shape[1]), int(shape[2])
    except (TypeError, ValueError):
        return None


def _encoder_shape_issues(recipe: ModelRecipe, data_instance: DataRefineryInstance) -> list[str]:
    encoder = _encoder_op(recipe)
    if encoder is None:
        return []
    # R1.4: validate() must work without [huggingface]; the requirement is
    # encoder-introspected, so skip the comparison when transformers is absent.
    import importlib.util

    if importlib.util.find_spec("transformers") is None:
        return []
    hwc = _instance_image_hwc(data_instance)
    if hwc is None:
        return []
    model_id = encoder.get("id")
    if not isinstance(model_id, str):
        return []
    try:
        from transformers import AutoConfig  # type: ignore[import-not-found, unused-ignore]

        cfg = AutoConfig.from_pretrained(model_id, local_files_only=True)
    except Exception:
        # Encoder not in the offline warm cache / not introspectable — don't fail
        # validate on an introspection error; materialize is the hard gate (R1.5).
        return []
    size = getattr(cfg, "image_size", None)
    channels = getattr(cfg, "num_channels", None)
    if not isinstance(size, int) or not isinstance(channels, int):
        return []
    h, w, c = hwc
    if (h, w, c) != (size, size, channels):
        return [
            f"bound instance produces {h}x{w}x{c} images but Encoder.id={model_id!r} requires "
            f"{size}x{size}x{channels} — re-materialize the DataRefinery instance at the encoder's "
            f"resolution (DataRefinery owns data prep, FR-6)"
        ]
    return []


def _normalization_scale_issues(data_instance: DataRefineryInstance) -> list[str]:
    fitted = getattr(data_instance, "fitted_statistics", None)
    dr_recipe = getattr(data_instance, "recipe", None)
    transformations = getattr(dr_recipe, "Transformations", None)
    if fitted is None or not transformations:
        return []
    issues: list[str] = []
    for op in transformations:
        if getattr(op, "op", None) != "normalize":
            continue
        name = getattr(op, "name", None)
        if not isinstance(name, str):
            continue
        means = _read_fitted_means(fitted, name)
        # The adapter applies stats in 0-255 pixel units (H.a). All-channel means
        # at or below 1.0 are the [0,1]-scale signature of a units mismatch (a
        # natural image's per-channel mean is far above 1 in 0-255 space).
        if means and all(m <= 1.0 for m in means):
            issues.append(
                f"DataRefinery normalize op {name!r} has fitted means {means} that look "
                f"[0,1]-scale, but the PyTorch adapter applies normalization in 0-255 pixel units "
                f"(Story H.a) — likely a units mismatch; re-fit the DataRefinery instance with "
                f"0-255-scale statistics"
            )
    return issues


def _read_fitted_means(fitted: Any, op_name: str) -> list[float]:
    try:
        table = fitted.get_vector(op_name, "mean")
        return [float(v) for v in table.column("value").to_pylist()]
    except Exception:
        return []


# --- Check 22 ---


def _check_22_extensions_keys_claimed(recipe: ModelRecipe, plugin: Plugin) -> ValidationCheck:
    """Warn (non-fatally) on `extensions:` keys no installed plugin claims (F3, I.d).

    Extensions are a sanctioned space for bounded experimentation, so an unclaimed
    key is a *heads-up*, not a failure — the check passes with a message (the
    skip-with-message pattern of checks 16/20). `Plugin.extension_keys` is read
    tolerantly so an honest plugin that hasn't wired the attribute claims none.
    """
    extensions = recipe.extensions
    if not extensions:
        return _ok(22, "extensions_keys_claimed")
    claimed = {str(k) for k in getattr(plugin, "extension_keys", ()) or ()}
    unclaimed = sorted(k for k in extensions if k not in claimed)
    if not unclaimed:
        return _ok(22, "extensions_keys_claimed")
    return ValidationCheck(
        id=22,
        name="extensions_keys_claimed",
        passed=True,  # non-fatal: extensions are for experimentation
        message=(
            f"extensions keys not claimed by plugin {plugin.name!r}: {unclaimed} "
            f"(declarative params only — they enter cache identity but no plugin reads them)"
        ),
        detail={"unclaimed": unclaimed, "claimed": sorted(claimed)},
    )


# --- helpers ---


def _ok(check_id: int, name: str) -> ValidationCheck:
    return ValidationCheck(id=check_id, name=name, passed=True)


def _fail(
    check_id: int,
    name: str,
    message: str,
    *,
    detail: dict[str, Any] | None = None,
) -> ValidationCheck:
    return ValidationCheck(id=check_id, name=name, passed=False, message=message, detail=detail)
