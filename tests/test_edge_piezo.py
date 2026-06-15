"""Edge-change ↔ cortical fluorescence correlation (edge_piezo). GUI-free."""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from maskviewer.analysis import edge_piezo as ep        # noqa: E402


def test_fluor_kymograph_shape_and_values():
    T, H, W = 3, 80, 80
    labels = np.zeros((T, H, W), np.int32)
    labels[:, 30:50, 30:50] = 1                          # static square
    image = np.full((T, H, W), 7.0)                      # uniform intensity 7
    fr, mat = ep.fluor_kymograph(labels, image, 1)
    assert list(fr) == [0, 1, 2]
    assert mat.shape == (3, ep.N_SECTORS)
    vals = mat[np.isfinite(mat)]
    assert vals.size and np.allclose(vals, 7.0)          # cortical band of a flat image


def test_correlation_sign():
    rng = np.random.default_rng(0)
    pfr = np.array([0, 1, 2, 3])
    vfr = np.array([1, 2, 3])                             # 3 frame-pairs
    velmat = rng.normal(size=(3, ep.N_SECTORS))
    # fluorescence at the later frame == velocity → Pearson ≈ +1
    piezo = np.zeros((4, ep.N_SECTORS))
    for k, fr in enumerate(vfr):
        piezo[fr] = velmat[k]
    assert ep.edge_fluor_correlation(vfr, velmat, pfr, piezo)["edge_piezo_pearson"] > 0.99
    # negated → ≈ −1, and protrusion intensity < retraction intensity
    out = ep.edge_fluor_correlation(vfr, velmat, pfr, -piezo)
    assert out["edge_piezo_pearson"] < -0.99
    assert out["piezo_protr_minus_retr"] < 0
    assert out["n_edge_piezo"] > 0


def test_edge_fluor_for_cell_runs():
    T, H, W = 6, 120, 120
    side = 40
    labels = np.zeros((T, H, W), np.int32)
    for t in range(T):
        x = 30 + t * 4                                   # square translates right
        labels[t, 40:40 + side, x:x + side] = 1
    # brighter toward +x (the leading edge) → some real correlation, finite output
    image = np.tile(np.linspace(0, 10, W)[None, :], (T, H, 1))
    vfr, velmat, pfr, piezo, summ = ep.edge_fluor_for_cell(labels, image, 1, 0.65, 10.0)
    assert velmat.shape[1] == ep.N_SECTORS and piezo.shape[1] == ep.N_SECTORS
    assert np.isfinite(summ["edge_piezo_pearson"])
    assert set(ep._SUMMARY_KEYS) <= set(summ)
