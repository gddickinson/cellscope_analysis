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

## Refinement: the shape features are collinear → one roundness score

The fingerprint above lists eccentricity, circularity, solidity and aspect
ratio as separate bars, but they are **largely one axis** (across all 48
recordings: circularity↔solidity r=+0.92, circularity↔eccentricity r=−0.68,
frac_rounded↔circularity +0.61). Treating them as independent evidence
overstates the phenotype's richness.

**The test was still valid** (permutation/CV make no independence
assumption); only the interpretation needed fixing. The KO result is robust
to the redundancy — KO vs WT survives every de-collinearised variant:

| feature set | PERMANOVA p | LORO-AUC |
|---|---|---|
| full 12 | 0.004 | 0.80 |
| curated 6 (1 shape metric) | 0.030 | 0.86 |
| eccentricity_spread alone | 0.003 | 0.81 |
| circularity_spread alone | 0.005 | 0.77 |
| PCA-decorrelated (6 PCs) | 0.004 | 0.77 |

**So the four shape metrics are collapsed into one `shape_roundness` score**
= PC1 of the standardised cluster (62% of their variance; circularity +0.62,
solidity +0.58, eccentricity −0.51, aspect_ratio −0.14 → higher = rounder /
more compact). This single, interpretable axis is the *strongest* single
discriminator of all:

- **`shape_roundness`: WT=−0.14 vs KO=+1.69, MWU p=0.0006** (survives
  Bonferroni; beats any individual feature and the 12-feature test).
- GOF=+1.12 (also elevated), drug arm all negative.

So the honest statement of the phenotype is one dimension, not twelve:
**KO (and to a lesser extent GOF) spread cells are rounder / more compact**,
with reduced migratory persistence as a secondary, separable effect.
(`add_shape_score` in `multivariate.py`; figure `mv_shape_score.png`.) The
WT/GOF/KO-vs-drug-arm gap in the score is cross-arm and confounded by the
vehicle/batch effect — only the within-genetic KO-vs-WT contrast is valid.

**What else should be combined? Nothing (full scan in `mv_feature_correlation.png`).**
- **persistence + straightness** were evaluated for the same treatment but
  are only **weakly correlated (r=0.25)** — they measure distinct things
  (local angular consistency vs global net/path ratio), so combining them
  would discard ~38% real variance (their local-vs-global difference). **Kept
  separate.**
- `frac_rounded` is moderately correlated with the shape metrics (r≈0.6) but
  is a different construct (fraction of *time* in the rounded state vs the
  *morphology* of spread-state cells) — kept separate to avoid conflating two
  biological levels.
- All other pairs are |r| < 0.5. The shape cluster was the only group that
  warranted combination.

## Edge-truncated cells — excluded from shape; finding is robust

A mask cut by the image border gives unreliable area/circularity/eccentricity
and a centroid biased inward. Checked how the data handles it:

- **Shape/state is already edge-clean.** The CellScope pipeline voids
  edge-touching cell-frames to `unknown`, excluding them from all shape
  metrics + the rounded/spread call. In this corpus 85% of cells *never*
  touch the edge (frac_in_view median=1.0), only 47/313 have any edge frame,
  and 0 cells lack clean shape data. (`frac_in_view`, `n_frames_edge` per
  cell.)
- **The KO finding survives an extra cell-level edge filter unchanged** —
  dropping the 25 cells with frac_in_view < 0.8:

  | metric (KO vs WT) | all cells | frac_in_view ≥ 0.8 |
  |---|---|---|
  | eccentricity_spread | p=0.0047 | p=0.0047 |
  | circularity_spread | p=0.0207 | p=0.0207 |
  | **shape_roundness** | **p=0.0006** | **p=0.0006** |

  So the roundness phenotype is not an edge artefact.
- **Tracks:** state-based track metrics already exclude edge (edge→unknown).
  Centroid-based metrics now skip edge frames too (`maskviewer/analysis/
  edges.py` computes a per-frame edge flag from the masks; `dynamics` NaN-outs
  edge steps). The remaining track limitation is **field-of-view censoring**
  (cells that migrate *out* of frame are truncated) — a FOV issue, fixed by
  larger/tiled imaging, not edge masking.

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
- **`mv_shape_score.png`** — the **combined roundness score**: how the four
  collinear shape features collapse into PC1 (left), and the score by
  condition (right) — KO highest, GOF intermediate, WT ≈ 0 (KO vs WT
  p=0.0006). The honest, de-duplicated headline.
- **`mv_feature_correlation.png`** — full feature correlation matrix (why
  the shape cluster was combined and nothing else was).
- **`mv_phenotype_2d.png`** — the KO phenotype in its two *non-redundant*
  axes (shape_roundness vs persistence): KO is rounder AND less persistent.
- **`persistence_spread_arms.png`** / **`persistence_spread_effect.png`**
  (`scripts/plot_metric_arms.py`, reusable for any metric) — control-vs-
  treatment comparison of directional persistence. **Persistence is graded
  down in the genetic arm** (WT 0.39 → GOF 0.22 → KO 0.10; genetic-arm
  Kruskal-Wallis significant; KO-vs-WT Cohen's d ≈ −1.3 with a bootstrap CI
  excluding 0) — though the *Bonferroni-corrected* pairwise MWU is n.s. at
  n=8, so it is suggestive, not Bonferroni-robust. The drug arm is flat. This
  corroborates the "less persistent" secondary axis of the KO phenotype.
  Run for the other spread metrics too (`--metric straightness_spread |
  mean_speed_spread | shape_roundness`): **shape_roundness** is the robust hit
  (genetic KW **, KO-vs-WT Bonferroni **), persistence is suggestive, while
  **straightness and speed are flat everywhere** (all n.s.). So the KO
  phenotype is specifically *rounder + lower local persistence*, with
  unchanged global straightness and speed — and persistence dropping while
  straightness doesn't is exactly why those two were not merged.

All feature-based plots use the **de-duplicated** set (shape→`shape_roundness`):
the fingerprint, heatmap, PCA and this scatter show one roundness axis, not
four collinear bars. The plots that *do* still show circularity/eccentricity
individually do so on purpose — the correlation matrix (to justify combining),
the `mv_shape_score` loadings (to show the inputs), and story-panel A (single
features fail Bonferroni, the combined score doesn't).
- `plot_followup.py` also writes the plain PCA + fingerprint.

*Analyses: `maskviewer/analysis/{multivariate,dynamics,interactions,
feature_tables}.py`. Figures in `analysis_out/` (gitignored).*
