"""Multivariate treatment-vs-control tests at the recording level.

Univariate per-metric tests diluted the genetic effect; aggregating the
whole recording-level feature vector recovers it. Two complementary tests
per contrast, plus a feature 'fingerprint':

  permanova   permutational MANOVA on z-scored Euclidean distances
              (handles p > n; permutation null on the labels).
  loro_auc    leave-ONE-RECORDING-out logistic classifier; AUC over the
              held-out predictions, with a label-permutation null (valid
              even though the model can overfit — the null overfits too).
  loadings    per-feature standardized mean difference (Cohen's d),
              ranked — what drives the separation.

Recording = experimental unit throughout (CV folds and permutations are by
recording, never by cell).
"""
from __future__ import annotations

import numpy as np

from . import feature_tables as ft

# Recording-level features (biologically meaningful; drop bookkeeping cols).
FEATURES = [
    "n_cells", "division_rate", "frac_rounded_mean",
    "mean_speed_rounded_mean", "mean_speed_spread_mean",
    "persistence_spread_mean", "straightness_spread_mean",
    "mean_area_um2_spread_mean", "mean_circularity_spread_mean",
    "mean_solidity_spread_mean", "mean_eccentricity_spread_mean",
    "mean_aspect_ratio_spread_mean",
]

# Only the SHAPE cluster is strongly collinear (circularity~solidity r=.92,
# ~eccentricity r=-.68) — one "roundness/compactness" axis — so it is the only
# group collapsed into a single PC1 score. Persistence + straightness were
# evaluated for the same treatment but are only weakly correlated (r=.25;
# local angular consistency vs global net/path ratio are distinct), so they
# are KEPT SEPARATE. A full pairwise scan (scripts/plot_multivariate.py
# correlation_fig) found no other cluster warranting combination.
SHAPE_FEATURES = ["mean_circularity_spread_mean", "mean_solidity_spread_mean",
                  "mean_eccentricity_spread_mean", "mean_aspect_ratio_spread_mean"]
# Non-redundant features + the one combined shape score.
FEATURES_COMBINED = [f for f in FEATURES if f not in SHAPE_FEATURES] + \
                    ["shape_roundness"]


def _pc1_score(df, features, orient_by, name):
    """Add `name` = PC1 of the standardised `features`, oriented so `orient_by`
    loads positive. Returns (df, {feature: loading}, variance_explained).
    Unsupervised (fit on all rows) — no label leakage."""
    X = df[features].to_numpy(float)
    mu = np.nanmean(X, 0)
    inds = np.where(~np.isfinite(X))
    X[inds] = np.take(mu, inds[1])
    sd = X.std(0)
    Xz = (X - X.mean(0)) / np.where(sd > 0, sd, 1.0)
    U, S, Vt = np.linalg.svd(Xz - Xz.mean(0), full_matrices=False)
    pc1 = Vt[0]
    if pc1[features.index(orient_by)] < 0:
        pc1 = -pc1
    out = df.copy()
    out[name] = (Xz - Xz.mean(0)) @ pc1
    return out, dict(zip(features, pc1)), float(S[0] ** 2 / np.sum(S ** 2))


def add_shape_score(df):
    """`shape_roundness` = PC1 of the shape cluster (higher = rounder/compact)."""
    return _pc1_score(df, SHAPE_FEATURES, "mean_circularity_spread_mean",
                      "shape_roundness")


def _matrix(df, conds, features=FEATURES):
    sub = df[df["condition"].isin(conds)].copy()
    X = sub[features].to_numpy(dtype=float)
    for j in range(X.shape[1]):                       # median-impute, z-score
        col = X[:, j]
        col[~np.isfinite(col)] = np.nanmedian(col)
        sd = col.std()
        X[:, j] = (col - col.mean()) / (sd if sd else 1.0)
    return X, sub["condition"].to_numpy()


def permanova(X, labels, b=4999, seed=0):
    rng = np.random.default_rng(seed)
    D2 = ((X[:, None, :] - X[None, :, :]) ** 2).sum(-1)    # squared euclidean
    N = len(labels)
    sst = D2.sum() / (2 * N)

    def within(lab):
        s = 0.0
        for g in np.unique(lab):
            m = np.where(lab == g)[0]
            s += D2[np.ix_(m, m)].sum() / (2 * len(m))
        return s

    a = len(np.unique(labels))
    ssw = within(labels)
    F = ((sst - ssw) / (a - 1)) / (ssw / (N - a))
    ge = 1
    for _ in range(b):
        sw = within(rng.permutation(labels))
        Fp = ((sst - sw) / (a - 1)) / (sw / (N - a))
        ge += Fp >= F
    return float(F), ge / (b + 1)


