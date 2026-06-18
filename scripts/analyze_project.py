"""Headless analyze-project — load a project, run the cross-recording Comparison, and
write paper-ready CSVs + figures with no GUI interaction.

    python scripts/analyze_project.py --data-root data/by_condition --name IC295 --out OUT
    python scripts/analyze_project.py --project myproject.cmp --out OUT
    python scripts/analyze_project.py --data-root data/by_condition --name IC --out OUT --limit 9

Writes to OUT/: per_cell.csv, per_recording.csv, multivariate.csv, and per arm-contrast
a forest_<test>_vs_<control>.csv + ranked CSVs, plus box-plot PNGs for the most
differentiating metrics and an ensemble direction-autocorrelation PNG. Reproducible:
the same project + masks always give the same tables (recording = unit throughout).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # offscreen Qt for the figures

import numpy as np                                      # noqa: E402
import pyqtgraph as pg                                  # noqa: E402
from PyQt5 import QtWidgets                             # noqa: E402

from maskviewer import project as projmod               # noqa: E402
from maskviewer.analysis import compare                 # noqa: E402


def _parse():
    p = argparse.ArgumentParser(description="Headless project analysis → CSVs + figures")
    p.add_argument("--data-root", help="folder of <condition>/<recording> masks")
    p.add_argument("--name", default="project")
    p.add_argument("--project", help="a saved .cmp project file (instead of --data-root)")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--lags", type=int, default=0, help="MSD/autocorr lags (0 = default)")
    p.add_argument("--limit", type=int, default=0, help="cap recordings (for a quick run)")
    p.add_argument("--top", type=int, default=8, help="# of box-plot metric figures")
    return p.parse_args()


def _load(args):
    if args.project:
        return projmod.load_project(args.project)
    if not args.data_root:
        sys.exit("give --data-root or --project")
    return projmod.from_data_roots(args.data_root, name=args.name)


def _render(draw, path, w=760, h=480):
    """Draw onto a fresh offscreen PlotWidget and grab a PNG (grab renders the axis
    text, which the ImageExporter drops for custom string ticks offscreen)."""
    try:
        plot = pg.PlotWidget()
        plot.resize(w, h)
        plot.setBackground("w")                          # white margins → labels visible
        draw(plot)
        QtWidgets.QApplication.processEvents()
        plot.grab().save(path)
        return True
    except Exception as exc:
        print(f"  (skipped figure {os.path.basename(path)}: {exc})")
        return False


def main():
    args = _parse()
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    os.makedirs(args.out, exist_ok=True)
    proj = _load(args)
    entries = proj.entries[: args.limit] if args.limit else proj.entries
    design = proj.design
    print(f"Analyzing {len(entries)} recordings → {args.out}")

    per_cell, msd, autocorr, *_ = compare.build_comparison(
        entries, max_lag=args.lags, corrections=proj.corrections,
        scale_override=proj.scale_override,
        progress_cb=lambda i, n: print(f"  recording {i}/{n}", end="\r") or True)
    print()
    if per_cell is None or per_cell.empty:
        sys.exit("no cells found across recordings")
    per_rec = compare.aggregate(per_cell)

    per_cell.to_csv(os.path.join(args.out, "per_cell.csv"), index=False)
    per_rec.to_csv(os.path.join(args.out, "per_recording.csv"), index=False)
    print(f"  wrote per_cell.csv ({len(per_cell)} cells), per_recording.csv "
          f"({len(per_rec)} recordings)")

    # multivariate phenotype (PERMANOVA + leave-one-recording-out AUC) per arm
    try:
        import pandas as pd
        mv = compare.multivariate_contrasts(per_rec, arms=design.arms)
        if mv:
            pd.DataFrame(mv).to_csv(os.path.join(args.out, "multivariate.csv"), index=False)
            print("  wrote multivariate.csv (PERMANOVA p + LORO-AUC per arm)")
    except Exception as exc:
        print(f"  (multivariate skipped: {exc})")

    # per arm-contrast: forest (effect size of every metric) + rank the headline metric
    contrasts = []
    for arm, spec in design.arms.items():
        ctrl = spec["control"]
        for test in [c for c in spec["conditions"] if c != ctrl]:
            contrasts.append((ctrl, test))
    best_metrics = set()
    for ctrl, test in contrasts:
        fd = compare.forest_data(per_rec, ctrl, test)
        if not fd:
            continue
        import pandas as pd
        pd.DataFrame(fd).to_csv(
            os.path.join(args.out, f"forest_{test}_vs_{ctrl}.csv"), index=False)
        best_metrics.update(r["metric"] for r in fd[: args.top])
        _render(lambda p, fd=fd, c=ctrl, t=test: _draw_forest(p, fd, c, t),
                os.path.join(args.out, f"forest_{test}_vs_{ctrl}.png"))
    print(f"  wrote {len(contrasts)} forest CSV/PNG contrast(s)")

    # box-plot PNGs for the most differentiating metrics
    from maskviewer.gui import compare_plots
    from maskviewer.gui.plot_style import PlotStyle
    style = PlotStyle(); style.background = "white"      # publication-style figures
    n_box = 0
    for m in list(best_metrics)[: args.top]:
        if m in per_rec.columns and _render(
                lambda p, m=m: compare_plots.box(p, per_rec, m, design, style),
                os.path.join(args.out, f"box_{m}.png")):
            n_box += 1
    print(f"  wrote {n_box} box-plot PNG(s)")

    # ensemble direction-autocorrelation figure
    if autocorr is not None and not autocorr.empty:
        _render(lambda p: compare_plots.ensemble_autocorr(p, autocorr, design,
                                                          "mean ± SEM", style),
                os.path.join(args.out, "autocorr.png"))
        print("  wrote autocorr.png")
    print("Done.")


def _draw_forest(plot, fd, ctrl, test, top=20):
    rows = fd[:top]
    ys = np.arange(len(rows))[::-1]
    d = np.array([r["d"] for r in rows], float)
    lo = np.array([r["lo"] for r in rows], float)
    hi = np.array([r["hi"] for r in rows], float)
    plot.addItem(pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen("k", style=2)))
    plot.addItem(pg.ErrorBarItem(x=d, y=ys, left=np.nan_to_num(d - lo),
                                 right=np.nan_to_num(hi - d), beam=0.25,
                                 pen=pg.mkPen("k")))
    sig = [np.isfinite(r["p"]) and r["p"] < 0.05 for r in rows]
    brushes = [pg.mkBrush(214, 39, 40) if s else pg.mkBrush(120, 120, 120) for s in sig]
    plot.addItem(pg.ScatterPlotItem(d, ys, size=9, brush=brushes, pen=pg.mkPen("k")))
    from maskviewer.analysis import metric_docs
    ax = plot.getAxis("left"); ax.setWidth(160)
    ax.setTicks([[(int(y), metric_docs.column_label(r["metric"]))
                  for y, r in zip(ys, rows)]])
    plot.setLabel("bottom", f"Cohen's d ({test} - {ctrl})")
    plot.setTitle(f"{test} vs {ctrl}")
    plot.getViewBox().setBackgroundColor("w")
    for ax in ("left", "bottom"):
        plot.getAxis(ax).setPen("k"); plot.getAxis(ax).setTextPen("k")


if __name__ == "__main__":
    main()
