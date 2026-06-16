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
5. Speed across tracking gaps (``motion`` / per-frame series) ÷ elapsed time.
6. ``contacts._boundary_mask`` counts image-border pixels (no edge-cell undercount).
7. ``edge_dynamics.edge_summary`` returns NaN (not 0) when a cell never protrudes/
   retracts; PERMANOVA guards degenerate group counts; ``loadings`` pooled SD matches
   ``cohens_d``; ``bootstrap_ci`` returns NaN when resamples are degenerate.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maskviewer.analysis import (motion, shape_modes, compare, cell_metrics,   # noqa: E402
                                 contacts, edge_dynamics, edge_intensity,
                                 multivariate, stats_extra)


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


# -- 5. speed divided by elapsed time across tracking gaps ------------------
def test_speed_across_gap_uses_elapsed_time():
    cen = np.array([[0, 0], [2, 0], [np.nan, np.nan], [8, 0]], float)  # gap at frame 2
    sp = motion.instantaneous_speed(cen, dt_min=1.0)
    assert np.allclose(sp, [2.0, 3.0])                          # 6 px over 2 frames = 3, not 6
    dm = motion.displacement_metrics(cen, dt_min=1.0)
    assert np.isclose(dm["mean_speed"], 8.0 / 3.0)             # total 8 px ÷ 3 elapsed frames
    # gapless track: unchanged (one frame per step)
    straight = np.array([[0, 0], [1, 0], [2, 0], [3, 0]], float)
    assert np.allclose(motion.instantaneous_speed(straight, dt_min=1.0), [1, 1, 1])


# -- 6. boundary includes image-border pixels (edge-cell undercount) --------
def test_boundary_mask_counts_image_border():
    def block(corner):
        f = np.zeros((40, 40), np.int32)
        if corner:
            f[0:10, 0:10] = 1                                   # flush against 2 image edges
        else:
            f[15:25, 15:25] = 1                                 # interior
        return f
    bp_interior = contacts.frame_contacts(block(False))[1]["boundary_px"]
    bp_corner = contacts.frame_contacts(block(True))[1]["boundary_px"]
    assert bp_corner == bp_interior == 36                       # full 10×10 ring both ways


# -- 7. edge_summary NaN / PERMANOVA guard / loadings SD / bootstrap_ci -----
def test_edge_summary_nan_when_no_events():
    s = edge_dynamics.edge_summary(np.array([[1.0, 2.0], [0.5, 1.5]]))   # all protrusion
    assert np.isnan(s["mean_retraction_velocity"])              # no retraction → NaN not 0
    assert np.isfinite(s["mean_protrusion_velocity"])


def test_permanova_degenerate_groups_return_nan():
    X = np.arange(18.0).reshape(6, 3)
    F, p = multivariate.permanova(X, np.array(["A"] * 6), b=99)  # one group
    assert np.isnan(F) and np.isnan(p)


def test_loadings_pooled_sd_matches_cohens_d():
    import pandas as pd
    df = pd.DataFrame({"condition": ["WT"] * 5 + ["KO"] * 7,
                       "m": [1, 2, 3, 4, 5] + [4, 5, 6, 7, 8, 9, 10]})
    d = dict(multivariate.loadings(df, "WT", "KO", features=["m"]))["m"]
    a = df.loc[df.condition == "WT", "m"].to_numpy(float)
    b = df.loc[df.condition == "KO", "m"].to_numpy(float)
    assert np.isclose(d, compare.cohens_d(a, b))                # n-weighted, consistent


def test_bootstrap_ci_degenerate_returns_nan():
    lo, hi = stats_extra.bootstrap_ci([5, 5, 5], [5, 5, 5], compare.cohens_d, n_boot=200)
    assert np.isnan(lo) and np.isnan(hi)


def test_lagged_correlation_frame_path_matches_rows_when_contiguous():
    rng = np.random.RandomState(0)
    velmat = rng.randn(4, 8)
    intmat = rng.randn(5, 8)
    _, rs_rows, pl_rows, _ = edge_intensity.lagged_intensity_correlation(velmat, intmat)
    _, rs_fr, pl_fr, _ = edge_intensity.lagged_intensity_correlation(
        velmat, intmat, frames=[0, 1, 2, 3, 4])                 # contiguous → identical
    assert pl_rows == pl_fr and np.allclose(rs_rows, rs_fr, equal_nan=True)
