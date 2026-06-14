"""Dockable GUI panels (each a self-contained QWidget that emits signals).

  timeline.py      TimelinePanel    — frame slider + play/pause/fps/loop (bottom)
  display_panel.py DisplayPanel     — recording/channel/composite/colour-by/overlays
  image_adjust.py  ImageAdjustPanel — histogram + levels/brightness/contrast/
                                      gamma/LUT/invert (per channel)
  cell_info.py     CellInfoPanel    — selected-cell metrics + per-frame plots + MSD
  edge_panel.py    EdgePanel        — membrane protrusion/retraction kymograph
"""
from .timeline import TimelinePanel
from .display_panel import DisplayPanel
from .image_adjust import ImageAdjustPanel
from .cell_info import CellInfoPanel
from .edge_panel import EdgePanel

__all__ = ["TimelinePanel", "DisplayPanel", "ImageAdjustPanel", "CellInfoPanel",
           "EdgePanel"]
