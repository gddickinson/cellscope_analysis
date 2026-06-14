"""Discover recordings + their masks under one or more data roots.

A CellScope results tree looks like:

    <root>/<condition>/<label>/<name>.ome.tif
    <root>/<condition>/<label>/pipeline_results/masks.npz

(the `by_condition/` layout), but discovery only relies on the invariant
"a recording folder contains a `*.ome.tif` and a `pipeline_results/masks.npz`".
The flat sample layout `<root>/<label>/...` works too. Real data lives
outside this repo and is pointed at via `config.json` (see config loader);
the bundled `sample_data/` is a tiny synthetic stand-in.
"""
from __future__ import annotations

import os
import glob
from dataclasses import dataclass

from .recording import load_recording, Recording
from .masks import load_masks, Masks
from .divisions import load_divisions, divisions_path_for


@dataclass
class Entry:
    """One discovered recording: paths now, pixels loaded on demand."""
    label: str
    condition: str
    recording_path: str
    mask_path: str | None

    def load_recording(self) -> Recording:
        return load_recording(self.recording_path)

    def load_masks(self) -> Masks | None:
        return load_masks(self.mask_path) if self.mask_path else None

    def load_divisions(self) -> list:
        """Division events (parent→daughter, frame) from the sibling
        divisions.json, or [] if none."""
        return load_divisions(divisions_path_for(self.mask_path))


def _first_tif(folder: str) -> str | None:
    tifs = sorted(glob.glob(os.path.join(folder, "*.ome.tif")) or
                  glob.glob(os.path.join(folder, "*.tif")))
    return tifs[0] if tifs else None


def discover(roots) -> list:
    """Walk `roots` for recording folders → sorted list of `Entry`.

    A folder qualifies if it holds a `*.ome.tif`/`*.tif`; its masks are the
    sibling `pipeline_results/masks.npz` (or any `*.npz` in the folder)."""
    if isinstance(roots, (str, os.PathLike)):
        roots = [roots]
    entries: dict[str, Entry] = {}
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for dirpath, _dirs, _files in os.walk(root):
            if os.path.basename(dirpath) == "pipeline_results":
                continue
            tif = _first_tif(dirpath)
            if not tif:
                continue
            label = os.path.basename(dirpath.rstrip(os.sep))
            parent = os.path.basename(os.path.dirname(dirpath.rstrip(os.sep)))
            condition = parent if parent not in ("", os.path.basename(root)) else ""
            mask = os.path.join(dirpath, "pipeline_results", "masks.npz")
            if not os.path.exists(mask):
                npzs = sorted(glob.glob(os.path.join(dirpath, "*.npz")))
                mask = npzs[0] if npzs else None
            entries.setdefault(tif, Entry(label, condition, tif, mask))
    return sorted(entries.values(), key=lambda e: (e.condition, e.label))
