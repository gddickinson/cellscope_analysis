"""Export Masks dialog — write the label stack to TIFF / PNG / NumPy for other
viewers (Fiji/ImageJ, napari, QuPath, …). Pick a format, scope (current recording or the
whole project), and options; the write runs on a worker QThread (progress + Cancel).
Backed by `analysis.mask_export`. `open_mask_export(win)` is a free function so it adds
nothing to `window_actions` (which is at its size limit).
"""
from __future__ import annotations

import os

from PyQt5 import QtCore, QtWidgets

from ..analysis import mask_export
from ..config import PROJECT_ROOT


class _Cancelled(Exception):
    pass


class _MaskWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(int)
    error = QtCore.pyqtSignal(str)

    def __init__(self, fn, kw):
        super().__init__()
        self._fn, self._kw = fn, kw
        self.cancel = False

    def _cb(self, d, t):
        if self.cancel:
            raise _Cancelled()
        self.progress.emit(d, t)

    def run(self):
        try:
            res = self._fn(progress_cb=self._cb, **self._kw)
            n = (sum(len(v) for v in res.values()) if isinstance(res, dict)
                 else len(res))                       # files written
        except _Cancelled:
            self.error.emit("Cancelled.")
        except Exception as exc:                       # surface, don't crash
            self.error.emit(str(exc))
        else:
            self.done.emit(n)


class MaskExportDialog(QtWidgets.QDialog):
    def __init__(self, labels, um_per_px, dt_min, out_dir, prefix, parent=None,
                 project=None):
        super().__init__(parent)
        self.setWindowTitle("Export Masks (TIFF / PNG / NumPy)")
        self.labels = labels
        self.um_per_px = um_per_px
        self.dt_min = dt_min
        self.project = project
        self._thread = self._worker = None

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(_wrap("Export the label masks for other software. <b>0</b> = "
                            "background; positive integers are tracked cell IDs "
                            "(preserved exactly — these are label images, not renders). "
                            "Bit depth is chosen automatically (8/16/32-bit)."))
        form = QtWidgets.QFormLayout()
        self.fmt = QtWidgets.QComboBox()
        for key, label, _seq in mask_export.FORMATS:
            self.fmt.addItem(label, key)
        form.addRow("Format", self.fmt)
        lay.addLayout(form)

        self.scope_current = QtWidgets.QRadioButton("Current recording")
        n = len(self.project.entries) if self.project else 0
        self.scope_all = QtWidgets.QRadioButton(f"All recordings in project ({n})")
        self.scope_current.setChecked(True)
        self.scope_all.setEnabled(bool(self.project and n))
        lay.addWidget(self.scope_current)
        lay.addWidget(self.scope_all)
        self.relabel = QtWidgets.QCheckBox(
            "Relabel IDs to consecutive 1..N (some tools expect dense labels)")
        lay.addWidget(self.relabel)

        grid = QtWidgets.QFormLayout()
        self.dir_edit = QtWidgets.QLineEdit(out_dir)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        drow = QtWidgets.QHBoxLayout()
        drow.addWidget(self.dir_edit, 1)
        drow.addWidget(browse)
        dw = QtWidgets.QWidget()
        dw.setLayout(drow)
        self.prefix_edit = QtWidgets.QLineEdit(prefix)
        grid.addRow("Folder", dw)
        grid.addRow("Filename prefix (current-recording only)", self.prefix_edit)
        lay.addLayout(grid)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._start)
        self.buttons.rejected.connect(self._cancel_or_close)
        lay.addWidget(self.buttons)

    # -- helpers ---------------------------------------------------------
    def _browse(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Export folder", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def _save_btn(self):
        return self.buttons.button(QtWidgets.QDialogButtonBox.Save)

    # -- run -------------------------------------------------------------
    def _start(self):
        fmt = self.fmt.currentData()
        out_dir = self.dir_edit.text() or "."
        if self.scope_all.isChecked() and self.project is not None:
            fn = mask_export.export_masks_project
            kw = dict(entries=self.project.entries, fmt=fmt, out_dir=out_dir,
                      relabel=self.relabel.isChecked(),
                      scale_override=self.project.scale_override,
                      corrections=self.project.corrections,
                      excluded=self.project.excluded)
        else:
            fn = mask_export.export_masks
            kw = dict(labels=self.labels, fmt=fmt, out_dir=out_dir,
                      prefix=self.prefix_edit.text(), um_per_px=self.um_per_px,
                      dt_min=self.dt_min, relabel=self.relabel.isChecked())
        self._save_btn().setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self._thread = QtCore.QThread(self)
        self._worker = _MaskWorker(fn, kw)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, d, t):
        self.progress.setValue(int(100 * d / t) if t else 0)

    def _on_done(self, n):
        self._stop_thread()
        QtWidgets.QMessageBox.information(
            self, "Export complete", f"Wrote {n} mask file(s) to {self.dir_edit.text()}")
        self.accept()

    def _on_error(self, msg):
        self._stop_thread()
        self.progress.hide()
        self._save_btn().setEnabled(True)
        if msg != "Cancelled.":
            QtWidgets.QMessageBox.critical(self, "Export failed", msg)

    def _cancel_or_close(self):
        if self._worker is not None and self._thread is not None \
                and self._thread.isRunning():
            self._worker.cancel = True
        else:
            self.reject()

    def _stop_thread(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None


def _wrap(text):
    lab = QtWidgets.QLabel(text)
    lab.setWordWrap(True)
    return lab


def open_mask_export(win):
    """File ▸ Export Masks… — open the dialog for the current recording's masks."""
    if getattr(win, "masks", None) is None or getattr(win, "recording", None) is None:
        QtWidgets.QMessageBox.information(
            win, "No masks", "This recording has no masks to export.")
        return
    idx = max(win.display.recording.currentIndex(), 0)
    label = win.entries[idx].label if win.entries else "masks"
    MaskExportDialog(win.masks.labels, win.recording.um_per_px,
                     win.recording.time_interval_min,
                     os.path.join(PROJECT_ROOT, "analysis_out"), f"{label}_",
                     win, project=win.project).exec_()
