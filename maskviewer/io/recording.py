"""Load a CellScope recording (.ome.tif + .ome.json sidecar).

Recordings are multi-channel time-lapses written by the CellScope pipeline:
a `.ome.tif` of shape (T, C, H, W) uint16 (or (T, H, W) single-channel) and
an optional `.ome.json` sidecar with physical metadata:

    {"um_per_px": 0.6523, "time_interval_min": 10.0,
     "channel_names": ["Cy5", "DIC 10x", "None"], ...}

This module is GUI-agnostic — it just returns a `Recording` with the pixel
array + metadata, lazily loaded.
"""
from __future__ import annotations

import os
import glob
import json
from dataclasses import dataclass, field

import numpy as np
import tifffile


@dataclass
class Recording:
    """A loaded recording. `data` is (T, C, H, W); single-channel inputs are
    promoted to C=1 so the rest of the app has one shape to reason about."""
    path: str
    data: np.ndarray
    channel_names: list
    um_per_px: float | None = None
    time_interval_min: float | None = None
    meta: dict = field(default_factory=dict)

    @property
    def n_frames(self) -> int:
        return int(self.data.shape[0])

    @property
    def n_channels(self) -> int:
        return int(self.data.shape[1])

    @property
    def height(self) -> int:
        return int(self.data.shape[2])

    @property
    def width(self) -> int:
        return int(self.data.shape[3])

    def frame(self, t: int, channel: int) -> np.ndarray:
        """2-D (H, W) image for time `t`, channel `channel`."""
        t = max(0, min(t, self.n_frames - 1))
        channel = max(0, min(channel, self.n_channels - 1))
        return np.asarray(self.data[t, channel])


def _sidecar_path(tif_path: str) -> str | None:
    """`<stem>.ome.tif` → `<stem>.ome.json` (falls back to `<stem>.json`)."""
    for cand in (tif_path[:-len(".ome.tif")] + ".ome.json" if
                 tif_path.endswith(".ome.tif") else None,
                 os.path.splitext(tif_path)[0] + ".json"):
        if cand and os.path.exists(cand):
            return cand
    matches = glob.glob(os.path.join(os.path.dirname(tif_path), "*.ome.json"))
    return matches[0] if matches else None


def channel_names_of(tif_path: str) -> list:
    """Channel names from the sidecar JSON without loading the (large) tif — for
    populating a channel picker cheaply. [] if unknown."""
    sc = _sidecar_path(tif_path) if tif_path else None
    if sc:
        try:
            with open(sc) as f:
                return list(json.load(f).get("channel_names") or [])
        except (OSError, ValueError):
            pass
    return []


def _normalise_axes(arr: np.ndarray) -> np.ndarray:
    """Coerce common layouts to (T, C, H, W)."""
    if arr.ndim == 2:                      # (H, W)            -> (1, 1, H, W)
        return arr[None, None]
    if arr.ndim == 3:                      # (T, H, W)         -> (T, 1, H, W)
        return arr[:, None]
    if arr.ndim == 4:                      # assume (T, C, H, W)
        return arr
    raise ValueError(f"unexpected recording ndim={arr.ndim} (shape {arr.shape})")


def load_recording(tif_path: str) -> Recording:
    """Read a `.ome.tif` + sidecar into a `Recording`."""
    if not os.path.exists(tif_path):
        raise FileNotFoundError(tif_path)
    arr = _normalise_axes(np.asarray(tifffile.imread(tif_path)))
    meta: dict = {}
    sc = _sidecar_path(tif_path)
    if sc:
        try:
            with open(sc) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = {}
    names = meta.get("channel_names") or [f"ch{i}" for i in range(arr.shape[1])]
    if len(names) < arr.shape[1]:
        names = list(names) + [f"ch{i}" for i in range(len(names), arr.shape[1])]
    return Recording(
        path=tif_path, data=arr, channel_names=list(names[:arr.shape[1]]),
        um_per_px=meta.get("um_per_px"),
        time_interval_min=meta.get("time_interval_min"),
        meta=meta,
    )
