#!/usr/bin/env python
"""Write the Python-vs-JS fixture for the web engine tests (tests/fixtures/web_engine/).

  masks.npz      a small SYNTHETIC label stack (maskviewer/web/demo_data.simulate)
  expected.json  what the repo's Python analysis computes on it: per-frame region
                 properties, per-cell table (scaled and unscaled), per-cell motion
                 curves + MSD fit, the per-recording ensemble curves, and Mann-Whitney /
                 Benjamini-Hochberg / Cohen's d / ensemble-by-condition cases.

The JS ports (maskviewer/web/static/*_engine.js) are checked against expected.json by
the node tests; tests/test_web.py checks that this fixture is still current.
Run: python scripts/make_web_fixture.py
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from maskviewer.analysis import cell_metrics, compare, exporters, motion, stats_extra  # noqa: E402
from maskviewer.web import demo_data  # noqa: E402

OUT = os.path.join(ROOT, "tests", "fixtures", "web_engine")
UM, DT = 0.8, 5.0


def clean(v):
    """JSON-safe: NaN/inf -> None, numpy -> python."""
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [clean(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if not math.isfinite(float(v)) else float(v)
    return v


def records(df):
    return [clean(r) for r in df.to_dict(orient="records")]


def labels():
    _, lab = demo_data.simulate(7, 0.8, T=12, H=96, W=96, n_cells=4)
    return lab


def expected(lab):
    from scipy import stats
    pf = exporters.per_frame_table(lab, UM, DT, with_solidity=True, with_contacts=False)
    pc = exporters.per_cell_table(lab, UM, DT)
    pc_px = exporters.per_cell_table(lab, None, None)
    cents = cell_metrics.centroid_history(lab)
    cells = {}
    for cid, c in cents.items():
        sc = c * UM
        tau, m = motion.msd(sc, DT)
        dr = motion.directionality_ratio(sc, DT)
        cells[cid] = {"msd_tau": tau, "msd": m, "fit": motion.fit_msd(tau, m),
                      "autocorr": motion.direction_autocorrelation(c),
                      "velcorr": motion.velocity_autocorrelation(c),
                      "dir_ratio": dr[1], "turning": motion.turning_angles(sc),
                      "speed": motion.instantaneous_speed(sc, DT)}
    _, msd_l, ac_l, dr_l, vc_l = compare.build_comparison(
        [_Entry(lab)], with_contacts=False, with_state_segmented=False)
    rng = np.random.default_rng(3)
    mw = []
    for a, b in [(rng.normal(0, 1, 3), rng.normal(1, 1, 3)), (rng.normal(0, 1, 5), rng.normal(0.5, 1, 7)),
                 (rng.normal(0, 1, 10), rng.normal(0.8, 1, 12)), ([1, 2, 2, 3], [2, 3, 4, 4, 5])]:
        r = stats.mannwhitneyu(a, b, alternative="two-sided")
        mw.append({"x": list(a), "y": list(b), "U": r.statistic, "p": r.pvalue,
                   "d": compare.cohens_d(a, b)})
    ps = [0.01, np.nan, 0.04, 0.03, 0.2, 0.001]
    long = [{"condition": c, "tau": t, "msd": v} for c, t, v in
            [("A", 5, 1.0), ("A", 5, 2.0), ("A", 10, 3.0), ("A", 10, 5.0), ("A", 10, 4.5), ("B", 5, 0.5), ("B", 10, 1.5)]]
    import pandas as pd
    ens = compare.ensemble_by_condition(pd.DataFrame(long))
    return clean({
        "um_per_px": UM, "dt_min": DT,
        "per_frame": records(pf), "per_cell": records(pc), "per_cell_px": records(pc_px),
        "cells": cells,
        "curves": {"msd": records(msd_l), "autocorr": records(ac_l), "dir_ratio": records(dr_l),
                   "velcorr": records(vc_l)},
        "mannwhitney": mw, "bh": {"p": ps, "q": stats_extra.benjamini_hochberg(ps)},
        "ensemble": {"long": long, "out": {k: [list(x) for x in v] for k, v in ens.items()}},
    })


class _Entry:
    """Minimal stand-in for io.dataset.Entry so build_comparison runs on the fixture stack."""
    label, condition = "fixture", "synthetic"

    def __init__(self, lab):
        self._lab = lab

    def load_masks(self):
        from maskviewer.io.masks import Masks
        return Masks(path="fixture", labels=self._lab)

    def load_recording(self):
        from maskviewer.io.recording import Recording
        T, H, W = self._lab.shape
        return Recording(path="fixture", data=np.zeros((T, 1, H, W), np.uint16), channel_names=["none"],
                         um_per_px=UM, time_interval_min=DT)


def main():
    os.makedirs(OUT, exist_ok=True)
    lab = labels()
    np.savez_compressed(os.path.join(OUT, "masks.npz"), labels=lab)
    with open(os.path.join(OUT, "expected.json"), "w") as f:
        json.dump(expected(lab), f, separators=(",", ":"))
    print(f"wrote {OUT} ({lab.shape}, {int(lab.max())} cells)")


if __name__ == "__main__":
    main()
