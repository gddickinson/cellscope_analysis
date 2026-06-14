"""Cross-recording comparison — aggregate per-cell metrics over many recordings,
grouped by condition, with **recording = experimental unit**.

`build_comparison` loads each recording's masks (via its `Entry`) and reuses
`exporters.per_cell_table`, tagging rows with the recording label + condition.
`aggregate` reduces to one row per recording (mean over cells = the unit).
`by_condition` + the IC295 arm structure (`feature_tables.ARMS` / `arm_tests`)
give per-arm Kruskal-Wallis + within-arm Bonferroni + the vehicle test. GUI-free.

Heavy (a per-frame regionprops pass per recording) — call with a progress
callback from a worker thread and cache the result.
"""
from __future__ import annotations

import numpy as np

from . import exporters

# arm-ordered conditions for display (IC295); others appended alphabetically
ARM_ORDER = ["WT", "GOF", "KO", "DMSO", "Y1", "OT"]
_SKIP = {"cell_id", "first_frame", "last_frame"}


def build_comparison(entries, progress_cb=None, with_solidity=False):
    """Per-cell DataFrame across all entries with masks (+ recording, condition).

    ``progress_cb(done, total)`` is called per recording; if it returns False the
    run stops early (cancel). Recordings without masks/cells are skipped.
    """
    import pandas as pd
    parts = []
    n = len(entries)
    for i, e in enumerate(entries):
        if progress_cb and progress_cb(i, n) is False:
            break
        masks = e.load_masks()
        if masks is None:
            continue
        rec = e.load_recording()
        df = exporters.per_cell_table(masks.labels, rec.um_per_px,
                                      rec.time_interval_min, with_solidity)
        if df.empty:
            continue
        df = df.copy()
        df["recording"] = e.label
        df["condition"] = e.condition or "?"
        parts.append(df)
    if progress_cb:
        progress_cb(n, n)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def aggregate(per_cell):
    """One row per recording: mean over cells of every numeric metric (+ n_cells)."""
    if per_cell is None or per_cell.empty:
        return per_cell
    num = per_cell.select_dtypes(include="number")
    per_rec = num.groupby(per_cell["recording"]).mean()
    per_rec["condition"] = per_cell.groupby("recording")["condition"].first()
    per_rec["n_cells"] = per_cell.groupby("recording").size()
    return per_rec.reset_index()


def metric_columns(per_cell):
    return [c for c in per_cell.columns
            if c not in _SKIP and c not in ("recording", "condition")
            and np.issubdtype(per_cell[c].dtype, np.number)]


def order_conditions(conditions):
    conds = list(conditions)
    return ([c for c in ARM_ORDER if c in conds]
            + sorted(c for c in conds if c not in ARM_ORDER))


def by_condition(per_recording, metric):
    """{condition: [per-recording values]} for arm tests (recording = unit)."""
    out = {}
    for cond, g in per_recording.groupby("condition"):
        vals = g[metric].to_numpy(float)
        out[cond] = vals[np.isfinite(vals)].tolist()
    return out
