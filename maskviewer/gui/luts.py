"""Lookup tables + per-channel display state for the grayscale base image.

`build_lut` turns a named colormap + gamma + invert into a (256, 4) uint8 RGBA
LUT that pyqtgraph applies after the display levels. Single-hue ramps
(red/green/blue/magenta/cyan/grey) suit fluorescence channels (e.g. SiR-actin
Cy5 in magenta); the perceptual maps come from matplotlib. `DisplayState` is the
small, GUI-free record the viewer caches per channel so contrast/colour survive
channel switches. No Qt import here, so it's importable and testable headless.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

_SINGLE = {
    "grey": (1, 1, 1), "gray": (1, 1, 1),
    "red": (1, 0, 0), "green": (0, 1, 0), "blue": (0, 0, 1),
    "magenta": (1, 0, 1), "cyan": (0, 1, 1), "yellow": (1, 1, 0),
}
_MPL = ["viridis", "magma", "inferno", "plasma", "hot", "jet", "turbo"]
PRESETS = ["grey", "red", "green", "blue", "magenta", "cyan", "yellow"] + _MPL


def build_lut(colormap: str = "grey", gamma: float = 1.0,
              invert: bool = False, n: int = 256) -> np.ndarray:
    """(n, 4) uint8 RGBA LUT. gamma > 1 brightens mid-tones; gamma < 1 darkens."""
    x = np.linspace(0.0, 1.0, n)
    if gamma and gamma != 1.0:
        x = np.clip(x, 0.0, 1.0) ** (1.0 / float(gamma))
    if colormap in _SINGLE:
        r, g, b = _SINGLE[colormap]
        rgb = np.stack([x * r, x * g, x * b], axis=1)
    else:
        import matplotlib
        rgb = matplotlib.colormaps[colormap](x)[:, :3]
    if invert:
        rgb = rgb[::-1]
    lut = np.zeros((n, 4), dtype=np.ubyte)
    lut[:, :3] = (np.clip(rgb, 0.0, 1.0) * 255).astype(np.ubyte)
    lut[:, 3] = 255
    return lut


@dataclass
class DisplayState:
    """Per-channel display settings cached by the viewer."""
    levels: tuple = (0.0, 1.0)
    colormap: str = "grey"
    gamma: float = 1.0
    invert: bool = False

    def lut(self, n: int = 256) -> np.ndarray:
        return build_lut(self.colormap, self.gamma, self.invert, n)
