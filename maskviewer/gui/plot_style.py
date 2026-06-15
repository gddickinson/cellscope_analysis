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
    trendline: bool = False      # scatter: least-squares line; categorical: connect
                                 # the per-group centres across conditions
    hist_bins: int = 30
    hist_density: bool = True     # density vs raw cell counts
    hist_bars: bool = False       # filled bars vs outlined step curve
    msd_bin_min: int = 0          # ensemble-MSD lag-τ bin width (min); 0 = raw lags
    msd_log: bool = True          # ensemble MSD on log-log axes (else linear)
    msd_points: bool = False      # draw markers + error bars at each MSD lag
    background: str = "default"   # plot background: default / black / white / grey
    legend: bool = False          # show a per-group legend on the graphs
    fit_kind: str = "none"        # scatter fit: none / linear / power / exponential / log
    fit_all: bool = False         # fit a single line over all points
    fit_groups: bool = False      # fit one line per group
    fit_ci: bool = False          # ± std-error band around each fit

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
              ("hist_bins", "Histogram bins", 5, 120),
              ("msd_bin_min", "Ensemble-MSD τ bin (min, 0=off)", 0, 240)]
    _COMBOS = [("background", "Background", ["default", "black", "white", "grey"]),
               ("fit_kind", "Scatter fit", ["none", "linear", "power",
                                            "exponential", "log"])]
    _CHECKS = [("grid", "Grid"),
               ("legend", "Show legend"),
               ("log_x", "Log X (scatter)"),
               ("log_y", "Log Y (distributions / scatter)"),
               ("msd_log", "Ensemble-MSD log-log axes (else linear)"),
               ("msd_points", "Ensemble-MSD points + error bars"),
               ("show_points", "Show individual points (box / bars)"),
               ("trendline", "Trendline (connect group means)"),
               ("fit_all", "Scatter fit over all points"),
               ("fit_groups", "Scatter fit per group"),
               ("fit_ci", "Scatter fit ± std-error band"),
               ("hist_density", "Histogram density (else cell counts)"),
               ("hist_bars", "Histogram filled bars (else step curve)")]

    def __init__(self, style, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plot style")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.resize(400, 640)
        self.style = style
        self._hidden = None
        self._widgets = {}
        outer = QtWidgets.QVBoxLayout(self)
        outer.addWidget(QtWidgets.QLabel(
            "Applies to the Comparison-window graphs (shift-right-click a plot "
            "reopens this). Group colours are set in Groups…."))
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        body = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        form = QtWidgets.QFormLayout()
        for attr, label, lo, hi in self._SPINS:
            w = QtWidgets.QSpinBox()
            w.setRange(lo, hi)
            w.setValue(int(getattr(style, attr)))
            w.valueChanged.connect(lambda v, a=attr: self._set(a, int(v)))
            self._widgets[attr] = w
            form.addRow(label, w)
        for attr, label, items in self._COMBOS:
            w = QtWidgets.QComboBox()
            w.addItems(items)
            w.setCurrentText(str(getattr(style, attr)))
            w.currentTextChanged.connect(lambda v, a=attr: self._set(a, v))
            self._widgets[attr] = w
            form.addRow(label, w)
        lay.addLayout(form)
        for attr, label in self._CHECKS:
            w = QtWidgets.QCheckBox(label)
            w.setChecked(bool(getattr(style, attr)))
            w.toggled.connect(lambda v, a=attr: self._set(a, bool(v)))
            self._widgets[attr] = w
            lay.addWidget(w)
        self._groups_box = QtWidgets.QGroupBox("Show groups")
        QtWidgets.QVBoxLayout(self._groups_box)
        self._groups_box.setVisible(False)
        lay.addWidget(self._groups_box)
        lay.addStretch(1)

        btns = QtWidgets.QDialogButtonBox()
        reset = btns.addButton("Reset", QtWidgets.QDialogButtonBox.ResetRole)
        btns.addButton(QtWidgets.QDialogButtonBox.Close)
        reset.clicked.connect(self._reset)
        btns.rejected.connect(self.close)
        outer.addWidget(btns)

    def set_groups(self, conditions, hidden, design=None):
        """(Re)build the per-group visibility checkboxes; `hidden` is the set the
        dialog mutates (a group in it is hidden from the graphs)."""
        self._hidden = hidden
        box_lay = self._groups_box.layout()
        while box_lay.count():
            w = box_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        for cond in conditions:
            cb = QtWidgets.QCheckBox(cond)
            cb.setChecked(cond not in hidden)
            if design is not None:
                cb.setStyleSheet(f"color: {design.color(cond)};")
            cb.toggled.connect(lambda on, c=cond: self._toggle_group(c, on))
            box_lay.addWidget(cb)
        self._groups_box.setVisible(bool(conditions))

    def _toggle_group(self, cond, on):
        if self._hidden is None:
            return
        (self._hidden.discard if on else self._hidden.add)(cond)
        self.changed.emit()

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
            if isinstance(w, QtWidgets.QSpinBox):
                w.setValue(v)
            elif isinstance(w, QtWidgets.QComboBox):
                w.setCurrentText(str(v))
            else:
                w.setChecked(v)
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
        groups = getattr(self, "_style_groups", None)
        if groups is not None:
            conds, hidden, design = groups()
            self._style_dialog.set_groups(conds, hidden, design)
        self._style_dialog.show()
        self._style_dialog.raise_()

    def _on_style_changed(self):
        s = getattr(self, "_settings", None)
        if s is not None:
            s.setValue("plot_style", self.style.to_dict())
        self._replot()
