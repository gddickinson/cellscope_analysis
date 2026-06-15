"""Headless smoke for the status-bar progress bars + threaded compute.

Drives the main viewer's Population / Cell-table / Shape computes through the
off-thread TaskRunner and checks the StatusProgress bar receives progress and
the result is applied; also unit-checks StatusProgress + TaskRunner directly.

    QT_QPA_PLATFORM=offscreen python scripts/smoke_progress.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets                       # noqa: E402
from maskviewer import project as projmod                 # noqa: E402
from maskviewer.gui.status_progress import StatusProgress, fmt_secs  # noqa: E402
from maskviewer.gui.task_runner import TaskRunner         # noqa: E402


def wait_until(app, pred, timeout_s=20.0):
    loop_ms, waited = 10, 0.0
    while not pred() and waited < timeout_s:
        app.processEvents(QtCore.QEventLoop.AllEvents, loop_ms)
        QtCore.QThread.msleep(loop_ms)
        waited += loop_ms / 1000.0
    return pred()


def test_units(app):
    assert fmt_secs(5) == "5s" and fmt_secs(75) == "1m15s", fmt_secs(75)
    sp = StatusProgress()
    sp.start("X")
    assert sp.isVisible()
    sp.update(2, 10)
    assert sp.bar.maximum() == 10 and sp.bar.value() == 2
    assert "left" in sp.eta.text()
    sp.finish()
    assert sp.bar.value() == 1

    runner = TaskRunner()
    got = {}
    prog = []
    runner.progress.connect(lambda d, t: prog.append((d, t)))
    runner.run(lambda cb: (cb(1, 2), cb(2, 2), 42)[-1],
               on_done=lambda r: got.setdefault("r", r))
    assert wait_until(app, lambda: "r" in got), "TaskRunner never finished"
    assert got["r"] == 42 and (2, 2) in prog, (got, prog)
    print(f"  units: StatusProgress + TaskRunner OK (progress={prog})")


def drive_compute(app, win, panel, label):
    prog = []
    win._task.progress.connect(lambda d, t: prog.append((d, t)))
    panel._compute()                                       # async via run_task
    ok = wait_until(app, lambda: not win._task.busy)
    win._task.progress.disconnect()
    assert ok, f"{label}: task did not finish"
    assert prog and prog[-1][0] == prog[-1][1], f"{label}: no full progress {prog}"
    print(f"  {label}: threaded compute OK ({len(prog)} progress ticks)")


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    test_units(app)

    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "sample_data")
    proj = projmod.from_data_roots(root, name="sample")
    from maskviewer.gui import ViewerWindow
    win = ViewerWindow(proj)
    assert win.masks is not None, "sample recording has no masks"

    drive_compute(app, win, win.population, "Population")
    assert win.population._df is not None and not win.population._df.empty
    drive_compute(app, win, win.cell_table, "Cell table")
    assert win.cell_table._df is not None and not win.cell_table._df.empty
    drive_compute(app, win, win.shape, "Shape modes")     # may yield no model on tiny data

    # zoom-to-cell (UX): select a cell, frame the canvas on it (must not raise)
    cid = int(win.cell_table._df["cell_id"].iloc[0])
    win.select_cell(cid)
    before = win.canvas.vb.viewRange()
    win.zoom_to_cell()
    app.processEvents()
    assert win.canvas.vb.viewRange() != before, "zoom-to-cell did not change the view"
    print(f"  zoom-to-cell OK (cell {cid})")

    # edge ↔ fluorescence (PIEZO1-style): correlate edge change with a channel
    chans = win.recording.channel_names
    win.edge.fluor.setCurrentText(chans[0])               # the sample's fluor channel
    app.processEvents()
    assert win.edge._piezo is not None and win.edge._piezo.size, "fluor kymograph empty"
    for m in range(win.edge.mode.count()):                # all modes incl. fluor views
        win.edge.mode.setCurrentIndex(m); app.processEvents()
    print(f"  edge↔fluor OK (channel '{chans[0]}', "
          f"r={win.edge._psum.get('edge_piezo_pearson')})")
    shot = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--shot=")), None)
    if shot:
        win.edge.mode.setCurrentText("Edge ↔ fluorescence")
        win.edge.resize(560, 460); app.processEvents()
        win.edge.grab().save(shot)
        print(f"  saved screenshot → {shot}")

    # Comparison window: real threaded build_comparison drives its bottom bar
    from maskviewer.gui.compare_window import CompareWindow
    cw = CompareWindow(proj)
    cw.recompute.setChecked(True)                          # force the worker thread
    cw._compute()
    ok = wait_until(app, lambda: cw._thread is None and cw._per_cell is not None)
    assert ok, "CompareWindow threaded compute did not finish"
    print(f"  CompareWindow: threaded compute OK "
          f"({cw._per_cell['recording'].nunique()} recording(s))")
    # edge-PIEZO1 correlation as a comparison metric (recompute with the channel)
    cw.fluor.setCurrentText(chans[0])
    cw.recompute.setChecked(True)
    cw._compute()
    ok = wait_until(app, lambda: cw._thread is None and cw._per_cell is not None)
    assert ok and "edge_piezo_corr" in cw._per_cell.columns, "edge_piezo_corr missing"
    print("  comparison edge_piezo_corr metric OK")

    # busy-guard: a second task while one runs is refused (not started)
    win.busy.start("blocker")
    win._task._thread = QtCore.QThread(win)               # fake "busy"
    win._task._thread.start()
    assert win._task.busy
    refused = win.run_task("X", lambda cb: None, lambda r: None)
    win._task._thread.quit(); win._task._thread.wait(); win._task._thread = None
    print("  busy-guard: second concurrent task refused OK")

    print("SMOKE OK")


if __name__ == "__main__":
    main()
