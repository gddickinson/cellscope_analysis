"""Build the mask-overlay lookup table for the current colour-by metric.

Kept out of `viewer_window` (file-size budget). `overlay_lut(win, lab)` reads
what it needs off the ViewerWindow (loaded masks/recording, the colour-by mode,
the lazy caches/providers) and returns ``(lut, legend)`` where ``lut`` is a
per-label RGBA LUT (or None for default per-ID colouring) and ``legend`` is
``(lo, hi, cmap_name, label)`` for the units colour bar (or None for categorical
modes / no bar).
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


def _label(mode, um, dt):
    u = "µm" if um else "px"
    spd = f"{u}/min" if dt else f"{u}/frame"
    return {"area": f"area ({u}²)", "perimeter": f"perimeter ({u})",
            "circularity": "circularity", "eccentricity": "eccentricity",
            "aspect_ratio": "aspect ratio", "solidity": "solidity",
            "extent": "extent", "nn_dist": f"NN distance ({u})",
            "n_neighbors": "neighbour count", "speed": f"mean speed ({spd})",
            "track": "track length (frames)"}.get(mode, mode)


def mean_speeds(win) -> dict:
    """{cell_id: mean speed} for the recording (lazy, cached on the window)."""
    if win._mean_speed is None and win.masks is not None:
        scale = win.recording.um_per_px or 1.0
        dt = win.recording.time_interval_min
        win._mean_speed = {
            cid: motion.displacement_metrics(cen * scale, dt)["mean_speed"]
            for cid, cen in win._centroid_history().items()}
    return win._mean_speed or {}


def _continuous(vals, mx, cmap, label):
    finite = [v for v in vals.values() if np.isfinite(v)]
    lo, hi = (float(min(finite)), float(max(finite))) if finite else (0.0, 1.0)
    return scalar_label_lut(vals, mx, cmap), (lo, hi, cmap, label)


def overlay_lut(win, lab):
    if lab is None:
        return None, None
    mode = win.display.color_by_mode()
    mx = win.masks.max_label
    um = win.recording.um_per_px
    dt = win.recording.time_interval_min
    if mode == "id":
        return None, None
    if mode == "state":
        props = cell_metrics.regionprops_frame(lab, um)
        lut = np.zeros((mx + 1, 4), dtype=np.ubyte)
        for cid, r in props.items():
            if 0 < cid < lut.shape[0]:
                lut[cid] = (*cell_state.STATE_COLOR.get(r["state"],
                                                        (130, 130, 130)), 255)
        return lut, None                               # categorical → no bar
    if mode == "track":
        win._ensure_track_len()
        return _continuous(win._track_len, mx, "magma", _label(mode, um, dt))
    if mode == "speed":
        return _continuous(mean_speeds(win), mx, "magma", _label(mode, um, dt))
    if mode == "shape_mode":
        model = win._shape_modes_model()
        if not model:
            return None, None
        t = win.timeline.value()
        vals = {cid: m for (cid, ft), m in model["by_cell_frame"].items()
                if ft == t}
        return scalar_label_lut(vals, mx, "tab10"), None   # categorical
    # per-frame region metrics (recomputed for the current frame)
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
    return _continuous(vals, mx, CMAP.get(mode, "viridis"), _label(mode, um, dt))
