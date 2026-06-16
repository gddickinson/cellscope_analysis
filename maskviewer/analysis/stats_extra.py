"""Extra statistics for the cross-recording comparison (GUI-free).

Beyond the per-contrast KW / Mann-Whitney tests: a Benjamini-Hochberg FDR (less
conservative than Bonferroni across the many metrics/contrasts), percentile
**bootstrap CIs** on effect sizes, and a **recording-clustered** cell-level test
(cluster-robust OLS — uses within-recording structure for more power than the
recording-as-unit test, while still respecting that cells in a dish are not
independent). Dependency-free (numpy + scipy only — no statsmodels).
"""
from __future__ import annotations

import numpy as np


def benjamini_hochberg(pvals) -> np.ndarray:
    """Benjamini-Hochberg FDR-adjusted q-values, in the **input order** (NaNs pass
    through). Controls the expected false-discovery rate — less conservative than the
    Bonferroni family-wise correction when testing many metrics / contrasts."""
    p = np.asarray(pvals, float)
    out = np.full(p.size, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return out
    idx = np.where(ok)[0]
    order = idx[np.argsort(p[idx])]                   # ascending by p
    q = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(q[::-1])[::-1]          # enforce monotone non-decreasing
    out[order] = np.clip(q, 0.0, 1.0)
    return out


def bootstrap_ci(control, test, statistic, n_boot=2000, ci=0.95, seed=0):
    """Percentile bootstrap ``(lo, hi)`` of ``statistic(control, test)`` by resampling
    each group with replacement. Deterministic (fixed ``seed``). NaN bounds if either
    group has < 2 finite values."""
    a = np.asarray(control, float); a = a[np.isfinite(a)]
    b = np.asarray(test, float); b = b[np.isfinite(b)]
    if a.size < 2 or b.size < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    vals = np.empty(int(n_boot))
    for i in range(int(n_boot)):
        sa = a[rng.integers(0, a.size, a.size)]
        sb = b[rng.integers(0, b.size, b.size)]
        vals[i] = statistic(sa, sb)
    finite = vals[np.isfinite(vals)]
    if finite.size < 0.5 * vals.size:        # too many degenerate resamples (e.g.
        return (np.nan, np.nan)              # zero-variance groups) → CI unreliable
    vals = finite
    lo = (1.0 - ci) / 2.0 * 100.0
    return (float(np.percentile(vals, lo)), float(np.percentile(vals, 100.0 - lo)))


def cluster_robust_p(df, metric, group_col="condition", cluster_col="recording"):
    """p-value of the cell-level **group** effect with **recording-clustered** robust
    standard errors (Liang-Zeger CR1).

    Fits OLS ``metric ~ group`` on the *per-cell* data but corrects the standard error
    for within-recording correlation — cells in one dish are not independent — then a
    t-test with df = (#recordings − 1). Uses all cells for power while keeping the
    recording the unit of inference: a dependency-free stand-in for a random-intercept
    mixed model (the project's stats stay statsmodels-free). NaN unless exactly two
    groups with ≥3 recordings and ≥6 cells total."""
    from scipy.stats import t as _t
    d = df[[metric, group_col, cluster_col]].dropna()
    groups = sorted(d[group_col].unique())
    if len(groups) != 2 or d[cluster_col].nunique() < 3 or len(d) < 6:
        return np.nan
    y = d[metric].to_numpy(float)
    x1 = (d[group_col].to_numpy() == groups[1]).astype(float)
    X = np.column_stack([np.ones(y.size), x1])
    try:
        XtX_inv = np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return np.nan
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    clusters = d[cluster_col].to_numpy()
    uniq = np.unique(clusters)
    meat = np.zeros((2, 2))
    for c in uniq:                                    # Σ_g X_g' u_g u_g' X_g
        sel = clusters == c
        sc = X[sel].T @ resid[sel]
        meat += np.outer(sc, sc)
    G, n = uniq.size, y.size
    adj = (G / (G - 1.0)) * ((n - 1.0) / (n - 2.0))   # CR1 small-sample correction
    se = float(np.sqrt(max(adj * (XtX_inv @ meat @ XtX_inv)[1, 1], 0.0)))
    if se == 0.0:
        return np.nan
    return float(2.0 * _t.sf(abs(beta[1] / se), df=G - 1))
