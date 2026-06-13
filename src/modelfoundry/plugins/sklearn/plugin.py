# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""sklearn `MLPClassifier` baseline plugin (FR-24, Story C.m).

A real, materializable baseline — the brief's "ceiling baseline" — implementing
the `Plugin` Protocol over `sklearn.neural_network.MLPClassifier`: `build_model`,
`run_training`, `run_evaluation`, `save_model` / `load_model`,
`predict` / `predict_proba`. The feature path (`sklearn.data.feature_matrix`)
reuses the PyTorch C.f normalization + label scan, so its features and class
ordering match the PyTorch path. Metrics come from the shared
`sklearn.metrics` vocabulary.

`run_optimization` and `render_visualization` raise `NotImplementedError` — the
baseline is a fixed comparison model with no HPO or per-plugin visualization.

**Import-safe without heavy extras.** This module ships in ModelFoundry's
entry-point table and is loaded by `discover_plugins()` on every install, so
`sklearn` / `joblib` / the torch-backed feature path import lazily inside the
methods, never at module top.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, ValidationError

from modelfoundry._version import __version__
from modelfoundry.core.errors import InstanceError, PluginError
from modelfoundry.pipeline.data_binding import DataRefineryInstance
from modelfoundry.pipeline.seeding import derive_seed
from modelfoundry.plugins.base import OperationSpec, Plugin
from modelfoundry.plugins.sklearn import metrics
from modelfoundry.recipe.models import EvaluationSpec, ModelRecipe, OptimizationSpec, TrainingSpec

_U32 = (1 << 32) - 1
_ESTIMATOR_FILE = "estimator.joblib"


class MLPClassifierParams(BaseModel):
    """Params for the `mlp_classifier` baseline architecture op."""

    model_config = ConfigDict(extra="forbid")

    num_classes: int
    hidden_layer_sizes: tuple[int, ...] = (100,)
    activation: str = "relu"
    alpha: float = 1e-4
    max_iter: int = 200
    learning_rate_init: float = 1e-3


#: The sklearn baseline's architecture op.
ARCHITECTURE_OPERATIONS: dict[str, OperationSpec] = {
    "mlp_classifier": OperationSpec(
        op_name="mlp_classifier", param_model=MLPClassifierParams, applies_to="architecture"
    )
}


class SklearnHealthReport(BaseModel):
    """Result of `SklearnPlugin.health_check`."""

    model_config = ConfigDict(extra="forbid")

    plugin: str
    available: bool
    sklearn_version: str | None
    numpy_version: str | None
    # CPU-only; exposed in `Training.device` terms so validator check 20 reads it.
    accelerators: tuple[str, ...] = ("cpu",)


@dataclass(frozen=True)
class SklearnTrainingResult:
    classes: list[str]
    n_iter: int
    final_loss: float
    weights_path: Path
    history_path: Path


@dataclass(frozen=True)
class SklearnEvaluationResult:
    metrics: dict[str, dict[str, Any]]
    metrics_path: Path
    predictions_path: Path
    confusion_matrix_path: Path | None
    calibration_path: Path | None
    warnings: list[str] = field(default_factory=list)


