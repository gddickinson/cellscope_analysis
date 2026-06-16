"""Nearest-neighbour measurements between cells in a frame (GUI-free).

Centroid-to-centroid: for each cell in a frame, the distance to the closest
other cell and the number of cells within a radius. Crowding / contact context
for the migration + contact-inhibition questions; surfaced in the per-frame /
per-cell CSV exports and as a selectable per-frame series in the cell-info plot.
"""
from __future__ import annotations

import numpy as np

DEFAULT_RADIUS_UM = 50.0


def frame_nn(cys, cxs, scale=1.0, radius=None):
    """Per-cell nearest-neighbour distance + neighbour count for one frame.

    ``cys`` / ``cxs`` are centroid row/col arrays (px); distances are returned in
    scaled units (µm when ``scale`` is µm/px). ``nn_dist`` is NaN and the count 0
    when there are fewer than two cells. ``radius=None`` reads the (configurable)
    module-level ``DEFAULT_RADIUS_UM`` at call time so a GUI setting applies.
    """
    radius = DEFAULT_RADIUS_UM if radius is None else radius
    cys = np.asarray(cys, float) * scale
    cxs = np.asarray(cxs, float) * scale
    n = cys.size
    nn = np.full(n, np.nan)
    cnt = np.zeros(n, int)
    if n < 2:
        return nn, cnt
    for i in range(n):
        d = np.sqrt((cys - cys[i]) ** 2 + (cxs - cxs[i]) ** 2)
        d[i] = np.inf
        nn[i] = d.min()
        if radius:
            cnt[i] = int((d <= radius).sum())
    return nn, cnt
