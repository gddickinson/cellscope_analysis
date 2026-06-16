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

Per-cell results are memoised, so revisiting a cell is instant. **Precompute all
cells** computes every cell up front (off the GUI thread, with the status-bar
progress + ETA) so switching between cells to compare them has no recompute lag.
The cache is keyed by the recording + the enabled-metric set and drops itself
when either changes.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ...analysis import cell_metrics, motion, metric_docs, lineage
from ..plot_export import save_plot
from ..task_runner import AsyncComputeMixin

_MSD = "MSD (log-log)"
_MSD_LIN = "MSD (linear)"
_AUTO = "Direction autocorrelation"
_NN = {"nn_dist", "n_neighbors"}


class CellInfoPanel(AsyncComputeMixin, QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell_id = 0
        self._cft = {}
        self._dt = None
        self._ctx = None                       # (labels, um, dt, recording)
        self._cache = {}                       # cell_id -> cft (so revisits are instant)
        self._cache_sig = None                 # invalidates the cache on ctx/metric change
        self._precomputed = False
        self.available = []                    # selectable metric keys
        self.neighbor_provider = None          # callable -> {cid:(T,2)} | None
        self.shape_mode_provider = None        # callable -> shape-mode model | None
        self.divisions = []                    # division events for lineage info
        self._settings = QtCore.QSettings("cellscope_analysis", "viewer")
        saved = self._settings.value("cell_metrics_enabled")
        if saved is None:                              # first run → minimal fast default
            self._enabled = set(cell_metrics.DEFAULT_PLOT_METRICS)
        else:
            if isinstance(saved, str):                 # QSettings may unwrap a 1-list
                saved = [saved]
            self._enabled = set(saved)
        self._auto_precompute = self._settings.value(
            "cell_info/auto_precompute", False, type=bool)

        self.title = QtWidgets.QLabel("No cell selected")
        self.title.setStyleSheet("font-weight: bold;")
        self.info = QtWidgets.QLabel("Click a cell in the view to inspect it.")
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(self.info.textInteractionFlags() | 0x1)
        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(120)
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

        self.precompute_btn = QtWidgets.QPushButton("Precompute all cells")
        self.precompute_btn.setToolTip(
            "Compute every cell's metrics now (with the current Cell-plot-metrics "
            "selection) so switching between cells to compare them is instant. "
            "Re-run after enabling more metrics.")
        self.precompute_btn.clicked.connect(self.precompute_all)
        self.cache_label = QtWidgets.QLabel("")
        self.cache_label.setStyleSheet("color: gray;")
        prow = QtWidgets.QHBoxLayout()
        prow.addWidget(self.precompute_btn)
        prow.addWidget(self.cache_label, 1)
        lay.addLayout(prow)
        lay.addWidget(self.plot)

    # -- config ----------------------------------------------------------
    def set_available(self, channel_names, um_per_px=None):
        self.available = cell_metrics.available_frame_metrics(channel_names)

    def enabled(self):
        return [k for k in self.available if k in self._enabled]

    def is_enabled(self, key):
        return key in self._enabled

    def set_metric_enabled(self, key, on):
        if on:
            self._enabled.add(key)
        else:
            self._enabled.discard(key)
        self._settings.setValue("cell_metrics_enabled", sorted(self._enabled))
        self._invalidate_cache()               # cached cfts are now stale
        if self._ctx and self.cell_id:
            self._compute()                    # recompute + re-list immediately

    # -- data ------------------------------------------------------------
    def set_context(self, labels, um_per_px=None, dt_min=None, recording=None):
        """Give the panel the recording's data without selecting a cell, so
        **Precompute all cells** works before anything is clicked. Invalidates the
        per-cell cache when the recording changes; auto-precomputes then if the
        Config toggle is on."""
        ctx = (labels, um_per_px, dt_min, recording)
        changed = self._cache_key(ctx, self.enabled()) != self._cache_sig
        if changed:
            self._invalidate_cache()
        self._dt = dt_min
        self._ctx = ctx
        if changed and self._auto_precompute and labels is not None:
            self.precompute_all()

    def set_auto_precompute(self, on):
        """Config toggle (persisted): precompute all cells automatically when a
        recording loads. Turning it on precomputes the current recording now."""
        self._auto_precompute = bool(on)
        self._settings.setValue("cell_info/auto_precompute", self._auto_precompute)
        if on and self._ctx and self._ctx[0] is not None and not self._precomputed:
            self.precompute_all()

    def set_cell(self, cell_id, labels, um_per_px=None, dt_min=None, recording=None):
        if not cell_id:
            return self.clear_cell()
        self.cell_id = int(cell_id)
        self.set_context(labels, um_per_px, dt_min, recording)
        self._compute()

    def _cache_key(self, ctx, want):
        """Signature that must hold for a cached cft to stay valid."""
        labels, um, dt, rec = ctx
        return (id(labels), um, dt, id(rec), tuple(sorted(want)))

    def _invalidate_cache(self):
        self._cache.clear()
        self._cache_sig = None
        self._precomputed = False
        self._update_cache_label()

    def _update_cache_label(self):
        self.cache_label.setText(
            f"✓ {len(self._cache)} cells cached — switching is instant"
            if self._precomputed else "")

    def _providers(self, want):
        """Fetch the neighbour-history / shape-model inputs (on the GUI thread)
        only when an enabled metric needs them."""
        nh = self.neighbor_provider() if (self.neighbor_provider
                                          and _NN & set(want)) else None
        sm = self.shape_mode_provider() if (self.shape_mode_provider
                                            and "shape_mode" in want) else None
        return nh, sm

    def _make_cft(self, cell_id, ctx, want, nh, sm):
        """Pure per-cell compute — safe to call off the GUI thread (numpy only)."""
        labels, um, dt, rec = ctx
        return cell_metrics.cell_frame_table(
            labels, cell_id, um, dt, recording=rec, metrics=want,
            neighbor_history=nh, shape_model=sm)

    def _compute(self):
        want = self.enabled()
        sig = self._cache_key(self._ctx, want)
        if sig != self._cache_sig:             # ctx/metrics changed → drop cache
            self._cache.clear()
            self._cache_sig = sig
            self._precomputed = False
            self._update_cache_label()
        cft = self._cache.get(self.cell_id)
        if cft is None:                        # cache miss → compute + memoise
            nh, sm = self._providers(want)
            cft = self._make_cft(self.cell_id, self._ctx, want, nh, sm)
            self._cache[self.cell_id] = cft
        self._cft = cft
        self.title.setText(f"Cell {self.cell_id}")
        self._update_info()
        self._rebuild_combo()

    def precompute_all(self):
        """Compute every cell's metrics up front (off-thread, with the status-bar
        progress + ETA) so subsequent cell switches are instant lookups."""
        if not self._ctx or self._ctx[0] is None:
            self.cache_label.setText("Load a recording first.")
            return
        ctx = self._ctx
        want = self.enabled()
        sig = self._cache_key(ctx, want)
        nh, sm = self._providers(want)
        ids = [int(c) for c in np.unique(ctx[0]) if c > 0]
        if not ids:
            self.cache_label.setText("No cells to precompute.")
            return

        def work(progress_cb):
            out = {}
            for i, cid in enumerate(ids):
                out[cid] = self._make_cft(cid, ctx, want, nh, sm)
                if progress_cb:
                    progress_cb(i + 1, len(ids))
            return out

        def apply(cache):
            self._cache = cache
            self._cache_sig = sig
            self._precomputed = True
            self._update_cache_label()
            if self.cell_id in cache:          # refresh the open cell from the cache
                self._cft = cache[self.cell_id]
                self._update_info()
                self._rebuild_combo()

        self.cache_label.setText(f"Precomputing {len(ids)} cells…")
        self._dispatch("Cell info (all cells)", work, apply)

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
        # Deselect only — keep the data context + precomputed cache so a misclick
        # doesn't discard a precompute. The cache is dropped when the recording
        # (or the enabled metric set) changes, via the signature check.
        self.cell_id = 0
        self._cft = {}
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
            fu = motion.fit_furth(tau, vals)
            pt = (f"  ·  Fürth P={fu['persistence_time']:.1f} "
                  f"{'min' if self._dt else 'fr'}"
                  if np.isfinite(fu["persistence_time"]) else "")
            self.plot.setTitle(f"α={fit['alpha']:.2f}  D={fit['D']:.3g}  "
                               f"R²={fit['r2']:.2f}{pt}")
        self.plot.setLabel("left", "MSD (µm²)" if self._cft.get("scaled") else "MSD (px²)")
        self.plot.setLabel("bottom", "lag (min)" if self._dt else "lag (frames)")
