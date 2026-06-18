"""Include/Exclude dialog + session refresh (`gui/inclusion.py`).

Headless (QT offscreen): a project of several recordings (all pointing at the real
synthetic sample so `_load_entry` actually loads), then exercise the dialog's
move/transfer logic and `apply_inclusion` — the recording dropdown must show only
included recordings, the excluded current recording must hand off to an included
one, and a project loaded with a pre-set `excluded` must hide it from the session.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SAMPLE = os.path.join(ROOT, "sample_data", "Pos_demo")
TIF = os.path.join(SAMPLE, "Pos_demo.ome.tif")
NPZ = os.path.join(SAMPLE, "pipeline_results", "masks.npz")

pytest.importorskip("PyQt5")
from PyQt5 import QtCore, QtWidgets  # noqa: E402
from maskviewer import project as projmod  # noqa: E402
from maskviewer.io.dataset import Entry  # noqa: E402
from maskviewer.gui import inclusion  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _project(excluded=None):
    entries = [Entry(f"R{i}", "WT" if i < 2 else "KO", TIF, NPZ) for i in range(4)]
    proj = projmod.from_entries(entries, name="T")
    proj.excluded = set(excluded or [])
    return proj


def _window(proj, tmp_path):
    from maskviewer.gui import ViewerWindow
    win = ViewerWindow(proj)
    win._settings = QtCore.QSettings(str(tmp_path / "viewer.ini"),
                                     QtCore.QSettings.IniFormat)
    return win


def test_dialog_partitions_and_moves(app):
    proj = _project(excluded=["R2"])
    dlg = inclusion.IncludeExcludeDialog(proj)
    assert dlg.inc.count() == 3 and dlg.exc.count() == 1
    assert dlg.excluded_labels() == {"R2"}
    # move R0 (first included) → excluded
    dlg.inc.setCurrentRow(0)
    dlg._move_selected(dlg.inc, dlg.exc)
    assert dlg.exc.count() == 2
    assert "R2" in dlg.excluded_labels() and len(dlg.excluded_labels()) == 2


def test_dialog_ok_disabled_when_none_included(app):
    dlg = inclusion.IncludeExcludeDialog(_project())
    dlg._move_all(dlg.inc, dlg.exc)
    ok = dlg.bb.button(QtWidgets.QDialogButtonBox.Ok)
    assert not ok.isEnabled()
    dlg._move_all(dlg.exc, dlg.inc)
    assert ok.isEnabled()


def test_project_with_preset_excluded_hides_from_session(app, tmp_path):
    win = _window(_project(excluded=["R3"]), tmp_path)
    labels = [e.label for e in win.entries]
    assert "R3" not in labels and len(labels) == 3
    assert win.display.recording.count() == 3


def test_apply_inclusion_keeps_current_when_still_included(app, tmp_path):
    win = _window(_project(), tmp_path)
    assert win.display.recording.currentIndex() == 0          # R0 loaded
    rec_before = win.recording
    inclusion.apply_inclusion(win, {"R2", "R3"})              # exclude others, keep R0
    assert [e.label for e in win.entries] == ["R0", "R1"]
    assert win.display.recording.count() == 2
    assert win.recording is rec_before                        # not reloaded
    assert win.project.excluded == {"R2", "R3"}


def test_apply_inclusion_loads_new_when_current_excluded(app, tmp_path):
    win = _window(_project(), tmp_path)
    inclusion.apply_inclusion(win, {"R0"})                    # exclude the loaded one
    assert "R0" not in [e.label for e in win.entries]
    assert win.recording is not None                          # handed off to an included rec
    assert win.display.recording.currentIndex() == 0


def test_apply_inclusion_reinclude_restores(app, tmp_path):
    win = _window(_project(excluded=["R1", "R2"]), tmp_path)
    assert len(win.entries) == 2
    inclusion.apply_inclusion(win, set())                     # include everything again
    assert len(win.entries) == 4
    assert win.display.recording.count() == 4


def test_design_editor_exclude_updates_session(app, tmp_path):
    """Excluding in the Comparison window's Groups editor removes it from the main
    viewer's session dropdown (designChanged → inclusionChanged → apply_inclusion)."""
    win = _window(_project(), tmp_path)
    win.open_compare_window()
    win._compare_window._open_design_editor()
    de = win._compare_window._design_editor
    de._row_include["R1"].setChecked(False)                   # exclude via design editor
    assert win.project.excluded == {"R1"}
    assert "R1" not in [e.label for e in win.entries]         # session synced
    assert win.display.recording.count() == 3


def test_main_inclusion_updates_design_editor(app, tmp_path):
    """The main viewer's apply_inclusion refreshes the Groups editor checkboxes."""
    win = _window(_project(), tmp_path)
    win.open_compare_window()
    win._compare_window._open_design_editor()
    de = win._compare_window._design_editor
    inclusion.apply_inclusion(win, {"R2"})                    # as the File-menu dialog would
    assert de._row_include["R2"].isChecked() is False         # checkbox synced
    assert de._row_include["R0"].isChecked() is True


def test_save_project_to_path_persists_excluded(app, tmp_path):
    """File ▸ Save Project (passing the loaded path) writes the excluded set."""
    win = _window(_project(excluded=["R1"]), tmp_path)
    fn = str(tmp_path / "proj.json")
    win.save_project_as(fn)                                   # explicit path → no prompt
    reloaded = projmod.load_project(fn)
    assert "R1" in reloaded.excluded
