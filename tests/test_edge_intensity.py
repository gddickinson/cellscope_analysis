"""Edge-movement ↔ fluorescence-intensity correlation (faithful pipeline)."""
import numpy as np

from maskviewer.analysis import edge_intensity as ei


def _disc(cy, cx, r, shape=(80, 80)):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return ((yy - cy) ** 2 + (xx - cx) ** 2) <= r * r


def _ellipse(cy, cx, a, b, shape=(80, 80)):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return ((xx - cx) / a) ** 2 + ((yy - cy) / b) ** 2 <= 1.0


def _growing_cell(n=8, r0=14):
    """A disc that grows by 1 px/frame → every sector protrudes each step."""
    labels = np.zeros((n, 80, 80), np.int32)
    for t in range(n):
        labels[t][_disc(40, 40, r0 + t)] = 1
    return labels


def _disc_to_ellipse(n=4, r0=16):
    """Disc → x-stretched ellipse: left/right sectors protrude (radius grows),
    top/bottom retract (radius shrinks) → displacement varies across sectors."""
    labels = np.zeros((n, 80, 80), np.int32)
    labels[0][_disc(40, 40, r0)] = 1
    for t in range(1, n):
        labels[t][_ellipse(40, 40, r0 + 4 * t, r0 - 2 * t)] = 1
    return labels


def test_rectangle_intensity_shape_and_coverage():
    m = _disc(40, 40, 18)
    img = np.ones((80, 80), float) * 50.0
    center = ei._frame_centroid(m)
    radii = ei.edge_dynamics._radii(m, center)
    vals = ei.rectangle_intensity(img, m, center, radii)
    assert vals.shape == (ei.N_SECTORS,)
    # uniform image → every sampled rectangle reads the constant value
    fin = vals[np.isfinite(vals)]
    assert fin.size > ei.N_SECTORS // 2
    assert np.allclose(fin, 50.0)


def test_correlation_sign_positive():
    """Left/right sectors protrude (positive disp) and sit in the bright columns
    (|x-40| large); top/bottom retract and sit in the dark central column →
    protrusion co-occurs with high intensity → r > 0."""
    labels = _disc_to_ellipse()
    n = labels.shape[0]
    yy, xx = np.ogrid[:80, :80]
    grad = np.abs(xx - 40.0).astype(float)          # bright left & right, dark centre
    image = np.broadcast_to(grad, (n, 80, 80)).copy()
    _, _, _, _, disp, inten, summary = ei.analyze_cell(labels, image, 1)
    assert summary["n_edge_intensity"] >= 3
    assert disp.size == inten.size and disp.size >= 3
    assert summary["edge_move_intensity_r"] > 0.4
    assert np.isfinite(summary["edge_move_intensity_slope"])
    assert summary["n_protruding"] > 0 and summary["n_retracting"] > 0


def test_correlation_sign_negative():
    """Same geometry, intensity *decreases* outward → r < 0."""
    labels = _disc_to_ellipse()
    n = labels.shape[0]
    yy, xx = np.ogrid[:80, :80]
    grad = -np.abs(xx - 40.0).astype(float)
    image = np.broadcast_to(grad, (n, 80, 80)).copy()
    _, _, _, _, _, _, summary = ei.analyze_cell(labels, image, 1)
    assert summary["edge_move_intensity_r"] < -0.4


def test_classification_and_difference():
    labels = _disc_to_ellipse()
    n = labels.shape[0]
    yy, xx = np.ogrid[:80, :80]
    grad = np.abs(xx - 40.0).astype(float)
    image = np.broadcast_to(grad, (n, 80, 80)).copy()
    _, _, _, _, disp, inten, summary = ei.analyze_cell(labels, image, 1)
    assert summary["n_protruding"] > 0 and summary["n_retracting"] > 0
    # protruding sectors (left/right) sit in the bright columns
    assert summary["piezo_protr_minus_retr"] > 0
    assert np.isfinite(summary["protr_retr_ttest_p"])


def test_empty_and_degenerate():
    d = np.array([]); i = np.array([])
    out = ei.correlation_summary(d, i)
    assert out["n_edge_intensity"] == 0
    assert np.isnan(out["edge_move_intensity_r"])
    # constant intensity → undefined correlation, no crash
    out2 = ei.correlation_summary(np.arange(10.0), np.ones(10))
    assert np.isnan(out2["edge_move_intensity_r"])


def test_rectangles_for_frame():
    labels = _growing_cell()
    image = np.ones((labels.shape[0], 80, 80), float)
    corners, inten = ei.rectangles_for_frame(labels, image, 1, 3)
    assert corners.ndim == 3 and corners.shape[1:] == (4, 2)
    assert corners.shape[0] == inten.size
