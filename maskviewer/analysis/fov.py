"""Field-of-view (FOV) detection + cropping — GUI-free.

Recordings sometimes carry a black (zero / near-constant) border outside the
imaged field — registration padding, camera dead rows, or a smaller acquired
area. Those pixels are not real signal: cells there are artefacts and intensity
rectangles reaching into them are biased. This finds the **inner FOV rectangle**
(``(y0, y1, x0, x1)``, half-open) by trimming near-empty borders, and crops a
label stack to it (everything outside the rectangle is set to background) so all
mask-based analysis ignores out-of-FOV content.

``auto_fov`` works on a 2-D image, a ``(T, H, W)`` stack, or a ``(T, C, H, W)``
recording (reduced to a max projection so any frame/channel with signal counts).
"""
from __future__ import annotations

import numpy as np


def content_projection(arr):
    """Reduce a 2-D / (T,H,W) / (T,C,H,W) array to a 2-D max projection (the
    brightest each pixel ever gets across frames/channels)."""
    arr = np.asarray(arr, float)
    while arr.ndim > 2:
        arr = arr.max(axis=0)
    return arr


def auto_fov(arr, threshold=None, min_valid_frac=0.5):
    """Inner FOV rectangle ``(y0, y1, x0, x1)`` by trimming near-empty borders.

    A pixel is "valid" if its max projection exceeds ``threshold`` (default: 2 %
    of the dynamic range above the minimum — i.e. anything but the black border).
    Rows/cols are trimmed from each side while fewer than ``min_valid_frac`` of
    their pixels are valid. Returns the full frame if nothing would be trimmed."""
    proj = content_projection(arr)
    h, w = proj.shape
    lo, hi = float(proj.min()), float(proj.max())
    if threshold is None:
        threshold = lo + 0.02 * (hi - lo) if hi > lo else lo
    valid = proj > threshold
    rows, cols = valid.mean(axis=1), valid.mean(axis=0)
    y0 = 0
    while y0 < h and rows[y0] < min_valid_frac:
        y0 += 1
    y1 = h
    while y1 > y0 and rows[y1 - 1] < min_valid_frac:
        y1 -= 1
    x0 = 0
    while x0 < w and cols[x0] < min_valid_frac:
        x0 += 1
    x1 = w
    while x1 > x0 and cols[x1 - 1] < min_valid_frac:
        x1 -= 1
    if y1 <= y0 or x1 <= x0:
        return (0, h, 0, w)
    return (int(y0), int(y1), int(x0), int(x1))


def clamp_rect(rect, shape):
    """Clamp ``(y0, y1, x0, x1)`` to a ``(..., H, W)`` shape; None → full frame."""
    h, w = shape[-2:]
    if rect is None:
        return (0, h, 0, w)
    y0, y1, x0, x1 = rect
    y0, y1 = max(0, int(y0)), min(h, int(y1))
    x0, x1 = max(0, int(x0)), min(w, int(x1))
    if y1 <= y0 or x1 <= x0:
        return (0, h, 0, w)
    return (y0, y1, x0, x1)


def fov_mask(shape, rect):
    """Boolean ``(H, W)`` mask, True inside ``rect`` (True everywhere if None)."""
    h, w = shape[-2:]
    m = np.zeros((h, w), bool)
    y0, y1, x0, x1 = clamp_rect(rect, shape)
    m[y0:y1, x0:x1] = True
    return m


def apply_fov(labels, rect):
    """Copy of a label array with everything outside ``rect`` set to 0 (so
    out-of-FOV cells / pixels drop out of all mask-based analysis)."""
    if rect is None:
        return labels
    labels = np.asarray(labels)
    y0, y1, x0, x1 = clamp_rect(rect, labels.shape)
    out = np.zeros_like(labels)
    out[..., y0:y1, x0:x1] = labels[..., y0:y1, x0:x1]
    return out
