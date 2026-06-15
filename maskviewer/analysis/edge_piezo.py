"""Edge-change ↔ cortical fluorescence correlation (e.g. tagged PIEZO1).

When a fluorescence channel is available (tagged PIEZO1, SiR-actin, …), measure
its intensity in a thin cortical band per angular sector per frame — a
"fluorescence kymograph" matched to the edge-velocity kymograph
(`edge_dynamics`) — then correlate edge velocity against cortical intensity
across (frame, sector). Positive r → the channel is enriched where the membrane
protrudes; negative r → enriched at retracting edges (PIEZO1 is reported to rise
at the retracting rear, Holt et al. 2021). The per-cell Pearson r is a
scale-free, directly comparable readout for cross-treatment comparison.

GUI-free; reuses the 72 angular sectors / present-frame logic of `edge_dynamics`.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import edge_dynamics

N_SECTORS = edge_dynamics.N_SECTORS
BAND_PX = 3                      # cortical band thickness (px) sampled inward
_SUMMARY_KEYS = ("edge_piezo_pearson", "edge_piezo_spearman",
                 "piezo_at_protrusion", "piezo_at_retraction",
                 "piezo_protr_minus_retr", "edge_piezo_lag1", "n_edge_piezo")


def fluor_kymograph(labels, image, cell_id, band_px=BAND_PX):
    """(present_frames, (n, N_SECTORS)) mean intensity of ``image`` (T, H, W) in
    an inner cortical band (≤ ``band_px`` px from the boundary) per angular sector,
    binned about each frame's centroid (same sectors as the velocity kymograph)."""
    labels = np.asarray(labels)
    frames = edge_dynamics._present_frames(labels, cell_id)
    mat = np.full((len(frames), N_SECTORS), np.nan)
    for i, t in enumerate(frames):
        m = labels[t] == cell_id
        band = m & ~ndimage.binary_erosion(m, iterations=int(band_px))
        if not band.any():
            band = m
        rr, cc = np.nonzero(band)
        my, mx = np.nonzero(m)
        cy, cx = my.mean(), mx.mean()
        sect = (((np.arctan2(rr - cy, cc - cx) + np.pi) / (2 * np.pi) * N_SECTORS)
                .astype(int)) % N_SECTORS
        vals = np.asarray(image[t], float)[rr, cc]
        for s in range(N_SECTORS):
            sel = sect == s
            if sel.any():
                mat[i, s] = float(vals[sel].mean())
    return np.array(frames), mat


def _pearson(a, b):
    if a.size < 3 or a.std() == 0 or b.std() == 0:
        return np.nan
    return float(((a - a.mean()) * (b - b.mean())).mean() / (a.std() * b.std()))


def aligned_pairs(vfr, velmat, pfr, piezomat, lag=0):
    """Flattened finite (edge_velocity, cortical_intensity) pairs across all
    (frame, sector). lag=0 → intensity at the pair's later frame; lag=1 → one
    present-frame earlier ('fluorescence leads the edge change')."""
    if velmat.size == 0 or piezomat.size == 0:
        return np.array([]), np.array([])
    pindex = {int(f): j for j, f in enumerate(pfr)}
    vs, ps = [], []
    for k, fr in enumerate(vfr):
        j = pindex.get(int(fr))
        if j is None or j - lag < 0:
            continue
        vv, pp = velmat[k], piezomat[j - lag]
        ok = np.isfinite(vv) & np.isfinite(pp)
        vs.append(vv[ok]); ps.append(pp[ok])
    v = np.concatenate(vs) if vs else np.array([])
    p = np.concatenate(ps) if ps else np.array([])
    return v, p


def edge_fluor_correlation(vfr, velmat, pfr, piezomat):
    """Correlate edge velocity (per frame-pair, later-frame indices ``vfr``) with
    cortical fluorescence per sector. Returns Pearson + Spearman r at lag 0
    (intensity at the pair's *later* frame), the mean intensity at protruding vs
    retracting sectors (and their difference), a lag-1 r (intensity one frame
    *earlier* → 'fluorescence leads the edge change'), and the sample count."""
    out = {k: np.nan for k in _SUMMARY_KEYS}
    out["n_edge_piezo"] = 0
    if velmat.size == 0 or piezomat.size == 0:
        return out
    v0, p0 = aligned_pairs(vfr, velmat, pfr, piezomat, lag=0)
    out["n_edge_piezo"] = int(v0.size)
    if v0.size >= 3:
        out["edge_piezo_pearson"] = _pearson(v0, p0)
        try:
            from scipy.stats import spearmanr
            out["edge_piezo_spearman"] = float(spearmanr(v0, p0).correlation)
        except Exception:
            pass
        prot, retr = p0[v0 > 0], p0[v0 < 0]
        if prot.size:
            out["piezo_at_protrusion"] = float(prot.mean())
        if retr.size:
            out["piezo_at_retraction"] = float(retr.mean())
        if prot.size and retr.size:
            out["piezo_protr_minus_retr"] = (out["piezo_at_protrusion"]
                                             - out["piezo_at_retraction"])
    v1, p1 = aligned_pairs(vfr, velmat, pfr, piezomat, lag=1)
    out["edge_piezo_lag1"] = _pearson(v1, p1)
    return out


def edge_fluor_for_cell(labels, image, cell_id, um_per_px=None, dt_min=None):
    """Velocity + fluorescence kymographs + correlation summary for one cell.
    Returns (vfr, velmat, pfr, piezomat, summary)."""
    vfr, velmat = edge_dynamics.edge_velocity_kymograph(labels, cell_id,
                                                        um_per_px, dt_min)
    pfr, piezomat = fluor_kymograph(labels, image, cell_id)
    summary = edge_fluor_correlation(vfr, velmat, pfr, piezomat)
    return vfr, velmat, pfr, piezomat, summary
