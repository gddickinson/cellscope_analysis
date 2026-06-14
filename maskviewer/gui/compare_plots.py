"""Design-aware comparison plots (shared by the Comparison window).

Pure-ish drawing functions over a pyqtgraph PlotWidget: strip / box / superplot
by condition, ensemble MSD by condition, and a metric-vs-metric scatter. Each
takes the project ``Design`` (condition order + colours) and, where points are
recordings, an optional ``pick_cb(label)`` for click-to-load.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from ..analysis import compare, feature_tables, metric_docs

_REC_PALETTE = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
                (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127)]


def _rgb(hexc):
    h = (hexc or "#777777").lstrip("#")
    return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))


def _conds(per, design):
    return compare.order_conditions(per["condition"].unique(),
                                    order=design.condition_order())


def _ticks(plot, conds):
    plot.getAxis("bottom").setTicks([[(i, c) for i, c in enumerate(conds)]])
    plot.setLabel("bottom", "")


def _pick(sp, pick_cb):
    if pick_cb:
        sp.sigClicked.connect(lambda _s, pts: pts and pick_cb(str(pts[0].data())))


def strip(plot, per_rec, metric, design, pick_cb=None):
    conds = _conds(per_rec, design)
    rng = np.random.default_rng(0)
    for i, cond in enumerate(conds):
        sub = per_rec[per_rec["condition"] == cond]
        col = _rgb(design.color(cond))
        spots = [{"pos": (i + float(rng.uniform(-0.12, 0.12)), float(r[metric])),
                  "data": r["recording"], "brush": pg.mkBrush(*col, 210)}
                 for _, r in sub.iterrows() if np.isfinite(r[metric])]
        if not spots:
            continue
        sp = pg.ScatterPlotItem(size=11, pen=pg.mkPen("k"))
        sp.addPoints(spots)
        _pick(sp, pick_cb)
        plot.addItem(sp)
        vals = np.array([s["pos"][1] for s in spots])
        mean = vals.mean()
        sem = vals.std(ddof=1) / np.sqrt(vals.size) if vals.size > 1 else 0.0
        plot.addItem(pg.ErrorBarItem(x=np.array([i]), y=np.array([mean]),
                                     height=np.array([2 * sem]), beam=0.12,
                                     pen=pg.mkPen("w", width=2)))
        plot.plot([i - 0.22, i + 0.22], [mean, mean], pen=pg.mkPen("w", width=2))
    _ticks(plot, conds)
    plot.setLabel("left", metric_docs.axis_label(metric))
    plot.setTitle("each point = one recording (mean ± SEM)")


def box(plot, per_rec, metric, design):
    conds = _conds(per_rec, design)
    bc = compare.by_condition(per_rec, metric)
    r = feature_tables.arm_tests(bc, arms=design.arms, vehicle=design.vehicle)
    rng = np.random.default_rng(0)
    for i, cond in enumerate(conds):
        v = np.array(bc.get(cond, []), float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        col = _rgb(design.color(cond))
        pen = pg.mkPen(col, width=1.6)
        for x0, y0, x1, y1 in [(i - .25, q1, i + .25, q1), (i - .25, q3, i + .25, q3),
                               (i - .25, q1, i - .25, q3), (i + .25, q1, i + .25, q3)]:
            plot.plot([x0, x1], [y0, y1], pen=pen)
        plot.plot([i - .25, i + .25], [med, med], pen=pg.mkPen(col, width=2.5))
        plot.plot([i, i], [v.min(), q1], pen=pen)
        plot.plot([i, i], [q3, v.max()], pen=pen)
        plot.addItem(pg.ScatterPlotItem(i + rng.uniform(-0.09, 0.09, v.size), v,
                                        size=7, brush=pg.mkBrush(*col, 160), pen=None))
    for arm, spec in design.arms.items():
        ctrl = spec["control"]
        for t in [c for c in spec["conditions"] if c != ctrl]:
            if t in conds and bc.get(t):
                pb = r[arm]["pairs"].get(f"{ctrl}_vs_{t}", {}).get("p_bonf")
                star = feature_tables.stars(pb).split()[-1] if pb is not None else ""
                if star in ("*", "**", "***"):
                    lbl = pg.TextItem(star, color="w", anchor=(0.5, 1))
                    lbl.setPos(conds.index(t), max(bc[t]))
                    plot.addItem(lbl)
    _ticks(plot, conds)
    plot.setLabel("left", metric_docs.axis_label(metric))
    plot.setTitle("box = recordings/condition · * vs arm control (Bonferroni)")


def superplot(plot, per_cell, per_rec, metric, design):
    conds = _conds(per_cell, design)
    rng = np.random.default_rng(0)
    for i, cond in enumerate(conds):
        cc = per_cell[per_cell["condition"] == cond]
        for ri, rec in enumerate(cc["recording"].unique()):
            v = cc[cc["recording"] == rec][metric].to_numpy(float)
            v = v[np.isfinite(v)]
            if v.size:
                plot.addItem(pg.ScatterPlotItem(
                    i + rng.uniform(-0.18, 0.18, v.size), v, size=4,
                    brush=pg.mkBrush(*_REC_PALETTE[ri % len(_REC_PALETTE)], 90),
                    pen=None))
        mr = per_rec[per_rec["condition"] == cond][metric].to_numpy(float)
        mr = mr[np.isfinite(mr)]
        if mr.size:
            plot.addItem(pg.ScatterPlotItem(
                i + rng.uniform(-0.1, 0.1, mr.size), mr, size=12,
                brush=pg.mkBrush(*_rgb(design.color(cond)), 235),
                pen=pg.mkPen("k", width=1.5)))
            plot.plot([i - 0.22, i + 0.22], [mr.mean(), mr.mean()],
                      pen=pg.mkPen("w", width=2))
    _ticks(plot, conds)
    plot.setLabel("left", metric_docs.axis_label(metric))
    plot.setTitle("small = cells (by recording) · large = recording means")


def ensemble_msd(plot, msd, design, stat):
    if msd is None or msd.empty:
        plot.setTitle("no ensemble MSD (recompute to build it)")
        return
    ens = compare.ensemble_by_condition(msd, stat=stat)
    for cond in compare.order_conditions(ens, order=design.condition_order()):
        tau, centre, lo, hi = ens[cond]
        col = _rgb(design.color(cond))
        top, bot = pg.PlotDataItem(tau, hi), pg.PlotDataItem(tau, lo)
        plot.addItem(pg.FillBetweenItem(top, bot, brush=pg.mkBrush(*col, 60)))
        plot.plot(tau, centre, pen=pg.mkPen(col, width=2))
    plot.setLogMode(x=True, y=True)
    plot.setLabel("bottom", "lag τ (min)")
    plot.setLabel("left", "MSD (µm²)")
    plot.setTitle(f"ensemble MSD by condition ({'median + 95% CI' if stat == 'median' else 'mean ± SEM'})")


def scatter(plot, per_rec, mx, my, design, pick_cb=None):
    if mx not in per_rec.columns or my not in per_rec.columns:
        return
    for cond in compare.order_conditions(per_rec["condition"].unique(),
                                         order=design.condition_order()):
        sub = per_rec[per_rec["condition"] == cond]
        spots = [{"pos": (float(r[mx]), float(r[my])), "data": r["recording"]}
                 for _, r in sub.iterrows()
                 if np.isfinite(r[mx]) and np.isfinite(r[my])]
        if spots:
            sp = pg.ScatterPlotItem(size=11, pen=pg.mkPen("k"),
                                    brush=pg.mkBrush(*_rgb(design.color(cond)), 220))
            sp.addPoints(spots)
            _pick(sp, pick_cb)
            plot.addItem(sp)
    x = per_rec[mx].to_numpy(float)
    y = per_rec[my].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y)
    title = f"{metric_docs.column_label(mx)} vs {metric_docs.column_label(my)}"
    if ok.sum() >= 3:
        from scipy.stats import spearmanr
        rho, p = spearmanr(x[ok], y[ok])
        title += f"   (Spearman ρ={rho:.2f}, p={p:.3f})"
    plot.setLabel("bottom", metric_docs.axis_label(mx))
    plot.setLabel("left", metric_docs.axis_label(my))
    plot.setTitle(title)


def histogram(plot, per_cell, metric, design, density=True):
    """Per-cell distribution of ``metric``, one outlined+filled curve per group
    (shared bins, design colours). Complements the recording-level views."""
    if per_cell is None or per_cell.empty or metric not in per_cell.columns:
        return
    allv = per_cell[metric].to_numpy(float)
    allv = allv[np.isfinite(allv)]
    if allv.size == 0:
        return
    lo, hi = np.percentile(allv, [0.5, 99.5])
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        lo, hi = float(allv.min()), float(allv.max()) + 1e-9
    edges = np.linspace(lo, hi, 31)
    centres = 0.5 * (edges[:-1] + edges[1:])
    for cond in _conds(per_cell, design):
        v = per_cell[per_cell["condition"] == cond][metric].to_numpy(float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        h, _ = np.histogram(v, bins=edges, density=density)
        col = _rgb(design.color(cond))
        plot.addItem(pg.PlotCurveItem(centres, h, name=cond, fillLevel=0,
                                      pen=pg.mkPen(col, width=2),
                                      brush=pg.mkBrush(*col, 55)))
    plot.setLabel("bottom", metric_docs.axis_label(metric))
    plot.setLabel("left", "density" if density else "cells")
    plot.setTitle("per-cell distribution by group")
