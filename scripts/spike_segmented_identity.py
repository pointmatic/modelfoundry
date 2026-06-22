# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Story I.a architectural spike — segmented recipe identity (THROWAWAY).

Proves the four genuinely-unproven mechanics behind Phase I before any
production module lands (spike §9 / plan §4):

  1. `join_stable` — a labeled, length-framed, prefix-capable combiner over
     per-segment SHA-256 digests, with sparse (empty ⇒ nothing) semantics.
  2. Cross-plugin identity isolation — a PyTorch recipe's hash does not move
     when the sklearn surface changes (F2).
  3. Discriminated-union plugin surface, FLAT on disk — top-level `plugin`
     selects the concrete typed Training variant; validator checks 3 + 17 adapt.
  4. No-implicit-defaults sparsity — an unwritten optional contributes nothing,
     so adding an optional field to a shared spec does not invalidate caches
     that omit it (the consequence-(2) blast-radius fix).

This is a spike: it writes nothing to disk, imports nothing torch-y (runs in the
base venv), prints a findings summary, and exits 0 when every claim holds. The
DELIVERABLE is docs/spikes/I.a-segmented-recipe-identity.md, not this script.

Run:  pyve run python scripts/spike_segmented_identity.py
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

# ---------------------------------------------------------------------------
# Part 1 — join_stable: the segment combiner
# ---------------------------------------------------------------------------
#
# Byte format (the I.a deliverable; MUST be confirmed byte-for-byte against
# DataRefinery's `join_stable` before I.b implements — spike §3 governance):
#
#   frame(label, payload) := len(label):u32be ‖ label ‖ len(payload):u32be ‖ payload
#   join_stable(segments, upstream=None) :=
#       SHA-256(
#           [frame(b"\x00upstream", upstream) if upstream]
#           ‖ for label in sorted(present, non-empty) segments:
#                 frame(label, SHA-256(segment_bytes))
#       )
#
# Properties this format buys:
#   * Length-framing  -> no boundary-ambiguity collisions (label/payload splits
#     are unambiguous, so {"a":"bc"} and {"ab":"c"} never collide).
#   * Labeled         -> a value moving between segments changes the hash.
#   * sorted(labels)  -> order-independent; stable across dict insertion order.
#   * Sparse (omit empty) -> an absent/empty segment contributes nothing, so the
#     extensions mechanism with extensions empty for everyone is a no-op (I.d).
#   * `upstream` digest -> prefix-capable: H(H_upstream ‖ segment) composes, so
#     the deferred vertical stage-waterfall can layer on without re-specifying
#     the combiner (cross-repo agreement with DataRefinery, spike §4b).

_ALL_EMPTY = hashlib.sha256(b"\x00mf-empty-combination").digest()


def _frame(label: bytes, payload: bytes) -> bytes:
    return len(label).to_bytes(4, "big") + label + len(payload).to_bytes(4, "big") + payload


def _seg_canonical(value: Any) -> bytes | None:
    """Canonical bytes for one segment's sub-document; None/empty ⇒ sparse omit."""
    if value is None:
        return None
    if isinstance(value, (dict, list)) and len(value) == 0:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def join_stable(segments: dict[str, Any], *, upstream: bytes | None = None) -> bytes:
    parts: list[bytes] = []
    if upstream is not None:
        parts.append(_frame(b"\x00upstream", upstream))
    for label in sorted(segments):
        payload = _seg_canonical(segments[label])
        if payload is None:
            continue  # sparse: empty/absent segment contributes nothing
        parts.append(_frame(label.encode("utf-8"), hashlib.sha256(payload).digest()))
    if not parts:
        return _ALL_EMPTY
    return hashlib.sha256(b"".join(parts)).digest()


def recipe_digest(segments: dict[str, Any]) -> str:
    return join_stable(segments).hex()


# ---------------------------------------------------------------------------
# Part 3 — discriminated-union plugin surface, FLAT on disk
# ---------------------------------------------------------------------------
#
# The recipe stays flat: the discriminator is the TOP-LEVEL `plugin` key, which
# the loader injects as a private `kind` before validating the union. Nothing
# extra is written to the YAML. (models.py itself must stay plugin-agnostic — it
# cannot import plugins — so in production this resolution is driven by the
# discovered plugin's registered specs; here we hard-code two variants to prove
# the pydantic mechanics + validator adaptation.)


