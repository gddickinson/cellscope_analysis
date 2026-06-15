"""Edge-movement ↔ fluorescence-intensity correlation (e.g. tagged PIEZO1).

A faithful reproduction of the lab's ``cell_edge_analysis`` PIEZO1 pipeline
(steps 3–9: local edge displacement → classify extruding/retracting/stable →
**sampling rectangles into the cell** → mean fluorescence per rectangle → pair
each intensity with its local edge displacement → correlate), **adapted to this
project's closed, tracked cells**.

The original works on a single advancing edge ``y(x)``: per x-column it takes
the displacement of the uppermost edge point between frames, samples PIEZO1 in a
vertical rectangle reaching into the cell, and correlates that intensity with the
local displacement. Here a cell is a closed contour, so the equivalent of the
"per-x edge displacement" is the **per-sector radial edge velocity** about the
mid-centroid (`edge_dynamics`, translation-removed), and the equivalent of the
"vertical rectangle into the cell" is a rectangle along the **inward normal**
(toward the centroid) at each sector's boundary point.

Method per cell, over its present frames:
  * boundary sampled into ``N_SECTORS`` directions (same sectors as the velocity
    kymograph);
  * at each sector, a ``depth``×``width`` px rectangle reaches inward from the
    boundary point; its mean fluorescence (over in-cell pixels, coverage-gated)
    is the local intensity — `intensity_kymograph`;
  * each intensity (frame *t*) is paired with the local signed edge displacement
    (positive = protrusion / outward; negative = retraction / inward) of the
    pair ending at *t* (``temporal='past'``) or starting at *t* (``'future'``);
  * over all (displacement, intensity) pairs: Pearson **r / R² / p / slope**, the
    mean intensity of **protruding vs retracting vs stable** points (split at a
    displacement threshold), their difference, and a t-test + Mann–Whitney
    between protruding and retracting intensities — `correlation_summary`.

A per-cell **r** is scale-free and the headline cross-treatment readout:
``r > 0`` → the channel is brighter where the edge protrudes; ``r < 0`` → brighter
where it retracts (PIEZO1 is reported to rise at the retracting rear,
Holt et al. 2021). GUI-free, no cv2.
"""
from __future__ import annotations

import numpy as np

from . import edge_dynamics

N_SECTORS = edge_dynamics.N_SECTORS
DEPTH_PX = 12                    # rectangle reach into the cell (px)
WIDTH_PX = 7                     # rectangle width along the edge (px)
MIN_COVERAGE = 0.3               # min fraction of the rectangle inside the cell
_SUMMARY_KEYS = (
    "edge_move_intensity_r", "edge_move_intensity_r2", "edge_move_intensity_p",
    "edge_move_intensity_slope", "piezo_at_protrusion", "piezo_at_retraction",
    "piezo_protr_minus_retr", "protr_retr_ttest_p", "protr_retr_mwu_p",
    "n_protruding", "n_retracting", "n_stable", "n_edge_intensity",
)


def _pearson(a, b):
    if a.size < 3 or a.std() == 0 or b.std() == 0:
        return np.nan
    return float(((a - a.mean()) * (b - b.mean())).mean() / (a.std() * b.std()))


def _frame_centroid(mask):
    rr, cc = np.nonzero(mask)
    return rr.mean(), cc.mean()


def _sector_geometry(center, radii):
    """Boundary point, inward unit normal and tangent (unit) per sector.

    Sector angles match `edge_dynamics` (``bins = (atan2(dy,dx)+π)/2π·N``), so an
    outward unit vector in (row, col) is ``(sinθ, cosθ)``.
    """
    cy, cx = center
    theta = -np.pi + (np.arange(N_SECTORS) + 0.5) / N_SECTORS * 2 * np.pi
    out = np.column_stack([np.sin(theta), np.cos(theta)])     # outward unit
    point = np.column_stack([cy + radii * out[:, 0], cx + radii * out[:, 1]])
    inward = -out
    tangent = np.column_stack([out[:, 1], -out[:, 0]])        # ⟂ unit
    return point, inward, tangent


