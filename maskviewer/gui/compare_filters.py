"""Cell / recording filters for the Comparison window.

`FilterMixin` builds the filter widgets, lays them out in a non-modal **Filters…**
dialog, and applies the cell-level ones in `_filtered()` (the recording-level
min-cells filter is read by the window's `_replot`). Filters are session-only — a
Reset button clears them. Split out to keep `compare_window` small.

Filters: min frames tracked · min track-quality · min cells/recording · cell
state · distance from image edge · nearest-neighbour distance (min/max) ·
neighbour count (min/max).
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

_STATES = ["all cells", "mostly spread", "mostly rounded"]


class FilterMixin:
    def _build_filter_widgets(self):
        self._filters_dlg = None
        self.min_frames = self._fspin(1, 9999, 1, "≥",
                                      "Keep cells tracked for ≥ this many frames")
        self.min_quality = self._fdspin(0.0, 1.0, 0.05, 0.0, "≥",
                                        "Keep cells with track_quality ≥ this (0–1)")
        self.min_cells = self._fspin(0, 99999, 0, "≥",
                                     "Drop recordings with fewer than this many "
                                     "(filtered) cells — recording = unit")
        self.state_sel = QtWidgets.QComboBox()
        self.state_sel.addItems(_STATES)
        self.state_sel.setToolTip("Keep cells spending most of their time in this "
                                  "state (frac_spread / frac_rounded ≥ 0.5)")
        self.state_sel.currentIndexChanged.connect(self._replot)
        self.min_border = self._fdspin(0.0, 99999.0, 5.0, 0.0, "≥",
                                       "Keep cells whose centroid stays at least this "
                                       "far (µm) from every image edge; 0 = off")
        self.min_nn = self._fdspin(0.0, 99999.0, 5.0, 0.0, "≥",
                                   "Keep cells whose mean nearest-neighbour distance "
                                   "≥ this (µm); 0 = off — selects isolated cells")
        self.max_nn = self._fdspin(0.0, 99999.0, 5.0, 0.0, "≤",
                                   "Keep cells whose mean nearest-neighbour distance "
                                   "≤ this (µm); 0 = off — selects crowded cells")
        self.min_neighbors = self._fdspin(0.0, 99.0, 1.0, 0.0, "≥",
                                          "Keep cells with mean neighbour count ≥ "
                                          "this; 0 = off — cells in contact")
        self.max_neighbors = self._fdspin(0.0, 99.0, 1.0, 0.0, "≤",
                                          "Keep cells with mean neighbour count ≤ "
                                          "this; 0 = off")

    # -- widget factories ------------------------------------------------
    def _fspin(self, lo, hi, val, prefix, tip):
        w = QtWidgets.QSpinBox()
        w.setRange(lo, hi)
        w.setValue(val)
        w.setPrefix(prefix)
        w.setToolTip(tip)
        w.valueChanged.connect(self._replot)
        return w

    def _fdspin(self, lo, hi, step, val, prefix, tip):
        w = QtWidgets.QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setValue(val)
        w.setPrefix(prefix)
        w.setToolTip(tip)
        w.valueChanged.connect(self._replot)
        return w

    # -- dialog ----------------------------------------------------------
    def _open_filters_dialog(self):
        if self._filters_dlg is None:
            self._filters_dlg = self._make_filters_dialog()
        self._filters_dlg.show()
        self._filters_dlg.raise_()

    def _make_filters_dialog(self):
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Filters")
        dlg.setWindowFlags(dlg.windowFlags() | QtCore.Qt.Window)
        lay = QtWidgets.QVBoxLayout(dlg)
        lay.addWidget(QtWidgets.QLabel(
            "Restrict which cells / recordings enter the comparison. Applies live; "
            "session-only (Reset clears). 0 / “all cells” = off."))

        def group(title, rows):
            box = QtWidgets.QGroupBox(title)
            form = QtWidgets.QFormLayout(box)
            for label, w in rows:
                form.addRow(label, w)
            lay.addWidget(box)

        group("Track", [("Min frames tracked", self.min_frames),
                        ("Min track quality", self.min_quality),
                        ("Min cells / recording", self.min_cells)])
        group("State", [("Cell state", self.state_sel)])
        group("Crowding — nearest neighbour",
              [("Mean NN distance ≥ (µm)", self.min_nn),
               ("Mean NN distance ≤ (µm)", self.max_nn),
               ("Mean neighbours ≥", self.min_neighbors),
               ("Mean neighbours ≤", self.max_neighbors)])
        group("Field-of-view position",
              [("Distance from image edge ≥ (µm)", self.min_border)])

        btns = QtWidgets.QDialogButtonBox()
        reset = btns.addButton("Reset", QtWidgets.QDialogButtonBox.ResetRole)
        btns.addButton(QtWidgets.QDialogButtonBox.Close)
        reset.clicked.connect(self._reset_filters)
        btns.rejected.connect(dlg.close)
        lay.addWidget(btns)
        return dlg

    def _reset_filters(self):
        self.min_frames.setValue(1)
        for w in (self.min_quality, self.min_cells, self.min_border, self.min_nn,
                  self.max_nn, self.min_neighbors, self.max_neighbors):
            w.setValue(0)
        self.state_sel.setCurrentIndex(0)

    # -- application -----------------------------------------------------
    @staticmethod
    def _col(pc, base):
        for suf in ("_um", "_px", ""):
            if base + suf in pc.columns:
                return base + suf
        return None

    def _filtered(self):
        pc = self.project.regroup(self._per_cell)        # drop excluded + regroup
        if pc is None or pc.empty:
            return pc
        if self.min_frames.value() > 1 and "frames_tracked" in pc.columns:
            pc = pc[pc["frames_tracked"] >= self.min_frames.value()]
        if self.min_quality.value() > 0 and "track_quality" in pc.columns:
            pc = pc[pc["track_quality"] >= self.min_quality.value()]
        state = self.state_sel.currentText()
        if state == "mostly spread" and "frac_spread" in pc.columns:
            pc = pc[pc["frac_spread"] >= 0.5]
        elif state == "mostly rounded" and "frac_rounded" in pc.columns:
            pc = pc[pc["frac_rounded"] >= 0.5]
        bcol = self._col(pc, "min_border_dist")
        if self.min_border.value() > 0 and bcol:
            pc = pc[pc[bcol] >= self.min_border.value()]
        ncol = self._col(pc, "mean_nn_dist")
        if ncol is not None:
            if self.min_nn.value() > 0:
                pc = pc[pc[ncol] >= self.min_nn.value()]
            if self.max_nn.value() > 0:
                pc = pc[pc[ncol] <= self.max_nn.value()]
        if "mean_n_neighbors" in pc.columns:
            if self.min_neighbors.value() > 0:
                pc = pc[pc["mean_n_neighbors"] >= self.min_neighbors.value()]
            if self.max_neighbors.value() > 0:
                pc = pc[pc["mean_n_neighbors"] <= self.max_neighbors.value()]
        return pc
