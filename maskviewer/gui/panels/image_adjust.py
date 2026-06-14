"""Image-adjustment panel — the display controls for the base channel.

An interactive histogram with a draggable min/max region is the primary
brightness/contrast control (as in ImageJ / napari). Brightness & contrast
sliders mirror that region (center / width), and there are gamma, colormap (LUT)
and invert controls plus Auto (percentile stretch) and Reset. State is reported
as a `luts.DisplayState`; the viewer caches one per channel so settings survive
channel switches. Emits `displayChanged` whenever the rendered look changes.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ..luts import DisplayState, PRESETS

_SLIDER = 1000


class ImageAdjustPanel(QtWidgets.QWidget):
    displayChanged = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dmin, self._dmax = 0.0, 1.0
        self._img = None
        self._emit = True

        self.plot = pg.PlotWidget()
        self.plot.setMaximumHeight(150)
        self.plot.setMenuEnabled(False)
        self.plot.hideAxis("left")
        self.plot.setMouseEnabled(x=False, y=False)
        self.curve = pg.PlotDataItem(pen=pg.mkPen((180, 180, 180)),
                                     fillLevel=0, brush=(140, 140, 140, 120))
        self.plot.addItem(self.curve)
        self.region = pg.LinearRegionItem(brush=(0, 128, 255, 40))
        self.region.sigRegionChanged.connect(self._on_region)
        self.plot.addItem(self.region)

        self.plot.setToolTip("Intensity histogram; drag the blue handles to set "
                             "the display range (brightness/contrast)")
        self.bright = self._slider()
        self.bright.setToolTip("Shift the display range (brightness)")
        self.contrast = self._slider()
        self.contrast.setToolTip("Narrow/widen the display range (contrast)")
        self.bright.valueChanged.connect(self._on_bc)
        self.contrast.valueChanged.connect(self._on_bc)
        self.gamma = self._slider(10, 300, 100)
        self.gamma.setToolTip("Gamma (mid-tone) correction; >1 brightens")
        self.gamma_lbl = QtWidgets.QLabel("1.00")
        self.gamma.valueChanged.connect(self._on_gamma)
        self.cmap = QtWidgets.QComboBox()
        self.cmap.addItems(PRESETS)
        self.cmap.setToolTip("Colormap / LUT for this channel "
                             "(e.g. magenta for SiR-actin Cy5)")
        self.cmap.currentTextChanged.connect(self._fire)
        self.invert = QtWidgets.QCheckBox("Invert LUT")
        self.invert.setToolTip("Invert the colormap")
        self.invert.toggled.connect(self._fire)
        self.levels_lbl = QtWidgets.QLabel("–")

        auto = QtWidgets.QPushButton("Auto")
        auto.setToolTip("Stretch the display range to the 1–99th percentile")
        auto.clicked.connect(self.auto)
        reset = QtWidgets.QPushButton("Reset")
        reset.setToolTip("Reset to full range, gamma 1, no invert")
        reset.clicked.connect(self.reset)
        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(auto)
        btns.addWidget(reset)

        form = QtWidgets.QFormLayout()
        form.addRow("Brightness", self.bright)
        form.addRow("Contrast", self.contrast)
        grow = QtWidgets.QHBoxLayout()
        grow.addWidget(self.gamma, 1)
        grow.addWidget(self.gamma_lbl)
        form.addRow("Gamma", self._wrap(grow))
        form.addRow("Colormap", self.cmap)
        form.addRow(self.invert)
        form.addRow("Levels", self.levels_lbl)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.plot)
        lay.addLayout(form)
        lay.addLayout(btns)
        lay.addStretch(1)

    # -- public ----------------------------------------------------------
    def set_image_data(self, img):
        """Update the histogram + data range for a new frame (keeps levels)."""
        self._img = np.asarray(img)
        finite = self._img[np.isfinite(self._img)]
        if finite.size:
            self._dmin = float(finite.min())
            self._dmax = float(finite.max())
        if self._dmax <= self._dmin:
            self._dmax = self._dmin + 1.0
        hist, edges = np.histogram(finite if finite.size else [0, 1], bins=256)
        centers = (edges[:-1] + edges[1:]) / 2.0
        self.curve.setData(centers, hist)
        lo, hi = self.region.getRegion()           # never clamp the live levels
        self.region.setBounds((min(self._dmin, lo), max(self._dmax, hi)))
        self.plot.setXRange(self._dmin, self._dmax, padding=0.02)
        self._sync_bc_from_region()

    def state(self) -> DisplayState:
        lo, hi = self.region.getRegion()
        return DisplayState(levels=(float(lo), float(hi)),
                            colormap=self.cmap.currentText(),
                            gamma=self.gamma.value() / 100.0,
                            invert=self.invert.isChecked())

    def set_state(self, ds: DisplayState):
        """Apply a cached DisplayState without emitting (viewer renders after)."""
        self._emit = False
        self._set_combo(self.cmap, ds.colormap)
        self.gamma.setValue(int(round(ds.gamma * 100)))
        self.gamma_lbl.setText(f"{ds.gamma:.2f}")
        self.invert.setChecked(ds.invert)
        lo, hi = ds.levels
        self.region.setBounds((min(self._dmin, lo), max(self._dmax, hi)))
        self.region.setRegion(ds.levels)
        self._sync_bc_from_region()
        self._emit = True

    def auto(self, lo_pct=1.0, hi_pct=99.0):
        if self._img is None:
            return
        finite = self._img[np.isfinite(self._img)]
        lo, hi = np.percentile(finite if finite.size else [0, 1], (lo_pct, hi_pct))
        if hi <= lo:
            hi = lo + 1.0
        self.region.setRegion((float(lo), float(hi)))   # → _on_region → fire

    def reset(self):
        self._emit = False
        self.gamma.setValue(100)
        self.gamma_lbl.setText("1.00")
        self.invert.setChecked(False)
        self._emit = True
        self.region.setRegion((self._dmin, self._dmax))

    # -- internal --------------------------------------------------------
    def _on_region(self):
        self._sync_bc_from_region()
        self._update_levels_label()
        self._fire()

    def _on_bc(self):
        if not self._emit:
            return
        drange = self._dmax - self._dmin
        bright = self.bright.value() / _SLIDER
        contrast = self.contrast.value() / _SLIDER
        width = max(1.0 - contrast, 0.001) * drange
        center = self._dmin + bright * drange
        self._emit = False
        self.region.setRegion((center - width / 2.0, center + width / 2.0))
        self._emit = True
        self._update_levels_label()
        self._fire()

    def _sync_bc_from_region(self):
        lo, hi = self.region.getRegion()
        drange = self._dmax - self._dmin or 1.0
        center = (lo + hi) / 2.0
        width = hi - lo
        bright = (center - self._dmin) / drange
        contrast = 1.0 - (width / drange)
        prev = self._emit
        self._emit = False
        self.bright.setValue(int(np.clip(bright, 0, 1) * _SLIDER))
        self.contrast.setValue(int(np.clip(contrast, 0, 1) * _SLIDER))
        self._emit = prev
        self._update_levels_label()

    def _on_gamma(self, v):
        self.gamma_lbl.setText(f"{v / 100.0:.2f}")
        self._fire()

    def _fire(self, *_):
        if self._emit:
            self.displayChanged.emit()

    def _update_levels_label(self):
        lo, hi = self.region.getRegion()
        self.levels_lbl.setText(f"{lo:.0f} – {hi:.0f}")

    # -- widget helpers --------------------------------------------------
    @staticmethod
    def _slider(lo=0, hi=_SLIDER, val=None):
        s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(hi // 2 if val is None else val)
        return s

    @staticmethod
    def _wrap(layout):
        w = QtWidgets.QWidget()
        w.setLayout(layout)
        return w

    @staticmethod
    def _set_combo(combo, text):
        i = combo.findText(text)
        if i >= 0:
            combo.setCurrentIndex(i)
