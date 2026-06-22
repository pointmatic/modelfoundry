# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch architecture vocabulary (FR-7 / FR-ARCH-1, Story C.c).

Registers the CIFAR-10 baseline vocabulary — primitives (`Conv2d`, `BatchNorm2d`,
`ReLU`, `MaxPool2d`, `AvgPool2d`, `AdaptiveAvgPool2d`, `Linear`, `Dropout`,
`Flatten`), composites (`MLP`, `ConvBlock`, `ResidualBlock`), and the baseline
architectures `simple_cnn`, `resnet8`, `resnet20` — plus the deferred-but-
contract-supported pretrained-encoder path (`Encoder`, `LoRA`, `Pooling`,
`Head`, all `requires_extras=("huggingface",)`).

**Import-safe without the `[pytorch]` extra.** The op registry
(`ARCHITECTURE_OPERATIONS`) is pure pydantic so `discover_plugins()` and the
recipe validator (FR-2 check 17) work on a torch-less install; `torch` is
imported lazily inside `build_model`, only when a model is actually constructed.

The recipe's `Architecture:` block (`dict[str, Any]`) takes one of two shapes:

* **named baseline** — `{type: resnet20, num_classes: 10, in_channels: 3}`
* **explicit layers** — `{num_classes: 10, layers: [{op: Conv2d, ...}, ...]}`
  composed into an `nn.Sequential` in declared order.

The `num_classes` ↔ DataRefinery-label-count cross-check is FR-2 check 18 (the
validator owns it; `build_model` does not receive the bound instance).
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, ValidationError

from modelfoundry.core.errors import PluginError
from modelfoundry.plugins.base import OperationSpec

if TYPE_CHECKING:
    import torch.nn as nn


# --- parameter models (torch-free) -------------------------------------------


class _ArchParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Conv2dParams(_ArchParams):
    in_channels: int
    out_channels: int
    kernel_size: int = 3
    stride: int = 1
    padding: int = 0
    bias: bool = True


class BatchNorm2dParams(_ArchParams):
    num_features: int


class ReLUParams(_ArchParams):
    inplace: bool = False


class MaxPool2dParams(_ArchParams):
    kernel_size: int = 2
    stride: int | None = None
    padding: int = 0


class AvgPool2dParams(_ArchParams):
    kernel_size: int = 2
    stride: int | None = None
    padding: int = 0


class AdaptiveAvgPool2dParams(_ArchParams):
    output_size: int = 1


class LinearParams(_ArchParams):
    in_features: int
    out_features: int
    bias: bool = True


class DropoutParams(_ArchParams):
    p: float = 0.5


class FlattenParams(_ArchParams):
    start_dim: int = 1
    end_dim: int = -1


class MLPParams(_ArchParams):
    in_features: int
    hidden_dims: list[int]
    num_classes: int
    dropout: float = 0.0
    activation: str = "relu"


class ConvBlockParams(_ArchParams):
    in_channels: int
    out_channels: int
    kernel_size: int = 3
    stride: int = 1
    padding: int = 1
    with_batchnorm: bool = True
    with_pool: bool = False


class ResidualBlockParams(_ArchParams):
    in_channels: int
    out_channels: int
    stride: int = 1


class BaselineParams(_ArchParams):
    """Params for a named baseline architecture (`simple_cnn`/`resnet8`/`resnet20`)."""

    num_classes: int
    in_channels: int = 3


# Pretrained-encoder path — registered so recipe-time validation works without
# `[huggingface]`; `build_model` composes Encoder->Pooling->Head when the extra is
# present (Story H.j.1) and raises ImportError with a pointer when it is missing.
# `LoRA` is registered but its build path lands in Story H.k.


class EncoderParams(_ArchParams):
    source: str = "huggingface"
    id: str
    frozen: bool = True


class LoRAParams(_ArchParams):
    rank: int
    alpha: int
    dropout: float = 0.0
    target_modules: list[str]


