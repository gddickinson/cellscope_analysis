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
    f.addSeparator()
    f.addAction(_act(win, "Open Project &Folder…", win.open_data_root_dialog,
                     tip="Open a folder of recordings as a project"))
    f.addAction(_act(win, "Open &Project File…", win.open_project_file))
    f.addAction(_act(win, "&Save Project As…", win.save_project_as))
    win.recent_menu = f.addMenu("&Recent Projects")
    win.recent_menu.setToolTipsVisible(True)
    win._rebuild_recent_menu()
    f.addSeparator()
    f.addAction(_act(win, "&Export CSV…", win.export_csv, "Ctrl+E",
                     "Export tracks / masks / cell properties as CSV"))
    f.addAction(_act(win, "Save &View Image…", win.save_screenshot, "Ctrl+Shift+P",
                     "Save the image view (canvas) as PNG"))
    f.addAction(_act(win, "Save &Window Screenshot…", win.save_window_screenshot,
                     "Ctrl+Shift+W", "Save the whole window as PNG"))
    f.addSeparator()
    f.addAction(_act(win, "&Quit", win.close, "Ctrl+Q"))

    v = mb.addMenu("&View")
    v.addAction(_act(win, "Zoom &In", lambda: win.canvas.zoom(0.8), "Ctrl+="))
    v.addAction(_act(win, "Zoom &Out", lambda: win.canvas.zoom(1.25), "Ctrl+-"))
    v.addAction(_act(win, "Zoom to &Fit", win.canvas.autorange, "Ctrl+0"))
    v.addAction(_act(win, "Zoom to &Cell", win.zoom_to_cell, "Z",
                     "Frame the view on the selected cell"))

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
    an.addAction(_act(win, "&Comparison window…", win.open_compare_window,
                     "Ctrl+Shift+C", "Cross-recording / treatment comparison"))
    an.addAction(_act(win, "Channel &Alignment && FOV…", win.open_prep_dialog,
                     tip="Align a fluorescence channel to a reference + define the "
                         "field of view (non-destructive pre-analysis)"))
    an.addAction(_act(win, "&Export CSV…", win.export_csv, "Ctrl+E"))

    cfg = mb.addMenu("&Config")
    win.metrics_menu = cfg.addMenu("Cell plot &metrics")
    win.metrics_menu.setToolTipsVisible(True)
    win._rebuild_metrics_menu()
    cfg.addSeparator()
    cfg.addAction(_act(win, "Pixel size & &time scale…", win.open_scale_dialog,
                       tip="Manually set µm/px + min/frame for ALL recordings "
                           "(use when file metadata is missing or wrong)"))
    cfg.addAction(_act(win, "Comparison &plot options…", win.open_compare_plot_options,
                       tip="Fonts, sizes, axes, bins, trendlines… for the "
                           "Comparison-window graphs"))

    w = mb.addMenu("&Window")
    for dock in win.docks.values():
        w.addAction(dock.toggleViewAction())
    w.addSeparator()
    w.addAction(_act(win, "Show &All Panels", win.show_all_panels))
    w.addAction(_act(win, "&Save Current Layout", win.save_layout_default,
                     tip="Make the current layout the one Reset Layout restores"))
    w.addAction(_act(win, "&Reset Layout", win.reset_layout))

    h = mb.addMenu("&Help")
    h.addAction(_act(win, "&Data && Provenance", lambda: win.open_doc("docs/DATA.md")))
    h.addAction(_act(win, "&Findings", lambda: win.open_doc("docs/FINDINGS_followup.md")))
    h.addAction(_act(win, "&Interface Map", lambda: win.open_doc("INTERFACE.md")))
    h.addSeparator()
    h.addAction(_act(win, "&Metrics Reference…", win.show_metrics_help,
                     tip="What each metric means and how it is calculated"))
    h.addAction(_act(win, "&Keyboard Shortcuts", win.show_shortcuts))
    h.addAction(_act(win, "&About", win.show_about))
