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


@dataclass
class Masks:
    path: str
    labels: np.ndarray            # (T, H, W) int

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


def load_masks(path: str) -> Masks:
    """Read a `masks.npz` (key `labels`, else the first stored array)."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with np.load(path) as z:
        if "labels" in z:
            arr = z["labels"]
        else:
            keys = list(z.keys())
            if not keys:
                raise ValueError(f"{path}: empty npz")
            arr = z[keys[0]]
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = arr[None]
    return Masks(path=path, labels=arr)