class PoolingParams(_ArchParams):
    type: str = "mean"
    hidden_dim: int | None = None


class HeadParams(_ArchParams):
    type: str = "mlp"
    hidden_dims: list[int]
    num_classes: int
    id2label: dict[int, str] | None = None


_PRIMITIVE_PARAMS: dict[str, type[BaseModel]] = {
    "Conv2d": Conv2dParams,
    "BatchNorm2d": BatchNorm2dParams,
    "ReLU": ReLUParams,
    "MaxPool2d": MaxPool2dParams,
    "AvgPool2d": AvgPool2dParams,
    "AdaptiveAvgPool2d": AdaptiveAvgPool2dParams,
    "Linear": LinearParams,
    "Dropout": DropoutParams,
    "Flatten": FlattenParams,
}
_COMPOSITE_PARAMS: dict[str, type[BaseModel]] = {
    "MLP": MLPParams,
    "ConvBlock": ConvBlockParams,
    "ResidualBlock": ResidualBlockParams,
}
_BASELINE_PARAMS: dict[str, type[BaseModel]] = {
    "simple_cnn": BaselineParams,
    "resnet8": BaselineParams,
    "resnet20": BaselineParams,
}
_HF_PARAMS: dict[str, type[BaseModel]] = {
    "Encoder": EncoderParams,
    "LoRA": LoRAParams,
    "Pooling": PoolingParams,
    "Head": HeadParams,
}

BASELINES: frozenset[str] = frozenset(_BASELINE_PARAMS)
_HF_OPS: frozenset[str] = frozenset(_HF_PARAMS)


def _operation_specs() -> dict[str, OperationSpec]:
    specs: dict[str, OperationSpec] = {}
    for name, model in {**_PRIMITIVE_PARAMS, **_COMPOSITE_PARAMS, **_BASELINE_PARAMS}.items():
        specs[name] = OperationSpec(op_name=name, param_model=model, applies_to="architecture")
    for name, model in _HF_PARAMS.items():
        specs[name] = OperationSpec(
            op_name=name,
            param_model=model,
            applies_to="architecture",
            requires_extras=("huggingface",),
        )
    return specs


#: The architecture ops the PyTorch plugin contributes to `Plugin.operations`.
ARCHITECTURE_OPERATIONS: dict[str, OperationSpec] = _operation_specs()


# --- torch-bearing builders (lazy) -------------------------------------------


