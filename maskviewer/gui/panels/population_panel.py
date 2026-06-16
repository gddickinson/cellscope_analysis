"""Population panel — plot metrics across ALL cells of the current recording.

Plot types: every cell's time-course; population mean ± SEM/SD; histogram;
flower plot (origin-centred trajectories); scatter of one metric vs another
(per cell, click a point to select that cell); lineage tree and division
timeline (divisions inferred from the masks). Filters: min track length, state, exclude
edge. The per-(cell, frame) table is built once on Compute and cached. Inspired
by CellScope's flower / comparison / lineage plots.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import population, metric_docs, lineage
from ..plot_export import save_plot
from ..task_runner import AsyncComputeMixin

_KINDS = ["Time series (all cells)", "Mean ± error", "Histogram", "Flower plot",
          "Scatter (X vs Y)", "Rose (net direction)", "Lineage tree",
          "Division timeline"]
_NEEDS_DF = {"Time series (all cells)", "Mean ± error", "Histogram",
             "Scatter (X vs Y)"}


class PopulationPanel(AsyncComputeMixin, QtWidgets.QWidget):
    cellSelected = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = None
        self._um = None
        self._dt = None
        self._df = None
        self._flower = None
        self._divisions = []
        self.table_provider = None      # callable -> cached population DataFrame

        self.title = QtWidgets.QLabel("Population (all cells)")
        self.title.setStyleSheet("font-weight: bold;")
        self.compute_btn = QtWidgets.QPushButton("Compute population")
        self.compute_btn.setToolTip("Measure every cell in every frame (one "
                                    "pass), then plot from the cache")
        self.compute_btn.clicked.connect(self._compute)
        self.save_btn = QtWidgets.QPushButton("Save plot…")
        self.save_btn.clicked.connect(lambda: save_plot(self.plot, self,
                                                        "population.png"))

        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(_KINDS)
        self.kind.currentIndexChanged.connect(self._replot)
        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.metric_y = QtWidgets.QComboBox()
        self.metric_y.setToolTip("Y metric (for the scatter plot)")
        self.metric_y.currentIndexChanged.connect(self._replot)
        self.err = QtWidgets.QComboBox()
        self.err.addItems(["SEM", "SD"])
        self.err.currentIndexChanged.connect(self._replot)
        self.show_cells = QtWidgets.QCheckBox("show cells")
        self.show_cells.setChecked(True)
        self.show_cells.toggled.connect(self._replot)
        self.min_frames = QtWidgets.QSpinBox()
        self.min_frames.setRange(1, 9999)
        self.min_frames.setToolTip("Drop cells tracked for fewer frames than this")
        self.min_frames.valueChanged.connect(self._replot)
        self.state_sel = QtWidgets.QComboBox()
        self.state_sel.addItems(["all states", "spread", "rounded"])
        self.state_sel.currentIndexChanged.connect(self._replot)
        self.exclude_edge = QtWidgets.QCheckBox("exclude edge")
        self.exclude_edge.setChecked(True)
        self.exclude_edge.toggled.connect(self._replot)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.2)

        form = QtWidgets.QFormLayout()
        form.addRow("Plot", self.kind)
        form.addRow("Metric (X)", self.metric)
        form.addRow("Metric (Y)", self.metric_y)
        erow = QtWidgets.QHBoxLayout()
        erow.addWidget(self.err)
        erow.addWidget(self.show_cells)
        form.addRow("Error", self._wrap(erow))
        form.addRow("Min frames", self.min_frames)
        form.addRow("State", self.state_sel)
        form.addRow(self.exclude_edge)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        brow = QtWidgets.QHBoxLayout()
        brow.addWidget(self.compute_btn)
        brow.addWidget(self.save_btn)
        lay.addLayout(brow)
        lay.addLayout(form)
        lay.addWidget(self.plot, 1)

    # -- public ----------------------------------------------------------
    def set_recording(self, labels, um_per_px=None, dt_min=None, divisions=None):
        self._labels, self._um, self._dt = labels, um_per_px, dt_min
        self._divisions = divisions or []
        self._df = self._flower = None
        self.plot.clear()
        self.title.setText("Population (all cells) — click Compute")

    # -- internal --------------------------------------------------------
    def _compute(self):
        if self._labels is None:
            return
        self._dispatch("Population", self._work, self._apply)

    def _work(self, progress_cb):
        df = (self.table_provider(progress_cb) if self.table_provider
              else population.population_table(self._labels, self._um, self._dt,
                                               progress_cb=progress_cb))
        return df, population.flower_tracks(self._labels, self._um)

    def _apply(self, result):
        self._df, self._flower = result
        cols = population.metric_columns(self._df)
        for combo in (self.metric, self.metric_y):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(cols)
            for i, c in enumerate(cols):
                tip = metric_docs.tooltip(c.rsplit("_um", 1)[0].rsplit("_px", 1)[0])
                if tip:
                    combo.setItemData(i, tip, QtCore.Qt.ToolTipRole)
            if cur in cols:
                combo.setCurrentText(cur)
            combo.blockSignals(False)
        n = 0 if self._df is None else self._df["cell_id"].nunique()
        self.title.setText(f"Population — {n} cells")
        self._replot()

    def _xcol(self, df):
        return "time_min" if "time_min" in df.columns else "frame"

    def _filtered(self):
        df = self._df
        if df is None or df.empty:
            return None
        if self.exclude_edge.isChecked() and "state" in df.columns:
            df = df[df["state"] != "edge"]
        st = self.state_sel.currentText()
        if st in ("spread", "rounded") and "state" in df.columns:
            df = df[df["state"] == st]
        if self.min_frames.value() > 1:
            keep = df.groupby("cell_id")["frame"].transform("size")
            df = df[keep >= self.min_frames.value()]
        return df

    def _replot(self):
        kind = self.kind.currentText()
        if self._labels is None:
            return
        if kind in _NEEDS_DF and self._df is None:
            return
        self.plot.clear()
        self.plot.getViewBox().setAspectLocked(kind in ("Flower plot",
                                                        "Rose (net direction)"))
        if kind == "Flower plot":
            return self._plot_flower()
        if kind == "Rose (net direction)":
            return self._plot_rose()
        if kind == "Lineage tree":
            return self._plot_lineage()
        if kind == "Division timeline":
            return self._plot_div_timeline()
        df = self._filtered()
        if df is None or df.empty:
            return
        if kind == "Scatter (X vs Y)":
            return self._plot_scatter(df)
        metric = self.metric.currentText()
        if metric not in df.columns:
            return
        if kind == "Histogram":
            self._plot_hist(df, metric)
        elif kind == "Mean ± error":
            self._plot_mean(df, metric)
        else:
            self._plot_timeseries(df, metric)

    def _plot_rose(self, n_bins=24):
        """Polar histogram of per-cell net-migration directions (image frame) — shows
        directional bias; the title's R is the mean resultant length (0 = uniform,
        1 = all one way)."""
        from PyQt5 import QtGui
        from ...analysis import cell_metrics
        angles = []
        for cen in cell_metrics.centroid_history(self._labels).values():
            fin = cen[np.isfinite(cen).all(axis=1)]
            if fin.shape[0] >= 2:
                dy, dx = fin[-1] - fin[0]
                if np.hypot(dy, dx) > 0:
                    angles.append(np.arctan2(-dy, dx))    # flip row so up = up
        if not angles:
            return
        a = np.asarray(angles)
        counts, edges = np.histogram(a, bins=n_bins, range=(-np.pi, np.pi))
        r = counts / counts.max() if counts.max() else counts.astype(float)
        for k in range(n_bins):
            poly = QtGui.QPolygonF([QtCore.QPointF(0, 0)])
            for ang in np.linspace(edges[k], edges[k + 1], 6):
                poly.append(QtCore.QPointF(r[k] * np.cos(ang), r[k] * np.sin(ang)))
            poly.append(QtCore.QPointF(0, 0))
            it = QtWidgets.QGraphicsPolygonItem(poly)
            it.setBrush(pg.mkBrush(70, 130, 230, 170)); it.setPen(pg.mkPen("k"))
            self.plot.addItem(it)
        for rad in (0.5, 1.0):                            # grid rings
            t = np.linspace(0, 2 * np.pi, 80)
            self.plot.plot(rad * np.cos(t), rad * np.sin(t),
                           pen=pg.mkPen((150, 150, 150), width=1))
        R = float(np.hypot(np.cos(a).mean(), np.sin(a).mean()))
        self.plot.setTitle(f"net-direction rose · n={a.size} cells · R={R:.2f}")
        self.plot.setLabel("bottom", "→ x"); self.plot.setLabel("left", "↑ y")

    def _plot_timeseries(self, df, metric):
        x = self._xcol(df)
        for _, g in df.groupby("cell_id"):
            g = g.sort_values(x)
            self.plot.plot(g[x].to_numpy(float), g[metric].to_numpy(float),
                           pen=pg.mkPen((90, 160, 255, 70)))
        self.plot.setLabel("left", metric)
        self.plot.setLabel("bottom", "time (min)" if x == "time_min" else "frame")

    def _plot_mean(self, df, metric):
        x = self._xcol(df)
        if self.show_cells.isChecked():
            for _, g in df.groupby("cell_id"):
                g = g.sort_values(x)
                self.plot.plot(g[x].to_numpy(float), g[metric].to_numpy(float),
                               pen=pg.mkPen((150, 150, 150, 45)))
        grp = df.groupby(x)[metric]
        xs = grp.mean().index.to_numpy(float)
        m = grp.mean().to_numpy()
        e = (grp.sem() if self.err.currentText() == "SEM" else grp.std()).to_numpy()
        e = np.nan_to_num(e)
        top = pg.PlotDataItem(xs, m + e)
        bot = pg.PlotDataItem(xs, m - e)
        self.plot.addItem(pg.FillBetweenItem(top, bot, brush=(0, 160, 255, 80)))
        self.plot.plot(xs, m, pen=pg.mkPen((0, 120, 255), width=2),
                       symbol="o", symbolSize=4, symbolBrush=(0, 120, 255))
        self.plot.setLabel("left", f"{metric}  (mean ± {self.err.currentText()})")
        self.plot.setLabel("bottom", "time (min)" if x == "time_min" else "frame")

    def _plot_hist(self, df, metric):
        vals = df[metric].to_numpy(float)
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            return
        y, edges = np.histogram(vals, bins=40)
        self.plot.plot(edges, y, stepMode=True, fillLevel=0,
                       brush=(0, 160, 255, 120), pen=pg.mkPen((0, 120, 255)))
        self.plot.setLabel("bottom", metric)
        self.plot.setLabel("left", "count (cell-frames)")

    def _plot_scatter(self, df):
        mx, my = self.metric.currentText(), self.metric_y.currentText()
        if mx not in df.columns or my not in df.columns:
            return
        gm = df.groupby("cell_id")
        xs, ys = gm[mx].mean(), gm[my].mean()
        spots = [{"pos": (float(xs[c]), float(ys[c])), "data": int(c)}
                 for c in xs.index
                 if np.isfinite(xs[c]) and np.isfinite(ys[c])]
        sp = pg.ScatterPlotItem(size=10, brush=(0, 160, 255, 160),
                                pen=pg.mkPen("w"))
        sp.addPoints(spots)
        sp.sigClicked.connect(self._scatter_clicked)
        self.plot.addItem(sp)
        self.plot.setLabel("bottom", f"{mx} (per-cell mean)")
        self.plot.setLabel("left", f"{my} (per-cell mean)")

    def _scatter_clicked(self, _scatter, points):
        if len(points):
            self.cellSelected.emit(int(points[0].data()))

    def _plot_flower(self):
        if not self._flower:
            return
        import matplotlib
        cmap = matplotlib.colormaps["hsv"]
        n = max(len(self._flower) - 1, 1)
        for i, cid in enumerate(sorted(self._flower)):
            rel = self._flower[cid]
            c = cmap(i / n)
            self.plot.plot(rel[:, 1], rel[:, 0],
                           pen=pg.mkPen([int(v * 255) for v in c[:3]], width=1))
        self.plot.addItem(pg.ScatterPlotItem([0], [0], symbol="+", size=16,
                                             pen=pg.mkPen("w", width=2)))
        u = "µm" if self._um else "px"
        self.plot.setLabel("bottom", f"x from origin ({u})")
        self.plot.setLabel("left", f"y from origin ({u})")

    def _plot_lineage(self):
        spans = lineage.track_spans(self._labels)
        if not spans:
            return
        rows = lineage.lineage_rows(spans)
        dt = self._dt or 1.0
        for cid, (f0, f1) in spans.items():
            y = rows[cid]
            self.plot.plot([f0 * dt, f1 * dt], [y, y],
                           pen=pg.mkPen((150, 150, 150)))
        for d in self._divisions:
            if d["parent"] in rows and d["daughter"] in rows:
                fr = d["frame"] * dt
                self.plot.plot([fr, fr], [rows[d["parent"]], rows[d["daughter"]]],
                               pen=pg.mkPen((214, 39, 40), width=2))
        self.plot.setLabel("bottom", "time (min)" if self._dt else "frame")
        self.plot.setLabel("left", "track (lifeline row)")

    def _plot_div_timeline(self):
        n = self._labels.shape[0]
        counts = lineage.division_counts(self._divisions, n)
        dt = self._dt or 1.0
        x = np.arange(n) * dt
        self.plot.addItem(pg.BarGraphItem(x=x, height=counts, width=0.8 * dt,
                                          brush=(214, 39, 40, 150)))
        self.plot.plot(x, np.cumsum(counts), pen=pg.mkPen((0, 120, 255), width=2))
        self.plot.setLabel("bottom", "time (min)" if self._dt else "frame")
        self.plot.setLabel("left", "divisions / cumulative")

    @staticmethod
    def _wrap(layout):
        w = QtWidgets.QWidget()
        w.setLayout(layout)
        return w
