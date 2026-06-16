"""VAMPIRE-style shape-mode classification (GUI-free; sklearn, no cv2/skimage).

A lightweight take on VAMPIRE (Lam et al., Nat Protocols 2021) for tracking
masks: each cell-frame's boundary becomes an aligned, scale-normalised radial
signature r(θ) (reusing the edge-dynamics boundary sampler); the recording's
signatures are reduced by PCA and clustered (K-means) into a few recurrent
**shape modes**. Each cell-frame gets a mode label, and the spread of modes
gives a morphological-heterogeneity (Shannon entropy) score. KO/GOF/YODA1 shift
the mode mix in PIEZO1 keratinocytes — a population shape readout.

  fit_shape_modes(labels) -> model dict (by_cell_frame, mode_signatures,
                             mode_fractions, entropy, explained_variance, …)
  cell_mode_series(model, cell_id) -> (frames, modes)
  mode_contour(signature)          -> (x, y) closed contour for display
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from . import edge_dynamics as _edge
from . import state as _state

N_POINTS = _edge.N_SECTORS          # 72-point radial signature
N_MODES = 5
N_PCS = 8


def _align_to_axis(rad):
    """Rotate a radial signature ``r(θ)`` to a canonical phase so clustering keys on
    *shape*, not orientation.

    The elongation axis is the phase of the **2nd Fourier harmonic** of ``r(θ)``,
    computed in the SAME angular convention the radii were binned in
    (``θ = arctan2(dy, dx)``, bin-centres ``-π + (s+½)·2π/N``). The 2nd harmonic is
    π-periodic, exactly matching an *undirected* axis, so a pure rotation of the cell
    becomes a circular shift that this cancels. The axis is rolled to bin 0; the
    residual 180° ambiguity is resolved by putting the heavier lobe in the front half
    (so a 180°-rotated cell maps to the same signature). A near-circular cell (tiny
    harmonic) is already rotation-invariant and is left unrolled.
    """
    n = rad.size
    theta = -np.pi + (np.arange(n) + 0.5) * (2 * np.pi / n)
    c2 = complex(np.sum(rad * np.exp(-2j * theta)))
    if abs(c2) < 1e-6 * max(float(rad.sum()), 1e-9):     # ~circular → rotation-invariant
        return rad
    axis = np.angle(c2) / 2.0                            # major-axis angle (binning frame)
    # roll by +shift: the 2nd-harmonic phase moves opposite to a circular shift, so
    # this cancels a cell rotation (a −shift would double it). Where the axis lands is
    # irrelevant — only that it lands in the same bin for every rotation of the shape.
    shift = int(round((axis + np.pi) / (2 * np.pi) * n)) % n
    rolled = np.roll(rad, shift)
    alt = np.roll(rolled, n // 2)                        # the opposite (180°) axis end
    return alt if alt[:n // 2].sum() > rolled[:n // 2].sum() else rolled


def contour_signature(mask):
    """Aligned, scale-normalised radial signature of one boolean mask, or None.

    Rotation-aligned to the elongation axis (``_align_to_axis``) and divided by the
    equivalent radius (scale-invariant), so only *shape* drives the clustering.
    """
    rr, cc = np.nonzero(mask)
    if rr.size < _state.MIN_AREA_PX:
        return None
    rad = _edge._interp_circular(_edge._radii(mask, (rr.mean(), cc.mean())))
    if not np.isfinite(rad).all():
        return None
    eqr = np.sqrt(rr.size / np.pi)
    rad = rad / eqr if eqr > 0 else rad
    return _align_to_axis(rad)


def fit_shape_modes(labels, n_modes=None, n_pcs=N_PCS, progress_cb=None):
    """Cluster all cell-frame contours into shape modes. None if too few cells.
    ``progress_cb(done, total)`` drives a GUI progress bar (per frame, during the
    contour-extraction pass — the dominant cost before PCA/K-means).
    ``n_modes=None`` reads the (configurable) module-level ``N_MODES`` at call time."""
    n_modes = N_MODES if n_modes is None else n_modes
    labels = np.asarray(labels)
    sigs, keys = [], []
    T = labels.shape[0]
    for t in range(T):
        for lab, sl in enumerate(ndimage.find_objects(labels[t]), start=1):
            if sl is None:
                continue
            sig = contour_signature(labels[t][sl] == lab)
            if sig is not None:
                sigs.append(sig)
                keys.append((lab, t))
        if progress_cb:
            progress_cb(t + 1, T)
    if len(sigs) < max(n_modes, 5):
        return None
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    X = np.asarray(sigs)
    n_pcs = int(min(n_pcs, X.shape[1], X.shape[0]))
    pca = PCA(n_components=n_pcs).fit(X - X.mean(0))
    z = pca.transform(X - X.mean(0))
    n_modes = int(min(n_modes, len(sigs)))
    lab = KMeans(n_clusters=n_modes, n_init=10, random_state=0).fit(z).labels_
    # relabel so mode 0 is the most common (stable colours across runs)
    order = np.argsort(-np.bincount(lab, minlength=n_modes))
    remap = {old: new for new, old in enumerate(order)}
    lab = np.array([remap[x] for x in lab])
    mode_sig = np.array([X[lab == k].mean(0) for k in range(n_modes)])
    fr = np.bincount(lab, minlength=n_modes).astype(float)
    fr /= fr.sum()
    ent = float(-(fr[fr > 0] * np.log2(fr[fr > 0])).sum())
    return {"by_cell_frame": {k: int(m) for k, m in zip(keys, lab)},
            "n_modes": n_modes, "mode_signatures": mode_sig,
            "mode_fractions": fr, "entropy": ent, "n_samples": len(sigs),
            "explained_variance": float(pca.explained_variance_ratio_.sum()),
            "normalized_entropy": ent / np.log2(n_modes) if n_modes > 1 else 0.0,
            "explained_variance_per_pc": pca.explained_variance_ratio_.tolist(),
            "eigenshapes": pca.components_,        # (n_pcs, n_points) deformations
            "mean_signature": X.mean(0)}


def cell_mode_series(model, cell_id):
    """(frames, modes) for one cell, ordered by frame."""
    items = sorted((t, m) for (cid, t), m in model["by_cell_frame"].items()
                   if cid == cell_id)
    if not items:
        return np.array([]), np.array([])
    fr, md = zip(*items)
    return np.array(fr), np.array(md)


def cell_heterogeneity(model, cell_id):
    """Shannon entropy (bits) of one cell's shape-mode distribution over time."""
    modes = [m for (cid, t), m in model["by_cell_frame"].items() if cid == cell_id]
    if not modes:
        return float("nan")
    f = np.bincount(modes).astype(float)
    f = f[f > 0] / len(modes)
    return float(-(f * np.log2(f)).sum())


