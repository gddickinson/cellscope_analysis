"""Interaction + clean-subset analyses.

The treatment effect might not be a main effect but conditional:

  density_slope   per recording, regress cell speed on local crowding; the
                  SLOPE (how strongly density suppresses motility) is compared
                  across conditions — a treatment×density interaction test at
                  the recording level.
  clean_subset    restrict to 'clean' cells (non-dividing, stable single
                  state, fully in view) and re-test key metrics — removes the
                  state-transition / division / edge noise that may mask a
                  small effect. (Conditioning on state can bias, so this is a
                  sensitivity check, not the primary test.)
"""
from __future__ import annotations

import numpy as np

from . import feature_tables as ft

ROUNDED, SPREAD = "rounded", "spread"


def _cell_summ(recs):
    """Per cell: cond, label, speed, median local density."""
    rows = []
    for r in recs:
        nb = np.asarray(r["n_neighbors"], float)
        pres = np.isfinite(np.asarray(r["cents"])[:, 0])
        dens = np.nanmedian(nb[pres]) if pres.any() else np.nan
        rows.append((r["cond"], r["label"], r["speed"], dens))
    return rows


def density_slope_test(recs):
    """Per-recording OLS slope speed~density → arm test on the slopes."""
    rows = _cell_summ(recs)
    by = {}
    for cond, label, sp, dens in rows:
        by.setdefault((cond, label), []).append((sp, dens))
    slopes = {c: [] for c in ft.CONDITIONS}
    for (cond, _l), vals in by.items():
        a = np.array([(s, d) for s, d in vals
                      if np.isfinite(s) and np.isfinite(d)])
        if len(a) >= 5 and np.ptp(a[:, 1]) > 0:        # need density spread
            slope = np.polyfit(a[:, 1], a[:, 0], 1)[0]
            slopes[cond].append(float(slope))
    print("\n  treatment×density (per-recording speed~crowding slope, µm/min "
          "per neighbour)")
    meds = {c: (float(np.median(v)) if v else float('nan'))
            for c, v in slopes.items()}
    print("    median slope: " +
          ", ".join(f"{c}={meds[c]:+.3f}(n={len(slopes[c])})"
                    for c in ft.CONDITIONS))
    return ft.print_arm_tests("density-slope", slopes)


CLEAN_METRICS = ["mean_speed_spread", "mean_eccentricity_spread",
                 "mean_circularity_spread", "mean_area_um2_spread"]


def clean_subset_test(cells_df):
    """Restrict to non-dividing, stable-state, fully-in-view cells; re-test."""
    df = cells_df
    div = df.get("division_frame")
    parent = df.get("parent_id")
    nondiv = (div.isna() if div is not None else True) & \
             (parent.isna() if parent is not None else True)
    stable = (df["frac_spread"] >= 0.95) | (df["frac_spread"] <= 0.05)
    inview = df["frac_in_view"] >= 0.95
    clean = df[nondiv & stable & inview]
    spread_clean = clean[clean["frac_spread"] >= 0.95]
    n_per = {c: int((spread_clean["condition"] == c).sum())
             for c in ft.CONDITIONS}
    print(f"\n  clean spread cells (non-dividing, stable, in-view): "
          f"{len(spread_clean)} total — " +
          ", ".join(f"{c}={n_per[c]}" for c in ft.CONDITIONS))
    out = {}
    for m in CLEAN_METRICS:
        if m not in spread_clean.columns:
            continue
        by = {c: [] for c in ft.CONDITIONS}
        for (cond, _l), g in spread_clean.groupby(["condition", "label"]):
            v = g[m].to_numpy(float)
            v = v[np.isfinite(v)]
            if v.size:
                by[cond].append(float(v.mean()))
        print(f"\n  [{m}] (clean spread, per-recording mean)")
        out[m] = ft.print_arm_tests(m, by)
    return out


def run():
    print("=== INTERACTIONS + CLEAN SUBSET ===")
    recs = ft.tracks()
    res = {"density_slope": density_slope_test(recs)}
    res["clean_subset"] = clean_subset_test(ft.cells())
    return res
