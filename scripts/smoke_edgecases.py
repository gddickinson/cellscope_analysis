"""Headless smoke for adversarial GUI edge cases — the classic crash sources.

Drives the Comparison window with **empty / over-filtered** data, hide-all-groups,
and exclude-all-recordings, and the main viewer with **invalid cell selections**,
**out-of-range frames**, rapid overlay toggling, and the intensity edge-map with no
fluorescence channel — asserting none of these throw. Synthetic / sample data only.

    QT_QPA_PLATFORM=offscreen python scripts/smoke_edgecases.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets                                # noqa: E402
from maskviewer import project as projmod                 # noqa: E402
from maskviewer.io.dataset import Entry                   # noqa: E402
import smoke_compare_window as sc                         # noqa: E402

_ERRORS = []


def op(ctx, fn):
    try:
        fn()
    except Exception as exc:                               # collect, don't abort
        _ERRORS.append(f"{ctx}: {type(exc).__name__}: {exc}")
        print(f"  !! {ctx}: {type(exc).__name__}: {exc}", flush=True)


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    QtWidgets.QDialog.exec_ = lambda self: 1               # no modal blocking offscreen
    for m in ("information", "warning", "critical", "question"):
        setattr(QtWidgets.QMessageBox, m, staticmethod(lambda *a, **k: QtWidgets.QMessageBox.Ok))
    from maskviewer.gui.compare_window import CompareWindow
    from maskviewer.gui import ViewerWindow

    # --- Comparison window edge cases (synthetic) ---
    conds = ["WT", "KO", "GOF"]
    ents = [Entry(f"{c}__{r}", c, "x.tif", None) for c in conds for r in range(4)]
    cw = CompareWindow(projmod.from_entries(ents))
    cw._on_done(sc.fake_data(conds), cached=True)          # (per_cell, msd, autocorr)
    app.processEvents()

    def all_tabs():
        for t in range(cw.tabs.count()):
            cw.tabs.setCurrentIndex(t); app.processEvents()
        for r in range(cw.right_tabs.count()):
            cw.right_tabs.setCurrentIndex(r); app.processEvents()

    op("filter excludes every cell (min_frames huge)",
       lambda: (cw.min_frames.setValue(99999), all_tabs()))
    op("multivariate on empty selection", lambda: cw._show_multivariate())
    cw.min_frames.setValue(1); app.processEvents()
    op("hide every group", lambda: (setattr(cw, "hidden_groups", set(cw.project.conditions)),
                                    cw._replot(), all_tabs()))
    cw.hidden_groups = set()
    op("exclude every recording",
       lambda: (setattr(cw.project, "excluded", {e.label for e in cw.project.entries}),
                cw._replot(), all_tabs()))
    op("current-plot resolves on every tab (incl. Dir. autocorr)",
       lambda: [cw.tabs.setCurrentIndex(t) or cw._current_plot()
                for t in range(cw.tabs.count())])
    QtWidgets.QDialog.exec_ = lambda self: 1            # forest / phenotype dialogs
    op("ranked report + forest + phenotype map dialogs",
       lambda: (cw._show_ranked_report(), cw._show_forest(), cw._show_phenotype_map()))
    print("  comparison edge cases OK", flush=True)

    # --- Viewer edge cases (synthetic sample) ---
    sp = projmod.from_data_roots(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "sample_data"), name="sample")
    win = ViewerWindow(sp)
    nf = win.recording.n_frames
    op("select_cell(0)", lambda: win.select_cell(0))
    op("select_cell(nonexistent)", lambda: win.select_cell(99999))
    op("zoom to nonexistent cell", lambda: (win.select_cell(99999), win.zoom_to_cell()))
    op("frame beyond range", lambda: win.timeline.slider.setValue(nf + 9))
    op("frame negative", lambda: win.timeline.slider.setValue(-5))
    op("rapid overlay toggling", lambda: [cb.toggle() or cb.toggle() for cb in win.display.ov.values()])
    op("intensity edge-map without fluor at frame 0",
       lambda: (win.select_cell(1), win.edge.mode.setCurrentText("Edge this frame: intensity"),
                win.timeline.slider.setValue(0), app.processEvents()))
    # the edge panel auto-selects a fluorescence channel so rectangles + edge-intensity
    # render by default (sample has a "Fluo (synthetic)" channel)
    op("edge panel auto-selects a fluorescence channel",
       lambda: (win.select_cell(1), app.processEvents(),
                _assert(win.edge.fluor.currentText() != "(none)",
                        f"fluor not auto-selected: {win.edge.fluor.currentText()!r}")))
    op("population rose (net direction)",
       lambda: (win.population.set_recording(win.masks.labels, win.recording.um_per_px,
                                             win.recording.time_interval_min)
                if hasattr(win.population, "set_recording") else None,
                win.population.kind.setCurrentText("Rose (net direction)"),
                app.processEvents()))
    print("  viewer edge cases OK", flush=True)

    assert not _ERRORS, f"{len(_ERRORS)} edge-case failure(s): {_ERRORS}"
    print("SMOKE OK")


if __name__ == "__main__":
    main()
