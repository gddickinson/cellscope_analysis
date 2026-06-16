"""Edge / membrane dynamics from a tracked cell's masks (GUI-free, no cv2).

Replicates the CellScope radial edge-velocity kymograph so values are
comparable. For each consecutive frame pair the cell boundary is sampled into
``N_SECTORS`` angular sectors about the **mid-centroid** of the two frames
(removing whole-cell translation), the median boundary radius per sector is
taken, and edge velocity = (r_curr − r_prev)·µm/dt — **positive = protrusion,
negative = retraction**. Sectors are angularly smoothed (Savitzky-Golay) and the
kymograph lightly smoothed over time, then aggregated into protrusion /
retraction summary metrics plus a per-sector ruffling (temporal variance).

This is the most PIEZO1-specific readout: KO reduces edge velocities; GOF /
YODA1 increase them, disproportionately retraction (Holt et al. 2021).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

N_SECTORS = 72
ANGULAR_SG_WINDOW = 5             # Savitzky-Golay window for per-frame angular smoothing
TEMPORAL_SIGMA = 1.0             # Gaussian sigma (frames) for temporal kymograph smoothing
POLARITY_FRONT_DEG = 60.0        # half-cone (deg) defining front/rear sectors
_SUMMARY_KEYS = ("mean_protrusion_velocity", "mean_retraction_velocity",
                 "protrusion_fraction", "net_velocity", "max_protrusion",
                 "max_retraction", "ruffling")


def _radii(mask: np.ndarray, center) -> np.ndarray:
    """Median boundary radius (px) per angular sector about ``center`` (row,col)."""
    boundary = mask & ~ndimage.binary_erosion(mask)
    rr, cc = np.nonzero(boundary)
    out = np.full(N_SECTORS, np.nan)
    if rr.size == 0:
        return out
    dy, dx = rr - center[0], cc - center[1]
    radius = np.sqrt(dx * dx + dy * dy)
    bins = ((np.arctan2(dy, dx) + np.pi) / (2 * np.pi) * N_SECTORS).astype(int)
    bins %= N_SECTORS
    for s in range(N_SECTORS):
        m = bins == s
        if m.any():
            out[s] = np.median(radius[m])
    return out


def _interp_circular(v: np.ndarray) -> np.ndarray:
    """Fill NaNs in a periodic 1-D array by circular linear interpolation."""
    good = np.isfinite(v)
    if good.all() or not good.any():
        return v
    n = v.size
    xs, ys = np.where(good)[0], v[good]
    xs_ext = np.concatenate([xs - n, xs, xs + n])
    ys_ext = np.concatenate([ys, ys, ys])
    return np.interp(np.arange(n), xs_ext, ys_ext)


def _smooth_angular(v: np.ndarray) -> np.ndarray:
    try:
        from scipy.signal import savgol_filter
        if np.isfinite(v).sum() >= ANGULAR_SG_WINDOW:
            return savgol_filter(v, ANGULAR_SG_WINDOW, 2, mode="wrap")
    except Exception:
        pass
    return v


def _nan_gaussian1d(mat, sigma):
    """Gaussian smooth down the time axis, ignoring (not propagating) NaNs — a
    normalized convolution, so a missing-edge sector doesn't blank its whole column."""
    finite = np.isfinite(mat).astype(float)
    num = ndimage.gaussian_filter1d(np.where(finite > 0, mat, 0.0), sigma, axis=0)
    den = ndimage.gaussian_filter1d(finite, sigma, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den == 0] = np.nan
    return out


def _present_frames(labels, cell_id):
    return [t for t in range(labels.shape[0]) if (labels[t] == cell_id).any()]


def radius_kymograph(labels, cell_id, um_per_px=None):
    """(present_frames, (n, N_SECTORS) median boundary radius µm) for one cell."""
    labels = np.asarray(labels)
    scale = float(um_per_px) if um_per_px else 1.0
    frames = _present_frames(labels, cell_id)
    mat = np.full((len(frames), N_SECTORS), np.nan)
    for i, t in enumerate(frames):
        m = labels[t] == cell_id
        rr, cc = np.nonzero(m)
        mat[i] = _radii(m, (rr.mean(), cc.mean())) * scale
    return np.array(frames), mat


