"""Include / Exclude recordings — a dual-list dialog acting on the loaded Project.

`IncludeExcludeDialog` shows every recording in the project in two lists —
**Included** (loaded in the session) and **Excluded** (removed from the session
and from all analysis) — and lets the user move recordings between them (arrow
buttons or double-click, multi-select). On OK the new excluded set is applied to
the session via `apply_inclusion`, which:

  * stores it on the project (`Project.excluded`, saved with the project),
  * rebuilds the recording dropdown to show only included recordings (so the
    excluded ones are *removed from the session*), and
  * loads the first included recording if the one on screen was excluded.

Non-destructive: only the project's `excluded` set changes — files are untouched.
`manage_inclusion(win)` / `apply_inclusion(win, excluded)` are free functions
(not window methods) to keep `window_actions` / `viewer_window` under their size
limits; they read only public window attributes.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets


def _tag(entry):
    return f"{entry.condition}/{entry.label}" if entry.condition else entry.label


class IncludeExcludeDialog(QtWidgets.QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("Include / Exclude Recordings")
        self.resize(640, 470)
        self._build()
        self._populate()
        self._update_counts()

    # -- UI -------------------------------------------------------------
    def _build(self):
        lay = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Move recordings between <b>Included</b> (loaded in the session + used "
            "in all analysis) and <b>Excluded</b> (removed from the session). "
            "Double-click an item or use the arrows; select several at once. Changes "
            "apply on <b>OK</b>; <b>Save Project</b> (Ctrl+S) writes them to the "
            "project file. Files on disk are never modified.")
        info.setWordWrap(True)
        lay.addWidget(info)

        row = QtWidgets.QHBoxLayout()
        lay.addLayout(row, 1)
        self.inc = self._make_list()
        self.exc = self._make_list()
        row.addLayout(self._column("Included (in session)", self.inc), 1)

        mid = QtWidgets.QVBoxLayout()
        mid.addStretch(1)
        self.btn_exc = QtWidgets.QPushButton("Exclude →")
        self.btn_inc = QtWidgets.QPushButton("← Include")
        self.btn_exc_all = QtWidgets.QPushButton("Exclude all")
        self.btn_inc_all = QtWidgets.QPushButton("Include all")
        self.btn_exc.clicked.connect(lambda: self._move_selected(self.inc, self.exc))
        self.btn_inc.clicked.connect(lambda: self._move_selected(self.exc, self.inc))
        self.btn_exc_all.clicked.connect(lambda: self._move_all(self.inc, self.exc))
        self.btn_inc_all.clicked.connect(lambda: self._move_all(self.exc, self.inc))
        for b in (self.btn_exc, self.btn_inc, self.btn_exc_all, self.btn_inc_all):
            mid.addWidget(b)
        mid.addStretch(1)
        row.addLayout(mid)
        row.addLayout(self._column("Excluded", self.exc), 1)

        self.inc.itemDoubleClicked.connect(
            lambda it: self._move_item(it, self.inc, self.exc))
        self.exc.itemDoubleClicked.connect(
            lambda it: self._move_item(it, self.exc, self.inc))

        self.count = QtWidgets.QLabel()
        lay.addWidget(self.count)
        self.bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)
        lay.addWidget(self.bb)

    @staticmethod
    def _make_list():
        w = QtWidgets.QListWidget()
        w.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        w.setSortingEnabled(True)
        return w

    @staticmethod
    def _column(title, listw):
        col = QtWidgets.QVBoxLayout()
        col.addWidget(QtWidgets.QLabel(f"<b>{title}</b>"))
        col.addWidget(listw)
        return col

    # -- data -----------------------------------------------------------
    def _populate(self):
        for e in self.project.entries:
            it = QtWidgets.QListWidgetItem(_tag(e))
            it.setData(QtCore.Qt.UserRole, e.label)
            (self.exc if e.label in self.project.excluded else self.inc).addItem(it)

    def _move_item(self, item, src, dst):
        dst.addItem(src.takeItem(src.row(item)))
        self._update_counts()

    def _move_selected(self, src, dst):
        for item in src.selectedItems():
            dst.addItem(src.takeItem(src.row(item)))
        self._update_counts()

    def _move_all(self, src, dst):
        while src.count():
            dst.addItem(src.takeItem(0))
        self._update_counts()

    def _update_counts(self):
        self.count.setText(
            f"{self.inc.count()} included · {self.exc.count()} excluded "
            f"(of {self.inc.count() + self.exc.count()})")
        ok = self.bb.button(QtWidgets.QDialogButtonBox.Ok)
        ok.setEnabled(self.inc.count() > 0)            # keep at least one recording
        ok.setToolTip("" if self.inc.count() else "Keep at least one recording included.")

    def excluded_labels(self):
        """The set of labels now in the Excluded list."""
        return {self.exc.item(i).data(QtCore.Qt.UserRole) for i in range(self.exc.count())}


# ---------------------------------------------------------- session wiring
def _current_label(win):
    ci = win.display.recording.currentIndex()
    if 0 <= ci < len(win.entries):
        return win.entries[ci].label
    return None


def manage_inclusion(win):
    """File ▸ Include / Exclude Recordings… — open the dialog and apply the result."""
    if not win.project.entries:
        QtWidgets.QMessageBox.information(
            win, "No project",
            "Open a project (File ▸ Open Project Folder / File) first.")
        return
    dlg = IncludeExcludeDialog(win.project, win)
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        apply_inclusion(win, dlg.excluded_labels())


def apply_inclusion(win, excluded, notify_compare=True):
    """Adopt a new excluded set and refresh the session: the dropdown shows only
    included recordings; if the one on screen was excluded, load the first
    included one (the current recording is kept — no reload — if still included).

    ``notify_compare`` pushes the change into an open Comparison window (refresh its
    Groups editor + replot); set False when the change *came from* that window, to
    avoid an echo loop."""
    excluded = set(excluded)
    cur = _current_label(win)                          # before we rebuild win.entries
    win.project.excluded = excluded
    win.entries = list(win.project.included_entries())
    win.display.set_recordings(win.entries)            # signals blocked inside
    combo = win.display.recording
    if not win.entries:                                # degenerate (dialog forbids it)
        win.recording = win.masks = None
        win.statusBar().showMessage("All recordings excluded — none loaded.", 8000)
    else:
        keep = next((i for i, e in enumerate(win.entries) if e.label == cur), None)
        combo.blockSignals(True)
        combo.setCurrentIndex(keep if keep is not None else 0)
        combo.blockSignals(False)
        if keep is None:                               # current was excluded → load anew
            win._load_entry(0)
        win.statusBar().showMessage(
            f"Session: {len(win.entries)} recording(s) included, {len(excluded)} "
            f"excluded. Save Project (Ctrl+S) to keep this.", 6000)
    if notify_compare:                                 # push into an open Comparison window
        cw = getattr(win, "_compare_window", None)
        if cw is not None:
            if cw._design_editor is not None:          # refresh its include checkboxes
                cw._design_editor.set_data(cw._per_cell)
            cw._on_design_changed()                    # remap + replot (echo is idempotent)
