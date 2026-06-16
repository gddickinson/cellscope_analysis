"""Unified tabbed Config / Settings window.

One dialog gathering the project's configurable analysis settings as tabs —
**Cell plot metrics** (which per-frame metrics the Cell-Info plot computes /
offers, plus an *auto-precompute all cells on load* toggle), **Comparison
analysis** (which families the Comparison window computes),
and **Pixel size & time scale** (manual µm/px + min/frame overrides). Opened from
Config ▸ Settings… (Ctrl+,). The metric / comparison toggles apply live (the
comparison ones on its next Recompute); the scale tab applies on its button.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from ..analysis import cell_metrics, metric_docs
from .compare_tables import (COMPARE_OPTIONS, ANALYSIS_PARAMS, ANALYSIS_CHOICES,
                             apply_analysis_params)
from .scale_dialog import ScalePanel

_METRIC_ORDER = ["Shape & state", "Motion & dynamics", "Neighbours & contact",
                 "Fluorescence (per channel)"]


def _metric_category(key):
    if key.startswith(("intensity_", "membrane_contrast_", "boundary_grad_",
                       "membrane_score_")):
        return "Fluorescence (per channel)"
    if (key in ("nn_dist", "n_neighbors") or key.startswith(("contact_", "n_contacts",
                                                             "max_contact"))):
        return "Neighbours & contact"
    if key in ("speed", "displacement_from_start", "turning_angle", "iou_prev",
               "area_change"):
        return "Motion & dynamics"
    return "Shape & state"


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
        tabs.addTab(self._params_tab(), "Analysis parameters")
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
        v.addWidget(_wrap("Per-frame metrics computed + offered in the Cell-Info plot "
                          "menu (grouped by kind; toggling recomputes at once). The "
                          "default is a cheap subset — enable more as you need them."))
        auto = QtWidgets.QCheckBox("Auto-precompute all cells when a recording loads")
        auto.setToolTip("Precompute every cell's Cell-Info metrics automatically when a "
                        "recording loads so switching between cells is instant. Off by "
                        "default; runs in the background with a progress bar. (The heavier "
                        "Edge-dynamics precompute stays on the 'Precompute all cells' button.)")
        auto.setChecked(info._auto_precompute)
        auto.toggled.connect(info.set_auto_precompute)
        v.addWidget(auto)
        host = QtWidgets.QWidget()
        hv = QtWidgets.QVBoxLayout(host)
        avail = list(info.available)
        by_cat = {c: [k for k in avail if _metric_category(k) == c] for c in _METRIC_ORDER}
        for cat in _METRIC_ORDER:
            keys = by_cat[cat]
            if not keys:
                continue
            head = QtWidgets.QLabel(f"<b>{cat}</b>")
            hv.addWidget(head)
            grid = QtWidgets.QGridLayout()
            for i, key in enumerate(keys):
                cb = QtWidgets.QCheckBox(cell_metrics.metric_label(key, um))
                cb.setChecked(info.is_enabled(key))
                cb.setToolTip(metric_docs.tooltip(key))
                cb.toggled.connect(lambda on, k=key: info.set_metric_enabled(k, on))
                grid.addWidget(cb, i // 2, i % 2)
            hv.addLayout(grid)
        if not avail:
            hv.addWidget(QtWidgets.QLabel("(load a recording)"))
        hv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        v.addWidget(scroll)
        return w

    def _params_tab(self):
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        v.addWidget(_wrap("Parameters that define the analyses (grouped by kind). Apply "
                          "to <b>both</b> the comparison (on its next Recompute) and the "
                          "interactive overlays / colour-by / panels."))
        host = QtWidgets.QWidget()
        hv = QtWidgets.QVBoxLayout(host)
        self._param_spins = {}
        self._param_combos = {}
        sections = []                                      # first-appearance order
        for *_a, sect, _t in list(ANALYSIS_PARAMS) + list(ANALYSIS_CHOICES):
            if sect not in sections:
                sections.append(sect)
        for sect in sections:
            hv.addWidget(QtWidgets.QLabel(f"<b>{sect}</b>"))
            form = QtWidgets.QFormLayout()
            hv.addLayout(form)
            for key, label, default, lo, hi, dec, s, tip in ANALYSIS_PARAMS:
                if s != sect:
                    continue
                sp = QtWidgets.QDoubleSpinBox()
                sp.setRange(lo, hi)
                sp.setDecimals(dec)
                sp.setValue(self._settings.value(f"analysis/{key}", default, type=float))
                sp.setToolTip(tip)
                sp.valueChanged.connect(lambda val, k=key: self._set_param(k, val))
                self._param_spins[key] = sp
                form.addRow(label, sp)
            for key, label, default, choices, s, tip in ANALYSIS_CHOICES:
                if s != sect:
                    continue
                cb = QtWidgets.QComboBox()
                cb.addItems(choices)
                cur = self._settings.value(f"analysis/{key}", default, type=str)
                cb.setCurrentText(cur if cur in choices else default)
                cb.setToolTip(tip)
                cb.currentTextChanged.connect(lambda txt, k=key: self._set_choice(k, txt))
                self._param_combos[key] = cb
                form.addRow(label, cb)
        hv.addStretch(1)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        v.addWidget(scroll)
        reset = QtWidgets.QPushButton("Reset to defaults")
        reset.clicked.connect(self._reset_params)
        v.addWidget(reset)
        return w

    # params whose change invalidates the cached VAMPIRE shape model (it re-fits)
    _SHAPE_PARAMS = ("shape_n_modes", "state_min_area_px")

    def _set_param(self, key, val):
        self._settings.setValue(f"analysis/{key}", float(val))
        apply_analysis_params(self._settings)
        if key in self._SHAPE_PARAMS:                     # shape model must re-fit
            self.win._shape_model = None
        for attr in ("_contact_cache", "_iface_cache"):   # force overlays to recompute
            getattr(self.win, attr, {}).clear()
        if getattr(self.win, "masks", None) is not None:
            self.win._on_frame(self.win.timeline.value())  # redraw with the new params

    def _set_choice(self, key, text):
        self._settings.setValue(f"analysis/{key}", str(text))
        apply_analysis_params(self._settings)
        if getattr(self.win, "masks", None) is not None:
            self.win._on_frame(self.win.timeline.value())

    def _reset_params(self):
        for key, _l, default, *_ in ANALYSIS_PARAMS:
            self._param_spins[key].setValue(default)
        for key, _l, default, *_ in ANALYSIS_CHOICES:
            self._param_combos[key].setCurrentText(default)

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
