"""Menu bar construction (kept out of viewer_window so it stays small).

`build_menubar(win)` builds File / View / Image / Analysis / Window / Help and
wires each action to a `win` method or directly to a panel widget (the panel
checkbox/combo stays the single source of truth — menu items just trigger it).
"""
from __future__ import annotations

from PyQt5 import QtWidgets

from .luts import PRESETS


def _act(parent, text, slot, shortcut=None, tip=None):
    a = QtWidgets.QAction(text, parent)
    if shortcut:
        a.setShortcut(shortcut)
    if tip:
        a.setStatusTip(tip)
    a.triggered.connect(lambda *_: slot())
    return a


def build_menubar(win):
    mb = win.menuBar()

    f = mb.addMenu("&File")
    f.addAction(_act(win, "Open &Recording…", win.open_recording_dialog, "Ctrl+O"))
    f.addAction(_act(win, "Open Data &Folder…", win.open_data_root_dialog))
    f.addSeparator()
    f.addAction(_act(win, "&Export CSV…", win.export_csv, "Ctrl+E",
                     "Export tracks / masks / cell properties as CSV"))
    f.addAction(_act(win, "Save &Screenshot…", win.save_screenshot, "Ctrl+Shift+P"))
    f.addSeparator()
    f.addAction(_act(win, "&Quit", win.close, "Ctrl+Q"))

    v = mb.addMenu("&View")
    v.addAction(_act(win, "Zoom &In", lambda: win.canvas.zoom(0.8), "Ctrl+="))
    v.addAction(_act(win, "Zoom &Out", lambda: win.canvas.zoom(1.25), "Ctrl+-"))
    v.addAction(_act(win, "Zoom to &Fit", win.canvas.autorange, "Ctrl+0"))

    im = mb.addMenu("&Image")
    im.addAction(_act(win, "&Auto Contrast", win.adjust.auto, "Ctrl+Shift+A"))
    im.addAction(_act(win, "&Reset Display", win.adjust.reset))
    im.addAction(_act(win, "&Invert LUT", win.adjust.invert.toggle))
    cmap = im.addMenu("&Colormap")
    for name in PRESETS:
        cmap.addAction(_act(win, name,
                            lambda n=name: win.adjust.cmap.setCurrentText(n)))
    im.addSeparator()
    im.addAction(_act(win, "Show &Masks", win.display.show_masks.toggle))
    im.addAction(_act(win, "&Outlines Only", win.display.outline.toggle))

    an = mb.addMenu("&Analysis")
    an.addAction(_act(win, "&Export CSV…", win.export_csv, "Ctrl+E"))
    soon = QtWidgets.QAction("Comparison plots… (coming soon)", win)
    soon.setEnabled(False)
    an.addAction(soon)

    w = mb.addMenu("&Window")
    for dock in win.docks.values():
        w.addAction(dock.toggleViewAction())
    w.addSeparator()
    w.addAction(_act(win, "&Reset Layout", win.reset_layout))

    h = mb.addMenu("&Help")
    h.addAction(_act(win, "&Data && Provenance", lambda: win.open_doc("docs/DATA.md")))
    h.addAction(_act(win, "&Findings", lambda: win.open_doc("docs/FINDINGS_followup.md")))
    h.addAction(_act(win, "&Interface Map", lambda: win.open_doc("INTERFACE.md")))
    h.addSeparator()
    h.addAction(_act(win, "&Keyboard Shortcuts", win.show_shortcuts))
    h.addAction(_act(win, "&About", win.show_about))