def rectangle_intensity(image_frame, mask_frame, center, radii,
                        depth=DEPTH_PX, width=WIDTH_PX, min_coverage=MIN_COVERAGE,
                        return_corners=False):
    """Mean fluorescence per sector in an inward ``depth``×``width`` px rectangle.

    For each sector with a finite boundary radius, a rectangle reaches ``depth``
    px inward from the boundary point (``width`` px along the edge). Pixels inside
    the cell mask are averaged; a sector is NaN if too little of its rectangle
    lies in the cell (< ``min_coverage``). Returns ``(N_SECTORS,)`` intensities
    (and, if asked, ``(N_SECTORS, 4, 2)`` rectangle corners in (row, col))."""
    img = np.asarray(image_frame, float)
    h, w = mask_frame.shape
    point, inward, tangent = _sector_geometry(center, radii)
    nd, nw = max(2, int(round(depth))), max(2, int(round(width)))
    ds = np.linspace(0.0, depth, nd)
    ws = np.linspace(-width / 2.0, width / 2.0, nw)
    out = np.full(N_SECTORS, np.nan)
    corners = np.full((N_SECTORS, 4, 2), np.nan)
    for s in range(N_SECTORS):
        if not np.isfinite(radii[s]):
            continue
        grid = (point[s] + inward[s] * ds[:, None, None]
                + tangent[s] * ws[None, :, None]).reshape(-1, 2)
        ri = np.rint(grid[:, 0]).astype(int)
        ci = np.rint(grid[:, 1]).astype(int)
        inb = (ri >= 0) & (ri < h) & (ci >= 0) & (ci < w)
        incell = np.zeros(grid.shape[0], bool)
        incell[inb] = mask_frame[ri[inb], ci[inb]]
        if incell.mean() < min_coverage:
            continue
        out[s] = float(img[ri[incell], ci[incell]].mean())
        if return_corners:
            hw = tangent[s] * (width / 2.0)
            corners[s] = np.array([point[s] + hw, point[s] + hw + inward[s] * depth,
                                   point[s] - hw + inward[s] * depth, point[s] - hw])
    return (out, corners) if return_corners else out


def intensity_kymograph(labels, image, cell_id, depth=DEPTH_PX, width=WIDTH_PX):
    """(present_frames, (n, N_SECTORS)) mean rectangle fluorescence per sector."""
    labels = np.asarray(labels)
    frames = edge_dynamics._present_frames(labels, cell_id)
    mat = np.full((len(frames), N_SECTORS), np.nan)
    for i, t in enumerate(frames):
        m = labels[t] == cell_id
        center = _frame_centroid(m)
        radii = edge_dynamics._radii(m, center)
        mat[i] = rectangle_intensity(image[t], m, center, radii, depth, width)
    return np.array(frames), mat


def movement_intensity_pairs(present, velmat, intmat, temporal="past"):
    """Flattened finite (displacement, intensity) pairs over all (frame, sector).

    ``velmat`` row k is the edge velocity of pair (present[k] → present[k+1]);
    ``intmat`` row k is the rectangle intensity at frame present[k]. ``past``
    pairs an intensity with the movement *into* its frame (intmat[k+1] ↔
    velmat[k]); ``future`` with the movement *out of* it (intmat[k] ↔ velmat[k])."""
    if velmat.size == 0 or intmat.size == 0:
        return np.array([]), np.array([])
    disp, inten = [], []
    for k in range(velmat.shape[0]):
        it = intmat[k + 1] if temporal == "past" else intmat[k]
        ok = np.isfinite(velmat[k]) & np.isfinite(it)
        disp.append(velmat[k][ok]); inten.append(it[ok])
    d = np.concatenate(disp) if disp else np.array([])
    i = np.concatenate(inten) if inten else np.array([])
    return d, i