def edge_velocity_kymograph(labels, cell_id, um_per_px=None, dt_min=None,
                            smooth=True):
    """(later-frame indices, (n_pairs, N_SECTORS) edge velocity) for one cell.

    Velocity is µm/min (µm/frame if no dt); the mid-centroid of each pair is
    used so whole-cell translation does not register as edge motion.
    """
    labels = np.asarray(labels)
    scale = float(um_per_px) if um_per_px else 1.0
    dt = float(dt_min) if dt_min else 1.0
    present = _present_frames(labels, cell_id)
    pairs, vel = [], []
    for a, b in zip(present[:-1], present[1:]):
        ma, mb = labels[a] == cell_id, labels[b] == cell_id
        ra, ca = np.nonzero(ma)
        rb, cb = np.nonzero(mb)
        cen = ((ra.mean() + rb.mean()) / 2.0, (ca.mean() + cb.mean()) / 2.0)
        rprev_raw, rcurr_raw = _radii(ma, cen), _radii(mb, cen)
        if smooth:
            rprev = _smooth_angular(_interp_circular(rprev_raw))
            rcurr = _smooth_angular(_interp_circular(rcurr_raw))
        else:
            rprev, rcurr = rprev_raw, rcurr_raw
        v = (rcurr - rprev) * scale / ((b - a) * dt)
        if smooth:                                 # a sector with no edge pixel in either
            v[~np.isfinite(rprev_raw) | ~np.isfinite(rcurr_raw)] = np.nan  # frame = no measure
        vel.append(v)
        pairs.append(b)
    mat = np.array(vel) if vel else np.zeros((0, N_SECTORS))
    if smooth and mat.shape[0] >= 3:
        mat = _nan_gaussian1d(mat, TEMPORAL_SIGMA)
    return np.array(pairs), mat


def edge_summary(velmat: np.ndarray) -> dict:
    """Protrusion / retraction / ruffling summary from a velocity kymograph."""
    if velmat.size == 0:
        return {k: np.nan for k in _SUMMARY_KEYS}
    v = velmat[np.isfinite(velmat)]
    prot, retr = v[v > 0], v[v < 0]
    # ruffling = mean per-sector temporal std, over sectors with ≥2 samples
    enough = np.isfinite(velmat).sum(axis=0) >= 2
    ruffle = float(np.nanmean(np.nanstd(velmat[:, enough], axis=0))) \
        if enough.any() else np.nan
    return {
        "mean_protrusion_velocity": float(prot.mean()) if prot.size else np.nan,
        "mean_retraction_velocity": float(retr.mean()) if retr.size else np.nan,
        "protrusion_fraction": float((v > 0).mean()) if v.size else np.nan,
        "net_velocity": float(v.mean()) if v.size else np.nan,
        "max_protrusion": float(v.max()) if v.size else np.nan,
        "max_retraction": float(v.min()) if v.size else np.nan,
        "ruffling": ruffle,
    }


def _runs(flags, min_len):
    """[(start, stop)] contiguous True runs of length ≥ min_len."""
    runs, i, n = [], 0, len(flags)
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            if j - i >= min_len:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


_EVENT_KEYS = ("n_protrusions", "n_retractions", "protrusion_event_rate",
               "retraction_event_rate", "mean_protrusion_duration",
               "mean_retraction_duration", "mean_protrusion_strength",
               "mean_retraction_strength")


def edge_events(velmat, dt_min=None, thresh=None, min_len=2) -> dict:
    """Discrete protrusion/retraction events on the velocity kymograph (ADAPT-
    style): per angular sector, time-runs where velocity stays above +thresh
    (protrusion) or below −thresh (retraction) for ≥ ``min_len`` frames. Default
    threshold = ½·std of the edge velocity. Returns counts, event rates (per
    sector·min), and mean duration / strength."""
    if velmat.size == 0:
        return {k: np.nan for k in _EVENT_KEYS}
    fin = velmat[np.isfinite(velmat)]
    thr = thresh if thresh is not None else (0.5 * float(np.nanstd(fin))
                                             if fin.size else 0.0)
    dt = float(dt_min) if dt_min else 1.0
    nframes, nsec = velmat.shape
    pdur, pstr, rdur, rstr = [], [], [], []
    for s in range(nsec):
        col = velmat[:, s]
        c = np.nan_to_num(col)
        for a, b in _runs(c > thr, min_len):
            pdur.append((b - a) * dt)
            pstr.append(float(np.nanmean(col[a:b])))
        for a, b in _runs(c < -thr, min_len):
            rdur.append((b - a) * dt)
            rstr.append(float(np.nanmean(col[a:b])))
    span = nframes * dt * nsec
    return {
        "n_protrusions": len(pdur), "n_retractions": len(rdur),
        "protrusion_event_rate": len(pdur) / span if span else np.nan,
        "retraction_event_rate": len(rdur) / span if span else np.nan,
        "mean_protrusion_duration": float(np.mean(pdur)) if pdur else np.nan,
        "mean_retraction_duration": float(np.mean(rdur)) if rdur else np.nan,
        "mean_protrusion_strength": float(np.mean(pstr)) if pstr else np.nan,
        "mean_retraction_strength": float(np.mean(rstr)) if rstr else np.nan,
    }


