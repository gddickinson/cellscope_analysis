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
from ..analysis import (cell_metrics, state as cell_state, neighbors, motion,
                        contacts as cell_contacts)

CMAP = {"area": "viridis", "perimeter": "viridis", "extent": "plasma",
        "eccentricity": "coolwarm", "circularity": "coolwarm",
        "solidity": "coolwarm", "aspect_ratio": "plasma",
        "nn_dist": "cividis", "n_neighbors": "cividis",
        "contact_fraction": "inferno", "n_contacts": "cividis",
        "speed": "magma", "shape_mode": "tab10"}


def _label(mode, um, dt):
    u = "µm" if um else "px"
    spd = f"{u}/min" if dt else f"{u}/frame"
    return {"area": f"area ({u}²)", "perimeter": f"perimeter ({u})",
            "circularity": "circularity", "eccentricity": "eccentricity",
            "aspect_ratio": "aspect ratio", "solidity": "solidity",
            "extent": "extent", "nn_dist": f"NN distance ({u})",
            "n_neighbors": "neighbour count", "speed": f"mean speed ({spd})",
            "contact_fraction": "boundary in contact (fraction)",
            "n_contacts": "cells in contact (count)",
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


def _column_for(mode, um):
    suffixed = {"area": ("area_um2", "area_px"),
                "perimeter": ("perimeter_um", "perimeter_px"),
                "nn_dist": ("nn_dist_um", "nn_dist_px")}
    if mode in suffixed:
        return suffixed[mode][0 if um else 1]
    return mode


def _fixed_range(win, mode, um):
    """Global (lo, hi) for a per-frame metric from the cached population table."""
    df = win._population_table()
    col = _column_for(mode, um)
    if df is None or col not in getattr(df, "columns", []):
        return None
    s = df[col].to_numpy(float)
    s = s[np.isfinite(s)]
    return (float(s.min()), float(s.max())) if s.size else None


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
    if mode in ("contact_state", "contact_fraction", "n_contacts"):
        fc = win._frame_contacts(win.timeline.value(), lab)
        if mode == "contact_state":                    # categorical → no bar
            lut = np.zeros((mx + 1, 4), dtype=np.ubyte)
            for cid, r in fc.items():
                if 0 < cid < lut.shape[0]:
                    lut[cid] = (*cell_contacts.CONTACT_COLOR[r["contact_class"]], 255)
            return lut, None
        key = "contact_fraction" if mode == "contact_fraction" else "n_contacts"
        vals = {cid: float(r[key]) for cid, r in fc.items()}
        return _continuous(vals, mx, CMAP[mode], _label(mode, um, dt))
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
    cmap, label = CMAP.get(mode, "viridis"), _label(mode, um, dt)
    if win.display.fixed_scale_on():
        gr = _fixed_range(win, mode, um)
        if gr:
            return (scalar_label_lut(vals, mx, cmap, vmin=gr[0], vmax=gr[1]),
                    (gr[0], gr[1], cmap, label))
    return _continuous(vals, mx, cmap, label)
