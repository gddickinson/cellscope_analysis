"""Smoke tests for IO + analysis against the bundled synthetic sample.

Run: `conda run -n cellpose4 python -m pytest -q`
(regenerate the sample first if missing: `python scripts/make_sample_data.py`)
"""
import os
import subprocess
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
SAMPLE = os.path.join(ROOT, "sample_data", "Pos_demo")


@pytest.fixture(scope="session", autouse=True)
def _ensure_sample():
    if not os.path.exists(os.path.join(SAMPLE, "Pos_demo.ome.tif")):
        subprocess.run([sys.executable,
                        os.path.join(ROOT, "scripts", "make_sample_data.py")],
                       check=True)


def test_discover_finds_sample():
    from maskviewer.io import discover
    entries = discover(os.path.join(ROOT, "sample_data"))
    assert any(e.label == "Pos_demo" for e in entries)


def test_load_recording_shape_and_meta():
    from maskviewer.io import load_recording
    rec = load_recording(os.path.join(SAMPLE, "Pos_demo.ome.tif"))
    assert rec.data.ndim == 4               # (T, C, H, W)
    assert rec.n_channels == 2
    assert rec.um_per_px == pytest.approx(0.6523)
    assert rec.frame(0, 0).ndim == 2


def test_load_masks_and_stats():
    from maskviewer.io import load_masks
    from maskviewer.analysis import summary, track_lengths
    m = load_masks(os.path.join(SAMPLE, "pipeline_results", "masks.npz"))
    assert m.labels.ndim == 3
    assert m.max_label == 3                 # three synthetic cells
    s = summary(m.labels, um_per_px=0.6523)
    assert s["n_cells_total"] == 3
    assert s["mean_cell_area_um2"] > 0
    assert all(v > 0 for v in track_lengths(m.labels).values())
