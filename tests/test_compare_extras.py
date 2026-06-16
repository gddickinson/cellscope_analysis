"""Units/labels (metric_docs) + per-group summary (compare) — pure, GUI-free."""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from maskviewer.analysis import metric_docs, compare      # noqa: E402


def test_column_units():
    cases = {
        "mean_area_um2": "µm²",
        "mean_perimeter_um": "µm",
        "mean_speed_um_per_min": "µm/min",
        "furth_D_um2_per_min": "µm²/min",
        "persistence_time_min": "min",
        "frames_tracked": "frames",
        "mean_n_neighbors": "count",
        "n_cells": "count",
        "frac_spread": "",            # fraction → dimensionless
        "mean_circularity": "",       # ratio → dimensionless
        "track_quality": "",
    }
    for col, want in cases.items():
        assert metric_docs.column_units(col) == want, (col, metric_docs.column_units(col))


def test_column_label_and_axis():
    assert metric_docs.column_label("mean_area_um2") == "mean area"
    assert metric_docs.column_label("mean_speed_um_per_min") == "mean speed"
    assert metric_docs.column_label("persistence_dir_autocorr") == "persistence dir autocorr"
    assert metric_docs.axis_label("mean_area_um2") == "mean area (µm²)"
    assert metric_docs.axis_label("mean_circularity") == "mean circularity"   # no units


def test_state_suffix_units_and_labels():
    # per-state columns inherit the base metric's units + are flagged [state]
    assert metric_docs.column_units("mean_area_um2_spread") == "µm²"
    assert metric_docs.column_units("persistence_rounded") == ""
    assert metric_docs.column_label("mean_area_um2_spread") == "mean area [spread]"
    assert metric_docs.axis_label("mean_area_um2_rounded") == "mean area [rounded] (µm²)"


def test_comparison_doc_resolves_base():
    what, how = metric_docs.comparison_doc("mean_speed_spread")
    assert what and "speed" in what.lower()
    assert "spread" in how.lower()                 # state note present
    # tooltip is non-empty and mentions the metric
    assert "speed" in metric_docs.comparison_tooltip("mean_speed_spread").lower()
    # comparison section is in the Help reference
    assert "state-segmented" in metric_docs.as_html().lower()


def test_border_distance_metric():
    from maskviewer.analysis import exporters
    T, H, W = 3, 100, 100
    labels = np.zeros((T, H, W), np.int32)
    labels[:, 40:60, 40:60] = 1            # centroid ~ (49.5, 49.5)
    df = exporters.per_cell_table(labels, 0.5, 10.0)
    assert "min_border_dist_um" in df.columns
    # nearest edge is 49.5 px away → × 0.5 µm/px ≈ 24.75 µm
    assert abs(df.iloc[0]["min_border_dist_um"] - 49.5 * 0.5) < 1.0


def test_ensemble_by_condition_bin_and_maxlag():
    rows = [{"recording": r, "condition": "WT", "tau": (k + 1) * 10.0,
             "msd": (k + 1) * 5.0} for r in ("a", "b") for k in range(10)]
    msd = pd.DataFrame(rows)
    # native: 10 lags at 10,20,…,100
    tau, c, lo, hi = compare.ensemble_by_condition(msd)["WT"]
    assert len(tau) == 10 and tau[0] == 10.0 and tau[-1] == 100.0
    # max_lag caps to the first N lags
    tau3 = compare.ensemble_by_condition(msd, max_lag=3)["WT"][0]
    assert list(tau3) == [10.0, 20.0, 30.0]
    # binning groups lags; bin x = mean of the real lags it holds (≥ first lag)
    tb = compare.ensemble_by_condition(msd, bin_min=50)["WT"][0]
    assert len(tb) < 10 and tb.min() >= 10.0


def test_ensemble_autocorr_by_condition():
    """The generalized aggregator also averages the direction-autocorrelation
    column (DiPer ensemble) across recordings."""
    rows = [{"recording": r, "condition": "KO", "tau": (k + 1) * 10.0,
             "autocorr": 1.0 - 0.1 * k} for r in ("a", "b") for k in range(5)]
    ac = pd.DataFrame(rows)
    tau, c, lo, hi = compare.ensemble_by_condition(ac, value_col="autocorr")["KO"]
    assert len(tau) == 5 and tau[0] == 10.0
    assert abs(c[0] - 1.0) < 1e-9 and abs(c[-1] - 0.6) < 1e-9   # mean over recordings


