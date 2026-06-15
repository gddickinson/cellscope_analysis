"""Edge-dynamics panel — protrusion/retraction kymographs, a per-frame edge map,
and the **edge-movement ↔ fluorescence** analysis (e.g. tagged PIEZO1).

For the selected cell:
  * **Velocity / Radius kymograph** — angle × time heatmaps
    (blue=retraction / red=protrusion; or boundary radius).
  * **Intensity kymograph** — per-sector mean fluorescence in a rectangle
    reaching into the cell from the edge (needs a Fluor channel).
  * **Edge movement ↔ intensity** — the headline scatter: local edge displacement
    vs the rectangle fluorescence, points coloured by movement class
    (blue=protruding / grey=stable / red=retracting), with the regression line and
    Pearson r / R² / p (faithful reproduction of the lab ``cell_edge_analysis``).
  * **Sampling rectangles** — the inward sampling rectangles on the current frame,
    centres coloured by intensity.
  * **Edge this frame** — the boundary coloured by per-sector velocity / radius.
Plus a protrusion/retraction summary and CSV export. The maths lives in
`analysis.edge_dynamics` + `analysis.edge_intensity`; this panel just displays it.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from scipy import ndimage
from PyQt5 import QtCore, QtWidgets

from ...analysis import edge_dynamics, edge_intensity
from ..plot_export import save_plot

_MODES = ["Velocity kymograph", "Radius kymograph", "Intensity kymograph",
          "Edge movement ↔ intensity", "Edge this frame: velocity",
          "Edge this frame: radius", "Sampling rectangles"]
_INTENSITY_KYMO = 2
_SCATTER = 3
_EDGE_FRAME = (4, 5, 6)          # mode indices drawn on the current frame
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
        self._ifr = self._int = None    # rectangle-intensity kymograph
        self._disp = self._inten = None  # (displacement, intensity) pairs
        self._summary = {}              # edge-movement ↔ intensity correlation
        self._lut_div = _lut("RdBu_r")
        self._lut_seq = _lut("viridis")

        self.title = QtWidgets.QLabel("No cell selected")
        self.title.setStyleSheet("font-weight: bold;")
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(_MODES)
        self.mode.setToolTip("Kymograph (angle × time), the cell boundary this "
                             "frame, or edge movement ↔ fluorescence intensity")
        self.mode.currentIndexChanged.connect(self._replot)
        self.fluor = QtWidgets.QComboBox()
        self.fluor.addItem(_NONE)
        self.fluor.setToolTip("Fluorescence channel to correlate with edge "
                              "protrusion/retraction — tagged PIEZO1, SiR-actin "
                              "(cortical actin), or any fluorescent signal")
        self.fluor.currentIndexChanged.connect(self._on_fluor)
        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.getViewBox().invertY(True)
        self.img = pg.ImageItem()
        self.line = pg.PlotCurveItem()           # regression line / rectangle edges
        self.scatter = pg.ScatterPlotItem(pxMode=True)
        self.plot.addItem(self.img)
        self.plot.addItem(self.line)
        self.plot.addItem(self.scatter)
        self.summary = QtWidgets.QLabel("")
        self.summary.setWordWrap(True)
        self.export_btn = QtWidgets.QPushButton("Export CSV…")
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
        vu = self._vel_units()
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

    def _vel_units(self):
        return "µm/min" if (self._um and self._dt) else (
            "µm/frame" if self._um else "px/step")

    def _fluor_summary_html(self):
        p = self._summary
        if not p or not np.isfinite(p.get("edge_move_intensity_r", np.nan)):
            return ""
        ch = self.fluor.currentText()
        line = (f"<br><b>{ch}</b> ↔ edge movement: r = "
                f"{p['edge_move_intensity_r']:+.2f} "
                f"(R² = {p.get('edge_move_intensity_r2', float('nan')):.2f}, "
                f"p = {p.get('edge_move_intensity_p', float('nan')):.1e}, "
                f"n = {p.get('n_edge_intensity', 0)})")
        if np.isfinite(p.get("piezo_protr_minus_retr", np.nan)):
            line += (f"<br>protruding {p['piezo_at_protrusion']:.0f} "
                     f"(n={p['n_protruding']}) vs retracting "
                     f"{p['piezo_at_retraction']:.0f} (n={p['n_retracting']}) · "
                     f"Δ = {p['piezo_protr_minus_retr']:+.1f} · MWU p = "
                     f"{p.get('protr_retr_mwu_p', float('nan')):.1e}")
        return line

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
        if name == _NONE or self._rec is None or name not in (self._chan_names or []):
            return None
        return self._chan_names.index(name)

    def _channel_stack(self):
        ch = self._fluor_channel()
        return None if ch is None else self._rec.data[:, ch]

    def _compute_fluor(self):
        self._ifr = self._int = self._disp = self._inten = None
        self._summary = {}
        image = self._channel_stack()
        if image is None or self._labels is None or not self.cell_id:
            return
        (_, _, self._ifr, self._int, self._disp, self._inten,
         self._summary) = edge_intensity.analyze_cell(
            self._labels, image, self.cell_id, self._um, self._dt)

    def _on_fluor(self):
        if self.cell_id and self._labels is not None:
            self._compute_fluor()
            base = self.summary.text().split("<br><b>")[0]
            self.summary.setText(base + self._fluor_summary_html())
            self._replot()

    def set_frame(self, t):
        self._frame = t
        if self.mode.currentIndex() in _EDGE_FRAME:    # per-frame views
            self._replot()

    def clear_cell(self):
        self.cell_id = 0
        self._vel = self._rad = self._labels = None
        self._ifr = self._int = self._disp = self._inten = None
        self._summary = {}
        self.title.setText("No cell selected")
        self.summary.setText("")
        self.img.clear()
        self.line.clear()
        self.scatter.clear()
        self.export_btn.setEnabled(False)

    # -- internal --------------------------------------------------------
    def _replot(self):
        idx = self.mode.currentIndex()
        vb = self.plot.getViewBox()
        vb.setAspectLocked(idx in _EDGE_FRAME)
        vb.invertY(idx != _SCATTER)                    # scatter uses y-up axes
        self.img.clear()
        self.line.clear()
        self.scatter.clear()
        if idx == 6:
            self._draw_rectangles()
        elif idx in _EDGE_FRAME:
            self._draw_edge_frame(velocity=(idx == 4))
        elif idx == _SCATTER:
            self._draw_move_intensity_scatter()
        elif idx == _INTENSITY_KYMO:
            self._draw_intensity_kymograph()
        else:
            self._draw_kymograph(velocity=(idx == 0))

    def _need_fluor(self):
        if self._int is None or self._int.size == 0:
            self.plot.setTitle("select a fluorescence channel (Fluor)")
            return True
        return False

    def _draw_intensity_kymograph(self):
        if self._need_fluor():
            return
        mat = self._int
        self.img.setImage(mat, autoLevels=False)
        lo, hi = float(np.nanmin(mat)), float(np.nanmax(mat))
        self.img.setLookupTable(self._lut_seq)
        self.img.setLevels((lo, hi if hi > lo else lo + 1))
        y0 = float(self._ifr[0]) * (self._dt or 1.0)
        y1 = float(self._ifr[-1]) * (self._dt or 1.0)
        self.img.setRect(QtCore.QRectF(0.0, y0, 360.0, (y1 - y0) or 1.0))
        self.plot.setTitle(f"{self.fluor.currentText()} intensity (edge rectangles)")
        self.plot.setLabel("bottom", "angle (deg)")
        self.plot.setLabel("left", "time (min)" if self._dt else "frame")
        self.plot.autoRange()

    def _draw_move_intensity_scatter(self):
        if self._disp is None or self._disp.size == 0:
            self.plot.setTitle("select a fluorescence channel (Fluor)")
            return
        d, it, p = self._disp, self._inten, self._summary
        thr = p.get("_threshold", 0.0)
        brushes = [pg.mkBrush(214, 39, 40, 110) if v > thr else
                   (pg.mkBrush(31, 119, 180, 110) if v < -thr else
                    pg.mkBrush(140, 140, 140, 90)) for v in d]
        self.scatter.setData(x=d, y=it, size=5, pen=None, brush=brushes)
        slope = p.get("edge_move_intensity_slope", float("nan"))
        if np.isfinite(slope):
            xs = np.array([float(d.min()), float(d.max())])
            self.line.setData(x=xs, y=slope * xs + p.get("_intercept", 0.0),
                              pen=pg.mkPen("k", width=2, style=QtCore.Qt.DashLine))
        r = p.get("edge_move_intensity_r", float("nan"))
        r2 = p.get("edge_move_intensity_r2", float("nan"))
        self.plot.setTitle(f"edge movement vs {self.fluor.currentText()}  "
                           f"(r = {r:+.2f}, R² = {r2:.2f}; blue protrude · red retract)")
        self.plot.setLabel("bottom", f"edge displacement ({self._vel_units()})")
        self.plot.setLabel("left", "fluorescence intensity")
        self.plot.autoRange()

    def _draw_kymograph(self, velocity):
        mat = self._vel if velocity else self._rad
        frames = self._vfr if velocity else self._rfr
        if mat is None or mat.size == 0:
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

    def _crop_to_cell(self, cy, cx, pad=1.15):
        if self._half:
            h = self._half * pad
            self.plot.setXRange(cx - h, cx + h, padding=0)
            self.plot.setYRange(cy - h, cy + h, padding=0)

    def _draw_edge_frame(self, velocity):
        t = self._frame
        if self._labels is None or t is None:
            return
        m = self._labels[t] == self.cell_id
        if not m.any():
            return
        ry, rx = np.nonzero(m)
        cy, cx = ry.mean(), rx.mean()
        by, bx = np.nonzero(m & ~ndimage.binary_erosion(m))
        if velocity:
            hit = np.where(self._vfr == t)[0]
            if hit.size == 0:
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
        self._crop_to_cell(cy, cx)

    def _draw_rectangles(self):
        t = self._frame
        image = self._channel_stack()
        if image is None or self._labels is None or t is None:
            self.plot.setTitle("select a fluorescence channel (Fluor)")
            return
        corners, inten = edge_intensity.rectangles_for_frame(
            self._labels, image, self.cell_id, t)
        if corners.shape[0] == 0:
            self.plot.setTitle("no sampling rectangles this frame")
            return
        xs, ys = [], []
        for c in corners:                              # outline each rectangle
            xs += [c[0, 1], c[1, 1], c[2, 1], c[3, 1], c[0, 1], np.nan]
            ys += [c[0, 0], c[1, 0], c[2, 0], c[3, 0], c[0, 0], np.nan]
        self.line.setData(x=np.array(xs), y=np.array(ys),
                          pen=pg.mkPen(255, 255, 255, 110), connect="finite")
        centers = corners.mean(axis=1)                 # (m, 2) row, col
        lo, hi = float(inten.min()), float(inten.max())
        ci = np.clip((inten - lo) / ((hi - lo) or 1.0) * 255, 0, 255).astype(int)
        lut = self._lut_seq
        brushes = [pg.mkBrush(int(lut[i, 0]), int(lut[i, 1]), int(lut[i, 2]))
                   for i in ci]
        self.scatter.setData(x=centers[:, 1], y=centers[:, 0], brush=brushes,
                             size=8, pen=None)
        self.plot.setTitle(f"{self.fluor.currentText()} sampling rectangles "
                           "(centres coloured by intensity)")
        self.plot.setLabel("bottom", "x (px)")
        self.plot.setLabel("left", "y (px)")
        m = self._labels[t] == self.cell_id
        ry, rx = np.nonzero(m)
        self._crop_to_cell(ry.mean(), rx.mean(), pad=1.3)

    def _export(self):
        idx = self.mode.currentIndex()
        if idx == _SCATTER:                            # (displacement, intensity) pairs
            if self._disp is None or self._disp.size == 0:
                return
            fn, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export pairs CSV",
                f"cell{self.cell_id}_edge_move_intensity.csv", "CSV (*.csv)")
            if fn:
                np.savetxt(fn, np.column_stack([self._disp, self._inten]),
                           delimiter=",", header="edge_displacement,intensity",
                           comments="")
            return
        if idx in (_INTENSITY_KYMO, 6):
            mat, frames, tag = self._int, self._ifr, "fluor_intensity"
        elif idx in (1, 5):
            mat, frames, tag = self._rad, self._rfr, "boundary_radius"
        else:
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
