"""Display panel — recording / channel pickers + mask & overlay options.

A signal-only QWidget (no data/array logic) so it stays small and reusable. The
viewer owns the data and reacts: recording/channel selection, mask show /
outline / opacity, colour-by mode (Cell ID, per-frame area, track length) and
the overlay toggles (scale bar, info text, cell-ID labels, track trails).
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

COLOR_BY = [("Cell ID", "id"), ("Cell state", "state"),
            ("Area (per frame)", "area"), ("Track length", "track")]
OVERLAYS = [("scalebar", "Scale bar", True), ("info", "Frame / time", True),
            ("ids", "Cell IDs", False), ("trails", "Track trails", False)]


class DisplayPanel(QtWidgets.QWidget):
    recordingChanged = QtCore.pyqtSignal(int)
    channelChanged = QtCore.pyqtSignal(int)
    maskOptionsChanged = QtCore.pyqtSignal()
    colorByChanged = QtCore.pyqtSignal(str)
    overlayToggled = QtCore.pyqtSignal(str, bool)
    displayModeChanged = QtCore.pyqtSignal()        # composite on/off or channels

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)

        rec_box = QtWidgets.QGroupBox("Recording")
        rf = QtWidgets.QFormLayout(rec_box)
        self.recording = QtWidgets.QComboBox()
        self.recording.currentIndexChanged.connect(self.recordingChanged)
        self.channel = QtWidgets.QComboBox()
        self.channel.currentIndexChanged.connect(self.channelChanged)
        rf.addRow("Recording", self.recording)
        rf.addRow("Channel", self.channel)
        self.composite = QtWidgets.QCheckBox("Composite (blend channels)")
        self.composite.toggled.connect(self._composite_toggled)
        rf.addRow(self.composite)
        outer.addWidget(rec_box)

        self.comp_box = QtWidgets.QGroupBox("Composite channels")
        self.comp_box.setEnabled(False)
        self._comp_layout = QtWidgets.QVBoxLayout(self.comp_box)
        self._chan_checks = []
        outer.addWidget(self.comp_box)

        mask_box = QtWidgets.QGroupBox("Masks")
        mf = QtWidgets.QFormLayout(mask_box)
        self.show_masks = QtWidgets.QCheckBox("Show masks")
        self.show_masks.setChecked(True)
        self.show_masks.toggled.connect(self.maskOptionsChanged)
        self.outline = QtWidgets.QCheckBox("Outlines only")
        self.outline.toggled.connect(self.maskOptionsChanged)
        self.opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(50)
        self.opacity.valueChanged.connect(self.maskOptionsChanged)
        self.color_by = QtWidgets.QComboBox()
        for label, _ in COLOR_BY:
            self.color_by.addItem(label)
        self.color_by.currentIndexChanged.connect(
            lambda i: self.colorByChanged.emit(COLOR_BY[i][1]))
        mf.addRow(self.show_masks)
        mf.addRow(self.outline)
        mf.addRow("Opacity", self.opacity)
        mf.addRow("Colour by", self.color_by)
        outer.addWidget(mask_box)

        ov_box = QtWidgets.QGroupBox("Overlays")
        ovl = QtWidgets.QVBoxLayout(ov_box)
        self.ov = {}
        for key, label, default in OVERLAYS:
            cb = QtWidgets.QCheckBox(label)
            cb.setChecked(default)
            cb.toggled.connect(lambda on, k=key: self.overlayToggled.emit(k, on))
            self.ov[key] = cb
            ovl.addWidget(cb)
        outer.addWidget(ov_box)
        outer.addStretch(1)

    # -- populate / accessors -------------------------------------------
    def set_recordings(self, entries):
        self.recording.blockSignals(True)
        self.recording.clear()
        for e in entries:
            tag = f"{e.condition}/{e.label}" if e.condition else e.label
            self.recording.addItem(tag)
        self.recording.blockSignals(False)

    def set_channels(self, names):
        self.channel.blockSignals(True)
        self.channel.clear()
        self.channel.addItems(list(names))
        self.channel.blockSignals(False)
        for cb in self._chan_checks:
            cb.setParent(None)
            cb.deleteLater()
        self._chan_checks = []
        for i, n in enumerate(names):
            cb = QtWidgets.QCheckBox(n or f"ch{i}")
            cb.setChecked((n or "").strip().lower() not in ("none", ""))
            cb.toggled.connect(self.displayModeChanged)
            self._comp_layout.addWidget(cb)
            self._chan_checks.append(cb)

    def current_channel(self) -> int:
        return max(self.channel.currentIndex(), 0)

    def color_by_mode(self) -> str:
        return COLOR_BY[max(self.color_by.currentIndex(), 0)][1]

    def composite_on(self) -> bool:
        return self.composite.isChecked()

    def visible_channels(self) -> list:
        on = [i for i, cb in enumerate(self._chan_checks) if cb.isChecked()]
        return on or [self.current_channel()]

    def _composite_toggled(self, on):
        self.comp_box.setEnabled(on)
        self.displayModeChanged.emit()

    @property
    def opacity_value(self) -> float:
        return self.opacity.value() / 100.0
