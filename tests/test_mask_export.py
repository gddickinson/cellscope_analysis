"""Mask export to TIFF / PNG / NumPy — labels must round-trip exactly (these are label
images for other software, not renders). Pure backend (`analysis.mask_export`)."""
import os

import numpy as np
import pytest

from maskviewer.analysis import mask_export as mx


def _stack():
    T, H, W = 4, 24, 24
    L = np.zeros((T, H, W), np.int32)
    for t in range(T):
        L[t, 3:8, 3 + t:8 + t] = 5            # IDs 5 and 9 (non-consecutive on purpose)
        L[t, 14:18, 14:18] = 9
    return L


def test_tiff_stack_roundtrip(tmp_path):
    import tifffile
    L = _stack()
    paths = mx.export_masks(L, "tiff_stack", str(tmp_path), prefix="r_",
                            um_per_px=0.65, dt_min=10.0)
    assert len(paths) == 1 and paths[0].endswith("r_masks.tif")
    back = tifffile.imread(paths[0])
    assert back.shape == L.shape and (back == L).all()


def test_npz_roundtrip(tmp_path):
    L = _stack()
    (p,) = mx.export_masks(L, "npz", str(tmp_path))
    back = np.load(p)["labels"]                 # same key as the input masks.npz
    assert (back == L).all()


def test_npy_roundtrip(tmp_path):
    L = _stack()
    (p,) = mx.export_masks(L, "npy", str(tmp_path))
    assert (np.load(p) == L).all()


def test_tiff_and_png_sequence(tmp_path):
    import tifffile
    from PIL import Image
    L = _stack()
    tifs = mx.export_masks(L, "tiff_seq", str(tmp_path / "t"))
    pngs = mx.export_masks(L, "png_seq", str(tmp_path / "p"))
    assert len(tifs) == L.shape[0] and len(pngs) == L.shape[0]
    assert (tifffile.imread(tifs[0]) == L[0]).all()
    assert (np.array(Image.open(pngs[0])) == L[0]).all()


def test_relabel_consecutive():
    L = _stack()
    rl = mx.relabel_consecutive(L)
    assert sorted(np.unique(rl).tolist()) == [0, 1, 2]      # 5,9 → 1,2; 0 kept
    # spatial identity preserved (same pixels, just renumbered)
    assert ((rl > 0) == (L > 0)).all()


def test_bit_depth_auto(tmp_path):
    import tifffile
    small = np.zeros((2, 4, 4), np.int32); small[:, 0, 0] = 3
    big = np.zeros((2, 4, 4), np.int32); big[:, 0, 0] = 300
    (a,) = mx.export_masks(small, "npy", str(tmp_path / "a"))
    (b,) = mx.export_masks(big, "tiff_stack", str(tmp_path / "b"))
    assert np.load(a).dtype == np.uint8                      # < 256 → 8-bit
    assert tifffile.imread(b).dtype == np.uint16             # ≥ 256 → 16-bit


def test_unknown_format_raises(tmp_path):
    with pytest.raises(ValueError):
        mx.export_masks(_stack(), "jpeg", str(tmp_path))


def test_png_rejects_over_16bit(tmp_path):
    L = np.zeros((1, 4, 4), np.int32); L[0, 0, 0] = 70000     # > 65535 → 32-bit
    with pytest.raises(ValueError):
        mx.export_masks(L, "png_seq", str(tmp_path))
