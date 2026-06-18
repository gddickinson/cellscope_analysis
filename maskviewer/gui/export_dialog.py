"""CSV export dialog — write per-frame / per-cell / track tables for Origin.

Pick which tables, **which per-frame columns**, the **scope** (the current recording or
every recording in the project — as separate files or one combined file with
`recording` + `condition` columns), an output folder and a filename prefix. The export
runs on a worker QThread (progress bar + Cancel) so the UI stays responsive on full
2048² stacks. Tidy CSVs with units in the headers, via `analysis.exporters`.
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
_CONTACT_PREFIXES = ("n_contacts", "contact", "max_contact")


def _categorize(cols):
    groups = {"Coordinates": [], "Size": [], "Shape": [], "State & flags": [],
              "Neighbours & contact": [], "Other": []}
    for c in cols:
        if c.startswith(("centroid", "bbox")):
            g = "Coordinates"
        elif c.startswith(("area", "perimeter", "major_axis", "minor_axis",
                           "equiv_diameter")):
            g = "Size"
        elif c in ("eccentricity", "aspect_ratio", "orientation_rad", "extent",
                   "solidity", "circularity", "convexity"):
            g = "Shape"
        elif c in ("state", "edge"):
            g = "State & flags"
        elif c.startswith(("nn_dist", "n_neighbors") + _CONTACT_PREFIXES):
            g = "Neighbours & contact"
        else:
            g = "Other"
        groups[g].append(c)
    return {k: v for k, v in groups.items() if v}


class _Cancelled(Exception):
    pass


class _ExportWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)

    def __init__(self, jobs):
        super().__init__()
        self._jobs = jobs                               # [(fn, kw), …] run in sequence
        self.cancel = False

    def run(self):
        try:
            paths, n = {}, len(self._jobs)
            for i, (fn, kw) in enumerate(self._jobs):
                def cb(d, t, i=i):
                    if self.cancel:
                        raise _Cancelled()
                    self.progress.emit(int(100 * (i + (d / t if t else 1.0)) / n), 100)
                paths.update(fn(progress_cb=cb, **kw))
        except _Cancelled:
            self.error.emit("Cancelled.")
        except Exception as exc:                        # surface, don't crash
            self.error.emit(str(exc))
        else:
            self.done.emit(paths)


class CSVExportDialog(QtWidgets.QDialog):
    _GROUPS = ["recording", "combined", "condition"]

    def __init__(self, labels, um_per_px, dt_min, out_dir, prefix, parent=None,
                 project=None, current_label="", current_condition=""):
        super().__init__(parent)
        self.setWindowTitle("Export CSV (tracks / masks / cell properties)")
        self.labels = labels
        self.um_per_px = um_per_px
        self.dt_min = dt_min
        self.project = project
        self.current_label = current_label
        self.current_condition = current_condition
        self._thread = self._worker = None

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self._scope_box())
        lay.addWidget(QtWidgets.QLabel("<b>Tables to export</b>"))
        self.cb = {}
        for key, label, default in _TABLES:
            box = QtWidgets.QCheckBox(label)
            box.setChecked(default)
            self.cb[key] = box
            lay.addWidget(box)
        lay.addWidget(self._columns_box())
        self.solidity = QtWidgets.QCheckBox("Compute solidity (convex hull — slower)")
        self.edge = QtWidgets.QCheckBox(
            "Include edge dynamics in per-cell  (protrusion/retraction — slow)")
        lay.addWidget(self.solidity)
        lay.addWidget(self.edge)
        lay.addLayout(self._dest_form(out_dir, prefix))

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._start)
        self.buttons.rejected.connect(self._cancel_or_close)
        lay.addWidget(self.buttons)

    # -- UI builders -----------------------------------------------------
    def _scope_box(self):
        box = QtWidgets.QGroupBox("Scope && grouping")
        v = QtWidgets.QVBoxLayout(box)
        self.scope_current = QtWidgets.QRadioButton("Current recording")
        n = len(self.project.entries) if self.project else 0
        self.scope_all = QtWidgets.QRadioButton(f"All recordings in project ({n})")
        self.scope_current.setChecked(True)
        self.scope_all.setEnabled(bool(self.project and n))
        v.addWidget(self.scope_current)
        v.addWidget(self.scope_all)
        grow = QtWidgets.QHBoxLayout()
        grow.addWidget(QtWidgets.QLabel("When “all”, write:"))
        self.group = QtWidgets.QComboBox()
        self.group.addItems(["Separate file per recording", "One combined file",
                             "One file per condition"])
        self.group.setCurrentIndex(2)                    # default: per condition
        self.group.setEnabled(False)
        self.scope_all.toggled.connect(self.group.setEnabled)
        grow.addWidget(self.group, 1)
        v.addLayout(grow)
        self.diper = QtWidgets.QCheckBox(
            "Also export DiPer-ready trajectories  (cols frame, x, y for diper_clone)")
        self.diper.setToolTip(
            "Trajectory coordinates in the diper_clone column layout (cols 4/5/6 = "
            "frame, x, y; frame resets per cell). Honours the grouping above — one CSV "
            "per recording / combined / per condition (each condition file = one DiPer "
            "group); current-recording scope → one file.")
        v.addWidget(self.diper)
        return box

    def _columns_box(self):
        box = QtWidgets.QGroupBox("Per-frame columns")
        v = QtWidgets.QVBoxLayout(box)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("cell_id, frame, time always included."))
        row.addStretch(1)
        for txt, on in (("All", True), ("None", False)):
            b = QtWidgets.QPushButton(txt)
            b.clicked.connect(lambda _c, s=on: self._set_all_columns(s))
            row.addWidget(b)
        v.addLayout(row)
        self.col_cb = {}
        host = QtWidgets.QWidget()
        hv = QtWidgets.QVBoxLayout(host)
        hv.setContentsMargins(0, 0, 0, 0)
        for group, cols in _categorize(self._discover_columns()).items():
            hv.addWidget(QtWidgets.QLabel(f"<b>{group}</b>"))
            grid = QtWidgets.QGridLayout()
            for i, c in enumerate(cols):
                cb = QtWidgets.QCheckBox(c)
                cb.setChecked(True)
                self.col_cb[c] = cb
                grid.addWidget(cb, i // 3, i % 3)
            hv.addLayout(grid)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(host)
        scroll.setMaximumHeight(190)
        v.addWidget(scroll)
        return box

    def _dest_form(self, out_dir, prefix):
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
        return grid

    # -- helpers ---------------------------------------------------------
    def _discover_columns(self):
        """Actual per-frame columns (built from the first frame, solidity+contacts on)."""
        try:
            df = exporters.per_frame_table(self.labels[:1], self.um_per_px, self.dt_min,
                                           with_solidity=True, with_contacts=True)
            ident = set(exporters._PF_IDENTITY)
            return [c for c in df.columns if c not in ident]
        except Exception:
            return []

    def _set_all_columns(self, on):
        for cb in self.col_cb.values():
            cb.setChecked(on)

    def _selected_columns(self):
        return [c for c, cb in self.col_cb.items() if cb.isChecked()]

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
        diper = self.diper.isChecked()
        if not which and not diper:
            QtWidgets.QMessageBox.warning(self, "Nothing selected",
                                          "Tick at least one table (or DiPer) to export.")
            return
        cols = self._selected_columns()
        out_dir = self.dir_edit.text() or "."
        all_scope = self.scope_all.isChecked() and self.project is not None
        group = self._GROUPS[self.group.currentIndex()]
        proj_kw = (dict(scale_override=self.project.scale_override,
                        corrections=self.project.corrections,
                        excluded=self.project.excluded) if all_scope else {})
        jobs = []
        if which:
            common = dict(which=tuple(which), columns=cols,
                          with_solidity=self.solidity.isChecked() or "solidity" in cols,
                          with_edge=self.edge.isChecked(),
                          with_contacts=any(c.startswith(_CONTACT_PREFIXES) for c in cols))
            if all_scope:
                jobs.append((exporters.export_project,
                             dict(entries=self.project.entries, out_dir=out_dir,
                                  group=group, **proj_kw, **common)))
            else:
                jobs.append((exporters.export_all,
                             dict(labels=self.labels, um_per_px=self.um_per_px,
                                  dt_min=self.dt_min, out_dir=out_dir,
                                  prefix=self.prefix_edit.text(), **common)))
        if diper:
            if all_scope:
                jobs.append((exporters.export_diper,
                             dict(entries=self.project.entries, out_dir=out_dir,
                                  group=group, **proj_kw)))
            else:
                jobs.append((exporters.export_diper_one,
                             dict(labels=self.labels, um_per_px=self.um_per_px,
                                  dt_min=self.dt_min, out_dir=out_dir,
                                  label=self.current_label or "recording",
                                  condition=self.current_condition)))

        self._save_btn().setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self._thread = QtCore.QThread(self)
        self._worker = _ExportWorker(jobs)
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
        names = [os.path.basename(p) for p in paths.values()]
        shown = names[:12] + ([f"…(+{len(names) - 12} more)"] if len(names) > 12 else [])
        QtWidgets.QMessageBox.information(
            self, "Export complete",
            f"Wrote {len(names)} file(s) in {self.dir_edit.text()}:\n" + "\n".join(shown))
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
