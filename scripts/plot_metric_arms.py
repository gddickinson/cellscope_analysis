#!/usr/bin/env python
"""Arm-structured comparison of a recording-level metric: control vs treatments.

Default metric: persistence_spread (directional persistence of spread cells).
The IC295 design has two independent experiments + a vehicle check, so the
comparison is arm-structured (cross-arm contrasts are meaningless):
  GENETIC  control WT   → GOF, KO
  DRUG     vehicle DMSO → YODA1 (Y1), OT
  VEHICLE  WT vs DMSO
Recording = experimental unit; within-arm Bonferroni pairwise vs the control.

  conda run -n cellscope_analysis python scripts/plot_metric_arms.py
  ... plot_metric_arms.py --metric mean_speed_spread

Writes analysis_out/<metric>_arms.png (box+strip per arm) and
<metric>_effect.png (Cohen's d vs control ± 95% bootstrap CI).
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from maskviewer.analysis import feature_tables as ft

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "analysis_out")


def _sym(p):
    if p is None or not np.isfinite(p):
        return "n/a"
    return ("***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05
            else "ns")


def _col(df, metric):
    return metric if metric in df.columns else metric + "_mean"


def _bracket(ax, x1, x2, y, h, label):
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=1.1, c="#333")
    ax.text((x1 + x2) / 2, y + h, label, ha="center", va="bottom", fontsize=10)


def box_arms(df, col, label, path):
    by = {c: df.loc[df.condition == c, col].dropna().to_numpy()
          for c in ft.CONDITIONS}
    stats = ft.arm_tests(by)
    rng = np.random.default_rng(0)
    allv = np.concatenate([v for v in by.values() if len(v)])
    lo, hi = float(allv.min()), float(allv.max())
    step = (hi - lo) * 0.08 or 0.1
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), sharey=True)
    for ax, (arm, spec) in zip(axes, ft.ARMS.items()):
        conds, ctrl = spec["conditions"], spec["control"]
        data = [by[c] for c in conds]
        pos = list(range(1, len(conds) + 1))
        bp = ax.boxplot(data, positions=pos, widths=0.6, showfliers=False,
                        patch_artist=True)
        for patch, c in zip(bp["boxes"], conds):
            patch.set(facecolor="#cccccc" if c == ctrl else ft.COND_COLOR[c],
                      alpha=0.55, edgecolor="#446")
        for p, c in zip(pos, conds):
            v = by[c]
            ax.scatter(rng.normal(p, 0.06, len(v)), v, s=32,
                       color=ft.COND_COLOR[c], edgecolor="#222", zorder=3)
        k = 0
        for j, c in enumerate(conds):
            if c == ctrl:
                continue
            pb = stats[arm]["pairs"][f"{ctrl}_vs_{c}"]["p_bonf"]
            _bracket(ax, conds.index(ctrl) + 1, j + 1, hi + step * (1 + 1.6 * k),
                     step * 0.4, _sym(pb))
            k += 1
        kw = stats[arm]["kw"]
        ax.set_title(f"{arm} arm   (Kruskal-Wallis {_sym(kw)})", fontsize=11)
        ax.set_xticks(pos)
        ax.set_xticklabels([f"{c}\n(control)" if c == ctrl else c for c in conds])
    axes[0].set_ylabel(label)
    veh = stats["vehicle"]["p"]
    fig.suptitle(f"{label} — control vs treatments (recording = unit, within-arm "
                 f"Bonferroni)\nvehicle WT vs DMSO: {_sym(veh)}", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=140); plt.close(fig)
    return stats


def _cohend(b, a):
    sp = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2) or 1.0
    return (b.mean() - a.mean()) / sp


def effect_forest(df, col, label, path):
    rng = np.random.default_rng(0)
    items = []
    for arm, spec in ft.ARMS.items():
        ctrl = spec["control"]
        a = df.loc[df.condition == ctrl, col].dropna().to_numpy()
        for c in spec["conditions"]:
            if c == ctrl:
                continue
            b = df.loc[df.condition == c, col].dropna().to_numpy()
            d = _cohend(b, a)
            boot = [_cohend(rng.choice(b, len(b)), rng.choice(a, len(a)))
                    for _ in range(2000)]
            items.append((f"{c} vs {ctrl}", d, np.percentile(boot, 2.5),
                          np.percentile(boot, 97.5), ft.COND_COLOR[c]))
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    y = np.arange(len(items))
    for yi, (_lab, d, lo, hi, col_) in zip(y, items):
        ax.errorbar(d, yi, xerr=[[d - lo], [hi - d]], fmt="o", color=col_,
                    capsize=4, ms=8, elinewidth=2)
    ax.axvline(0, color="#444", ls="--", lw=1.2)
    ax.set_yticks(y); ax.set_yticklabels([it[0] for it in items])
    ax.invert_yaxis()
    ax.set_xlabel(f"Cohen's d vs control  ({label})  ± 95% CI")
    ax.set_title(f"{label}: treatment − control effect size\n"
                 "(d>0 = higher than control; CI crossing 0 = n.s.)", fontsize=10)
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout(); fig.savefig(path, dpi=140); plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--metric", default="persistence_spread",
                    help="recording-level metric (e.g. persistence_spread, "
                    "straightness_spread, mean_speed_spread)")
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    df = ft.recordings()
    if args.metric == "shape_roundness":          # derived score, not a CSV column
        from maskviewer.analysis import multivariate as mv
        df = mv.add_shape_score(df)[0]
    col = _col(df, args.metric)
    if col not in df.columns:
        print(f"metric '{args.metric}' not found (col '{col}'). Available "
              f"*_spread columns: "
              f"{[c for c in df.columns if c.endswith('_spread_mean')]}")
        return 2
    label = args.metric
    box_arms(df, col, label, os.path.join(OUT, f"{args.metric}_arms.png"))
    effect_forest(df, col, label, os.path.join(OUT, f"{args.metric}_effect.png"))
    print(f"Wrote {args.metric}_arms.png + {args.metric}_effect.png → {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
