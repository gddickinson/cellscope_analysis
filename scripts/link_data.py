#!/usr/bin/env python
"""Populate the local `data/` folder with symlinks into a CellScope tree.

Convenience + a ready-made viewer data_root: links every recording, the
aggregate results, and the ground-truth dirs from a CellScope project into
`data/` (which is **gitignored** — the symlinks point at private local data
and this is a PUBLIC repo). Re-run whenever the source paths change.

    python scripts/link_data.py
    python scripts/link_data.py --source /path/to/cellscope/ic295_analysis \
                                --gt     /path/to/cellscope/data

Creates:
    data/by_condition              -> <source>/by_condition        (whole tree)
    data/recordings/<cond>__<label>-> each recording folder         (flat)
    data/results/compare           -> <source>/compare
    data/results/compare_pooled    -> <source>/compare_pooled
    data/gt/<name>                 -> <gt>/<name>                   (GT dirs)
"""
from __future__ import annotations

import os
import argparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
DEFAULT_SOURCE = "/Users/george/claude_test/cellscope/ic295_analysis"
DEFAULT_GT = "/Users/george/claude_test/cellscope/data"


def _link(src: str, dst: str) -> bool:
    """Create/refresh a symlink dst -> src (absolute). Skip if src missing."""
    src = os.path.abspath(src)
    if not os.path.exists(src):
        print(f"  skip (missing): {src}")
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.islink(dst):
        os.unlink(dst)
    elif os.path.exists(dst):
        print(f"  skip (real path in the way, not a symlink): {dst}")
        return False
    os.symlink(src, dst)
    return True


def _subdirs(path: str):
    if not os.path.isdir(path):
        return []
    return sorted(d for d in os.listdir(path)
                  if os.path.isdir(os.path.join(path, d)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=DEFAULT_SOURCE,
                    help="CellScope analysis dir (has by_condition/, compare/)")
    ap.add_argument("--gt", default=DEFAULT_GT,
                    help="CellScope data dir holding ground-truth folders")
    args = ap.parse_args(argv)

    n = 0
    # whole condition-grouped tree (also the recommended viewer data_root)
    bc = os.path.join(args.source, "by_condition")
    n += _link(bc, os.path.join(DATA, "by_condition"))

    # flat per-recording links: data/recordings/<cond>__<label>
    recs = 0
    for cond in _subdirs(bc):
        for label in _subdirs(os.path.join(bc, cond)):
            if _link(os.path.join(bc, cond, label),
                     os.path.join(DATA, "recordings", f"{cond}__{label}")):
                recs += 1
    print(f"  linked {recs} recordings")

    # aggregate results
    for name in ("compare", "compare_pooled"):
        n += _link(os.path.join(args.source, name),
                   os.path.join(DATA, "results", name))

    # ground truth
    gt = 0
    for name in _subdirs(args.gt):
        if name.startswith((".", "gt_backups")):
            continue
        if "gt" in name.lower() or name in ("ic295_gt_full", "legacy_gt"):
            gt += _link(os.path.join(args.gt, name),
                        os.path.join(DATA, "gt", name))
    print(f"  linked {gt} ground-truth dir(s)")

    print(f"\nDone → {DATA}  ({recs} recordings + results + gt). "
          "data/ is gitignored.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
