# CIFAR-10 best-results scoreboard + the bug-suppression story (H.f.9)

**Bottom line.** At the canonical regime on the full data the ordering is the textbook one —
**`resnet20` 0.7764 > `simple_cnn` 0.7305 > sklearn MLP 0.4653 > random 0.1012** — but that ordering
is *earned by data*: at the 3k scale the smaller `simple_cnn` (0.530) **beats** `resnet20` (0.453) —
the high-capacity net is data-starved — and `resnet20` only **crosses over at 30k** and widens its
lead at 50k (the capacity-vs-budget thesis, under one identical rigorous regime). The architecture
was **canonical and correct the entire time** (272,474 params, He-2015 CIFAR-ResNet, verified H.f.5);
its long-running underperformance was a **succession of train/eval-path bugs**, not the net. And even
the best rigorous run (0.7764) stays short of the published ~0.91 — the remaining gap is **training
data** (28k carved vs the paper's full 50k + official 10k test).

---

## As a learning narrative (curriculum)

Read this **after** training the same `resnet20` on the 3k (1,700-train) interactive notebook and
seeing a modest result. The arc the data tells:

1. **At 3k, casually (what you just did):** the interactive default (AdamW + early stopping) gives
   `resnet20` ≈ **0.30** — data-starved, *below* even the flattened-pixel MLP. Not a failure —
   expected.
2. **A more rigorous approach — hardware acceleration (Apple-silicon MPS) + the canonical regime
   (SGD 0.1 / cosine-160 / no early stopping) — run across all three dataset sizes:**

   | dataset | resnet20 | simple_cnn |
   |---|---:|---:|
   | 3k (1,700 train) | 0.453 | **0.530** |
   | 30k (17,000 train) | **0.733** | 0.707 |
   | 50k (28,330 train) | **0.776** | 0.731 |

   Two lessons at once: (a) rigor lifts the high-capacity net at *every* scale (3k `resnet20`
   0.30 → 0.45), but (b) **at 3k the smaller `simple_cnn` still wins** — capacity is wasted without
   data. `resnet20` only **crosses over at 30k** and widens its lead at 50k. *That* is what data
   buys, and why the 3k result was never going to be magical.
3. **The telling part — even rigor at 50k falls short of the benchmark.** 0.776 is still well below
   the published ~0.91. The remaining gap is *data the model never saw* (28,330 carved train vs the
   paper's full 50,000 + a separate official 10k test set), **not** the architecture or the regime.
   Chasing benchmark success on the **true full dataset** is a deliberate **future project**, not
   this one.

The internal rigor — the scoreboard, the bug history, the methodology — follows.

---

## 1. Best results

### The rigorous approach, by dataset size (3k → 30k → 50k)

The *identical* canonical regime (SGD 0.1 / cosine-160 / no early stop / crop+flip / MPS) at each
dataset size — only the data differs (source:
[canonical_scale_ladder_results.md](canonical_scale_ladder_results.md)):

| dataset (train) | resnet20 | simple_cnn | leader | sklearn MLP† | random† |
|---|---:|---:|---|---:|---:|
| 3k (1,700) | 0.4530 | **0.5300** | simple_cnn **+0.077** | 0.3520 | 0.0950 |
| 30k (17,000) | **0.7325** | 0.7073 | resnet20 **+0.025** | 0.4512 | 0.0993 |
| 50k (28,330) | **0.7764** | 0.7305 | resnet20 **+0.046** | 0.4653 | 0.1012 |

† baselines are regime-invariant (not trainer models); carried from the ladder.

**The capacity-vs-data crossover, in one table.** At 3k the smaller `simple_cnn` *wins* — `resnet20`
is data-starved. `resnet20` **crosses over at 30k** and **widens** its lead at 50k. Same architecture,
same rigorous regime throughout: capacity only pays off once the data is there. Even at 50k the best
run (0.7764) is short of the published ~0.91 — the true full 50k-train + official-10k-test protocol
is the deferred future project.

### Per model at 50k (28,330 train), by regime

| model | dynamic regime¹ | canonical regime² | **best** |
|---|---:|---:|---:|
| random | 0.1012 | — (regime-invariant) | **0.1012** |
| sklearn MLP | 0.4653 | — (regime-invariant) | **0.4653** |
| simple_cnn (~94k params) | 0.6722 | 0.7305 | **0.7305** |
| **resnet20 (272k params)** | 0.6792 | **0.7764** | **0.7764** |

¹ *dynamic* = AdamW lr 1e-3, cosine `T_max=40`, early stopping (patience 5), `color_jitter` on
([postfix_ladder.md](postfix_ladder.md), v0.10.2-equivalent — all early-stopping runs).
² *canonical* = SGD 0.1 + momentum 0.9 + Nesterov, cosine over 160 epochs, no early stopping,
crop+flip only ([canonical_comparison_results.md](canonical_comparison_results.md), v0.10.2). The
baselines are not trainer models, so the regime does not apply — they are identical across regimes
*and* instances (0.1012 / 0.4653 reproduce to the digit), which is why they are a trustworthy floor.

**High-vs-high:** ResNet-20 beats `simple_cnn` by **+0.0459** at the canonical regime, vs only
**+0.0070** at the dynamic regime — the canonical regime *widens* the capacity advantage (the
capacity-vs-budget thesis, at budget).

> **Note — "canonical regime" is a *bundle*.** "Dynamic" and "canonical" differ on **six axes at
> once** (optimizer AdamW→SGD, LR 1e-3→0.1, cosine horizon 40→160, early stopping on→off, epoch
> budget, `color_jitter` on→off). So the scoreboard makes a deliberate **bundle-level** claim — the
> rigorous approach vs the dynamic one, and (§ ladder) vs data scale — and does **not** attribute the
> gain to LR scheduling or early stopping *individually*. Decomposing per-knob is a possible future
> ablation (not needed for the data-scaling narrative); the older H.f.4/H.f.5 schedule/stopping
> experiments can't substitute — they ran at 1,700 scale *and* under the now-fixed best-weights/
> early-stopping bugs.

### Per model, by data scale — casual/dynamic regime (the interactive-notebook experience)

The contrast to the rigorous ladder above: the AdamW + early-stopping + `color_jitter` regime a
student gets by default.

| model | 1,700 train | 17k train | 28k train |
|---|---:|---:|---:|
| random | 0.0950 | 0.0993 | 0.1012 |
| sklearn MLP | 0.3520 | 0.4512 | 0.4653 |
| simple_cnn | 0.4200 | 0.5956 | 0.6722 |
| resnet20 | 0.2990 | 0.5837 | 0.6792 |

ResNet-20 is **data-starved at 1,700** (0.299, *below* both the MLP and `simple_cnn`) and only
clears the MLP from 17k on — capacity needs data. The rigorous regime lifts every CNN cell here
(e.g. 1,700 `resnet20` 0.299 → 0.453, 28k 0.679 → 0.776). (Source:
[postfix_ladder.md](postfix_ladder.md).)

---

## 2. The accuracy was suppressed by bugs, not architecture

ResNet-20's measured accuracy was floored by a **succession of train/eval-path bugs, revealed
one-by-one** — each one masked the next (the accuracy is pinned by the worst active bug, so the
next is invisible until the prior is fixed), and each was plausibly rationalized at the time as
"low-data noise / data-starved / regime-bound." The sklearn MLP — trained through a different path
— stayed near its true level throughout and is the yardstick that exposes the cost:

| bug (fix) | mechanism | ResNet-20 vs the MLP yardstick |
|---|---|---|
| normalization units (v0.8.4, H.a) | 0–255 stats applied to a `[0,1]` image → `train_loss` pinned at ln(10) | **0.10 — equals random** |
| augment-before-normalize (v0.9.2, H.d) | `color_jitter` on the standardized tensor → `val_loss`→~15 | **~0.13 — below the MLP (0.34)** |
| best-weights not restored (v0.10.1, H.f.8) | early stopping shipped the final, not the best, epoch | 0.646 → 0.679 (edges MLP, *loses to* `simple_cnn`) |
| restore over-applied (v0.10.2, H.f.10) | no-early-stop run shipped ep8, not the converged model | 0.731 → 0.776 |
| + canonical regime (H.f.9) | SGD 0.1 / 160 ep vs AdamW / ~17 ep, drop `color_jitter` | **0.776 — beats the MLP by +0.31** |

The trajectory: **equals random → below the MLP → (four bugs peeled off, each masked as noise) →
beats the MLP with the advanced regime.** Architecture canonical throughout.

---

## 3. Methodological takeaway

Real-world model building requires **measured suspicion of bugs balanced against** domain and
statistical factors, proper architecture, sufficient data, adequate regime rigor, and compliance to
canonical approaches — underscored by **persistence when outcomes don't match expectations** and
**hesitation to draw conclusions without comprehensive trials**. This series is the case study: a
~26-point gap against a published benchmark was *repeatedly* explained away as noise, and each
explanation hid a real defect. The benchmark gap was the signal to keep digging, not to lower
expectations; the discriminating trials (cheapest-highest-information first — "can it overfit a tiny
set?" before any multi-hour run — then re-running the *full* comparison after every fix) are what
surfaced the bugs. A "regime" or "noise" verdict was never safe until bugs were ruled out with
evidence.

---

## 4. The canonical ResNet-20 run (detail)

[recipes/cifar10_resnet20_canonical.yml](../../recipes/cifar10_resnet20_canonical.yml) on the
crop+flip full instance, MPS, ~26 min, v0.10.2:

- `train_loss → 0.001` (fully fits train — capacity is not the limit).
- `val_accuracy` → **0.7936 @ ep160**, peak 0.7990 @ ep91; **test 0.7764**.
- `val_loss` bottoms at ep8 then rises under overfitting while `val_accuracy` climbs — the
  cross-entropy signature that drove the H.f.10 bug.

**Residual gap to ~0.91 is data, not bug.** The model trains on 28,330 images (~57% of CIFAR-10's
50k; the rest is carved into val + test) and the paper trains on the full 50k + a separate official
10k test set. The full-50k canonical protocol is expected to add several points; the small remainder
is minor regime detail (PyTorch default `kaiming_uniform` init vs canonical `kaiming_normal`/fan-out
+ zero-init-residual). Closing it is the deferred **true-paper protocol** — source the official
labeled 10k test set (not on disk: the Kaggle `test/` is 300k unlabeled distractors) and train on the
full 50k.

---

## 5. Provenance (how the numbers were validated)

ResNet-20, full data, as bugs were removed: **0.646 → 0.679 (H.f.8) → 0.731 → 0.776 (H.f.10 +
canonical regime).** The two fixes this investigation shipped are cache-invalidating patches with
regression guards (`tests/integration/test_pytorch_trainer.py`); see [CHANGELOG.md](../../CHANGELOG.md)
(v0.10.1, v0.10.2) and the stories (H.f.8, H.f.9, H.f.10). Sibling findings:
[overfit_diagnostic.md](overfit_diagnostic.md) (ResNet-20 *can* learn — `train_loss→0.015`),
[postfix_ladder.md](postfix_ladder.md) (the data-scale × model ladder).

**Reproduce:** `modelfoundry materialize recipes/cifar10_resnet20_canonical.yml` (canonical run) and
`python scripts/experiments/canonical_comparison.py` (the scoreboard) — both require the crop+flip
full instance materialized under `./data`, v0.10.2+.

## Still open (H.f.9 follow-ons)

- **Per-knob regime ablation (optional).** Single-factor sweeps from the canonical baseline (early
  stopping on/off — now correct under v0.10.2; schedule cosine / constant / `reduce_on_plateau`;
  optimizer SGD/AdamW; ±`color_jitter`; 40 vs 160 epochs) would decompose *which* canonical choice
  contributes what. Not needed for the bundle-level data-scaling narrative; a candidate future
  experiment.
- **Robustness / CIFAR-10-C** — route the converged models through
  [recipes/cifar10c-eval.yaml](../../recipes/cifar10c-eval.yaml); the BN-heavier ResNet may degrade
  more under noise (testable now on the best-weights-fixed checkpoints).
- **True-paper protocol** — full 50k train + official 10k test (upstream DataRefinery).