def test_direction_autocorrelation_matches_diper():
    """DiPer method: C(τ) = ⟨û(t)·û(t+τ)⟩ over unit step vectors. A straight track
    → 1 at every lag; a 90° zig-zag → 0 at lag 1 (perpendicular steps)."""
    from maskviewer.analysis import motion
    straight = np.array([[float(i), 0.0] for i in range(8)])      # all steps = +x
    ac = motion.direction_autocorrelation(straight)
    assert np.allclose(ac[1:], 1.0)
    zig = np.array([[0, 0], [1, 0], [1, 1], [2, 1], [2, 2], [3, 2], [3, 3]], float)
    acz = motion.direction_autocorrelation(zig)
    assert abs(acz[1]) < 1e-9                                     # consecutive steps ⟂


def test_multivariate_contrasts():
    rng = np.random.default_rng(0)
    rows = []
    for cond, shift in (("WT", 0.0), ("KO", 1.0)):       # KO clearly separated
        for r in range(4):
            rows.append({"recording": f"{cond}{r}", "condition": cond,
                         "mean_area_um2": float(rng.normal(100 + 40 * shift, 5)),
                         "frac_spread": float(rng.normal(0.5 + 0.2 * shift, 0.02)),
                         "mean_speed_spread": float(rng.normal(1.0 + shift, 0.05))})
    per_rec = pd.DataFrame(rows)
    arms = {"genetic": {"control": "WT", "conditions": ["WT", "KO"]}}
    res = compare.multivariate_contrasts(per_rec, arms=arms)
    assert len(res) == 1
    r = res[0]
    assert r["contrast"] == "KO vs WT" and r["n_features"] >= 2
    assert 0.0 <= r["permanova_p"] <= 1.0
    assert r["loro_auc"] >= 0.5                           # separable → strong AUC
    # too few recordings → graceful None
    tiny = per_rec[per_rec["recording"].isin(["WT0", "KO0"])]
    assert compare.multivariate_contrasts(tiny, arms=arms)[0]["permanova_p"] is None


def test_save_load_results_roundtrip(tmp_path):
    pc = pd.DataFrame({"recording": ["a", "b"], "condition": ["WT", "KO"],
                       "cell_id": [1, 2], "mean_area_um2": [100.0, 200.0]})
    msd = pd.DataFrame({"recording": ["a"], "condition": ["WT"], "tau": [10.0],
                        "msd": [5.0]})
    fp = os.path.join(tmp_path, "r.cmp")
    compare.save_results(fp, pc, msd, {"name": "x", "excluded": ["b"]})
    blob = compare.load_results(fp)
    assert blob["meta"]["name"] == "x" and blob["meta"]["excluded"] == ["b"]
    assert blob["per_cell"].equals(pc) and blob["msd"].equals(msd)


def test_per_condition_summary():
    per_rec = pd.DataFrame({
        "recording": ["a", "b", "c", "d"],
        "condition": ["WT", "WT", "KO", "KO"],
        "mean_area_um2": [100.0, 120.0, 200.0, 240.0],
    })
    summ = {s["group"]: s for s in compare.per_condition_summary(per_rec, "mean_area_um2")}
    assert set(summ) == {"WT", "KO"}
    assert summ["WT"]["n"] == 2 and summ["WT"]["mean"] == 110.0
    assert summ["KO"]["median"] == 220.0
    assert summ["WT"]["sem"] > 0
    # empty / missing metric → []
    assert compare.per_condition_summary(per_rec, "nope") == []
    assert compare.per_condition_summary(pd.DataFrame(), "mean_area_um2") == []


