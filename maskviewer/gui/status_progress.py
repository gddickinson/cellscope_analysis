"""A compact progress widget for a status bar: label + bar + elapsed/ETA.

Embed one per window via ``statusBar().addPermanentWidget(StatusProgress())``.
`start(text)` begins (busy/indeterminate until the first `update`),
`update(done, total)` shows a % bar + an ETA estimated from elapsed time, and
`finish()` shows the total time then auto-hides. Pure Qt, GUI-thread only.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets


def fmt_secs(secs):
    """Human time: '8s', '1m20s'."""
    secs = max(0.0, float(secs))
    if secs < 60:
        return f"{secs:.0f}s"
    m, s = divmod(int(round(secs)), 60)
    return f"{m}m{s:02d}s"


class StatusProgress(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QtCore.QElapsedTimer()
        self._gen = 0                      # invalidate stale auto-hide timers
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.label = QtWidgets.QLabel("")
        self.bar = QtWidgets.QProgressBar()
        self.bar.setMaximumWidth(170)
        self.bar.setMaximumHeight(14)
        self.bar.setTextVisible(True)
        self.eta = QtWidgets.QLabel("")
        self.eta.setMinimumWidth(120)
        for w in (self.label, self.bar, self.eta):
            lay.addWidget(w)
        self.setVisible(False)

    def start(self, text="Working…"):
        self._gen += 1
        self.label.setText(text)
        self.bar.setRange(0, 0)            # busy until the first update()
        self.bar.setValue(0)
        self.eta.setText("")
        self._timer.restart()
        self.setVisible(True)

    def update(self, done, total):
        done, total = int(done), int(total)
        if total <= 0:
            return
        self.bar.setRange(0, total)
        self.bar.setValue(min(done, total))
        el = self._timer.elapsed() / 1000.0
        if 0 < done < total:
            remain = el * (total - done) / done
            self.eta.setText(f"{fmt_secs(el)} elapsed · ~{fmt_secs(remain)} left")
        else:
            self.eta.setText(f"{fmt_secs(el)} elapsed")

    def finish(self, text=None):
        el = self._timer.elapsed() / 1000.0
        self.bar.setRange(0, 1)
        self.bar.setValue(1)
        base = self.label.text().rstrip(" …")
        self.label.setText(text or f"{base} — done")
        self.eta.setText(f"in {fmt_secs(el)}")
        gen = self._gen
        QtCore.QTimer.singleShot(
            2000, lambda: self.setVisible(False) if gen == self._gen else None)

    def fail(self, text="failed"):
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.label.setText(text)
        self.eta.setText("")
        gen = self._gen
        QtCore.QTimer.singleShot(
            3000, lambda: self.setVisible(False) if gen == self._gen else None)
