"""Comparison panel — compare a metric across recordings, grouped by condition.

**Recording = experimental unit.** Computes per-cell metrics for every discovered
recording (background thread + progress + cancel; cached to disk) and plots, by
condition:
  * Recording means — strip of per-recording values + mean ± SEM.
  * Box by condition — box + strip with Bonferroni significance stars vs control.
  * Superplot — per-cell cloud (by recording) behind the per-recording means.
  * Ensemble MSD — per-condition MSD(τ), mean ± SEM or median + bootstrap CI.
  * Scatter (X vs Y) — per-recording points coloured by condition + Spearman.
Stats reuse the IC295 arm structure (`feature_tables.arm_tests`): per-arm
Kruskal-Wallis + within-arm Bonferroni vs control + the WT-vs-DMSO vehicle test,
plus an optional covariate-adjusted OLS (outcome ~ treatment + frac_spread +
density). Click a point to load that recording; export the tables.
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import compare, metric_docs, feature_tables
from ...config import PROJECT_ROOT
from ..plot_export import save_plot

_REC_PALETTE = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
                (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127)]
_KINDS = ["Recording means", "Box by condition", "Superplot (cells + means)",
          "Ensemble MSD", "Scatter (X vs Y)"]


class _Worker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(object)

    def __init__(self, entries):
        super().__init__()
        self.entries = entries
        self.cancel = False

    def _cb(self, i, n):
        self.progress.emit(i, n)
        return not self.cancel

    def run(self):
        try:
            res = compare.build_comparison(self.entries, progress_cb=self._cb)
        except Exception as exc:                          # surface, don't crash
            res = exc
        self.done.emit(res)


class ComparePanel(QtWidgets.QWidget):
    recordingPicked = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []
        self._per_cell = None
        self._msd = None
        self._thread = self._worker = None
        self._cache = os.path.join(PROJECT_ROOT, "analysis_out", "_comparison.pkl")

        self.title = QtWidgets.QLabel("Compare recordings (by condition)")
        self.title.setStyleSheet("font-weight: bold;")
        self.info = QtWidgets.QLabel(
            "Per-cell metrics across ALL recordings (recording = unit). First run "
            "can take minutes; result is cached.")
        self.info.setWordWrap(True)
        self.compute_btn = QtWidgets.QPushButton("Compute comparison")
        self.compute_btn.clicked.connect(self._compute)
        self.recompute = QtWidgets.QCheckBox("ignore cache")
        self.progress = QtWidgets.QProgressBar()
        self.progress.hide()

        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.metric_y = QtWidgets.QComboBox()
        self.metric_y.setToolTip("Y metric (for the scatter)")
        self.metric_y.currentIndexChanged.connect(self._replot)
        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(_KINDS)
        self.kind.currentIndexChanged.connect(self._replot)
        self.stat = QtWidgets.QComboBox()
        self.stat.addItems(["mean ± SEM", "median ± 95% CI"])
        self.stat.setToolTip("Ensemble-MSD centre + error")
        self.stat.currentIndexChanged.connect(self._replot)
        self.min_frames = QtWidgets.QSpinBox()
        self.min_frames.setRange(1, 9999)
        self.min_frames.valueChanged.connect(self._replot)
        self.ols = QtWidgets.QCheckBox("covariate-adjusted (OLS)")
        self.ols.setToolTip("Add treatment effect after frac_spread + density "
                            "(OLS, recording level)")
        self.ols.toggled.connect(self._replot)
        self.save_btn = QtWidgets.QPushButton("Save plot…")
        self.save_btn.clicked.connect(lambda: save_plot(self.plot, self,
                                                        "comparison.png"))
        self.export_btn = QtWidgets.QPushButton("Export CSV…")
        self.export_btn.clicked.connect(self._export)
        self.export_btn.setEnabled(False)

        self.stats = QtWidgets.QLabel("")
        self.stats.setWordWrap(True)
        self.stats.setTextInteractionFlags(self.stats.textInteractionFlags() | 0x1)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.2)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.info)
        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(self.compute_btn)
        crow.addWidget(self.recompute)
        lay.addLayout(crow)
        lay.addWidget(self.progress)
        form = QtWidgets.QFormLayout()
        form.addRow("Plot", self.kind)
        form.addRow("Metric", self.metric)
        form.addRow("Metric (Y)", self.metric_y)
        form.addRow("MSD stat", self.stat)
        form.addRow("Min frames", self.min_frames)
        form.addRow(self.ols)
        lay.addLayout(form)
        brow = QtWidgets.QHBoxLayout()
        brow.addWidget(self.save_btn)
        brow.addWidget(self.export_btn)
        lay.addLayout(brow)
        lay.addWidget(self.stats)
        lay.addWidget(self.plot, 1)

    # -- public ----------------------------------------------------------
    def set_entries(self, entries):
        self._entries = list(entries)

    # -- compute ---------------------------------------------------------
    def _compute(self):
        if self._thread is not None and self._thread.isRunning():
            if self._worker:
                self._worker.cancel = True
            return
        if not self._entries:
            return
        if os.path.exists(self._cache) and not self.recompute.isChecked():
            try:
                with open(self._cache, "rb") as f:
                    blob = pickle.load(f)
                return self._on_done((blob["per_cell"], blob.get("msd")), cached=True)
            except Exception:
                pass
        self.compute_btn.setText("Cancel")
        self.progress.setValue(0)
        self.progress.show()
        self._thread = QtCore.QThread(self)
        self._worker = _Worker(self._entries)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(lambda r: self._on_done(r, cached=False))
        self._thread.start()

    def _on_progress(self, i, n):
        self.progress.setValue(int(100 * i / n) if n else 0)

    def _stop_thread(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = self._worker = None

    def _on_done(self, result, cached):
        self._stop_thread()
        self.compute_btn.setText("Compute comparison")
        self.progress.hide()
        if isinstance(result, Exception):
            self.info.setText(f"Compute failed: {result}")
            return
        per_cell, msd = result
        if per_cell is None or per_cell.empty:
            self.info.setText("No cells found across recordings.")
            return
        self._per_cell, self._msd = per_cell, msd
        if not cached:
            try:
                os.makedirs(os.path.dirname(self._cache), exist_ok=True)
                with open(self._cache, "wb") as f:
                    pickle.dump({"per_cell": per_cell, "msd": msd}, f)
            except Exception:
                pass
        cols = compare.metric_columns(per_cell)
        for combo in (self.metric, self.metric_y):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(cols)
            for i, c in enumerate(cols):
                base = c.replace("mean_", "").replace("median_", "")
                base = base.rsplit("_um", 1)[0].rsplit("_px", 1)[0]
                tip = metric_docs.tooltip(base)
                if tip:
                    combo.setItemData(i, tip, QtCore.Qt.ToolTipRole)
            default = "mean_area_um2" if "mean_area_um2" in cols else (cols[0] if cols else "")
            combo.setCurrentText(cur if cur in cols else default)
            combo.blockSignals(False)
        self.info.setText(
            f"{per_cell['recording'].nunique()} recordings · "
            f"{per_cell['condition'].nunique()} conditions · {len(per_cell)} cells"
            + ("  (cached)" if cached else ""))
        self.export_btn.setEnabled(True)
        self._replot()

    # -- plot / stats ----------------------------------------------------
    def _filtered(self):
        pc = self._per_cell
        mf = self.min_frames.value()
        if mf > 1 and "frames_tracked" in pc.columns:
            pc = pc[pc["frames_tracked"] >= mf]
        return pc

    def _cond_color(self, cond):
        hexc = feature_tables.COND_COLOR.get(cond)
        if hexc:
            h = hexc.lstrip("#")
            return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))
        return (120, 120, 120)

    def _ticks(self, conds):
        self.plot.getAxis("bottom").setTicks([[(i, c) for i, c in enumerate(conds)]])
        self.plot.setLabel("bottom", "")

    def _replot(self):
        if self._per_cell is None or self._per_cell.empty:
            return
        self.plot.clear()
        self.plot.setLogMode(x=False, y=False)
        self.stats.setText("")
        kind = self.kind.currentText()
        if kind == "Ensemble MSD":
            return self._plot_ensemble()
        pc = self._filtered()
        metric = self.metric.currentText()
        if pc.empty or not metric:
            return
        per_rec = compare.aggregate(pc)
        if metric not in per_rec.columns:
            return
        if kind == "Box by condition":
            self._plot_box(per_rec, metric)
        elif kind.startswith("Superplot"):
            self._plot_super(pc, per_rec, metric)
        elif kind == "Scatter (X vs Y)":
            return self._plot_scatter(per_rec)
        else:
            self._plot_means(per_rec, metric)
        self._stats(per_rec, metric)

    def _plot_means(self, per_rec, metric):
        conds = compare.order_conditions(per_rec["condition"].unique())
        rng = np.random.default_rng(0)
        for i, cond in enumerate(conds):
            sub = per_rec[per_rec["condition"] == cond]
            col = self._cond_color(cond)
            spots = [{"pos": (i + float(rng.uniform(-0.12, 0.12)), float(r[metric])),
                      "data": r["recording"], "brush": pg.mkBrush(*col, 210)}
                     for _, r in sub.iterrows() if np.isfinite(r[metric])]
            if not spots:
                continue
            sp = pg.ScatterPlotItem(size=11, pen=pg.mkPen("k"))
            sp.addPoints(spots)
            sp.sigClicked.connect(self._point_clicked)
            self.plot.addItem(sp)
            vals = np.array([s["pos"][1] for s in spots])
            mean = vals.mean()
            sem = vals.std(ddof=1) / np.sqrt(vals.size) if vals.size > 1 else 0.0
            self.plot.addItem(pg.ErrorBarItem(x=np.array([i]), y=np.array([mean]),
                                              height=np.array([2 * sem]), beam=0.12,
                                              pen=pg.mkPen("w", width=2)))
            self.plot.plot([i - 0.22, i + 0.22], [mean, mean],
                           pen=pg.mkPen("w", width=2))
        self._ticks(conds)
        self.plot.setLabel("left", metric)
        self.plot.setTitle("each point = one recording (mean ± SEM)")

    def _plot_box(self, per_rec, metric):
        conds = compare.order_conditions(per_rec["condition"].unique())
        bc = compare.by_condition(per_rec, metric)
        r = feature_tables.arm_tests(bc)
        rng = np.random.default_rng(0)
        for i, cond in enumerate(conds):
            v = np.array(bc.get(cond, []), float)
            v = v[np.isfinite(v)]
            if v.size == 0:
                continue
            q1, med, q3 = np.percentile(v, [25, 50, 75])
            col = self._cond_color(cond)
            pen = pg.mkPen(col, width=1.6)
            for x0, y0, x1, y1 in [(i - .25, q1, i + .25, q1), (i - .25, q3, i + .25, q3),
                                   (i - .25, q1, i - .25, q3), (i + .25, q1, i + .25, q3)]:
                self.plot.plot([x0, x1], [y0, y1], pen=pen)
            self.plot.plot([i - .25, i + .25], [med, med], pen=pg.mkPen(col, width=2.5))
            self.plot.plot([i, i], [v.min(), q1], pen=pen)
            self.plot.plot([i, i], [q3, v.max()], pen=pen)
            x = i + rng.uniform(-0.09, 0.09, v.size)
            self.plot.addItem(pg.ScatterPlotItem(x, v, size=7,
                                                 brush=pg.mkBrush(*col, 160), pen=None))
        for arm, spec in feature_tables.ARMS.items():
            ctrl = spec["control"]
            for t in [c for c in spec["conditions"] if c != ctrl]:
                if t in conds and bc.get(t):
                    pb = r[arm]["pairs"].get(f"{ctrl}_vs_{t}", {}).get("p_bonf")
                    star = feature_tables.stars(pb).split()[-1] if pb is not None else ""
                    if star in ("*", "**", "***"):
                        lbl = pg.TextItem(star, color="w", anchor=(0.5, 1))
                        lbl.setPos(conds.index(t), max(bc[t]))
                        self.plot.addItem(lbl)
        self._ticks(conds)
        self.plot.setLabel("left", metric)
        self.plot.setTitle("box = recordings/condition · * vs arm control (Bonferroni)")

    def _plot_super(self, per_cell, per_rec, metric):
        conds = compare.order_conditions(per_cell["condition"].unique())
        rng = np.random.default_rng(0)
        for i, cond in enumerate(conds):
            cc = per_cell[per_cell["condition"] == cond]
            for ri, rec in enumerate(cc["recording"].unique()):
                v = cc[cc["recording"] == rec][metric].to_numpy(float)
                v = v[np.isfinite(v)]
                if v.size:
                    self.plot.addItem(pg.ScatterPlotItem(
                        i + rng.uniform(-0.18, 0.18, v.size), v, size=4,
                        brush=pg.mkBrush(*_REC_PALETTE[ri % len(_REC_PALETTE)], 90),
                        pen=None))
            mr = per_rec[per_rec["condition"] == cond][metric].to_numpy(float)
            mr = mr[np.isfinite(mr)]
            if mr.size:
                self.plot.addItem(pg.ScatterPlotItem(
                    i + rng.uniform(-0.1, 0.1, mr.size), mr, size=12,
                    brush=pg.mkBrush(*self._cond_color(cond), 235),
                    pen=pg.mkPen("k", width=1.5)))
                self.plot.plot([i - 0.22, i + 0.22], [mr.mean(), mr.mean()],
                               pen=pg.mkPen("w", width=2))
        self._ticks(conds)
        self.plot.setLabel("left", metric)
        self.plot.setTitle("small = cells (by recording) · large = recording means")

    def _plot_ensemble(self):
        if self._msd is None or self._msd.empty:
            self.plot.setTitle("no ensemble MSD (recompute to build it)")
            return
        stat = "median" if self.stat.currentText().startswith("median") else "mean"
        ens = compare.ensemble_by_condition(self._msd, stat=stat)
        for cond in compare.order_conditions(ens):
            tau, centre, lo, hi = ens[cond]
            col = self._cond_color(cond)
            top, bot = pg.PlotDataItem(tau, hi), pg.PlotDataItem(tau, lo)
            self.plot.addItem(pg.FillBetweenItem(top, bot, brush=pg.mkBrush(*col, 60)))
            self.plot.plot(tau, centre, pen=pg.mkPen(col, width=2), name=cond)
        self.plot.setLogMode(x=True, y=True)
        self.plot.setLabel("bottom", "lag τ (min)")
        self.plot.setLabel("left", "MSD (µm²)")
        self.plot.setTitle(f"ensemble MSD by condition ({self.stat.currentText()})")

    def _plot_scatter(self, per_rec):
        mx, my = self.metric.currentText(), self.metric_y.currentText()
        if mx not in per_rec.columns or my not in per_rec.columns:
            return
        for cond in compare.order_conditions(per_rec["condition"].unique()):
            sub = per_rec[per_rec["condition"] == cond]
            spots = [{"pos": (float(r[mx]), float(r[my])), "data": r["recording"]}
                     for _, r in sub.iterrows()
                     if np.isfinite(r[mx]) and np.isfinite(r[my])]
            if spots:
                sp = pg.ScatterPlotItem(size=11, pen=pg.mkPen("k"),
                                        brush=pg.mkBrush(*self._cond_color(cond), 220))
                sp.addPoints(spots)
                sp.sigClicked.connect(self._point_clicked)
                self.plot.addItem(sp)
        x = per_rec[mx].to_numpy(float)
        y = per_rec[my].to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y)
        title = f"{mx} vs {my}"
        if ok.sum() >= 3:
            from scipy.stats import spearmanr
            rho, p = spearmanr(x[ok], y[ok])
            title += f"   (Spearman ρ={rho:.2f}, p={p:.3f})"
        self.plot.setLabel("bottom", mx)
        self.plot.setLabel("left", my)
        self.plot.setTitle(title)

    def _stats(self, per_rec, metric):
        bc = compare.by_condition(per_rec, metric)
        kw_all = feature_tables._kw(list(bc.values()))
        lines = [f"<b>omnibus KW</b> ({len(bc)} conditions): "
                 f"{feature_tables.stars(kw_all)}"]
        r = feature_tables.arm_tests(bc)
        for arm, spec in feature_tables.ARMS.items():
            ctrl = spec["control"]
            bits = [f"KW {feature_tables.stars(r[arm]['kw'])}"]
            for t in [c for c in spec["conditions"] if c != ctrl]:
                pr = r[arm]["pairs"].get(f"{ctrl}_vs_{t}", {})
                bits.append(f"{t}v{ctrl} {feature_tables.stars(pr.get('p_bonf'))}")
            lines.append(f"<b>{arm}</b>: " + " · ".join(bits))
        lines.append(f"<b>vehicle</b> WT vs DMSO: "
                     f"{feature_tables.stars(r['vehicle']['p'])}")
        if self.ols.isChecked():
            ols = compare.ols_adjusted(per_rec, metric)
            if ols:
                lines.append("<b>covariate-adjusted (OLS · +frac_spread +density):</b>")
                for o in ols:
                    lines.append(f"&nbsp;&nbsp;{o['arm']} {o['contrast']}: "
                                 f"β={o['coef']:.3g} "
                                 f"[{o['ci_lo']:.3g}, {o['ci_hi']:.3g}] "
                                 f"{feature_tables.stars(o['p'])}")
        self.stats.setText("<br>".join(lines))

    def _point_clicked(self, _scatter, points):
        if len(points):
            self.recordingPicked.emit(str(points[0].data()))

    def _export(self):
        if self._per_cell is None:
            return
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Export comparison CSVs")
        if not d:
            return
        pc = self._filtered()
        pc.to_csv(os.path.join(d, "comparison_per_cell.csv"), index=False)
        compare.aggregate(pc).to_csv(
            os.path.join(d, "comparison_per_recording.csv"), index=False)
        if self._msd is not None and not self._msd.empty:
            self._msd.to_csv(os.path.join(d, "comparison_ensemble_msd.csv"),
                             index=False)
        QtWidgets.QMessageBox.information(self, "Exported", f"CSVs written to {d}")