def _per_rec_three_groups():
    rows = []
    for v in (1.0, 1.1, 0.9, 1.05):
        rows.append({"recording": f"w{v}", "condition": "WT", "m": v})
    for v in (5.0, 5.2, 4.8, 5.1):                 # KO clearly separated from WT/GOF
        rows.append({"recording": f"k{v}", "condition": "KO", "m": v})
    for v in (1.05, 0.95, 1.1, 1.0):               # GOF overlaps WT
        rows.append({"recording": f"g{v}", "condition": "GOF", "m": v})
    return pd.DataFrame(rows)


def test_ranked_group_comparisons_orders_by_significance():
    res = compare.ranked_group_comparisons(_per_rec_three_groups(), "m")
    assert len(res) == 3                                       # every group pair
    assert [tuple(sorted((r["group_a"], r["group_b"]))) for r in res]  # all pairs present
    ps = [r["p"] for r in res]
    assert ps == sorted(ps)                                   # ranked ascending by p
    # the overlapping WT–GOF pair is the least likely to differ → last
    assert {res[-1]["group_a"], res[-1]["group_b"]} == {"WT", "GOF"}
    # KO (separated) appears in the top contrast
    assert "KO" in (res[0]["group_a"], res[0]["group_b"])
    for r in res:                                             # Bonferroni ≥ raw p, n tagged
        assert r["p_bonferroni"] >= r["p"] - 1e-9
        assert r["n_a"] == 4 and r["n_b"] == 4


def test_ranked_group_comparisons_edge_cases():
    df = _per_rec_three_groups()
    assert compare.ranked_group_comparisons(df, "missing_metric") == []   # no such col
    one = df[df["condition"] == "WT"]
    assert compare.ranked_group_comparisons(one, "m") == []               # single group


def test_benjamini_hochberg_monotone_and_le_bonferroni():
    from maskviewer.analysis import stats_extra as se
    p = np.array([0.001, 0.01, 0.02, 0.2, 0.5])
    q = se.benjamini_hochberg(p)
    assert np.all(np.diff(q) >= -1e-9)                 # monotone non-decreasing
    assert np.all(q <= np.minimum(p * p.size, 1) + 1e-9)  # FDR ≤ Bonferroni
    assert np.all((q >= 0) & (q <= 1))
    # NaNs pass through, finite count drives m
    q2 = se.benjamini_hochberg([0.01, np.nan, 0.02])
    assert np.isnan(q2[1]) and np.isfinite(q2[0])


def test_bootstrap_ci_brackets_effect():
    from maskviewer.analysis import stats_extra as se, compare
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 30); b = rng.normal(2, 1, 30)   # clear separation
    lo, hi = se.bootstrap_ci(a, b, compare.cohens_d)
    d = compare.cohens_d(a, b)
    assert lo < d < hi and lo > 0                        # CI excludes 0 (real effect)
    assert se.bootstrap_ci([1.0], [2.0, 3.0], compare.cohens_d) == (float("nan"),) * 2 \
        or np.isnan(se.bootstrap_ci([1.0], [2.0, 3.0], compare.cohens_d)[0])


def test_ranked_report_has_fdr_and_ci():
    from maskviewer.analysis import compare
    res = compare.ranked_group_comparisons(_per_rec_three_groups(), "m")
    assert all("q_fdr" in r and "cohen_d_lo" in r and "cluster_p" in r for r in res)
    fin = [r for r in res if np.isfinite(r["p"])]
    for r in fin:                                        # q ≤ Bonferroni per row
        assert r["q_fdr"] <= r["p_bonferroni"] + 1e-9


def test_cluster_robust_detects_group_effect():
    from maskviewer.analysis import stats_extra as se
    rng = np.random.default_rng(2)
    rows = []
    for rec in range(4):
        wbase, kbase = rng.normal(0, 0.3), rng.normal(0, 0.3)   # per-recording intercepts
        for _ in range(12):
            rows.append({"condition": "WT", "recording": f"w{rec}", "m": wbase + rng.normal(0, 1)})
            rows.append({"condition": "KO", "recording": f"k{rec}", "m": kbase + 3 + rng.normal(0, 1)})
    df = pd.DataFrame(rows)
    p = se.cluster_robust_p(df, "m")
    assert np.isfinite(p) and p < 0.05                   # large group effect detected
    assert np.isnan(se.cluster_robust_p(df[df["condition"] == "WT"], "m"))   # 1 group → NaN
