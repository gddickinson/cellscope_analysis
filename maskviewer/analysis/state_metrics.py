"""State-segmented per-cell metrics — reproduce the original CellScope IC295
state-aware analysis so the Comparison window matches `compare/per_recording.csv`.

A whole-track average mixes two very different behaviours (how a cell moves while
**spread** vs while **rounded**) with how long it spends in each — so the
original never reports it. Instead, for every cell, motility + shape are computed
**separately over rounded vs spread frames**:

* edge-truncated frames are excluded (they are state ``edge``/``unknown``);
* per-step **speed** uses the state at the step's *start* frame, drops any step
  touching an edge frame, and caps at ``SPEED_CAP_UM_PER_MIN`` (tracking
  glitches) — no contiguous-segment requirement, so brief events aren't lost;
* **persistence** (lag-1 direction autocorrelation) and **straightness** use
  contiguous same-state segments of length ≥ ``SEG_MIN`` (single steps are noise);
* **shape** means are over a state's frames.

Output: one row per cell with ``mean_speed_{s}`` / ``persistence_{s}`` /
``straightness_{s}`` / ``mean_area_um2_{s}`` / ``mean_eccentricity_{s}`` /
``mean_aspect_ratio_{s}`` (+ circularity/solidity when available) for
``s ∈ {rounded, spread}``. GUI-free; mirrors `core/motility_state.py` +
`core/state_analysis.py` of the original project. Pure functions, tested.
"""
from __future__ import annotations

import numpy as np

from . import cell_metrics

SPEED_CAP_UM_PER_MIN = 15.0     # drop per-step speeds above this (tracking jumps)
SEG_MIN = 5                     # min contiguous same-state frames for persistence
_SHAPE_KEYS = ("eccentricity", "aspect_ratio", "circularity", "solidity")
_TARGETS = ("rounded", "spread")


def _segments(states):
    """Contiguous runs → [(state, start, end_inclusive)] (gaps break runs)."""
    out = []
    if len(states) == 0:
        return out
    cur, start = states[0], 0
    for i in range(1, len(states)):
        if states[i] != cur:
            out.append((cur, start, i - 1))
            cur, start = states[i], i
    out.append((cur, start, len(states) - 1))
    return out


def _ranges(states, target, min_len):
    return [(s, e) for st, s, e in _segments(states)
            if st == target and e - s + 1 >= min_len]


def _persistence(cents, states, target):
    """Lag-1 direction autocorrelation over target-state segments (≥ SEG_MIN)."""
    cos = []
    for s, e in _ranges(states, target, SEG_MIN):
        c = cents[s:e + 1]
        c = c[~np.isnan(c[:, 0])]
        if len(c) < 3:
            continue
        v = np.diff(c, axis=0)
        u = v / np.maximum(np.linalg.norm(v, axis=1)[:, None], 1e-9)
        cos.extend((u[1:] * u[:-1]).sum(axis=1).tolist())
    return float(np.mean(cos)) if cos else np.nan


def _straightness(cents, states, target):
    """Σ endpoint-displacement / Σ path over target-state segments (≥ SEG_MIN)."""
    td = tp = 0.0
    for s, e in _ranges(states, target, SEG_MIN):
        c = cents[s:e + 1]
        c = c[~np.isnan(c[:, 0])]
        if len(c) < 2:
            continue
        td += float(np.linalg.norm(c[-1] - c[0]))
        tp += float(np.linalg.norm(np.diff(c, axis=0), axis=1).sum())
    return (td / tp) if tp > 0 else np.nan


def per_cell_state_metrics(labels, um_per_px=None, dt_min=None, per_frame_df=None):
    """DataFrame: one row per cell of rounded/spread-segmented metrics.

    Pass ``per_frame_df`` (a `exporters.per_frame_table`) to reuse the regionprops
    pass; otherwise it is computed here (with solidity).
    """
    import pandas as pd
    scale = float(um_per_px) if um_per_px else 1.0
    dt = float(dt_min) if dt_min else 1.0
    if per_frame_df is None:
        per_frame_df = pd.DataFrame(
            cell_metrics.per_frame_records(labels, um_per_px, with_solidity=True))
    pf = per_frame_df
    T = int(labels.shape[0])
    cents = cell_metrics.centroid_history(labels)
    have = [k for k in _SHAPE_KEYS if k in getattr(pf, "columns", [])]
    rows = []
    if pf is None or getattr(pf, "empty", True):
        return pd.DataFrame(rows)
    for cid, g in pf.groupby("cell_id"):
        fr = g["frame"].to_numpy(int)
        states = np.array(["unknown"] * T, dtype=object)
        states[fr] = g["state"].to_numpy()
        edge = np.zeros(T, bool)
        if "edge" in g.columns:
            edge[fr] = g["edge"].to_numpy(bool)
        cen = cents.get(int(cid))
        if cen is None:
            cen = np.full((T, 2), np.nan)
        if T > 1:
            step = np.linalg.norm(np.diff(cen, axis=0), axis=1) * scale / dt
            sstate, sok = states[:-1], ~(edge[:-1] | edge[1:])
        else:
            step = sstate = sok = np.array([])
        row = {"cell_id": int(cid)}
        for tg in _TARGETS:
            if len(step):
                sm = step[(sstate == tg) & sok]
                sm = sm[np.isfinite(sm)]
                sm = sm[sm <= SPEED_CAP_UM_PER_MIN]
            else:
                sm = np.array([])
            row[f"mean_speed_{tg}"] = float(sm.mean()) if sm.size else np.nan
            row[f"persistence_{tg}"] = _persistence(cen, states, tg)
            row[f"straightness_{tg}"] = _straightness(cen, states, tg)
            sub = g[g["state"].to_numpy() == tg]
            row[f"mean_area_um2_{tg}"] = (float(sub["area_um2"].mean())
                                         if len(sub) and "area_um2" in sub else np.nan)
            for k in have:
                row[f"mean_{k}_{tg}"] = float(sub[k].mean()) if len(sub) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