_POLARITY_KEYS = ("front_velocity", "rear_velocity", "side_velocity",
                  "polarity_index", "rear_retraction_fraction")


def edge_polarity(labels, cell_id, um_per_px=None, dt_min=None, front_deg=None,
                  pairs=None, vel=None) -> dict:
    """Edge velocity resolved in the **migration-direction frame**.

    Each frame-pair's angular sectors are rotated by the cell's instantaneous
    migration direction (centroid displacement), so 'front' sectors point the way
    the cell is going and 'rear' sectors point opposite. ``front_deg`` is the
    half-cone (deg): front = within it of forward, rear = within it of backward,
    else side. Reports mean front / rear / side edge velocity (+protrusion /
    −retraction), a ``polarity_index`` (front − rear; large when the front protrudes
    and the rear retracts) and ``rear_retraction_fraction`` (share of all retraction
    happening at the rear — the PIEZO1 rear-retraction signature). Pass a precomputed
    ``pairs`` / ``vel`` (from ``edge_velocity_kymograph``) to avoid recomputing."""
    if front_deg is None:
        front_deg = POLARITY_FRONT_DEG
    labels = np.asarray(labels)
    if pairs is None or vel is None:
        pairs, vel = edge_velocity_kymograph(labels, cell_id, um_per_px, dt_min)
    if vel.size == 0:
        return {k: np.nan for k in _POLARITY_KEYS}
    present = _present_frames(labels, cell_id)
    cents = {}
    for t in present:
        rr, cc = np.nonzero(labels[t] == cell_id)
        cents[t] = (rr.mean(), cc.mean())
    centers = (np.arange(N_SECTORS) + 0.5) / N_SECTORS * 2 * np.pi - np.pi
    fh = np.deg2rad(front_deg)
    fv, rv, sv = [], [], []
    for i, b in enumerate(pairs):
        a = present[i]                                # pairs[i] == present[i+1]
        dy, dx = cents[b][0] - cents[a][0], cents[b][1] - cents[a][1]
        if dy == 0 and dx == 0:
            continue                                  # no migration → no front/rear
        rel = np.abs(((centers - np.arctan2(dy, dx) + np.pi) % (2 * np.pi)) - np.pi)
        row = vel[i]
        for bucket, sel in ((fv, rel <= fh), (rv, rel >= np.pi - fh),
                            (sv, (rel > fh) & (rel < np.pi - fh))):
            bucket.extend(row[sel][np.isfinite(row[sel])].tolist())
    fv, rv, sv = np.array(fv), np.array(rv), np.array(sv)
    allv = np.concatenate([fv, rv, sv]) if fv.size + rv.size + sv.size else np.array([])
    retr = allv[allv < 0]
    rear_retr = rv[rv < 0]
    return {
        "front_velocity": float(fv.mean()) if fv.size else np.nan,
        "rear_velocity": float(rv.mean()) if rv.size else np.nan,
        "side_velocity": float(sv.mean()) if sv.size else np.nan,
        "polarity_index": (float(fv.mean() - rv.mean())
                           if fv.size and rv.size else np.nan),
        "rear_retraction_fraction": (float(rear_retr.sum() / retr.sum())
                                     if retr.sum() != 0 else np.nan),
    }


def edge_summary_for_cell(labels, cell_id, um_per_px=None, dt_min=None) -> dict:
    """Convenience: velocity kymograph → summary + event + polarity metrics."""
    labels = np.asarray(labels)
    pairs, mat = edge_velocity_kymograph(labels, cell_id, um_per_px, dt_min)
    out = edge_summary(mat)
    out.update(edge_events(mat, dt_min))
    out.update(edge_polarity(labels, cell_id, pairs=pairs, vel=mat))
    return out
