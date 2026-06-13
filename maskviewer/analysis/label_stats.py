"""Basic label-stack statistics — the seed for future analysis.

Pure NumPy functions over a (T, H, W) integer label stack (0 = background,
>0 = track-consistent cell ID). No GUI / IO dependency, so they're easy to
unit-test and to call from notebooks or new analysis scripts. Future
sessions should grow analysis HERE (shape, motility, state, …) rather than
inside the GUI.
"""
from __future__ import annotations

import numpy as np


def n_cells_per_frame(labels: np.ndarray) -> np.ndarray:
    """(T,) count of distinct non-zero labels in each frame."""
    return np.array([int((np.unique(labels[t]) > 0).sum())
                     for t in range(labels.shape[0])])


def cell_ids(labels: np.ndarray) -> np.ndarray:
    u = np.unique(labels)
    return u[u > 0]


def cell_areas_px(labels: np.ndarray) -> dict:
    """{cell_id: (T,) per-frame area in pixels} (0 where the cell is absent)."""
    out: dict[int, np.ndarray] = {}
    for cid in cell_ids(labels):
        out[int(cid)] = (labels == cid).reshape(labels.shape[0], -1).sum(axis=1)
    return out


def track_lengths(labels: np.ndarray) -> dict:
    """{cell_id: number of frames in which the cell appears}."""
    return {cid: int(np.count_nonzero(a)) for cid, a in
            cell_areas_px(labels).items()}


def centroids(labels: np.ndarray) -> dict:
    """{cell_id: (T, 2) centroid (row, col); NaN where the cell is absent}."""
    T, H, W = labels.shape
    rr, cc = np.arange(H), np.arange(W)
    out: dict[int, np.ndarray] = {}
    for cid in cell_ids(labels):
        cen = np.full((T, 2), np.nan)
        for t in range(T):
            m = labels[t] == cid
            n = m.sum()
            if n:
                cen[t, 0] = (m.sum(axis=1) * rr).sum() / n
                cen[t, 1] = (m.sum(axis=0) * cc).sum() / n
        out[int(cid)] = cen
    return out


def summary(labels: np.ndarray, um_per_px: float | None = None) -> dict:
    """A compact overview dict — handy for a status line or a report."""
    per_frame = n_cells_per_frame(labels)
    tl = track_lengths(labels)
    px2 = (um_per_px ** 2) if um_per_px else None
    areas = cell_areas_px(labels)
    mean_area_px = {cid: float(a[a > 0].mean()) if (a > 0).any() else 0.0
                    for cid, a in areas.items()}
    return {
        "n_frames": int(labels.shape[0]),
        "n_cells_total": int(len(tl)),
        "cells_per_frame_mean": float(per_frame.mean()) if per_frame.size else 0.0,
        "cells_per_frame_max": int(per_frame.max()) if per_frame.size else 0,
        "track_length_mean": (float(np.mean(list(tl.values()))) if tl else 0.0),
        "mean_cell_area_px": (float(np.mean(list(mean_area_px.values())))
                              if mean_area_px else 0.0),
        "mean_cell_area_um2": ((float(np.mean(list(mean_area_px.values()))) * px2)
                               if (px2 and mean_area_px) else None),
        "um_per_px": um_per_px,
    }
