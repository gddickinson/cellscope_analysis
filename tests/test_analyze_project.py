"""Integration test for the headless analyze-project runner (scripts/analyze_project.py).

Runs the actual CLI as a subprocess on the synthetic sample project and checks the
core CSVs are written — a real end-to-end smoke of the reproducible pipeline.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_analyze_project_writes_csvs(tmp_path):
    out = str(tmp_path / "report")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "analyze_project.py"),
         "--data-root", os.path.join(ROOT, "sample_data"), "--name", "sample",
         "--out", out],
        capture_output=True, text=True, env=env, timeout=300)
    assert r.returncode == 0, r.stderr[-800:]
    assert os.path.exists(os.path.join(out, "per_cell.csv"))
    assert os.path.exists(os.path.join(out, "per_recording.csv"))
    # the per-cell table has cells + a condition column
    with open(os.path.join(out, "per_cell.csv")) as f:
        header = f.readline()
    assert "condition" in header and "cell_id" in header
