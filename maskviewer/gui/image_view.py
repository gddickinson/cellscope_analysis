"""pyqtgraph canvas: a grayscale recording frame + a coloured label overlay.

One `ViewBox` stacks two `ImageItem`s — the base channel (grayscale, with a
user LUT + display levels) and the mask overlay (per-cell colour via a lookup
table; background transparent) — plus an `Overlays` layer (scale bar, IDs,
trails, selection). Emits the cell ID under the cursor (`cellHovered`) and the
cell clicked (`cellClicked`). Row-major axis order so (H, W) arrays show upright.
"""
from __future__ import annotations

import colorsys

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtGui

from .overlays import Overlays

pg.setConfigOptions(imageAxisOrder="row-major", antialias=False)


def _hsv(h, s, v):
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v))


def make_label_lut(n: int, seed: int = 1) -> np.ndarray:
    """(n+1, 4) RGBA LUT: index 0 transparent, 1..n stable distinct colours."""
    n = max(int(n), 1)
    rng = np.random.default_rng(seed)
    lut = np.zeros((n + 1, 4), dtype=np.ubyte)
    hues = (np.arange(n) * 0.61803398875) % 1.0           # golden-ratio spread
    rng.shuffle(hues)
    for i, h in enumerate(hues, start=1):
        lut[i] = (*_hsv(h, 0.75, 1.0), 255)
    return lut


def scalar_label_lut(value_by_id: dict, max_label: int,
                     cmap: str = "viridis") -> np.ndarray:
    """(max_label+1, 4) LUT colouring each label by a scalar (e.g. area).

    Values are min-max normalised across the supplied ids; absent labels and
    index 0 are transparent.
    """
    import matplotlib
    lut = np.zeros((max(int(max_label), 1) + 1, 4), dtype=np.ubyte)
    if value_by_id:
        vals = np.array(list(value_by_id.values()), float)
        lo, hi = np.nanmin(vals), np.nanmax(vals)
        rng = (hi - lo) or 1.0
        cm = matplotlib.colormaps[cmap]
        for cid, v in value_by_id.items():
            if 0 < cid < lut.shape[0] and np.isfinite(v):
                r, g, b, _ = cm(float((v - lo) / rng))
                lut[cid] = (int(r * 255), int(g * 255), int(b * 255), 255)
    return lut


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
    """Base image + label overlay + overlays layer in a locked-aspect viewbox."""

    cellHovered = QtCore.pyqtSignal(int)        # cell id under cursor (0 = none)
    cellClicked = QtCore.pyqtSignal(int)        # cell id clicked (0 = empty)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.vb = self.addViewBox()
        self.vb.setAspectLocked(True)
        self.vb.invertY(True)
        self.base = pg.ImageItem()
        self.base.setZValue(0)
        self.overlay = pg.ImageItem()
        self.overlay.setZValue(15)
        self.vb.addItem(self.base)
        self.vb.addItem(self.overlay)
        self._extra = []                  # extra base layers for composite blend
        self.overlays = Overlays(self.vb)
        self._lut = make_label_lut(1)
        self._max_label = 1
        self._cur_labels = None
        self.scene().sigMouseMoved.connect(self._on_move)
        self.scene().sigMouseClicked.connect(self._on_click)

    # -- base channel ----------------------------------------------------
    def set_base(self, img, levels=None, lut=None):
        self._hide_extra()
        self.base.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        self.base.setImage(np.asarray(img), autoLevels=False, levels=levels, lut=lut)

    def set_base_layers(self, layers):
        """Composite blend: layers = [{img, levels, lut}, ...]. The first is the
        opaque base (SourceOver, bottom); the rest blend additively (Plus) on
        top — DIC grey + fluorescence colour, etc."""
        if not layers:
            self.base.clear()
            self._hide_extra()
            return
        first = layers[0]
        self.base.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
        self.base.setImage(np.asarray(first["img"]), autoLevels=False,
                           levels=first.get("levels"), lut=first.get("lut"))
        need = len(layers) - 1
        while len(self._extra) < need:
            it = pg.ImageItem()
            it.setZValue(1 + len(self._extra))
            self.vb.addItem(it)
            self._extra.append(it)
        for i, it in enumerate(self._extra):
            if i < need:
                lyr = layers[i + 1]
                it.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
                it.setImage(np.asarray(lyr["img"]), autoLevels=False,
                            levels=lyr.get("levels"), lut=lyr.get("lut"))
                it.show()
            else:
                it.clear()
                it.hide()

    def _hide_extra(self):
        for it in self._extra:
            it.clear()
            it.hide()

    # -- label overlay ---------------------------------------------------
    def set_label_lut(self, max_label: int):
        self._max_label = max(int(max_label), 1)
        self._lut = make_label_lut(self._max_label)

    def set_overlay(self, labels, opacity: float = 0.5, outline: bool = False,
                    visible: bool = True, lut=None):
        if labels is None or not visible:
            self.overlay.clear()
            self._cur_labels = np.asarray(labels) if labels is not None else None
            return
        self._cur_labels = np.asarray(labels)
        disp = label_boundaries(self._cur_labels) if outline else self._cur_labels
        self.overlay.setImage(disp, autoLevels=False, levels=(0, self._max_label),
                              lut=lut if lut is not None else self._lut)
        self.overlay.setOpacity(float(opacity))

    # -- view ------------------------------------------------------------
    def autorange(self):
        self.vb.autoRange()

    def zoom(self, factor: float):
        self.vb.scaleBy((factor, factor))

    # -- mouse -----------------------------------------------------------
    def _cell_at(self, scene_pos):
        if self._cur_labels is None:
            return 0
        p = self.base.mapFromScene(scene_pos)
        x, y = int(p.x()), int(p.y())
        h, w = self._cur_labels.shape
        return int(self._cur_labels[y, x]) if (0 <= y < h and 0 <= x < w) else 0

    def _on_move(self, pos):
        if self._cur_labels is not None:
            self.cellHovered.emit(self._cell_at(pos))

    def _on_click(self, ev):
        if ev.button() == QtCore.Qt.LeftButton and self._cur_labels is not None:
            self.cellClicked.emit(self._cell_at(ev.scenePos()))