def loro_auc(X, y, b=999, seed=0):
    """y: 0/1. Leave-one-out logistic AUC + label-permutation p."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    rng = np.random.default_rng(seed)

    def loo_auc(yy):
        if len(np.unique(yy)) < 2:
            return 0.5
        scores = np.empty(len(yy))
        for i in range(len(yy)):
            tr = np.arange(len(yy)) != i
            if len(np.unique(yy[tr])) < 2:
                scores[i] = 0.5
                continue
            clf = LogisticRegression(C=0.3, max_iter=2000)
            clf.fit(X[tr], yy[tr])
            scores[i] = clf.predict_proba(X[i:i + 1])[0, 1]
        return roc_auc_score(yy, scores)

    obs = loo_auc(y)
    ge = 1
    for _ in range(b):
        ge += loo_auc(rng.permutation(y)) >= obs
    return float(obs), ge / (b + 1)


def loro_detail(X, y, b=999, seed=0):
    """Like loro_auc but also returns the held-out scores + permutation null
    (for ROC / score-distribution / null-histogram plots)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    def loo_scores(yy):
        s = np.full(len(yy), 0.5)
        for i in range(len(yy)):
            tr = np.arange(len(yy)) != i
            if len(np.unique(yy[tr])) < 2:
                continue
            clf = LogisticRegression(C=0.3, max_iter=2000).fit(X[tr], yy[tr])
            s[i] = clf.predict_proba(X[i:i + 1])[0, 1]
        return s

    rng = np.random.default_rng(seed)
    scores = loo_scores(y)
    auc = roc_auc_score(y, scores)
    perm = np.empty(b)
    for k in range(b):
        yp = rng.permutation(y)
        perm[k] = roc_auc_score(yp, loo_scores(yp))
    p = (int((perm >= auc).sum()) + 1) / (b + 1)
    return {"scores": scores, "auc": float(auc), "perm_aucs": perm, "p": p}


def univariate_p(df, ctrl, test, features=FEATURES):
    """Mann-Whitney p per feature (recording-level) — shows why single
    features 'fail' (multiple-comparison penalty) while the joint test holds."""
    from scipy.stats import mannwhitneyu
    out = []
    for f in features:
        a = df.loc[df["condition"] == ctrl, f].to_numpy(float)
        b = df.loc[df["condition"] == test, f].to_numpy(float)
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        try:
            p = float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
        except ValueError:
            p = 1.0
        out.append((f, p))
    return out


def loadings(df, ctrl, test, features=FEATURES, top=6):
    """Per-feature Cohen's d (test − ctrl), ranked by |d|."""
    out = []
    for f in features:
        a = df.loc[df["condition"] == ctrl, f].to_numpy(float)
        b = df.loc[df["condition"] == test, f].to_numpy(float)
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if len(a) < 2 or len(b) < 2:
            continue
        sp = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2) or 1.0
        out.append((f, (b.mean() - a.mean()) / sp))
    out.sort(key=lambda kv: -abs(kv[1]))
    return out[:top]


CONTRASTS = [("genetic", "WT", "KO"), ("genetic", "WT", "GOF"),
             ("drug", "DMSO", "Y1"), ("drug", "DMSO", "OT"),
             ("vehicle", "WT", "DMSO")]


def run():
    df = ft.recordings()
    print("=== MULTIVARIATE (recording-level) ===")
    results = {}
    # arm omnibus
    for arm, spec in ft.ARMS.items():
        X, lab = _matrix(df, spec["conditions"])
        F, p = permanova(X, lab)
        print(f"  omnibus {arm:8s} ({'/'.join(spec['conditions'])}): "
              f"PERMANOVA F={F:.2f} p={ft.stars(p)}")
        results[f"omnibus_{arm}"] = {"F": F, "p": p}
    # pairwise contrasts
    for arm, ctrl, test in CONTRASTS:
        X, lab = _matrix(df, [ctrl, test])
        y = (lab == test).astype(int)
        F, pp = permanova(X, lab)
        auc, pa = loro_auc(X, y)
        ld = loadings(df, ctrl, test)
        print(f"\n  {test} vs {ctrl} ({arm}): PERMANOVA F={F:.2f} p={ft.stars(pp)}"
              f" | LORO-AUC={auc:.2f} p={ft.stars(pa)}")
        print("     top features (Cohen's d): " +
              ", ".join(f"{f}={d:+.2f}" for f, d in ld))
        results[f"{test}_vs_{ctrl}"] = {
            "permanova_F": F, "permanova_p": pp, "loro_auc": auc,
            "loro_p": pa, "loadings": ld}
    return results
