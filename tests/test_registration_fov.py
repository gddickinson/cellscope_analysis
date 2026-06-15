"""Channel registration (translation) + FOV detection/cropping."""
import numpy as np
from scipy import ndimage

from maskviewer.analysis import registration as reg
from maskviewer.analysis import fov


def _texture(h=96, w=96, seed=0):
    """A smooth, aperiodic texture with clear gradient structure."""
    rng = np.random.default_rng(seed)
    return ndimage.gaussian_filter(rng.standard_normal((h, w)), 4.0)


def test_estimate_shift_integer_roundtrip():
    ref = _texture()
    mov = ndimage.shift(ref, (4, -3), order=1)          # mov = ref moved by (4,-3)
    dy, dx = reg.estimate_shift(ref, mov)               # → the correction (−4, +3)
    assert abs(dy + 4) < 0.6 and abs(dx - 3) < 0.6, (dy, dx)
    # applying the correction brings mov back onto ref
    back = reg.apply_shift(mov, dy, dx)
    inner = (slice(10, -10), slice(10, -10))
    assert np.corrcoef(back[inner].ravel(), ref[inner].ravel())[0, 1] > 0.95


def test_estimate_shift_subpixel():
    ref = _texture(seed=1)
    mov = ndimage.shift(ref, (2.5, -1.5), order=1)
    dy, dx = reg.estimate_shift(ref, mov)
    assert abs(dy + 2.5) < 0.7 and abs(dx - 1.5) < 0.7, (dy, dx)


def test_estimate_shift_bounded_rejects_far_peak():
    """A shift beyond max_shift is not selectable (guards against the spurious
    far phase-correlation peaks that cross-modality data can produce)."""
    ref = _texture(128, 128, seed=3)
    mov = ndimage.shift(ref, (40, 30), order=1)
    dy, dx = reg.estimate_shift(ref, mov, max_shift=12)     # tight cap
    assert abs(dy) <= 12.5 and abs(dx) <= 12.5, (dy, dx)
    dy2, dx2 = reg.estimate_shift(ref, mov, max_shift=60)   # generous cap
    assert abs(dy2 + 40) < 1.0 and abs(dx2 + 30) < 1.0, (dy2, dx2)


def test_estimate_shift_flat_is_zero():
    flat = np.ones((32, 32))
    assert reg.estimate_shift(flat, flat) == (0.0, 0.0)


def test_max_shift_never_zero_for_tiny_images():
    """The default cap must never be 0 — a tiny image would otherwise forbid every
    non-zero displacement and silently report a zero shift."""
    assert reg._max_shift((3, 3), None) >= 1
    assert reg._max_shift((1, 1), None) >= 1
    # a tiny image with a real 1-px shift can still resolve it (cap isn't 0)
    ref = _texture(8, 8, seed=5)
    mov = ndimage.shift(ref, (1, 0), order=1)
    dy, dx = reg.estimate_shift(ref, mov)
    assert abs(dy + 1) < 1.0, (dy, dx)


def test_estimate_shift_degenerate_strip_no_crash():
    """A single-row/column image has no shift information and must not crash
    (np.gradient needs ≥2 samples per axis)."""
    assert reg.estimate_shift(np.zeros((1, 20)), np.zeros((1, 20))) == (0.0, 0.0)
    assert reg.estimate_shift(np.zeros((20, 1)), np.zeros((20, 1))) == (0.0, 0.0)


def test_apply_shift_stack_and_noop():
    stack = np.stack([_texture(48, 48, s) for s in range(3)])
    assert reg.apply_shift(stack, 0, 0) is stack          # no-op returns input
    out = reg.apply_shift(stack, 2, 1)
    assert out.shape == stack.shape
    assert np.corrcoef(ndimage.shift(stack[0], (2, 1)).ravel(),
                       out[0].ravel())[0, 1] > 0.99


def test_estimate_stack_shift():
    ref = np.stack([_texture(64, 64, s) for s in range(4)])
    mov = np.stack([ndimage.shift(ref[t], (3, 2), order=1) for t in range(4)])
    dy, dx = reg.estimate_stack_shift(ref, mov)         # correction = (−3, −2)
    assert abs(dy + 3) < 0.7 and abs(dx + 2) < 0.7, (dy, dx)


def test_auto_fov_trims_black_border():
    img = np.zeros((80, 100))
    img[8:70, 12:90] = 5.0 + np.random.default_rng(0).random((62, 78))
    y0, y1, x0, x1 = fov.auto_fov(img)
    assert abs(y0 - 8) <= 2 and abs(y1 - 70) <= 2
    assert abs(x0 - 12) <= 2 and abs(x1 - 90) <= 2


def test_auto_fov_full_when_no_border():
    img = 5.0 + np.random.default_rng(0).random((40, 50))
    assert fov.auto_fov(img) == (0, 40, 0, 50)


def test_auto_fov_on_stack():
    stack = np.zeros((5, 60, 60))
    stack[:, 6:54, 9:51] = 3.0
    y0, y1, x0, x1 = fov.auto_fov(stack)
    assert (abs(y0 - 6) <= 2 and abs(y1 - 54) <= 2
            and abs(x0 - 9) <= 2 and abs(x1 - 51) <= 2)


def test_apply_fov_zeros_outside():
    labels = np.ones((3, 40, 40), np.int32)
    out = fov.apply_fov(labels, (5, 35, 8, 32))
    assert out[:, :5, :].sum() == 0 and out[:, 35:, :].sum() == 0
    assert out[:, :, :8].sum() == 0 and out[:, :, 32:].sum() == 0
    assert (out[:, 5:35, 8:32] == 1).all()
    assert fov.apply_fov(labels, None) is labels


def test_fov_mask_and_clamp():
    assert fov.fov_mask((20, 20), None).all()
    m = fov.fov_mask((20, 20), (2, 10, 3, 12))
    assert m[2:10, 3:12].all() and m.sum() == 8 * 9
    assert fov.clamp_rect((-5, 999, -1, 999), (30, 40)) == (0, 30, 0, 40)


def test_apply_correction_skips_malformed_shifts():
    """A malformed/short channel-shift entry is skipped, not crashed on, while the
    valid entries (and a bad fov) are handled gracefully."""
    from maskviewer.io.recording import Recording, apply_correction
    rec = Recording("x.tif", np.zeros((2, 2, 8, 8), np.uint16), ["Cy5", "DIC"])
    corr = {"shifts": {"0": [1.0, 2.0], "1": [3.0], "2": None, "3": "bad"},
            "fov": ["oops"]}
    apply_correction(rec, corr)
    assert rec.channel_shifts == {0: (1.0, 2.0)}          # only the well-formed entry
    assert rec.fov is None                                # malformed fov ignored
