# Follow-up investigation — does anything bear fruit beneath the confounds?

Goal: recover treatment effects that the univariate, recording-level tests
missed because cell **state**, **state transitions**, and **cell–cell
contact** dominate the variance. Four families of analysis were run on the
existing IC295 results (recording = experimental unit throughout); reproduce
with `python scripts/run_followup.py` and `scripts/plot_followup.py`.

## TL;DR

| analysis | result |
|---|---|
| **Multivariate (recording-level)** | **WIN** — KO is robustly distinguishable from WT (PERMANOVA p=0.004, leave-one-recording-out AUC=0.80, perm p=0.022), with a coherent fingerprint. Invisible to univariate tests. |
| Dynamics (transitions, dwell, contact) | No treatment effect; **contact analysis is data-starved** at this density (only 2–5 recordings have enough contact events). |
| Interactions (treatment×density) | No significant interaction (and density varies too little within recordings to estimate slopes well). |
| Clean-cell subset | **Backfired** — filtering to stable/non-dividing/in-view cells *lost* the KO signal (less power; the effect isn't confined to "clean" cells). |
| Recurring **vehicle (WT vs DMSO)** effect | Multivariate-significant (AUC=0.83) + shows up in rounded-dwell and clean-cell speed → batch/vehicle variance is large. |

## The win: KO has a real, multivariate phenotype

A PERMANOVA + leave-one-recording-out logistic classifier on the 12-feature
recording vector separates **KO from WT** even though no single metric
survived Bonferroni:

- PERMANOVA pseudo-F=2.62, **p=0.004** (survives Bonferroni over the 5
  contrasts tested; replicates an independent earlier run at p≈0.001).
- Leave-one-recording-out **AUC=0.80**, permutation p=0.022 — you can
  classify a held-out recording as KO vs WT 80% of the time.

**Fingerprint** (`ko_fingerprint.png`, Cohen's d, KO−WT): KO **spread cells
are rounder and more compact** — ↓eccentricity (d=−1.8), ↑circularity
(+1.6), ↑solidity (+0.8), ↑frac_rounded (+0.7) — **and migrate less
directionally** (↓persistence −1.3, ↓straightness). A coherent
"rounder, less persistent" morphology+motility shift.

`GOF` shows no significant multivariate phenotype (AUC=0.53); the **drug arm
is null by every method** (Y1 AUC=0.34, OT AUC=0.44; drug omnibus p=0.47) —
either no effect or, more likely given the power analysis, too small to see
at n=8.

> Caveat: the 12 features were chosen by judgement (exploratory, not
> pre-registered). KO-vs-WT is reported as robust because it survives
> multiple-comparison correction, is concordant across two methods
> (PERMANOVA + classifier) and an independent prior run, and is biologically
> coherent. The 2-D PCA (`multivariate_genetic_pca.png`) shows only partial
> visual separation — expected, since the discriminating direction is
> multivariate, not the top 2 PCs.

## The informative nulls

- **Dynamics found no treatment effect** on state-transition rate, dwell
  times, or contact response — but the contact-triggered analyses are
  **starved for events**: at this plating density most cells are isolated, so
  only 1–5 recordings/condition have ≥3 contact-onset events. *We cannot
  test contact inhibition of locomotion with this data* → a direct argument
  for **denser/larger fields** if CIL is of interest.
- **Clean-cell subsetting reduced power and erased the KO eccentricity
  signal** (p 0.014 → 0.26). The KO phenotype is **not** confined to stable,
  non-dividing cells — over-filtering hurts. Don't condition on state.
- **treatment×density** slopes trend negative for KO/GOF (crowding slows
  them more than WT) but n.s. — suggestive, underpowered.

## The vehicle effect keeps reappearing

WT vs DMSO is multivariate-significant (AUC=0.83, PERMANOVA p=0.029) and also
shows up in **rounded dwell time** (p=0.010) and **clean-cell spread speed**
(p=0.029). DMSO cells are less solid/circular, divide a bit more, stay
rounded for shorter. This is batch/vehicle/handling variance, and it is **as
strong as or stronger than the genetic treatment effect** — so (a) drug
effects must be read strictly vs DMSO, never WT, and (b) controlling batch by
design is a priority (see below).

## What this means for next steps (evidence-weighted)

1. **Adopt multivariate as the primary readout.** It already recovered KO;
   report PERMANOVA + LORO-AUC + the loadings fingerprint per contrast. Apply
   it to future drug experiments to bound effect sizes.
2. **The drug arm needs power, not cleverness** — no analysis rescued it.
   Dose-response, more biological replicates (~25/condition for d≈0.8 per the
   power analysis), and batch-controlled design.
3. **To study contact/CIL, change the imaging** — denser plating or larger /
   tiled fields so contact events aren't rare. (Validates the user's
   "different recording conditions" instinct, *for the contact question
   specifically*.)
4. **Don't over-filter cells** — clean-subsetting cost more signal than it
   removed noise.
5. **Design out the batch effect** — paired/same-plate controls, randomised
   acquisition, and ideally differentially-labelled WT+KO **co-culture in one
   field** (kills batch + density confounds for the genetic arm).

## Figures (regenerate into `analysis_out/`, gitignored)

`python scripts/plot_multivariate.py` writes the explain-and-illustrate set:

- **`mv_story_panel.png`** — the whole argument in six panels: (A) *why
  multivariate* — single features don't survive Bonferroni but the joint
  test does; (B) held-out leave-one-recording-out scores cleanly split
  WT/KO; (C) ROC (AUC=0.80); (D) permutation null (the classifier isn't just
  overfitting); (E) effect across all contrasts (KO + vehicle separate, drug
  arm flat); (F) the Cohen's-d fingerprint.
- **`mv_feature_heatmap.png`** — recordings × features; the KO shift is
  modest/noisy per recording and spread across features (why aggregation is
  needed; eccentricity is the strongest single axis).
- **`mv_top_pair.png`** — the top-2 features overlap per-axis, separate more
  when combined.
- `plot_followup.py` also writes the plain PCA + fingerprint.

*Analyses: `maskviewer/analysis/{multivariate,dynamics,interactions,
feature_tables}.py`. Figures in `analysis_out/` (gitignored).*
