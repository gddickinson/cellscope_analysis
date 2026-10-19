#!/usr/bin/env python3
"""Repair a project whose ``_cache`` symlinks broke during a zip/transfer.

CellScope result trees keep the real recordings in a top-level ``_cache/`` and
reference them from every ``by_condition/<cond>/<rec>/`` folder via **symlinks**
(``*.ome.tif``, ``*_metadata.txt``, …). When such a tree is zipped on macOS and
unzipped on a machine/tool without symlink support (Windows Explorer, some
archivers), each symlink is written out as a tiny **text file holding the link
target** (e.g. ``/Users/.../_cache/X.ome.tif``). The viewer then reads that text
as the image and fails with ``not a TIFF file: header=b'/Use'...``.

The real bytes are still present (in ``_cache/``); only the references are
broken. This script walks the tree, finds every broken reference whose target
basename exists in ``_cache/``, and replaces it with the real file — hard-linking
when possible (no extra disk) and copying otherwise. Cross-platform, stdlib only.

Usage (run on the machine with the broken copy, e.g. the lab PC)::

    python repair_cache_symlinks.py /path/to/ic293_analysis            # dry run
    python repair_cache_symlinks.py /path/to/ic293_analysis --apply    # repair
    python repair_cache_symlinks.py /path/to/ic293_analysis --apply --copy

By default it previews; pass ``--apply`` to actually modify files. ``--copy``
forces real copies instead of hard links (use if the two folders end up on
different drives and you want it explicit).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

# A former-symlink text file is tiny; never treat a big file as a stray pointer.
MAX_REF_BYTES = 4096


def find_cache_dirs(root):
    """All directories named ``_cache`` under *root* (usually exactly one)."""
    out = []
    for dirpath, dirnames, _ in os.walk(root):
        if os.path.basename(dirpath) == "_cache":
            out.append(dirpath)
            dirnames[:] = []  # don't descend into a cache
    return out


def build_cache_index(cache_dirs):
    """Map ``basename -> real path`` for every file in the cache dirs."""
    index = {}
    dups = set()
    for cache in cache_dirs:
        for dirpath, _, filenames in os.walk(cache):
            for name in filenames:
                p = os.path.join(dirpath, name)
                if not os.path.isfile(p):
                    continue
                if name in index and os.path.abspath(index[name]) != os.path.abspath(p):
                    dups.add(name)
                index.setdefault(name, p)
    return index, dups


def _looks_like_path_text(path):
    """Read a tiny file; return its content as a path string if it looks like a
    former symlink target (single line, no NULs, contains a separator)."""
    try:
        if os.path.getsize(path) > MAX_REF_BYTES:
            return None
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return None
    if b"\x00" in blob:
        return None
    try:
        text = blob.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None
    if not text or "\n" in text:
        return None
    if "/" not in text and "\\" not in text:
        return None
    return text


def _target_basename(path):
    """If *path* is a broken reference, return the basename it points at."""
    if os.path.islink(path):
        if os.path.exists(path):
            return None  # link still resolves — not broken
        target = os.readlink(path)
        return os.path.basename(target.replace("\\", "/").rstrip("/"))
    text = _looks_like_path_text(path)
    if text is None:
        return None
    return os.path.basename(text.replace("\\", "/").rstrip("/"))


def iter_broken_refs(root):
    """Yield ``(path, target_basename)`` for every broken reference under *root*,
    skipping the cache dirs themselves."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "_cache"]
        for name in filenames:
            p = os.path.join(dirpath, name)
            base = _target_basename(p)
            if base:
                yield p, base


def repair_one(path, real, copy):
    """Replace broken *path* with *real* (hard link, or copy). Return mode used."""
    os.remove(path)
    if not copy:
        try:
            os.link(real, path)
            return "linked"
        except OSError:
            pass  # cross-device / unsupported — fall back to copy
    shutil.copy2(real, path)
    return "copied"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="project folder to repair (contains _cache/)")
    ap.add_argument("--apply", action="store_true",
                    help="actually repair (default: dry run / preview only)")
    ap.add_argument("--copy", action="store_true",
                    help="copy real files instead of hard-linking")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        ap.error(f"not a directory: {root}")

    cache_dirs = find_cache_dirs(root)
    if not cache_dirs:
        print(f"No _cache/ found under {root}.\n"
              "The real image data isn't in this copy — re-transfer the project "
              "(include _cache/), or copy the recordings with symlinks dereferenced.")
        return 1
    index, dups = build_cache_index(cache_dirs)
    print(f"Cache: {len(index)} files in {len(cache_dirs)} _cache dir(s).")
    if dups:
        print(f"  ({len(dups)} duplicate basenames across caches — first wins)")

    repaired = matched = unmatched = 0
    unmatched_examples = []
    for path, base in iter_broken_refs(root):
        rel = os.path.relpath(path, root)
        if base in index:
            matched += 1
            if args.apply:
                mode = repair_one(path, index[base], args.copy)
                repaired += 1
                print(f"  {mode}: {rel}  <-  _cache/{base}")
            else:
                print(f"  would repair: {rel}  <-  _cache/{base}")
        else:
            unmatched += 1
            if len(unmatched_examples) < 10:
                unmatched_examples.append((rel, base))

    print(f"\nBroken references found: {matched + unmatched} "
          f"({matched} resolvable from _cache, {unmatched} not).")
    if unmatched:
        print("Unmatched (target not in _cache) — usually harmless extras:")
        for rel, base in unmatched_examples:
            print(f"  {rel}  ->  {base}")
        if unmatched > len(unmatched_examples):
            print(f"  … and {unmatched - len(unmatched_examples)} more")

    if not args.apply:
        print(f"\nDRY RUN — nothing changed. Re-run with --apply to repair "
              f"{matched} reference(s).")
    else:
        print(f"\nRepaired {repaired} reference(s). Open the project in the viewer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