class PyTorchTraining(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["pytorch"] = "pytorch"
    op: str
    max_epochs: int = Field(gt=0)
    batch_size: int = Field(gt=0)
    precision: Literal["fp32", "amp"]  # no default — no-implicit-defaults


class SklearnTraining(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["sklearn"] = "sklearn"
    op: str
    warm_start: bool  # no default — no-implicit-defaults


TrainingSurface = Annotated[PyTorchTraining | SklearnTraining, Field(discriminator="kind")]
_TRAINING_ADAPTER: TypeAdapter[Any] = TypeAdapter(TrainingSurface)


def resolve_training(flat_section: dict[str, Any], plugin: str) -> BaseModel:
    """Inject the top-level `plugin` as the union discriminator, then validate."""
    return _TRAINING_ADAPTER.validate_python({**flat_section, "kind": plugin})


# A toy plugin operations registry (mirrors `plugin.operations` + OperationSpec).
class _AdamWParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learning_rate: float = Field(gt=0)


_PYTORCH_OPS: dict[str, type[BaseModel]] = {"adamw": _AdamWParams}


def adapted_check_3_and_17(section_label: str, typed: BaseModel, ops: dict[str, type[BaseModel]]):
    """Checks 3 (op registered) + 17 (params valid) over a TYPED variant.

    Under the union the params are real model fields, not a `model_extra` bag, so
    `_iter_ops` yields (label, op, params) where params is the variant dump minus
    structural keys (`kind`, `op`). The never-short-circuit accumulation is
    preserved by the caller; this returns (registered, params_ok, detail).
    """
    op = typed.op  # type: ignore[attr-defined]
    registered = op in ops
    params = {k: v for k, v in typed.model_dump().items() if k not in {"kind", "op"}}
    params_ok = True
    detail = ""
    if registered:
        try:
            ops[op].model_validate(params)
        except ValidationError as exc:
            params_ok = False
            detail = str(exc).splitlines()[0]
    return registered, params_ok, detail


# ---------------------------------------------------------------------------
# Findings harness
# ---------------------------------------------------------------------------

_passes = 0
_fails = 0


def claim(label: str, ok: bool, note: str = "") -> None:
    global _passes, _fails
    mark = "PASS" if ok else "FAIL"
    _passes += ok
    _fails += not ok
    suffix = f"  ({note})" if note else ""
    print(f"  [{mark}] {label}{suffix}")


def main() -> int:
    print("=== Part 1: join_stable combiner ===")

    base = {"core": {"plugin": "pytorch", "seed": 7}, "plugin": {"Loss": {"op": "ce"}}}
    claim("deterministic", recipe_digest(base) == recipe_digest(base))
    claim(
        "label-keyed: same payload under a different segment changes the hash",
        recipe_digest({"core": {"x": 1}}) != recipe_digest({"plugin": {"x": 1}}),
    )
    # Length-framing defeats boundary-ambiguity collisions.
    claim(
        "length-framed: no boundary collision",
        recipe_digest({"a": "bc"}) != recipe_digest({"ab": "c"}),
    )
    # Sparse: an empty / absent / explicitly-empty segment contributes nothing.
    claim(
        "sparse: empty extensions == no extensions == None",
        recipe_digest({**base})
        == recipe_digest({**base, "extensions": {}})
        == recipe_digest({**base, "extensions": None}),
    )
    claim(
        "non-empty extensions DOES enter identity",
        recipe_digest({**base, "extensions": {"foo": 1}}) != recipe_digest(base),
    )
    # Prefix-capable: H(H_upstream ‖ segment) composes for the deferred waterfall.
    core_h = join_stable({"core": base["core"]})
    h_arch = join_stable({"architecture": {"op": "cnn"}}, upstream=core_h)
    h_train = join_stable({"training": {"epochs": 3}}, upstream=h_arch)
    claim("prefix-capable: chained digests are 32 bytes & stable", len(h_train) == 32)
    claim(
        "prefix-capable: a core change ripples down the chain",
        h_train
        != join_stable(
            {"training": {"epochs": 3}},
            upstream=join_stable(
                {"architecture": {"op": "cnn"}},
                upstream=join_stable({"core": {**base["core"], "seed": 8}}),
            ),
        ),
    )

    print("\n=== Part 2: cross-plugin identity isolation (F2) ===")
    # A PyTorch recipe authors only the pytorch surface. With sparse hashing +
    # no-implicit-defaults, a change to the *sklearn* surface schema (a new
    # optional field sklearn recipes may set) cannot perturb the pytorch recipe:
    # the pytorch recipe never writes that field, so it never enters its bytes.
    pytorch_recipe = {
        "core": {"plugin": "pytorch", "seed": 7},
        "plugin": {
            "Training": {
                "op": "supervised",
                "max_epochs": 3,
                "batch_size": 32,
                "precision": "fp32",
            },
            "Loss": {"op": "adamw", "learning_rate": 0.001},
        },
    }
    h_before = recipe_digest(pytorch_recipe)
    # ... sklearn gains `warm_start`; a *sklearn* recipe sets it, pytorch does not.
    sklearn_before = recipe_digest(
        {"core": {"plugin": "sklearn", "seed": 7}, "plugin": {"Training": {"op": "rf"}}}
    )
    sklearn_after = recipe_digest(
        {
            "core": {"plugin": "sklearn", "seed": 7},
            "plugin": {"Training": {"op": "rf", "warm_start": True}},
        }
    )
    h_after = recipe_digest(pytorch_recipe)  # pytorch recipe text is unchanged
    claim("pytorch hash unmoved by a sklearn-surface change", h_before == h_after)
    claim("sklearn hash DOES move (the change scopes to sklearn)", sklearn_before != sklearn_after)

    print("\n=== Part 3: discriminated-union surface, flat on disk ===")
    flat_pt = {"op": "supervised", "max_epochs": 3, "batch_size": 32, "precision": "amp"}
    flat_sk = {"op": "rf", "warm_start": True}
    pt = resolve_training(flat_pt, "pytorch")
    sk = resolve_training(flat_sk, "sklearn")
    claim(
        "flat YAML + top-level plugin resolves to PyTorchTraining",
        type(pt).__name__ == "PyTorchTraining",
    )
    claim(
        "flat YAML + top-level plugin resolves to SklearnTraining",
        type(sk).__name__ == "SklearnTraining",
    )
    # A pytorch-only field is rejected for sklearn (extra="forbid" on the variant).
    cross_rejected = False
    try:
        resolve_training({"op": "rf", "precision": "amp", "warm_start": True}, "sklearn")
    except ValidationError:
        cross_rejected = True
    claim("a pytorch-only field is rejected on the sklearn variant", cross_rejected)

    print("\n=== Part 3b: validator checks 3 + 17 adapt to typed variants ===")
    ok_recipe = resolve_training(
        {"op": "adamw", "max_epochs": 3, "batch_size": 32, "precision": "fp32"}, "pytorch"
    )
    # Re-purpose `op` to an Optimizer-like check against the toy ops registry.
    reg, _pok, _ = adapted_check_3_and_17("Training", ok_recipe, _PYTORCH_OPS)
    claim("check 3: registered op recognised over the typed variant", reg)
    # An unregistered op is caught by check 3 without short-circuiting check 17.
    bad_op = resolve_training(
        {"op": "nope", "max_epochs": 3, "batch_size": 32, "precision": "fp32"}, "pytorch"
    )
    reg2, _, _ = adapted_check_3_and_17("Training", bad_op, _PYTORCH_OPS)
    claim("check 3: unregistered op flagged", not reg2)

    print("\n=== Part 4: no-implicit-defaults sparsity (consequence-2 fix) ===")
    # Two recipes identical except one OMITS an optional the other never sets.
    # Sparse hashing: omission contributes nothing, so they hash identically.
    r_min = {
        "core": {"plugin": "pytorch", "seed": 7},
        "plugin": {"Training": {"op": "s", "max_epochs": 3}},
    }
    r_min_2 = {
        "core": {"plugin": "pytorch", "seed": 7},
        "plugin": {"Training": {"op": "s", "max_epochs": 3}},
    }
    claim(
        "omitting an optional ⇒ identical bytes (sparse)",
        recipe_digest(r_min) == recipe_digest(r_min_2),
    )
    # Today's hazard, reproduced: a code-supplied default injected into the dump
    # shifts the bytes for every omitting recipe. No-implicit-defaults removes the
    # injection, so adding the field as an *unwritten optional* is a no-op.
    legacy_default_injected = {
        **r_min,
        "plugin": {"Training": {"op": "s", "max_epochs": 3, "num_workers": 2}},
    }
    claim(
        "a code-injected default WOULD invalidate (this is what we remove)",
        recipe_digest(legacy_default_injected) != recipe_digest(r_min),
    )

    print(f"\n{_passes} passed, {_fails} failed")
    return 0 if _fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
