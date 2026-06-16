"""Multi-position OME-TIFF handling in the recording loader.

Micro-Manager writes one physical file per stage position, but its OME-XML
names the whole acquisition — so a naive read reports a phantom
``(R, T, C, H, W)`` stack. `recording._read_single_position` reads just the
file's own pages and reshapes to ``(T, C, H, W)``. The reshape core
(`planes_to_tcyx`) is pure, so we test the plane-ordering logic directly
(no real microscopy data — this repo is public).
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from maskviewer.io.recording import planes_to_tcyx, _looks_multiposition  # noqa: E402


def _planes(T, C, c_fast):
    """(T*C, H, W) planes; plane (t,c) is filled with the value t*10+c, laid
    out C-fast (MM/XYCZT) or T-fast."""
    H = W = 4
    out = np.zeros((T * C, H, W), np.uint16)
    for t in range(T):
        for c in range(C):
            p = (c + C * t) if c_fast else (t + T * c)
            out[p] = t * 10 + c
    return out


def test_reshape_c_fast_recovers_tc_layout():
    T, C = 5, 3
    arr = planes_to_tcyx(_planes(T, C, c_fast=True), C, T, c_fast=True)
    assert arr.shape == (T, C, 4, 4)
    for t in range(T):
        for c in range(C):
            assert (arr[t, c] == t * 10 + c).all(), (t, c)


def test_reshape_t_fast_recovers_tc_layout():
    T, C = 4, 2
    arr = planes_to_tcyx(_planes(T, C, c_fast=False), C, T, c_fast=False)
    assert arr.shape == (T, C, 4, 4)
    for t in range(T):
        for c in range(C):
            assert (arr[t, c] == t * 10 + c).all(), (t, c)


def test_infers_T_from_plane_count():
    T, C = 6, 3
    arr = planes_to_tcyx(_planes(T, C, c_fast=True), C, None, c_fast=True)
    assert arr.shape == (T, C, 4, 4)


def test_rejects_multi_position_in_one_file():
    # plane count not equal to C*Z*T -> a single file holding several positions
    with pytest.raises(ValueError):
        planes_to_tcyx(np.zeros((290, 4, 4), np.uint16), 3, 97, c_fast=True)


def test_looks_multiposition_detects_position_axis():
    class S:
        def __init__(self, axes, ndim):
            self.axes, self.ndim = axes, ndim
    assert _looks_multiposition(S("RTCYX", 5))
    assert _looks_multiposition(S("TCYX", 5))          # >4 dims
    assert not _looks_multiposition(S("TCYX", 4))
    assert not _looks_multiposition(S("TYX", 3))
