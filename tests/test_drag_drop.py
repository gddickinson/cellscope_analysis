"""Drag-and-drop opening (drop a project folder / .json / recording onto the window).

Headless (QT offscreen): build a blank ViewerWindow, isolate its QSettings to a
temp store (so `_remember_project` doesn't touch the real prefs), and exercise the
`open_paths` dispatch directly — folder → project, recording file → appended entry,
.json → project — plus the `dragEnterEvent` accept/ignore gating.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SAMPLE_ROOT = os.path.join(ROOT, "sample_data")
SAMPLE_TIF = os.path.join(SAMPLE_ROOT, "Pos_demo", "Pos_demo.ome.tif")

pytest.importorskip("PyQt5")
from PyQt5 import QtCore, QtWidgets  # noqa: E402
from maskviewer import project as projmod  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _blank_window(tmp_path):
    from maskviewer.gui import ViewerWindow
    win = ViewerWindow(projmod.from_entries([], name="(blank)"))
    win._settings = QtCore.QSettings(str(tmp_path / "viewer.ini"),
                                     QtCore.QSettings.IniFormat)
    return win


def test_drop_folder_opens_project(app, tmp_path):
    win = _blank_window(tmp_path)
    assert win.project.n_recordings == 0
    win.open_paths([SAMPLE_ROOT])
    assert any(e.label == "Pos_demo" for e in win.entries)
    assert win.recording is not None                 # first entry auto-loaded


def test_drop_recording_file_appends_entry(app, tmp_path):
    win = _blank_window(tmp_path)
    win.open_paths([SAMPLE_TIF])
    # label is the basename sans final ext (matches File ▸ Open Recording: "Pos_demo.ome")
    assert win.entries and win.entries[-1].recording_path == SAMPLE_TIF
    assert win.entries[-1].mask_path and win.entries[-1].mask_path.endswith(".npz")


def test_drop_project_json_opens_it(app, tmp_path):
    proj = projmod.from_data_roots(SAMPLE_ROOT)
    fn = str(tmp_path / "demo.json")
    projmod.save_project(proj, fn)
    win = _blank_window(tmp_path)
    win.open_paths([fn])
    assert win.project.path == fn
    assert any(e.label == "Pos_demo" for e in win.entries)


def test_drop_empty_folder_warns_not_crash(app, tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    warned = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning",
                        lambda *a, **k: warned.append(a))
    win = _blank_window(tmp_path)
    win.open_paths([str(empty)])
    assert warned                                    # warned, no recordings added
    assert win.project.n_recordings == 0


class _FakeDragEvent:
    """Minimal stand-in for a QDrag*Event (constructing the real ones segfaults
    under the offscreen platform). dragEnterEvent only calls these three."""
    def __init__(self, urls):
        self._md = QtCore.QMimeData()
        self._md.setUrls([QtCore.QUrl.fromLocalFile(u) for u in urls])
        self.accepted = None

    def mimeData(self):
        return self._md

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def test_drag_enter_accepts_files_rejects_empty(app, tmp_path):
    win = _blank_window(tmp_path)
    ev = _FakeDragEvent([SAMPLE_TIF])
    win.dragEnterEvent(ev)
    assert ev.accepted is True
    empty = _FakeDragEvent([])
    win.dragEnterEvent(empty)
    assert empty.accepted is False
