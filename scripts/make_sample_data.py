#!/usr/bin/env python
"""Generate a tiny SYNTHETIC recording + mask so the viewer runs out of the box.

Writes, under `sample_data/Pos_demo/`:
  Pos_demo.ome.tif           (T, C, H, W) uint16 — 2 channels (fluo, DIC-ish)
  Pos_demo.ome.json          sidecar (um_per_px, time_interval_min, channels)
  pipeline_results/masks.npz labels (T, H, W) int32, track-consistent IDs

Entirely synthetic (moving Gaussian blobs) — NO real microscopy data, safe
for a public repo. Re-run any time: `python scripts/make_sample_data.py`.
"""
from __future__ import annotations

import os
import json
import numpy as np
import tifffile

T, H, W = 8, 192, 192
UM_PER_PX = 0.6523
DT_MIN = 10.0
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "sample_data", "Pos_demo")


def _blob(cy, cx, rad, shape):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return ((yy - cy) ** 2 + (xx - cx) ** 2) <= rad ** 2


def main():
    os.makedirs(os.path.join(OUT, "pipeline_results"), exist_ok=True)
    rng = np.random.default_rng(0)
    # three cells on linear-ish tracks
    tracks = [(40, 30, 1.4, 1.1, 16), (100, 150, -1.0, 0.6, 20),
              (150, 60, 0.5, 1.6, 13)]
    data = np.zeros((T, 2, H, W), dtype=np.uint16)
    labels = np.zeros((T, H, W), dtype=np.int32)
    for t in range(T):
        fluo = rng.normal(300, 25, (H, W))
        dic = rng.normal(1500, 40, (H, W))
        for cid, (y0, x0, vy, vx, rad) in enumerate(tracks, start=1):
            cy, cx = y0 + vy * t, x0 + vx * t
            m = _blob(cy, cx, rad, (H, W))
            fluo[m] += 1600
            dic[m] -= 500                       # DIC: cells darker than background
            labels[t][m] = cid
        data[t, 0] = np.clip(fluo, 0, 65535)
        data[t, 1] = np.clip(dic, 0, 65535)

    tif = os.path.join(OUT, "Pos_demo.ome.tif")
    tifffile.imwrite(tif, data, metadata={"axes": "TCYX"})
    with open(os.path.join(OUT, "Pos_demo.ome.json"), "w") as f:
        json.dump({"um_per_px": UM_PER_PX, "time_interval_min": DT_MIN,
                   "channel_names": ["Fluo (synthetic)", "DIC (synthetic)"],
                   "name": "Pos_demo", "metadata_source": "make_sample_data.py"},
                  f, indent=2)
    np.savez_compressed(os.path.join(OUT, "pipeline_results", "masks.npz"),
                        labels=labels)
    print(f"Wrote synthetic sample → {OUT}  "
          f"(data {data.shape}, {len(tracks)} cells)")


if __name__ == "__main__":
    main()
