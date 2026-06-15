"""Headless smoke: single-cell-crop recordings of varying shape + length.

A new experiment style crops one cell out of each field, so recordings differ in
H×W and frame count (only the portion where the cell is present), sometimes with
the cell appearing partway through. This drives the viewer, edge analysis,
comparison and the manual pixel-size / time-scale override across such a mixed
project, asserting nothing assumes a fixed shape, length, or present-from-frame-0.

    QT_QPA_PLATFORM=offscreen python scripts/smoke_singlecell.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np                                         # noqa: E402
import tifffile                                            # noqa: E402
from PyQt5 import QtCore, QtWidgets                        # noqa: E402

# (label, T, H, W, present-frame range) — varied crops, incl. partial presence
SPECS = [
    ("cellA", 5, 64, 72, range(0, 5)),
    ("cellB", 12, 120, 96, range(0, 12)),
    ("cellC", 3, 48, 56, range(0, 3)),
    ("cellD", 10, 96, 88, range(2, 9)),               # cell appears partway through
]


def wait(app, pred, t=60.0):
    w = 0.0
    while not pred() and w < t:
        app.processEvents(QtCore.QEventLoop.AllEvents, 20)
        QtCore.QThread.msleep(20); w += 0.02
    return pred()


def write_crop(folder, t_n, h, w, present):
    os.makedirs(os.path.join(folder, "pipeline_results"), exist_ok=True)
    rng = np.random.default_rng(h * w)
    data = np.zeros((t_n, 2, h, w), np.uint16)
    labels = np.zeros((t_n, h, w), np.int32)
    rad = max(6, min(h, w) // 4)
    cy0, cx0 = h / 2.0, w / 2.0
    yy, xx = np.ogrid[:h, :w]
    for t in range(t_n):
        fluo = rng.normal(300, 20, (h, w)); dic = rng.normal(1500, 30, (h, w))
        if t in present:
            cy, cx = cy0 + 0.6 * (t - t_n / 2), cx0 + 0.4 * (t - t_n / 2)
            m = (yy - cy) ** 2 + (xx - cx) ** 2 <= rad ** 2
            fluo[m] += 1500; dic[m] -= 400
            labels[t][m] = 1
        data[t, 0] = np.clip(fluo, 0, 65535); data[t, 1] = np.clip(dic, 0, 65535)
    tifffile.imwrite(os.path.join(folder, "rec.ome.tif"), data, metadata={"axes": "TCYX"})
    with open(os.path.join(folder, "rec.ome.json"), "w") as f:
        json.dump({"um_per_px": 0.5, "time_interval_min": 5.0,
                   "channel_names": ["Fluo", "DIC"]}, f)
    np.savez_compressed(os.path.join(folder, "pipeline_results", "masks.npz"),
                        labels=labels)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    from maskviewer import project as projmod
    from maskviewer.gui import ViewerWindow
    from maskviewer.analysis import compare

    with tempfile.TemporaryDirectory() as root:
        for name, t_n, h, w, present in SPECS:
            write_crop(os.path.join(root, f"crop__{name}"), t_n, h, w, present)
        proj = projmod.from_data_roots(root, name="crops")
        assert len(proj.entries) == len(SPECS)
        win = ViewerWindow(proj)

        for idx, (name, t_n, h, w, present) in enumerate(SPECS):
            win.display.recording.setCurrentIndex(idx); app.processEvents()
            rec = win.recording
            assert rec.data.shape == (t_n, 2, h, w), (name, rec.data.shape)
            # display: channels + composite render at this (different) shape
            win.display.channel.setCurrentIndex(1); app.processEvents()
            win.display.composite.setChecked(True); app.processEvents()
            win.display.composite.setChecked(False); app.processEvents()
            # the single cell (id 1) — present possibly only partway through
            win.select_cell(1)
            win.edge.fluor.setCurrentText("Fluo"); app.processEvents()
            assert win.edge._int is not None and win.edge._int.size, f"{name}: no kymo"
            # off-thread computes finish on this small/odd-shaped crop
            for panel in (win.population, win.cell_table):
                panel._compute()
                assert wait(app, lambda: not win._task.busy, 40), f"{name}: compute hung"
            r = win.edge._summary.get("edge_move_intensity_r")
            print(f"  {name} {t_n}f {h}x{w} (present {present.start}-{present.stop - 1}): "
                  f"edge r={r}, pop rows={len(win.population._df)}", flush=True)

        # manual scale override applies to every recording
        win.display.recording.setCurrentIndex(1); app.processEvents()
        win._apply_scale(0.25, 2.0)
        assert win.recording.um_per_px == 0.25 and win.recording.time_interval_min == 2.0
        win.display.recording.setCurrentIndex(3); app.processEvents()
        assert win.recording.um_per_px == 0.25 and win.recording.time_interval_min == 2.0
        print("  scale override applies to all recordings OK", flush=True)
        # persists through save/load
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.json")
            projmod.save_project(win.project, p)
            p2 = projmod.load_project(p)
            assert p2.px_size == 0.25 and p2.frame_interval == 2.0
        print("  scale override persists save/load OK", flush=True)

        # comparison over the mixed-shape project + scale override
        per_cell, _ = compare.build_comparison(
            proj.entries, piezo_channel="Fluo", scale_override=(0.25, 2.0), max_lag=8)
        assert per_cell["recording"].nunique() == len(SPECS)
        assert "edge_piezo_corr" in per_cell.columns
        print(f"  build_comparison over {len(SPECS)} varied crops: {len(per_cell)} cells, "
              f"scale-overridden OK", flush=True)

    print("SMOKE OK")


if __name__ == "__main__":
    main()
