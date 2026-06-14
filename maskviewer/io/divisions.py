"""Load CellScope division events (`pipeline_results/divisions.json`).

The pipeline records candidate cell-division events. We use the ``candidates``
list, whose ``parent_track`` / ``daughter_track`` are the **label IDs** that match
the mask stack (the sibling ``track_lineage`` is 0-based track indices instead).
Returns a simple list of events; GUI-agnostic. Missing/empty file → ``[]``.
"""
from __future__ import annotations

import json
import os


def divisions_path_for(mask_path: str | None) -> str | None:
    if not mask_path:
        return None
    return os.path.join(os.path.dirname(mask_path), "divisions.json")


def load_divisions(path: str | None) -> list:
    """[{parent, daughter, frame, score, parent_centroid, daughter_centroid}]."""
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            blob = json.load(f)
    except (OSError, ValueError):
        return []
    cands = (blob.get("candidates", []) if isinstance(blob, dict)
             else blob if isinstance(blob, list) else [])
    out = []
    for c in cands:
        parent = int(c.get("parent_track", -1))
        daughter = int(c.get("daughter_track", -1))
        if parent < 0 or daughter < 0:
            continue
        out.append({
            "parent": parent,
            "daughter": daughter,
            "frame": int(c.get("frame", c.get("daughter_first_frame", 0))),
            "score": float(c.get("score", float("nan"))),
            "parent_centroid": c.get("parent_centroid"),
            "daughter_centroid": c.get("daughter_centroid"),
        })
    return out
