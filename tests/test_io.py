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


def test_discover_skips_internal_underscore_folders(tmp_path):
    """A CellScope results root holds a real `by_condition/` tree alongside
    internal `_cache/` (a flat dump of recordings, no masks), `_runs/`, and a
    hidden `.thumbs/`. Pointing discovery at the whole root must find only the
    real recording — never a bogus `_cache` entry (regression for opening the
    project folder instead of `by_condition/`)."""
    from maskviewer.io import discover
    import numpy as np
    import tifffile

    def _tif(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tifffile.imwrite(p, np.zeros((2, 4, 4), np.uint16))

    root = tmp_path / "results"
    # one real recording folder (with masks)
    rec = root / "by_condition" / "WT" / "Pos0-WT"
    _tif(str(rec / "Pos0-WT.ome.tif"))
    os.makedirs(rec / "pipeline_results", exist_ok=True)
    np.savez(rec / "pipeline_results" / "masks.npz",
             labels=np.zeros((2, 4, 4), np.int32))
    # internal cache: a flat dump of .ome.tifs, no masks
    for name in ("Pos0-WT", "Pos1-WT", "Pos2-WT"):
        _tif(str(root / "_cache" / f"{name}.ome.tif"))
    _tif(str(root / "_runs" / "scratch.ome.tif"))
    _tif(str(root / ".thumbs" / "preview.tif"))

    entries = discover(str(root))
    assert [e.label for e in entries] == ["Pos0-WT"]
    assert all(not e.label.startswith(("_", ".")) for e in entries)


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
