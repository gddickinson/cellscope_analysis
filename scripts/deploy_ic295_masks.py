"""Deploy a masks-only IC295 project next to the lab-share recordings.

Builds a viewer-discoverable ``by_condition/<cond>/<label>/`` tree at a
destination, containing each recording's **masks + provenance + sidecars**
(copied) and a **relative symlink** to the original recording that already
lives on the share. The recordings are *not* copied (they're huge); the
loader reads them in place — including the raw multi-position Micro-Manager
OME-TIFFs (see ``maskviewer/io/recording.py``).

Because the recording link is *relative*, the whole destination tree resolves
on any machine that mounts the same share, regardless of mount point — point
``config.json`` at ``<dest>/by_condition`` and run.

Read-only on the source masks and on the recordings; only writes under
``--dest`` (which must be empty or new). Idempotent + ``--dry-run``.

    python scripts/deploy_ic295_masks.py \
        --source       /Users/george/claude_test/cellscope/ic295_analysis/by_condition \
        --recordings   "/Volumes/pathaklab/Lab/Ignasi/IC295_ECmigrationwithSirActin/IC295__1" \
        --dest         "/Volumes/pathaklab/Lab/Ignasi/IC295_ECmigrationwithSirActin/IC295__1/2026_06_SegmentationMasks" \
        --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import shutil

# Recording / metadata files that are per-position symlinks or huge in the
# source — never copied (the recording is linked instead).
_SKIP_SUFFIXES = (".ome.tif", "_metadata.txt")
_REC_PREFIX = "IC295__1_MMStack_"


def _recording_dirs(source):
    """Yield (condition, label, abs_dir) for every recording folder under a
    ``by_condition`` root (a dir holding a ``pipeline_results/``)."""
    for cond in sorted(os.listdir(source)):
        cdir = os.path.join(source, cond)
        if not os.path.isdir(cdir):
            continue
        for label in sorted(os.listdir(cdir)):
            ldir = os.path.join(cdir, label)
            if os.path.isdir(os.path.join(ldir, "pipeline_results")):
                yield cond, label, ldir


def _copy_real_files(src_dir, dst_dir, dry_run):
    """Copy every real (non-symlink) file under src_dir into dst_dir,
    preserving structure, skipping recording symlinks. Returns bytes copied."""
    total = 0
    for dirpath, _dirs, files in os.walk(src_dir):
        rel = os.path.relpath(dirpath, src_dir)
        out_dir = os.path.normpath(os.path.join(dst_dir, rel))
        for name in sorted(files):
            if name.endswith(_SKIP_SUFFIXES):
                continue
            src = os.path.join(dirpath, name)
            if os.path.islink(src) or not os.path.isfile(src):
                continue
            dst = os.path.join(out_dir, name)
            size = os.path.getsize(src)
            if os.path.exists(dst) and os.path.getsize(dst) == size:
                continue                      # idempotent skip
            total += size
            if dry_run:
                continue
            os.makedirs(out_dir, exist_ok=True)
            tmp = dst + ".tmp"
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
    return total


def _link_recording(recordings, label, label_dst, dry_run):
    """Create a relative symlink <label_dst>/<rec>.ome.tif -> the recording on
    the share. Returns a short status string."""
    name = f"{_REC_PREFIX}{label}.ome.tif"
    target = os.path.join(recordings, name)
    if not os.path.exists(target):
        return "MISSING-RECORDING"
    link = os.path.join(label_dst, name)
    rel = os.path.relpath(os.path.realpath(target), os.path.realpath(label_dst))
    if os.path.islink(link):
        if os.readlink(link) == rel:
            return "link-ok"
        if not dry_run:
            os.unlink(link)
    elif os.path.exists(link):
        return "link-blocked(real-file)"
    if dry_run:
        return f"would-link -> {rel}"
    os.makedirs(label_dst, exist_ok=True)
    os.symlink(rel, link)
    return f"linked -> {rel}"


def _write_config(dest, dry_run):
    """Write a ready-to-use config.json (data_roots -> <dest>/by_condition)."""
    cfg_path = os.path.join(dest, "config.json")
    cfg = {"data_roots": [os.path.join(dest, "by_condition")]}
    if dry_run:
        return cfg_path
    with open(cfg_path, "w") as f:
        json.dump(cfg, f, indent=2)
    return cfg_path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True,
                    help="by_condition root of the masks (real npz/json files)")
    ap.add_argument("--recordings", required=True,
                    help="dir holding the flat IC295__1_MMStack_*.ome.tif originals")
    ap.add_argument("--dest", required=True,
                    help="destination dir (e.g. .../2026_06_SegmentationMasks)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would happen; write nothing")
    args = ap.parse_args(argv)

    for p, what in ((args.source, "source"), (args.recordings, "recordings")):
        if not os.path.isdir(p):
            ap.error(f"{what} not found / not mounted: {p}")

    recs = list(_recording_dirs(args.source))
    if not recs:
        ap.error(f"no recording folders under {args.source}")
    print(f"{'DRY-RUN: ' if args.dry_run else ''}deploying {len(recs)} "
          f"recordings\n  source     : {args.source}\n  recordings : "
          f"{args.recordings}\n  dest       : {args.dest}\n", flush=True)

    by_cond = os.path.join(args.dest, "by_condition")
    copied = 0
    statuses = {}
    for cond, label, ldir in recs:
        label_dst = os.path.join(by_cond, cond, label)
        copied += _copy_real_files(ldir, label_dst, args.dry_run)
        status = _link_recording(args.recordings, label, label_dst, args.dry_run)
        statuses[status.split(" ")[0]] = statuses.get(status.split(" ")[0], 0) + 1
        print(f"  [{cond}/{label}] {status}", flush=True)

    cfg = _write_config(args.dest, args.dry_run)
    print(f"\n=== summary ===")
    print(f"  files to copy : {copied/1e6:.1f} MB")
    print(f"  recording links: " + ", ".join(f"{k}={v}" for k, v in statuses.items()))
    print(f"  config.json   : {cfg}")
    print(f"\nOn the other machine: set cellscope_analysis config.json data_roots")
    print(f"to {os.path.join(args.dest, 'by_condition')!r} (or run with "
          f"--data-root), then `python main_viewer.py`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
