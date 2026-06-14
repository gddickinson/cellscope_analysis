"""Menu-action methods for ViewerWindow, split out to keep viewer_window small.

`WindowActionsMixin` provides the File / Window / Help action handlers; it only
uses attributes the ViewerWindow already owns (entries, recording, masks, docks,
display, canvas, _settings, _default_state).
"""
from __future__ import annotations

import os

from PyQt5 import QtCore, QtGui, QtWidgets

from .export_dialog import CSVExportDialog
from ..analysis import metric_docs
from ..io.dataset import discover, Entry
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

    def open_data_root_dialog(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Open data folder")
        if not d:
            return
        found = discover(d)
        if not found:
            QtWidgets.QMessageBox.warning(self, "Nothing found",
                                          "No recordings under that folder.")
            return
        self.entries = found
        self.display.set_recordings(self.entries)
        self._load_entry(0)

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
