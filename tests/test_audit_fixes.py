"""Regression tests for the deep-dive audit fixes (2026-06-16).

Each test pins a specific calculation bug found during the correctness audit so it
cannot silently regress:

1. ``motion.turning_angles`` — a paused cell (zero-length step) must not produce a
   phantom 90° turn, so ``run_and_tumble`` stops mis-reporting straight tracks.
2. ``shape_modes.contour_signature`` — the radial signature must be rotation-
   invariant (encode shape, not orientation).
3. ``compare.ranked_group_comparisons`` — two recording groups that are each
   internally constant but clearly different must still yield a finite p-value.
4. ``cell_metrics`` → ``state.classify_state`` — the circularity/solidity fallback
   must be reachable for a scale-less recording (state not all "unknown").
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maskviewer.analysis import motion, shape_modes, compare, cell_metrics  # noqa: E402


# -- 1. turning_angles / run_and_tumble pause handling ----------------------
def test_turning_angles_pause_is_nan_not_phantom_turn():
    # straight north track with one pause (identical consecutive centroids)
    cen = np.array([[0, 0], [1, 0], [1, 0], [2, 0], [3, 0]], float)
    turns = motion.turning_angles(cen)
    # the two joints adjacent to the zero-length step are undefined, not ±90°
    assert np.isnan(turns[0]) and np.isnan(turns[1])
    assert np.isfinite(turns[2]) and abs(turns[2]) < 1e-9      # real joint = straight


def test_run_and_tumble_straight_paused_track_is_not_all_tumble():
    cen = np.array([[0, 0], [1, 0], [1, 0], [2, 0], [3, 0]], float)
    rt = motion.run_and_tumble(cen, dt_min=10.0)
    assert rt["frac_tumble"] == 0.0 and rt["n_runs"] == 1
    # a genuine 90° turn is still counted
    turn = np.array([[0, 0], [1, 0], [2, 0], [2, 1], [2, 2]], float)
    assert motion.run_and_tumble(turn)["frac_tumble"] > 0


# -- 2. shape-mode signature is rotation-invariant --------------------------
def _ellipse(angle_deg, a=34, b=18, H=120, W=120):
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    cy, cx = H / 2, W / 2
    t = np.deg2rad(angle_deg)
    xr = (xx - cx) * np.cos(t) + (yy - cy) * np.sin(t)
    yr = -(xx - cx) * np.sin(t) + (yy - cy) * np.cos(t)
    return ((xr / a) ** 2 + (yr / b) ** 2) <= 1.0


def test_contour_signature_rotation_invariant():
    sigs = np.array([shape_modes.contour_signature(_ellipse(d))
                     for d in range(0, 180, 15)])
    ref = sigs[0]
    rms = max(np.sqrt(np.mean((s - ref) ** 2)) for s in sigs)
    assert rms < 0.05, f"signature varies with orientation (RMS {rms:.3f})"
    # a 180° rotation maps to the same signature
    assert np.allclose(shape_modes.contour_signature(_ellipse(40)),
                       shape_modes.contour_signature(_ellipse(220)), atol=0.05)


def test_shape_modes_cluster_by_shape_not_orientation():
    # round cells (varied angles) vs elongated cells (varied angles)
    labels = np.zeros((10, 120, 120), np.int32)
    for t in range(5):
        labels[t][_ellipse(31 * t, a=22, b=20)] = 1
    for t in range(5, 10):
        labels[t][_ellipse(31 * t, a=42, b=11)] = 1
    model = shape_modes.fit_shape_modes(labels, n_modes=2)
    md = [model["by_cell_frame"][(1, t)] for t in range(10)]
    assert len(set(md[:5])) == 1 and len(set(md[5:])) == 1   # each group is one mode
    assert set(md[:5]) != set(md[5:])                        # the two differ


# -- 3. ranked report keeps constant-but-different groups -------------------
def test_ranked_group_comparisons_constant_but_different_groups():
    import pandas as pd
    per_rec = pd.DataFrame({
        "condition": ["WT", "WT", "WT", "KO", "KO", "KO"],
        "metric": [5.0, 5.0, 5.0, 9.0, 9.0, 9.0],          # each group constant, differ
    })
    rows = compare.ranked_group_comparisons(per_rec, "metric", with_ci=False)
    assert len(rows) == 1
    assert np.isfinite(rows[0]["p"]) and rows[0]["p"] < 1.0
    # an all-identical pair is still (correctly) skipped
    per_rec2 = pd.DataFrame({"condition": ["A", "A", "B", "B"],
                             "metric": [3.0, 3.0, 3.0, 3.0]})
    assert not np.isfinite(
        compare.ranked_group_comparisons(per_rec2, "metric", with_ci=False)[0]["p"])


# -- 4. classify_state fallback reachable for scale-less recordings ---------
def test_state_classified_without_scale_via_circularity_fallback():
    # one round-ish blob, no µm/px → must classify via circularity/solidity, not "unknown"
    frame = np.zeros((60, 60), np.int32)
    yy, xx = np.mgrid[0:60, 0:60]
    frame[((yy - 30) ** 2 + (xx - 30) ** 2) <= 14 ** 2] = 1     # disk, ~615 px > MIN_AREA
    props = cell_metrics.regionprops_frame(frame, um_per_px=None,
                                           with_solidity=True, with_perimeter=True)
    assert props[1]["state"] != "unknown"                       # fallback now reachable
    assert props[1]["state"] == "rounded"                       # a disk is rounded
