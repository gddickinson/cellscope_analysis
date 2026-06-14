"""Cell-info panel — inspect the cell clicked in the view.

Shows a summary of the selected cell's track (length, motion, state fractions)
and a time-series plot of any per-frame characteristic — area, eccentricity,
aspect ratio, solidity, axes, orientation, extent, speed, displacement, turning
angle, per-frame state, and mean intensity of each channel (e.g. SiR-actin Cy5)
— plus an MSD (log-log) view with the diffusion-exponent fit. Computation uses
the GUI-free `analysis` helpers; this panel only formats + plots.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets

from ...analysis import cell_metrics, motion, state

_MSD = "MSD (log-log)"


class CellInfoPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell_id = 0
        self._cft = {}
        self._dt = None

        self.title = QtWidgets.QLabel("No cell selected")
        self.title.setStyleSheet("font-weight: bold;")
        self.info = QtWidgets.QLabel("Click a cell in the view to inspect it.")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(self.info.textInteractionFlags() | 0x1)
        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(220)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.curve = self.plot.plot([], [], pen=pg.mkPen((0, 160, 255), width=2),
                                    symbol="o", symbolSize=4,
                                    symbolBrush=(0, 160, 255))
        self.fit = self.plot.plot([], [], pen=pg.mkPen((230, 90, 60), width=2,
                                                       style=2))   # dashed
        self.marker = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen((255, 200, 0), width=1))
        self.plot.addItem(self.marker)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.info)
        mrow = QtWidgets.QHBoxLayout()
        mrow.addWidget(QtWidgets.QLabel("Plot"))
        mrow.addWidget(self.metric, 1)
        lay.addLayout(mrow)
        lay.addWidget(self.plot)

    # -- public ----------------------------------------------------------
    def set_cell(self, cell_id, labels, um_per_px=None, dt_min=None, recording=None):
        if not cell_id:
            return self.clear_cell()
        self.cell_id = int(cell_id)
        self._dt = dt_min
        self._cft = cell_metrics.cell_frame_table(
            labels, self.cell_id, um_per_px, dt_min, recording=recording)
        s = self._cft.get("series", {})
        m = self._cft.get("summary", {})
        u = "µm" if self._cft.get("scaled") else "px"

        # state fractions (rounded/spread over classifiable frames)
        codes = s.get("state_code", (np.array([]),))[0]
        cls = codes[(codes == state.STATE_CODE["rounded"]) |
                    (codes == state.STATE_CODE["spread"])]
        frac_round = float((codes == state.STATE_CODE["rounded"]).sum() / cls.size) \
            if cls.size else float("nan")

        self.metric.blockSignals(True)
        self.metric.clear()
        self.metric.addItems(sorted(s) + [_MSD])
        self.metric.setCurrentText("area" if "area" in s else (sorted(s)[0] if s else _MSD))
        self.metric.blockSignals(False)

        self.title.setText(f"Cell {self.cell_id}")
        fr = self._cft.get("frame", np.array([]))
        self.info.setText(
            f"frames tracked: {fr.size}"
            f" ({int(fr[0]) if fr.size else '-'}→{int(fr[-1]) if fr.size else '-'})<br>"
            f"net disp: {m.get('net_disp', float('nan')):.1f} {u}"
            f"   path: {m.get('total_path', float('nan')):.1f} {u}<br>"
            f"straightness: {m.get('straightness', float('nan')):.3f}"
            f"   persistence: {m.get('dir_autocorr_lag1', float('nan')):.3f}<br>"
            f"mean speed: {m.get('mean_speed', float('nan')):.3f} "
            f"{u}/{'min' if dt_min else 'frame'}<br>"
            f"rounded fraction: {frac_round:.2f}")
        self._replot()

    def set_frame_marker(self, t):
        self.marker.setValue(t * self._dt if self._dt else t)

    def clear_cell(self):
        self.cell_id = 0
        self._cft = {}
        self.title.setText("No cell selected")
        self.info.setText("Click a cell in the view to inspect it.")
        self.curve.setData([], [])
        self.fit.setData([], [])

    # -- internal --------------------------------------------------------
    def _replot(self):
        key = self.metric.currentText()
        self.fit.setData([], [])
        if key == _MSD:
            self._plot_msd()
            return
        self.plot.setLogMode(x=False, y=False)
        self.marker.show()
        series = self._cft.get("series", {})
        if key not in series:
            self.curve.setData([], [])
            return
        vals, ylabel = series[key]
        self.curve.setData(self._cft["frame"] * (self._dt or 1.0), np.asarray(vals))
        self.plot.setLabel("left", ylabel)
        self.plot.setLabel("bottom", "time (min)" if self._dt else "frame")

    def _plot_msd(self):
        cen = self._cft.get("centroid_um")
        if cen is None:
            self.curve.setData([], [])
            return
        tau, vals = motion.msd(cen, self._dt)
        self.marker.hide()
        self.plot.setLogMode(x=True, y=True)
        self.curve.setData(np.asarray(tau), np.asarray(vals))
        fit = motion.fit_msd(tau, vals)
        if np.isfinite(fit["alpha"]) and len(tau):
            model = 4 * fit["D"] * np.asarray(tau) ** fit["alpha"]
            self.fit.setData(np.asarray(tau), model)
            self.plot.setTitle(f"α={fit['alpha']:.2f}  D={fit['D']:.3g}  "
                               f"R²={fit['r2']:.2f}")
        self.plot.setLabel("left", "MSD (µm²)" if self._cft.get("scaled") else "MSD (px²)")
        self.plot.setLabel("bottom", "lag (min)" if self._dt else "lag (frames)")