class SklearnPlugin:
    """The `sklearn` baseline plugin."""

    name: str = "sklearn"
    version: str = __version__

    def __init__(self) -> None:
        self.operations: dict[str, OperationSpec] = dict(ARCHITECTURE_OPERATIONS)

    def health_check(self) -> SklearnHealthReport:
        sklearn_version = _safe_version("scikit-learn")
        return SklearnHealthReport(
            plugin=self.name,
            available=sklearn_version is not None,
            sklearn_version=sklearn_version,
            numpy_version=_safe_version("numpy"),
        )

    def build_model(self, arch: dict[str, Any]) -> Any:
        params = _validate_architecture(arch)
        from sklearn.neural_network import MLPClassifier  # type: ignore[import-untyped]

        return MLPClassifier(
            hidden_layer_sizes=params.hidden_layer_sizes,
            activation=params.activation,
            alpha=params.alpha,
            max_iter=params.max_iter,
            learning_rate_init=params.learning_rate_init,
        )

    def run_training(
        self,
        training: TrainingSpec,
        model: Any,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
    ) -> SklearnTrainingResult:
        from modelfoundry.plugins.sklearn.data import feature_matrix

        x, y, classes = feature_matrix(data, "train")
        # Determinism: seed the estimator's RNG from the master seed (32-bit).
        model.set_params(random_state=derive_seed(seed, "weight_init") & _U32)
        model.fit(x, y)

        model_dir = temp_dir / "model"
        self.save_model(model, model_dir)

        training_dir = temp_dir / "training"
        training_dir.mkdir(parents=True, exist_ok=True)
        loss_curve = [float(v) for v in getattr(model, "loss_curve_", [])]
        history_path = training_dir / "history.parquet"
        _write_history(loss_curve, history_path)

        return SklearnTrainingResult(
            classes=classes,
            n_iter=int(getattr(model, "n_iter_", len(loss_curve))),
            final_loss=loss_curve[-1] if loss_curve else float("nan"),
            weights_path=model_dir / _ESTIMATOR_FILE,
            history_path=history_path,
        )

    def run_evaluation(
        self,
        evaluation: EvaluationSpec,
        model: Any,
        data: DataRefineryInstance,
        temp_dir: Path,
    ) -> SklearnEvaluationResult:
        from modelfoundry.plugins.sklearn.data import feature_matrix

        eval_dir = temp_dir / "evaluation"
        eval_dir.mkdir(parents=True, exist_ok=True)
        requested = set(evaluation.metrics)

        out_metrics: dict[str, dict[str, Any]] = {}
        prediction_rows: list[dict[str, Any]] = []
        confusion: dict[str, np.ndarray] = {}
        calibration_rows: list[dict[str, Any]] = []
        classes: list[str] = []

        for split in evaluation.splits:
            x, y, classes = feature_matrix(data, split)
            proba = np.asarray(model.predict_proba(x))
            preds = proba.argmax(axis=1)
            labels = list(range(len(classes)))

            out_metrics[split] = _split_metrics(
                requested, y, preds, proba, labels, evaluation.calibration_bins
            )
            prediction_rows.extend(_prediction_rows(split, y, preds, proba, classes))

            if "confusion_matrix" in requested:
                cm = metrics.confusion_matrix(y, preds, labels=labels)
                out_metrics[split]["confusion_matrix"] = cm.tolist()
                confusion[split] = cm
            if "calibration_curve" in requested:
                curve = metrics.calibration_curve(
                    proba.max(axis=1),
                    (preds == y).astype(float),
                    n_bins=evaluation.calibration_bins,
                )
                out_metrics[split]["calibration_curve"] = curve
                calibration_rows.extend(_calibration_rows(split, curve))

        warnings: list[str] = []
        if evaluation.comparison is not None:
            warnings.append(
                f"baseline comparison against {evaluation.comparison.baseline_model_id!r} "
                f"is not resolvable from the sklearn baseline; skipped"
            )

        metrics_path = eval_dir / "metrics.json"
        metrics_path.write_text(json.dumps(out_metrics, indent=2, sort_keys=True), encoding="utf-8")
        predictions_path = eval_dir / "predictions.parquet"
        _write_predictions(prediction_rows, classes, predictions_path)

        confusion_path = None
        if confusion:
            confusion_path = eval_dir / "confusion_matrix.npz"
            np.savez(confusion_path, **confusion)  # type: ignore[arg-type]
        calibration_path = None
        if calibration_rows:
            calibration_path = eval_dir / "calibration.parquet"
            _write_calibration(calibration_rows, calibration_path)

        return SklearnEvaluationResult(
            metrics=out_metrics,
            metrics_path=metrics_path,
            predictions_path=predictions_path,
            confusion_matrix_path=confusion_path,
            calibration_path=calibration_path,
            warnings=warnings,
        )

    def save_model(self, model: Any, path: Path) -> None:
        import joblib  # type: ignore[import-untyped]

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path / _ESTIMATOR_FILE)

    def load_model(self, path: Path) -> Any:
        import joblib

        estimator = Path(path) / _ESTIMATOR_FILE
        if not estimator.is_file():
            raise InstanceError(
                f"missing {estimator}; no sklearn estimator to load",
                detail={"path": str(estimator)},
            )
        return joblib.load(estimator)

    def predict(self, model: Any, X: Any) -> np.ndarray:
        return np.asarray(model.predict(_as_matrix(X)))

    def predict_proba(self, model: Any, X: Any) -> np.ndarray:
        return np.asarray(model.predict_proba(_as_matrix(X)))

    def run_optimization(
        self,
        opt: OptimizationSpec,
        recipe: ModelRecipe,
        data: DataRefineryInstance,
        seed: int,
        temp_dir: Path,
    ) -> Any:
        raise NotImplementedError(
            "the sklearn baseline is a fixed comparison model and does not support "
            "Optuna optimization"
        )

    def render_visualization(self, viz: Any, instance_artifacts: Any) -> bytes | None:
        raise NotImplementedError(
            "the sklearn baseline does not render its own visualizations"
        )


