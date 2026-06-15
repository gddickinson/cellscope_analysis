"""Headless smoke: recordings with 1, 2 and 3+ channels all load + analyse.

Generates synthetic recording folders with varying channel counts, then for each
drives the viewer (channel switch, composite, render), the pre-analysis dialog
(auto-align + auto-FOV + apply), the edge-movement↔intensity panel on a chosen
channel, and `build_comparison` — asserting nothing assumes exactly two channels.

    QT_QPA_PLATFORM=offscreen python scripts/smoke_channels.py
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
from PyQt5 import QtWidgets                                # noqa: E402

T, H, W = 6, 96, 96


def _blob(cy, cx, rad):
    yy, xx = np.ogrid[:H, :W]
    return ((yy - cy) ** 2 + (xx - cx) ** 2) <= rad ** 2


def write_recording(folder, n_channels):
    """A tiny (T, C, H, W) recording + masks with `n_channels` channels."""
    os.makedirs(os.path.join(folder, "pipeline_results"), exist_ok=True)
    rng = np.random.default_rng(n_channels)
    data = np.zeros((T, n_channels, H, W), np.uint16)
    labels = np.zeros((T, H, W), np.int32)
    tracks = [(30, 24, 1.2, 0.8, 11), (60, 60, -0.6, 0.9, 13)]
    for t in range(T):
        chans = [rng.normal(300 + 200 * c, 20, (H, W)) for c in range(n_channels)]
        for cid, (y0, x0, vy, vx, rad) in enumerate(tracks, start=1):
            m = _blob(y0 + vy * t, x0 + vx * t, rad)
            for c in range(n_channels):
                chans[c][m] += 1400
            labels[t][m] = cid
        for c in range(n_channels):
            data[t, c] = np.clip(chans[c], 0, 65535)
    names = (["DIC"] if n_channels == 1 else
             ["Fluo", "DIC"] if n_channels == 2 else
             ["Fluo", "DIC"] + [f"extra{c}" for c in range(n_channels - 2)])
    tifffile.imwrite(os.path.join(folder, "rec.ome.tif"), data,
                     metadata={"axes": "TCYX"})
    with open(os.path.join(folder, "rec.ome.json"), "w") as f:
        json.dump({"um_per_px": 0.65, "time_interval_min": 10.0,
                   "channel_names": names[:n_channels]}, f)
    np.savez_compressed(os.path.join(folder, "pipeline_results", "masks.npz"),
                        labels=labels)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    from maskviewer import project as projmod
    from maskviewer.gui import ViewerWindow
    from maskviewer.gui.prep_dialog import PrepDialog
    from maskviewer.analysis import compare, registration, fov

    with tempfile.TemporaryDirectory() as root:
        for c in (1, 2, 3):
            write_recording(os.path.join(root, f"cond{c}__rec{c}ch"), c)
        proj = projmod.from_data_roots(root, name="chantest")
        assert len(proj.entries) == 3, [e.label for e in proj.entries]
        win = ViewerWindow(proj)

        for idx, e in enumerate(win.entries):
            win.display.recording.setCurrentIndex(idx)
            app.processEvents()
            rec = win.recording
            nc = rec.n_channels
            assert nc == idx + 1, (e.label, nc)
            assert len(win.display._chan_checks) == nc, "composite boxes ≠ channels"
            # switch through every channel + render
            for ch in range(nc):
                win.display.channel.setCurrentIndex(ch)
                app.processEvents()
            # composite blend of all channels then back
            win.display.composite.setChecked(True); app.processEvents()
            win.display.composite.setChecked(False); app.processEvents()

            # pure tools cope with any channel count
            fov.auto_fov(rec.data)
            registration.estimate_stack_shift(rec.data[:, 0], rec.data[:, nc - 1])

            # pre-analysis dialog: construct, auto, apply (no raise)
            applied = {}
            dlg = PrepDialog(rec, e.label, {}, lambda d: applied.update(d), win)
            assert dlg.ref.count() == nc and dlg.mov.count() == nc
            dlg._do_auto_align(); dlg._do_auto_fov(); dlg._update_preview()
            dlg.dy.setValue(1.0); dlg.dx.setValue(-1.0); dlg._apply()
            win._apply_correction(applied)

            # edge-movement ↔ intensity on the last channel
            win.select_cell(1)
            win.edge.fluor.setCurrentText(rec.channel_names[nc - 1])
            app.processEvents()
            assert win.edge._int is not None and win.edge._int.size, "no intensity"
            print(f"  {nc}-channel '{e.label}': display+prep+edge OK "
                  f"(r={win.edge._summary.get('edge_move_intensity_r')})", flush=True)

        # comparison across mixed channel counts, sampling channel index 0
        per_cell, *_ = compare.build_comparison(
            proj.entries, piezo_channel=0, corrections=proj.corrections)
        assert "edge_piezo_corr" in per_cell.columns
        assert per_cell["recording"].nunique() == 3
        print(f"  build_comparison over 1/2/3-channel recordings: "
              f"{len(per_cell)} cells OK", flush=True)

    print("SMOKE OK")


if __name__ == "__main__":
    main()
