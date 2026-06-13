"""pyqtgraph canvas: a grayscale recording frame + a coloured label overlay.

One `ViewBox` holds two stacked `ImageItem`s — the base channel (grayscale)
and the mask overlay (per-cell colour via a lookup table; background
transparent). Supports global overlay opacity, outline-only mode, and emits
the cell ID under the cursor. Row-major image axis order so (H, W) arrays
display upright.
"""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore

pg.setConfigOptions(imageAxisOrder="row-major", antialias=False)


def make_label_lut(n: int, seed: int = 1) -> np.ndarray:
    """(n+1, 4) RGBA LUT: index 0 transparent, 1..n stable distinct colours."""
    n = max(int(n), 1)
    rng = np.random.default_rng(seed)
    lut = np.zeros((n + 1, 4), dtype=np.ubyte)
    hues = (np.arange(n) * 0.61803398875) % 1.0           # golden-ratio spread
    rng.shuffle(hues)
    for i, h in enumerate(hues, start=1):
        r, g, b = _hsv(h, 0.75, 1.0)
        lut[i] = (r, g, b, 255)
    return lut


def _hsv(h, s, v):
    import colorsys
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))


def label_boundaries(lab: np.ndarray) -> np.ndarray:
    """Label image with interiors zeroed — only boundary pixels keep their ID."""
    b = np.zeros(lab.shape, dtype=bool)
    d = lab[:-1, :] != lab[1:, :]
    b[:-1, :] |= d
    b[1:, :] |= d
    d = lab[:, :-1] != lab[:, 1:]
    b[:, :-1] |= d
    b[:, 1:] |= d
    return np.where(b, lab, 0)


class ImageCanvas(pg.GraphicsLayoutWidget):
    """Base image + label overlay in a locked-aspect viewbox."""

    cellHovered = QtCore.pyqtSignal(int)        # cell id under cursor (0 = none)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vb = self.addViewBox()
        self.vb.setAspectLocked(True)
        self.vb.invertY(True)
        self.base = pg.ImageItem()
        self.overlay = pg.ImageItem()
        self.vb.addItem(self.base)
        self.vb.addItem(self.overlay)
        self._lut = make_label_lut(1)
        self._max_label = 1
        self._cur_labels = None
        self.scene().sigMouseMoved.connect(self._on_move)

    # -- base channel ----------------------------------------------------
    def set_base(self, img: np.ndarray, levels=None):
        self.base.setImage(np.asarray(img), autoLevels=False,
                           levels=levels if levels is not None else None)
        if levels is not None:
            self.base.setLevels(levels)

    # -- label overlay ---------------------------------------------------
    def set_label_lut(self, max_label: int):
        self._max_label = max(int(max_label), 1)
        self._lut = make_label_lut(self._max_label)

    def set_overlay(self, labels: np.ndarray | None, opacity: float = 0.5,
                    outline: bool = False, visible: bool = True):
        if labels is None or not visible:
            self.overlay.clear()
            self._cur_labels = None
            return
        self._cur_labels = np.asarray(labels)
        disp = label_boundaries(self._cur_labels) if outline else self._cur_labels
        self.overlay.setImage(disp, autoLevels=False, levels=(0, self._max_label),
                              lut=self._lut)
        self.overlay.setOpacity(float(opacity))

    def autorange(self):
        self.vb.autoRange()

    # -- hover -> cell id ------------------------------------------------
    def _on_move(self, pos):
        if self._cur_labels is None:
            return
        p = self.base.mapFromScene(pos)
        x, y = int(p.x()), int(p.y())
        h, w = self._cur_labels.shape
        cid = int(self._cur_labels[y, x]) if (0 <= y < h and 0 <= x < w) else 0
        self.cellHovered.emit(cid)
