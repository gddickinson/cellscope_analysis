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

from ...analysis import edge_dynamics, edge_piezo
from ..plot_export import save_plot

_MODES = ["Velocity kymograph", "Radius kymograph", "Fluorescence kymograph",
          "Edge ↔ fluorescence", "Edge this frame: velocity",
          "Edge this frame: radius"]
_EDGE_FRAME = (4, 5)             # mode indices that draw the per-frame edge map
_NONE = "(none)"


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
        self._half = None               # max cell radius (px) → stable edge crop
        self._vfr = self._vel = self._rfr = self._rad = None
        self._rec = None                # Recording (for the fluorescence channel)
        self._chan_names = None
        self._pfr = self._piezo = None  # fluorescence kymograph + its summary
        self._psum = {}
        self._lut_div = _lut("RdBu_r")
        self._lut_seq = _lut("viridis")

        self.title = QtWidgets.QLabel("No cell selected")
        self.title.setStyleSheet("font-weight: bold;")
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(_MODES)
        self.mode.setToolTip("Kymograph (angle × time), the cell boundary this "
                             "frame, or edge-velocity ↔ cortical fluorescence")
        self.mode.currentIndexChanged.connect(self._replot)
        self.fluor = QtWidgets.QComboBox()
        self.fluor.addItem(_NONE)
        self.fluor.setToolTip("Fluorescence channel (e.g. tagged PIEZO1) to "
                              "correlate with edge protrusion/retraction")
        self.fluor.currentIndexChanged.connect(self._on_fluor)
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
        self.save_btn = QtWidgets.QPushButton("Save plot…")
        self.save_btn.clicked.connect(
            lambda: save_plot(self.plot, self, f"cell{self.cell_id}_edge.png"))

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("View"))
        row.addWidget(self.mode, 1)
        row.addWidget(QtWidgets.QLabel("Fluor"))
        row.addWidget(self.fluor, 1)
        lay.addLayout(row)
        lay.addWidget(self.plot, 1)
        lay.addWidget(self.summary)
        brow = QtWidgets.QHBoxLayout()
        brow.addWidget(self.export_btn)
        brow.addWidget(self.save_btn)
        lay.addLayout(brow)

    # -- public ----------------------------------------------------------
    def set_cell(self, cell_id, labels, um_per_px=None, dt_min=None, recording=None):
        if not cell_id:
            return self.clear_cell()
        self.cell_id = int(cell_id)
        self._dt = dt_min
        self._um = um_per_px
        self._labels = labels
        self._rec = recording
        self._populate_fluor(recording)
        self._vfr, self._vel = edge_dynamics.edge_velocity_kymograph(
            labels, self.cell_id, um_per_px, dt_min)
        self._rfr, self._rad = edge_dynamics.radius_kymograph(
            labels, self.cell_id, um_per_px)
        self._half = (float(np.nanmax(self._rad)) / (um_per_px or 1.0)
                      if self._rad.size and np.isfinite(self._rad).any() else None)
        self._compute_fluor()
        s = edge_dynamics.edge_summary(self._vel)
        ev = edge_dynamics.edge_events(self._vel, dt_min)
        vu = "µm/min" if (um_per_px and dt_min) else ("µm/frame" if um_per_px
                                                      else "px/step")
        tu = "min" if dt_min else "frames"
        self.title.setText(f"Cell {self.cell_id} — edge dynamics")
        txt = (
            f"protrusion: {s['mean_protrusion_velocity']:.3f} {vu}    "
            f"retraction: {s['mean_retraction_velocity']:.3f} {vu}<br>"
            f"net: {s['net_velocity']:.3f} {vu}    "
            f"protruding fraction: {s['protrusion_fraction']:.2f}<br>"
            f"ruffling (edge activity): {s['ruffling']:.3f} {vu}<br>"
            f"events: {ev['n_protrusions']} protr / {ev['n_retractions']} retr"
            f"  ·  mean dur {ev['mean_protrusion_duration']:.1f} / "
            f"{ev['mean_retraction_duration']:.1f} {tu}")
        self.summary.setText(txt + self._fluor_summary_html())
        self.export_btn.setEnabled(True)
        self._replot()

    def _fluor_summary_html(self):
        p = self._psum
        if not p or not np.isfinite(p.get("edge_piezo_pearson", np.nan)):
            return ""
        ch = self.fluor.currentText()
        return (f"<br><b>{ch}</b> ↔ edge: r = {p['edge_piezo_pearson']:+.2f} "
                f"(ρ = {p.get('edge_piezo_spearman', float('nan')):+.2f}) · "
                f"lag-1 r = {p.get('edge_piezo_lag1', float('nan')):+.2f} · "
                f"protrude−retract = {p.get('piezo_protr_minus_retr', float('nan')):+.1f}")

    def _populate_fluor(self, recording):
        names = list(getattr(recording, "channel_names", []) or [])
        if names == self._chan_names:
            return
        self._chan_names = names
        cur = self.fluor.currentText()
        self.fluor.blockSignals(True)
        self.fluor.clear()
        self.fluor.addItem(_NONE)
        self.fluor.addItems(names)
        self.fluor.setCurrentText(cur if cur in ([_NONE] + names) else _NONE)
        self.fluor.blockSignals(False)

    def _fluor_channel(self):
        name = self.fluor.currentText()
        if name == _NONE or self._rec is None or name not in self._chan_names:
            return None
        return self._chan_names.index(name)

    def _compute_fluor(self):
        self._pfr = self._piezo = None
        self._psum = {}
        ch = self._fluor_channel()
        if ch is None or self._labels is None or not self.cell_id:
            return
        image = self._rec.data[:, ch]                  # (T, H, W) for this channel
        self._pfr, self._piezo = edge_piezo.fluor_kymograph(
            self._labels, image, self.cell_id)
        self._psum = edge_piezo.edge_fluor_correlation(
            self._vfr, self._vel, self._pfr, self._piezo)

    def _on_fluor(self):
        if self.cell_id and self._labels is not None:
            self._compute_fluor()
            # refresh the summary's correlation line + the plot
            base = self.summary.text().split("<br><b>")[0]
            self.summary.setText(base + self._fluor_summary_html())
            self._replot()

    def set_frame(self, t):
        self._frame = t
        if self.mode.currentIndex() in _EDGE_FRAME:    # edge-this-frame view
            self._replot()

    def clear_cell(self):
        self.cell_id = 0
        self._vel = self._rad = self._labels = None
        self._pfr = self._piezo = None
        self._psum = {}
        self.title.setText("No cell selected")
        self.summary.setText("")
        self.img.clear()
        self.scatter.clear()
        self.export_btn.setEnabled(False)

    # -- internal --------------------------------------------------------
    def _replot(self):
        idx = self.mode.currentIndex()
        vb = self.plot.getViewBox()
        vb.setAspectLocked(idx in _EDGE_FRAME)
        vb.invertY(idx != 3)                           # scatter uses y-up axes
        if idx in _EDGE_FRAME:
            self.img.clear()
            self._draw_edge_frame(velocity=(idx == 4))
        elif idx == 3:
            self.img.clear()
            self._draw_fluor_scatter()
        elif idx == 2:
            self.scatter.clear()
            self._draw_fluor_kymograph()
        else:
            self.scatter.clear()
            self._draw_kymograph(velocity=(idx == 0))

    def _draw_fluor_kymograph(self):
        if self._piezo is None or self._piezo.size == 0:
            self.img.clear()
            self.plot.setTitle("select a fluorescence channel (Fluor)")
            return
        mat = self._piezo
        self.img.setImage(mat, autoLevels=False)
        lo, hi = float(np.nanmin(mat)), float(np.nanmax(mat))
        self.img.setLookupTable(self._lut_seq)
        self.img.setLevels((lo, hi if hi > lo else lo + 1))
        y0 = float(self._pfr[0]) * (self._dt or 1.0)
        y1 = float(self._pfr[-1]) * (self._dt or 1.0)
        self.img.setRect(QtCore.QRectF(0.0, y0, 360.0, (y1 - y0) or 1.0))
        self.plot.setTitle(f"{self.fluor.currentText()} cortical intensity")
        self.plot.setLabel("bottom", "angle (deg)")
        self.plot.setLabel("left", "time (min)" if self._dt else "frame")
        self.plot.autoRange()

    def _draw_fluor_scatter(self):
        self.scatter.clear()
        if self._piezo is None or self._piezo.size == 0:
            self.plot.setTitle("select a fluorescence channel (Fluor)")
            return
        v, p = edge_piezo.aligned_pairs(self._vfr, self._vel, self._pfr, self._piezo)
        if v.size == 0:
            self.plot.setTitle("no overlapping edge / fluorescence data")
            return
        brushes = [pg.mkBrush(214, 39, 40, 130) if vv > 0
                   else pg.mkBrush(31, 119, 180, 130) for vv in v]
        self.scatter.setData(x=v, y=p, size=4, pen=None, brush=brushes)
        r = self._psum.get("edge_piezo_pearson", float("nan"))
        vu = "µm/min" if (self._um and self._dt) else ("µm/frame" if self._um
                                                       else "px/step")
        self.plot.setTitle(f"edge velocity vs {self.fluor.currentText()}  "
                           f"(r = {r:+.2f}; red protrude · blue retract)")
        self.plot.setLabel("bottom", f"edge velocity ({vu})")
        self.plot.setLabel("left", "cortical intensity")
        self.plot.autoRange()

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
        self.plot.autoRange()

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
        if self._half:                                 # stable crop, cell centred
            h = self._half * 1.15
            self.plot.setXRange(cx - h, cx + h, padding=0)
            self.plot.setYRange(cy - h, cy + h, padding=0)

    def _export(self):
        idx = self.mode.currentIndex()
        if idx == 2:                                   # fluorescence kymograph
            mat, frames, tag = self._piezo, self._pfr, "fluor_cortical"
        elif idx in (1, 5):                            # boundary radius
            mat, frames, tag = self._rad, self._rfr, "boundary_radius"
        else:                                          # velocity (0, 4) or scatter (3)
            mat, frames, tag = self._vel, self._vfr, "edge_velocity"
        if mat is None or mat.size == 0:
            return
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
