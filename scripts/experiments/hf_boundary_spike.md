# Story H.i — `[huggingface]` integration-spike findings

**Type:** throwaway integration spike (de-risk the R1 boundary before H.j/H.k).
**Deliverable:** this verdict + the documented Q3/Q5 decisions. No shipped `src/` change.
**Reproducer:** [hf_boundary_spike.py](hf_boundary_spike.py) (text encoder, full boundary) + an inline
ViT image-path proof (recorded below). Run in the `smoke-huggingface` env.

## Verdict: VIABLE — build H.j/H.k as planned

Every boundary mechanic R1 needs works end-to-end against the installed HF stack, **offline**, and
the peft adapter round-trips byte-identically. No blocker found. The findings below are *inputs to
H.j/H.k*, not reasons to re-scope.

## What was proven

Two encoders exercised — a warm text encoder (`sentence-transformers/all-MiniLM-L6-v2`, 22.7M params)
and a seeded tiny ViT (`WinKawaks/vit-tiny-patch16-224`, 5.6M params, the R1 image modality). The
boundary mechanics are architecture-agnostic; the image path differs only in the input tensor
(`pixel_values` vs `input_ids`) and a future image processor.

| Spike task | Outcome |
|---|---|
| 1. HF stack imports alongside torch | ✅ `transformers 5.12.1`, `peft 0.19.1`, `evaluate 0.4.6`, `torch 2.12.1` coexist in one venv |
| 2. Offline warm-cache load (R1.5 / criterion 2) | ✅ `AutoModel.from_pretrained(id, local_files_only=True)` under `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` loads with **zero network** for both encoders |
| 3. LoRA forward → poolable features (R1.2/R1.3) | ✅ text: `last_hidden_state (2, 8, 384)`; ViT: `(2, 197, 192)` = CLS + 196 patches; mean-pool + MLP head → `(batch, num_classes)` |
| 4. Q3 LoRA serialization round-trip | ✅ peft adapter dir (~300 KB: `adapter_config.json` + `adapter_model.safetensors` + `README.md`, **no base weights**) reloads on top of the warm-cache base → **byte-identical** forward output |
| 5. Q5 source dispatch | ✅ `source` is a clean dispatch point; non-HF source rejects with `NotImplementedError`, no contract change needed to add sources later |
| 6. Determinism | ✅ two offline loads + same seed → byte-identical forward hash under `use_deterministic_algorithms(True)` (CPU, eval/forward) |

## Decisions settled

### Q3 — LoRA serialization: **base + adapter-deltas separately** (confirmed)

peft's native `save_pretrained` writes **only** the adapter (`adapter_model.safetensors` + an
`adapter_config.json` that records `base_model_name_or_path`). Round-trip is
`PeftModel.from_pretrained(AutoModel.from_pretrained(id, local_files_only=True), adapter_dir)` and
reproduces the forward output **byte-identically** (verified for both encoders). The base never gets
re-persisted into the ModelInstance — it is supplied by the offline warm cache. This is the §3-plan
default, now evidence-backed:

- **Instance size**: adapter is ~300 KB vs a multi-MB–GB base. Merged-weights serialization (the
  deferred Q3 alternative) is unnecessary and wasteful here.
- **H.k serialization shape**: `model/` persists the peft adapter dir + an `architecture.json` that
  records the `Encoder.id` (so the base is re-fetched from the warm cache on load). The round-trip
  contract (criterion 9) is `architecture.json` (encoder id + LoRA config + Pooling/Head) + adapter
  weights + the trained Head weights — the base is *referenced*, not stored.

### Q5 — encoder-source breadth: **`huggingface` only, `source` stays a dispatch point** (confirmed)

`EncoderParams.source` already defaults to `"huggingface"`. `AutoModel.from_pretrained` is the HF
dispatch; the spike showed a trivial `if source == "huggingface": ... else: raise NotImplementedError`
admits other sources later (timm, local checkpoints) **without a recipe-contract change**. Implement
HF only in H.j.

## Findings that feed H.j / H.k (load-bearing)

1. **transformers resolved to 5.12.1, not 4.x.** `pyproject` declares `transformers>=4.40`, but the
   resolver pulls **5.x** (a major release with renamed internals). H.j must decide: pin a supported
   major, or be version-aware. This directly causes finding #2.

2. **LoRA `target_modules` names are architecture- AND transformers-version-dependent.** The BERT-family
   MiniLM uses `query`/`value`; the **ViT in transformers 5.x uses `q_proj`/`v_proj`/`k_proj`/`o_proj`**
   (renamed from 4.x's `query`/`key`/`value`). A recipe naming the wrong modules gets a peft
   "target module not found" error **at materialize time**. H.k should either (a) validate
   `target_modules` against the instantiated encoder's module names with a helpful error, or (b)
   document the per-model names. This is the single biggest authoring footgun the spike surfaced.

3. **Loading `AutoModel` (encoder-only) from a `*ForImageClassification` checkpoint prints a LOAD
   REPORT** (UNEXPECTED `classifier.*`, MISSING `pooler.*`). For the Encoder→Pooling→Head composition
   this is *correct* — we deliberately drop the pretrained classifier and add our own Head — but H.j
   should (a) quiet the report or surface it intentionally, and (b) note that any freshly-initialized
   submodule (e.g. the ViT `pooler`) is **entropy-seeded unless covered by `prepare_for_build(seed)`**.
   The determinism contract (project-essentials invariant; weight-init must be seeded *before*
   `build_model`) extends to these HF-initialized tensors, not just our Head.

4. **peft emits a benign `save_pretrained` warning** ("Could not find a config file in `<id>` - will
   assume that the vocabulary was not modified"). Harmless for our use (we never modify the tokenizer
   vocab); H.l can assert it does not break the round-trip.

5. **Offline contract requires the env flags, not just `local_files_only`.** Setting
   `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` **before** importing `transformers` is the belt-and-
   suspenders form; `local_files_only=True` on the call alone is sufficient for `from_pretrained` but
   the env flags also gate any module-load-time metadata probe. H.j's offline path should set both.

## Determinism caveats (carry into H.j/H.k/H.m)

- **Proven**: forward/eval determinism for both encoders on **CPU** under
  `use_deterministic_algorithms(True)` — byte-identical across reloads.
- **Not yet exercised** (out of scope for this spike, flagged for H.j/H.l):
  - the **training/backward** pass (only forward/eval was run) — whether any HF/peft op hard-errors
    under deterministic mode, per the project-essentials contract, is an H.j question;
  - **MPS** determinism for HF ops (the spike ran CPU);
  - seeding the HF-initialized submodules (ViT `pooler`, our Head) via `prepare_for_build(seed)` so
    weight init is reproducible (finding #3).

## Env / artifacts

- New durable env-requirements file `tests/integration/env/huggingface.txt` (referenced by the
  pre-declared `[env.smoke-huggingface]` in `pyve.toml`); the `smoke-huggingface` venv is now
  provisioned (`-e .[huggingface,pytorch]` + pytest tooling).
- Warm cache seeded with `WinKawaks/vit-tiny-patch16-224` (~22 MB) for H.j/H.l offline tests, beside
  the already-warm `sentence-transformers/all-MiniLM-L6-v2`.
