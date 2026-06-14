"""Per-cell shape / region metrics from a label stack (GUI-free, no skimage).

Moment-based morphometry computed directly with NumPy/SciPy so the package
keeps its light, CPU-only dependency set. The eccentricity and axis-length
definitions match scikit-image's ``regionprops`` (central second moments with
the +1/12 pixel-area correction), so values are comparable to the wider
literature. Perimeter / circularity (which need a robust boundary trace, i.e.
scikit-image) are intentionally omitted — they are also noise-sensitive at this
pixel size; ``solidity`` is provided via a SciPy convex hull when requested.

These are the building blocks for the CSV exporters (``exporters.py``) and the
GUI cell-info panel. Pure functions over ``(T, H, W)`` / ``(H, W)`` int arrays.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import state as _state
from . import motion as _motion


def _region_shape(rows: np.ndarray, cols: np.ndarray) -> dict:
    """Second-moment shape descriptors for one region's pixel coordinates.

    ``rows`` (y) and ``cols`` (x) are float pixel coordinates. Returns the
    centroid, major/minor axis lengths, eccentricity and orientation using the
    same normalised central moments as scikit-image.
    """
    cr = float(rows.mean())
    cc = float(cols.mean())
    dr = rows - cr
    dc = cols - cc
    mrr = float((dr * dr).mean()) + 1.0 / 12.0
    mcc = float((dc * dc).mean()) + 1.0 / 12.0
    mrc = float((dr * dc).mean())
    half = (mrr + mcc) / 2.0
    diff = np.sqrt(((mrr - mcc) / 2.0) ** 2 + mrc * mrc)
    l1 = half + diff
    l2 = max(half - diff, 0.0)
    major = 4.0 * np.sqrt(l1)
    minor = 4.0 * np.sqrt(l2)
    ecc = float(np.sqrt(1.0 - l2 / l1)) if l1 > 0 else 0.0
    orient = 0.5 * float(np.arctan2(2.0 * mrc, (mrr - mcc)))   # major-axis angle
    return {"centroid_row": cr, "centroid_col": cc, "major_axis": major,
            "minor_axis": minor, "eccentricity": ecc, "orientation": orient}


def _solidity(rows: np.ndarray, cols: np.ndarray, area: int) -> float:
    """area / convex-hull area, via a SciPy 2-D convex hull of pixel centres.

    Approximate (hull of pixel centres slightly under-counts the true filled
    area), so the value is clipped to 1.0; NaN if a hull can't be built.
    """
    try:
        from scipy.spatial import ConvexHull
        pts = np.column_stack([cols, rows]).astype(float)
        if pts.shape[0] < 3:
            return float("nan")
        hull = ConvexHull(pts)                      # .volume == area in 2-D
        return float(min(area / hull.volume, 1.0)) if hull.volume > 0 else float("nan")
    except Exception:
        return float("nan")


def regionprops_frame(labels2d: np.ndarray, um_per_px: float | None = None,
                      with_solidity: bool = False) -> dict:
    """{cell_id: props} for every labelled region in one (H, W) frame.

    Props: area (px and µm² if scaled), centroid (x, y), bounding box,
    major/minor axis, eccentricity, aspect ratio, orientation, extent,
    equivalent diameter, and (optional) solidity.
    """
    labels2d = np.asarray(labels2d)
    H, W = labels2d.shape[-2], labels2d.shape[-1]
    objs = ndimage.find_objects(labels2d)           # index i -> label i+1
    scale = float(um_per_px) if um_per_px else None
    out: dict[int, dict] = {}
    for lab, sl in enumerate(objs, start=1):
        if sl is None:
            continue
        sub = labels2d[sl] == lab
        rr, cc = np.nonzero(sub)
        if rr.size == 0:
            continue
        rows = (rr + sl[0].start).astype(float)
        cols = (cc + sl[1].start).astype(float)
        sh = _region_shape(rows, cols)
        area = int(rr.size)
        bbox_h = sl[0].stop - sl[0].start
        bbox_w = sl[1].stop - sl[1].start
        minor = sh["minor_axis"]
        rec = {
            "cell_id": lab,
            "area_px": area,
            "centroid_x": sh["centroid_col"],
            "centroid_y": sh["centroid_row"],
            "bbox_x0": int(sl[1].start), "bbox_y0": int(sl[0].start),
            "bbox_x1": int(sl[1].stop), "bbox_y1": int(sl[0].stop),
            "major_axis_px": sh["major_axis"],
            "minor_axis_px": minor,
            "eccentricity": sh["eccentricity"],
            "aspect_ratio": (sh["major_axis"] / minor) if minor > 0 else np.nan,
            "orientation_rad": sh["orientation"],
            "extent": area / (bbox_h * bbox_w) if bbox_h * bbox_w else np.nan,
            "equiv_diameter_px": float(np.sqrt(4.0 * area / np.pi)),
            "edge": bool(sl[1].start == 0 or sl[0].start == 0
                         or sl[1].stop >= W or sl[0].stop >= H),
        }
        if scale:
            rec["area_um2"] = area * scale * scale
            rec["centroid_x_um"] = sh["centroid_col"] * scale
            rec["centroid_y_um"] = sh["centroid_row"] * scale
            rec["major_axis_um"] = sh["major_axis"] * scale
            rec["minor_axis_um"] = minor * scale
            rec["equiv_diameter_um"] = rec["equiv_diameter_px"] * scale
        if with_solidity:
            rec["solidity"] = _solidity(rows, cols, area)
        rec["state"] = _state.classify_state(
            area, rec.get("area_um2"), rec["eccentricity"],
            solidity=rec.get("solidity"), edge=rec["edge"])
        out[lab] = rec
    return out


def per_frame_records(labels: np.ndarray, um_per_px: float | None = None,
                      dt_min: float | None = None,
                      with_solidity: bool = False, progress_cb=None) -> list:
    """Flat list of per-(cell, frame) row dicts across a (T, H, W) stack.

    ``progress_cb(done, total)`` is called after each frame if given (for a GUI
    progress bar); it must be cheap and thread-safe.
    """
    labels = np.asarray(labels)
    T = labels.shape[0]
    rows: list[dict] = []
    for t in range(T):
        props = regionprops_frame(labels[t], um_per_px, with_solidity)
        for lab in sorted(props):
            row = {"frame": int(t)}
            if dt_min:
                row["time_min"] = t * float(dt_min)
            row.update(props[lab])
            rows.append(row)
        if progress_cb:
            progress_cb(t + 1, T)
    return rows


def centroid_history(labels: np.ndarray) -> dict:
    """{cell_id: (T, 2) (y, x) centroid in px, NaN where absent}.

    Fast path for the GUI (track trails / ID labels): one ``find_objects`` scan
    per frame rather than a full-array compare per cell.
    """
    labels = np.asarray(labels)
    T = labels.shape[0]
    ids = np.unique(labels)
    out = {int(c): np.full((T, 2), np.nan) for c in ids[ids > 0]}
    for t in range(T):
        for lab, rec in regionprops_frame(labels[t]).items():
            if lab in out:
                out[lab][t] = (rec["centroid_y"], rec["centroid_x"])
    return out


def cell_series(labels: np.ndarray, cell_id: int, um_per_px: float | None = None,
                dt_min: float | None = None) -> dict:
    """Per-frame area + centroid for one cell (for the cell-info panel).

    Returns dict of arrays over present frames: ``frame``, ``time_min``,
    ``area`` (µm² if scaled else px), ``centroid`` (T,2 px, NaN absent).
    """
    labels = np.asarray(labels)
    T = labels.shape[0]
    cen = np.full((T, 2), np.nan)
    area = np.full(T, np.nan)
    a2 = (float(um_per_px) ** 2) if um_per_px else 1.0
    for t in range(T):
        m = labels[t] == cell_id
        n = int(m.sum())
        if n:
            area[t] = n * a2
            rr, cc = np.nonzero(m)
            cen[t] = (rr.mean(), cc.mean())
    frames = np.where(np.isfinite(area))[0]
    return {"frame": frames,
            "time_min": frames * float(dt_min) if dt_min else frames.astype(float),
            "area": area[frames], "area_all": area, "centroid": cen,
            "area_unit": "µm²" if um_per_px else "px"}


def _ylabel(key: str, u: str) -> str:
    if key.startswith("intensity_"):
        return f"{key[10:]} mean intensity"
    return {"area": f"area ({u}²)", "eccentricity": "eccentricity",
            "aspect_ratio": "aspect ratio", "major_axis": f"major axis ({u})",
            "minor_axis": f"minor axis ({u})", "orientation": "orientation (rad)",
            "extent": "extent", "equiv_diameter": f"equiv. diameter ({u})",
            "solidity": "solidity",
            "state_code": "state (0=unk,1=spread,2=round,3=edge)"
            }.get(key, key.replace("_", " "))


def cell_frame_table(labels: np.ndarray, cell_id: int, um_per_px=None,
                     dt_min=None, recording=None, with_solidity=True) -> dict:
    """Rich per-frame metrics for ONE cell (for the cell-info panel / plots).

    Returns {frame, time_min, series{name: (values, ylabel)}, summary}. ``series``
    covers morphometry (area, eccentricity, aspect ratio, axes, orientation,
    extent, equiv diameter, solidity), per-frame ``state_code``, motion-derived
    (speed, displacement_from_start, turning_angle) and — if ``recording`` is
    given — mean intensity of each channel inside the mask (e.g. SiR-actin Cy5).
    """
    labels = np.asarray(labels)
    T = labels.shape[0]
    H, W = labels.shape[-2], labels.shape[-1]
    scale = float(um_per_px) if um_per_px else None
    u = "µm" if scale else "px"
    cen = np.full((T, 2), np.nan)
    frames: list = []
    recs: list = []
    for t in range(T):
        m = labels[t] == cell_id
        area = int(m.sum())
        if area == 0:
            continue
        rr, cc = np.nonzero(m)
        rows, cols = rr.astype(float), cc.astype(float)
        sh = _region_shape(rows, cols)
        cen[t] = (sh["centroid_row"], sh["centroid_col"])
        y0, y1, x0, x1 = int(rr.min()), int(rr.max()), int(cc.min()), int(cc.max())
        minor = sh["minor_axis"]
        area_um2 = area * scale * scale if scale else None
        rec = {
            "area": area_um2 if scale else area,
            "eccentricity": sh["eccentricity"],
            "aspect_ratio": sh["major_axis"] / minor if minor > 0 else np.nan,
            "major_axis": sh["major_axis"] * (scale or 1.0),
            "minor_axis": minor * (scale or 1.0),
            "orientation": sh["orientation"],
            "extent": area / ((y1 - y0 + 1) * (x1 - x0 + 1)),
            "equiv_diameter": np.sqrt(4.0 * area / np.pi) * (scale or 1.0),
        }
        if with_solidity:
            rec["solidity"] = _solidity(rows, cols, area)
        edge = bool(x0 == 0 or y0 == 0 or x1 >= W - 1 or y1 >= H - 1)
        rec["state_code"] = _state.STATE_CODE[_state.classify_state(
            area, area_um2, sh["eccentricity"], solidity=rec.get("solidity"),
            edge=edge)]
        if recording is not None:
            for c in range(recording.n_channels):
                name = recording.channel_names[c] or f"ch{c}"
                rec[f"intensity_{name}"] = float(recording.frame(t, c)[m].mean())
        frames.append(t)
        recs.append(rec)

    if not frames:
        return {"frame": np.array([]), "time_min": np.array([]), "series": {},
                "summary": {}}
    fr = np.array(frames)
    times = fr * float(dt_min) if dt_min else fr.astype(float)
    series = {k: (np.array([r.get(k, np.nan) for r in recs], float), _ylabel(k, u))
              for k in recs[0]}
    cen_um = cen * scale if scale else cen
    pres = cen_um[fr]
    speed = np.full(fr.size, np.nan)
    if fr.size >= 2:
        seg = np.sqrt((np.diff(pres, axis=0) ** 2).sum(axis=1))
        speed[1:] = seg / float(dt_min) if dt_min else seg
    series["speed"] = (speed, f"speed ({u}/{'min' if dt_min else 'frame'})")
    series["displacement_from_start"] = (
        np.sqrt(((pres - pres[0]) ** 2).sum(axis=1)), f"displacement ({u})")
    turn = np.full(fr.size, np.nan)
    if fr.size >= 3:
        turn[1:-1] = _motion.turning_angles(pres)
    series["turning_angle"] = (turn, "turning angle (rad)")
    return {"frame": fr, "time_min": times, "series": series,
            "summary": _motion.motion_summary(cen_um, dt_min),
            "centroid_um": cen_um, "dt": dt_min, "scaled": bool(scale)}
