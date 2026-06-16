"""Project / Design model: auto-design, regrouping, include/exclude, JSON I/O.

GUI-free — these back the Groups & Comparisons editor. Run with the rest:
`python -m pytest -q`.
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from maskviewer import project as projmod          # noqa: E402
from maskviewer.io.dataset import Entry            # noqa: E402


def _project(conditions, n=2):
    ents = [Entry(f"{c}__{r}", c, "", None) for c in conditions for r in range(n)]
    return projmod.from_entries(ents, name="t")


def _frame(project):
    rows = [{"recording": e.label, "condition": e.condition, "x": i}
            for i, e in enumerate(project.entries)]
    return pd.DataFrame(rows)


def test_auto_design_ic295():
    d = _project(["WT", "GOF", "KO", "DMSO", "Y1", "OT"]).design
    assert set(d.arms) >= {"genetic", "drug"}
    assert d.arms["genetic"]["control"] == "WT"
    assert d.arms["drug"]["control"] == "DMSO"
    assert d.vehicle == ["WT", "DMSO"]


def test_auto_design_generic_single_arm():
    d = _project(["ctrl", "drugA", "drugB"]).design
    assert len(d.arms) == 1
    arm = next(iter(d.arms.values()))
    assert arm["control"] == "ctrl"          # heuristic picks the control-ish name


def test_regroup_excludes_and_overrides():
    p = _project(["WT", "KO"])
    df = _frame(p)
    p.excluded = {"WT__1"}
    p.overrides = {"KO__0": "KO_fast"}
    g = p.regroup(df)
    assert "WT__1" not in g["recording"].values            # excluded dropped
    assert set(g[g["recording"] == "KO__0"]["condition"]) == {"KO_fast"}
    assert sorted(g["condition"].unique()) == ["KO", "KO_fast", "WT"]


def test_effective_conditions_and_groups():
    p = _project(["WT", "KO"])
    p.excluded = {"KO__0", "KO__1"}            # whole KO group excluded
    assert p.conditions == ["WT"]
    p.overrides = {"WT__0": "WT_a"}
    assert "WT_a" in p.all_groups              # available even before assigned to an arm
    assert p.n_recordings == 2                 # included recordings only


def test_ensure_colors_assigns_new_groups():
    p = _project(["WT", "KO"])
    p.overrides = {"WT__0": "Brand_New"}
    projmod.ensure_colors(p.design, p.all_groups)
    assert p.design.colors.get("Brand_New")    # a colour was assigned
    assert p.design.color("Brand_New") != "#777777"


def test_save_load_roundtrip_preserves_groups(tmp_path):
    p = _project(["WT", "KO", "GOF"])
    p.excluded = {"GOF__1"}
    p.overrides = {"KO__0": "KO_fast"}
    fp = os.path.join(tmp_path, "proj.json")
    projmod.save_project(p, fp)
    q = projmod.load_project(fp)
    assert q.excluded == {"GOF__1"}
    assert q.overrides == {"KO__0": "KO_fast"}
    assert q.design.arms == p.design.arms


class _Rec:
    def __init__(self, um, dt):
        self.um_per_px = um
        self.time_interval_min = dt


def test_scale_override_applies_and_persists(tmp_path):
    p = _project(["WT", "KO"])
    # unset → file metadata untouched
    assert p.scale_override == (None, None)
    r = _Rec(0.65, 10.0)
    p.scaled(r)
    assert (r.um_per_px, r.time_interval_min) == (0.65, 10.0)
    # set → overrides every recording, independent fields
    p.px_size, p.frame_interval = 0.25, 2.0
    p.scaled(r)
    assert (r.um_per_px, r.time_interval_min) == (0.25, 2.0)
    assert p.scaled(_Rec(9, 9)).um_per_px == 0.25
    # corrections + scale survive save/load
    p.corrections = {"WT__0": {"shifts": {"0": [1.0, -2.0]}, "fov": [1, 9, 2, 8]}}
    fp = os.path.join(tmp_path, "proj.json")
    projmod.save_project(p, fp)
    q = projmod.load_project(fp)
    assert q.px_size == 0.25 and q.frame_interval == 2.0
    assert q.correction_for("WT__0")["fov"] == [1, 9, 2, 8]


def test_exclude_cell_and_regroup_drops_it():
    p = _project(["WT", "KO"])
    rows = [{"recording": e.label, "condition": e.condition, "cell_id": c, "x": 1}
            for e in p.entries for c in (1, 2, 3)]
    df = pd.DataFrame(rows)
    assert not p.is_cell_excluded("WT__0", 2)
    p.exclude_cell("WT__0", 2)
    assert p.is_cell_excluded("WT__0", 2)
    g = p.regroup(df)
    assert not ((g["recording"] == "WT__0") & (g["cell_id"] == 2)).any()   # dropped
    assert ((g["recording"] == "WT__0") & (g["cell_id"] == 1)).any()       # sibling kept
    assert ((g["recording"] == "KO__0") & (g["cell_id"] == 2)).any()       # other rec kept
    p.exclude_cell("WT__0", 2, on=False)                                   # toggle off
    assert not p.is_cell_excluded("WT__0", 2) and "WT__0" not in p.excluded_cells
    assert ((p.regroup(df)["recording"] == "WT__0") & (p.regroup(df)["cell_id"] == 2)).any()


def test_excluded_cells_save_load_roundtrip(tmp_path):
    p = _project(["WT", "KO"])
    p.exclude_cell("WT__0", 5)
    p.exclude_cell("WT__0", 7)
    p.exclude_cell("KO__1", 3)
    fp = str(tmp_path / "p.cmp")
    projmod.save_project(p, fp)
    q = projmod.load_project(fp)
    assert q.is_cell_excluded("WT__0", 5) and q.is_cell_excluded("WT__0", 7)
    assert q.is_cell_excluded("KO__1", 3) and not q.is_cell_excluded("WT__0", 99)
