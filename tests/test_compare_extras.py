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


def test_state_suffix_units_and_labels():
    # per-state columns inherit the base metric's units + are flagged [state]
    assert metric_docs.column_units("mean_area_um2_spread") == "µm²"
    assert metric_docs.column_units("persistence_rounded") == ""
    assert metric_docs.column_label("mean_area_um2_spread") == "mean area [spread]"
    assert metric_docs.axis_label("mean_area_um2_rounded") == "mean area [rounded] (µm²)"


def test_comparison_doc_resolves_base():
    what, how = metric_docs.comparison_doc("mean_speed_spread")
    assert what and "speed" in what.lower()
    assert "spread" in how.lower()                 # state note present
    # tooltip is non-empty and mentions the metric
    assert "speed" in metric_docs.comparison_tooltip("mean_speed_spread").lower()
    # comparison section is in the Help reference
    assert "state-segmented" in metric_docs.as_html().lower()


def test_border_distance_metric():
    from maskviewer.analysis import exporters
    T, H, W = 3, 100, 100
    labels = np.zeros((T, H, W), np.int32)
    labels[:, 40:60, 40:60] = 1            # centroid ~ (49.5, 49.5)
    df = exporters.per_cell_table(labels, 0.5, 10.0)
    assert "min_border_dist_um" in df.columns
    # nearest edge is 49.5 px away → × 0.5 µm/px ≈ 24.75 µm
    assert abs(df.iloc[0]["min_border_dist_um"] - 49.5 * 0.5) < 1.0


def test_save_load_results_roundtrip(tmp_path):
    pc = pd.DataFrame({"recording": ["a", "b"], "condition": ["WT", "KO"],
                       "cell_id": [1, 2], "mean_area_um2": [100.0, 200.0]})
    msd = pd.DataFrame({"recording": ["a"], "condition": ["WT"], "tau": [10.0],
                        "msd": [5.0]})
    fp = os.path.join(tmp_path, "r.cmp")
    compare.save_results(fp, pc, msd, {"name": "x", "excluded": ["b"]})
    blob = compare.load_results(fp)
    assert blob["meta"]["name"] == "x" and blob["meta"]["excluded"] == ["b"]
    assert blob["per_cell"].equals(pc) and blob["msd"].equals(msd)


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
