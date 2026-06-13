"""Main viewer window: recording + mask overlay browser.

Owns the data (the discovered `Entry` list, the currently loaded recording
+ masks) and wires the `ControlPanel` to the `ImageCanvas`. Recordings load
lazily on selection; per-channel display levels are cached for contrast.
Arrow keys step through frames for quick review.
"""
from __future__ import annotations

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

from .image_view import ImageCanvas
from .controls import ControlPanel
from ..analysis import label_stats


class ViewerWindow(QtWidgets.QMainWindow):
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("cellscope_analysis — recording + mask viewer")
        self.resize(1100, 800)
        self.entries = list(entries)
        self.recording = None
        self.masks = None
        self._levels: dict[int, tuple] = {}

        self.canvas = ImageCanvas()
        self.controls = ControlPanel()
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.addWidget(self.canvas)
        panel = QtWidgets.QWidget()
        pl = QtWidgets.QVBoxLayout(panel)
        pl.addWidget(self.controls)
        pl.addStretch(1)
        split.addWidget(panel)
        split.setStretchFactor(0, 1)
        split.setSizes([850, 250])
        self.setCentralWidget(split)
        self.status = self.statusBar()
        self._hover_cell = 0

        self.controls.recordingChanged.connect(self._load_entry)
        self.controls.channelChanged.connect(lambda _i: self._update_display(reset=True))
        self.controls.frameChanged.connect(lambda _i: self._update_display())
        self.controls.overlayChanged.connect(self._update_overlay)
        self.canvas.cellHovered.connect(self._on_hover)
        for key, step in ((QtCore.Qt.Key_Left, -1), (QtCore.Qt.Key_Right, +1)):
            sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
            sc.activated.connect(lambda s=step: self._step_frame(s))

        self.controls.set_recordings(self.entries)
        if self.entries:
            self._load_entry(0)

    # -- loading ---------------------------------------------------------
    def _load_entry(self, idx: int):
        if not (0 <= idx < len(self.entries)):
            return
        entry = self.entries[idx]
        try:
            self.recording = entry.load_recording()
            self.masks = entry.load_masks()
        except Exception as exc:                       # surface, don't crash
            self.status.showMessage(f"Load failed: {exc}", 8000)
            self.recording = self.masks = None
            return
        self._levels = {}
        self.controls.set_channels(self.recording.channel_names)
        self.controls.set_frame_range(self.recording.n_frames)
        self.canvas.set_label_lut(self.masks.max_label if self.masks else 1)
        self._update_display(reset=True)
        self.canvas.autorange()

    def _channel_levels(self, ch: int):
        if ch not in self._levels:
            t = self.recording.n_frames // 2
            f = self.recording.frame(t, ch).astype(np.float32)
            lo, hi = np.percentile(f, (1, 99))
            self._levels[ch] = (float(lo), float(hi if hi > lo else lo + 1))
        return self._levels[ch]

    # -- display ---------------------------------------------------------
    def _step_frame(self, step):
        self.controls.frame.setValue(self.controls.frame.value() + step)

    def _update_display(self, reset: bool = False):
        if self.recording is None:
            return
        t = self.controls.frame.value()
        ch = max(self.controls.channel.currentIndex(), 0)
        self.canvas.set_base(self.recording.frame(t, ch), self._channel_levels(ch))
        self._update_overlay()

    def _update_overlay(self):
        if self.recording is None:
            return
        t = self.controls.frame.value()
        lab = self.masks.frame(t) if self.masks else None
        self.canvas.set_overlay(lab, opacity=self.controls.opacity_value,
                                outline=self.controls.outline.isChecked(),
                                visible=self.controls.show_masks.isChecked())
        self._update_status(t, lab)

    def _update_status(self, t, lab):
        r = self.recording
        bits = [f"frame {t+1}/{r.n_frames}"]
        if r.time_interval_min:
            bits.append(f"t={t * r.time_interval_min:.0f} min")
        if r.um_per_px:
            bits.append(f"{r.um_per_px:.4f} µm/px")
        if lab is not None:
            bits.append(f"{int((np.unique(lab) > 0).sum())} cells")
        if self._hover_cell:
            bits.append(f"cursor → cell {self._hover_cell}")
        self.status.showMessage("   |   ".join(bits))

    def _on_hover(self, cid: int):
        self._hover_cell = cid
        self._update_status(self.controls.frame.value(),
                            self.masks.frame(self.controls.frame.value())
                            if self.masks else None)
