"""Membrane / boundary-quality metrics from a cell mask + an image channel.

Replicates CellScope's boundary-fidelity readouts — central to a PIEZO1 study
(PIEZO1 is a membrane channel; SiR-actin marks cortex):

* ``boundary_confidence`` — mean image-gradient magnitude *along the contour*
  (edge sharpness; distinct from an inside-vs-outside intensity step).
* ``intensity_contrast`` — |mean inside-ring − mean outside-ring| intensity.
* ``texture_contrast``   — inside-ring − outside-ring local-std (texture).
* ``membrane_score``     — composite 0.15·intensity + 0.85·max(texture, 0).

Ring-based inside/outside (erosion/dilation) rather than per-normal sampling,
but the same spirit. Pass a bbox-cropped mask + matching image for speed.
GUI-free.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def _rings(mask, width=2):
    inner = mask & ~ndimage.binary_erosion(mask, iterations=width)
    outer = ndimage.binary_dilation(mask, iterations=width) & ~mask
    return inner, outer


def boundary_confidence(mask, img):
    """Mean gradient magnitude of the (blurred) image along the cell boundary."""
    boundary = mask & ~ndimage.binary_erosion(mask)
    if not boundary.any():
        return float("nan")
    gy, gx = np.gradient(ndimage.gaussian_filter(img.astype(float), 2.0))
    return float(np.sqrt(gx * gx + gy * gy)[boundary].mean())


def intensity_contrast(mask, img):
    inner, outer = _rings(mask)
    if not inner.any() or not outer.any():
        return float("nan")
    return float(abs(img[inner].mean() - img[outer].mean()))


def texture_contrast(mask, img, win=7):
    f = img.astype(float)
    mean = ndimage.uniform_filter(f, win)
    std = np.sqrt(np.clip(ndimage.uniform_filter(f * f, win) - mean * mean, 0, None))
    inner, outer = _rings(mask)
    if not inner.any() or not outer.any():
        return float("nan")
    return float(std[inner].mean() - std[outer].mean())


def membrane_score(mask, img):
    """Composite membrane-fidelity score (CellScope weighting)."""
    ic, tc = intensity_contrast(mask, img), texture_contrast(mask, img)
    if not (np.isfinite(ic) or np.isfinite(tc)):
        return float("nan")
    return (0.15 * (ic if np.isfinite(ic) else 0.0)
            + 0.85 * max(tc if np.isfinite(tc) else 0.0, 0.0))
