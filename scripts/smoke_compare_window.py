"""Headless smoke for the Comparison window + Project wiring (QT offscreen).

Builds fake per-cell / MSD frames (no disk data needed) and drives CompareWindow
through every tab + the stats table for both a multi-arm (IC295-like) design and
a single-arm design (editable control combo); then builds a real ViewerWindow on
sample_data and checks open_compare_window() + set_project() are wired.

    QT_QPA_PLATFORM=offscreen python scripts/smoke_compare_window.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets                                    # noqa: E402
from maskviewer import project as projmod                      # noqa: E402
from maskviewer.io.dataset import Entry                        # noqa: E402
from maskviewer.gui.compare_window import CompareWindow        # noqa: E402

rng = np.random.default_rng(0)


def fake_data(conditions, n_rec=4, n_cells=15):
    """(per_cell, msd) mimicking compare.build_comparison output."""
    pc_rows, msd_rows = [], []
    for cond in conditions:
        bump = 1.0 + 0.15 * conditions.index(cond)             # per-cond shift
        for r in range(n_rec):
            rec = f"{cond}__{r}"
            for cid in range(n_cells):
                pc_rows.append({
                    "recording": rec, "condition": cond, "cell_id": cid,
                    "frames_tracked": int(rng.integers(3, 30)),
                    "mean_area_um2": float(rng.normal(120 * bump, 20)),
                    "frac_spread": float(np.clip(rng.normal(0.5 * bump, 0.1), 0, 1)),
                    "mean_n_neighbors": float(abs(rng.normal(2.0, 0.6))),
                    "shape_roundness": float(np.clip(rng.normal(0.6, 0.1), 0, 1)),
                })
            for k in range(10):
                msd_rows.append({"recording": rec, "condition": cond,
                                 "tau": (k + 1) * 2.0,
                                 "msd": float((k + 1) * 3.0 * bump
                                              + rng.normal(0, 1))})
    return pd.DataFrame(pc_rows), pd.DataFrame(msd_rows)


def make_project(name, conditions):
    entries = [Entry(f"{c}__{r}", c, "", None)
               for c in conditions for r in range(4)]
    return projmod.from_entries(entries, name=name)


def drive(win, label):
    """Exercise every tab + the dist kinds + OLS + stats table."""
    # Distributions: strip / box / superplot
    win.tabs.setCurrentIndex(0)
    for k in range(win.dist_kind.count()):
        win.dist_kind.setCurrentIndex(k)
    # Ensemble MSD: mean then median
    win.tabs.setCurrentIndex(1)
    for s in range(win.stat.count()):
        win.stat.setCurrentIndex(s)
    # Scatter (x != y)
    win.tabs.setCurrentIndex(2)
    if win.metric_y.count() > 1:
        win.metric_y.setCurrentIndex(1)
    # OLS-adjust + a min-frames filter, back on Distributions
    win.tabs.setCurrentIndex(0)
    win.ols.setChecked(True)
    win.min_frames.setValue(5)
    rows = win.table.rowCount()
    assert rows > 0, f"{label}: stats table is empty"
    print(f"  {label}: tabs OK · stats rows={rows} · omnibus={win.omnibus.text()[:48]!r}")


def drive_editor(win, app):
    """Open the Groups & Comparisons editor and exercise every edit path."""
    win._open_design_editor()
    ed = win._design_editor
    base_recs = win._filtered()["recording"].nunique()

    # exclude one recording (via its row checkbox) → window drops it
    ed._row_include["WT__0"].setChecked(False)
    app.processEvents()
    assert "WT__0" in win.project.excluded
    assert win._filtered()["recording"].nunique() == base_recs - 1, "exclude failed"
    assert win._filtered_msd()["recording"].nunique() == base_recs - 1

    # reassign a recording to a brand-new group → appears in the plots' data
    ed._row_combos["GOF__0"].setCurrentText("GOF_special")
    app.processEvents()
    assert win.project.overrides.get("GOF__0") == "GOF_special"
    assert "GOF_special" in win._filtered()["condition"].unique(), "regroup failed"

    # add a comparison, set its control, set the vehicle pair
    n_before = len(ed.project.design.arms)
    ed._add_comparison()
    app.processEvents()
    assert len(ed.project.design.arms) == n_before + 1, "add comparison failed"
    arm = next(iter(ed.project.design.arms))
    ed._set_control(arm, ed.project.design.arms[arm]["conditions"][0])
    ed.veh_a.setCurrentText("WT")
    ed.veh_b.setCurrentText("KO")
    app.processEvents()
    assert ed.project.design.vehicle == ["WT", "KO"], ed.project.design.vehicle

    # reset clears exclusions + overrides and re-detects the design
    ed._reset()
    app.processEvents()
    assert win.project.excluded == set() and win.project.overrides == {}
    assert win._filtered()["recording"].nunique() == base_recs, "reset failed"
    win._replot()                                     # must not raise
    print(f"  editor: exclude/regroup/add-comparison/control/vehicle/reset OK "
          f"({base_recs} recordings)")


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    # --- multi-arm (IC295-like) design ---------------------------------
    ic = make_project("ic295-like", ["WT", "GOF", "KO", "DMSO", "Y1", "OT"])
    assert len(ic.design.arms) >= 2, "expected genetic+drug arms"
    assert ic.design.vehicle == ["WT", "DMSO"], ic.design.vehicle
    win = CompareWindow(ic)
    assert not win.control.isEnabled(), "multi-arm control combo should be disabled"
    win._on_done((*fake_data(ic.conditions),), cached=True)
    drive(win, "multi-arm")

    shot = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--shot=")), None)
    if shot:                                          # box view = clearest for docs
        win.metric.setCurrentText("mean_area_um2")
        win.ols.setChecked(False)
        win.min_frames.setValue(1)
        win.tabs.setCurrentIndex(0)
        win.dist_kind.setCurrentIndex(1)
        win.resize(1180, 720)
        app.processEvents()
        win.grab().save(shot)
        print(f"  saved screenshot → {shot}")

    eshot = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--editshot=")), None)
    if eshot:                                         # clean editor, before any edits
        win._open_design_editor()
        ed = win._design_editor
        ed.resize(760, 680)
        app.processEvents()
        ed.grab().save(eshot)
        print(f"  saved editor screenshot → {eshot}")

    drive_editor(win, app)

    # --- single-arm design (editable control combo) -------------------
    sp = make_project("single-arm", ["ctrl", "drugA", "drugB"])
    assert len(sp.design.arms) == 1, sp.design.arms
    win.set_project(sp)                                # exercise project switch
    assert win.control.isEnabled(), "single-arm control combo should be editable"
    assert win.control.currentText() == "ctrl", win.control.currentText()
    win._on_done((*fake_data(sp.conditions),), cached=True)
    drive(win, "single-arm")
    win.control.setCurrentText("drugA")               # change control → recompute
    assert sp.design.arms["comparison"]["control"] == "drugA"
    print("  single-arm: control switch OK")

    # --- ViewerWindow wiring on sample_data ----------------------------
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "sample_data")
    proj = projmod.from_data_roots(root, name="sample")
    from maskviewer.gui import ViewerWindow
    vw = ViewerWindow(proj)
    cw = None
    vw.open_compare_window()
    cw = vw._compare_window
    assert cw is not None and cw.project.name == "sample"
    vw.set_project(ic)                                # propagates to compare window
    assert cw.project.name == "ic295-like", cw.project.name
    print(f"  viewer: open_compare_window + set_project OK "
          f"({proj.n_recordings} sample recording(s))")

    print("SMOKE OK")


if __name__ == "__main__":
    main()
