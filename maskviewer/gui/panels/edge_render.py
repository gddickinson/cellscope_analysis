"""Rendering for the Edge-dynamics panel — the view layer split out of
`edge_panel.py` (kept < 500 lines). `EdgeRenderMixin` draws the kymographs,
per-frame edge maps, the edge-movement↔intensity scatter, sampling rectangles,
and CSV export from the panel's already-computed per-cell state (`self._vel`,
`self._int`, …). Mixed into `EdgePanel`; all state lives on the panel.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from scipy import ndimage
from PyQt5 import QtCore, QtWidgets

from ...analysis import edge_dynamics, edge_intensity

_MODES = ["Velocity kymograph", "Radius kymograph", "Intensity kymograph",
          "Edge movement ↔ intensity", "Edge this frame: velocity",
          "Edge this frame: radius", "Edge this frame: intensity",
          "Sampling rectangles", "Curvature kymograph",
          "Edge this frame: curvature"]
_INTENSITY_KYMO = 2
_SCATTER = 3
_RECTANGLES = 7
_CURV_KYMO = 8
_EDGE_FRAME = (4, 5, 6, 7, 9)    # mode indices drawn on the current frame
_FRAME_METRIC = {4: "velocity", 5: "radius", 6: "intensity", 9: "curvature"}


class EdgeRenderMixin:
    """Drawing helpers for `EdgePanel` (view only; reads computed panel state)."""

    # -- internal --------------------------------------------------------
    def _replot(self):
        idx = self.mode.currentIndex()
        vb = self.plot.getViewBox()
        vb.setAspectLocked(idx in _EDGE_FRAME)
        vb.invertY(idx != _SCATTER)                    # scatter uses y-up axes
        self.img.clear()
        self.line.clear()
        self.scatter.clear()
        if idx == _RECTANGLES:
            self._draw_rectangles()
        elif idx in _EDGE_FRAME:
            self._draw_edge_frame(_FRAME_METRIC[idx])
        elif idx == _SCATTER:
            self._draw_move_intensity_scatter()
        elif idx == _INTENSITY_KYMO:
            self._draw_intensity_kymograph()
        elif idx == _CURV_KYMO:
            self._draw_kymograph("curvature")
        else:
            self._draw_kymograph("velocity" if idx == 0 else "radius")

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

    def _draw_kymograph(self, kind):
        mat = {"velocity": self._vel, "radius": self._rad,
               "curvature": self._curv}[kind]
        frames = {"velocity": self._vfr, "radius": self._rfr,
                  "curvature": self._cfr}[kind]
        if mat is None or mat.size == 0:
            return
        self.img.setImage(mat, autoLevels=False)
        if kind in ("velocity", "curvature"):
            vmax = float(np.nanmax(np.abs(mat))) or 1.0
            self.img.setLookupTable(self._lut_div)
            self.img.setLevels((-vmax, vmax))
            self.plot.setTitle("blue = retraction · red = protrusion" if kind == "velocity"
                               else f"curvature ({'1/µm' if self._um else '1/px'}); "
                                    "red convex · blue concave")
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

    def _draw_edge_frame(self, metric):
        """Colour the cell's boundary this frame by a per-sector metric:
        ``velocity`` (RdBu), ``radius`` or ``intensity`` (viridis)."""
        t = self._frame
        if self._labels is None or t is None:
            return
        m = self._labels[t] == self.cell_id
        if not m.any():
            return
        ry, rx = np.nonzero(m)
        cy, cx = ry.mean(), rx.mean()
        by, bx = np.nonzero(m & ~ndimage.binary_erosion(m))
        n = edge_dynamics.N_SECTORS
        sect = ((np.arctan2(by - cy, bx - cx) + np.pi) / (2 * np.pi) * n).astype(int) % n
        if metric == "velocity":
            hit = np.where(self._vfr == t)[0]
            if hit.size == 0:
                self.scatter.clear()
                self.plot.setTitle("no edge velocity for the first tracked frame")
                return
            # the velocity kymograph bins about the mid-centroid of the (prev, t) pair,
            # so map this frame's boundary to sectors about that same centroid
            present = [f for f in range(self._labels.shape[0])
                       if (self._labels[f] == self.cell_id).any()]
            a = present[present.index(t) - 1] if present.index(t) > 0 else t
            pa, pb = np.nonzero(self._labels[a] == self.cell_id), (ry, rx)
            mcy = (pa[0].mean() + pb[0].mean()) / 2.0
            mcx = (pa[1].mean() + pb[1].mean()) / 2.0
            vsect = ((np.arctan2(by - mcy, bx - mcx) + np.pi) / (2 * np.pi) * n).astype(int) % n
            val = self._vel[hit[0]][vsect]
            vmax = float(np.nanmax(np.abs(self._vel))) or 1.0
            lut, lo, hi = self._lut_div, -vmax, vmax
            self.plot.setTitle("edge velocity (blue retract · red protrude)")
        elif metric == "intensity":
            hit = np.array([]) if self._int is None or self._ifr is None \
                else np.where(self._ifr == t)[0]
            if self._need_fluor() or hit.size == 0:
                self.scatter.clear()
                if self._int is not None and self._int.size:
                    self.plot.setTitle("no intensity for this frame")
                return
            val = self._int[hit[0]][sect]
            lut = self._lut_seq
            lo, hi = float(np.nanmin(self._int)), float(np.nanmax(self._int))
            self.plot.setTitle(f"{self.fluor.currentText()} intensity (this frame)")
        elif metric == "curvature":
            hit = np.where(self._cfr == t)[0] if self._cfr is not None else np.array([])
            if hit.size == 0:
                self.scatter.clear()
                self.plot.setTitle("no curvature for this frame")
                return
            val = self._curv[hit[0]][sect]            # binned about this frame's centroid
            vmax = float(np.nanmax(np.abs(self._curv))) or 1.0
            lut, lo, hi = self._lut_div, -vmax, vmax
            self.plot.setTitle(f"edge curvature ({'1/µm' if self._um else '1/px'}; "
                               "red convex · blue concave)")
        else:                                          # radius (per-point distance)
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
        if idx in (_INTENSITY_KYMO, 6, _RECTANGLES):   # intensity kymo / edge-int / rects
            mat, frames, tag = self._int, self._ifr, "fluor_intensity"
        elif idx in (_CURV_KYMO, 9):                   # curvature kymo / edge-curvature
            mat, frames, tag = self._curv, self._cfr, "boundary_curvature"
        elif idx in (1, 5):                            # radius kymo / edge-radius
            mat, frames, tag = self._rad, self._rfr, "boundary_radius"
        else:                                          # velocity kymo / edge-velocity
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
