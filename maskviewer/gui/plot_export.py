"""Save a pyqtgraph plot to PNG or SVG (shared by the plot panels)."""
from __future__ import annotations

from PyQt5 import QtWidgets


def save_plot(plot_widget, parent=None, default="plot.png"):
    fn, _ = QtWidgets.QFileDialog.getSaveFileName(
        parent, "Save plot", default, "PNG image (*.png);;SVG vector (*.svg)")
    if not fn:
        return
    item = (plot_widget.getPlotItem() if hasattr(plot_widget, "getPlotItem")
            else plot_widget)
    try:
        if fn.lower().endswith(".svg"):
            from pyqtgraph.exporters import SVGExporter
            SVGExporter(item).export(fn)
        else:
            from pyqtgraph.exporters import ImageExporter
            ImageExporter(item).export(fn)
    except Exception as exc:                            # surface, don't crash
        QtWidgets.QMessageBox.critical(parent, "Save failed", str(exc))
