"""GUI subpackage (PyQt5 + pyqtgraph).

  image_view.py     ImageCanvas — base channel + label overlay + overlays layer
  overlays.py       Overlays — scale bar / info / IDs / trails / selection
  luts.py           build_lut + DisplayState — base-channel colour/contrast
  panels/           TimelinePanel, DisplayPanel, ImageAdjustPanel, CellInfoPanel
  menus.py          build_menubar — File/View/Image/Analysis/Window/Help
  export_dialog.py  CSVExportDialog — tracks / masks / cell-property CSVs
  viewer_window.py  ViewerWindow — main window, owns data, wires the docks
"""
from .viewer_window import ViewerWindow

__all__ = ["ViewerWindow"]
