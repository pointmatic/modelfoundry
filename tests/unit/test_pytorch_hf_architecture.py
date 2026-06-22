# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the pretrained-encoder architecture path (Story H.j.1, R1.1/R1.3).

Builds `Encoder` -> `Pooling` -> `Head` compositions from the PyTorch plugin's
architecture vocabulary and exercises the forward pass, the `frozen` toggle, the
pooling variants, and the seed-before-build determinism discipline.

Gated on BOTH `torch` and `transformers`: skips cleanly in the default `testenv`
and `smoke-pytorch` (no transformers), runs in `smoke-huggingface`. Weights load
from the OFFLINE warm HF cache (the H.i spike seeded `WinKawaks/vit-tiny-patch16-224`),
so no network is touched — the offline env flags are set before any transformers
import.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

# Offline warm-cache contract (R1.5): force offline before transformers loads.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")

from modelfoundry.plugins.pytorch.architecture import build_model  # noqa: E402

# A tiny ViT warm in the local HF hub cache (seeded by the H.i spike). 224x224,
# patch 16, hidden 192 — its native input resolution is what a bound DR instance
# must match (the DR<->MF input-shape contract H.j.2/H.j.3 will validate).
_VIT = "WinKawaks/vit-tiny-patch16-224"
_IMG = 224
_CLASSES = 3


def _encoder_spec(*, frozen: bool = True, pooling: str = "mean") -> dict[str, object]:
    return {
        "num_classes": _CLASSES,
        "layers": [
            {"op": "Encoder", "source": "huggingface", "id": _VIT, "frozen": frozen},
            {"op": "Pooling", "type": pooling},
            {"op": "Head", "type": "mlp", "hidden_dims": [16], "num_classes": _CLASSES},
        ],
    }


def _batch(n: int = 2) -> Any:
    torch.manual_seed(123)
    return torch.randn(n, 3, _IMG, _IMG)


def test_encoder_pooling_head_builds_and_forwards() -> None:
    model = build_model(_encoder_spec())
    model.eval()
    with torch.no_grad():
        logits = model(_batch(2))
    assert tuple(logits.shape) == (2, _CLASSES)


def test_frozen_encoder_freezes_only_the_encoder() -> None:
    model = build_model(_encoder_spec(frozen=True))
    enc = model.encoder
    assert all(not p.requires_grad for p in enc.parameters()), "frozen encoder must not train"
    head_trainable = [p for p in model.head.parameters() if p.requires_grad]
    assert head_trainable, "the head must stay trainable when the encoder is frozen"


def test_unfrozen_encoder_is_trainable() -> None:
    model = build_model(_encoder_spec(frozen=False))
    assert any(p.requires_grad for p in model.encoder.parameters()), (
        "frozen=False must leave the encoder trainable"
    )


@pytest.mark.parametrize("pooling", ["mean", "max", "attention"])
def test_pooling_variants_produce_class_logits(pooling: str) -> None:
    model = build_model(_encoder_spec(pooling=pooling))
    model.eval()
    with torch.no_grad():
        logits = model(_batch(2))
    assert tuple(logits.shape) == (2, _CLASSES)


def test_build_is_deterministic_under_seed() -> None:
    # prepare_for_build seeds torch.manual_seed before build_model, so the fresh
    # head/pool init must be reproducible across two equally-seeded builds.
    torch.manual_seed(7)
    a = build_model(_encoder_spec(pooling="attention"))
    torch.manual_seed(7)
    b = build_model(_encoder_spec(pooling="attention"))
    a_params = dict(a.named_parameters())
    b_params = dict(b.named_parameters())
    assert a_params.keys() == b_params.keys()
    for name in a_params:
        assert torch.equal(a_params[name], b_params[name]), f"param {name} diverged across builds"


def test_model_is_self_describing_for_round_trip() -> None:
    spec = _encoder_spec()
    model = build_model(spec)
    assert model.architecture_spec == spec, (
        "architecture_spec must be set for the from-disk rebuild"
    )


def _lora_spec() -> dict[str, object]:
    return {
        "num_classes": _CLASSES,
        "layers": [
            {"op": "Encoder", "source": "huggingface", "id": _VIT, "frozen": True},
            {"op": "LoRA", "rank": 8, "alpha": 16, "target_modules": ["q_proj", "v_proj"]},
            {"op": "Pooling", "type": "mean"},
            {"op": "Head", "type": "mlp", "hidden_dims": [16], "num_classes": _CLASSES},
        ],
    }


def test_lora_composition_builds_and_forwards() -> None:
    model = build_model(_lora_spec())
    model.eval()
    with torch.no_grad():
        logits = model(_batch(2))
    assert tuple(logits.shape) == (2, _CLASSES)


def test_lora_injects_trainable_adapters_into_a_frozen_encoder() -> None:
    model = build_model(_lora_spec())
    enc_params = dict(model.encoder.named_parameters())
    # peft injects `lora_` adapter params, trainable; the base encoder stays frozen.
    lora_trainable = [n for n, p in enc_params.items() if "lora_" in n and p.requires_grad]
    base_trainable = [n for n, p in enc_params.items() if "lora_" not in n and p.requires_grad]
    assert lora_trainable, "LoRA must inject trainable adapter params"
    assert not base_trainable, "the base encoder weights must stay frozen under LoRA"
