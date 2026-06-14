"""Build the mask-overlay lookup table for the current colour-by metric.

Kept out of `viewer_window` (file-size budget); `overlay_lut(win, lab)` reads
what it needs off the ViewerWindow (loaded masks/recording, the colour-by mode,
and the lazy caches/providers) and returns a per-label RGBA LUT, or None for the
default per-ID colouring.
"""
from __future__ import annotations

import numpy as np

from .image_view import scalar_label_lut
from ..analysis import cell_metrics, state as cell_state, neighbors, motion

CMAP = {"area": "viridis", "perimeter": "viridis", "extent": "plasma",
        "eccentricity": "coolwarm", "circularity": "coolwarm",
        "solidity": "coolwarm", "aspect_ratio": "plasma",
        "nn_dist": "cividis", "n_neighbors": "cividis",
        "speed": "magma", "shape_mode": "tab10"}


def mean_speeds(win) -> dict:
    """{cell_id: mean speed} for the recording (lazy, cached on the window)."""
    if win._mean_speed is None and win.masks is not None:
        scale = win.recording.um_per_px or 1.0
        dt = win.recording.time_interval_min
        win._mean_speed = {
            cid: motion.displacement_metrics(cen * scale, dt)["mean_speed"]
            for cid, cen in win._centroid_history().items()}
    return win._mean_speed or {}


def overlay_lut(win, lab):
    if lab is None:
        return None
    mode = win.display.color_by_mode()
    mx = win.masks.max_label
    if mode == "id":
        return None
    if mode == "state":
        props = cell_metrics.regionprops_frame(lab, win.recording.um_per_px)
        lut = np.zeros((mx + 1, 4), dtype=np.ubyte)
        for cid, r in props.items():
            if 0 < cid < lut.shape[0]:
                lut[cid] = (*cell_state.STATE_COLOR.get(r["state"],
                                                        (130, 130, 130)), 255)
        return lut
    if mode == "track":
        win._ensure_track_len()
        return scalar_label_lut(win._track_len, mx, "magma")
    if mode == "speed":
        return scalar_label_lut(mean_speeds(win), mx, "magma")
    if mode == "shape_mode":
        model = win._shape_modes_model()
        if not model:
            return None
        t = win.timeline.value()
        vals = {cid: m for (cid, ft), m in model["by_cell_frame"].items()
                if ft == t}
        return scalar_label_lut(vals, mx, "tab10")
    # per-frame region metrics (recomputed for the current frame)
    um = win.recording.um_per_px
    props = cell_metrics.regionprops_frame(
        lab, um, with_solidity=(mode == "solidity"),
        with_perimeter=(mode in ("perimeter", "circularity")))
    if mode in ("nn_dist", "n_neighbors"):
        ids = sorted(props)
        nn, cnt = neighbors.frame_nn([props[i]["centroid_y"] for i in ids],
                                     [props[i]["centroid_x"] for i in ids],
                                     float(um) if um else 1.0)
        arr = nn if mode == "nn_dist" else cnt
        vals = {ids[j]: float(arr[j]) for j in range(len(ids))
                if np.isfinite(arr[j])}
    else:
        key = {"area": "area_um2" if um else "area_px",
               "perimeter": "perimeter_um" if um else "perimeter_px"
               }.get(mode, mode)
        vals = {cid: props[cid][key] for cid in props if key in props[cid]}
    return scalar_label_lut(vals, mx, CMAP.get(mode, "viridis"))