def per_cell_shape_summary(model) -> dict:
    """``{cell_id: summary}`` of each cell's shape-mode usage over its track — for the
    comparison: ``dominant_shape_mode`` (most-used mode), ``n_shape_modes`` (distinct
    modes visited), ``shape_mode_entropy`` (bits — how varied) and
    ``shape_mode_switch_rate`` (fraction of consecutive frames that change mode — shape
    instability)."""
    from collections import defaultdict, Counter
    seq: dict = defaultdict(list)
    for (cid, t), m in model.get("by_cell_frame", {}).items():
        seq[cid].append((t, m))
    out = {}
    for cid, items in seq.items():
        modes = [m for _, m in sorted(items)]
        n = len(modes)
        cnt = Counter(modes)
        fr = np.array(list(cnt.values()), float) / n
        switches = sum(1 for a, b in zip(modes[:-1], modes[1:]) if a != b)
        out[int(cid)] = {
            "dominant_shape_mode": int(cnt.most_common(1)[0][0]),
            "n_shape_modes": len(cnt),
            "shape_mode_entropy": float(-(fr * np.log2(fr)).sum()) if n else np.nan,
            "shape_mode_switch_rate": float(switches / (n - 1)) if n > 1 else np.nan,
        }
    return out


def mode_contour(signature):
    """Closed (x, y) contour reconstructed from a radial signature, for display.

    Uses the same bin-centre angles the signature was sampled at
    (``θ = -π + (s+½)·2π/N`` with ``x = r·cosθ``, ``y = r·sinθ``) so the drawn mode
    shape matches the radii's angular frame rather than an arbitrary 0→2π sweep.
    """
    n = signature.size
    th = -np.pi + (np.arange(n) + 0.5) * (2 * np.pi / n)
    x, y = signature * np.cos(th), signature * np.sin(th)
    return np.append(x, x[0]), np.append(y, y[0])
