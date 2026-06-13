"""GUI subpackage (PyQt5 + pyqtgraph).

  image_view.py     ImageCanvas — base channel + label overlay, hover→cell id
  controls.py       ControlPanel — recording / channel / frame / overlay
  viewer_window.py  ViewerWindow — main window, owns data, wires the above
"""
from .viewer_window import ViewerWindow

__all__ = ["ViewerWindow"]
