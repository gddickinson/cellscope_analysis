"""Comparison panel — compare a metric across recordings, grouped by condition.

**Recording = experimental unit.** Computes per-cell metrics for every discovered
recording (background thread + progress + cancel; cached to disk), aggregates to
one value per recording, and plots:
  * Recording means — a strip of per-recording values per condition + mean ± SEM.
  * Superplot — the per-cell cloud (coloured by recording) behind the
    per-recording means.
Stats reuse the IC295 arm structure (`feature_tables.arm_tests`): per-arm
Kruskal-Wallis + within-arm Bonferroni vs control + the WT-vs-DMSO vehicle test,
plus an omnibus KW. Click a point to load that recording. Exports the tables.
"""
from __future__ import annotations

import os

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import compare, metric_docs, feature_tables
from ...config import PROJECT_ROOT
from ..plot_export import save_plot

_REC_PALETTE = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
                (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127)]


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
            df = compare.build_comparison(self.entries, progress_cb=self._cb)
        except Exception as exc:                          # surface, don't crash
            df = exc
        self.done.emit(df)


class ComparePanel(QtWidgets.QWidget):
    recordingPicked = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []
        self._per_cell = None
        self._thread = self._worker = None
        self._cache = os.path.join(PROJECT_ROOT, "analysis_out",
                                   "_comparison_per_cell.csv")

        self.title = QtWidgets.QLabel("Compare recordings (by condition)")
        self.title.setStyleSheet("font-weight: bold;")
        self.info = QtWidgets.QLabel(
            "Compares per-cell metrics across ALL recordings (recording = unit). "
            "First run can take minutes; result is cached.")
        self.info.setWordWrap(True)
        self.compute_btn = QtWidgets.QPushButton("Compute comparison")
        self.compute_btn.clicked.connect(self._compute)
        self.recompute = QtWidgets.QCheckBox("ignore cache")
        self.recompute.setToolTip("Recompute from masks instead of the cached table")
        self.progress = QtWidgets.QProgressBar()
        self.progress.hide()

        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(["Recording means", "Superplot (cells + means)"])
        self.kind.currentIndexChanged.connect(self._replot)
        self.min_frames = QtWidgets.QSpinBox()
        self.min_frames.setRange(1, 9999)
        self.min_frames.setToolTip("Drop cells tracked fewer frames than this "
                                   "before aggregating")
        self.min_frames.valueChanged.connect(self._replot)
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
        form.addRow("Metric", self.metric)
        form.addRow("Plot", self.kind)
        form.addRow("Min frames", self.min_frames)
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
            import pandas as pd
            try:
                return self._on_done(pd.read_csv(self._cache), cached=True)
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
        if result is None or result.empty:
            self.info.setText("No cells found across recordings.")
            return
        self._per_cell = result
        if not cached:
            try:
                os.makedirs(os.path.dirname(self._cache), exist_ok=True)
                result.to_csv(self._cache, index=False)
            except Exception:
                pass
        cols = compare.metric_columns(result)
        cur = self.metric.currentText()
        self.metric.blockSignals(True)
        self.metric.clear()
        self.metric.addItems(cols)
        for i, c in enumerate(cols):
            base = c.replace("mean_", "").replace("median_", "")
            base = base.rsplit("_um", 1)[0].rsplit("_px", 1)[0]
            tip = metric_docs.tooltip(base)
            if tip:
                self.metric.setItemData(i, tip, QtCore.Qt.ToolTipRole)
        default = "mean_area_um2" if "mean_area_um2" in cols else (cols[0] if cols else "")
        self.metric.setCurrentText(cur if cur in cols else default)
        self.metric.blockSignals(False)
        self.info.setText(
            f"{result['recording'].nunique()} recordings · "
            f"{result['condition'].nunique()} conditions · {len(result)} cells"
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

    def _replot(self):
        if self._per_cell is None or self._per_cell.empty:
            return
        metric = self.metric.currentText()
        pc = self._filtered()
        if not metric or pc.empty:
            return
        per_rec = compare.aggregate(pc)
        if metric not in per_rec.columns:
            return
        self.plot.clear()
        if self.kind.currentText().startswith("Superplot"):
            self._plot_super(pc, per_rec, metric)
        else:
            self._plot_means(per_rec, metric)
        self._stats(per_rec, metric)

    def _ticks(self, conds):
        self.plot.getAxis("bottom").setTicks([[(i, c) for i, c in enumerate(conds)]])
        self.plot.setLabel("bottom", "")

    def _plot_means(self, per_rec, metric):
        conds = compare.order_conditions(per_rec["condition"].unique())
        rng = np.random.default_rng(0)
        for i, cond in enumerate(conds):
            sub = per_rec[per_rec["condition"] == cond]
            col = self._cond_color(cond)
            spots = []
            for _, r in sub.iterrows():
                v = r[metric]
                if np.isfinite(v):
                    spots.append({"pos": (i + float(rng.uniform(-0.12, 0.12)),
                                          float(v)), "data": r["recording"],
                                  "brush": pg.mkBrush(*col, 210)})
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

    def _plot_super(self, per_cell, per_rec, metric):
        conds = compare.order_conditions(per_cell["condition"].unique())
        rng = np.random.default_rng(0)
        for i, cond in enumerate(conds):
            cc = per_cell[per_cell["condition"] == cond]
            for ri, rec in enumerate(cc["recording"].unique()):
                v = cc[cc["recording"] == rec][metric].to_numpy(float)
                v = v[np.isfinite(v)]
                if v.size:
                    x = i + rng.uniform(-0.18, 0.18, v.size)
                    col = _REC_PALETTE[ri % len(_REC_PALETTE)]
                    self.plot.addItem(pg.ScatterPlotItem(
                        x, v, size=4, brush=pg.mkBrush(*col, 90), pen=None))
            mr = per_rec[per_rec["condition"] == cond][metric].to_numpy(float)
            mr = mr[np.isfinite(mr)]
            if mr.size:
                xm = i + rng.uniform(-0.1, 0.1, mr.size)
                self.plot.addItem(pg.ScatterPlotItem(
                    xm, mr, size=12, brush=pg.mkBrush(*self._cond_color(cond), 235),
                    pen=pg.mkPen("k", width=1.5)))
                self.plot.plot([i - 0.22, i + 0.22], [mr.mean(), mr.mean()],
                               pen=pg.mkPen("w", width=2))
        self._ticks(conds)
        self.plot.setLabel("left", metric)
        self.plot.setTitle("small = cells (by recording) · large = recording means")

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
        QtWidgets.QMessageBox.information(
            self, "Exported",
            "comparison_per_cell.csv + comparison_per_recording.csv")
