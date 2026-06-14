"""Main viewer window — the analysis workbench shell.

Owns the data (discovered `Entry` list + the loaded recording/masks) and wires
the dockable panels to the central `ImageCanvas`:

  * central : ImageCanvas (base channel + label overlay + overlays layer)
  * right   : Display + Cell-Info (tabbed) and Image-Adjust docks
  * bottom  : Timeline (the frame/time bar, full width under the image)

Every panel is a detachable/resizable `QDockWidget`; the layout is persisted via
QSettings and restorable via View ▸ Reset Layout. Rendering is split into base
(channel + LUT + levels) and overlay (masks + scale bar / IDs / trails /
selection); per-channel display state is cached so contrast survives switches.
"""
from __future__ import annotations

import os

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets

from .image_view import ImageCanvas
from .panels import (TimelinePanel, DisplayPanel, ImageAdjustPanel,
                     CellInfoPanel, EdgePanel, ShapeModesPanel, PopulationPanel,
                     CellTablePanel, ComparePanel)
from ..analysis import population as _population
from .luts import DisplayState
from .menus import build_menubar
from .window_actions import WindowActionsMixin
from . import colorby
from ..analysis import label_stats, cell_metrics, shape_modes, metric_docs

_RIGHT = QtCore.Qt.RightDockWidgetArea
_BOTTOM = QtCore.Qt.BottomDockWidgetArea


