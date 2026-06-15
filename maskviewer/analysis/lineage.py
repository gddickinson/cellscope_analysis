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

from . import cell_metrics


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


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def _circularity(lab, cid, cy, cx, area) -> float:
    """Cropped circularity (4π·area / perimeter²) of one cell — a roundedness proxy
    for the 'balled' division cue. Computed on a small crop around the cell."""
    if area < 8:
        return 0.0
    r = int(2.0 * (area / np.pi) ** 0.5) + 4
    y0, y1 = max(0, int(cy) - r), min(lab.shape[0], int(cy) + r + 1)
    x0, x1 = max(0, int(cx) - r), min(lab.shape[1], int(cx) + r + 1)
    m = lab[y0:y1, x0:x1] == cid
    a = int(m.sum())
    per = cell_metrics._perimeter(m) if a >= 8 else 0.0
    return float(min(4.0 * np.pi * a / (per * per), 1.0)) if per > 0 else 0.0


_DIV_CUES = ("prox", "swell", "balled", "persist", "mass")


def _score_division(labels, geom, spans, p, d, f0, last_d, dist, r_d, r_p,
                    window, min_persist) -> dict:
    """Five [0,1] cues for a parent→daughter candidate (the original detector's
    signature, computed from the masks): proximity, parent area-swelling, parent
    balled/rounded, daughter persistence, ½-mass split."""
    rsum = r_d + r_p
    prox = _clip01(1.0 - dist / (2.0 * rsum)) if rsum > 0 else 0.0
    fp0, fp1 = spans[p]                                # parent life → baseline area
    life = [geom[t][p][2] for t in range(fp0, fp1 + 1) if p in geom[t]]
    base = float(np.median(life)) if life else 0.0
    win = [t for t in range(max(0, f0 - window), f0) if p in geom[t]]
    peak = max((geom[t][p][2] for t in win), default=base)
    swell = _clip01(((peak / base) - 1.0) / 0.5) if base > 0 else 0.0
    balled = float(np.mean([_circularity(labels[t], p, *geom[t][p])
                            for t in win])) if win else 0.0
    persist = _clip01((last_d - f0 + 1) / float(min_persist))
    a_p_prev = geom[f0 - 1][p][2]
    ratio = (geom[f0][d][2] / a_p_prev) if a_p_prev > 0 else 0.0
    mass = _clip01(1.0 - 2.0 * abs(ratio - 0.5))
    return {"prox": prox, "swell": swell, "balled": balled,
            "persist": persist, "mass": mass}


def infer_divisions(labels, prox_factor=1.0, window=4, min_persist=5,
                    score_threshold=0.5, return_all=False) -> list:
    """Division events inferred + **scored** from the masks alone — the cue set the
    original pipeline detector used, recomputed in-project on the cleaned label stack
    (no ``divisions.json``, so no stale/removed IDs).

    A candidate is a **daughter track that first appears adjacent to a parent present
    the previous frame** (centroid distance ≤ ``prox_factor``·(rₚ+r_d)), **not** first
    seen touching the image border (entering the FOV ≠ dividing). Each candidate is
    scored on five cues, each ∈ [0,1] (``score`` = their mean), kept when
    ``score ≥ score_threshold``:
      * **prox** — how close the daughter emerges to the parent;
      * **swell** — the parent's area swelling before the split (window peak ÷ life
        baseline);
      * **balled** — how rounded the parent is in the pre-split ``window`` (circularity);
      * **persist** — how long the daughter then survives (vs ``min_persist``);
      * **mass** — daughter:parent area near ½ (a mass split).
    Every event carries ``score`` + the sub-cues and references real surviving tracks.
    ``return_all=True`` also returns sub-threshold candidates (for inspection/tuning)."""
    labels = np.asarray(labels)
    if labels.ndim != 3 or labels.shape[0] < 2:
        return []
    geom = _frame_geometry(labels)
    spans = track_spans(labels)
    events = []
    for d, (f0, last_d) in sorted(spans.items()):
        if f0 == 0 or d not in geom[f0] or _touches_border(labels[f0], d):
            continue
        cy, cx, a_d = geom[f0][d]
        r_d = (a_d / np.pi) ** 0.5
        best, best_dist, r_p = None, np.inf, 0.0
        for p, (pcy, pcx, a_p) in geom[f0 - 1].items():
            rp = (a_p / np.pi) ** 0.5
            dist = float(np.hypot(cy - pcy, cx - pcx))
            if p != d and dist <= prox_factor * (r_d + rp) and dist < best_dist:
                best, best_dist, r_p = p, dist, rp
        if best is None:
            continue
        cues = _score_division(labels, geom, spans, best, d, f0, last_d,
                               best_dist, r_d, r_p, window, min_persist)
        score = float(np.mean([cues[k] for k in _DIV_CUES]))
        if score < score_threshold and not return_all:
            continue
        pcy, pcx, _ = geom[f0 - 1][best]
        events.append({"parent": int(best), "daughter": int(d), "frame": int(f0),
                       "score": score, **cues,
                       "parent_centroid": [pcy, pcx], "daughter_centroid": [cy, cx]})
    return events