@functools.lru_cache(maxsize=1)
def _kit() -> Any:
    """Build (once) the torch-dependent module classes + builders.

    Imported lazily so this module stays import-safe without `[pytorch]`. Returns
    a namespace exposing `build_op(name, params)` and `baselines[name]`.
    """
    import torch
    from torch import nn

    class ConvBlock(nn.Module):
        def __init__(self, p: ConvBlockParams) -> None:
            super().__init__()
            layers: list[nn.Module] = [
                nn.Conv2d(
                    p.in_channels,
                    p.out_channels,
                    kernel_size=p.kernel_size,
                    stride=p.stride,
                    padding=p.padding,
                    bias=not p.with_batchnorm,
                )
            ]
            if p.with_batchnorm:
                layers.append(nn.BatchNorm2d(p.out_channels))
            layers.append(nn.ReLU(inplace=True))
            if p.with_pool:
                layers.append(nn.MaxPool2d(kernel_size=2))
            self.block = nn.Sequential(*layers)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out: torch.Tensor = self.block(x)
            return out

    class ResidualBlock(nn.Module):
        """CIFAR BasicBlock with option-B (1x1 conv) projection shortcuts."""

        def __init__(self, in_channels: int, out_channels: int, stride: int = 1) -> None:
            super().__init__()
            self.conv1 = nn.Conv2d(
                in_channels, out_channels, kernel_size=3, stride=stride, padding=1, bias=False
            )
            self.bn1 = nn.BatchNorm2d(out_channels)
            self.conv2 = nn.Conv2d(
                out_channels, out_channels, kernel_size=3, stride=1, padding=1, bias=False
            )
            self.bn2 = nn.BatchNorm2d(out_channels)
            if stride != 1 or in_channels != out_channels:
                self.shortcut: nn.Module = nn.Sequential(
                    nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False),
                    nn.BatchNorm2d(out_channels),
                )
            else:
                self.shortcut = nn.Identity()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out = torch.relu(self.bn1(self.conv1(x)))
            out = self.bn2(self.conv2(out))
            out = out + self.shortcut(x)
            return torch.relu(out)

    class MLP(nn.Module):
        def __init__(self, p: MLPParams) -> None:
            super().__init__()
            act = {"relu": nn.ReLU, "gelu": nn.GELU, "tanh": nn.Tanh}.get(p.activation)
            if act is None:
                raise PluginError(
                    f"MLP.activation {p.activation!r} not in {{relu, gelu, tanh}}",
                    stage="build_model",
                )
            layers: list[nn.Module] = []
            prev = p.in_features
            for hidden in p.hidden_dims:
                layers += [nn.Linear(prev, hidden), act()]
                if p.dropout > 0:
                    layers.append(nn.Dropout(p.dropout))
                prev = hidden
            layers.append(nn.Linear(prev, p.num_classes))
            self.net = nn.Sequential(*layers)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out: torch.Tensor = self.net(x)
            return out

    def _make_stage(in_ch: int, out_ch: int, num_blocks: int, stride: int) -> nn.Module:
        blocks: list[nn.Module] = [ResidualBlock(in_ch, out_ch, stride)]
        blocks += [ResidualBlock(out_ch, out_ch, 1) for _ in range(num_blocks - 1)]
        return nn.Sequential(*blocks)

    def _build_cifar_resnet(num_classes: int, in_channels: int, blocks_per_stage: int) -> nn.Module:
        return nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU(inplace=True),
            _make_stage(16, 16, blocks_per_stage, stride=1),
            _make_stage(16, 32, blocks_per_stage, stride=2),
            _make_stage(32, 64, blocks_per_stage, stride=2),
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(64, num_classes),
        )

    def _conv_block(i: int, o: int) -> nn.Module:
        return ConvBlock(ConvBlockParams(in_channels=i, out_channels=o, with_pool=True))

    def build_simple_cnn(num_classes: int, in_channels: int) -> nn.Module:
        return nn.Sequential(
            _conv_block(in_channels, 32),
            _conv_block(32, 64),
            _conv_block(64, 128),
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(128, num_classes),
        )

    baselines = {
        "simple_cnn": build_simple_cnn,
        "resnet8": lambda nc, ic: _build_cifar_resnet(nc, ic, blocks_per_stage=1),
        "resnet20": lambda nc, ic: _build_cifar_resnet(nc, ic, blocks_per_stage=3),
    }

    def build_op(name: str, params: Any) -> nn.Module:
        # `params` is the concrete validated param model for `name` (matched by
        # the caller); typed `Any` here so the dispatch can read op-specific
        # fields without per-branch casts.
        if name == "Conv2d":
            return nn.Conv2d(
                params.in_channels,
                params.out_channels,
                params.kernel_size,
                params.stride,
                params.padding,
                bias=params.bias,
            )
        if name == "BatchNorm2d":
            return nn.BatchNorm2d(params.num_features)
        if name == "ReLU":
            return nn.ReLU(inplace=params.inplace)
        if name == "MaxPool2d":
            return nn.MaxPool2d(params.kernel_size, params.stride, params.padding)
        if name == "AvgPool2d":
            return nn.AvgPool2d(params.kernel_size, params.stride, params.padding)
        if name == "AdaptiveAvgPool2d":
            return nn.AdaptiveAvgPool2d(params.output_size)
        if name == "Linear":
            return nn.Linear(params.in_features, params.out_features, bias=params.bias)
        if name == "Dropout":
            return nn.Dropout(params.p)
        if name == "Flatten":
            return nn.Flatten(params.start_dim, params.end_dim)
        if name == "MLP":
            return MLP(params)
        if name == "ConvBlock":
            return ConvBlock(params)
        if name == "ResidualBlock":
            return ResidualBlock(params.in_channels, params.out_channels, params.stride)
        raise PluginError(f"op {name!r} is not constructible as a layer", stage="build_model")

    return _Kit(build_op=build_op, baselines=baselines)


