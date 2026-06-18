"""Build a project incrementally — add another folder's recordings to the loaded
project (merge, not replace). The complement to File ▸ Open Project Folder (which
replaces): lets a user assemble one project from several cellscope result trees.

`add_folder_to_project(win)` is a free function (keeps `window_actions` under its
size limit); the data mutation lives on `Project.add_folder`, the session refresh on
`ViewerWindow.set_project`.
"""
from __future__ import annotations

from PyQt5 import QtWidgets


def add_folder_to_project(win):
    if not getattr(win, "project", None):
        return
    d = QtWidgets.QFileDialog.getExistingDirectory(win, "Add folder to project")
    if not d:
        return
    added = win.project.add_folder(d)
    if not added:
        QtWidgets.QMessageBox.information(
            win, "Nothing added",
            "No new recordings under that folder (already in the project, or none "
            "present).")
        return
    win.set_project(win.project)        # rebuild session + comparison from the project
    win.statusBar().showMessage(
        f"Added {added} recording(s) — Save Project (Ctrl+S) to keep this.", 6000)
