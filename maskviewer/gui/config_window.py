"""Unified tabbed Config / Settings window.

One dialog gathering the project's configurable analysis settings as tabs —
**Cell plot metrics** (which per-frame metrics the Cell-Info plot computes /
offers), **Comparison analysis** (which families the Comparison window computes),
and **Pixel size & time scale** (manual µm/px + min/frame overrides). Opened from
Config ▸ Settings… (Ctrl+,). The metric / comparison toggles apply live (the
comparison ones on its next Recompute); the scale tab applies on its button.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from ..analysis import cell_metrics, metric_docs
from .compare_tables import COMPARE_OPTIONS
from .scale_dialog import ScalePanel


class ConfigWindow(QtWidgets.QDialog):
    def __init__(self, win, parent=None):
        super().__init__(parent or win)
        self.win = win
        self.setWindowTitle("Settings")
        self.resize(540, 480)
        self._settings = QtCore.QSettings("cellscope_analysis", "viewer")
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._metrics_tab(), "Cell plot metrics")
        tabs.addTab(self._compare_tab(), "Comparison analysis")
        tabs.addTab(self._scale_tab(), "Pixel size && time scale")
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)

    # -- Cell plot metrics ----------------------------------------------
    def _metrics_tab(self):
        info = self.win.cell_info
        um = self.win.recording.um_per_px if self.win.recording else None
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(_wrap("Per-frame metrics computed + offered in the Cell-Info "
                          "plot menu (toggling recomputes immediately)."))
        grid = QtWidgets.QGridLayout()
        avail = list(info.available)
        for i, key in enumerate(avail):
            cb = QtWidgets.QCheckBox(cell_metrics.metric_label(key, um))
            cb.setChecked(info.is_enabled(key))
            cb.setToolTip(metric_docs.tooltip(key))
            cb.toggled.connect(lambda on, k=key: info.set_metric_enabled(k, on))
            grid.addWidget(cb, i // 2, i % 2)
        if not avail:
            grid.addWidget(QtWidgets.QLabel("(load a recording)"), 0, 0)
        host = QtWidgets.QWidget()
        host.setLayout(grid)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        v.addWidget(scroll)
        return w

    # -- Comparison analysis --------------------------------------------
    def _compare_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(_wrap("Analysis families the Comparison window computes — disable "
                          "the heavy ones you don't need to speed up the per-recording "
                          "pass. Changes apply on the next Recompute. (Edge↔fluorescence "
                          "is set by the Comparison window's channel selector.)"))
        for key, label, default, tip in COMPARE_OPTIONS:
            cb = QtWidgets.QCheckBox(label)
            cb.setToolTip(tip)
            cb.setChecked(self._settings.value(f"compare/opt_{key}", default, type=bool))
            cb.toggled.connect(
                lambda on, k=key: self._settings.setValue(f"compare/opt_{k}", on))
            v.addWidget(cb)
        v.addStretch(1)
        btn = QtWidgets.QPushButton("Comparison plot options…")
        btn.setToolTip("Fonts, sizes, axes, bins, trendlines… for the graphs")
        btn.clicked.connect(self.win.open_compare_plot_options)
        v.addWidget(btn)
        return w

    # -- Pixel size & time scale ----------------------------------------
    def _scale_tab(self):
        rec = self.win.recording
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        self._scale = ScalePanel(
            self.win.project.px_size, self.win.project.frame_interval,
            rec.um_per_px if rec else None, rec.time_interval_min if rec else None)
        v.addWidget(self._scale)
        btn = QtWidgets.QPushButton("Apply scale to all recordings")
        btn.clicked.connect(lambda: self.win._apply_scale(*self._scale.values()))
        v.addWidget(btn)
        v.addStretch(1)
        return w


def _wrap(text):
    lab = QtWidgets.QLabel(text)
    lab.setWordWrap(True)
    return lab
