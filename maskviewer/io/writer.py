"""Write a recording folder in the CellScope results layout (GUI-free).

    <folder>/<name>.ome.tif              (T, C, H, W) uint16 image stack
    <folder>/<name>.ome.json             sidecar: um_per_px, time_interval_min, channel_names
    <folder>/pipeline_results/masks.npz  key ``labels``: (T, H, W) int32, track-consistent IDs

This is the layout `io.dataset.discover` reads. Used by `scripts/make_sample_data.py`
and the synthetic web demo (`maskviewer/web/demo_data.py`); never used to write real data
into this public repo.
"""
from __future__ import annotations

import json
import os

import numpy as np


def write_recording(folder: str, name: str, data: np.ndarray, labels: np.ndarray,
                    um_per_px: float, time_interval_min: float, channel_names,
                    metadata_source: str) -> dict:
    """Write one recording folder; returns the written paths."""
    import tifffile
    os.makedirs(os.path.join(folder, "pipeline_results"), exist_ok=True)
    tif = os.path.join(folder, f"{name}.ome.tif")
    tifffile.imwrite(tif, np.asarray(data, np.uint16), metadata={"axes": "TCYX"})
    side = os.path.join(folder, f"{name}.ome.json")
    with open(side, "w") as f:
        json.dump({"um_per_px": um_per_px, "time_interval_min": time_interval_min,
                   "channel_names": list(channel_names), "name": name,
                   "metadata_source": metadata_source}, f, indent=2)
    npz = os.path.join(folder, "pipeline_results", "masks.npz")
    np.savez_compressed(npz, labels=np.asarray(labels, np.int32))
    return {"tif": tif, "sidecar": side, "masks": npz}
