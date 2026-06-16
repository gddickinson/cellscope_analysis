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

# tifffile labels position / scene dimensions R (region), I, Q, S(eries) — any of
# these on a series means the file is part of a multi-position acquisition.
_POSITION_AXES = "RIQ"


@dataclass
class Recording:
    """A loaded recording. `data` is (T, C, H, W); single-channel inputs are
    promoted to C=1 so the rest of the app has one shape to reason about.

    `channel_shifts` (channel → (dy, dx) px) and `fov` ((y0,y1,x0,x1)) are
    non-destructive **pre-analysis corrections** (see `analysis.registration` /
    `analysis.fov`): `frame` / `aligned_channel` apply the per-channel shift on
    read; `fov` is the inner field of view (the raw `data` is never modified)."""
    path: str
    data: np.ndarray
    channel_names: list
    um_per_px: float | None = None
    time_interval_min: float | None = None
    meta: dict = field(default_factory=dict)
    channel_shifts: dict = field(default_factory=dict)   # channel -> (dy, dx) px
    fov: tuple | None = None                              # (y0, y1, x0, x1)

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
        """2-D (H, W) image for time `t`, channel `channel` (alignment applied)."""
        t = max(0, min(t, self.n_frames - 1))
        channel = max(0, min(channel, self.n_channels - 1))
        return self._shifted(np.asarray(self.data[t, channel]), channel)

    def aligned_channel(self, channel: int) -> np.ndarray:
        """(T, H, W) stack for `channel` with its alignment shift applied — what
        analysis should sample (e.g. `edge_intensity` against the masks)."""
        channel = max(0, min(channel, self.n_channels - 1))
        return self._shifted(np.asarray(self.data[:, channel]), channel)

    def _shifted(self, arr, channel):
        sh = self.channel_shifts.get(channel) or self.channel_shifts.get(int(channel))
        if not sh or (not sh[0] and not sh[1]):
            return arr
        from ..analysis import registration
        return registration.apply_shift(arr, float(sh[0]), float(sh[1]))


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


def apply_correction(rec: "Recording", corr: dict | None) -> "Recording":
    """Set a recording's non-destructive corrections from a project entry
    (``{"shifts": {channel: [dy, dx]}, "fov": [y0, y1, x0, x1]}``). Mutates +
    returns ``rec``; an empty/None ``corr`` clears them."""
    shifts = (corr or {}).get("shifts") or {}
    parsed = {}
    for k, v in shifts.items():
        try:                                 # skip malformed entries, don't crash
            parsed[int(k)] = (float(v[0]), float(v[1]))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
    rec.channel_shifts = parsed
    fov = (corr or {}).get("fov")
    try:
        rec.fov = tuple(int(x) for x in fov) if fov else None
    except (TypeError, ValueError):
        rec.fov = None
    return rec


def _normalise_axes(arr: np.ndarray) -> np.ndarray:
    """Coerce common layouts to (T, C, H, W)."""
    if arr.ndim == 2:                      # (H, W)            -> (1, 1, H, W)
        return arr[None, None]
    if arr.ndim == 3:                      # (T, H, W)         -> (T, 1, H, W)
        return arr[:, None]
    if arr.ndim == 4:                      # assume (T, C, H, W)
        return arr
    raise ValueError(f"unexpected recording ndim={arr.ndim} (shape {arr.shape})")


def planes_to_tcyx(planes, size_c, size_t, size_z=1, c_fast=True) -> np.ndarray:
    """Reshape one position's physical planes ``(n, H, W)`` → ``(T, C, H, W)``.

    `c_fast` is the page-order convention: True (Micro-Manager / OME ``XYCZT``)
    means the channel varies fastest, so plane index = c + C·(z + Z·t); False
    means time varies fastest. Any Z is folded into C deterministically (these
    recordings are Z=1). Pure + testable — no TIFF object needed."""
    planes = np.asarray(planes)
    n, H, W = planes.shape
    size_z = size_z or 1
    size_c = size_c or 1
    size_t = size_t or (n // max(size_c * size_z, 1))
    if size_c * size_t * size_z != n:
        raise ValueError(
            f"plane count {n} != C·Z·T = {size_c}·{size_z}·{size_t}; this looks "
            f"like a single file holding multiple positions, which is not "
            f"supported (expected one position per file)")
    if c_fast:                              # standard MM: C varies faster than T
        arr = planes.reshape(size_t, size_z * size_c, H, W)
    else:                                   # T varies faster than C
        arr = planes.reshape(size_z * size_c, size_t, H, W).swapaxes(0, 1)
    return arr


def _looks_multiposition(series) -> bool:
    """True for a multi-position acquisition series (a position/scene axis or
    >4 dims) — the file's own pages are then just one of those positions."""
    axes = getattr(series, "axes", "") or ""
    return getattr(series, "ndim", 0) >= 5 or any(a in axes for a in _POSITION_AXES)


def _read_single_position(tf: "tifffile.TiffFile") -> np.ndarray:
    """Extract THIS file's single position from a multi-position OME-TIFF.

    Micro-Manager writes one physical file per stage position, yet each file's
    embedded OME-XML describes the *whole* acquisition (every position) — so the
    naive read reports a phantom ``(R, T, C, H, W)`` stack the viewer rejects.
    The file's own pages are exactly one position; read just those and reshape
    to ``(T, C, H, W)``. Sibling-position files are never opened.

    Dimensions come from the (reliable) series axes/shape; in numpy axis order
    the later of C/T is the faster-varying plane axis. MM ``Summary.Channels``
    is the fallback channel count when the series lacks a C axis."""
    series = tf.series[0]
    axes, shape = series.axes or "", series.shape

    def _dim(letter, default=None):
        return shape[axes.index(letter)] if letter in axes else default

    size_c, size_t, size_z = _dim("C"), _dim("T"), _dim("Z", 1)
    if "C" in axes and "T" in axes:
        c_fast = axes.index("C") > axes.index("T")
    else:
        c_fast = True
    if not size_c:
        mm = (getattr(tf, "micromanager_metadata", None) or {}).get("Summary", {})
        size_c = mm.get("Channels")
    planes = np.stack([p.asarray() for p in tf.pages])          # (n_local, H, W)
    return planes_to_tcyx(planes, size_c, size_t, size_z, c_fast)


def load_recording(tif_path: str) -> Recording:
    """Read a `.ome.tif` + sidecar into a `Recording`.

    Handles both clean per-recording TIFFs and **raw multi-position
    Micro-Manager OME-TIFFs** (each physical file = one stage position, but its
    OME-XML names the whole acquisition) — the latter are read down to their own
    single position so masks still align."""
    if not os.path.exists(tif_path):
        raise FileNotFoundError(tif_path)
    with tifffile.TiffFile(tif_path) as tf:
        series = tf.series[0]
        arr = (_read_single_position(tf) if _looks_multiposition(series)
               else np.asarray(series.asarray()))
    arr = _normalise_axes(arr)
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
