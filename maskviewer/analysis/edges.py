"""Per-frame edge flags for tracked cells (for skipping edge-truncated frames).

A cell-frame whose mask reaches the image border is only partially in view —
its centroid is biased inward and its shape unreliable. CellScope already
voids such frames to the `unknown` state (so shape/state metrics exclude
them), but the raw centroid track in the cache does not carry that flag.
This module recomputes it directly from the masks (via the `data/` symlinks):
a cell is edge-truncated in frame t if its label appears in the border pixels
of that frame.

  edge_flags(rebuild=False) -> {recording_label: {cell_id: bool array (T,)}}

Computed once and cached (the mask load dominates); `dynamics` uses it to
NaN-out edge frames from centroid-based metrics.
"""
from __future__ import annotations

import os
import pickle

import numpy as np

from ..config import PROJECT_ROOT, load_config
from ..io import discover, load_masks

EDGE_CACHE = os.path.join(PROJECT_ROOT, "analysis_out", "_edge_flags.pkl")
MARGIN = 0                       # 0 = literal border contact (CellScope default)


def border_labels(frame, margin=MARGIN):
    """Set of non-zero label IDs touching the border of a 2-D label image."""
    m = margin
    strips = (frame[:m + 1, :], frame[-m - 1:, :], frame[:, :m + 1], frame[:, -m - 1:])
    ids = np.unique(np.concatenate([s.ravel() for s in strips]))
    return set(int(v) for v in ids if v > 0)


def recording_edge_flags(labels, margin=MARGIN):
    """(T,H,W) labels → {cell_id: bool array (T,)}, True where that cell
    touches the border in that frame."""
    T = labels.shape[0]
    per_frame = [border_labels(labels[t], margin) for t in range(T)]
    cids = np.unique(labels)
    cids = cids[cids > 0]
    out = {}
    for cid in cids:
        out[int(cid)] = np.array([int(cid) in per_frame[t] for t in range(T)])
    return out


def _build():
    flags = {}
    entries = [e for e in discover(load_config()["data_roots"]) if e.mask_path]
    for i, e in enumerate(entries):
        try:
            labels = load_masks(e.mask_path).labels
        except Exception as exc:                       # skip unreadable, keep going
            print(f"  WARN {e.label}: {exc}", flush=True)
            continue
        flags[e.label] = recording_edge_flags(labels)
        print(f"  [{i + 1}/{len(entries)}] {e.label}: "
              f"{sum(int(a.any()) for a in flags[e.label].values())} "
              f"cells with edge frames", flush=True)
    return flags


def edge_flags(rebuild=False):
    """Return {label: {cell_id: bool array}}, building + caching on first use."""
    if not rebuild and os.path.exists(EDGE_CACHE):
        with open(EDGE_CACHE, "rb") as f:
            return pickle.load(f)
    print("Computing per-frame edge flags from masks (one-time)…", flush=True)
    flags = _build()
    os.makedirs(os.path.dirname(EDGE_CACHE), exist_ok=True)
    with open(EDGE_CACHE, "wb") as f:
        pickle.dump(flags, f)
    print(f"  cached → {EDGE_CACHE}", flush=True)
    return flags


if __name__ == "__main__":
    import sys
    edge_flags(rebuild="--rebuild" in sys.argv)
