"""Compare PIEZO1 treatment effects across the IC293 (manual) and IC295 (programmatic)
single-cell-crop datasets → figures + a markdown report.

    python scripts/compare_datasets.py            # uses cached per-cell tables if present
    python scripts/compare_datasets.py --recompute

Writes analysis_out/ic293_vs_ic295/{REPORT.md, figs/*.png, <key>/*.csv}. Recording =
unit (one single-cell crop = one cell). Study-specific; reuses maskviewer.analysis.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))           # scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo

import ds_config as cfg          # noqa: E402
import ds_compute                # noqa: E402
import ds_stats as st            # noqa: E402
import ds_figures as figs        # noqa: E402
import ds_report                 # noqa: E402

DS = [d["key"] for d in cfg.DATASETS]


def _multivariate_cached(key, per_rec, recompute):
    """Cache the (slow, permutation-based) multivariate result per dataset to JSON."""
    path = os.path.join(cfg.OUT, key, "multivariate.json")
    if not recompute and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    res = st.multivariate(per_rec)
    with open(path, "w") as f:
        json.dump(res, f, indent=2)
    return res


def main():
    recompute = "--recompute" in sys.argv
    raw = ds_compute.compute_all(recompute)              # {key: {per_cell, per_recording,…}}
    figdir = os.path.join(cfg.OUT, "figs")
    os.makedirs(figdir, exist_ok=True)

    per_rec, autocorr, counts, effects, mv = {}, {}, {}, {}, {}
    for k in DS:
        pr = st.filter_tracks(raw[k]["per_recording"])
        per_rec[k] = pr
        kept = set(pr["recording"])
        ac = raw[k]["autocorr"]
        autocorr[k] = ac[ac["recording"].isin(kept)] if not ac.empty else ac
        counts[k] = {"raw": len(raw[k]["per_recording"]), "filtered": len(pr),
                     "by_cond": st.condition_counts(pr)}
        effects[k] = st.all_contrast_effects(pr)
        mv[k] = _multivariate_cached(k, pr, recompute)
        print(f"[{k}] {counts[k]['filtered']}/{counts[k]['raw']} cells kept "
              f"(≥{cfg.MIN_FRAMES} frames); per-condition {counts[k]['by_cond']}")

    # cross-dataset concordance per treatment contrast (A = first dataset, B = second)
    conc = {}
    for _arm, ctrl, test in cfg.CONTRASTS:
        if _arm == "batch":
            continue
        m, stats = st.concordance(effects[DS[0]].get((ctrl, test)),
                                  effects[DS[1]].get((ctrl, test)))
        if not m.empty:
            m.attrs["pearson_r"] = stats.get("pearson_r")
        conc[(ctrl, test)] = (m, stats)
        print(f"  concordance {test} vs {ctrl}: r={stats.get('pearson_r')}, "
              f"robust={stats.get('n_robust')}")

    # figures
    figs.fig_distributions(per_rec, os.path.join(figdir, "distributions.png"))
    figs.fig_concordance({k: v[0] for k, v in conc.items()},
                         os.path.join(figdir, "concordance.png"))
    figs.fig_autocorr(autocorr, os.path.join(figdir, "autocorr.png"))
    figs.fig_forest(effects, [("WT", "GOF"), ("WT", "KO")],
                    os.path.join(figdir, "forest_genetic.png"))
    figs.fig_forest(effects, [("DMSO", "Y1"), ("DMSO", "OT")],
                    os.path.join(figdir, "forest_drug.png"))
    figs.fig_multivariate(mv, os.path.join(figdir, "multivariate.png"))

    res = {"counts": counts, "effects": effects, "concordance": conc,
           "multivariate": mv,
           "figs": {n: f"figs/{n}.png" for n in
                    ("distributions", "concordance", "autocorr",
                     "forest_genetic", "forest_drug", "multivariate")}}
    path = ds_report.write_report(os.path.join(cfg.OUT, "REPORT.md"), res)
    print(f"\nReport → {path}")


if __name__ == "__main__":
    main()
