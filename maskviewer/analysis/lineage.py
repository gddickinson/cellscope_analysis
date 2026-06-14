"""Cell lineage + division helpers (GUI-free).

Track lifespans from mask presence + division events (from divisions.json) →
the data for a lineage tree (lifelines + parent→daughter connectors), a division
timeline, and parent/daughter lookups for the cell-info panel.
"""
from __future__ import annotations

import numpy as np


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
