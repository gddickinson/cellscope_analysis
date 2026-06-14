"""Population (all-cells) analysis for one recording — GUI-free.

Builds a tidy per-(cell, frame) table for plotting distributions / time-courses
across every cell, and origin-centred trajectories for a flower plot. Reuses the
per-frame region table (shape + nearest-neighbour + state, incl. a Crofton
perimeter + circularity) and adds a per-frame speed column from the centroid
tracks. pandas-backed; cache the result (one regionprops pass) and re-plot from
it. The cross-recording / treatment comparison layer builds on this.
"""
from __future__ import annotations

import numpy as np

from . import cell_metrics, exporters

# numeric per-(cell, frame) columns worth plotting (those present are offered)
PLOT_COLUMNS = ["area_um2", "area_px", "perimeter_um", "perimeter_px",
                "circularity", "eccentricity", "aspect_ratio", "solidity",
                "extent", "equiv_diameter_um", "equiv_diameter_px",
                "nn_dist_um", "nn_dist_px", "n_neighbors", "speed"]


def population_table(labels, um_per_px=None, dt_min=None, with_solidity=True,
                     progress_cb=None):
    """DataFrame: one row per (cell, frame) — region/shape + nearest-neighbour +
    state (from `per_frame_table`) plus a per-frame ``speed`` column.
    ``progress_cb(done, total)`` drives a GUI progress bar (per frame)."""
    df = exporters.per_frame_table(labels, um_per_px, dt_min, with_solidity,
                                   progress_cb=progress_cb)
    if df.empty:
        return df
    scale = float(um_per_px) if um_per_px else 1.0
    dt = float(dt_min) if dt_min else 1.0
    speed = {}
    for cid, cen in cell_metrics.centroid_history(labels).items():
        fin = np.isfinite(cen).all(axis=1)
        for t in range(1, cen.shape[0]):
            if fin[t] and fin[t - 1]:
                speed[(cid, t)] = np.sqrt(((cen[t] - cen[t - 1]) ** 2).sum()) \
                    * scale / dt
    df["speed"] = [speed.get((int(c), int(f)), np.nan)
                   for c, f in zip(df["cell_id"], df["frame"])]
    return df


def metric_columns(df):
    return [c for c in PLOT_COLUMNS if c in getattr(df, "columns", [])]


def flower_tracks(labels, um_per_px=None):
    """{cell_id: (n, 2) (y, x) trajectory translated so the first point is the
    origin} (scaled to µm) — for a flower/rose migration plot."""
    scale = float(um_per_px) if um_per_px else 1.0
    out = {}
    for cid, cen in cell_metrics.centroid_history(labels).items():
        pts = cen[np.isfinite(cen).all(axis=1)]
        if pts.shape[0] >= 2:
            out[int(cid)] = (pts - pts[0]) * scale
    return out
