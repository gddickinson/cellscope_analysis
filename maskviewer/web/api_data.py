"""Data behind the web API: the synthetic demo set, Python reference tables, the comparison and metric docs.

Everything here calls the repo's own GUI-free code (`io.dataset.discover`, `analysis.exporters`,
`analysis.compare`, `analysis.metric_docs`); nothing is re-implemented. Results are memoised per
process (the demo is fixed, so the static site exports them once).
"""
from __future__ import annotations

import io
import math
import os
from functools import lru_cache

import numpy as np

from ..analysis import compare, exporters, metric_docs
from ..io import dataset
from . import demo_data

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO_DIR = os.path.join(ROOT, "web_demo")          # gitignored; rebuilt from the fixed seeds
# per-frame columns the web pages plot (cell_metrics.per_frame_records names)
PER_FRAME_COLUMNS = ["area_um2", "area_px", "perimeter_um", "perimeter_px", "circularity", "convexity",
                     "eccentricity", "aspect_ratio", "extent", "major_axis_um", "minor_axis_um",
                     "major_axis_px", "minor_axis_px", "orientation_rad", "nn_dist_um", "nn_dist_px",
                     "n_neighbors", "rel_area", "state_code", "speed", "displacement_from_start",
                     "turning_angle"]
HEADLINE = ["persistence_dir_autocorr", "straightness", "mean_speed_um_per_min",
            "mean_area_um2", "frac_rounded", "mean_eccentricity", "frac_tumble"]


def clean(v):
    """JSON-safe values: NaN/inf -> None, numpy scalars -> Python."""
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, np.ndarray)):
        return [clean(x) for x in v]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if math.isfinite(float(v)) else None
    return v


def records(df):
    return [] if df is None or df.empty else [clean(r) for r in df.to_dict(orient="records")]


@lru_cache(maxsize=1)
def demo_entries():
    return dataset.discover(demo_data.ensure_demo(DEMO_DIR))


def _rel(path):
    return os.path.relpath(path, DEMO_DIR).replace(os.sep, "/")


@lru_cache(maxsize=1)
def demo_list():
    out = []
    for e in demo_entries():
        rec, masks = e.load_recording(), e.load_masks()
        T, H, W = masks.labels.shape
        out.append({"label": e.label, "condition": e.condition,
                    "condition_note": demo_data.CONDITIONS[e.condition][1],
                    "tif": "demo/" + _rel(e.recording_path), "masks": "demo/" + _rel(e.mask_path),
                    "sidecar": "demo/" + _rel(e.recording_path).replace(".ome.tif", ".ome.json"),
                    "um_per_px": rec.um_per_px, "time_interval_min": rec.time_interval_min,
                    "channel_names": rec.channel_names, "T": T, "H": H, "W": W,
                    "n_cells": len(masks.cell_ids())})
    return {"synthetic": True, "source": demo_data.SOURCE,
            "description": ("Synthetic demo: simulated cells written in the CellScope results layout "
                            "by the repo's own writer. The two conditions are two simulated motion "
                            "models, not treatments; no real microscopy data."),
            "recordings": out}


def _entry(label):
    for e in demo_entries():
        if e.label == label:
            return e
    raise KeyError(label)


@lru_cache(maxsize=16)
def reference(label):
    """The Python per-cell table for one demo recording (the JS port is compared against it)."""
    e = _entry(label)
    rec, masks = e.load_recording(), e.load_masks()
    pc = exporters.per_cell_table(masks.labels, rec.um_per_px, rec.time_interval_min)
    return {"label": label, "per_cell": records(pc)}


@lru_cache(maxsize=1)
def demo_compare():
    """compare.build_comparison over the demo (recording = unit) -> per-recording table,
    ensemble curves by condition, and ranked group comparisons for the headline metrics."""
    per_cell, msd, ac, dr, vc = compare.build_comparison(
        demo_entries(), with_contacts=False, with_state_segmented=False)
    per_rec = compare.aggregate(per_cell)
    curves = {}
    for name, df, col in (("msd", msd, "msd"), ("autocorr", ac, "autocorr"),
                          ("dir_ratio", dr, "dir_ratio"), ("velcorr", vc, "velcorr")):
        ens = compare.ensemble_by_condition(df, value_col=col)
        curves[name] = {c: {"tau": t, "centre": m, "lo": lo, "hi": hi} for c, (t, m, lo, hi) in ens.items()}
    ranked = {m: compare.ranked_group_comparisons(per_rec, m, with_ci=False)
              for m in HEADLINE if m in per_rec.columns}
    return clean({"per_recording": records(per_rec), "curves": curves, "ranked": ranked,
                  "headline": HEADLINE})


def metric_info(columns=None):
    """{column: {label, units, what, how}} from metric_docs for the per-cell columns."""
    if columns is None:
        columns = sorted({k for r in reference(demo_entries()[0].label)["per_cell"] for k in r}
                         | set(PER_FRAME_COLUMNS))
    out = {}
    for c in columns:
        what, how = metric_docs.comparison_doc(c)
        out[c] = {"label": metric_docs.axis_label(c), "units": metric_docs.column_units(c),
                  "what": what, "how": how}
    for k, (what, how) in metric_docs.METRICS.items():
        out.setdefault(k, {"label": k.replace("_", " "), "units": "", "what": what, "how": how})
    return out


def analyse_upload(data: bytes, um_per_px=None, dt_min=None):
    """Python per-cell + track tables for an uploaded masks.npz (the full set of columns)."""
    with np.load(io.BytesIO(data), allow_pickle=False) as z:
        keys = list(z.keys())
        if not keys:
            raise ValueError("empty .npz")
        lab = np.asarray(z["labels"] if "labels" in z else z[keys[0]])
    if lab.ndim == 2:
        lab = lab[None]
    if lab.ndim != 3 or not np.issubdtype(lab.dtype, np.integer):
        raise ValueError(f"expected an integer (T, H, W) label stack, got {lab.dtype} {lab.shape}")
    pc = exporters.per_cell_table(lab, um_per_px or None, dt_min or None)
    return {"shape": list(lab.shape), "per_cell": records(pc),
            "columns": list(pc.columns), "metrics": metric_info(list(pc.columns))}
