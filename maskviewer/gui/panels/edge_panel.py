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
`analysis.edge_dynamics` + `analysis.edge_intensity`; the rendering lives in
`edge_render.EdgeRenderMixin`; this module owns state + the per-cell compute.

The per-cell compute is **lazy**: `set_cell` stores the request and defers the
multi-second kymograph/fluorescence work until this dock is actually the visible
tab (tracked via show/hide events), so clicking cells while on another tab (e.g.
Cell Info) stays instant. `showEvent` computes the pending cell.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets

from ...analysis import edge_dynamics, edge_intensity
from ..plot_export import save_plot
from .edge_render import EdgeRenderMixin, _MODES, _EDGE_FRAME

_NONE = "(none)"
# brightfield / transmitted / placeholder channel names (NOT fluorescence)
_NON_FLUOR = ("dic", "bright", "bf", "phase", "trans", "label", "none", "empty")


def _is_fluor_name(name) -> bool:
    """Heuristic: a real fluorescence channel (e.g. ``Cy5``) — not a brightfield /
    transmitted-light / empty placeholder channel."""
    low = (name or "").strip().lower()
    return bool(low) and not any(k in low for k in _NON_FLUOR)


def _lut(name):
    import matplotlib
    return (matplotlib.colormaps[name](np.linspace(0, 1, 256))[:, :3] * 255
            ).astype(np.ubyte)


class EdgePanel(EdgeRenderMixin, QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell_id = 0
        self._dt = None
        self._um = None
        self._labels = None
        self._frame = None
        self._pending = None            # deferred (cell, …) compute while this dock is hidden
        self._visible = False           # tracked via show/hide events (tabbed docks)
        self._half = None               # max cell radius (px) → stable edge crop
        self._vfr = self._vel = self._rfr = self._rad = None
        self._cfr = self._curv = None   # curvature kymograph (frames, per-sector)
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
        self._populate_fluor(recording)              # cheap (just the channel picker)
        # The heavy kymograph + fluorescence compute is **deferred until this dock
        # is actually visible** — the right-hand docks are tabbed, so when the user
        # is on another tab (e.g. Cell Info) clicking cells must not pay for edge
        # dynamics they aren't looking at. Showing the tab computes the pending cell.
        self._pending = self.cell_id
        if self._visible:
            self._ensure_computed()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._visible = True                         # became the front tab → compute
        self._ensure_computed()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._visible = False                        # tabbed behind / closed → defer

    def _ensure_computed(self):
        """Run the deferred per-cell compute if one is pending (i.e. the panel just
        became visible, or the cell changed while it was already visible)."""
        if self._pending is None or self._labels is None:
            return
        self._pending = None
        self._compute_cell()

    def _compute_cell(self):
        labels, um_per_px, dt_min = self._labels, self._um, self._dt
        self._vfr, self._vel = edge_dynamics.edge_velocity_kymograph(
            labels, self.cell_id, um_per_px, dt_min)
        self._rfr, self._rad = edge_dynamics.radius_kymograph(
            labels, self.cell_id, um_per_px)
        self._cfr, self._curv = edge_dynamics.curvature_kymograph(
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
        if self._curv is not None and np.isfinite(self._curv).any():
            cu = "1/µm" if self._um else "1/px"
            txt += (f"<br>mean curvature: {np.nanmean(self._curv):.3f} {cu}  ·  "
                    f"|κ| (edge roughness): {np.nanmean(np.abs(self._curv)):.3f} {cu}")
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
        first_time = self._chan_names is None          # never populated with real channels
        self._chan_names = names
        cur = self.fluor.currentText()
        self.fluor.blockSignals(True)
        self.fluor.clear()
        self.fluor.addItem(_NONE)
        self.fluor.addItems(names)
        # keep a still-valid *user* choice; otherwise (incl. the initial "(none)"
        # default) auto-select the first fluorescence channel so the rectangles +
        # edge-intensity views work without the user having to pick a channel
        pick = (cur if not first_time and cur in ([_NONE] + names)
                else next((n for n in names if _is_fluor_name(n)), _NONE))
        self.fluor.setCurrentText(pick)
        self.fluor.blockSignals(False)

    def _fluor_channel(self):
        name = self.fluor.currentText()
        if name == _NONE or self._rec is None or name not in (self._chan_names or []):
            return None
        return self._chan_names.index(name)

    def _channel_stack(self):
        ch = self._fluor_channel()
        return None if ch is None else self._rec.aligned_channel(ch)

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
        if not self.cell_id or self._labels is None:
            return
        if not self._visible:                  # defer; recomputed (incl. fluor) when shown
            self._pending = self.cell_id
            return
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
        self._pending = None
        self._vel = self._rad = self._labels = None
        self._cfr = self._curv = None
        self._ifr = self._int = self._disp = self._inten = None
        self._summary = {}
        self.title.setText("No cell selected")
        self.summary.setText("")
        self.img.clear()
        self.line.clear()
        self.scatter.clear()
        self.export_btn.setEnabled(False)

