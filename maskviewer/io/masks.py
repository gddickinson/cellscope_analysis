"""Load CellScope detection masks (`masks.npz`).

The pipeline writes a single array under key `labels` of shape (T, H, W),
int32: 0 = background, >0 = a cell ID that is **consistent across frames**
(i.e. the same integer is the same tracked cell over time). This module
loads that array and offers a few label helpers; it is GUI-agnostic.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

# Per-pixel detection-source codes in the pipeline's `fusion_source_stack`
# (DIC↔Cy5 detection fusion): 0 = background, then which channel(s) detected it.
_SOURCE_KEY = "fusion_source_stack"
SOURCE_CODE_NAME = {1: "DIC", 2: "Cy5", 3: "both"}
SOURCE_CODE_COLOR = {1: (214, 39, 40), 2: (240, 200, 0), 3: (60, 200, 60)}  # red/yellow/lime


@dataclass
class Masks:
    path: str
    labels: np.ndarray            # (T, H, W) int
    source_path: str | None = None   # npz holding `fusion_source_stack` (or None)

    @property
    def n_frames(self) -> int:
        return int(self.labels.shape[0])

    @property
    def shape_hw(self) -> tuple:
        return (int(self.labels.shape[1]), int(self.labels.shape[2]))

    @property
    def max_label(self) -> int:
        return int(self.labels.max()) if self.labels.size else 0

    def frame(self, t: int) -> np.ndarray:
        t = max(0, min(t, self.n_frames - 1))
        return np.asarray(self.labels[t])

    def cell_ids(self) -> np.ndarray:
        """All non-zero label IDs present anywhere in the stack."""
        u = np.unique(self.labels)
        return u[u > 0]

    def n_cells_per_frame(self) -> np.ndarray:
        return np.array([int(np.count_nonzero(np.unique(self.labels[t]) > 0))
                         for t in range(self.n_frames)])

    def source_stack(self):
        """(T, H, W) uint8 per-pixel detection-source codes, or None.

        Lazily read from ``source_path`` (a sibling pipeline artifact). DISPLAY /
        QC only — provenance of where each mask region was detected; never fed to
        analysis (kept apart from the masks-only analysis path)."""
        if not getattr(self, "_source_loaded", False):
            self._source = None
            if self.source_path and os.path.exists(self.source_path):
                try:
                    with np.load(self.source_path) as z:
                        if _SOURCE_KEY in z:
                            s = np.asarray(z[_SOURCE_KEY])
                            self._source = s[None] if s.ndim == 2 else s
                except Exception:
                    self._source = None
            self._source_loaded = True
        return self._source

    def cell_sources(self) -> dict:
        """``{cell_id: dominant source code}`` by majority pixel vote over each cell's
        whole track (matches the pipeline's per-track ``fusion_source``). ``{}`` if no
        source data. Codes per ``SOURCE_CODE_NAME`` (1=DIC, 2=Cy5, 3=both)."""
        src = self.source_stack()
        if src is None:
            return {}
        mx = self.max_label
        cnt = np.zeros((mx + 1, 4), np.int64)            # columns 1/2/3 used
        for t in range(min(self.n_frames, src.shape[0])):
            lab = np.asarray(self.labels[t]).ravel()
            s = np.asarray(src[t]).ravel()
            for code in (1, 2, 3):
                sel = s == code
                if sel.any():
                    cnt[:, code] += np.bincount(lab[sel], minlength=mx + 1)
        out = {}
        for cid in range(1, mx + 1):
            c = cnt[cid, 1:4]
            if c.sum() > 0:
                out[cid] = int(np.argmax(c) + 1)
        return out


def _find_source_path(path: str, keys) -> str | None:
    """The npz holding ``fusion_source_stack`` — the loaded file if it has it, else a
    sibling pipeline artifact (the final `masks.npz` drops the source stack, but the
    pre-cleaning backups keep it). None if none is found."""
    if _SOURCE_KEY in keys:
        return path
    d = os.path.dirname(path)
    for sib in ("masks_precleanup.npz", "masks_original.npz"):
        sp = os.path.join(d, sib)
        if os.path.exists(sp):
            try:
                with np.load(sp) as z:
                    if _SOURCE_KEY in z:
                        return sp
            except Exception:
                pass
    return None


def load_masks(path: str) -> Masks:
    """Read a `masks.npz` (key `labels`, else the first stored array)."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with np.load(path) as z:
        keys = list(z.keys())
        arr = z["labels"] if "labels" in z else (z[keys[0]] if keys else None)
        if arr is None:
            raise ValueError(f"{path}: empty npz")
        arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = arr[None]
    return Masks(path=path, labels=arr, source_path=_find_source_path(path, keys))
