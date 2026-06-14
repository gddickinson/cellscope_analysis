"""State-segmented per-cell metrics (reproduce the original state-aware analysis).

Helper functions on synthetic state/centroid arrays + an end-to-end check on a
synthetic moving-square stack. GUI-free.
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from maskviewer.analysis import state_metrics as sm     # noqa: E402


def test_segments():
    states = ["spread", "spread", "rounded", "rounded", "rounded", "spread"]
    assert sm._segments(states) == [("spread", 0, 1), ("rounded", 2, 4),
                                    ("spread", 5, 5)]
    assert sm._segments([]) == []


def test_persistence_straight_line():
    # a perfectly straight, all-spread track → persistence ≈ 1, straightness ≈ 1
    cents = np.array([[0.0, float(i)] for i in range(8)])   # move along +x
    states = np.array(["spread"] * 8, dtype=object)
    assert abs(sm._persistence(cents, states, "spread") - 1.0) < 1e-6
    assert abs(sm._straightness(cents, states, "spread") - 1.0) < 1e-6
    # too-short segment (< SEG_MIN) → NaN
    short = np.array(["spread"] * 3 + ["rounded"] * 5, dtype=object)
    assert np.isnan(sm._persistence(cents, short, "spread"))


def test_per_cell_state_metrics_moving_square():
    T, H, W = 8, 200, 200
    side, step = 60, 5                       # area 3600 px → spread (> 960 µm²)
    labels = np.zeros((T, H, W), dtype=np.int32)
    for t in range(T):
        y, x = 40, 30 + t * step            # stays off the border (not edge)
        labels[t, y:y + side, x:x + side] = 1

    um, dt = 0.65, 10.0
    df = sm.per_cell_state_metrics(labels, um, dt)
    assert len(df) == 1
    r = df.iloc[0]
    # all frames are spread → rounded metrics are NaN
    assert np.isnan(r["mean_speed_rounded"])
    # straight, constant-velocity spread track
    assert abs(r["persistence_spread"] - 1.0) < 1e-6
    assert abs(r["straightness_spread"] - 1.0) < 1e-6
    assert abs(r["mean_speed_spread"] - step * um / dt) < 1e-3      # 0.325 µm/min
    assert abs(r["mean_area_um2_spread"] - side * side * um * um) < 1.0


def test_speed_cap_drops_jumps():
    # one giant teleport step must be capped out of the mean speed
    T, H, W = 4, 400, 400
    side = 60
    xs = [20, 25, 320, 325]                 # frame 1→2 is a huge jump
    labels = np.zeros((T, H, W), dtype=np.int32)
    for t, x in enumerate(xs):
        labels[t, 40:40 + side, x:x + side] = 1
    df = sm.per_cell_state_metrics(labels, 0.65, 10.0)
    speed = df.iloc[0]["mean_speed_spread"]
    # the ~19 µm/min jump (>15 cap) is dropped → mean stays small (~0.325)
    assert speed < 1.0
