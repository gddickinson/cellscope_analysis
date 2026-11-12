"""Regression tests for two per-cell export bugs (exporters.per_cell_table).

1. speed_isolated / speed_crowded divided a step that bridges a tracking gap by one
   frame interval, over-stating it (mean_speed and motion.instantaneous_speed already
   divide by the elapsed frames).
2. track_quality was NaN for a one-frame track: its total path is NaN and
   ``nan or 0.0`` is still NaN, so the path score never fell back to 0.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maskviewer.analysis import exporters  # noqa: E402


def _stack():
    L = np.zeros((6, 40, 40), np.int32)
    L[:, 5:20, 5:20] = 1                      # static neighbour (keeps cell 3 "crowded")
    L[2, 25:35, 25:35] = 2                    # a one-frame cell
    for t in (0, 1, 4, 5):                    # cell 3: 2 px/frame, absent in frames 2-3
        L[t, 22:30, 2 + 2 * t:10 + 2 * t] = 3
    return L


def test_density_speed_is_gap_aware():
    pc = exporters.per_cell_table(_stack(), 1.0, 10.0).set_index("cell_id")
    assert abs(pc.loc[3, "mean_speed_um_per_min"] - 0.2) < 1e-12
    assert abs(pc.loc[3, "speed_crowded_um_per_min"] - 0.2) < 1e-12


def test_density_speed_is_gap_aware_without_dt():
    pc = exporters.per_cell_table(_stack(), 1.0, None).set_index("cell_id")
    assert abs(pc.loc[3, "speed_crowded_um_per_frame"] - 2.0) < 1e-12


def test_track_quality_defined_for_single_frame_track():
    pc = exporters.per_cell_table(_stack(), 1.0, 10.0).set_index("cell_id")
    q = pc.loc[2, "track_quality"]
    assert np.isfinite(q)
    # frames 1/6, area_cv 0 -> area score 1, no path -> path score 0
    assert abs(q - (0.5 / 6 + 0.3)) < 1e-12
