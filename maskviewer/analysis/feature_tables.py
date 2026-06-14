"""Load the CellScope IC295 result artifacts (via the data/ symlinks) and
provide the experimental design + arm-structured statistics.

This couples to CellScope's analysis outputs (it reads the aggregate CSVs and
the per-cell track cache it produced — see docs/DATA.md), so it lives apart
from the generic `label_stats`. It is the data layer for the follow-up
analyses (multivariate / dynamics / interactions) that probe for treatment
effects beneath the state + contact confounds.

  recordings()  -> DataFrame, one row per recording (recording = unit)
  cells()       -> DataFrame, one row per tracked cell (pooled)
  tracks()      -> list of per-cell dicts with per-frame time series
                   (label, cond, cents µm, states, n_neighbors, nn_dist)
  arm_tests(by_cond) -> per-arm Kruskal-Wallis + within-arm Bonferroni
                        pairwise + the WT-vs-DMSO vehicle MWU
"""
from __future__ import annotations

import os
import pickle
from itertools import combinations

import numpy as np

from ..config import PROJECT_ROOT

DT_MIN = 10.0
UM_PER_PX = 0.6523
CONDITIONS = ["WT", "KO", "GOF", "Y1", "OT", "DMSO"]
COND_COLOR = {"WT": "#1f77b4", "KO": "#d62728", "GOF": "#2ca02c",
              "Y1": "#9467bd", "OT": "#ff7f0e", "DMSO": "#7f7f7f"}
# Two independent experiments (control first) + the vehicle check.
ARMS = {"genetic": {"control": "WT", "conditions": ["WT", "GOF", "KO"]},
        "drug": {"control": "DMSO", "conditions": ["DMSO", "Y1", "OT"]}}
VEHICLE = ["WT", "DMSO"]

_RES = os.path.join(PROJECT_ROOT, "data", "results")
REC_CSV = os.path.join(_RES, "compare", "per_recording.csv")
CELL_CSV = os.path.join(_RES, "compare_pooled", "per_cell_pooled.csv")
TRACK_CACHE = os.path.join(_RES, "compare", "flower_plots", "_track_cache.pkl")


def _require(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} missing — run scripts/link_data.py and make sure the "
            "CellScope analysis has been run (see docs/DATA.md).")
    return path


def recordings():
    import pandas as pd
    return pd.read_csv(_require(REC_CSV))


def cells():
    import pandas as pd
    return pd.read_csv(_require(CELL_CSV))


def tracks():
    """Flat list of per-cell records (each a dict with per-frame arrays)."""
    with open(_require(TRACK_CACHE), "rb") as f:
        blob = pickle.load(f)
    data = blob["data"] if isinstance(blob, dict) and "data" in blob else blob
    out = []
    for cond, groups in data.items():
        for rec in groups.get("cells", groups.get("all", [])):
            out.append(rec)
    return out


# ----------------------------------------------------------- arm statistics
def _mwu(a, b):
    from scipy.stats import mannwhitneyu
    a = np.asarray(a, float); a = a[np.isfinite(a)]
    b = np.asarray(b, float); b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return None
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except ValueError:
        return None


def _kw(groups):
    from scipy.stats import kruskal
    gs = [np.asarray(g, float)[np.isfinite(np.asarray(g, float))] for g in groups]
    gs = [g for g in gs if len(g) >= 2]
    if len(gs) < 2:
        return None
    try:
        return float(kruskal(*gs).pvalue)
    except ValueError:
        return None


def arm_tests(by_cond: dict, arms=None, vehicle=None) -> dict:
    """by_cond = {condition: [values]} → {arm: {kw, pairs{ctrl_vs_test:{p,p_bonf}}},
    vehicle: {p}}. Bonferroni n = #test-vs-control pairs within the arm.

    ``arms`` / ``vehicle`` default to the IC295 design (back-compat); pass a
    project's design (``Design.arms`` / ``Design.vehicle``) for other datasets.
    """
    use_arms = ARMS if arms is None else arms
    if arms is None and vehicle is None:
        vehicle = VEHICLE
    res = {}
    for arm, spec in use_arms.items():
        conds = spec["conditions"]
        ctrl = spec["control"]
        res[arm] = {"kw": _kw([by_cond.get(c, []) for c in conds]), "pairs": {}}
        tests = [c for c in conds if c != ctrl]
        for t in tests:
            p = _mwu(by_cond.get(ctrl, []), by_cond.get(t, []))
            pb = min(p * len(tests), 1.0) if p is not None else None
            res[arm]["pairs"][f"{ctrl}_vs_{t}"] = {"p": p, "p_bonf": pb}
    res["vehicle"] = {"p": (_mwu(by_cond.get(vehicle[0], []), by_cond.get(vehicle[1], []))
                            if vehicle else None)}
    return res


def stars(p):
    if p is None or not np.isfinite(p):
        return "n/a"
    s = ("***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns")
    return f"{p:.3f} {s}"


def print_arm_tests(name, by_cond):
    r = arm_tests(by_cond)
    out = [f"  [{name}]"]
    for arm, spec in ARMS.items():
        ctrl = spec["control"]
        bits = [f"KW {stars(r[arm]['kw'])}"]
        for t in [c for c in spec["conditions"] if c != ctrl]:
            bits.append(f"{t}v{ctrl} {stars(r[arm]['pairs'][f'{ctrl}_vs_{t}']['p_bonf'])}")
        out.append("    " + arm + ": " + " | ".join(bits))
    out.append(f"    vehicle WTvDMSO: {stars(r['vehicle']['p'])}")
    print("\n".join(out))
    return r
