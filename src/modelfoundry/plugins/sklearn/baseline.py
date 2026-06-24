# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""FR-12 scikit-learn baseline comparison — resolver + seeded fit-on-train scoring.

The self-contained half of FR-12 (Story I.t; design in
`phase-i-subphase-2-feature-code-reconciliation-plan.md` § 7). A recipe's
`Evaluation.comparison.baseline_model_id` names a scikit-learn classifier via the
`sklearn:<EstimatorClassName>` grammar (D-I.s.1); `score_baseline` resolves the
class through a curated allowlist, instantiates it with a **seeded** `random_state`
(D-I.s.3, the determinism contract — a fit-on-train baseline is a new stochastic
source), fits it on the `train` feature matrix via the C.f flattened-feature path
(reusing the same train-fitted normalization + label→index scan as the main model,
so the baseline learns the bound instance's labels directly — no HF label-space
alignment problem), and scores it on every `Evaluation.splits` entry with the same
metric vocabulary as the main model (D-I.s.2).

The estimator class learns the dataset's own labels, so this half ships now; the
HF-pretrained baseline (label-space alignment + the deferred `[huggingface]` extra)
is the design-heavy half, deferred (§ 5 of the plan).

**Persistence (D-I.s.4):** metrics only — the caller writes the returned
`{split: {metric: value}}` under `evaluation/metrics.json` `baseline.<split>.<metric>`.
No round-trippable baseline `ModelInstance`, predictions, or estimator artifact.

**Torch-free at import.** sklearn / the torch-backed feature path import lazily
inside `score_baseline`, so importing this module (e.g. for the grammar parse in the
validator path) stays light.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from modelfoundry.pipeline.seeding import derive_seed

if TYPE_CHECKING:
    from modelfoundry.pipeline.data_binding import DataRefineryInstance
    from modelfoundry.recipe.models import EvaluationSpec

#: D-I.s.1 grammar: `sklearn:` prefix + a Python-identifier estimator class name.
_BASELINE_ID_RE = re.compile(r"^sklearn:([A-Za-z_]\w*)$")

#: sklearn's `random_state` must fit in 32 bits.
_U32 = (1 << 32) - 1

#: D-I.s.1 curated allowlist: estimator class name → import module. Every entry is a
#: classifier that consumes the flat `(n_samples, n_features)` matrix and exposes
#: `predict_proba` (so `ece` / `calibration_curve` score uniformly). Extensible.
ALLOWLIST: dict[str, str] = {
    "RandomForestClassifier": "sklearn.ensemble",
    "GradientBoostingClassifier": "sklearn.ensemble",
    "LogisticRegression": "sklearn.linear_model",
    "KNeighborsClassifier": "sklearn.neighbors",
    "DummyClassifier": "sklearn.dummy",
}


class BaselineUnresolvable(Exception):
    """A well-formed `baseline_model_id` could not be resolved/fit at runtime.

    The caller catches this and follows the kept FR-12 warn-and-skip contract
    (warn + omit the `baseline` block + main metrics proceed). A *malformed* id is
    caught earlier by validator check 13 at validate time and never reaches here.
    """


def parse_baseline_model_id(model_id: str) -> str | None:
    """Return the estimator class name if `model_id` matches the grammar, else `None`.

    Format check only (D-I.s.1) — does *not* assert allowlist membership. Validator
    check 13 calls this; a well-formed-but-unknown class passes the format check and
    is rejected later at runtime (warn-and-skip), per the kept failure-mode split.
    """
    m = _BASELINE_ID_RE.match(model_id)
    return m.group(1) if m else None


def resolve_estimator_class(class_name: str) -> type[Any] | None:
    """Resolve an allowlisted estimator class by name, or `None` if not allowlisted."""
    module_path = ALLOWLIST.get(class_name)
    if module_path is None:
        return None
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name, None)


def _instantiate_seeded(cls: type[Any], seed: int) -> Any:
    """Instantiate `cls` with a seeded `random_state` when the estimator accepts one.

    Seeding via `derive_seed(seed, "baseline")` (a distinct scope, 32-bit-masked) is
    the D-I.s.3 determinism obligation. `KNeighborsClassifier` and friends take no
    `random_state` — guarded by inspecting the default params.
    """
    estimator = cls()
    if "random_state" in estimator.get_params():
        estimator.set_params(random_state=derive_seed(seed, "baseline") & _U32)
    return estimator


def score_baseline(
    baseline_model_id: str,
    data: DataRefineryInstance,
    evaluation: EvaluationSpec,
    seed: int,
) -> dict[str, dict[str, Any]]:
    """Fit a seeded sklearn baseline on `train` and score it per `evaluation.splits`.

    Returns `{split: {metric: value}}` for the caller to persist under
    `metrics.json` `baseline.*`. Raises `BaselineUnresolvable` (caught upstream →
    warn + omit) when the id is unknown/un-importable or the fit/score fails.
    """
    class_name = parse_baseline_model_id(baseline_model_id)
    if class_name is None:
        # Normally unreachable: check 13 rejects malformed ids at validate time.
        raise BaselineUnresolvable(
            f"baseline_model_id {baseline_model_id!r} is malformed "
            f"(expected 'sklearn:<EstimatorClassName>'); skipped"
        )
    cls = resolve_estimator_class(class_name)
    if cls is None:
        raise BaselineUnresolvable(
            f"baseline comparison against {baseline_model_id!r} is not resolvable "
            f"(unknown estimator class {class_name!r}; "
            f"allowlist: {sorted(ALLOWLIST)}); skipped"
        )

    from modelfoundry.plugins.sklearn import metrics
    from modelfoundry.plugins.sklearn.data import feature_matrix

    try:
        estimator = _instantiate_seeded(cls, seed)
        x_train, y_train, classes = feature_matrix(data, "train")
        estimator.fit(x_train, y_train)

        requested = set(evaluation.metrics)
        labels = list(range(len(classes)))
        out: dict[str, dict[str, Any]] = {}
        for split in evaluation.splits:
            x, y, _ = feature_matrix(data, split)
            proba = estimator.predict_proba(x)
            import numpy as np

            proba = np.asarray(proba)
            preds = proba.argmax(axis=1)
            split_metrics = metrics.score_split(
                requested, y, preds, proba, labels=labels, n_bins=evaluation.calibration_bins
            )
            if "confusion_matrix" in requested:
                split_metrics["confusion_matrix"] = metrics.confusion_matrix(
                    y, preds, labels=labels
                ).tolist()
            if "calibration_curve" in requested:
                split_metrics["calibration_curve"] = metrics.calibration_curve(
                    proba.max(axis=1),
                    (preds == y).astype(float),
                    n_bins=evaluation.calibration_bins,
                )
            out[split] = split_metrics
        return out
    except BaselineUnresolvable:
        raise
    except Exception as exc:  # any fit/score failure → warn-and-skip (kept FR-12 contract)
        raise BaselineUnresolvable(
            f"baseline comparison against {baseline_model_id!r} failed to fit/score "
            f"({type(exc).__name__}: {exc}); skipped"
        ) from exc
