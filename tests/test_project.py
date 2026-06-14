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