class _Kit:
    def __init__(self, build_op: Any, baselines: Any) -> None:
        self.build_op = build_op
        self.baselines = baselines


# --- public builder ----------------------------------------------------------


def build_model(arch_spec: dict[str, Any]) -> Any:
    """Compose an `nn.Module` from a recipe `Architecture:` block.

    Raises `PluginError` on a malformed block or invalid op params, and
    `ImportError` (with an install pointer) if the deferred pretrained-encoder
    path is requested without the `[huggingface]` extra.
    """
    if not isinstance(arch_spec, dict):
        raise PluginError(
            f"Architecture must be a mapping, got {type(arch_spec).__name__}",
            stage="build_model",
        )
    num_classes = arch_spec.get("num_classes")
    if not isinstance(num_classes, int) or isinstance(num_classes, bool) or num_classes < 1:
        raise PluginError(
            "Architecture.num_classes must be a positive integer", stage="build_model"
        )

    arch_type = arch_spec.get("type")
    layers = arch_spec.get("layers")

    if arch_type is not None and layers is not None:
        raise PluginError(
            "Architecture declares both 'type' and 'layers'; choose one", stage="build_model"
        )

    if arch_type is not None:
        if arch_type not in BASELINES:
            raise PluginError(
                f"unknown architecture type {arch_type!r}; known baselines: {sorted(BASELINES)}",
                stage="build_model",
            )
        params = _validate(
            "type",
            arch_type,
            BaselineParams,
            {
                "num_classes": num_classes,
                "in_channels": arch_spec.get("in_channels", 3),
            },
        )
        model = _kit().baselines[arch_type](params.num_classes, params.in_channels)
    elif layers is not None:
        if _has_hf_ops(layers):
            model = _compose_pretrained(layers, num_classes)
        else:
            model = _compose(layers)
    else:
        raise PluginError(
            "Architecture must declare either 'type' (a baseline) or 'layers'", stage="build_model"
        )

    # Make the module self-describing so the bare `save_model(model, path)` can
    # write `model/architecture.json` for the FR-23 from-disk round-trip (C.l).
    model.architecture_spec = dict(arch_spec)
    return model


def _compose(layers: Any) -> Any:
    if not isinstance(layers, list) or not layers:
        raise PluginError("Architecture.layers must be a non-empty list", stage="build_model")
    from torch import nn

    kit = _kit()
    modules: list[nn.Module] = []
    for i, layer in enumerate(layers):
        if not isinstance(layer, dict) or "op" not in layer:
            raise PluginError(
                f"Architecture.layers[{i}] must be a mapping with an 'op' key",
                stage="build_model",
            )
        op = layer["op"]
        spec = ARCHITECTURE_OPERATIONS.get(op)
        if spec is None:
            raise PluginError(
                f"Architecture.layers[{i}] references unknown op {op!r}", stage="build_model"
            )
        params = _validate(f"layers[{i}]", op, spec.param_model, _without_op(layer))
        modules.append(kit.build_op(op, params))
    return nn.Sequential(*modules)


def _has_hf_ops(layers: Any) -> bool:
    """True if any layer is a pretrained-encoder op (`Encoder`/`LoRA`/`Pooling`/`Head`)."""
    return isinstance(layers, list) and any(
        isinstance(layer, dict) and layer.get("op") in _HF_OPS for layer in layers
    )


def _without_op(layer: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in layer.items() if k != "op"}


