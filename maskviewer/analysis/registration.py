"""Channel alignment (translation) for multi-channel recordings — GUI-free.

DIC and fluorescence (e.g. tagged PIEZO1, SiR-actin) channels are often offset by
a sub-pixel x/y shift (chromatic / stage / camera). Because the masks are made
from one channel (the reference), sampling another channel relative to those masks
— as `edge_intensity` does — is biased unless the channels are first aligned.

This estimates the **translation** that brings a *moving* channel onto a
*reference* channel and applies it. DIC and fluorescence have different contrast,
so a raw intensity cross-correlation is unreliable; we phase-correlate the
**gradient magnitude** of each image (shared structure — cell boundaries — shows
up in both modalities) with a Hann window, and refine the peak to sub-pixel by
parabolic interpolation. Pure numpy/scipy (no scikit-image).

``estimate_shift(ref, mov)`` → ``(dy, dx)`` such that ``apply_shift(mov, dy, dx)``
lands on ``ref``. ``apply_shift`` handles a 2-D frame or a ``(T, H, W)`` stack.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def _prep(img):
    """Gradient-magnitude, mean-removed, Hann-windowed — robust across modalities."""
    img = np.asarray(img, float)
    gy, gx = np.gradient(img)
    g = np.hypot(gy, gx)
    g = g - g.mean()
    win = np.hanning(g.shape[0])[:, None] * np.hanning(g.shape[1])[None, :]
    return g * win


def _parabolic(c, i):
    """Sub-pixel offset of a peak at index ``i`` along a length-n periodic axis
    ``c`` (3-point parabolic fit using circular neighbours)."""
    n = c.size
    ym1, y0, yp1 = c[(i - 1) % n], c[i], c[(i + 1) % n]
    denom = ym1 - 2 * y0 + yp1
    return 0.0 if denom == 0 else 0.5 * (ym1 - yp1) / denom


def _max_shift(shape, max_shift):
    if max_shift is not None:
        return int(max_shift)
    return min(100, min(shape) // 4)                 # sane channel-offset cap


def estimate_shift(ref, mov, max_shift=None):
    """(dy, dx) bringing ``mov`` onto ``ref`` via gradient phase-correlation.

    Channel offsets are small, so the correlation peak is searched only within
    ``±max_shift`` px (default ``min(100, min(H,W)//4)``) — this rejects the
    spurious far peaks that cross-modality (DIC↔fluorescence) data can otherwise
    produce. Returns ``(0.0, 0.0)`` when either image has no gradient structure."""
    a, b = _prep(ref), _prep(mov)
    if a.std() == 0 or b.std() == 0:
        return 0.0, 0.0
    fa = np.fft.rfft2(a)
    fb = np.fft.rfft2(b)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-12
    corr = np.fft.irfft2(cross, s=a.shape)
    h, w = a.shape
    ms = _max_shift((h, w), max_shift)
    # restrict the peak to wrapped displacements within ±ms on each axis
    dist_y = np.minimum(np.arange(h), h - np.arange(h))
    dist_x = np.minimum(np.arange(w), w - np.arange(w))
    allowed = (dist_y[:, None] <= ms) & (dist_x[None, :] <= ms)
    py, px = np.unravel_index(int(np.argmax(np.where(allowed, corr, -np.inf))),
                              corr.shape)
    # sub-pixel refine along each axis through the peak
    dy = py + _parabolic(corr[:, px], py)
    dx = px + _parabolic(corr[py, :], px)
    if dy > h / 2:                                   # unwrap to a signed shift
        dy -= h
    if dx > w / 2:
        dx -= w
    # the cross-power peak sits at the correction that maps `mov` back onto `ref`
    return float(dy), float(dx)


def apply_shift(arr, dy, dx, order=1):
    """Shift a 2-D frame or a ``(T, H, W)`` stack by ``(dy, dx)`` (px). Areas
    shifted in from outside are 0. ``(0, 0)`` returns the input unchanged."""
    arr = np.asarray(arr)
    if not dy and not dx:
        return arr
    if arr.ndim == 2:
        return ndimage.shift(arr.astype(float), (dy, dx), order=order,
                             mode="constant", cval=0.0).astype(arr.dtype)
    out = np.empty_like(arr)
    for t in range(arr.shape[0]):
        out[t] = ndimage.shift(arr[t].astype(float), (dy, dx), order=order,
                               mode="constant", cval=0.0).astype(arr.dtype)
    return out


def _projection(stack):
    """Reduce a 2-D / (T,H,W) / (T,C,H,W) array to a representative 2-D image
    (mean over time) for a stable, translation-only estimate."""
    stack = np.asarray(stack, float)
    while stack.ndim > 2:
        stack = stack.mean(axis=0)
    return stack


def estimate_stack_shift(ref_stack, mov_stack, max_shift=None):
    """(dy, dx) aligning the ``mov`` channel stack onto the ``ref`` channel stack,
    estimated on their mean projections (robust to per-frame noise)."""
    return estimate_shift(_projection(ref_stack), _projection(mov_stack),
                          max_shift=max_shift)
