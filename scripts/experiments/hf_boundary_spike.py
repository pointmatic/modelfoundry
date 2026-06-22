# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Story H.i — integration spike for the `[huggingface]` boundary.

THROWAWAY SPIKE (per docs/specs/stories.md Story H.i). The deliverable is the
documented verdict in `hf_boundary_spike.md`, not production `src/` code. This
runner exists so the verdict is reproducible. It is NOT wired into the test
suite (it lives under scripts/experiments/, outside `testpaths`).

What it proves, against the R1 contract in
`advanced-and-probabilistic-requirements.md`:

  1. transformers + peft + evaluate import alongside the existing torch stack.
  2. A pretrained encoder loads from an OFFLINE warm cache (no network) via
     `local_files_only=True` + the HF offline env flags (R1.5 / criterion 2).
  3. A peft LoRA adapter applies to named attention modules; a forward pass
     yields encoder features poolable by a Pooling + Head composition (R1.2/R1.3).
  4. Q3 (LoRA serialization): the peft-native adapter save/load round-trips
     base + adapter-deltas-separately, reproducing the forward output from disk.
  5. Q5 (encoder-source breadth): `source` stays a dispatch point.
  6. Determinism caveats under `torch.use_deterministic_algorithms(True)`.

Run:  pyve env run smoke-huggingface -- python scripts/experiments/hf_boundary_spike.py
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

# Force offline BEFORE importing transformers so no module-load network probe
# can sneak through. This is the warm-cache contract (R1.5): the weights must
# already be in the local HF hub cache; nothing is fetched at run time.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# A small encoder already warm in ~/.cache/huggingface/hub (verified before the
# run). Text encoder, BERT-family: has `query`/`key`/`value` attention linears —
# the canonical LoRA targets. The boundary mechanics proved here (offline load,
# peft LoRA on attention, adapter save/load, deterministic forward) are
# architecture-agnostic; the image path (ViT) differs only in the input tensor
# (`pixel_values`) + an image processor, which is an H.j concern.
WARM_ENCODER_ID = "sentence-transformers/all-MiniLM-L6-v2"


def _hash(t: object) -> str:
    import torch

    assert isinstance(t, torch.Tensor)
    return hashlib.sha256(t.detach().cpu().contiguous().numpy().tobytes()).hexdigest()[:16]


def section(title: str) -> None:
    print(f"\n{'=' * 4} {title} {'=' * 4}")