def correlation_summary(disp, inten, move_threshold=None):
    """Pearson r / R² / p / slope between local edge displacement and intensity,
    plus protruding/retracting/stable counts + mean intensities and a t-test +
    Mann–Whitney between protruding and retracting intensities. ``move_threshold``
    (displacement units) splits the three classes; default = ½·std(displacement)."""
    out = {k: np.nan for k in _SUMMARY_KEYS}
    out.update(n_protruding=0, n_retracting=0, n_stable=0,
               n_edge_intensity=int(disp.size))
    if disp.size < 3 or np.std(disp) == 0 or np.std(inten) == 0:
        return out
    r = _pearson(disp, inten)
    out["edge_move_intensity_r"] = r
    out["edge_move_intensity_r2"] = r ** 2 if np.isfinite(r) else np.nan
    try:
        from scipy import stats
        slope, intercept, _, p, _ = stats.linregress(disp, inten)
        out["edge_move_intensity_slope"] = float(slope)
        out["edge_move_intensity_p"] = float(p)
        out["_intercept"] = float(intercept)
    except Exception:
        pass
    thr = (float(move_threshold) if move_threshold is not None
           else 0.5 * float(np.std(disp)))
    out["_threshold"] = thr
    prot, retr, stab = disp > thr, disp < -thr, np.abs(disp) <= thr
    out.update(n_protruding=int(prot.sum()), n_retracting=int(retr.sum()),
               n_stable=int(stab.sum()))
    if prot.any():
        out["piezo_at_protrusion"] = float(inten[prot].mean())
    if retr.any():
        out["piezo_at_retraction"] = float(inten[retr].mean())
    if prot.any() and retr.any():
        out["piezo_protr_minus_retr"] = (out["piezo_at_protrusion"]
                                         - out["piezo_at_retraction"])
        try:
            from scipy import stats
            out["protr_retr_ttest_p"] = float(
                stats.ttest_ind(inten[prot], inten[retr]).pvalue)
            out["protr_retr_mwu_p"] = float(stats.mannwhitneyu(
                inten[prot], inten[retr], alternative="two-sided").pvalue)
        except Exception:
            pass
    return out


def rectangles_for_frame(labels, image, cell_id, t, depth=DEPTH_PX, width=WIDTH_PX):
    """(corners (m, 4, 2) row/col, intensities (m,)) for accepted rectangles in
    frame ``t`` — for the per-frame sampling-rectangle overlay."""
    m = np.asarray(labels)[t] == cell_id
    if not m.any():
        return np.zeros((0, 4, 2)), np.array([])
    center = _frame_centroid(m)
    radii = edge_dynamics._radii(m, center)
    inten, corners = rectangle_intensity(image[t], m, center, radii, depth, width,
                                         return_corners=True)
    ok = np.isfinite(inten)
    return corners[ok], inten[ok]


def analyze_cell(labels, image, cell_id, um_per_px=None, dt_min=None,
                 depth=DEPTH_PX, width=WIDTH_PX, temporal="past",
                 move_threshold=None):
    """End-to-end for one cell. Returns
    ``(vfr, velmat, ifr, intmat, disp, inten, summary)``: the edge-velocity
    kymograph, the rectangle-intensity kymograph, the flattened
    (displacement, intensity) pairs, and the correlation summary dict."""
    labels = np.asarray(labels)
    vfr, velmat = edge_dynamics.edge_velocity_kymograph(labels, cell_id,
                                                        um_per_px, dt_min)
    ifr, intmat = intensity_kymograph(labels, image, cell_id, depth, width)
    disp, inten = movement_intensity_pairs(ifr, velmat, intmat, temporal)
    summary = correlation_summary(disp, inten, move_threshold)
    return vfr, velmat, ifr, intmat, disp, inten, summary
