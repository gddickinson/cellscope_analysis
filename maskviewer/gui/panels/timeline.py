"""Timeline panel — the frame scrubber, shown as a bar below the view.

Play/pause (QTimer-driven), a frame slider + spinbox kept in sync, an fps
control, a loop toggle and a frame/time readout. Emits `frameChanged(int)`;
the viewer owns the data and re-renders. Lives in the bottom dock so the time
bar sits under the image (and is still detachable like every other panel).
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets


class TimelinePanel(QtWidgets.QWidget):
    frameChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dt_min = None
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.play_btn = QtWidgets.QToolButton()
        self.play_btn.setText("▶")
        self.play_btn.setCheckable(True)
        self.play_btn.setToolTip("Play / pause (Space)")
        self.play_btn.toggled.connect(self._toggle_play)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setToolTip("Scrub frames (← / → to step)")
        self.spin = QtWidgets.QSpinBox()
        self.spin.setToolTip("Frame number")
        self.fps = QtWidgets.QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(10)
        self.fps.setSuffix(" fps")
        self.fps.setToolTip("Playback speed")
        self.loop = QtWidgets.QCheckBox("Loop")
        self.loop.setChecked(True)
        self.loop.setToolTip("Loop back to the start at the end")
        self.label = QtWidgets.QLabel("–")
        self.label.setMinimumWidth(150)

        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.fps.valueChanged.connect(self._apply_fps)

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 2)
        lay.addWidget(self.play_btn)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        lay.addWidget(self.fps)
        lay.addWidget(self.loop)
        lay.addWidget(self.label)

    # -- public ----------------------------------------------------------
    def set_range(self, n_frames: int):
        n = max(int(n_frames) - 1, 0)
        for w in (self.slider, self.spin):
            w.blockSignals(True)
            w.setMaximum(n)
            w.setValue(0)
            w.blockSignals(False)
        self._update_label(0)

    def set_time_interval(self, dt_min):
        self.dt_min = dt_min
        self._update_label(self.value())

    def value(self) -> int:
        return self.slider.value()

    def set_value(self, v: int):
        v = max(0, min(int(v), self.slider.maximum()))
        if v != self.slider.value():
            self.slider.setValue(v)          # → _from_slider → emit
        else:
            self._update_label(v)

    def step(self, d: int):
        self.set_value(self.value() + d)

    def toggle_play(self):
        self.play_btn.setChecked(not self.play_btn.isChecked())

    # -- internal --------------------------------------------------------
    def _from_slider(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self._update_label(v)
        self.frameChanged.emit(v)

    def _from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(v)
        self.slider.blockSignals(False)
        self._update_label(v)
        self.frameChanged.emit(v)

    def _toggle_play(self, on):
        self.play_btn.setText("⏸" if on else "▶")
        if on:
            self._apply_fps()
            self._timer.start()
        else:
            self._timer.stop()

    def _apply_fps(self, *_):
        self._timer.setInterval(int(1000 / max(self.fps.value(), 1)))

    def _tick(self):
        v = self.value()
        if v >= self.slider.maximum():
            if self.loop.isChecked():
                self.set_value(0)
            else:
                self.play_btn.setChecked(False)
        else:
            self.set_value(v + 1)

    def _update_label(self, v):
        n = self.slider.maximum() + 1
        s = f"frame {v + 1}/{n}"
        if self.dt_min:
            s += f"   t={v * self.dt_min:.0f} min"
        self.label.setText(s)
