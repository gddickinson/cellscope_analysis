"""Tests for the edge-analysis + viewer additions (2026-06-16):

* ``edge_dynamics.curvature_kymograph`` — per-sector boundary curvature per frame.
* ``edge_intensity.rectangle_intensity`` rotation positioning (none / flip / search).
* ``exporters.per_cell_table`` track length in minutes.
* the categorical ``edge_rect_rotation`` analysis-parameter plumbing.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from maskviewer.analysis import edge_dynamics, edge_intensity, exporters  # noqa: E402


# -- curvature ---------------------------------------------------------------
def test_curvature_kymograph_disk_is_inverse_radius():
    H = W = 80
    lab = np.zeros((2, H, W), np.int32)
    yy, xx = np.mgrid[0:H, 0:W]
    for t in range(2):
        lab[t][((yy - 40) ** 2 + (xx - 40) ** 2) <= 20 ** 2] = 1
    fr, k = edge_dynamics.curvature_kymograph(lab, 1)          # cell 1, no scale → 1/px
    assert k.shape == (2, edge_dynamics.N_SECTORS)
    assert abs(float(np.nanmedian(k)) - 1.0 / 20.0) < 0.02     # disk curvature ≈ 1/R
    # scaling to µm divides curvature by µm/px
    _, k_um = edge_dynamics.curvature_kymograph(lab, 1, um_per_px=0.5)
    assert np.isclose(np.nanmedian(k_um), np.nanmedian(k) / 0.5, rtol=0.05)


def test_curvature_high_at_ellipse_tips():
    H = W = 120
    lab = np.zeros((1, H, W), np.int32)
    yy, xx = np.mgrid[0:H, 0:W]
    lab[0][(((xx - 60) / 34.0) ** 2 + ((yy - 60) / 14.0) ** 2) <= 1] = 1
    _, k = edge_dynamics.curvature_kymograph(lab, 1)
    assert np.nanmax(k) > 5 * abs(np.nanmedian(k))             # tips are sharply curved


# -- rectangle positioning (rotation) ---------------------------------------
def _crescent():
    H = W = 100
    mask = np.zeros((H, W), bool)
    yy, xx = np.mgrid[0:H, 0:W]
    mask[((yy - 50) ** 2 + (xx - 50) ** 2) <= 35 ** 2] = True
    mask[((yy - 50) ** 2 + (xx - 30) ** 2) <= 22 ** 2] = False  # bite out → concavity
    return mask


def test_rotation_recovers_low_coverage_sectors():
    mask = _crescent()
    img = np.ones(mask.shape) * 100.0
    cen = (np.nonzero(mask)[0].mean(), np.nonzero(mask)[1].mean())
    radii = edge_dynamics._radii(mask, cen)
    n_none = np.isfinite(edge_intensity.rectangle_intensity(
        img, mask, cen, radii, min_coverage=0.8, rotation="none")).sum()
    n_flip = np.isfinite(edge_intensity.rectangle_intensity(
        img, mask, cen, radii, min_coverage=0.8, rotation="flip")).sum()
    n_search = np.isfinite(edge_intensity.rectangle_intensity(
        img, mask, cen, radii, min_coverage=0.8, rotation="search", search_angles=18)).sum()
    assert n_search >= n_flip >= n_none and n_search > n_none


def test_rotation_noop_on_convex_cell():
    H = W = 100
    yy, xx = np.mgrid[0:H, 0:W]
    disk = ((yy - 50) ** 2 + (xx - 50) ** 2) <= 30 ** 2
    img = np.ones((H, W)) * 100.0
    cen, radii = (50.0, 50.0), edge_dynamics._radii(disk, (50.0, 50.0))
    a = edge_intensity.rectangle_intensity(img, disk, cen, radii, rotation="none")
    b = edge_intensity.rectangle_intensity(img, disk, cen, radii, rotation="search")
    assert np.isfinite(a).sum() == np.isfinite(b).sum()        # well-covered → unchanged


# -- track length in minutes -------------------------------------------------
def test_track_length_min_column():
    lab = np.zeros((5, 40, 40), np.int32)
    lab[:, 10:20, 10:20] = 1                                   # present all 5 frames
    t = exporters.per_cell_table(lab, um_per_px=0.5, dt_min=10.0)
    assert int(t.loc[t.cell_id == 1, "frames_tracked"].iloc[0]) == 5
    assert float(t.loc[t.cell_id == 1, "track_length_min"].iloc[0]) == 50.0
    # no time scale → no minutes column
    assert "track_length_min" not in exporters.per_cell_table(lab, um_per_px=0.5).columns


# -- categorical analysis parameter plumbing ---------------------------------
def test_rect_rotation_choice_applies_and_tags(tmp_path):
    from PyQt5 import QtCore
    from maskviewer.gui.compare_tables import (apply_analysis_params, analysis_params_tag,
                                               analysis_choices)
    s = QtCore.QSettings(str(tmp_path / "r.ini"), QtCore.QSettings.IniFormat)
    assert analysis_choices(s)["edge_rect_rotation"] == "none"
    assert analysis_params_tag(s) == ""                        # all default → no tag
    s.setValue("analysis/edge_rect_rotation", "search")
    s.setValue("analysis/edge_rect_search_angles", 24)
    try:
        apply_analysis_params(s)
        assert edge_intensity.RECT_ROTATION == "search"
        assert edge_intensity.RECT_SEARCH_ANGLES == 24
        assert "search" in analysis_params_tag(s)
    finally:
        edge_intensity.RECT_ROTATION = "none"
        edge_intensity.RECT_SEARCH_ANGLES = 18
