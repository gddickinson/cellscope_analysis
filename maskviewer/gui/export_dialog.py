"""CSV export dialog — write per-frame / per-cell / track tables for Origin.

Pick which tables, an output folder and a filename prefix; the export runs on a
worker QThread (with a progress bar + Cancel) so the UI stays responsive on
full-size 2048² stacks. Tidy CSVs with units in the headers, via
`analysis.exporters`.
"""
from __future__ import annotations

import os

from PyQt5 import QtCore, QtWidgets

from ..analysis import exporters

_TABLES = [
    ("per_frame", "Per-frame region properties  (one row per cell × frame)", True),
    ("per_cell", "Per-cell summary  (track + shape + motion metrics)", True),
    ("tracks", "Centroid trajectories  (long format, px + µm)", True),
    ("contact_pairs", "Cell-pair contacts  (which cells touch, when, degree)", False),
]


class _Cancelled(Exception):
    pass


class _ExportWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)

    def __init__(self, kw):
        super().__init__()
        self._kw = kw
        self.cancel = False

    def _cb(self, d, t):
        if self.cancel:
            raise _Cancelled()
        self.progress.emit(d, t)

    def run(self):
        try:
            paths = exporters.export_all(progress_cb=self._cb, **self._kw)
        except _Cancelled:
            self.error.emit("Cancelled.")
        except Exception as exc:                        # surface, don't crash
            self.error.emit(str(exc))
        else:
            self.done.emit(paths)


class CSVExportDialog(QtWidgets.QDialog):
    def __init__(self, labels, um_per_px, dt_min, out_dir, prefix, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export CSV (tracks / masks / cell properties)")
        self.labels = labels
        self.um_per_px = um_per_px
        self.dt_min = dt_min
        self._thread = None
        self._worker = None

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Tables to export:"))
        self.cb = {}
        for key, label, default in _TABLES:
            box = QtWidgets.QCheckBox(label)
            box.setChecked(default)
            self.cb[key] = box
            lay.addWidget(box)
        self.solidity = QtWidgets.QCheckBox(
            "Include solidity (convex hull per cell — slower)")
        lay.addWidget(self.solidity)
        self.edge = QtWidgets.QCheckBox(
            "Include edge dynamics in per-cell  (protrusion/retraction — slow)")
        lay.addWidget(self.edge)

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
        grid.addRow("Filename prefix", self.prefix_edit)
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
        which = [k for k, b in self.cb.items() if b.isChecked()]
        if not which:
            QtWidgets.QMessageBox.warning(self, "Nothing selected",
                                          "Tick at least one table to export.")
            return
        kw = dict(labels=self.labels, um_per_px=self.um_per_px, dt_min=self.dt_min,
                  out_dir=self.dir_edit.text() or ".", prefix=self.prefix_edit.text(),
                  which=tuple(which), with_solidity=self.solidity.isChecked(),
                  with_edge=self.edge.isChecked())
        self._save_btn().setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()

        self._thread = QtCore.QThread(self)
        self._worker = _ExportWorker(kw)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._thread.start()

    def _on_progress(self, d, t):
        self.progress.setValue(int(100 * d / t) if t else 0)

    def _on_done(self, paths):
        self._stop_thread()
        QtWidgets.QMessageBox.information(
            self, "Export complete",
            "Wrote:\n" + "\n".join(os.path.basename(p) for p in paths.values())
            + f"\n\nin {self.dir_edit.text()}")
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
            self._worker.cancel = True                  # cooperative cancel
        else:
            self.reject()

    def _stop_thread(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
