"""Per-graph plot styling for the Comparison window.

`PlotStyle` is the (persisted) record of render options every comparison plot
honours — font size, marker/line size, fill opacity, grid, log axes, histogram
bins/density/bars, etc. `PlotStyleDialog` is a small non-modal editor for it, and
`PlotStyleMixin` lets a window open that editor from a toolbar button **or**
shift-right-click on any plot, persisting to QSettings and replotting live.

Per-group colours live in the Groups & Comparisons editor (the `Design`), not here.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from PyQt5 import QtCore, QtWidgets


@dataclass
class PlotStyle:
    font_size: int = 10          # axis labels / ticks / title (pt)
    point_size: int = 11         # scatter / strip / recording-mean markers
    line_width: int = 2          # box outlines, mean lines, MSD/hist curves
    fill_alpha: int = 60         # MSD band + histogram fill (0–255)
    grid: bool = False
    log_x: bool = False          # scatter X
    log_y: bool = False          # distributions / scatter Y (MSD is always log)
    show_points: bool = True     # individual recording points on box / bars
    scatter_fit: bool = False    # least-squares line on the scatter plot
    hist_bins: int = 30
    hist_density: bool = True     # density vs raw cell counts
    hist_bars: bool = False       # filled bars vs outlined step curve

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_settings(cls, settings):
        d = settings.value("plot_style") if settings is not None else None
        s = cls()
        if isinstance(d, dict):
            for k, v in d.items():
                if hasattr(s, k):
                    try:
                        setattr(s, k, type(getattr(s, k))(v))
                    except (TypeError, ValueError):
                        pass
        return s


class PlotStyleDialog(QtWidgets.QDialog):
    """Live editor for a `PlotStyle` (edits it in place, emits `changed`)."""
    changed = QtCore.pyqtSignal()

    _SPINS = [("font_size", "Font size (pt)", 6, 28),
              ("point_size", "Marker size", 2, 30),
              ("line_width", "Line width", 1, 10),
              ("fill_alpha", "Fill opacity (0–255)", 0, 255),
              ("hist_bins", "Histogram bins", 5, 120)]
    _CHECKS = [("grid", "Grid"),
               ("log_x", "Log X (scatter)"),
               ("log_y", "Log Y (distributions / scatter)"),
               ("show_points", "Show individual points (box / bars)"),
               ("scatter_fit", "Least-squares line (scatter)"),
               ("hist_density", "Histogram density (else cell counts)"),
               ("hist_bars", "Histogram filled bars (else step curve)")]

    def __init__(self, style, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plot style")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.style = style
        self._widgets = {}
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel(
            "Applies to the Comparison-window graphs. Group colours are set in "
            "Groups…  ·  shift-right-click a plot reopens this."))

        form = QtWidgets.QFormLayout()
        for attr, label, lo, hi in self._SPINS:
            w = QtWidgets.QSpinBox()
            w.setRange(lo, hi)
            w.setValue(int(getattr(style, attr)))
            w.valueChanged.connect(lambda v, a=attr: self._set(a, int(v)))
            self._widgets[attr] = w
            form.addRow(label, w)
        lay.addLayout(form)
        for attr, label in self._CHECKS:
            w = QtWidgets.QCheckBox(label)
            w.setChecked(bool(getattr(style, attr)))
            w.toggled.connect(lambda v, a=attr: self._set(a, bool(v)))
            self._widgets[attr] = w
            lay.addWidget(w)

        btns = QtWidgets.QDialogButtonBox()
        reset = btns.addButton("Reset", QtWidgets.QDialogButtonBox.ResetRole)
        btns.addButton(QtWidgets.QDialogButtonBox.Close)
        reset.clicked.connect(self._reset)
        btns.rejected.connect(self.close)
        lay.addWidget(btns)

    def _set(self, attr, value):
        setattr(self.style, attr, value)
        self.changed.emit()

    def _reset(self):
        for k, v in PlotStyle().to_dict().items():
            setattr(self.style, k, v)
            w = self._widgets.get(k)
            if w is None:
                continue
            w.blockSignals(True)
            (w.setValue if isinstance(w, QtWidgets.QSpinBox) else w.setChecked)(v)
            w.blockSignals(False)
        self.changed.emit()


class PlotStyleMixin:
    """Adds a shared PlotStyle editor (toolbar button + shift-right-click)."""

    def _install_style_filters(self, plots):
        self._style_plots = list(plots)
        for p in plots:
            p.viewport().installEventFilter(self)

    def eventFilter(self, obj, ev):
        if (ev.type() == QtCore.QEvent.MouseButtonPress
                and ev.button() == QtCore.Qt.RightButton
                and (ev.modifiers() & QtCore.Qt.ShiftModifier)):
            self._open_style_dialog()
            return True
        return super().eventFilter(obj, ev)

    def _open_style_dialog(self):
        if getattr(self, "_style_dialog", None) is None:
            self._style_dialog = PlotStyleDialog(self.style, self)
            self._style_dialog.changed.connect(self._on_style_changed)
        self._style_dialog.show()
        self._style_dialog.raise_()

    def _on_style_changed(self):
        s = getattr(self, "_settings", None)
        if s is not None:
            s.setValue("plot_style", self.style.to_dict())
        self._replot()
