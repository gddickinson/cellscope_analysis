"""The control panel: recording picker, channel, frame scrubber, overlay.

A plain QWidget of controls that emits Qt signals; `ViewerWindow` owns the
data and reacts. Kept free of any IO/array logic so it stays small and
reusable.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets


class ControlPanel(QtWidgets.QWidget):
    recordingChanged = QtCore.pyqtSignal(int)     # index into the entry list
    channelChanged = QtCore.pyqtSignal(int)
    frameChanged = QtCore.pyqtSignal(int)
    overlayChanged = QtCore.pyqtSignal()          # opacity / show / outline

    def __init__(self, parent=None):
        super().__init__(parent)
        form = QtWidgets.QFormLayout(self)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self.recording = QtWidgets.QComboBox()
        self.recording.currentIndexChanged.connect(self.recordingChanged)
        form.addRow("Recording", self.recording)

        self.channel = QtWidgets.QComboBox()
        self.channel.currentIndexChanged.connect(self.channelChanged)
        form.addRow("Channel", self.channel)

        # frame slider + spinbox kept in sync
        self.frame = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.frame.setMinimum(0)
        self.frame_spin = QtWidgets.QSpinBox()
        self.frame.valueChanged.connect(self._sync_from_slider)
        self.frame_spin.valueChanged.connect(self._sync_from_spin)
        frow = QtWidgets.QHBoxLayout()
        frow.addWidget(self.frame, 1)
        frow.addWidget(self.frame_spin)
        fwrap = QtWidgets.QWidget()
        fwrap.setLayout(frow)
        form.addRow("Frame", fwrap)

        self.show_masks = QtWidgets.QCheckBox("Show masks")
        self.show_masks.setChecked(True)
        self.show_masks.toggled.connect(self.overlayChanged)
        form.addRow(self.show_masks)

        self.outline = QtWidgets.QCheckBox("Outlines only")
        self.outline.toggled.connect(self.overlayChanged)
        form.addRow(self.outline)

        self.opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(50)
        self.opacity.valueChanged.connect(self.overlayChanged)
        form.addRow("Opacity", self.opacity)

    # -- populate --------------------------------------------------------
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

    def set_frame_range(self, n_frames):
        n = max(int(n_frames) - 1, 0)
        for w in (self.frame, self.frame_spin):
            w.blockSignals(True)
            w.setMaximum(n)
            w.setValue(0)
            w.blockSignals(False)

    # -- accessors -------------------------------------------------------
    @property
    def opacity_value(self) -> float:
        return self.opacity.value() / 100.0

    # -- internal --------------------------------------------------------
    def _sync_from_slider(self, v):
        self.frame_spin.blockSignals(True)
        self.frame_spin.setValue(v)
        self.frame_spin.blockSignals(False)
        self.frameChanged.emit(v)

    def _sync_from_spin(self, v):
        self.frame.blockSignals(True)
        self.frame.setValue(v)
        self.frame.blockSignals(False)
        self.frameChanged.emit(v)
