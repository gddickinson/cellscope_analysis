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
ANGULAR_SG_WINDOW = 5
TEMPORAL_SIGMA = 1.0
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
        rprev, rcurr = _radii(ma, cen), _radii(mb, cen)
        if smooth:
            rprev = _smooth_angular(_interp_circular(rprev))
            rcurr = _smooth_angular(_interp_circular(rcurr))
        vel.append((rcurr - rprev) * scale / ((b - a) * dt))
        pairs.append(b)
    mat = np.array(vel) if vel else np.zeros((0, N_SECTORS))
    if smooth and mat.shape[0] >= 3:
        mat = ndimage.gaussian_filter1d(mat, TEMPORAL_SIGMA, axis=0)
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
        "mean_protrusion_velocity": float(prot.mean()) if prot.size else 0.0,
        "mean_retraction_velocity": float(retr.mean()) if retr.size else 0.0,
        "protrusion_fraction": float((v > 0).mean()) if v.size else np.nan,
        "net_velocity": float(v.mean()) if v.size else np.nan,
        "max_protrusion": float(v.max()) if v.size else np.nan,
        "max_retraction": float(v.min()) if v.size else np.nan,
        "ruffling": ruffle,
    }


def edge_summary_for_cell(labels, cell_id, um_per_px=None, dt_min=None) -> dict:
    """Convenience: velocity kymograph → summary dict for one cell."""
    _, mat = edge_velocity_kymograph(labels, cell_id, um_per_px, dt_min)
    return edge_summary(mat)