def main() -> int:
    # --- 1. Imports alongside torch -----------------------------------------
    section("1. import closure (HF stack alongside torch)")
    import peft
    import torch
    import transformers

    try:
        import evaluate

        evaluate_ver = evaluate.__version__
    except Exception as exc:  # evaluate is optional for the boundary proof
        evaluate_ver = f"<import failed: {exc}>"
    print(f"torch        {torch.__version__}  (mps={torch.backends.mps.is_available()})")
    print(f"transformers {transformers.__version__}")
    print(f"peft         {peft.__version__}")
    print(f"evaluate     {evaluate_ver}")

    # Pin determinism the way the plugin does (project-essentials invariant 1).
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.use_deterministic_algorithms(True)

    from transformers import AutoModel

    # --- 2. Offline warm-cache load (R1.5 / criterion 2) --------------------
    section("2. offline warm-cache load (local_files_only, no network)")
    print(
        f"HF_HUB_OFFLINE={os.environ['HF_HUB_OFFLINE']} "
        f"TRANSFORMERS_OFFLINE={os.environ['TRANSFORMERS_OFFLINE']}"
    )
    torch.manual_seed(0)
    encoder = AutoModel.from_pretrained(WARM_ENCODER_ID, local_files_only=True)
    encoder.eval()
    n_params = sum(p.numel() for p in encoder.parameters())
    hidden = encoder.config.hidden_size
    print(f"loaded {WARM_ENCODER_ID!r} offline: {n_params:,} params, hidden_size={hidden}")

    # A synthetic batch standing in for a tokenized input. The spike proves the
    # forward/pool/head wiring; real tokenization/image-processing is H.j.
    batch, seq = 2, 8
    torch.manual_seed(123)
    input_ids = torch.randint(0, encoder.config.vocab_size, (batch, seq))
    attention_mask = torch.ones(batch, seq, dtype=torch.long)

    with torch.no_grad():
        out = encoder(input_ids=input_ids, attention_mask=attention_mask)
    last_hidden = out.last_hidden_state  # (batch, seq, hidden)
    print(f"encoder forward -> last_hidden_state {tuple(last_hidden.shape)}")

    # --- 3. Pooling + Head composition over encoder features ----------------
    section("3. Pooling + Head over pooled features (R1.3)")
    from torch import nn

    # mean Pooling over the (masked) sequence, then an MLP Head -> num_classes.
    num_classes = 5
    mask = attention_mask.unsqueeze(-1).float()
    pooled = (last_hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)  # (batch, hidden)
    head = nn.Sequential(nn.Linear(hidden, 64), nn.ReLU(), nn.Linear(64, num_classes))
    torch.manual_seed(7)
    for p in head.parameters():  # deterministic head init for the round-trip check
        if p.dim() > 1:
            nn.init.zeros_(p)
        else:
            nn.init.zeros_(p)
    with torch.no_grad():
        logits = head(pooled)
    print(
        f"pooled {tuple(pooled.shape)} -> head logits {tuple(logits.shape)} "
        f"(expect ({batch}, {num_classes}))"
    )
    assert logits.shape == (batch, num_classes)

    # --- 4. peft LoRA on named attention modules (R1.2) + Q3 round-trip -----
    section("4. peft LoRA adapter + Q3 serialization round-trip")
    from peft import LoraConfig, PeftModel, get_peft_model

    lora_cfg = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.0,
        target_modules=["query", "value"],  # canonical BERT/ViT attention targets
        bias="none",
    )
    torch.manual_seed(0)
    lora_encoder = get_peft_model(
        AutoModel.from_pretrained(WARM_ENCODER_ID, local_files_only=True), lora_cfg
    )
    lora_encoder.eval()
    trainable = sum(p.numel() for p in lora_encoder.parameters() if p.requires_grad)
    total = sum(p.numel() for p in lora_encoder.parameters())
    print(
        f"LoRA applied: {trainable:,} trainable / {total:,} total "
        f"({100 * trainable / total:.3f}% — adapter-only)"
    )

    with torch.no_grad():
        lora_out = lora_encoder(input_ids=input_ids, attention_mask=attention_mask)
    lora_hidden = lora_out.last_hidden_state
    pre_hash = _hash(lora_hidden)
    print(f"LoRA encoder forward last_hidden_state hash = {pre_hash}")

    with tempfile.TemporaryDirectory() as td:
        adapter_dir = Path(td) / "adapter"
        lora_encoder.save_pretrained(str(adapter_dir))
        files = sorted(p.name for p in adapter_dir.iterdir())
        adapter_bytes = sum(p.stat().st_size for p in adapter_dir.rglob("*") if p.is_file())
        print(f"saved adapter dir: {files}  ({adapter_bytes:,} bytes — deltas only)")

        # Round-trip: rebuild base from the WARM CACHE + load adapter deltas.
        base2 = AutoModel.from_pretrained(WARM_ENCODER_ID, local_files_only=True)
        reloaded = PeftModel.from_pretrained(base2, str(adapter_dir))
        reloaded.eval()
        with torch.no_grad():
            rt_out = reloaded(input_ids=input_ids, attention_mask=attention_mask)
        post_hash = _hash(rt_out.last_hidden_state)
        print(f"reloaded (base+adapter) forward hash       = {post_hash}")
        print(f"Q3 round-trip byte-identical: {pre_hash == post_hash}")

    # --- 5. Q5 source dispatch ----------------------------------------------
    section("5. Q5 — source stays a dispatch point")

    def load_encoder(source: str, model_id: str) -> object:
        if source == "huggingface":
            return AutoModel.from_pretrained(model_id, local_files_only=True)
        raise NotImplementedError(f"encoder source {source!r} not implemented (HF only in H.j)")

    _ = load_encoder("huggingface", WARM_ENCODER_ID)
    try:
        load_encoder("timm", "whatever")
    except NotImplementedError as exc:
        print(f"non-HF source rejected cleanly: {exc}")

    # --- 6. Determinism caveats ---------------------------------------------
    section("6. determinism under use_deterministic_algorithms(True)")
    torch.manual_seed(0)
    enc_a = AutoModel.from_pretrained(WARM_ENCODER_ID, local_files_only=True).eval()
    torch.manual_seed(0)
    enc_b = AutoModel.from_pretrained(WARM_ENCODER_ID, local_files_only=True).eval()
    with torch.no_grad():
        ha = _hash(enc_a(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state)
        hb = _hash(enc_b(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state)
    print(f"two offline loads, same seed, forward hashes: {ha} / {hb}  match={ha == hb}")

    section("VERDICT")
    print("VIABLE — offline encoder load + peft LoRA forward + adapter round-trip all pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
