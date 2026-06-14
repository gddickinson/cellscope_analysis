"""Units/labels (metric_docs) + per-group summary (compare) — pure, GUI-free."""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from maskviewer.analysis import metric_docs, compare      # noqa: E402


def test_column_units():
    cases = {
        "mean_area_um2": "µm²",
        "mean_perimeter_um": "µm",
        "mean_speed_um_per_min": "µm/min",
        "furth_D_um2_per_min": "µm²/min",
        "persistence_time_min": "min",
        "frames_tracked": "frames",
        "mean_n_neighbors": "count",
        "n_cells": "count",
        "frac_spread": "",            # fraction → dimensionless
        "mean_circularity": "",       # ratio → dimensionless
        "track_quality": "",
    }
    for col, want in cases.items():
        assert metric_docs.column_units(col) == want, (col, metric_docs.column_units(col))


def test_column_label_and_axis():
    assert metric_docs.column_label("mean_area_um2") == "mean area"
    assert metric_docs.column_label("mean_speed_um_per_min") == "mean speed"
    assert metric_docs.column_label("persistence_dir_autocorr") == "persistence dir autocorr"
    assert metric_docs.axis_label("mean_area_um2") == "mean area (µm²)"
    assert metric_docs.axis_label("mean_circularity") == "mean circularity"   # no units


def test_per_condition_summary():
    per_rec = pd.DataFrame({
        "recording": ["a", "b", "c", "d"],
        "condition": ["WT", "WT", "KO", "KO"],
        "mean_area_um2": [100.0, 120.0, 200.0, 240.0],
    })
    summ = {s["group"]: s for s in compare.per_condition_summary(per_rec, "mean_area_um2")}
    assert set(summ) == {"WT", "KO"}
    assert summ["WT"]["n"] == 2 and summ["WT"]["mean"] == 110.0
    assert summ["KO"]["median"] == 220.0
    assert summ["WT"]["sem"] > 0
    # empty / missing metric → []
    assert compare.per_condition_summary(per_rec, "nope") == []
    assert compare.per_condition_summary(pd.DataFrame(), "mean_area_um2") == []
