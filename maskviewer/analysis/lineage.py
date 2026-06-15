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
    """Per frame, ``{cell_id: (cy, cx, area_px, (y0, y1, x0, x1))}`` for present cells —
    centroid, footprint area and the cell's **true bounding box** (one pass)."""
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
            objs = ndimage.find_objects(lab)              # bbox slice per label index
            for cid, com, a in zip(ids, coms, areas):
                sl = objs[int(cid) - 1] if int(cid) - 1 < len(objs) else None
                bb = ((sl[0].start, sl[0].stop, sl[1].start, sl[1].stop)
                      if sl is not None else (0, lab.shape[0], 0, lab.shape[1]))
                g[int(cid)] = (float(com[0]), float(com[1]), float(a), bb)
        out.append(g)
    return out


def _touches_border(lab, cid) -> bool:
    return bool((lab[0] == cid).any() or (lab[-1] == cid).any()
                or (lab[:, 0] == cid).any() or (lab[:, -1] == cid).any())


def _clip01(x):
    return float(max(0.0, min(1.0, x)))


def _circularity(lab, cid, bbox) -> float:
    """Circularity (4π·area / perimeter²) of one cell measured on its **true bounding
    box** — a roundedness proxy for the 'balled' division cue (~1 for a disc, low for an
    elongated cell). Sizing the crop from the bbox (not the area-equivalent radius)
    keeps elongated/protrusive parents from being truncated and reading falsely round."""
    y0, y1, x0, x1 = bbox
    m = lab[max(0, y0 - 1):y1 + 1, max(0, x0 - 1):x1 + 1] == cid
    a = int(m.sum())
    if a < 8:
        return 0.0
    per = cell_metrics._perimeter(m)
    return float(min(4.0 * np.pi * a / (per * per), 1.0)) if per > 0 else 0.0


_DIV_CUES = ("prox", "swell", "balled", "persist", "mass")
# Weighted mean, not a plain average: proximity / persistence / roundedness are the
# reliable mask-only cues, so they carry the decision; area-change + mass only modulate.
_DIV_WEIGHTS = {"prox": 0.25, "persist": 0.25, "balled": 0.20,
                "swell": 0.15, "mass": 0.15}


def _score_division(labels, geom, spans, p, d, f0, last_d, dist, r_d, r_p,
                    window, min_persist) -> dict:
    """Five [0,1] cues for a parent→daughter candidate, computed from the masks and
    calibrated for this project's 2-D footprints (keratinocytes **round up** as they
    divide, so the parent's footprint often *shrinks* rather than swells, and the parent
    usually keeps its ID rather than splitting its mass in half):
      * **prox** — how close the daughter emerges to the parent;
      * **swell** — how much the parent's footprint *departs* from its pre-split
        baseline near the split (up **or** down — rounding shrinks the 2-D area);
      * **balled** — how rounded the parent is in the pre-split ``window``;
      * **persist** — how long the daughter then survives (vs ``min_persist``);
      * **mass** — the daughter is a *plausible* fraction of the parent (not a sliver,
        not larger) — lenient, since the parent commonly continues (no ½-split)."""
    rsum = r_d + r_p
    prox = _clip01(1.0 - dist / (2.0 * rsum)) if rsum > 0 else 0.0
    win = [t for t in range(max(0, f0 - window), f0) if p in geom[t]]
    balled = float(np.mean([_circularity(labels[t], p, geom[t][p][3])
                            for t in win])) if win else 0.0
    # footprint baseline from *before* the pre-split window (early, pre-rounding life),
    # so post-split shrinkage never biases it; bidirectional departure near the split.
    fp0, _fp1 = spans[p]
    early = [geom[t][p][2] for t in range(fp0, max(fp0 + 1, f0 - window)) if p in geom[t]]
    base = float(np.median(early)) if early else (
        float(geom[f0 - 1][p][2]) if p in geom[f0 - 1] else 0.0)
    near = [geom[t][p][2] for t in range(max(0, f0 - window), f0 + 1) if p in geom[t]]
    dev = max((abs(a / base - 1.0) for a in near), default=0.0) if base > 0 else 0.0
    swell = _clip01(dev / 0.4)
    persist = _clip01((last_d - f0 + 1) / float(max(1, min_persist)))   # guard /0
    a_p_prev = geom[f0 - 1][p][2] if p in geom[f0 - 1] else 0.0
    ratio = (geom[f0][d][2] / a_p_prev) if a_p_prev > 0 else 0.0
    # plateau ~1 for ratio∈[0.2, 1.0]; tapers for slivers (<0.2) and over-size (>1.0)
    mass = _clip01(min(ratio / 0.2, (1.3 - ratio) / 0.3, 1.0))
    return {"prox": prox, "swell": swell, "balled": balled,
            "persist": persist, "mass": mass}


def infer_divisions(labels, prox_factor=1.0, window=4, min_persist=5,
                    score_threshold=0.5, return_all=False) -> list:
    """Division events inferred + **scored** from the masks alone — the cue set the
    original pipeline detector used, recomputed in-project on the cleaned label stack
    (no ``divisions.json``, so no stale/removed IDs).

    A candidate is a **daughter track that first appears adjacent to a parent present
    the previous frame** (centroid distance ≤ ``prox_factor``·(rₚ+r_d)) **that continues
    past the split** (the parent is still present at the daughter's first frame — a
    track that ends there is a re-ID/hand-off, not a division), and is **not** first seen
    touching the image border (entering the FOV ≠ dividing). Each candidate is scored on
    five cues, each ∈ [0,1], combined as a **weighted mean** (``_DIV_WEIGHTS`` —
    proximity / persistence / roundedness carry the decision, area-change + mass
    modulate), kept when ``score ≥ score_threshold``:
      * **prox** — how close the daughter emerges to the parent;
      * **swell** — the parent's footprint departing from its pre-split baseline (up or
        down — keratinocytes round up, so the 2-D area often shrinks);
      * **balled** — how rounded the parent is in the pre-split ``window`` (circularity);
      * **persist** — how long the daughter then survives (vs ``min_persist``);
      * **mass** — daughter is a plausible fraction of the parent (lenient — the parent
        usually keeps its ID).
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
        cy, cx, a_d, _bb = geom[f0][d]
        r_d = (a_d / np.pi) ** 0.5
        best, best_dist, r_p = None, np.inf, 0.0
        for p, (pcy, pcx, a_p, _pbb) in geom[f0 - 1].items():
            if p == d or p not in geom[f0]:           # parent must continue past the split
                continue
            rp = (a_p / np.pi) ** 0.5
            dist = float(np.hypot(cy - pcy, cx - pcx))
            if dist <= prox_factor * (r_d + rp) and dist < best_dist:
                best, best_dist, r_p = p, dist, rp
        if best is None:
            continue
        cues = _score_division(labels, geom, spans, best, d, f0, last_d,
                               best_dist, r_d, r_p, window, min_persist)
        score = float(sum(cues[k] * _DIV_WEIGHTS[k] for k in _DIV_CUES))
        if score < score_threshold and not return_all:
            continue
        pcy, pcx, _a, _pbb = geom[f0 - 1][best]
        events.append({"parent": int(best), "daughter": int(d), "frame": int(f0),
                       "score": score, **cues,
                       "parent_centroid": [pcy, pcx], "daughter_centroid": [cy, cx]})
    return events
