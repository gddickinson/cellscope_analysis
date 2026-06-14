"""Edge-dynamics panel — the membrane protrusion/retraction kymograph.

For the selected cell, shows the radial edge-velocity kymograph (angle × time,
blue=retraction / red=protrusion) or the boundary-radius map, a protrusion/
retraction/ruffling summary, and a CSV export of the kymograph matrix. The
heavy lifting is in `analysis.edge_dynamics`; this panel only displays it.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import edge_dynamics


def _lut(name):
    import matplotlib
    ramp = matplotlib.colormaps[name](np.linspace(0, 1, 256))[:, :3]
    return (ramp * 255).astype(np.ubyte)


class EdgePanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell_id = 0
        self._dt = None
        self._vfr = self._vel = self._rfr = self._rad = None
        self._lut_div = _lut("RdBu_r")
        self._lut_seq = _lut("viridis")

        self.title = QtWidgets.QLabel("No cell selected")
        self.title.setStyleSheet("font-weight: bold;")
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["Edge velocity", "Boundary radius"])
        self.mode.currentIndexChanged.connect(self._replot)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("bottom", "angle (deg)")
        self.plot.setMenuEnabled(False)
        self.plot.getViewBox().invertY(True)
        self.img = pg.ImageItem()
        self.plot.addItem(self.img)
        self.summary = QtWidgets.QLabel("")
        self.summary.setWordWrap(True)
        self.export_btn = QtWidgets.QPushButton("Export kymograph CSV…")
        self.export_btn.clicked.connect(self._export)
        self.export_btn.setEnabled(False)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Map"))
        row.addWidget(self.mode, 1)
        lay.addLayout(row)
        lay.addWidget(self.plot, 1)
        lay.addWidget(self.summary)
        lay.addWidget(self.export_btn)

    # -- public ----------------------------------------------------------
    def set_cell(self, cell_id, labels, um_per_px=None, dt_min=None):
        if not cell_id:
            return self.clear_cell()
        self.cell_id = int(cell_id)
        self._dt = dt_min
        self._vfr, self._vel = edge_dynamics.edge_velocity_kymograph(
            labels, self.cell_id, um_per_px, dt_min)
        self._rfr, self._rad = edge_dynamics.radius_kymograph(
            labels, self.cell_id, um_per_px)
        s = edge_dynamics.edge_summary(self._vel)
        vu = "µm/min" if (um_per_px and dt_min) else ("µm/frame" if um_per_px
                                                      else "px/step")
        self.title.setText(f"Cell {self.cell_id} — edge dynamics")
        self.summary.setText(
            f"protrusion: {s['mean_protrusion_velocity']:.3f} {vu}    "
            f"retraction: {s['mean_retraction_velocity']:.3f} {vu}<br>"
            f"net: {s['net_velocity']:.3f} {vu}    "
            f"protruding fraction: {s['protrusion_fraction']:.2f}<br>"
            f"ruffling (edge activity): {s['ruffling']:.3f} {vu}")
        self.export_btn.setEnabled(True)
        self._replot()

    def clear_cell(self):
        self.cell_id = 0
        self._vel = self._rad = None
        self.title.setText("No cell selected")
        self.summary.setText("")
        self.img.clear()
        self.export_btn.setEnabled(False)

    # -- internal --------------------------------------------------------
    def _current(self):
        if self.mode.currentIndex() == 0:
            return self._vel, self._vfr, True
        return self._rad, self._rfr, False

    def _replot(self):
        mat, frames, velocity = self._current()
        if mat is None or mat.size == 0:
            self.img.clear()
            return
        self.img.setImage(mat, autoLevels=False)
        if velocity:
            vmax = float(np.nanmax(np.abs(mat))) or 1.0
            self.img.setLookupTable(self._lut_div)
            self.img.setLevels((-vmax, vmax))
            self.plot.setTitle("blue = retraction · red = protrusion")
        else:
            lo, hi = float(np.nanmin(mat)), float(np.nanmax(mat))
            self.img.setLookupTable(self._lut_seq)
            self.img.setLevels((lo, hi if hi > lo else lo + 1))
            self.plot.setTitle("boundary radius")
        y0 = float(frames[0]) * (self._dt or 1.0)
        y1 = float(frames[-1]) * (self._dt or 1.0)
        self.img.setRect(QtCore.QRectF(0.0, y0, 360.0, (y1 - y0) or 1.0))
        self.plot.setLabel("left", "time (min)" if self._dt else "frame")

    def _export(self):
        mat, frames, velocity = self._current()
        if mat is None or mat.size == 0:
            return
        tag = "edge_velocity" if velocity else "boundary_radius"
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export kymograph CSV", f"cell{self.cell_id}_{tag}.csv",
            "CSV (*.csv)")
        if not fn:
            return
        angles = (np.arange(edge_dynamics.N_SECTORS) + 0.5) * 360.0 \
            / edge_dynamics.N_SECTORS
        header = "frame," + ",".join(f"deg_{a:.0f}" for a in angles)
        np.savetxt(fn, np.column_stack([frames, mat]), delimiter=",",
                   header=header, comments="")
