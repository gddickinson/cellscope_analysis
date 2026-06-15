"""Manual pixel-size + time-scale overrides (project-wide).

When a recording's `.ome.json` metadata is missing or wrong, set the physical
**pixel size** (µm/px) and/or **frame interval** (min/frame) here. The values are
stored on the `Project` and applied to **every** recording loaded in the session
— the scale bar, all per-cell / motion / edge metrics (their µm and µm/min units),
and the cross-recording comparison. Unchecked = use each file's own metadata.
"""
from __future__ import annotations

from PyQt5 import QtWidgets


class ScaleDialog(QtWidgets.QDialog):
    def __init__(self, px_size, frame_interval, file_px, file_dt, on_apply,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pixel size & time scale")
        self.on_apply = on_apply

        self.px_chk = QtWidgets.QCheckBox("Override pixel size")
        self.px = QtWidgets.QDoubleSpinBox()
        self.px.setDecimals(5); self.px.setRange(1e-5, 1e6); self.px.setSuffix(" µm/px")
        self.px.setValue(px_size or file_px or 1.0)
        self.px_chk.setChecked(bool(px_size))

        self.dt_chk = QtWidgets.QCheckBox("Override time interval")
        self.dt = QtWidgets.QDoubleSpinBox()
        self.dt.setDecimals(4); self.dt.setRange(1e-4, 1e6); self.dt.setSuffix(" min/frame")
        self.dt.setValue(frame_interval or file_dt or 1.0)
        self.dt_chk.setChecked(bool(frame_interval))

        self.px.setEnabled(self.px_chk.isChecked())
        self.dt.setEnabled(self.dt_chk.isChecked())
        self.px_chk.toggled.connect(self.px.setEnabled)
        self.dt_chk.toggled.connect(self.dt.setEnabled)

        note = QtWidgets.QLabel(
            "Applies to ALL recordings in this project — use when a file's metadata "
            "is missing or wrong. Unchecked = use each file's own metadata.")
        note.setWordWrap(True)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)

        form = QtWidgets.QFormLayout()
        form.addRow(self.px_chk, self.px)
        form.addRow(self.dt_chk, self.dt)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(note)
        lay.addLayout(form)
        lay.addWidget(bb)

    def _apply(self):
        px = float(self.px.value()) if self.px_chk.isChecked() else None
        dt = float(self.dt.value()) if self.dt_chk.isChecked() else None
        self.on_apply(px, dt)
        self.accept()
