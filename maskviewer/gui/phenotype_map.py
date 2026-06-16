"""2D phenotype map (Comparison ▸ Stats ▸ Phenotype map…).

The per-**cell** cloud of two metrics, coloured by condition, with a 1σ + 2σ
covariance ellipse per condition — makes a multivariate phenotype (e.g. the KO
'rounder + less persistent' axis) visible as a figure rather than a PERMANOVA number.
Cells (not recordings) are the points so the distribution is meaningful.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets

from ..analysis import compare, metric_docs


def _rgb(hexc):
    h = hexc.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _ellipse(xy, nsd, n=64):
    """``(n, 2)`` points of the ``nsd``-σ covariance ellipse of point cloud ``xy``."""
    if xy.shape[0] < 3:
        return None
    mean = xy.mean(axis=0)
    cov = np.cov(xy.T)
    vals, vecs = np.linalg.eigh(cov)
    vals = np.clip(vals, 0.0, None)
    t = np.linspace(0, 2 * np.pi, n)
    circ = np.column_stack([np.cos(t), np.sin(t)]) * (nsd * np.sqrt(vals))
    return circ @ vecs.T + mean


class PhenotypeMapDialog(QtWidgets.QDialog):
    def __init__(self, per_cell, design, parent=None):
        super().__init__(parent)
        self.per_cell = per_cell
        self.design = design
        self.setWindowTitle("Phenotype map")
        self.resize(720, 640)
        cols = compare.metric_columns(per_cell)
        lay = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        self.mx = QtWidgets.QComboBox(); self.mx.addItems(cols)
        self.my = QtWidgets.QComboBox(); self.my.addItems(cols)
        self.mx.setCurrentText(_pref(cols, ("shape_roundness", "mean_circularity",
                                            "frac_rounded"), 0))
        self.my.setCurrentText(_pref(cols, ("persistence_dir_autocorr", "straightness",
                                            "mean_speed_um_per_min"), 1))
        for w in (QtWidgets.QLabel("X"), self.mx, QtWidgets.QLabel("Y"), self.my):
            row.addWidget(w)
        row.addStretch(1)
        lay.addLayout(row)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.addLegend(offset=(-10, 10))
        lay.addWidget(self.plot, 1)
        for c in (self.mx, self.my):
            c.currentIndexChanged.connect(self._draw)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._draw()

    def _draw(self):
        self.plot.clear()
        mx, my = self.mx.currentText(), self.my.currentText()
        if mx not in self.per_cell.columns or my not in self.per_cell.columns:
            return
        rng = np.random.default_rng(0)
        conds = compare.order_conditions(self.per_cell["condition"].unique(),
                                         order=self.design.condition_order())
        for cond in conds:
            sub = self.per_cell[self.per_cell["condition"] == cond]
            xy = sub[[mx, my]].to_numpy(float)
            xy = xy[np.isfinite(xy).all(axis=1)]
            if xy.shape[0] == 0:
                continue
            col = _rgb(self.design.color(cond))
            pts = xy if xy.shape[0] <= 600 else xy[rng.choice(xy.shape[0], 600, replace=False)]
            self.plot.addItem(pg.ScatterPlotItem(
                pts[:, 0], pts[:, 1], size=4, pen=None, brush=pg.mkBrush(*col, 70)))
            self.plot.plot([], [], name=f"{cond} (n={xy.shape[0]})",
                           pen=pg.mkPen(col, width=3))
            for nsd, w in ((1, 2), (2, 1)):
                e = _ellipse(xy, nsd)
                if e is not None:
                    self.plot.plot(e[:, 0], e[:, 1], pen=pg.mkPen(*col, width=w))
        self.plot.setLabel("bottom", metric_docs.axis_label(mx))
        self.plot.setLabel("left", metric_docs.axis_label(my))
        self.plot.setTitle("per-cell phenotype cloud · 1σ + 2σ covariance ellipse / group")


def _pref(cols, prefs, fallback_idx):
    for p in prefs:
        if p in cols:
            return p
    return cols[min(fallback_idx, len(cols) - 1)] if cols else ""
