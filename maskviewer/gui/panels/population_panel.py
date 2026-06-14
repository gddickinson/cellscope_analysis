"""Population panel — plot a metric across ALL cells of the current recording.

Plot types: every cell's time-course, the population mean ± SEM/SD error band,
a histogram of the metric's distribution, and a flower plot (origin-centred
trajectories). Filters: minimum track length, cell state, exclude edge frames.
The per-(cell, frame) table is built once on Compute (`analysis.population`) and
cached, then plots are instant. Inspired by CellScope's flower/comparison plots.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import population, metric_docs

_KINDS = ["Time series (all cells)", "Mean ± error", "Histogram", "Flower plot"]


class PopulationPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = None
        self._um = None
        self._dt = None
        self._df = None
        self._flower = None

        self.title = QtWidgets.QLabel("Population (all cells)")
        self.title.setStyleSheet("font-weight: bold;")
        self.compute_btn = QtWidgets.QPushButton("Compute population")
        self.compute_btn.setToolTip("Measure every cell in every frame "
                                    "(one pass), then plot from the cache")
        self.compute_btn.clicked.connect(self._compute)

        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(_KINDS)
        self.kind.currentIndexChanged.connect(self._replot)
        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.err = QtWidgets.QComboBox()
        self.err.addItems(["SEM", "SD"])
        self.err.setToolTip("Error band for the mean")
        self.err.currentIndexChanged.connect(self._replot)
        self.show_cells = QtWidgets.QCheckBox("show cells")
        self.show_cells.setChecked(True)
        self.show_cells.setToolTip("Overlay faint individual-cell curves")
        self.show_cells.toggled.connect(self._replot)
        self.min_frames = QtWidgets.QSpinBox()
        self.min_frames.setRange(1, 9999)
        self.min_frames.setToolTip("Drop cells tracked for fewer frames than this")
        self.min_frames.valueChanged.connect(self._replot)
        self.state_sel = QtWidgets.QComboBox()
        self.state_sel.addItems(["all states", "spread", "rounded"])
        self.state_sel.setToolTip("Keep only frames in this state")
        self.state_sel.currentIndexChanged.connect(self._replot)
        self.exclude_edge = QtWidgets.QCheckBox("exclude edge")
        self.exclude_edge.setChecked(True)
        self.exclude_edge.setToolTip("Drop edge-truncated cell-frames")
        self.exclude_edge.toggled.connect(self._replot)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.2)

        form = QtWidgets.QFormLayout()
        form.addRow("Plot", self.kind)
        form.addRow("Metric", self.metric)
        erow = QtWidgets.QHBoxLayout()
        erow.addWidget(self.err)
        erow.addWidget(self.show_cells)
        form.addRow("Error", self._wrap(erow))
        form.addRow("Min frames", self.min_frames)
        form.addRow("State", self.state_sel)
        form.addRow(self.exclude_edge)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.compute_btn)
        lay.addLayout(form)
        lay.addWidget(self.plot, 1)

    # -- public ----------------------------------------------------------
    def set_recording(self, labels, um_per_px=None, dt_min=None):
        self._labels, self._um, self._dt = labels, um_per_px, dt_min
        self._df = self._flower = None
        self.plot.clear()
        self.title.setText("Population (all cells) — click Compute")

    # -- internal --------------------------------------------------------
    def _compute(self):
        if self._labels is None:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            self._df = population.population_table(self._labels, self._um, self._dt)
            self._flower = population.flower_tracks(self._labels, self._um)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        cols = population.metric_columns(self._df)
        cur = self.metric.currentText()
        self.metric.blockSignals(True)
        self.metric.clear()
        self.metric.addItems(cols)
        for i, c in enumerate(cols):
            tip = metric_docs.tooltip(c.rsplit("_um", 1)[0].rsplit("_px", 1)[0])
            if tip:
                self.metric.setItemData(i, tip, QtCore.Qt.ToolTipRole)
        if cur in cols:
            self.metric.setCurrentText(cur)
        self.metric.blockSignals(False)
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
        if self._df is None:
            return
        kind = self.kind.currentText()
        self.plot.clear()
        self.plot.getViewBox().setAspectLocked(kind == "Flower plot")
        if kind == "Flower plot":
            return self._plot_flower()
        df = self._filtered()
        metric = self.metric.currentText()
        if df is None or df.empty or metric not in df.columns:
            return
        if kind == "Histogram":
            self._plot_hist(df, metric)
        elif kind == "Mean ± error":
            self._plot_mean(df, metric)
        else:
            self._plot_timeseries(df, metric)

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

    @staticmethod
    def _wrap(layout):
        w = QtWidgets.QWidget()
        w.setLayout(layout)
        return w
