"""View overlays drawn on top of the image: scale bar, info text, cell-ID
labels, track trails and the selected-cell highlight.

`Overlays` owns a set of pyqtgraph items parented to a ViewBox (all added with
``ignoreBounds=True`` so they never affect auto-range). Corner items (info text,
scale bar) re-anchor to the visible range on every pan/zoom; per-frame items
(IDs, trails, selection) are refreshed by the viewer each frame. Kept apart from
`image_view` so the canvas stays small.
"""
from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets

from ..analysis import contacts as _contacts

_Y = (255, 255, 0)
_W = (255, 255, 255)


def _nice_scale(view_w_px: float, um_per_px: float):
    """A round bar length (~1/5 of the view): (length_µm, length_px)."""
    target = view_w_px * 0.2 * um_per_px
    if target <= 0:
        return 1.0, 1.0
    p = 10 ** math.floor(math.log10(target))
    nice = next((m * p for m in (5, 2, 1) if m * p <= target), p)
    return nice, nice / um_per_px


class Overlays:
    def __init__(self, viewbox):
        self.vb = viewbox
        self.um_per_px = None
        self.show = {"info": True, "scalebar": True, "ids": False,
                     "trails": False, "selection": True, "divisions": False,
                     "contacts": False}
        self._info_text = ""
        self.info = pg.TextItem(color=_W, anchor=(0, 0))
        self.sbar = QtWidgets.QGraphicsLineItem()
        self.sbar.setPen(pg.mkPen(_W, width=4))
        self.sbar_text = pg.TextItem(color=_W, anchor=(0.5, 1))
        self.trails = pg.PlotDataItem(pen=pg.mkPen((255, 255, 0, 150), width=1.2))
        self.sel_rect = QtWidgets.QGraphicsRectItem()
        self.sel_rect.setPen(pg.mkPen(_Y, width=2))
        self.sel_rect.setBrush(pg.mkBrush(None))
        self.sel_marker = pg.ScatterPlotItem(size=16, symbol="+",
                                             pen=pg.mkPen(_Y, width=2), brush=None)
        _R = (255, 60, 60)                            # division marker / link colour
        self.div_link = pg.PlotCurveItem(pen=pg.mkPen(_R, width=2), connect="finite")
        self.div_parent = pg.ScatterPlotItem(size=15, symbol="o",     # parent
                                             pen=pg.mkPen(_R, width=2), brush=None)
        self.div_marker = pg.ScatterPlotItem(size=18, symbol="d",     # daughter
                                             pen=pg.mkPen(_R, width=2), brush=None)
        # cell–cell contact interface pixels (coloured by class: point / extensive)
        self.contacts = pg.ScatterPlotItem(size=5, symbol="s", pen=None)
        self._ids: list = []
        for z, it in ((58, self.contacts), (60, self.trails),
                      (80, self.sel_rect), (81, self.sel_marker),
                      (81, self.div_link), (82, self.div_parent), (82, self.div_marker),
                      (100, self.sbar), (100, self.sbar_text), (100, self.info)):
            it.setZValue(z)
            self.vb.addItem(it, ignoreBounds=True)
        self.vb.sigRangeChanged.connect(lambda *a: self._place_corners())

    # -- public ----------------------------------------------------------
    def set_scale(self, um_per_px):
        self.um_per_px = um_per_px

    def set_show(self, key, on):
        if key in self.show:
            self.show[key] = bool(on)

    def update_overlay(self, *, info_text="", centroids=None, history=None,
                       frame=0, selected=0, bbox=None, division_links=None,
                       contact_interfaces=None):
        """Refresh per-frame overlay items. ``centroids`` / ``bbox`` are
        {id: (y, x)} / {id: (x0, y0, x1, y1)} for the current frame; ``history``
        is {id: (T, 2) (y, x)} for trails; ``division_links`` are
        ``((parent_y, parent_x), (daughter_y, daughter_x))`` pairs dividing here;
        ``contact_interfaces`` is ``(ys, xs, class_codes)`` of contacting pixels."""
        self._info_text = info_text
        self._update_ids(centroids if self.show["ids"] else None)
        self._update_trails(history, frame if self.show["trails"] else None)
        self._update_selection(selected, centroids, bbox)
        self._update_divisions(division_links if self.show["divisions"] else None)
        self._update_contacts(contact_interfaces if self.show["contacts"] else None)
        self._place_corners()

    def _update_contacts(self, interfaces):
        """Mark the contacting boundary pixels, coloured by class (point / extensive)."""
        if interfaces is None or len(interfaces[0]) == 0:
            self.contacts.setVisible(False)
            return
        ys, xs, codes = interfaces
        pt, ext = _contacts.CONTACT_COLOR["point"], _contacts.CONTACT_COLOR["extensive"]
        brushes = [pg.mkBrush(*(ext if c == 2 else pt)) for c in codes]
        self.contacts.setData(x=np.asarray(xs, float), y=np.asarray(ys, float),
                              brush=brushes)
        self.contacts.setVisible(True)

    def _update_divisions(self, links):
        """Draw each division as a parent→daughter link: a line from the parent
        (open circle) to the daughter (diamond)."""
        if not links:
            for it in (self.div_link, self.div_parent, self.div_marker):
                it.setVisible(False)
            return
        lx, ly, px, py, dx, dy = [], [], [], [], [], []
        for (pcy, pcx), (dcy, dcx) in links:
            lx += [pcx, dcx, float("nan")]; ly += [pcy, dcy, float("nan")]
            px.append(pcx); py.append(pcy); dx.append(dcx); dy.append(dcy)
        self.div_link.setData(x=lx, y=ly); self.div_link.setVisible(True)
        self.div_parent.setData(px, py); self.div_parent.setVisible(True)
        self.div_marker.setData(dx, dy); self.div_marker.setVisible(True)

    # -- per-frame items -------------------------------------------------
    def _update_ids(self, centroids):
        for t in self._ids:
            self.vb.removeItem(t)
        self._ids = []
        if not centroids:
            return
        for cid, (y, x) in centroids.items():
            if not (np.isfinite(x) and np.isfinite(y)):
                continue
            t = pg.TextItem(str(cid), color=_Y, anchor=(0.5, 0.5))
            t.setPos(float(x), float(y))
            t.setZValue(70)
            self.vb.addItem(t, ignoreBounds=True)
            self._ids.append(t)

    def _update_trails(self, history, upto):
        if not history or upto is None:
            self.trails.clear()
            return
        xs: list = []
        ys: list = []
        for cen in history.values():
            seg = cen[:upto + 1]
            if np.isfinite(seg).all(axis=1).sum() < 2:
                continue
            xs += seg[:, 1].tolist() + [np.nan]
            ys += seg[:, 0].tolist() + [np.nan]
        if xs:
            self.trails.setData(x=np.array(xs), y=np.array(ys), connect="finite")
        else:
            self.trails.clear()

    def _update_selection(self, selected, centroids, bbox):
        ok = (self.show["selection"] and selected and centroids
              and selected in centroids
              and np.isfinite(centroids[selected]).all())
        if not ok:
            self.sel_rect.setVisible(False)
            self.sel_marker.setVisible(False)
            return
        y, x = centroids[selected]
        self.sel_marker.setData([float(x)], [float(y)])
        self.sel_marker.setVisible(True)
        if bbox and selected in bbox:
            x0, y0, x1, y1 = bbox[selected]
            self.sel_rect.setRect(x0, y0, x1 - x0, y1 - y0)
            self.sel_rect.setVisible(True)
        else:
            self.sel_rect.setVisible(False)

    # -- corner items ----------------------------------------------------
    def _place_corners(self):
        (x0, x1), (y0, y1) = self.vb.viewRange()
        dx, dy = (x1 - x0), (y1 - y0)
        self.info.setText(self._info_text)
        self.info.setPos(x0 + 0.02 * dx, y0 + 0.02 * dy)
        self.info.setVisible(self.show["info"] and bool(self._info_text))
        if self.show["scalebar"] and self.um_per_px:
            nice_um, length = _nice_scale(dx, self.um_per_px)
            xe = x1 - 0.04 * dx
            xs = xe - length
            yb = y1 - 0.06 * dy
            self.sbar.setLine(xs, yb, xe, yb)
            self.sbar_text.setText(f"{nice_um:g} µm")
            self.sbar_text.setPos((xs + xe) / 2.0, yb)
            self.sbar.setVisible(True)
            self.sbar_text.setVisible(True)
        else:
            self.sbar.setVisible(False)
            self.sbar_text.setVisible(False)
