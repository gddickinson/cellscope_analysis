"""FastAPI web app for cellscope_analysis: serves the front end in static/, the synthetic demo files under
/demo, and the JSON API under /api.

Run with `python run_web.py` (http://127.0.0.1:8213, local only). `scripts/build_static.py` exports every path in
STATIC_ENDPOINTS to JSON for the GitHub Pages site (and copies the demo files), so keep that list in step with the
GET routes below. Analysis of masks in the browser runs in the JS ports (static/*_engine.js); the Python API gives the
reference tables, the cross-recording comparison and the full per-cell table for uploads.
"""
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import api_data

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="CellScope Analysis")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
api_data.demo_entries()                                    # writes web_demo/ on first start
app.mount("/demo", StaticFiles(directory=api_data.DEMO_DIR), name="demo")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info():
    """Project summary for the home page (counts from the demo set)."""
    d = api_data.demo_list()
    recs = d["recordings"]
    return {"title": "CellScope Analysis", "repo": "cellscope_analysis",
            "n_recordings": len(recs), "n_cells": sum(r["n_cells"] for r in recs),
            "n_frames": sum(r["T"] for r in recs),
            "conditions": sorted({r["condition"] for r in recs}),
            "n_metrics": len(api_data.reference(recs[0]["label"])["per_cell"][0]),
            "demo_note": d["description"]}


@app.get("/api/demo")
def demo():
    """The synthetic demo recordings (file paths are relative to the site root)."""
    return api_data.demo_list()


@app.get("/api/demo/compare")
def demo_compare():
    """compare.build_comparison over the demo: per-recording table, curves by condition, ranked tests."""
    return api_data.demo_compare()


@app.get("/api/demo/{label}/reference")
def demo_reference(label: str):
    """The Python per-cell table of one demo recording."""
    try:
        return api_data.reference(label)
    except KeyError:
        raise HTTPException(404, f"no demo recording {label}")


@app.get("/api/metrics")
def metrics():
    """Label, units and what/how text (metric_docs.py) for every per-cell column."""
    return api_data.metric_info()


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), um_per_px: float = Form(0.0), dt_min: float = Form(0.0)):
    """Full Python per-cell table for an uploaded masks.npz (local app only)."""
    try:
        return api_data.analyse_upload(await file.read(), um_per_px or None, dt_min or None)
    except Exception as e:                                 # noqa: BLE001 - report the reason to the page
        raise HTTPException(400, f"could not analyse {file.filename}: {e}")


# GET paths (without the /api prefix) written to the static site as api/<path>.json.
STATIC_ENDPOINTS = ["/info", "/demo", "/demo/compare", "/metrics"] + [
    f"/demo/{r['label']}/reference" for r in api_data.demo_list()["recordings"]]
