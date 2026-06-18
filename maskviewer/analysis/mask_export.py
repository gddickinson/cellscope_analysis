"""Export a ``(T, H, W)`` int label stack to formats other viewers/software read —
**ImageJ/Fiji TIFF stack**, per-frame **TIFF** / **PNG** sequences, and **NumPy**
(`.npz`/`.npy`). Pure / GUI-free; the GUI dialog (`gui/mask_export_dialog.py`) and the
analysis package both call it. `0` = background; positive integers are tracked cell IDs,
consistent across frames (preserved exactly — these are label images, not renders).
"""
from __future__ import annotations

import os

import numpy as np

# (key, menu label, is_sequence) — order shown in the dialog.
FORMATS = [
    ("tiff_stack", "TIFF stack — multi-page, ImageJ/Fiji (one file)", False),
    ("tiff_seq", "TIFF sequence — one file per frame", True),
    ("png_seq", "PNG sequence — one file per frame", True),
    ("npz", "NumPy .npz — `labels` key (same as the input masks)", False),
    ("npy", "NumPy .npy — raw label array", False),
]
_FMT_KEYS = {k for k, _l, _s in FORMATS}


def _smallest_uint(labels):
    """Cast to the smallest *lossless* unsigned int (8/16/32-bit) — broadly readable."""
    m = int(labels.max()) if labels.size else 0
    dt = np.uint8 if m < 256 else (np.uint16 if m < 65536 else np.uint32)
    return labels.astype(dt, copy=False)


def relabel_consecutive(labels):
    """Remap positive IDs to a dense ``1..N`` (keeping ``0`` = background) — some tools
    expect consecutive labels. Track identity is otherwise unchanged."""
    labels = np.asarray(labels)
    ids = np.unique(labels)
    ids = ids[ids != 0]
    lut = np.zeros(int(labels.max()) + 1, dtype=np.int64) if labels.size else np.zeros(1)
    for new, old in enumerate(ids, start=1):
        lut[int(old)] = new
    return lut[labels].astype(labels.dtype, copy=False)


def _write_frame(frame, path):
    if path.endswith(".tif"):
        import tifffile
        tifffile.imwrite(path, frame)
    else:                                              # PNG via Pillow (8/16-bit grey)
        from PIL import Image
        if frame.dtype == np.uint32:
            raise ValueError("PNG supports ≤16-bit; >65535 labels — use TIFF or NumPy.")
        Image.fromarray(frame).save(path)


def _sequence(arr, out_dir, prefix, ext):
    os.makedirs(out_dir, exist_ok=True)
    n = arr.shape[0]
    w = max(4, len(str(max(n - 1, 0))))
    paths = []
    for t in range(n):
        p = os.path.join(out_dir, f"{prefix}t{t:0{w}d}{ext}")
        _write_frame(arr[t], p)
        paths.append(p)
    return paths


def _tiff_stack(arr, path, um_per_px, dt_min):
    import tifffile
    meta = {"axes": "TYX"}
    if dt_min:
        meta["finterval"] = float(dt_min) * 60.0       # ImageJ frame interval (seconds)
    kw = {}
    if um_per_px:
        kw["resolution"] = (1.0 / float(um_per_px), 1.0 / float(um_per_px))
        meta["unit"] = "um"
    tifffile.imwrite(path, arr, imagej=True, metadata=meta, **kw)
    return path


def export_masks(labels, fmt, out_dir, prefix="", um_per_px=None, dt_min=None,
                 relabel=False, progress_cb=None):
    """Write one recording's `labels` (T,H,W) into `out_dir` in format `fmt`. Sequences go
    to ``<out_dir>/<prefix>tNNNN.<ext>``; single-file formats to ``<out_dir>/<prefix>masks.<ext>``.
    Returns the list of written paths."""
    if fmt not in _FMT_KEYS:
        raise ValueError(f"unknown mask format {fmt!r}")
    labels = np.asarray(labels)
    if relabel:
        labels = relabel_consecutive(labels)
    arr = _smallest_uint(labels)
    os.makedirs(out_dir, exist_ok=True)
    if fmt == "tiff_stack":
        paths = [_tiff_stack(arr, os.path.join(out_dir, f"{prefix}masks.tif"),
                             um_per_px, dt_min)]
    elif fmt == "npz":
        p = os.path.join(out_dir, f"{prefix}masks.npz")
        np.savez_compressed(p, labels=arr)
        paths = [p]
    elif fmt == "npy":
        p = os.path.join(out_dir, f"{prefix}masks.npy")
        np.save(p, arr)
        paths = [p]
    else:                                              # tiff_seq / png_seq
        paths = _sequence(arr, out_dir, prefix, ".tif" if fmt == "tiff_seq" else ".png")
    if progress_cb:
        progress_cb(1, 1)
    return paths


def _load_masks_fov(entry, scale_override, corrections):
    """Load a recording's label stack with the project FOV crop applied (channel
    alignment doesn't affect masks) + the resolved µm/px + min/frame. None if no masks."""
    from . import fov as _fov
    masks = entry.load_masks()
    if masks is None:
        return None
    rec = entry.load_recording()
    px, dt = (scale_override or (None, None))
    um = float(px) if px else rec.um_per_px
    dtm = float(dt) if dt else rec.time_interval_min
    labels = _fov.apply_fov(masks.labels, rec.fov) if rec.fov else masks.labels
    return labels, um, dtm


def export_masks_project(entries, fmt, out_dir, relabel=False, scale_override=None,
                         corrections=None, excluded=None, progress_cb=None):
    """Export masks for **every recording** in a project — each into its own
    ``<out_dir>/<label>/`` subfolder (sequences) or ``<out_dir>/<label>_masks.<ext>``
    (single-file). Skips `excluded`. ``progress_cb(done, total)`` advances per recording."""
    corrections, excluded = corrections or {}, set(excluded or ())
    ents = [e for e in entries if e.label not in excluded]
    is_seq = dict((k, s) for k, _l, s in FORMATS)[fmt]
    paths, n = {}, len(ents)
    for i, e in enumerate(ents):
        if progress_cb:
            progress_cb(i, n)
        loaded = _load_masks_fov(e, scale_override, corrections)
        if loaded is None:
            continue
        labels, um, dt = loaded
        sub = os.path.join(out_dir, e.label) if is_seq else out_dir
        prefix = "" if is_seq else f"{e.label}_"
        paths[e.label] = export_masks(labels, fmt, sub, prefix, um, dt, relabel)
    if progress_cb:
        progress_cb(n, n)
    return paths