def _validate(where: str, op: str, model: type[BaseModel], params: dict[str, Any]) -> Any:
    try:
        return model(**params)
    except ValidationError as exc:
        raise PluginError(
            f"invalid params for op {op!r} at Architecture.{where}: {exc}",
            stage="build_model",
            detail={"op": op, "where": where},
        ) from exc


# --- pretrained-encoder path (Encoder -> Pooling -> Head, Story H.j.1) --------


@functools.lru_cache(maxsize=1)
def _hf_kit() -> Any:
    """Build (once) the torch module classes for the pretrained-encoder path.

    Imported lazily so the registry stays import-safe without `[pytorch]` /
    `[huggingface]`. The composite's `forward` runs the encoder on `pixel_values`
    (the image modality R1 targets — the bound DR instance feeds `(N, C, H, W)`
    image tensors; a text encoder would key on `input_ids`, a later modality),
    pools the token sequence, then classifies.
    """
    import torch
    from torch import nn

    class _MeanPool(nn.Module):
        def forward(self, h: torch.Tensor) -> torch.Tensor:
            return h.mean(dim=1)

    class _MaxPool(nn.Module):
        def forward(self, h: torch.Tensor) -> torch.Tensor:
            pooled: torch.Tensor = h.max(dim=1).values
            return pooled

    class _AttentionPool(nn.Module):
        """Learned single-query attention pool over the token sequence."""

        def __init__(self, hidden: int, proj_dim: int) -> None:
            super().__init__()
            self.proj = nn.Linear(hidden, proj_dim)
            self.query = nn.Parameter(torch.empty(proj_dim))
            nn.init.normal_(self.query, std=0.02)

        def forward(self, h: torch.Tensor) -> torch.Tensor:
            k = self.proj(h)  # (N, S, proj)
            scores = (k @ self.query) / (k.shape[-1] ** 0.5)  # (N, S)
            attn = scores.softmax(dim=1).unsqueeze(-1)  # (N, S, 1)
            pooled: torch.Tensor = (h * attn).sum(dim=1)  # (N, hidden)
            return pooled

    class _MLPHead(nn.Module):
        def __init__(self, in_dim: int, hidden_dims: list[int], num_classes: int) -> None:
            super().__init__()
            layers: list[nn.Module] = []
            prev = in_dim
            for hidden in hidden_dims:
                layers += [nn.Linear(prev, hidden), nn.ReLU()]
                prev = hidden
            layers.append(nn.Linear(prev, num_classes))
            self.net = nn.Sequential(*layers)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out: torch.Tensor = self.net(x)
            return out

    class _PretrainedClassifier(nn.Module):
        def __init__(self, encoder: nn.Module, pooling: nn.Module, head: nn.Module) -> None:
            super().__init__()
            self.encoder = encoder
            self.pooling = pooling
            self.head = head

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            out = self.encoder(pixel_values=x)
            hidden = getattr(out, "last_hidden_state", None)
            if hidden is None:
                hidden = out[0]
            logits: torch.Tensor = self.head(self.pooling(hidden))
            return logits

    return _HFKit(
        mean_pool=_MeanPool,
        max_pool=_MaxPool,
        attention_pool=_AttentionPool,
        mlp_head=_MLPHead,
        classifier=_PretrainedClassifier,
    )


class _HFKit:
    def __init__(
        self, mean_pool: Any, max_pool: Any, attention_pool: Any, mlp_head: Any, classifier: Any
    ) -> None:
        self.mean_pool = mean_pool
        self.max_pool = max_pool
        self.attention_pool = attention_pool
        self.mlp_head = mlp_head
        self.classifier = classifier


def _build_pooling(kit: _HFKit, params: PoolingParams, hidden: int) -> Any:
    if params.type == "mean":
        return kit.mean_pool()
    if params.type == "max":
        return kit.max_pool()
    if params.type == "attention":
        return kit.attention_pool(hidden, params.hidden_dim or hidden)
    raise PluginError(
        f"Pooling.type {params.type!r} not in {{mean, max, attention}}", stage="build_model"
    )


