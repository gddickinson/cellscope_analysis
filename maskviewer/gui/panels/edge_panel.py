"""Edge-dynamics panel — protrusion/retraction kymographs + a per-frame edge map.

For the selected cell:
  * **Velocity / Radius kymograph** — angle × time heatmaps
    (blue=retraction / red=protrusion; or boundary radius).
  * **Edge this frame** — the cell's boundary drawn in the current frame, each
    boundary point coloured by the per-sector edge velocity (RdBu) or its radius
    (viridis) — a spatial view of where the membrane is advancing/retracting now.
Plus a protrusion/retraction/ruffling summary and CSV export of the kymograph.
The heavy lifting is in `analysis.edge_dynamics`; this panel just displays it.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from scipy import ndimage
from PyQt5 import QtCore, QtWidgets

from ...analysis import edge_dynamics

_MODES = ["Velocity kymograph", "Radius kymograph",
          "Edge this frame: velocity", "Edge this frame: radius"]


def _lut(name):
    import matplotlib
    return (matplotlib.colormaps[name](np.linspace(0, 1, 256))[:, :3] * 255
            ).astype(np.ubyte)


class EdgePanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell_id = 0
        self._dt = None
        self._um = None
        self._labels = None
        self._frame = None
        self._vfr = self._vel = self._rfr = self._rad = None
        self._lut_div = _lut("RdBu_r")
        self._lut_seq = _lut("viridis")

        self.title = QtWidgets.QLabel("No cell selected")
        self.title.setStyleSheet("font-weight: bold;")
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(_MODES)
        self.mode.currentIndexChanged.connect(self._replot)
        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.getViewBox().invertY(True)
        self.img = pg.ImageItem()
        self.scatter = pg.ScatterPlotItem(pxMode=True)
        self.plot.addItem(self.img)
        self.plot.addItem(self.scatter)
        self.summary = QtWidgets.QLabel("")
        self.summary.setWordWrap(True)
        self.export_btn = QtWidgets.QPushButton("Export kymograph CSV…")
        self.export_btn.clicked.connect(self._export)
        self.export_btn.setEnabled(False)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("View"))
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
        self._um = um_per_px
        self._labels = labels
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

    def set_frame(self, t):
        self._frame = t
        if self.mode.currentIndex() >= 2:              # edge-this-frame view
            self._replot()

    def clear_cell(self):
        self.cell_id = 0
        self._vel = self._rad = self._labels = None
        self.title.setText("No cell selected")
        self.summary.setText("")
        self.img.clear()
        self.scatter.clear()
        self.export_btn.setEnabled(False)

    # -- internal --------------------------------------------------------
    def _replot(self):
        idx = self.mode.currentIndex()
        self.plot.getViewBox().setAspectLocked(idx >= 2)
        if idx >= 2:
            self.img.clear()
            self._draw_edge_frame(velocity=(idx == 2))
        else:
            self.scatter.clear()
            self._draw_kymograph(velocity=(idx == 0))

    def _draw_kymograph(self, velocity):
        mat = self._vel if velocity else self._rad
        frames = self._vfr if velocity else self._rfr
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
        self.plot.setLabel("bottom", "angle (deg)")
        self.plot.setLabel("left", "time (min)" if self._dt else "frame")

    def _draw_edge_frame(self, velocity):
        t = self._frame
        if self._labels is None or t is None:
            self.scatter.clear()
            return
        m = self._labels[t] == self.cell_id
        if not m.any():
            self.scatter.clear()
            return
        ry, rx = np.nonzero(m)
        cy, cx = ry.mean(), rx.mean()
        by, bx = np.nonzero(m & ~ndimage.binary_erosion(m))
        if velocity:
            hit = np.where(self._vfr == t)[0]
            if hit.size == 0:
                self.scatter.clear()
                self.plot.setTitle("no edge velocity for the first tracked frame")
                return
            row = self._vel[hit[0]]
            sect = ((np.arctan2(by - cy, bx - cx) + np.pi) / (2 * np.pi)
                    * row.size).astype(int) % row.size
            val = row[sect]
            vmax = float(np.nanmax(np.abs(self._vel))) or 1.0
            lut, lo, hi = self._lut_div, -vmax, vmax
            self.plot.setTitle("edge velocity (blue retract · red protrude)")
        else:
            val = np.sqrt((by - cy) ** 2 + (bx - cx) ** 2) * (self._um or 1.0)
            lut, lo, hi = self._lut_seq, float(np.nanmin(val)), float(np.nanmax(val))
            self.plot.setTitle("boundary radius")
        rng = (hi - lo) or 1.0
        ci = np.clip((np.nan_to_num(val, nan=lo) - lo) / rng * 255, 0, 255).astype(int)
        brushes = [pg.mkBrush(int(lut[i, 0]), int(lut[i, 1]), int(lut[i, 2]))
                   for i in ci]
        self.scatter.setData(x=bx, y=by, brush=brushes, size=5, pen=None)
        self.plot.setLabel("bottom", "x (px)")
        self.plot.setLabel("left", "y (px)")

    def _export(self):
        velocity = self.mode.currentIndex() in (0, 2)
        mat = self._vel if velocity else self._rad
        frames = self._vfr if velocity else self._rfr
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
