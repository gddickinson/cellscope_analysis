"""Pre-analysis dialog — channel alignment + field-of-view (FOV) cropping.

DIC and fluorescence channels are often offset by a small x/y shift, and the
imaged field can carry black borders. Both bias the mask-based analysis (e.g.
`edge_intensity` samples a channel relative to the masks). This dialog lets the
user **align** a moving channel onto a reference channel — automatically
(gradient phase-correlation, `analysis.registration`) or by nudging dy/dx — and
**define the FOV** rectangle — automatically (`analysis.fov`) or by hand — with a
live overlay preview (reference grey + moving magenta + the FOV box). Applying
stores a non-destructive correction on the project; the raw files are untouched.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from ..analysis import registration, fov as fov_mod

_REF_HINTS = ("dic", "bright", "phase", "trans")
_MOV_HINTS = ("cy5", "sir", "actin", "piezo", "gfp", "rfp", "488", "555", "594",
              "647", "fitc", "mscarlet", "tdtomato", "mneon")


def _guess(names, hints, default):
    for i, n in enumerate(names):
        if any(h in (n or "").lower() for h in hints):
            return i
    return default


def _norm(a):
    a = np.asarray(a, float)
    fin = a[np.isfinite(a)]
    if fin.size == 0:
        return np.zeros_like(a)
    lo, hi = np.percentile(fin, (1, 99.5))
    return np.clip((a - lo) / ((hi - lo) or 1.0), 0, 1)


class PrepDialog(QtWidgets.QDialog):
    def __init__(self, recording, label, correction, on_apply, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Channel alignment & FOV — {label}")
        self.rec = recording
        self.on_apply = on_apply
        self._base_shifts = dict((correction or {}).get("shifts") or {})
        names = list(recording.channel_names)
        h, w = recording.height, recording.width

        self.ref = QtWidgets.QComboBox(); self.ref.addItems(names)
        self.mov = QtWidgets.QComboBox(); self.mov.addItems(names)
        self.ref.setCurrentIndex(_guess(names, _REF_HINTS, 0))
        self.mov.setCurrentIndex(_guess(names, _MOV_HINTS,
                                        1 if len(names) > 1 else 0))
        self.dy = self._dspin(-h, h); self.dx = self._dspin(-w, w)   # dy spans height
        self.auto_align = QtWidgets.QPushButton("Auto-align")
        self.frame = QtWidgets.QSpinBox()
        self.frame.setRange(0, max(0, recording.n_frames - 1))
        self.frame.setValue(recording.n_frames // 2)
        self.y0, self.y1 = self._ispin(0, h, 0), self._ispin(0, h, h)
        self.x0, self.x1 = self._ispin(0, w, 0), self._ispin(0, w, w)
        self.auto_fov = QtWidgets.QPushButton("Auto-detect FOV")
        self.full_fov = QtWidgets.QPushButton("Full frame")

        self.view = pg.PlotWidget()
        self.view.setMenuEnabled(False)
        self.view.setAspectLocked(True)
        self.view.getViewBox().invertY(True)
        self.img = pg.ImageItem()
        self.img.setOpts(axisOrder="row-major")
        self.box = pg.PlotCurveItem(pen=pg.mkPen("y", width=1.5))
        self.view.addItem(self.img); self.view.addItem(self.box)

        self._init_from(correction)
        self._build_layout()
        self._wire()
        self._update_preview()

    # -- widgets ---------------------------------------------------------
    def _dspin(self, lo, hi):
        s = QtWidgets.QDoubleSpinBox(); s.setRange(lo, hi)
        s.setSingleStep(0.5); s.setDecimals(2); return s

    def _ispin(self, lo, hi, val):
        s = QtWidgets.QSpinBox(); s.setRange(lo, hi); s.setValue(val); return s

    def _init_from(self, correction):
        mov = self.mov.currentIndex()
        sh = self._base_shifts.get(str(mov))
        if sh:
            self.dy.setValue(float(sh[0])); self.dx.setValue(float(sh[1]))
        rect = (correction or {}).get("fov")
        if rect:
            self.y0.setValue(rect[0]); self.y1.setValue(rect[1])
            self.x0.setValue(rect[2]); self.x1.setValue(rect[3])

    def _build_layout(self):
        form = QtWidgets.QFormLayout()
        form.addRow("Reference channel", self.ref)
        form.addRow("Align channel", self.mov)
        sh = QtWidgets.QHBoxLayout()
        sh.addWidget(QtWidgets.QLabel("dy")); sh.addWidget(self.dy)
        sh.addWidget(QtWidgets.QLabel("dx")); sh.addWidget(self.dx)
        sh.addWidget(self.auto_align)
        form.addRow("Shift (px)", self._wrap(sh))
        fv = QtWidgets.QHBoxLayout()
        for lab, sp in (("y0", self.y0), ("y1", self.y1),
                        ("x0", self.x0), ("x1", self.x1)):
            fv.addWidget(QtWidgets.QLabel(lab)); fv.addWidget(sp)
        form.addRow("FOV (px)", self._wrap(fv))
        fb = QtWidgets.QHBoxLayout()
        fb.addWidget(self.auto_fov); fb.addWidget(self.full_fov)
        fb.addWidget(QtWidgets.QLabel("preview frame")); fb.addWidget(self.frame)
        form.addRow("", self._wrap(fb))

        bb = QtWidgets.QDialogButtonBox()
        self.apply_btn = bb.addButton("Apply", QtWidgets.QDialogButtonBox.AcceptRole)
        bb.addButton(QtWidgets.QDialogButtonBox.Close)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(
            "Reference grey · align-channel magenta. Align so cell structure "
            "overlaps; set the FOV box inside any black border. Applies "
            "non-destructively to display + analysis.")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addLayout(form)
        lay.addWidget(self.view, 1)
        lay.addWidget(bb)
        self.resize(560, 640)

    def _wrap(self, inner):
        w = QtWidgets.QWidget(); w.setLayout(inner); return w

    def _wire(self):
        self.auto_align.clicked.connect(self._do_auto_align)
        self.auto_fov.clicked.connect(self._do_auto_fov)
        self.full_fov.clicked.connect(self._do_full_fov)
        self.mov.currentIndexChanged.connect(self._on_mov_changed)
        for s in (self.dy, self.dx):
            s.valueChanged.connect(self._update_preview)
        for s in (self.y0, self.y1, self.x0, self.x1, self.frame):
            s.valueChanged.connect(self._update_preview)
        self.ref.currentIndexChanged.connect(self._update_preview)

    # -- actions ---------------------------------------------------------
    def _on_mov_changed(self):
        sh = self._base_shifts.get(str(self.mov.currentIndex()))
        self.dy.setValue(float(sh[0]) if sh else 0.0)
        self.dx.setValue(float(sh[1]) if sh else 0.0)
        self._update_preview()

    def _do_auto_align(self):
        r, m = self.ref.currentIndex(), self.mov.currentIndex()
        dy, dx = registration.estimate_stack_shift(self.rec.data[:, r],
                                                   self.rec.data[:, m])
        self.dy.setValue(dy); self.dx.setValue(dx)

    def _do_auto_fov(self):
        y0, y1, x0, x1 = fov_mod.auto_fov(self.rec.data)
        self.y0.setValue(y0); self.y1.setValue(y1)
        self.x0.setValue(x0); self.x1.setValue(x1)

    def _do_full_fov(self):
        self.y0.setValue(0); self.y1.setValue(self.rec.height)
        self.x0.setValue(0); self.x1.setValue(self.rec.width)

    def _rect(self):
        return (self.y0.value(), self.y1.value(), self.x0.value(), self.x1.value())

    def _update_preview(self):
        t = self.frame.value()
        # build BOTH layers from raw data so neither is pre-shifted by a stored
        # correction — the overlay then shows exactly the live dy/dx being edited
        ref = _norm(np.asarray(self.rec.data[t, self.ref.currentIndex()], float))
        mov = registration.apply_shift(
            np.asarray(self.rec.data[t, self.mov.currentIndex()], float),
            self.dy.value(), self.dx.value())
        mov = _norm(mov)
        rgb = np.zeros((*ref.shape, 3), float)
        rgb[..., 0] = np.clip(ref + mov, 0, 1)        # magenta = R+B
        rgb[..., 1] = ref
        rgb[..., 2] = np.clip(ref + mov, 0, 1)
        self.img.setImage((rgb * 255).astype(np.uint8), autoLevels=False)
        y0, y1, x0, x1 = self._rect()
        self.box.setData(x=[x0, x1, x1, x0, x0], y=[y0, y0, y1, y1, y0])
        self.view.autoRange()

    def _apply(self):
        shifts = dict(self._base_shifts)
        mov = str(self.mov.currentIndex())
        dy, dx = round(self.dy.value(), 3), round(self.dx.value(), 3)
        if dy or dx:
            shifts[mov] = [dy, dx]
        else:
            shifts.pop(mov, None)
        y0, y1, x0, x1 = self._rect()
        full = (y0, y1, x0, x1) == (0, self.rec.height, 0, self.rec.width)
        correction = {"shifts": shifts,
                      "fov": None if full else [y0, y1, x0, x1]}
        self.on_apply(correction)
        self.accept()
