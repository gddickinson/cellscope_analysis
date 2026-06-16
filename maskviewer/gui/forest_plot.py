"""Effect-size forest plot (Comparison ▸ Stats ▸ Forest…).

Cohen's d (test vs control) ± 95% bootstrap CI for **every metric**, sorted by |d| —
a one-figure view of where two groups differ most (the multivariate phenotype the
PERMANOVA/AUC summarises as a number). Recording = unit. Points red where the
Mann-Whitney p < 0.05; bars are the bootstrap CI; the dashed line is d = 0.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ..analysis import compare, metric_docs


class ForestPlotDialog(QtWidgets.QDialog):
    def __init__(self, per_rec, conditions, default_a, default_b, parent=None):
        super().__init__(parent)
        self.per_rec = per_rec
        self.setWindowTitle("Effect-size forest plot")
        self.resize(740, 620)
        lay = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        self.a = QtWidgets.QComboBox(); self.a.addItems(conditions)
        self.b = QtWidgets.QComboBox(); self.b.addItems(conditions)
        self.a.setCurrentText(default_a)
        self.b.setCurrentText(default_b if default_b in conditions else conditions[-1])
        self.topn = QtWidgets.QSpinBox(); self.topn.setRange(5, 80); self.topn.setValue(20)
        for w in (QtWidgets.QLabel("control"), self.a, QtWidgets.QLabel("vs test"),
                  self.b, QtWidgets.QLabel("top |d|"), self.topn):
            row.addWidget(w)
        row.addStretch(1)
        lay.addLayout(row)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=False, alpha=0.3)
        lay.addWidget(self.plot, 1)
        for c in (self.a, self.b):
            c.currentIndexChanged.connect(self._draw)
        self.topn.valueChanged.connect(self._draw)
        exp = QtWidgets.QPushButton("Export CSV…")
        exp.clicked.connect(self._export)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        foot = QtWidgets.QHBoxLayout()
        foot.addWidget(exp); foot.addStretch(1); foot.addWidget(bb)
        lay.addLayout(foot)
        self._rows = []
        self._draw()

    def _draw(self):
        self.plot.clear()
        a, b = self.a.currentText(), self.b.currentText()
        self._rows = compare.forest_data(self.per_rec, a, b)
        rows = self._rows[: self.topn.value()]
        if not rows:
            self.plot.setTitle("no comparable metrics for this pair")
            return
        ys = np.arange(len(rows))[::-1]                # largest |d| at the top
        d = np.array([r["d"] for r in rows], float)
        lo = np.array([r["lo"] for r in rows], float)
        hi = np.array([r["hi"] for r in rows], float)
        self.plot.addItem(pg.InfiniteLine(pos=0, angle=90,
                          pen=pg.mkPen("w", style=QtCore.Qt.DashLine)))
        self.plot.addItem(pg.ErrorBarItem(
            x=d, y=ys, left=np.nan_to_num(d - lo), right=np.nan_to_num(hi - d),
            beam=0.25, pen=pg.mkPen("w", width=1.5)))
        sig = [np.isfinite(r["p"]) and r["p"] < 0.05 for r in rows]
        brushes = [pg.mkBrush(214, 39, 40) if s else pg.mkBrush(140, 140, 140)
                   for s in sig]
        self.plot.addItem(pg.ScatterPlotItem(d, ys, size=11, brush=brushes,
                                             pen=pg.mkPen("k")))
        self.plot.getAxis("left").setTicks(
            [[(int(y), metric_docs.column_label(r["metric"]))
              for y, r in zip(ys, rows)]])
        self.plot.setLabel("bottom", f"Cohen's d  ({b} − {a})")
        self.plot.setTitle(f"{b} vs {a} — effect size ± 95% CI "
                           f"(red = Mann-Whitney p < 0.05)")

    def _export(self):
        if not self._rows:
            return
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export forest data",
            f"forest_{self.b.currentText()}_vs_{self.a.currentText()}.csv", "CSV (*.csv)")
        if not fn:
            return
        import csv
        with open(fn, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["metric", "cohen_d", "ci_lo", "ci_hi", "mwu_p"])
            for r in self._rows:
                w.writerow([r["metric"], r["d"], r["lo"], r["hi"], r["p"]])
