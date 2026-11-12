"""Web interface tests: every exported endpoint answers, the static build is complete, and the JS engine tests pass.

Run: python -m pytest -q tests/test_web.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from maskviewer.web.app import STATIC, STATIC_ENDPOINTS, app  # noqa: E402

client = TestClient(app)


def test_index_served():
    r = client.get("/")
    assert r.status_code == 200 and "static/main.js" in r.text


@pytest.mark.parametrize("path", STATIC_ENDPOINTS)
def test_endpoint(path):
    r = client.get("/api" + path)
    assert r.status_code == 200, r.text
    assert r.json() is not None


def test_static_build(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_static
    build_static.build(tmp_path / "site")
    assert (tmp_path / "site" / "index.html").read_text().count("APP_STATIC") == 1
    for path in STATIC_ENDPOINTS:
        assert (tmp_path / "site" / "api" / (path.strip("/") + ".json")).exists()


def test_static_assets_referenced_exist():
    html = (STATIC / "index.html").read_text()
    for name in ("style.css", "main.js"):
        assert f"static/{name}" in html and (STATIC / name).exists()


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_js_engine():
    tests = sorted(STATIC.glob("*.test.mjs"))
    for t in tests:
        r = subprocess.run(["node", str(t)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


# ---- project-specific -------------------------------------------------------------------------------------------
def test_demo_is_synthetic_and_in_cellscope_layout():
    d = client.get("/api/demo").json()
    assert d["synthetic"] and len(d["recordings"]) == 6
    for r in d["recordings"]:
        assert r["masks"].endswith("pipeline_results/masks.npz") and r["tif"].endswith(".ome.tif")
        assert client.get("/" + r["masks"]).status_code == 200
        assert r["n_cells"] > 0 and r["um_per_px"] == 1.0


def test_reference_matches_exporters():
    import numpy as np
    from maskviewer.analysis import exporters
    from maskviewer.web import api_data
    e = api_data.demo_entries()[0]
    rec, masks = e.load_recording(), e.load_masks()
    pc = exporters.per_cell_table(masks.labels, rec.um_per_px, rec.time_interval_min)
    ref = client.get(f"/api/demo/{e.label}/reference").json()["per_cell"]
    assert len(ref) == len(pc)
    assert np.allclose([r["mean_area_um2"] for r in ref], pc["mean_area_um2"], rtol=1e-12)


def test_compare_has_curves_and_tests():
    d = client.get("/api/demo/compare").json()
    assert len(d["per_recording"]) == 6
    assert set(d["curves"]) == {"msd", "autocorr", "dir_ratio", "velcorr"}
    r = d["ranked"]["persistence_dir_autocorr"][0]
    assert r["n_a"] == 3 and r["n_b"] == 3 and 0 < r["p"] <= 1


def test_unknown_demo_is_404():
    assert client.get("/api/demo/nope/reference").status_code == 404


def test_analyze_upload():
    npz = ROOT / "sample_data" / "Pos_demo" / "pipeline_results" / "masks.npz"
    r = client.post("/api/analyze", files={"file": ("masks.npz", npz.read_bytes())},
                    data={"um_per_px": "0.6523", "dt_min": "10"})
    assert r.status_code == 200, r.text
    assert len(r.json()["per_cell"]) == 3 and "mean_speed_um_per_min" in r.json()["columns"]
    bad = client.post("/api/analyze", files={"file": ("x.npz", b"not a zip")})
    assert bad.status_code == 400


def test_web_fixture_is_current():
    """tests/fixtures/web_engine/expected.json still matches the Python code (rtol 1e-9)."""
    import json
    import numpy as np
    sys.path.insert(0, str(ROOT / "scripts"))
    import make_web_fixture as mk
    fx = ROOT / "tests" / "fixtures" / "web_engine"
    with np.load(fx / "masks.npz") as z:
        lab = z["labels"]
    old = json.loads((fx / "expected.json").read_text())
    new = json.loads(json.dumps(mk.expected(lab)))

    def same(a, b, path="$"):
        if isinstance(a, dict):
            assert set(a) == set(b), path
            for k in a:
                same(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list):
            assert len(a) == len(b), path
            for i, (x, y) in enumerate(zip(a, b)):
                same(x, y, f"{path}[{i}]")
        elif isinstance(a, float) and isinstance(b, (int, float)):
            assert abs(a - b) <= 1e-9 * max(1.0, abs(b)), path
        else:
            assert a == b, path
    same(old, new)
