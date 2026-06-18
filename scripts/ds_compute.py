"""Compute (and cache) the per-cell / per-recording / MSD / autocorrelation tables
for each dataset via `compare.build_comparison`. Heavy step — cached to CSV under
OUT/<key>/ so the stats/figures/report can iterate without recomputing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from maskviewer import project as projmod  # noqa: E402
from maskviewer.analysis import compare  # noqa: E402
import ds_config as cfg  # noqa: E402


def _paths(key):
    d = os.path.join(cfg.OUT, key)
    return {n: os.path.join(d, f"{n}.csv")
            for n in ("per_cell", "per_recording", "msd", "autocorr")}


def compute_dataset(ds, recompute=False):
    """Return {per_cell, per_recording, msd, autocorr} DataFrames for one dataset,
    from cache when present (unless recompute)."""
    key, root = ds["key"], ds["root"]
    p = _paths(key)
    if not recompute and all(os.path.exists(v) for v in p.values()):
        print(f"[{key}] loading cached tables")
        return {n: pd.read_csv(p[n]) for n in p}

    os.makedirs(os.path.join(cfg.OUT, key), exist_ok=True)
    proj = projmod.from_data_roots(root, name=key)
    n = len(proj.entries)
    print(f"[{key}] computing {n} recordings (build_comparison)…")
    per_cell, msd, autocorr = compare.build_comparison(
        proj.entries,
        progress_cb=lambda i, t: print(f"  [{key}] {i}/{t}", end="\r") or True)
    print()
    if per_cell is None or per_cell.empty:
        raise SystemExit(f"[{key}] no cells found")
    per_rec = compare.aggregate(per_cell)
    out = {"per_cell": per_cell, "per_recording": per_rec,
           "msd": msd if msd is not None else pd.DataFrame(),
           "autocorr": autocorr if autocorr is not None else pd.DataFrame()}
    for name, df in out.items():
        df.to_csv(p[name], index=False)
    print(f"[{key}] wrote {len(per_cell)} cells / {len(per_rec)} recordings → {cfg.OUT}/{key}")
    return out


def compute_all(recompute=False):
    return {ds["key"]: compute_dataset(ds, recompute) for ds in cfg.DATASETS}


if __name__ == "__main__":
    compute_all("--recompute" in sys.argv)