def _compose_pretrained(layers: Any, num_classes: int) -> Any:
    """Compose `Encoder` -> (`LoRA`) -> `Pooling` -> `Head` into a classifier (R1.1/R1.2/R1.3).

    Raises `ImportError` (with an install pointer) when `[huggingface]` is absent
    — the extras gate (R1.4); `PluginError` for a malformed composition.
    """
    try:
        import transformers  # type: ignore[import-not-found, unused-ignore]
    except ImportError as exc:
        raise ImportError(
            "Architecture ops Encoder/Pooling/Head require the [huggingface] extra "
            "(pip install 'ml-modelfoundry[huggingface]')"
        ) from exc
    transformers.logging.set_verbosity_error()  # quiet the benign LOAD REPORT (H.i finding #3)
    from transformers import AutoModel

    encoder_p: EncoderParams | None = None
    lora_p: LoRAParams | None = None
    pooling_p: PoolingParams | None = None
    head_p: HeadParams | None = None
    for i, layer in enumerate(layers):
        if not isinstance(layer, dict) or "op" not in layer:
            raise PluginError(
                f"Architecture.layers[{i}] must be a mapping with an 'op' key", stage="build_model"
            )
        op = layer["op"]
        if op not in ("Encoder", "LoRA", "Pooling", "Head"):
            raise PluginError(
                f"the pretrained-encoder path composes only Encoder/LoRA/Pooling/Head; got {op!r}",
                stage="build_model",
            )
        params = _validate(
            f"layers[{i}]", op, ARCHITECTURE_OPERATIONS[op].param_model, _without_op(layer)
        )
        if op == "Encoder":
            encoder_p = params
        elif op == "LoRA":
            lora_p = params
        elif op == "Pooling":
            pooling_p = params
        else:
            head_p = params

    if encoder_p is None or head_p is None:
        raise PluginError(
            "the pretrained-encoder path requires an Encoder and a Head op", stage="build_model"
        )
    if encoder_p.source != "huggingface":
        raise PluginError(
            f"Encoder.source {encoder_p.source!r} not supported (only 'huggingface' today; "
            "other sources add later without a contract change)",
            stage="build_model",
        )
    if head_p.num_classes != num_classes:
        raise PluginError(
            f"Head.num_classes ({head_p.num_classes}) must match Architecture.num_classes "
            f"({num_classes})",
            stage="build_model",
        )
    if pooling_p is None:
        pooling_p = PoolingParams()  # default: mean pooling

    kit = _hf_kit()
    encoder = AutoModel.from_pretrained(encoder_p.id, local_files_only=True)
    if encoder_p.frozen:
        for p in encoder.parameters():
            p.requires_grad_(False)
    hidden = int(encoder.config.hidden_size)
    if lora_p is not None:
        # peft injects trainable low-rank adapters into the named modules and
        # freezes the base (R1.2). `hidden` is read from the base config before
        # wrapping; the peft wrapper preserves `.config` and the forward signature.
        encoder = _apply_lora(encoder, lora_p)
    pooling = _build_pooling(kit, pooling_p, hidden)
    head = kit.mlp_head(hidden, list(head_p.hidden_dims), head_p.num_classes)
    return kit.classifier(encoder, pooling, head)


def _apply_lora(encoder: Any, params: LoRAParams) -> Any:
    try:
        from peft import LoraConfig, get_peft_model  # type: ignore[import-not-found, unused-ignore]
    except ImportError as exc:
        raise ImportError(
            "the LoRA architecture op requires the [huggingface] extra "
            "(pip install 'ml-modelfoundry[huggingface]')"
        ) from exc
    config = LoraConfig(
        r=params.rank,
        lora_alpha=params.alpha,
        lora_dropout=params.dropout,
        target_modules=list(params.target_modules),
        bias="none",
    )
    return get_peft_model(encoder, config)
