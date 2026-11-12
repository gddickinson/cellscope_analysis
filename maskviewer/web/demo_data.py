"""SYNTHETIC demo results set for the web interface (no real microscopy data).

Simulated cells (irregular, wobbling outlines; some round up for a few frames) move by a
persistent random walk inside a small field, and are written in the CellScope results
layout (`io.writer.write_recording`) as a ``by_condition`` tree:

    <out>/by_condition/<condition>/<label>/<label>.ome.tif + .ome.json + pipeline_results/masks.npz

The two "conditions" are two simulated motion models, not treatments:
``persistent_walk`` (small turning noise) and ``random_walk`` (large turning noise). Every
value is generated from a fixed seed, so the set (and every number shown on the web
site) is reproducible. `ensure_demo(out)` writes it once (keyed by ``DEMO_VERSION``).
"""
from __future__ import annotations

import json
import os
import shutil

import numpy as np

from ..io.writer import write_recording

DEMO_VERSION = 1
UM_PER_PX = 1.0
DT_MIN = 10.0
CHANNELS = ["Fluo (synthetic)", "DIC (synthetic)"]
# condition -> (turning-noise SD per frame in rad, description)
CONDITIONS = {
    "persistent_walk": (0.25, "simulated persistent random walk (turning noise 0.25 rad/frame)"),
    "random_walk": (1.6, "simulated random walk (turning noise 1.6 rad/frame)"),
}
N_REC = 3                                  # recordings per condition
SOURCE = "maskviewer/web/demo_data.py (synthetic)"


def _cell_mask(cy, cx, radius, elong, phi, wob, shape):
    """Boolean mask of a star-shaped cell: r(θ) = R(1 + e·cos 2(θ−φ) + Σ wobble harmonics)."""
    H, W = shape
    yy, xx = np.mgrid[:H, :W]
    dy, dx = yy - cy, xx - cx
    th = np.arctan2(dy, dx)
    r = radius * (1.0 + elong * np.cos(2 * (th - phi))
                  + sum(a * np.cos(k * th + p) for k, a, p in wob))
    return dy * dy + dx * dx <= r * r


def simulate(seed, turn_sd, T=24, H=160, W=160, n_cells=5, speed=(1.5, 3.0)):
    """(data (T,2,H,W) uint16, labels (T,H,W) int32) for one synthetic recording."""
    rng = np.random.default_rng(seed)
    cells = []
    for _ in range(n_cells):
        rnd = rng.random(2)
        cells.append({
            "y": rng.uniform(25, H - 25), "x": rng.uniform(25, W - 25),
            "theta": rng.uniform(-np.pi, np.pi), "v": rng.uniform(*speed),
            "R": rng.uniform(19, 25), "elong": rng.uniform(0.05, 0.3),
            "wob": [(k, rng.uniform(0.02, 0.07), rng.uniform(0, 2 * np.pi)) for k in (3, 4, 5)],
            # a third of cells round up (shrink, lose elongation) for 4-6 frames
            "round": (int(rng.integers(4, T - 8)), int(rng.integers(4, 7))) if rnd[0] < 0.4 else None,
            "start": int(rng.integers(0, 4)) if rnd[1] < 0.3 else 0,   # some appear late
        })
    data = np.zeros((T, 2, H, W), np.uint16)
    labels = np.zeros((T, H, W), np.int32)
    for t in range(T):
        fluo = rng.normal(300, 25, (H, W))
        dic = rng.normal(1500, 40, (H, W))
        for cid, c in enumerate(cells, start=1):
            if t > 0:                                   # persistent random walk step
                c["theta"] += rng.normal(0, turn_sd)
                c["y"] += c["v"] * np.sin(c["theta"])
                c["x"] += c["v"] * np.cos(c["theta"])
                if not 8 < c["y"] < H - 8:              # bounce off the field edge
                    c["theta"] = -c["theta"]; c["y"] = min(max(c["y"], 8), H - 8)
                if not 8 < c["x"] < W - 8:
                    c["theta"] = np.pi - c["theta"]; c["x"] = min(max(c["x"], 8), W - 8)
            if t < c["start"]:
                continue
            R, elong = c["R"], c["elong"]
            if c["round"] and c["round"][0] <= t < c["round"][0] + c["round"][1]:
                R, elong = R * 0.62, 0.02
            m = _cell_mask(c["y"], c["x"], R, elong, c["theta"], c["wob"], (H, W))
            labels[t][m] = cid                          # later cells overlie earlier ones
            fluo[m] += 900 + 120 * cid
            dic[m] -= 450
        data[t, 0] = np.clip(fluo, 0, 65535)
        data[t, 1] = np.clip(dic, 0, 65535)
    return data, labels


def recordings():
    """[(condition, label, seed, turn_sd)] for the demo set."""
    out = []
    for ci, (cond, (sd, _)) in enumerate(CONDITIONS.items()):
        for r in range(N_REC):
            out.append((cond, f"{cond[:4]}_{r + 1}", 1000 + 10 * ci + r, sd))
    return out


def ensure_demo(out: str) -> str:
    """Write the demo tree under ``out`` (once per DEMO_VERSION); returns its by_condition root."""
    root = os.path.join(out, "by_condition")
    stamp = os.path.join(out, "DEMO_VERSION.json")
    try:
        with open(stamp) as f:
            if json.load(f).get("version") == DEMO_VERSION:
                return root
    except (OSError, ValueError):
        pass
    if os.path.isdir(root):
        shutil.rmtree(root)
    for cond, label, seed, sd in recordings():
        data, labels = simulate(seed, sd)
        write_recording(os.path.join(root, cond, label), label, data, labels,
                        UM_PER_PX, DT_MIN, CHANNELS, SOURCE)
    with open(stamp, "w") as f:
        json.dump({"version": DEMO_VERSION, "synthetic": True, "source": SOURCE}, f)
    return root
