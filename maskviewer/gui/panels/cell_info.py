"""Cell-info panel — inspect the cell clicked in the view.

Shows a summary of the selected cell's track and a time-series plot of any
*selected* per-frame characteristic — area, perimeter, circularity, eccentricity,
aspect ratio, solidity, axes, orientation, extent, speed, displacement, turning
angle, consecutive IoU, area change, nearest-neighbour distance/count, per-frame
state, and per-channel intensity / membrane contrast — plus an MSD (log-log)
view with the diffusion-exponent fit.

Which metrics are computed + offered is controlled by the Config ▸ Cell plot
metrics menu (the panel owns the enabled set, persisted via QSettings); changing
one recomputes the selected cell and updates this plot menu immediately.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import cell_metrics, motion, metric_docs, lineage
from ..plot_export import save_plot

_MSD = "MSD (log-log)"
_MSD_LIN = "MSD (linear)"
_AUTO = "Direction autocorrelation"
_NN = {"nn_dist", "n_neighbors"}


class CellInfoPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell_id = 0
        self._cft = {}
        self._dt = None
        self._ctx = None                       # (labels, um, dt, recording)
        self.available = []                    # selectable metric keys
        self.neighbor_provider = None          # callable -> {cid:(T,2)} | None
        self.shape_mode_provider = None        # callable -> shape-mode model | None
        self.divisions = []                    # division events for lineage info
        self._settings = QtCore.QSettings("cellscope_analysis", "viewer")
        dis = self._settings.value("cell_metrics_disabled", [])
        if isinstance(dis, str):                       # QSettings may unwrap a 1-list
            dis = [dis]
        self._disabled = set(dis) if dis else set()

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
                                                       style=2))
        self.marker = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen((255, 200, 0), width=1))
        self.plot.addItem(self.marker)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        lay.addWidget(self.info)
        self.save_btn = QtWidgets.QPushButton("Save…")
        self.save_btn.setToolTip("Save this plot as PNG/SVG")
        self.save_btn.clicked.connect(
            lambda: save_plot(self.plot, self, f"cell{self.cell_id}.png"))
        mrow = QtWidgets.QHBoxLayout()
        mrow.addWidget(QtWidgets.QLabel("Plot"))
        mrow.addWidget(self.metric, 1)
        mrow.addWidget(self.save_btn)
        lay.addLayout(mrow)
        lay.addWidget(self.plot)

    # -- config ----------------------------------------------------------
    def set_available(self, channel_names, um_per_px=None):
        self.available = cell_metrics.available_frame_metrics(channel_names)

    def enabled(self):
        return [k for k in self.available if k not in self._disabled]

    def is_enabled(self, key):
        return key not in self._disabled

    def set_metric_enabled(self, key, on):
        if on:
            self._disabled.discard(key)
        else:
            self._disabled.add(key)
        self._settings.setValue("cell_metrics_disabled", sorted(self._disabled))
        if self._ctx and self.cell_id:
            self._compute()                    # recompute + re-list immediately

    # -- data ------------------------------------------------------------
    def set_cell(self, cell_id, labels, um_per_px=None, dt_min=None, recording=None):
        if not cell_id:
            return self.clear_cell()
        self.cell_id = int(cell_id)
        self._dt = dt_min
        self._ctx = (labels, um_per_px, dt_min, recording)
        self._compute()

    def _compute(self):
        labels, um, dt, rec = self._ctx
        want = self.enabled()
        nh = self.neighbor_provider() if (self.neighbor_provider
                                          and _NN & set(want)) else None
        sm = self.shape_mode_provider() if (self.shape_mode_provider
                                            and "shape_mode" in want) else None
        self._cft = cell_metrics.cell_frame_table(
            labels, self.cell_id, um, dt, recording=rec, metrics=want,
            neighbor_history=nh, shape_model=sm)
        self.title.setText(f"Cell {self.cell_id}")
        self._update_info()
        self._rebuild_combo()

    def _update_info(self):
        s = self._cft.get("series", {})
        m = self._cft.get("summary", {})
        u = "µm" if self._cft.get("scaled") else "px"
        fr = self._cft.get("frame", np.array([]))
        extra = ""
        if "state_code" in s:
            codes = s["state_code"][0]
            cls = codes[(codes == 1) | (codes == 2)]
            fr_round = float((codes == 2).sum() / cls.size) if cls.size else float("nan")
            extra = f"<br>rounded fraction: {fr_round:.2f}"
        if self.divisions:
            parents, daughters = lineage.relatives(self.divisions, self.cell_id)
            if parents:
                extra += f"<br>parent: cell {parents[0]}"
            if daughters:
                extra += f"<br>daughters: {', '.join(map(str, daughters))}"
        self.info.setText(
            f"frames tracked: {fr.size}"
            f" ({int(fr[0]) if fr.size else '-'}→{int(fr[-1]) if fr.size else '-'})<br>"
            f"net disp: {m.get('net_disp', float('nan')):.1f} {u}"
            f"   path: {m.get('total_path', float('nan')):.1f} {u}<br>"
            f"straightness: {m.get('straightness', float('nan')):.3f}"
            f"   persistence: {m.get('dir_autocorr_lag1', float('nan')):.3f}<br>"
            f"mean speed: {m.get('mean_speed', float('nan')):.3f} "
            f"{u}/{'min' if self._dt else 'frame'}" + extra)

    def _rebuild_combo(self):
        cur = self.metric.currentText()
        s = self._cft.get("series", {})
        items = sorted(s) + [_MSD, _MSD_LIN, _AUTO]
        self.metric.blockSignals(True)
        self.metric.clear()
        self.metric.addItems(items)
        for i, k in enumerate(items):
            tip = metric_docs.tooltip("MSD") if k.startswith("MSD") \
                else metric_docs.tooltip(k)
            if tip:
                self.metric.setItemData(i, tip, QtCore.Qt.ToolTipRole)
        self.metric.setCurrentText(
            cur if cur in items else ("area" if "area" in s else items[0]))
        self.metric.blockSignals(False)
        self._replot()

    def set_frame_marker(self, t):
        self.marker.setValue(t * self._dt if self._dt else t)

    def clear_cell(self):
        self.cell_id = 0
        self._cft = {}
        self._ctx = None
        self.title.setText("No cell selected")
        self.info.setText("Click a cell in the view to inspect it.")
        self.curve.setData([], [])
        self.fit.setData([], [])

    # -- plotting --------------------------------------------------------
    def _replot(self):
        key = self.metric.currentText()
        self.fit.setData([], [])
        if key in (_MSD, _MSD_LIN):
            return self._plot_msd(log=(key == _MSD))
        if key == _AUTO:
            return self._plot_autocorr()
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

    def _plot_autocorr(self):
        cen = self._cft.get("centroid_um")
        if cen is None:
            self.curve.setData([], [])
            return
        ac = motion.direction_autocorrelation(cen)
        self.marker.hide()
        self.plot.setLogMode(x=False, y=False)
        lags = np.arange(ac.size) * (self._dt or 1.0)
        self.curve.setData(lags, ac)
        self.plot.setTitle(f"lag-1 persistence = "
                           f"{ac[1]:.3f}" if ac.size > 1 else "")
        self.plot.setLabel("left", "direction autocorrelation ⟨cos θ⟩")
        self.plot.setLabel("bottom", "lag (min)" if self._dt else "lag (frames)")

    def _plot_msd(self, log=True):
        cen = self._cft.get("centroid_um")
        if cen is None:
            self.curve.setData([], [])
            return
        tau, vals = motion.msd(cen, self._dt)
        self.marker.hide()
        self.plot.setLogMode(x=log, y=log)
        self.curve.setData(np.asarray(tau), np.asarray(vals))
        fit = motion.fit_msd(tau, vals)
        if np.isfinite(fit["alpha"]) and len(tau):
            self.fit.setData(np.asarray(tau), 4 * fit["D"] * np.asarray(tau) ** fit["alpha"])
            self.plot.setTitle(f"α={fit['alpha']:.2f}  D={fit['D']:.3g}  R²={fit['r2']:.2f}")
        self.plot.setLabel("left", "MSD (µm²)" if self._cft.get("scaled") else "MSD (px²)")
        self.plot.setLabel("bottom", "lag (min)" if self._dt else "lag (frames)")