class ViewerWindow(WindowActionsMixin, QtWidgets.QMainWindow):
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle("cellscope_analysis — viewer & workbench")
        self.setMinimumSize(720, 480)         # always shrinkable below screen
        scr = QtWidgets.QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else None
        if avail:
            self.resize(min(1280, avail.width() - 40),
                        min(860, avail.height() - 60))
        else:
            self.resize(1100, 760)
        self.entries = list(entries)
        self.recording = None
        self.masks = None
        self.selected = 0
        self._hover = 0
        self._display = {}              # channel -> luts.DisplayState
        self._cent_hist = None          # lazy {cid: (T,2)} for trails / NN
        self._track_len = None          # lazy {cid: int} for colour-by track
        self._mean_speed = None         # lazy {cid: float} for colour-by speed
        self._shape_model = None        # lazy VAMPIRE shape-mode model
        self._pop_df = None             # lazy population table (fixed scale + panel)
        self.divisions = []             # division events for the recording
        self._cur_lab = None
        self._cur_ncells = 0
        self._show_colorbar = True

        self.canvas = ImageCanvas()
        self.canvas.setMinimumSize(160, 160)   # don't let the view inflate the window
        self.setCentralWidget(self.canvas)
        self.setDockOptions(QtWidgets.QMainWindow.AllowNestedDocks
                            | QtWidgets.QMainWindow.AllowTabbedDocks
                            | QtWidgets.QMainWindow.AnimatedDocks)
        self.setCorner(QtCore.Qt.BottomLeftCorner, _BOTTOM)
        self.setCorner(QtCore.Qt.BottomRightCorner, _BOTTOM)

        self.display = DisplayPanel()
        self.adjust = ImageAdjustPanel()
        self.cell_info = CellInfoPanel()
        self.edge = EdgePanel()
        self.shape = ShapeModesPanel()
        self.population = PopulationPanel()
        self.cell_table = CellTablePanel()
        self.compare = ComparePanel()
        self.timeline = TimelinePanel()
        self.docks = {}
        self._add_dock("Display", self.display, _RIGHT)
        self._add_dock("Image Adjust", self.adjust, _RIGHT)
        self._add_dock("Cell Info", self.cell_info, _RIGHT)
        self._add_dock("Edge Dynamics", self.edge, _RIGHT)
        self._add_dock("Shape Modes", self.shape, _RIGHT)
        self._add_dock("Population", self.population, _RIGHT)
        self._add_dock("Cell Table", self.cell_table, _RIGHT)
        self._add_dock("Compare", self.compare, _RIGHT)
        self._add_dock("Timeline", self.timeline, _BOTTOM)
        for name in ("Cell Info", "Edge Dynamics", "Shape Modes", "Population",
                     "Cell Table", "Compare"):
            self.tabifyDockWidget(self.docks["Display"], self.docks[name])
        self.docks["Display"].raise_()
        self.resizeDocks([self.docks["Display"]], [400], QtCore.Qt.Horizontal)
        self.status = self.statusBar()

        build_menubar(self)
        self._wire()
        self._default_state = self.saveState()
        self._settings = QtCore.QSettings("cellscope_analysis", "viewer")
        self._restore_settings()
        self._fit_to_screen()                 # clamp restored geometry to the screen

        self.display.set_recordings(self.entries)
        self.compare.set_entries(self.entries)
        if self.entries:
            self._load_entry(0)
        self._start_remote()

    def _select_recording_by_label(self, label):
        for i, e in enumerate(self.entries):
            if e.label == label:
                self.display.recording.setCurrentIndex(i)
                self.docks["Display"].raise_()
                return

    def _start_remote(self):
        port = os.environ.get("MASKVIEWER_REMOTE")
        if not port:
            return
        try:
            from .remote import RemoteControl
            self._remote = RemoteControl(self, port)
            self.status.showMessage(f"Remote control on http://127.0.0.1:{port}")
        except Exception as exc:                          # don't block the GUI
            self.status.showMessage(f"Remote control failed: {exc}", 6000)

    # -- setup -----------------------------------------------------------
    def _add_dock(self, name, widget, area):
        d = QtWidgets.QDockWidget(name, self)
        d.setObjectName("dock_" + name.replace(" ", ""))
        # wrap in a scroll area so a tall panel scrolls instead of forcing the
        # whole window taller than the screen
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(widget)
        d.setWidget(scroll)
        d.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable
                      | QtWidgets.QDockWidget.DockWidgetFloatable
                      | QtWidgets.QDockWidget.DockWidgetClosable)
        self.addDockWidget(area, d)
        self.docks[name] = d
        return d

    def _wire(self):
        self.display.recordingChanged.connect(self._load_entry)
        self.display.channelChanged.connect(lambda *_: self._on_channel())
        self.display.maskOptionsChanged.connect(self._render_overlay)
        self.display.colorByChanged.connect(lambda *_: self._render_overlay())
        self.display.overlayToggled.connect(self._on_overlay_toggle)
        self.display.displayModeChanged.connect(self._on_display_mode)
        self.adjust.displayChanged.connect(self._on_display_changed)
        self.timeline.frameChanged.connect(self._on_frame)
        self.canvas.cellHovered.connect(self._on_hover)
        self.canvas.cellClicked.connect(self._on_click)
        self.cell_info.neighbor_provider = self._centroid_history
        self.cell_info.shape_mode_provider = self._shape_modes_model
        self.shape.set_provider(self._shape_modes_model)
        self.population.table_provider = self._population_table
        self.cell_table.cellSelected.connect(self.select_cell)
        self.population.cellSelected.connect(self.select_cell)
        self.compare.recordingPicked.connect(self._select_recording_by_label)
        for key, step in ((QtCore.Qt.Key_Left, -1), (QtCore.Qt.Key_Right, 1)):
            QtWidgets.QShortcut(QtGui.QKeySequence(key), self,
                                activated=lambda s=step: self.timeline.step(s))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Space), self,
                            activated=self.timeline.toggle_play)

    # -- loading ---------------------------------------------------------
    def _load_entry(self, idx):
        if not (0 <= idx < len(self.entries)):
            return
        entry = self.entries[idx]
        try:
            self.recording = entry.load_recording()
            self.masks = entry.load_masks()
        except Exception as exc:                       # surface, don't crash
            self.status.showMessage(f"Load failed: {exc}", 8000)
            self.recording = self.masks = None
            return
        self._display = {}
        self.selected = 0
        self._cent_hist = self._track_len = self._mean_speed = None
        self._shape_model = self._pop_df = None
        self.divisions = entry.load_divisions()
        labels = self.masks.labels if self.masks is not None else None
        self.cell_info.clear_cell()
        self.cell_info.divisions = self.divisions
        self.edge.clear_cell()
        self.shape.clear_model()
        self.population.set_recording(labels, self.recording.um_per_px,
                                      self.recording.time_interval_min,
                                      divisions=self.divisions)
        self.cell_table.set_recording(labels, self.recording.um_per_px,
                                      self.recording.time_interval_min,
                                      divisions=self.divisions)
        self.canvas.overlays.set_scale(self.recording.um_per_px)
        self.display.set_channels(self.recording.channel_names)
        self.cell_info.set_available(self.recording.channel_names,
                                     self.recording.um_per_px)
        self._rebuild_metrics_menu()
        self.timeline.set_time_interval(self.recording.time_interval_min)
        self.timeline.set_range(self.recording.n_frames)
        if self.masks is not None:
            self.canvas.set_label_lut(self.masks.max_label)
        self._on_channel()
        self.canvas.autorange()

    # -- rendering -------------------------------------------------------
    def _on_channel(self):
        if self.recording is None:
            return
        ch = self.display.current_channel()
        ds = self._display.get(ch)
        self.adjust.set_image_data(self.recording.frame(self.timeline.value(), ch))
        if ds is None:
            self.adjust.cmap.setCurrentText(self._default_cmap(ch))
            self.adjust.auto()                          # → _on_display_changed
        else:
            self.adjust.set_state(ds)
        self._render_base()
        self._render_overlay()

    def _on_display_mode(self):
        if self.recording is not None:
            self._render_base()

    def _on_frame(self, t):
        if self.recording is None:
            return
        ch = self.display.current_channel()
        self.adjust.set_image_data(self.recording.frame(t, ch))
        self._render_base()
        self._render_overlay()
        self.cell_info.set_frame_marker(t)
        self.edge.set_frame(t)

    def _on_display_changed(self):
        if self.recording is None:
            return
        self._display[self.display.current_channel()] = self.adjust.state()
        self._render_base()

    def _render_base(self):
        if self.recording is None:
            return
        t = self.timeline.value()
        if self.display.composite_on():
            chans = self.display.visible_channels()
            for ch in chans:
                self._ensure_channel_state(ch)
            chans = sorted(chans, key=lambda c: 0 if self._display[c].colormap
                           in ("grey", "gray") else 1)
            layers = [{"img": self.recording.frame(t, c),
                       "levels": self._display[c].levels,
                       "lut": self._display[c].lut()} for c in chans]
            self.canvas.set_base_layers(layers)
        else:
            ch = self.display.current_channel()
            ds = self.adjust.state()
            self.canvas.set_base(self.recording.frame(t, ch),
                                 levels=ds.levels, lut=ds.lut())

    def _ensure_channel_state(self, ch):
        if ch in self._display:
            return
        frame = self.recording.frame(self.timeline.value(), ch)
        finite = frame[np.isfinite(frame)]
        lo, hi = np.percentile(finite if finite.size else [0, 1], (1, 99))
        if hi <= lo:
            hi = lo + 1.0
        self._display[ch] = DisplayState(levels=(float(lo), float(hi)),
                                         colormap=self._default_cmap(ch))

    def _default_cmap(self, ch):
        name = (self.recording.channel_names[ch] or "").lower()
        if any(k in name for k in ("cy5", "sir", "actin", "rfp", "555", "594", "647")):
            return "magenta"
        if any(k in name for k in ("gfp", "488", "fitc", "yfp")):
            return "green"
        if any(k in name for k in ("dapi", "405", "hoechst")):
            return "blue"
        if any(k in name for k in ("dic", "bright", "phase", "trans")):
            return "grey"
        return ["grey", "magenta", "green", "cyan", "yellow", "red"][ch % 6]

    def _render_overlay(self):
        if self.recording is None:
            return
        t = self.timeline.value()
        lab = self.masks.frame(t) if self.masks is not None else None
        self._cur_lab = lab
        self._cur_ncells = int((np.unique(lab) > 0).sum()) if lab is not None else 0
        masks_on = self.display.show_masks.isChecked()
        lut, legend = colorby.overlay_lut(self, lab)
        self.canvas.set_overlay(lab, opacity=self.display.opacity_value,
                                outline=self.display.outline.isChecked(),
                                visible=masks_on, lut=lut)
        self.canvas.set_colorbar(legend if (self._show_colorbar and masks_on)
                                 else None)
        self._update_overlays(t, lab)
        self._update_status()

    def _centroid_history(self):
        """All cells' centroid tracks (lazy + cached) — for trails + nearest
        neighbour metrics."""
        if self._cent_hist is None and self.masks is not None:
            self._cent_hist = cell_metrics.centroid_history(self.masks.labels)
        return self._cent_hist

    def _population_table(self):
        """All-cells per-frame table (lazy + cached) — fixed colour scale +
        the Population panel."""
        if self._pop_df is None and self.masks is not None:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                self._pop_df = _population.population_table(
                    self.masks.labels, self.recording.um_per_px,
                    self.recording.time_interval_min)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
        return self._pop_df

    def _shape_modes_model(self):
        """VAMPIRE shape-mode model for the recording (lazy + cached)."""
        if self._shape_model is None and self.masks is not None:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                self._shape_model = shape_modes.fit_shape_modes(self.masks.labels)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
        return self._shape_model

    def _rebuild_metrics_menu(self):
        """Populate Config ▸ Cell plot metrics with a checkable item per
        available per-frame metric (toggling recomputes the cell plot)."""
        menu = getattr(self, "metrics_menu", None)
        if menu is None:
            return
        menu.clear()
        um = self.recording.um_per_px if self.recording else None
        for key in self.cell_info.available:
            act = QtWidgets.QAction(cell_metrics.metric_label(key, um), self)
            act.setCheckable(True)
            act.setChecked(self.cell_info.is_enabled(key))
            act.setToolTip(metric_docs.tooltip(key))
            act.toggled.connect(lambda on, k=key: self.cell_info.set_metric_enabled(k, on))
            menu.addAction(act)
        if not self.cell_info.available:
            empty = QtWidgets.QAction("(load a recording)", self)
            empty.setEnabled(False)
            menu.addAction(empty)

    def _ensure_track_len(self):
        if self._track_len is None and self.masks is not None:
            counts: dict = {}
            for t in range(self.masks.n_frames):
                for i in np.unique(self.masks.frame(t)):
                    if i > 0:
                        counts[int(i)] = counts.get(int(i), 0) + 1
            self._track_len = counts

    def _update_overlays(self, t, lab):
        ov = self.canvas.overlays.show
        centroids = bbox = history = None
        if lab is not None and (ov["ids"] or (ov["selection"] and self.selected)):
            props = cell_metrics.regionprops_frame(lab)
            centroids = {c: (r["centroid_y"], r["centroid_x"])
                         for c, r in props.items()}
            bbox = {c: (r["bbox_x0"], r["bbox_y0"], r["bbox_x1"], r["bbox_y1"])
                    for c, r in props.items()}
        if ov["trails"] and self.masks is not None:
            history = self._centroid_history()
        div_pts = None
        if self.canvas.overlays.show["divisions"] and self.divisions:
            div_pts = []
            for d in self.divisions:
                if d["frame"] == t:
                    for key in ("parent_centroid", "daughter_centroid"):
                        c = d.get(key)
                        if c:
                            div_pts.append((c[0], c[1]))
        self.canvas.overlays.update_overlay(
            info_text=self._info_text(t), centroids=centroids, history=history,
            frame=t, selected=self.selected, bbox=bbox, division_pts=div_pts)

    def _info_text(self, t):
        r = self.recording
        bits = [f"frame {t + 1}/{r.n_frames}"]
        if r.time_interval_min:
            bits.append(f"t={t * r.time_interval_min:.0f} min")
        return "    ".join(bits)

    # -- interaction -----------------------------------------------------
    def _on_overlay_toggle(self, key, on):
        if key == "colorbar":
            self._show_colorbar = on
        else:
            self.canvas.overlays.set_show(key, on)
        self._render_overlay()

    def _on_hover(self, cid):
        self._hover = cid
        self._update_status()

    def _on_click(self, cid):
        self.select_cell(cid)

    def select_cell(self, cid):
        """Central selection: view click, plot/table click all route here so
        every panel stays in sync."""
        self.selected = cid
        if cid and self.masks is not None:
            self.cell_info.set_cell(cid, self.masks.labels,
                                    self.recording.um_per_px,
                                    self.recording.time_interval_min,
                                    recording=self.recording)
            self.cell_info.set_frame_marker(self.timeline.value())
            self.edge.set_cell(cid, self.masks.labels, self.recording.um_per_px,
                               self.recording.time_interval_min)
            self.edge.set_frame(self.timeline.value())
            self.cell_table.select_in_table(cid)
            self.docks["Cell Info"].raise_()
        else:
            self.cell_info.clear_cell()
            self.edge.clear_cell()
        self._render_overlay()

    def _update_status(self):
        if self.recording is None:
            return
        r = self.recording
        t = self.timeline.value()
        bits = [f"frame {t + 1}/{r.n_frames}"]
        if r.time_interval_min:
            bits.append(f"t={t * r.time_interval_min:.0f} min")
        if r.um_per_px:
            bits.append(f"{r.um_per_px:.4f} µm/px")
        if self._cur_lab is not None:
            bits.append(f"{self._cur_ncells} cells")
        if self.selected:
            bits.append(f"selected cell {self.selected}")
        elif self._hover:
            bits.append(f"cursor → cell {self._hover}")
        self.status.showMessage("   |   ".join(bits))

    # -- settings --------------------------------------------------------
    def _restore_settings(self):
        geo = self._settings.value("geometry")
        st = self._settings.value("windowState")
        if geo is not None:
            self.restoreGeometry(geo)
        if st is not None:
            self.restoreState(st)

    def _fit_to_screen(self):
        """Clamp the window to the available screen + keep it on-screen, so a
        saved/oversized geometry can never escape the display or block resizing."""
        scr = (self.screen() if hasattr(self, "screen") else None) \
            or QtWidgets.QApplication.primaryScreen()
        if scr is None:
            return
        a = scr.availableGeometry()
        w, h = min(self.width(), a.width()), min(self.height(), a.height())
        if (w, h) != (self.width(), self.height()):
            self.resize(w, h)
        fg = self.frameGeometry()
        if not a.contains(fg):
            fg.moveCenter(a.center())
            self.move(fg.topLeft())

    def closeEvent(self, ev):
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())
        super().closeEvent(ev)
