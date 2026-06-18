"""Design-aware comparison plots (shared by the Comparison window).

Pure-ish drawing functions over a pyqtgraph PlotWidget: strip / box / bars /
superplot by condition, ensemble MSD, a metric-vs-metric scatter, and a per-cell
histogram. Each takes the project ``Design`` (condition order + colours) and a
``PlotStyle`` (font / marker / line sizes, fill opacity, grid, log axes,
histogram bins…); where points are recordings an optional ``pick_cb(label)``
loads that recording.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtGui

from ..analysis import compare, feature_tables, metric_docs
from .plot_style import PlotStyle

_REC_PALETTE = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
                (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127)]


def _rgb(hexc):
    h = (hexc or "#777777").lstrip("#")
    return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))


def _conds(per, design):
    return compare.order_conditions(per["condition"].unique(),
                                    order=design.condition_order())


def _individual_curves(plot, long_df, design, value_col, log, style):
    """Faintly overlay each recording's own curve (condition-coloured) behind the
    ensemble — shows the per-recording spread the mean ± band summarises."""
    if long_df is None or long_df.empty:
        return
    for (_rec, cond), g in long_df.groupby(["recording", "condition"]):
        g = g.sort_values("tau")
        tau, v = g["tau"].to_numpy(float), g[value_col].to_numpy(float)
        keep = np.isfinite(tau) & np.isfinite(v) & ((not log) | (v > 0))
        if style.msd_max_lag:
            keep &= np.arange(len(tau)) < style.msd_max_lag
        if keep.sum() < 2:
            continue
        tau, v = tau[keep], (np.maximum(v[keep], 1e-9) if log else v[keep])
        plot.plot(tau, v, pen=pg.mkPen(color=(*_rgb(design.color(cond)), 55), width=1))


_BG = {"black": "k", "white": "w", "grey": (60, 60, 60), "default": None}

_FILTER_NOTE = ""           # appended to plot titles when filters are active


def set_filter_note(note):
    """Set the 'filtered: …' suffix appended to every plot title (set once per
    replot by the window; '' clears it)."""
    global _FILTER_NOTE
    _FILTER_NOTE = note or ""


def _axes(plot, style, left=None, bottom=None, title=None, logx=False, logy=False):
    """Apply background / fonts / grid / log-mode shared by every plot."""
    bg = _BG.get(style.background)
    if bg is not None:
        plot.setBackground(bg)
    fg = "k" if style.background == "white" else "w"
    fs = f"{style.font_size}pt"
    if left is not None:
        plot.setLabel("left", left, **{"font-size": fs, "color": fg})
    if bottom is not None:
        plot.setLabel("bottom", bottom, **{"font-size": fs, "color": fg})
    if title is not None:
        if _FILTER_NOTE:
            title = f"{title}  ·  filtered: {_FILTER_NOTE}"
        plot.setTitle(title, size=fs, color=fg)
    plot.showGrid(x=style.grid, y=style.grid, alpha=0.3)
    f = QtGui.QFont()
    f.setPointSize(style.font_size)
    for ax in ("left", "bottom"):
        axis = plot.getAxis(ax)
        axis.setStyle(tickFont=f)
        axis.setPen(fg)
        axis.setTextPen(fg)
    plot.setLogMode(x=logx, y=logy)


def _legend_entry(plot, name, col, style):
    """Register a coloured legend entry (an empty named curve) when legend is on."""
    if style.legend:
        plot.plot([], [], name=name, pen=pg.mkPen(col, width=max(2, style.line_width)))


def _ticks(plot, conds):
    plot.getAxis("bottom").setTicks([[(i, c) for i, c in enumerate(conds)]])
    plot.setLabel("bottom", "")


def _pick(sp, pick_cb):
    if pick_cb:
        sp.sigClicked.connect(lambda _s, pts: pts and pick_cb(str(pts[0].data())))


_POLY_DEG = {"linear": 1, "polynomial (2)": 2, "polynomial (3)": 3}


def _fit_xy(x, y, kind):
    """(xs, ys, lo, hi) for a least-squares fit + ±1 std-error band, or None.

    Polynomial (linear / poly-2 / poly-3) is fit directly (multiparameter);
    power / exponential / log are fit in their linearising space. ``lo``/``hi``
    are the centre ± residual standard error.
    """
    ok = np.isfinite(x) & np.isfinite(y)
    if kind in ("log", "power"):
        ok &= x > 0
    if kind in ("exponential", "power"):
        ok &= y > 0
    x, y = x[ok], y[ok]
    if x.size < 2 or np.ptp(x) == 0:
        return None
    xs = np.linspace(x.min(), x.max(), 80)
    if kind in _POLY_DEG:                            # multiparameter polynomial fit
        deg = min(_POLY_DEG[kind], x.size - 1)
        coef = np.polyfit(x, y, deg)
        ys = np.polyval(coef, xs)
        resid = y - np.polyval(coef, x)
        se = float(resid.std(ddof=deg + 1)) if x.size > deg + 1 else 0.0
        return xs, ys, ys - se, ys + se
    X = np.log(x) if kind in ("log", "power") else x   # linearised 2-param models
    Y = np.log(y) if kind in ("exponential", "power") else y
    a, b = np.polyfit(X, Y, 1)
    se = float((Y - (a * X + b)).std(ddof=2)) if X.size > 2 else 0.0
    Xs = np.log(xs) if kind in ("log", "power") else xs
    Ys = a * Xs + b
    lo, hi = Ys - se, Ys + se
    if kind in ("exponential", "power"):
        return xs, np.exp(Ys), np.exp(lo), np.exp(hi)
    return xs, Ys, lo, hi


def _draw_fit(plot, x, y, kind, col, style):
    r = _fit_xy(np.asarray(x, float), np.asarray(y, float), kind)
    if r is None:
        return
    xs, ys, lo, hi = r
    if style.fit_ci:
        top = plot.plot(xs, hi, pen=None)
        bot = plot.plot(xs, lo, pen=None)
        plot.addItem(pg.FillBetweenItem(top, bot,
                                        brush=pg.mkBrush(*col, max(25, style.fill_alpha // 2))))
    plot.plot(xs, ys, pen=pg.mkPen(col, width=style.line_width, style=QtCore.Qt.DashLine))


def _trend(plot, centres, style):
    """Dashed line through the per-group centre values across conditions (a trend
    across an ordered series of conditions, e.g. a dose response)."""
    pts = [(i, v) for i, v in enumerate(centres) if v is not None and np.isfinite(v)]
    if len(pts) >= 2:
        xs, ys = zip(*pts)
        plot.plot(list(xs), list(ys),
                  pen=pg.mkPen((255, 215, 0), width=style.line_width,
                               style=QtCore.Qt.DashLine))


def strip(plot, per_rec, metric, design, pick_cb=None, style=None):
    style = style or PlotStyle()
    conds = _conds(per_rec, design)
    rng = np.random.default_rng(0)
    lw = style.line_width
    centres = [np.nan] * len(conds)
    for i, cond in enumerate(conds):
        sub = per_rec[per_rec["condition"] == cond]
        col = _rgb(design.color(cond))
        spots = [{"pos": (i + float(rng.uniform(-0.12, 0.12)), float(r[metric])),
                  "data": r["recording"], "brush": pg.mkBrush(*col, 210)}
                 for _, r in sub.iterrows() if np.isfinite(r[metric])]
        if not spots:
            continue
        sp = pg.ScatterPlotItem(size=style.point_size, pen=pg.mkPen("k"))
        sp.addPoints(spots)
        _pick(sp, pick_cb)
        plot.addItem(sp)
        _legend_entry(plot, cond, col, style)
        vals = np.array([s["pos"][1] for s in spots])
        mean = vals.mean()
        centres[i] = mean
        sem = vals.std(ddof=1) / np.sqrt(vals.size) if vals.size > 1 else 0.0
        plot.addItem(pg.ErrorBarItem(x=np.array([i]), y=np.array([mean]),
                                     height=np.array([2 * sem]), beam=0.12,
                                     pen=pg.mkPen("w", width=lw)))
        plot.plot([i - 0.22, i + 0.22], [mean, mean], pen=pg.mkPen("w", width=lw))
    if style.trendline:
        _trend(plot, centres, style)
    _axes(plot, style, left=metric_docs.axis_label(metric), logy=style.log_y,
          title="each point = one recording (mean ± SEM)")
    _ticks(plot, conds)


def box(plot, per_rec, metric, design, style=None):
    style = style or PlotStyle()
    conds = _conds(per_rec, design)
    bc = compare.by_condition(per_rec, metric)
    r = feature_tables.arm_tests(bc, arms=design.arms, vehicle=design.vehicle)
    rng = np.random.default_rng(0)
    lw = style.line_width
    centres = [np.nan] * len(conds)
    for i, cond in enumerate(conds):
        v = np.array(bc.get(cond, []), float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        q1, med, q3 = np.percentile(v, [25, 50, 75])
        centres[i] = med
        col = _rgb(design.color(cond))
        _legend_entry(plot, cond, col, style)
        pen = pg.mkPen(col, width=lw)
        for x0, y0, x1, y1 in [(i - .25, q1, i + .25, q1), (i - .25, q3, i + .25, q3),
                               (i - .25, q1, i - .25, q3), (i + .25, q1, i + .25, q3)]:
            plot.plot([x0, x1], [y0, y1], pen=pen)
        plot.plot([i - .25, i + .25], [med, med], pen=pg.mkPen(col, width=lw + 1))
        plot.plot([i, i], [v.min(), q1], pen=pen)
        plot.plot([i, i], [q3, v.max()], pen=pen)
        if style.show_points:
            plot.addItem(pg.ScatterPlotItem(
                i + rng.uniform(-0.09, 0.09, v.size), v,
                size=max(4, style.point_size - 4),
                brush=pg.mkBrush(*col, 160), pen=None))
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
    if style.trendline:
        _trend(plot, centres, style)
    _axes(plot, style, left=metric_docs.axis_label(metric), logy=style.log_y,
          title="box = recordings/condition · * vs arm control (Bonferroni)")
    _ticks(plot, conds)


def bars(plot, per_rec, metric, design, style=None):
    """Bar chart of per-group means ± SEM (recording = unit) — the bars-not-points
    view; individual recordings overlaid when `show_points`."""
    style = style or PlotStyle()
    conds = _conds(per_rec, design)
    rng = np.random.default_rng(0)
    centres = [np.nan] * len(conds)
    for i, cond in enumerate(conds):
        v = per_rec[per_rec["condition"] == cond][metric].to_numpy(float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        col = _rgb(design.color(cond))
        _legend_entry(plot, cond, col, style)
        mean = float(v.mean())
        centres[i] = mean
        sem = float(v.std(ddof=1) / np.sqrt(v.size)) if v.size > 1 else 0.0
        plot.addItem(pg.BarGraphItem(x=np.array([i]), height=np.array([mean]),
                                     width=0.6, brush=pg.mkBrush(*col, 160),
                                     pen=pg.mkPen("k", width=1)))
        plot.addItem(pg.ErrorBarItem(x=np.array([i]), y=np.array([mean]),
                                     height=np.array([2 * sem]), beam=0.12,
                                     pen=pg.mkPen("w", width=style.line_width)))
        if style.show_points:
            plot.addItem(pg.ScatterPlotItem(
                i + rng.uniform(-0.12, 0.12, v.size), v,
                size=max(4, style.point_size - 3), pen=pg.mkPen("k"),
                brush=pg.mkBrush(*col, 220)))
    if style.trendline:
        _trend(plot, centres, style)
    _axes(plot, style, left=metric_docs.axis_label(metric), logy=style.log_y,
          title="bar = group mean ± SEM (recording = unit)")
    _ticks(plot, conds)


def superplot(plot, per_cell, per_rec, metric, design, style=None):
    style = style or PlotStyle()
    conds = _conds(per_cell, design)
    rng = np.random.default_rng(0)
    cell_sz = max(2, style.point_size - 7)
    centres = [np.nan] * len(conds)
    for i, cond in enumerate(conds):
        cc = per_cell[per_cell["condition"] == cond]
        _legend_entry(plot, cond, _rgb(design.color(cond)), style)
        for ri, rec in enumerate(cc["recording"].unique()):
            v = cc[cc["recording"] == rec][metric].to_numpy(float)
            v = v[np.isfinite(v)]
            if v.size:
                plot.addItem(pg.ScatterPlotItem(
                    i + rng.uniform(-0.18, 0.18, v.size), v, size=cell_sz,
                    brush=pg.mkBrush(*_REC_PALETTE[ri % len(_REC_PALETTE)], 90),
                    pen=None))
        mr = per_rec[per_rec["condition"] == cond][metric].to_numpy(float)
        mr = mr[np.isfinite(mr)]
        if mr.size:
            centres[i] = float(mr.mean())
            plot.addItem(pg.ScatterPlotItem(
                i + rng.uniform(-0.1, 0.1, mr.size), mr, size=style.point_size,
                brush=pg.mkBrush(*_rgb(design.color(cond)), 235),
                pen=pg.mkPen("k", width=1.5)))
            plot.plot([i - 0.22, i + 0.22], [mr.mean(), mr.mean()],
                      pen=pg.mkPen("w", width=style.line_width))
    if style.trendline:
        _trend(plot, centres, style)
    _axes(plot, style, left=metric_docs.axis_label(metric), logy=style.log_y,
          title="small = cells (by recording) · large = recording means")
    _ticks(plot, conds)


def ensemble_msd(plot, msd, design, stat, style=None):
    style = style or PlotStyle()
    if msd is None or msd.empty:
        plot.setTitle("no ensemble MSD (recompute to build it)")
        return
    ens = compare.ensemble_by_condition(msd, stat=stat, bin_min=style.msd_bin_min,
                                        max_lag=style.msd_max_lag)
    log = style.msd_log
    eps = 1e-9                       # log axes need strictly-positive values
    if style.show_individual_curves:
        _individual_curves(plot, msd, design, "msd", log, style)
    for cond in compare.order_conditions(ens, order=design.condition_order()):
        tau, centre, lo, hi = ens[cond]
        keep = np.isfinite(tau) & np.isfinite(centre) & (not log or centre > 0)
        if keep.sum() < 1:
            continue
        tau, centre, lo, hi = tau[keep], centre[keep], lo[keep], hi[keep]
        if log:                      # clamp the band so the log transform is defined
            centre, lo, hi = (np.maximum(centre, eps), np.maximum(lo, eps),
                              np.maximum(hi, eps))
        col = _rgb(design.color(cond))
        # add the band's bound curves to the plot (pen=None) so they inherit its
        # log mode — a bare FillBetweenItem over loose curves renders misaligned
        top = plot.plot(tau, hi, pen=None)
        bot = plot.plot(tau, lo, pen=None)
        plot.addItem(pg.FillBetweenItem(top, bot, brush=pg.mkBrush(*col, style.fill_alpha)))
        plot.plot(tau, centre, pen=pg.mkPen(col, width=style.line_width), name=cond)
        if style.msd_points:
            # markers + per-point error bars drawn as PlotDataItems so they share
            # the plot's log mode (ErrorBarItem/ScatterPlotItem would not)
            plot.plot(tau, centre, pen=None, symbol="o", symbolSize=style.point_size,
                      symbolBrush=pg.mkBrush(*col, 235), symbolPen=pg.mkPen("k"))
            for k in range(len(tau)):
                plot.plot([tau[k], tau[k]], [lo[k], hi[k]],
                          pen=pg.mkPen(col, width=style.line_width))
    band = "median + 95% CI" if stat == "median" else "mean ± SEM"
    binned = f" · {style.msd_bin_min}-min bins" if style.msd_bin_min else ""
    _axes(plot, style, left="MSD (µm²)", bottom="lag τ (min)", logx=log, logy=log,
          title=f"ensemble MSD by condition ({band}{binned})")


def ensemble_autocorr(plot, autocorr, design, stat, style=None):
    """DiPer **direction autocorrelation** by condition: mean ± SEM (or median +
    bootstrap CI) of the per-recording autocorrelation curves vs the time interval
    τ. Decays from ~1 (persistent) toward 0 (random walk) — the speed-unbiased
    directional-persistence readout (Gorelik & Gautreau 2014)."""
    style = style or PlotStyle()
    if autocorr is None or autocorr.empty:
        plot.setTitle("no direction autocorrelation (recompute to build it)")
        return
    ens = compare.ensemble_by_condition(autocorr, stat=stat, bin_min=style.msd_bin_min,
                                        max_lag=style.msd_max_lag, value_col="autocorr")
    if style.show_individual_curves:
        _individual_curves(plot, autocorr, design, "autocorr", False, style)
    for cond in compare.order_conditions(ens, order=design.condition_order()):
        tau, centre, lo, hi = ens[cond]
        keep = np.isfinite(tau) & np.isfinite(centre)
        if keep.sum() < 1:
            continue
        tau, centre, lo, hi = tau[keep], centre[keep], lo[keep], hi[keep]
        col = _rgb(design.color(cond))
        top = plot.plot(tau, hi, pen=None)
        bot = plot.plot(tau, lo, pen=None)
        plot.addItem(pg.FillBetweenItem(top, bot, brush=pg.mkBrush(*col, style.fill_alpha)))
        plot.plot(tau, centre, pen=pg.mkPen(col, width=style.line_width), name=cond)
        if style.msd_points:
            plot.plot(tau, centre, pen=None, symbol="o", symbolSize=style.point_size,
                      symbolBrush=pg.mkBrush(*col, 235), symbolPen=pg.mkPen("k"))
            for k in range(len(tau)):
                plot.plot([tau[k], tau[k]], [lo[k], hi[k]],
                          pen=pg.mkPen(col, width=style.line_width))
    band = "median + 95% CI" if stat == "median" else "mean ± SEM"
    _axes(plot, style, left="direction autocorrelation",
          bottom="time interval τ (min)",
          title=f"DiPer direction autocorrelation by condition ({band})")
    plot.setYRange(-0.2, 1.05)


def scatter(plot, per_rec, mx, my, design, pick_cb=None, style=None):
    style = style or PlotStyle()
    if mx not in per_rec.columns or my not in per_rec.columns:
        return
    # fit is driven by two combos: the model (fit_kind, none = off) and the
    # target (fit_target: all data / per group / both) — no conflicting toggles
    kind = style.fit_kind
    tgt = style.fit_target
    fit_groups = kind != "none" and tgt in ("per group", "both")
    fit_all = kind != "none" and tgt in ("all data", "both")
    for cond in compare.order_conditions(per_rec["condition"].unique(),
                                         order=design.condition_order()):
        sub = per_rec[per_rec["condition"] == cond]
        spots = [{"pos": (float(r[mx]), float(r[my])), "data": r["recording"]}
                 for _, r in sub.iterrows()
                 if np.isfinite(r[mx]) and np.isfinite(r[my])]
        col = _rgb(design.color(cond))
        if spots:
            sp = pg.ScatterPlotItem(size=style.point_size, pen=pg.mkPen("k"),
                                    brush=pg.mkBrush(*col, 220))
            sp.addPoints(spots)
            _pick(sp, pick_cb)
            plot.addItem(sp)
            _legend_entry(plot, cond, col, style)
        if fit_groups:
            _draw_fit(plot, sub[mx].to_numpy(float), sub[my].to_numpy(float),
                      kind, col, style)
    x = per_rec[mx].to_numpy(float)
    y = per_rec[my].to_numpy(float)
    ok = np.isfinite(x) & np.isfinite(y)
    title = f"{metric_docs.column_label(mx)} vs {metric_docs.column_label(my)}"
    if ok.sum() >= 3:
        from scipy.stats import spearmanr
        rho, p = spearmanr(x[ok], y[ok])
        title += f"   (Spearman ρ={rho:.2f}, p={p:.3f})"
    if kind != "none":
        title += f"   · {kind} fit"
    if fit_all:
        _draw_fit(plot, x, y, kind, (255, 215, 0), style)
    _axes(plot, style, left=metric_docs.axis_label(my), bottom=metric_docs.axis_label(mx),
          logx=style.log_x, logy=style.log_y, title=title)


def histogram(plot, per_cell, metric, design, style=None):
    """Per-cell distribution of ``metric``, one curve/bar set per group (shared
    bins, design colours). Complements the recording-level views."""
    style = style or PlotStyle()
    if per_cell is None or per_cell.empty or metric not in per_cell.columns:
        return
    allv = per_cell[metric].to_numpy(float)
    allv = allv[np.isfinite(allv)]
    if allv.size == 0:
        return
    lo, hi = np.percentile(allv, [0.5, 99.5])
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        lo, hi = float(allv.min()), float(allv.max()) + 1e-9
    edges = np.linspace(lo, hi, int(style.hist_bins) + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    width = (edges[1] - edges[0]) * 0.9
    for cond in _conds(per_cell, design):
        v = per_cell[per_cell["condition"] == cond][metric].to_numpy(float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            continue
        h, _ = np.histogram(v, bins=edges, density=style.hist_density)
        col = _rgb(design.color(cond))
        _legend_entry(plot, cond, col, style)
        if style.hist_bars:
            plot.addItem(pg.BarGraphItem(x=centres, height=h, width=width,
                                         brush=pg.mkBrush(*col, style.fill_alpha),
                                         pen=pg.mkPen(col)))
        else:
            plot.addItem(pg.PlotCurveItem(centres, h, fillLevel=0,
                                          pen=pg.mkPen(col, width=style.line_width),
                                          brush=pg.mkBrush(*col, style.fill_alpha)))
    _axes(plot, style, left="density" if style.hist_density else "cells",
          bottom=metric_docs.axis_label(metric), title="per-cell distribution by group")
