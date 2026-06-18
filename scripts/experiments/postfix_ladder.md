# H.f.8 — honest ladder re-run after the restore-best-weights fix

**Context.** Story H.f.8 asked whether ResNet-20's H.f underperformance was a
training-regime limit or a residual bug. The cheap overfit diagnostic
(`overfit_diagnostic.py`) showed ResNet-20 *can* learn — on 400 images with no
augmentation it drives `train_loss` to **0.015**, below `simple_cnn`'s 0.105 —
so the forward/backward/residual path is sound. But chasing the train-vs-eval
gap surfaced a real training-path bug, and the H.f.4–H.f.7 numbers were all
produced *with* it.

**The bug (fixed in v0.10.1).** The trainer tracked the best-monitor weights and
promoted them to `model/weights/state_dict.pt`, but the runner evaluated the
in-memory **final-epoch** model and `save_model` then overwrote the promoted
weights with that final model. `run_training` never restored the best weights
into the model. Net effect: **early stopping stopped early but shipped the
`patience`-epochs-stale model** — there was no `restore_best_weights`. The fix
snapshots the best-monitor `state_dict` and restores it into the model before
`run_training` returns, so evaluation *and* persistence use the best epoch.
Cache-invalidating (materialized output changes); patch bump, no `schema_version`
change (pre-prod OR-9). Regression guard:
`tests/integration/test_pytorch_trainer.py::test_best_weights_are_restored_into_model_after_early_stop`.

**The re-run.** Same field as H.f.6/H.f.7 — `random` + sklearn `mlp` (cpu) vs
`simple_cnn` + `resnet20` (MPS, cosine `T_max=40` + early-stopping patience 5) —
across all three data scales, now with the fix.

| scale | model | pre-fix acc | post-fix acc | Δ | post epochs |
|---|---|---:|---:|---:|---:|
| 1700 | random | — | 0.0950 | — | — |
| 1700 | mlp | — | 0.3520 | — | 50 |
| 1700 | simple_cnn | — | 0.4200 | — | 27 |
| 1700 | resnet20 | — | 0.2990 | — | 14 |
| 10x | random | 0.0993 | 0.0993 | +0.0000 | — |
| 10x | mlp | 0.4512 | 0.4512 | +0.0000 | 50 |
| 10x | simple_cnn | 0.5441 | 0.5956 | +0.0515 | 19 |
| 10x | resnet20 | 0.5936 | 0.5837 | -0.0099 | 9 |
| full | random | 0.1012 | 0.1012 | -0.0000 | — |
| full | mlp | 0.4653 | 0.4653 | -0.0000 | 50 |
| full | simple_cnn | 0.6687 | 0.6722 | +0.0035 | 40 |
| full | resnet20 | 0.6458 | **0.6792** | **+0.0334** | 17 |

**Findings.**

1. **The fix's footprint is exactly the early-stopping models.** `random` / `mlp`
   reproduce their pre-fix numbers to the digit (they use the dummy / sklearn
   baseline plugins, not the PyTorch trainer) — a clean harness sanity check.
   `simple_cnn` at full barely moves (+0.0035; it ran the full 40 epochs, so
   final ≈ best). The gains land on the runs that early-stopped with best ≠
   final: `simple_cnn` 10x **+0.05** (stopped@19) and `resnet20` full **+0.033**
   (stopped@17).

2. **H.f.7's headline reversal was substantially the bug.** H.f.7 reported
   `simple_cnn 0.669` *edging* `resnet20 0.646` and attributed it to an
   "early-stopping × LR-schedule interaction." Post-fix at full data the
   canonical capacity ordering is restored: **`resnet20 0.6792` > `simple_cnn
   0.6722`**. The interaction was real, but its mechanism was this bug —
   `resnet20` early-stopped at epoch 17 and shipped a 5-epochs-stale model, while
   `simple_cnn` ran the full schedule.

3. **The residual gap to the published ~91% is regime, not (further) bug.** The
   net learns (overfit diagnostic). At full data `resnet20` reaches only ~0.68
   here because it trains ~17 epochs (early-stopped on val_loss) vs the canonical
   ~160, on ~28k carved train images vs the full 50k, with AdamW lr 1e-3 + cosine
   vs canonical SGD+momentum lr 0.1 + step decay, and PyTorch's default
   `kaiming_uniform` init rather than the canonical `kaiming_normal`/`fan_out` +
   zero-init-residual. Closing that gap is the deferred canonical-protocol
   reproduction (the official labeled 10k CIFAR-10 test set is **not** on disk —
   the Kaggle `test/` is 300k unlabeled distractors; sourcing it is upstream
   DataRefinery work).

4. **At 1700 `resnet20` stays data-starved** (0.299 < `simple_cnn` 0.420), as
   H.f.5 found — capacity needs data, and the fix does not change that.
