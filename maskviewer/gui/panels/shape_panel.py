"""Shape-modes panel — VAMPIRE-style population shape clustering.

Computes (lazily) the recording's shape modes and shows the mode mean-shapes
(eigenshape-like contours), the mode-fraction distribution and a heterogeneity
(Shannon entropy) score. The per-frame ``shape_mode`` is also plottable per cell
via the Cell-Info panel. Fitting can take a few seconds, so it's behind a button.
"""
from __future__ import annotations

import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import shape_modes

PALETTE = [(31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
           (148, 103, 189), (140, 86, 75), (227, 119, 194)]


class ShapeModesPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.provider = None                   # callable -> model dict | None

        self.title = QtWidgets.QLabel("Shape modes (VAMPIRE-style)")
        self.title.setStyleSheet("font-weight: bold;")
        self.info = QtWidgets.QLabel(
            "Cluster recurrent cell shapes across the recording, then plot each "
            "cell's shape mode over time (Cell Info ▸ shape_mode). Click Compute.")
        self.info.setWordWrap(True)
        self.compute_btn = QtWidgets.QPushButton("Compute shape modes")
        self.compute_btn.clicked.connect(self._compute)

        self.shapes = pg.PlotWidget()
        self.shapes.setAspectLocked(True)
        self.shapes.setMenuEnabled(False)
        self.shapes.hideAxis("left")
        self.shapes.hideAxis("bottom")
        self.shapes.setTitle("mode mean shapes")
        self.bars = pg.PlotWidget()
        self.bars.setMaximumHeight(160)
        self.bars.setMenuEnabled(False)
        self.bars.setTitle("mode fractions")
        self.bars.setLabel("left", "fraction")
        self.bars.setLabel("bottom", "shape mode")

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.info)
        lay.addWidget(self.compute_btn)
        lay.addWidget(self.shapes, 1)
        lay.addWidget(self.bars)

    def set_provider(self, fn):
        self.provider = fn

    def clear_model(self):
        self.shapes.clear()
        self.bars.clear()
        self.info.setText(
            "Cluster recurrent cell shapes across the recording, then plot each "
            "cell's shape mode over time (Cell Info ▸ shape_mode). Click Compute.")

    def _compute(self):
        if not self.provider:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            model = self.provider()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if not model:
            self.info.setText("Not enough cells/frames for shape modes "
                              "(need ≥5 valid contours).")
            return
        self.show_model(model)

    def show_model(self, model):
        self.shapes.clear()
        for k in range(model["n_modes"]):
            x, y = shape_modes.mode_contour(model["mode_signatures"][k])
            col = PALETTE[k % len(PALETTE)]
            self.shapes.plot(x + k * 3.0, y, pen=pg.mkPen(col, width=2))
            lbl = pg.TextItem(f"{k} ({model['mode_fractions'][k] * 100:.0f}%)",
                              color=col, anchor=(0.5, 0))
            lbl.setPos(k * 3.0, -1.7)
            self.shapes.addItem(lbl)
        self.bars.clear()
        n = model["n_modes"]
        self.bars.addItem(pg.BarGraphItem(
            x=list(range(n)), height=list(model["mode_fractions"]), width=0.6,
            brushes=[PALETTE[k % len(PALETTE)] for k in range(n)]))
        self.info.setText(
            f"{model['n_samples']} cell-frames · {n} modes · "
            f"heterogeneity {model['entropy']:.2f} bits · "
            f"PCA variance {model['explained_variance'] * 100:.0f}%")
