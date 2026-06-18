"""Statistics for the dataset comparison: per-contrast effect sizes (Cohen's d +
Mann-Whitney, Bonferroni over the metric panel), per-arm multivariate phenotype, and
cross-dataset concordance (do the same treatment effects reproduce in both datasets?).
Recording = unit (here one single-cell crop = one cell).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats as ss  # noqa: E402

from maskviewer.analysis import compare, metric_docs  # noqa: E402
import ds_config as cfg  # noqa: E402


def filter_tracks(per_rec):
    """Drop very short tracks (noisy motion); returns the filtered per-recording df."""
    if "frames_tracked" not in per_rec.columns:
        return per_rec.copy()
    return per_rec[per_rec["frames_tracked"] >= cfg.MIN_FRAMES].copy()


def condition_counts(per_rec):
    vc = per_rec["condition"].value_counts().to_dict()
    return {c: int(vc.get(c, 0)) for c in cfg.COND_ORDER if c in vc}


def contrast_effects(per_rec, control, test, metrics=None):
    """Cohen's d (test − control) + 95% CI + Mann-Whitney p (+ Bonferroni over the
    panel) for each metric, as a DataFrame sorted by |d|."""
    avail = [m for m in (metrics or cfg.KEY_METRICS) if m in per_rec.columns]
    df = pd.DataFrame(compare.forest_data(per_rec, control, test, metrics=avail))
    if df.empty:
        return df
    df["p_bonf"] = np.minimum(df["p"].to_numpy(float) * len(df), 1.0)
    df["label"] = df["metric"].map(metric_docs.column_label)
    df["control"], df["test"] = control, test
    return df


def all_contrast_effects(per_rec):
    return {(ctrl, test): contrast_effects(per_rec, ctrl, test)
            for _arm, ctrl, test in cfg.CONTRASTS}


def multivariate(per_rec):
    """Per-arm PERMANOVA p + leave-one-recording-out AUC over the curated KEY_METRICS
    (z-scored, median-imputed). Like `compare.multivariate_contrasts` but restricted to
    the interpretable panel and with reduced permutation counts (cfg.PERM_*) so the
    report runs inline — over all ~80 columns with the GUI defaults it is far too slow
    (and degenerate single-cell columns make it slower still)."""
    from maskviewer.analysis import multivariate as mv
    feats0 = [m for m in cfg.KEY_METRICS if m in per_rec.columns]
    out = []
    for arm, spec in cfg.ARMS.items():
        ctrl = spec["control"]
        for t in [c for c in spec["conditions"] if c != ctrl]:
            sub = per_rec[per_rec["condition"].isin([ctrl, t])]
            g = sub["condition"].to_numpy()
            n_c, n_t = int((g == ctrl).sum()), int((g == t).sum())
            row = {"arm": arm, "contrast": f"{t} vs {ctrl}", "n_ctrl": n_c,
                   "n_test": n_t, "n_features": 0, "permanova_p": None, "loro_auc": None}
            feats = [c for c in feats0 if np.nanstd(sub[c].to_numpy(float)) > 0]
            if n_c >= 2 and n_t >= 2 and len(feats) >= 2:
                X = sub[feats].to_numpy(float)
                med = np.nanmedian(X, axis=0)
                X = np.where(np.isfinite(X), X, med)          # median-impute NaNs
                X = (X - X.mean(0)) / np.where(X.std(0) > 0, X.std(0), 1.0)
                row["n_features"] = len(feats)
                try:
                    row["loro_auc"] = float(mv.loro_auc(
                        X, (g == t).astype(int), b=cfg.PERM_LORO)[0])
                    row["permanova_p"] = float(mv.permanova(
                        X, g, b=cfg.PERM_PMANOVA)[1])
                except Exception as exc:                      # pragma: no cover
                    print(f"  (multivariate {t} vs {ctrl} skipped: {exc})")
            out.append(row)
    return out


def concordance(eff_a, eff_b):
    """Align two same-contrast effect tables (datasets A, B) on metric → (merged_df,
    stats). `robust` = same-sign and Bonferroni-significant in BOTH datasets."""
    if eff_a is None or eff_b is None or eff_a.empty or eff_b.empty:
        return pd.DataFrame(), {}
    m = eff_a.merge(eff_b, on="metric", suffixes=("_a", "_b"))
    da, db = m["d_a"].to_numpy(float), m["d_b"].to_numpy(float)
    ok = np.isfinite(da) & np.isfinite(db)
    m = m[ok].copy()
    da, db = da[ok], db[ok]
    stats = {"n_metrics": int(len(m))}
    if len(m) >= 3:
        stats["pearson_r"] = float(ss.pearsonr(da, db)[0])
        stats["spearman_r"] = float(ss.spearmanr(da, db)[0])
    same_sign = np.sign(m["d_a"]) == np.sign(m["d_b"])
    sig_a, sig_b = m["p_bonf_a"] < 0.05, m["p_bonf_b"] < 0.05
    m["agree_sign"] = same_sign
    m["robust"] = same_sign & sig_a & sig_b
    m["label"] = m["label_a"]
    stats.update(n_agree_sign=int(same_sign.sum()), n_sig_a=int(sig_a.sum()),
                 n_sig_b=int(sig_b.sum()), n_robust=int(m["robust"].sum()))
    return m, stats


def summary_long(per_rec, metrics=None):
    """Tidy per-condition mean ± SEM (n recordings) for each metric."""
    rows = []
    for metric in (metrics or cfg.KEY_METRICS):
        for r in compare.per_condition_summary(per_rec, metric):
            rows.append({"metric": metric, "label": metric_docs.column_label(metric),
                         **r})
    return pd.DataFrame(rows)
