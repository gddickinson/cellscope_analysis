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
from . import neighbors as _nbr
from . import membrane as _membrane
from . import contacts as _contacts

# Crofton perimeter weights (identical to scikit-image's regionprops perimeter,
# neighborhood=4) so circularity is comparable to the wider literature.
_PERIM_W = np.zeros(50)
_PERIM_W[[5, 7, 15, 17, 25, 27]] = 1.0
_PERIM_W[[21, 33]] = np.sqrt(2)
_PERIM_W[[13, 23]] = (1 + np.sqrt(2)) / 2.0
_PERIM_KERNEL = np.array([[10, 2, 10], [2, 1, 2], [10, 2, 10]])


def _perimeter(mask: np.ndarray) -> float:
    """Boundary perimeter (px) of a 2-D boolean mask (Crofton estimate)."""
    img = mask.astype(np.uint8)
    border = img - ndimage.binary_erosion(img, border_value=0).astype(np.uint8)
    conv = ndimage.convolve(border, _PERIM_KERNEL, mode="constant", cval=0)
    return float(np.bincount(conv.ravel(), minlength=50)[:50] @ _PERIM_W)


def _convexity(rows: np.ndarray, cols: np.ndarray, perimeter_px: float) -> float:
    """Convex-hull perimeter / actual perimeter (≤1; lower = ruffled boundary).

    Perimeter-based (unlike solidity, which is area-based) so it is far more
    sensitive to fine membrane ruffling / blebbing — an actin-protrusion readout.
    """
    if perimeter_px <= 0:
        return float("nan")
    try:
        from scipy.spatial import ConvexHull
        pts = np.column_stack([cols, rows]).astype(float)
        if pts.shape[0] < 3:
            return float("nan")
        return float(min(ConvexHull(pts).area / perimeter_px, 1.0))  # 2-D .area = perim
    except Exception:
        return float("nan")


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
                      with_solidity: bool = False,
                      with_perimeter: bool = False) -> dict:
    """{cell_id: props} for every labelled region in one (H, W) frame.

    Props: area (px and µm² if scaled), centroid (x, y), bounding box,
    major/minor axis, eccentricity, aspect ratio, orientation, extent,
    equivalent diameter, edge flag, state, and (optional) solidity /
    perimeter + circularity.
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
        if with_perimeter:
            per_px = _perimeter(sub)
            rec["perimeter_px"] = per_px
            rec["circularity"] = (4.0 * np.pi * area / (per_px * per_px)
                                  if per_px > 0 else np.nan)
            rec["convexity"] = _convexity(rows, cols, per_px)
            if scale:
                rec["perimeter_um"] = per_px * scale
        rec["state"] = _state.classify_state(
            area, rec.get("area_um2"), rec["eccentricity"],
            solidity=rec.get("solidity"), edge=rec["edge"])
        out[lab] = rec
    return out


def per_frame_records(labels: np.ndarray, um_per_px: float | None = None,
                      dt_min: float | None = None,
                      with_solidity: bool = False, progress_cb=None,
                      with_contacts: bool = True) -> list:
    """Flat list of per-(cell, frame) row dicts across a (T, H, W) stack.

    ``progress_cb(done, total)`` is called after each frame if given (for a GUI
    progress bar); it must be cheap and thread-safe. ``with_contacts`` adds the
    cell–cell contact columns (interface extent + free/point/extensive class).
    """
    labels = np.asarray(labels)
    T = labels.shape[0]
    scale = float(um_per_px) if um_per_px else 1.0
    nn_key = f"nn_dist_{'um' if um_per_px else 'px'}"
    clen_key = f"contact_length_{'um' if um_per_px else 'px'}"
    rows: list[dict] = []
    for t in range(T):
        props = regionprops_frame(labels[t], um_per_px, with_solidity,
                                  with_perimeter=True)
        ids = sorted(props)
        nn, cnt = _nbr.frame_nn([props[i]["centroid_y"] for i in ids],
                                [props[i]["centroid_x"] for i in ids], scale)
        fc = _contacts.frame_contacts(labels[t], scale) if with_contacts else None
        for j, lab in enumerate(ids):
            row = {"frame": int(t)}
            if dt_min:
                row["time_min"] = t * float(dt_min)
            row.update(props[lab])
            row[nn_key] = float(nn[j])
            row["n_neighbors"] = int(cnt[j])
            if fc is not None:
                cr = fc.get(lab)
                if cr is not None:
                    row["n_contacts"] = int(cr["n_contacts"])
                    row["contact_fraction"] = float(cr["contact_fraction"])
                    row["max_contact_fraction"] = float(cr["max_contact_fraction"])
                    row[clen_key] = float(cr["contact_length"])
                    row["contact_state"] = cr["contact_class"]
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
    if key.startswith("membrane_contrast_"):
        return f"{key[18:]} membrane contrast"
    if key.startswith("boundary_grad_"):
        return f"{key[14:]} boundary gradient"
    if key.startswith("membrane_score_"):
        return f"{key[15:]} membrane score"
    return {"area": f"area ({u}²)", "eccentricity": "eccentricity",
            "aspect_ratio": "aspect ratio", "major_axis": f"major axis ({u})",
            "minor_axis": f"minor axis ({u})", "orientation": "orientation (rad)",
            "extent": "extent", "equiv_diameter": f"equiv. diameter ({u})",
            "solidity": "solidity", "perimeter": f"perimeter ({u})",
            "circularity": "circularity", "convexity": "convexity (hull / perim)",
            "rel_area": "rel. area (/90th pct)",
            "state_code": "state (0=unk,1=spread,2=round,3=edge)",
            "shape_mode": "shape mode (cluster)",
            "speed": f"speed ({u}/frame)",
            "displacement_from_start": f"displacement ({u})",
            "turning_angle": "turning angle (rad)",
            "iou_prev": "IoU vs previous frame",
            "area_change": "relative area change",
            "nn_dist": f"NN distance ({u})",
            "n_neighbors": f"neighbours (≤{int(_nbr.DEFAULT_RADIUS_UM)} {u})",
            "contact_fraction": "boundary in contact (fraction)",
            "max_contact_fraction": "largest contact (fraction)",
            "n_contacts": "cells in contact (count)",
            "contact_length": f"contact interface ({u})",
            "contact_state_code": "contact (0=free,1=point,2=extensive)",
            }.get(key, key.replace("_", " "))


# Per-frame metrics the cell-plot Config menu can switch on/off. Intensity /
# membrane-contrast keys are appended at runtime from the recording's channels.
BASE_FRAME_METRICS = ["area", "rel_area", "perimeter", "circularity",
                      "convexity", "eccentricity", "aspect_ratio", "solidity",
                      "major_axis", "minor_axis", "orientation", "extent",
                      "equiv_diameter", "state_code", "shape_mode", "speed",
                      "displacement_from_start", "turning_angle", "iou_prev",
                      "area_change", "nn_dist", "n_neighbors",
                      "contact_fraction", "n_contacts", "contact_length",
                      "contact_state_code"]

# The cheap, always-useful subset enabled by default in the Cell-Info plot menu so a
# fresh session stays fast — every one comes from the per-frame moment pass or the
# centroid track (no convex hull, perimeter trace, per-channel sampling or contact
# KD-tree). Everything else (perimeter/circularity/convexity, solidity, intensity /
# membrane, nearest-neighbour, contacts, shape mode, …) is opt-in via Config.
DEFAULT_PLOT_METRICS = ["area", "eccentricity", "aspect_ratio", "extent",
                        "state_code", "speed", "displacement_from_start",
                        "turning_angle"]


def available_frame_metrics(channel_names=None) -> list:
    """All selectable per-frame metric keys (intensity / membrane-contrast keys
    depend on the loaded recording's channels)."""
    keys = list(BASE_FRAME_METRICS)
    if channel_names:
        for i, n in enumerate(channel_names):
            nm = n or f"ch{i}"
            keys += [f"intensity_{nm}", f"membrane_contrast_{nm}",
                     f"boundary_grad_{nm}", f"membrane_score_{nm}"]
    return keys


def metric_label(key: str, um_per_px=None) -> str:
    """Human-readable label for a per-frame metric key."""
    return _ylabel(key, "µm" if um_per_px else "px")


def cell_frame_table(labels: np.ndarray, cell_id: int, um_per_px=None,
                     dt_min=None, recording=None, with_solidity=True,
                     metrics=None, neighbor_history=None,
                     nn_radius=None, shape_model=None) -> dict:
    """Rich per-frame metrics for ONE cell (for the cell-info panel / plots).

    Returns {frame, time_min, series{name: (values, ylabel)}, summary}. ``series``
    covers morphometry (area, eccentricity, aspect ratio, axes, orientation,
    extent, equiv diameter, solidity), per-frame ``state_code``, motion-derived
    (speed, displacement_from_start, turning_angle), nearest-neighbour distance /
    count (when ``neighbor_history`` is given) and — if ``recording`` is given —
    mean intensity of each channel inside the mask (e.g. SiR-actin Cy5).

    ``metrics`` (an iterable of keys) restricts which series are computed +
    returned, so unselected/expensive ones (solidity, intensity, nn) are skipped.
    """
    labels = np.asarray(labels)
    nn_radius = _nbr.DEFAULT_RADIUS_UM if nn_radius is None else nn_radius
    T = labels.shape[0]
    H, W = labels.shape[-2], labels.shape[-1]
    scale = float(um_per_px) if um_per_px else None
    u = "µm" if scale else "px"
    want = set(metrics) if metrics is not None else None
    want_sol = ("solidity" in want) if want is not None else with_solidity
    cen = np.full((T, 2), np.nan)
    frames: list = []
    recs: list = []
    want_per = want is None or bool({"perimeter", "circularity", "convexity"} & want)
    want_iou = want is None or bool({"iou_prev", "area_change"} & want)
    want_contact = want is None or bool(
        {"contact_fraction", "n_contacts", "contact_length",
         "max_contact_fraction", "contact_state_code"} & want)
    want_mem = recording is not None and (
        want is None or any(k.startswith(("membrane_contrast_", "boundary_grad_",
                                          "membrane_score_")) for k in want))
    prev_m = None
    prev_area = 0
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
        if want_sol:
            rec["solidity"] = _solidity(rows, cols, area)
        if want_per:
            per_px = _perimeter(m[y0:y1 + 1, x0:x1 + 1])
            rec["perimeter"] = per_px * (scale or 1.0)
            rec["circularity"] = (4.0 * np.pi * area / (per_px * per_px)
                                  if per_px > 0 else np.nan)
            rec["convexity"] = _convexity(rows, cols, per_px)
        edge = bool(x0 == 0 or y0 == 0 or x1 >= W - 1 or y1 >= H - 1)
        rec["state_code"] = _state.STATE_CODE[_state.classify_state(
            area, area_um2, sh["eccentricity"], solidity=rec.get("solidity"),
            edge=edge)]
        if want_iou:
            if prev_m is not None:
                union = float(np.logical_or(m, prev_m).sum())
                rec["iou_prev"] = (float(np.logical_and(m, prev_m).sum()) / union
                                   if union else np.nan)
                rec["area_change"] = abs(area - prev_area) / prev_area \
                    if prev_area else np.nan
            else:
                rec["iou_prev"] = np.nan
                rec["area_change"] = np.nan
        if want_contact:                          # cell–cell contact (needs the full frame)
            cr = _contacts.frame_contacts(labels[t], scale or 1.0).get(cell_id)
            if cr is not None:
                rec["contact_fraction"] = cr["contact_fraction"]
                rec["max_contact_fraction"] = cr["max_contact_fraction"]
                rec["n_contacts"] = cr["n_contacts"]
                rec["contact_length"] = cr["contact_length"]
                rec["contact_state_code"] = cr["contact_code"]
        if want_mem:
            ys = slice(max(y0 - 3, 0), min(y1 + 4, H))
            xs = slice(max(x0 - 3, 0), min(x1 + 4, W))
            subm = labels[t][ys, xs] == cell_id
            for c in range(recording.n_channels):
                name = recording.channel_names[c] or f"ch{c}"
                img = recording.frame(t, c)[ys, xs]
                for key, fn in (
                        (f"membrane_contrast_{name}", _membrane.intensity_contrast),
                        (f"boundary_grad_{name}", _membrane.boundary_confidence),
                        (f"membrane_score_{name}", _membrane.membrane_score)):
                    if want is None or key in want:
                        rec[key] = fn(subm, img)
        if recording is not None:
            for c in range(recording.n_channels):
                key = f"intensity_{recording.channel_names[c] or f'ch{c}'}"
                if want is None or key in want:
                    rec[key] = float(recording.frame(t, c)[m].mean())
        prev_m = m
        prev_area = area
        frames.append(t)
        recs.append(rec)

    if not frames:
        return {"frame": np.array([]), "time_min": np.array([]), "series": {},
                "summary": {}}
    fr = np.array(frames)
    times = fr * float(dt_min) if dt_min else fr.astype(float)
    series = {k: (np.array([r.get(k, np.nan) for r in recs], float), _ylabel(k, u))
              for k in recs[0]}
    if want is None or "rel_area" in want:
        areas = np.array([r["area"] for r in recs], float)
        base = np.nanpercentile(areas, 90) if np.isfinite(areas).any() else np.nan
        series["rel_area"] = (areas / base if base else areas * np.nan,
                              "rel. area (/90th pct)")
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
    if neighbor_history is not None and (
            want is None or {"nn_dist", "n_neighbors"} & want):
        nn = np.full(fr.size, np.nan)
        cnt = np.full(fr.size, np.nan)
        for i, t in enumerate(fr):
            others = [oc[t] for oid, oc in neighbor_history.items()
                      if oid != cell_id and np.isfinite(oc[t, 0])]
            if others and np.isfinite(cen[t, 0]):
                d = np.sqrt(((np.array(others) - cen[t]) ** 2).sum(axis=1)) \
                    * (scale or 1.0)
                nn[i] = d.min()
                cnt[i] = int((d <= nn_radius).sum())
        series["nn_dist"] = (nn, _ylabel("nn_dist", u))
        series["n_neighbors"] = (cnt, _ylabel("n_neighbors", u))
    if shape_model is not None and (want is None or "shape_mode" in want):
        bcf = shape_model.get("by_cell_frame", {})
        series["shape_mode"] = (
            np.array([bcf.get((cell_id, int(t)), np.nan) for t in fr], float),
            "shape mode (cluster)")
    if want is not None:
        series = {k: v for k, v in series.items() if k in want}
    return {"frame": fr, "time_min": times, "series": series,
            "summary": _motion.motion_summary(cen_um, dt_min),
            "centroid_um": cen_um, "dt": dt_min, "scaled": bool(scale)}
