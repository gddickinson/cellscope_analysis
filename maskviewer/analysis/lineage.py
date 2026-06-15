"""Cell lineage + division helpers (GUI-free).

Everything here is derived **from the loaded masks themselves** — track lifespans
from where each label is present, and division events inferred from the track
topology (`infer_divisions`). Nothing depends on the pipeline's pre-cleaning
``divisions.json`` (which references track IDs that manual cleaning may have
removed), so lineage is always consistent with the cleaned label stack in this
project. Provides the data for a lineage tree (lifelines + parent→daughter
connectors), a division timeline, and parent/daughter lookups for the cell-info
panel.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def present_ids(labels) -> set:
    """Set of track label IDs that appear anywhere in the mask stack."""
    return {int(i) for i in np.unique(np.asarray(labels)) if i > 0}


def valid_divisions(divisions: list, labels) -> list:
    """Keep only division events whose **parent and daughter tracks both exist**
    in the mask stack.

    `divisions.json` is recorded by the pipeline *before* the masks are manually
    cleaned, and lists scored *candidate* events — so it can name tracks that
    review later removed or merged (e.g. a daughter track that no longer exists).
    Such events are not real divisions of the cleaned recording; surfacing them
    puts phantom IDs in the cell table / cell-info and draws division markers on
    empty space. Dropping any event that references a missing track removes them,
    while keeping every division whose cells survive in the masks."""
    ids = present_ids(labels)
    return [d for d in divisions
            if int(d.get("parent", -1)) in ids and int(d.get("daughter", -1)) in ids]


def track_spans(labels) -> dict:
    """{cell_id: (first_frame, last_frame)} from where each label is present."""
    labels = np.asarray(labels)
    first, last = {}, {}
    for t in range(labels.shape[0]):
        for i in np.unique(labels[t]):
            i = int(i)
            if i <= 0:
                continue
            first.setdefault(i, t)
            last[i] = t
    return {c: (first[c], last[c]) for c in first}


def lineage_rows(spans: dict) -> dict:
    """{cell_id: y-row} ordered by first frame then id (for the lineage tree)."""
    return {c: i for i, c in enumerate(sorted(spans, key=lambda c: (spans[c][0], c)))}


def division_counts(divisions: list, n_frames: int) -> np.ndarray:
    """(n_frames,) number of division events at each frame."""
    counts = np.zeros(int(n_frames), int)
    for d in divisions:
        f = int(d["frame"])
        if 0 <= f < n_frames:
            counts[f] += 1
    return counts


def relatives(divisions: list, cell_id: int):
    """(parents, daughters) of a cell from the division events."""
    parents = [d["parent"] for d in divisions if d["daughter"] == cell_id]
    daughters = [d["daughter"] for d in divisions if d["parent"] == cell_id]
    return parents, daughters


def _frame_geometry(labels) -> list:
    """Per frame, ``{cell_id: (cy, cx, area_px)}`` for present cells (one pass)."""
    out = []
    for t in range(labels.shape[0]):
        lab = labels[t]
        ids = np.unique(lab)
        ids = ids[ids > 0]
        g = {}
        if ids.size:
            ones = np.ones_like(lab, dtype=np.uint8)
            coms = np.atleast_2d(ndimage.center_of_mass(ones, lab, ids))
            areas = np.atleast_1d(ndimage.sum(ones, lab, ids))
            for cid, com, a in zip(ids, coms, areas):
                g[int(cid)] = (float(com[0]), float(com[1]), float(a))
        out.append(g)
    return out


def _touches_border(lab, cid) -> bool:
    return bool((lab[0] == cid).any() or (lab[-1] == cid).any()
                or (lab[:, 0] == cid).any() or (lab[:, -1] == cid).any())


def infer_divisions(labels, prox_factor: float = 1.0) -> list:
    """Division events inferred from the mask track topology alone — no
    ``divisions.json``.

    A division is a **daughter track that first appears adjacent to a parent track
    present in the previous frame**: the new cell emerges from within / touching the
    parent's footprint (centroid distance ≤ ``prox_factor``·(rₚ+r_d), the cells'
    equivalent radii), and is **not** first seen touching the image border (a track
    that enters the field of view is migrating in, not dividing). Geometry only, but
    every event references real, surviving track IDs, so it is always consistent with
    the cleaned masks. Returns ``[{parent, daughter, frame, score(nan),
    parent_centroid, daughter_centroid}]`` (the shape the GUI consumes)."""
    labels = np.asarray(labels)
    if labels.ndim != 3 or labels.shape[0] < 2:
        return []
    geom = _frame_geometry(labels)
    spans = track_spans(labels)
    events = []
    for d, (f0, _last) in sorted(spans.items()):
        if f0 == 0 or d not in geom[f0] or _touches_border(labels[f0], d):
            continue
        cy, cx, a_d = geom[f0][d]
        r_d = (a_d / np.pi) ** 0.5
        best, best_dist = None, np.inf
        for p, (pcy, pcx, a_p) in geom[f0 - 1].items():
            if p == d:
                continue
            dist = float(np.hypot(cy - pcy, cx - pcx))
            if dist <= prox_factor * (r_d + (a_p / np.pi) ** 0.5) and dist < best_dist:
                best, best_dist = p, dist
        if best is not None:
            pcy, pcx, _ = geom[f0 - 1][best]
            events.append({"parent": int(best), "daughter": int(d),
                           "frame": int(f0), "score": float("nan"),
                           "parent_centroid": [pcy, pcx],
                           "daughter_centroid": [cy, cx]})
    return events