# --- helpers ---


def _validate_architecture(arch: dict[str, Any]) -> MLPClassifierParams:
    if not isinstance(arch, dict):
        raise PluginError(
            f"Architecture must be a mapping, got {type(arch).__name__}", stage="build_model"
        )
    arch_type = arch.get("type")
    if arch_type != "mlp_classifier":
        raise PluginError(
            f"sklearn plugin only builds 'mlp_classifier'; got type={arch_type!r}",
            stage="build_model",
        )
    try:
        return MLPClassifierParams(**{k: v for k, v in arch.items() if k != "type"})
    except ValidationError as exc:
        raise PluginError(
            f"invalid mlp_classifier params: {exc}", stage="build_model", detail={"arch": arch}
        ) from exc


def _split_metrics(
    requested: set[str],
    y: np.ndarray,
    preds: np.ndarray,
    proba: np.ndarray,
    labels: list[int],
    n_bins: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "accuracy" in requested:
        out["accuracy"] = metrics.accuracy(y, preds)
    if "macro_f1" in requested:
        out["macro_f1"] = metrics.f1_score(y, preds, labels=labels, average="macro")
    if "per_class_f1" in requested:
        out["per_class_f1"] = metrics.f1_score(y, preds, labels=labels, average=None)
    if "per_class_precision" in requested:
        out["per_class_precision"] = metrics.precision_score(y, preds, labels=labels)
    if "per_class_recall" in requested:
        out["per_class_recall"] = metrics.recall_score(y, preds, labels=labels)
    if "ece" in requested:
        out["ece"] = metrics.expected_calibration_error(
            proba.max(axis=1), (preds == y).astype(float), n_bins=n_bins
        )
    return out


def _prediction_rows(
    split: str, y: np.ndarray, preds: np.ndarray, proba: np.ndarray, classes: list[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i in range(len(preds)):
        row: dict[str, Any] = {
            "split": split,
            "record_id": i,
            "true_label": classes[int(y[i])],
            "pred_label": classes[int(preds[i])],
        }
        for c, name in enumerate(classes):
            row[f"pred_proba_{name}"] = float(proba[i, c])
        rows.append(row)
    return rows


def _calibration_rows(split: str, curve: dict[str, list[float]]) -> list[dict[str, Any]]:
    return [
        {
            "split": split,
            "bin_lower": curve["bin_lower"][i],
            "bin_upper": curve["bin_upper"][i],
            "mean_confidence": curve["mean_confidence"][i],
            "accuracy": curve["accuracy"][i],
            "count": int(curve["count"][i]),
        }
        for i in range(len(curve["count"]))
    ]


def _write_history(loss_curve: list[float], path: Path) -> None:
    import pandas as pd  # type: ignore[import-untyped]

    frame = pd.DataFrame(
        {"epoch": list(range(1, len(loss_curve) + 1)), "train_loss": loss_curve}
    )
    frame.to_parquet(path, index=False)


def _write_predictions(rows: list[dict[str, Any]], classes: list[str], path: Path) -> None:
    import pandas as pd

    columns = ["split", "record_id", "true_label", "pred_label"] + [
        f"pred_proba_{name}" for name in classes
    ]
    pd.DataFrame(rows).reindex(columns=columns).to_parquet(path, index=False)


def _write_calibration(rows: list[dict[str, Any]], path: Path) -> None:
    import pandas as pd

    pd.DataFrame(rows).to_parquet(path, index=False)


def _as_matrix(X: Any) -> np.ndarray:
    array = np.asarray(X, dtype=np.float32)
    if array.ndim != 2:
        raise PluginError(
            f"sklearn predict expects a 2-D feature matrix; got shape {array.shape}",
            stage="predict",
        )
    return array


def _safe_version(distribution: str) -> str | None:
    import importlib.metadata

    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


# The singleton registered via the `modelfoundry.plugins` entry point.
plugin: Plugin = SklearnPlugin()
