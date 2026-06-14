"""Menu-action methods for ViewerWindow, split out to keep viewer_window small.

`WindowActionsMixin` provides the File / Window / Help action handlers; it only
uses attributes the ViewerWindow already owns (entries, recording, masks, docks,
display, canvas, _settings, _default_state).
"""
from __future__ import annotations

import os

from PyQt5 import QtCore, QtGui, QtWidgets

from .export_dialog import CSVExportDialog
from ..analysis import metric_docs, population as _population, shape_modes
from ..io.dataset import Entry
from .. import project as projmod
from ..config import PROJECT_ROOT


class WindowActionsMixin:
    # -- File -----------------------------------------------------------
    def open_recording_dialog(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open recording", "", "OME-TIFF (*.ome.tif *.tif)")
        if not fn:
            return
        mask = os.path.join(os.path.dirname(fn), "pipeline_results", "masks.npz")
        if not os.path.exists(mask):
            mn, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Masks for this recording (Cancel for none)",
                os.path.dirname(fn), "NumPy masks (*.npz)")
            mask = mn or None
        self.entries.append(Entry(os.path.splitext(os.path.basename(fn))[0],
                                  "", fn, mask))
        self.display.set_recordings(self.entries)
        self.display.recording.setCurrentIndex(len(self.entries) - 1)

    # -- projects -------------------------------------------------------
    def open_data_root_dialog(self):
        """Open a folder of recordings as a project (auto-derives the design)."""
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Open project folder")
        if not d:
            return
        proj = projmod.from_data_roots(d)
        if not proj.entries:
            QtWidgets.QMessageBox.warning(self, "Nothing found",
                                          "No recordings under that folder.")
            return
        self.set_project(proj)
        self._remember_project(d)

    def open_project_file(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open project file", "", "Project (*.json)")
        if not fn:
            return
        try:
            proj = projmod.load_project(fn)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Open failed", str(exc))
            return
        self.set_project(proj)
        self._remember_project(fn)

    def save_project_as(self):
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save project", f"{self.project.name}.json", "Project (*.json)")
        if not fn:
            return
        projmod.save_project(self.project, fn)
        self._remember_project(fn)
        self.statusBar().showMessage(f"Saved project → {fn}", 5000)

    def _remember_project(self, path):
        recent = [path] + [p for p in self._recent_projects() if p != path]
        self._settings.setValue("recent_projects", recent[:8])
        self._rebuild_recent_menu()

    def _recent_projects(self):
        rec = self._settings.value("recent_projects", [])
        return [rec] if isinstance(rec, str) else list(rec or [])

    def _open_recent(self, path):
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Missing", f"Not found: {path}")
            return
        proj = (projmod.load_project(path) if path.lower().endswith(".json")
                else projmod.from_data_roots(path))
        self.set_project(proj)
        self._remember_project(path)

    def set_project(self, project):
        """Adopt a different project (recordings + experimental design)."""
        self.project = project
        self.entries = list(project.entries)
        self.display.set_recordings(self.entries)
        self.setWindowTitle(f"cellscope_analysis — {project.name}")
        if self._compare_window is not None:
            self._compare_window.set_project(project)
        if self.entries:
            self._load_entry(0)
        else:
            self.statusBar().showMessage("No recordings in this project.", 6000)

    def _rebuild_recent_menu(self):
        menu = getattr(self, "recent_menu", None)
        if menu is None:
            return
        menu.clear()
        recent = self._recent_projects()
        if not recent:
            a = QtWidgets.QAction("(none)", self)
            a.setEnabled(False)
            menu.addAction(a)
            return
        for p in recent:
            act = QtWidgets.QAction(os.path.basename(p.rstrip("/")) or p, self)
            act.setToolTip(p)
            act.triggered.connect(lambda _c, path=p: self._open_recent(path))
            menu.addAction(act)

    # -- heavy-compute providers (lazy + cached; progress_cb → off-thread) --
    def _population_table(self, progress_cb=None):
        """All-cells per-frame table (lazy + cached) — fixed colour scale +
        the Population panel. ``progress_cb`` set → caller runs us off-thread
        (no wait cursor); else block on the GUI thread with a busy cursor."""
        if self._pop_df is None and self.masks is not None:
            sync = progress_cb is None
            if sync:
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                self._pop_df = _population.population_table(
                    self.masks.labels, self.recording.um_per_px,
                    self.recording.time_interval_min, progress_cb=progress_cb)
            finally:
                if sync:
                    QtWidgets.QApplication.restoreOverrideCursor()
        return self._pop_df

    def _shape_modes_model(self, progress_cb=None):
        """VAMPIRE shape-mode model for the recording (lazy + cached)."""
        if self._shape_model is None and self.masks is not None:
            sync = progress_cb is None
            if sync:
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                self._shape_model = shape_modes.fit_shape_modes(
                    self.masks.labels, progress_cb=progress_cb)
            finally:
                if sync:
                    QtWidgets.QApplication.restoreOverrideCursor()
        return self._shape_model

    # -- threaded compute (status-bar progress + ETA) -------------------
    def run_task(self, label, work, apply):
        """Run ``work(progress_cb)`` off-thread with a status-bar bar/ETA, then
        ``apply(result)`` on the GUI thread. Injected into panels as run_async."""
        if self._task.busy:
            self.status.showMessage("Another computation is still running…", 3000)
            return

        def done(result):
            self.busy.finish()
            apply(result)

        def failed(msg):
            self.busy.fail("compute failed")
            self.status.showMessage(f"Compute failed: {msg}", 6000)

        self.busy.start(f"{label}…")
        self._task.run(work, done, failed)

    # -- comparison window ----------------------------------------------
    def open_compare_window(self):
        if self._compare_window is None:
            from .compare_window import CompareWindow
            self._compare_window = CompareWindow(self.project, self)
            self._compare_window.recordingPicked.connect(
                self._select_recording_by_label)
        self._compare_window.show()
        self._compare_window.raise_()

    def export_csv(self):
        if self.masks is None or self.recording is None:
            QtWidgets.QMessageBox.information(
                self, "No masks", "This recording has no masks to export.")
            return
        idx = max(self.display.recording.currentIndex(), 0)
        label = self.entries[idx].label if self.entries else "export"
        CSVExportDialog(self.masks.labels, self.recording.um_per_px,
                        self.recording.time_interval_min,
                        os.path.join(PROJECT_ROOT, "analysis_out"),
                        f"{label}_", self).exec_()

    def save_screenshot(self):
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save image (view only)", "view.png", "PNG (*.png)")
        if fn:
            self.canvas.grab().save(fn)

    def save_window_screenshot(self):
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save window screenshot", "window.png", "PNG (*.png)")
        if fn:
            self.grab().save(fn)

    # -- remote control (MASKVIEWER_REMOTE) -----------------------------
    def remote_state(self):
        return {"recordings": len(self.entries),
                "recording": self.display.recording.currentText(),
                "frame": self.timeline.value(),
                "n_frames": self.recording.n_frames if self.recording else 0,
                "channel": self.display.channel.currentText(),
                "color_by": self.display.color_by_mode(),
                "selected": self.selected,
                "n_cells": self._cur_ncells,
                "docks": list(self.docks)}

    def remote_set(self, q):
        if "recording" in q:
            self.display.recording.setCurrentIndex(int(q["recording"]))
        if "channel" in q:
            self.display.channel.setCurrentIndex(int(q["channel"]))
        if "frame" in q:
            self.timeline.set_value(int(q["frame"]))
        if "color_by" in q:
            self.display.set_color_by(q["color_by"])
        if "composite" in q:
            self.display.composite.setChecked(q["composite"] == "1")
        if "selected" in q:
            self.select_cell(int(q["selected"]))
        return self.remote_state()

    def remote_cmd(self, q):
        action = q.get("action", "")
        if action == "raise" and q.get("dock") in self.docks:
            self.docks[q["dock"]].raise_()
        elif action == "compute_population":
            self.population._compute()
        elif action == "population_kind":
            self.population.kind.setCurrentText(q.get("kind", ""))
        elif action == "compute_shape":
            self.shape._compute()
        elif action == "compute_table":
            self.cell_table._compute()
        elif action == "overlay":
            self._on_overlay_toggle(q.get("key"), q.get("on", "1") == "1")
        elif action == "autorange":
            self.canvas.autorange()
        return self.remote_state()

    def remote_screenshot(self, path, what):
        widget = self.canvas if what == "canvas" else self
        widget.grab().save(path)
        return {"path": path,
                "bytes": os.path.getsize(path) if os.path.exists(path) else 0}

    # -- Window ---------------------------------------------------------
    def reset_layout(self):
        self.restoreState(self._default_state)

    def save_layout_default(self):
        self._default_state = self.saveState()
        self._settings.setValue("windowState", self._default_state)

    def show_all_panels(self):
        for d in self.docks.values():
            d.show()

    # -- Help -----------------------------------------------------------
    def open_doc(self, rel):
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(os.path.join(PROJECT_ROOT, rel)))

    def show_about(self):
        QtWidgets.QMessageBox.about(
            self, "About cellscope_analysis",
            "<b>cellscope_analysis</b><br>Viewer &amp; analysis workbench for "
            "CellScope detection results (recordings + tracking masks).<br><br>"
            "Masks are produced by CellScope; this app views &amp; analyses them.")

    def show_metrics_help(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Metrics reference")
        dlg.resize(640, 660)
        lay = QtWidgets.QVBoxLayout(dlg)
        browser = QtWidgets.QTextBrowser()
        browser.setHtml(metric_docs.as_html())
        lay.addWidget(browser)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec_()

    def show_shortcuts(self):
        QtWidgets.QMessageBox.information(
            self, "Keyboard shortcuts",
            "← / →   step frame\n"
            "Space   play / pause\n"
            "Ctrl+O   open recording      Ctrl+E   export CSV\n"
            "Ctrl+=, Ctrl+-, Ctrl+0   zoom in / out / fit\n"
            "Ctrl+Shift+A   auto contrast      Ctrl+Shift+P   screenshot")
