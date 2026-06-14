"""Groups & Comparisons editor — configure the comparison design live.

A non-modal dialog over a `Project`: include/exclude recordings, reassign each
to a **group**, define **comparisons** (member groups + a control), set the
vehicle/batch pair, and recolour groups. It edits the project's `Design` plus
per-recording overrides/exclusions *in place* and emits ``designChanged`` so the
Comparison window replots **without recomputing** — grouping is a remap of the
already-computed per-cell table, not an expensive recompute.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtGui, QtWidgets

from .. import project as projmod

_NONE = "(none)"


class DesignEditor(QtWidgets.QDialog):
    designChanged = QtCore.pyqtSignal()

    def __init__(self, project, per_cell=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Groups & Comparisons")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)
        self.resize(740, 660)
        self.project = project
        self._counts = {}
        self._updating = False
        self._row_combos = {}
        self._row_include = {}
        self._entry_by_label = {}
        self._build_ui()
        self.set_data(per_cell)

    # ---- construction --------------------------------------------------
    def _build_ui(self):
        lay = QtWidgets.QVBoxLayout(self)
        intro = QtWidgets.QLabel(
            "Recording = experimental unit. Assign recordings to groups, pick a "
            "control per comparison, and include/exclude — changes apply instantly "
            "(no recompute). Save the project to keep them.")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        split.addWidget(self._build_recordings())
        split.addWidget(self._build_comparisons())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        lay.addWidget(split, 1)

        btns = QtWidgets.QDialogButtonBox()
        auto = btns.addButton("Auto-detect from names",
                              QtWidgets.QDialogButtonBox.ActionRole)
        reset = btns.addButton("Reset all", QtWidgets.QDialogButtonBox.ResetRole)
        btns.addButton(QtWidgets.QDialogButtonBox.Close)
        auto.setToolTip("Rebuild the comparisons from the current group names")
        reset.setToolTip("Clear overrides + exclusions and re-detect the design")
        auto.clicked.connect(self._auto_detect)
        reset.clicked.connect(self._reset)
        btns.rejected.connect(self.close)
        lay.addWidget(btns)

    def _build_recordings(self):
        box = QtWidgets.QGroupBox("Recordings → groups")
        v = QtWidgets.QVBoxLayout(box)
        self.rec_table = QtWidgets.QTableWidget(0, 4)
        self.rec_table.setHorizontalHeaderLabels(["Use", "Recording", "Group", "Cells"])
        self.rec_table.verticalHeader().setVisible(False)
        self.rec_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        v.addWidget(self.rec_table, 1)

        row = QtWidgets.QHBoxLayout()
        inc = QtWidgets.QPushButton("Include selected")
        exc = QtWidgets.QPushButton("Exclude selected")
        inc.clicked.connect(lambda: self._bulk_include(True))
        exc.clicked.connect(lambda: self._bulk_include(False))
        self.bulk_group = QtWidgets.QComboBox()
        self.bulk_group.setEditable(True)
        self.bulk_group.setMinimumWidth(120)
        setg = QtWidgets.QPushButton("Set group of selected")
        setg.clicked.connect(self._bulk_set_group)
        row.addWidget(inc)
        row.addWidget(exc)
        row.addStretch(1)
        row.addWidget(self.bulk_group)
        row.addWidget(setg)
        v.addLayout(row)
        return box

    def _build_comparisons(self):
        box = QtWidgets.QGroupBox("Comparisons (each = groups vs a control)")
        v = QtWidgets.QVBoxLayout(box)
        self.cmp_host = QtWidgets.QWidget()
        self.cmp_lay = QtWidgets.QVBoxLayout(self.cmp_host)
        self.cmp_lay.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.cmp_host)
        v.addWidget(scroll, 1)

        vr = QtWidgets.QHBoxLayout()
        vr.addWidget(QtWidgets.QLabel("Vehicle / batch pair:"))
        self.veh_a = QtWidgets.QComboBox()
        self.veh_b = QtWidgets.QComboBox()
        self.veh_a.currentIndexChanged.connect(self._vehicle_changed)
        self.veh_b.currentIndexChanged.connect(self._vehicle_changed)
        vr.addWidget(self.veh_a)
        vr.addWidget(QtWidgets.QLabel("vs"))
        vr.addWidget(self.veh_b)
        vr.addStretch(1)
        add = QtWidgets.QPushButton("+ Add comparison")
        add.clicked.connect(self._add_comparison)
        vr.addWidget(add)
        v.addLayout(vr)
        return box

    # ---- data / refresh ------------------------------------------------
    def set_data(self, per_cell):
        self._counts = {}
        if per_cell is not None and not getattr(per_cell, "empty", True):
            try:
                self._counts = per_cell.groupby("recording").size().to_dict()
            except Exception:
                self._counts = {}
        self._refresh()

    def set_project(self, project, per_cell=None):
        self.project = project
        self.set_data(per_cell)

    def _refresh(self):
        self._updating = True
        entries = self.project.entries
        self._entry_by_label = {e.label: e for e in entries}
        self._row_combos, self._row_include = {}, {}
        groups = self.project.all_groups
        self.rec_table.setRowCount(len(entries))
        for i, e in enumerate(entries):
            lbl = e.label
            cell, cb = self._checkbox_cell(
                lbl not in self.project.excluded,
                lambda on, l=lbl: self._on_include(l, on))
            self.rec_table.setCellWidget(i, 0, cell)
            self._row_include[lbl] = cb
            self.rec_table.setItem(i, 1, self._ro_item(lbl))
            combo = QtWidgets.QComboBox()
            combo.setEditable(True)
            combo.addItems(groups)
            combo.setCurrentText(self.project.group_of(e))
            combo.currentTextChanged.connect(lambda t, l=lbl: self._on_group(l, t))
            self.rec_table.setCellWidget(i, 2, combo)
            self._row_combos[lbl] = combo
            n = self._counts.get(lbl)
            self.rec_table.setItem(i, 3, self._ro_item("" if n is None else str(n)))
        self.rec_table.resizeColumnsToContents()
        self.rec_table.setColumnWidth(0, 40)
        self._sync_group_lists()
        self._rebuild_comparisons()
        self._sync_vehicle()
        self._updating = False

    def _refresh_groups(self):
        """Deferred: refresh group lists + comparison cards after a group edit."""
        self._updating = True
        self._sync_group_lists()
        self._rebuild_comparisons()
        self._sync_vehicle()
        self._updating = False

    def _sync_group_lists(self):
        groups = self.project.all_groups
        cur = self.bulk_group.currentText()
        self.bulk_group.blockSignals(True)
        self.bulk_group.clear()
        self.bulk_group.addItems(groups)
        self.bulk_group.setCurrentText(cur)
        self.bulk_group.blockSignals(False)
        for combo in self._row_combos.values():
            c = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(groups)
            combo.setCurrentText(c)
            combo.blockSignals(False)

    def _sync_vehicle(self):
        groups = [_NONE] + self.project.all_groups
        veh = self.project.design.vehicle or []
        for combo, val in ((self.veh_a, veh[0] if len(veh) > 0 else _NONE),
                           (self.veh_b, veh[1] if len(veh) > 1 else _NONE)):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(groups)
            combo.setCurrentText(val if val in groups else _NONE)
            combo.blockSignals(False)

    # ---- comparison cards ----------------------------------------------
    def _rebuild_comparisons(self):
        while self.cmp_lay.count():
            w = self.cmp_lay.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for arm, spec in self.project.design.arms.items():
            self.cmp_lay.addWidget(self._comparison_card(arm, spec))
        self.cmp_lay.addStretch(1)

    def _comparison_card(self, arm, spec):
        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.StyledPanel)
        cv = QtWidgets.QVBoxLayout(card)
        top = QtWidgets.QHBoxLayout()
        name = QtWidgets.QLineEdit(arm)
        name.editingFinished.connect(lambda a=arm, w=name: self._rename(a, w.text()))
        top.addWidget(QtWidgets.QLabel("Name:"))
        top.addWidget(name, 1)
        top.addWidget(QtWidgets.QLabel("Control:"))
        ctrl = QtWidgets.QComboBox()
        ctrl.addItems(spec.get("conditions", []))
        if spec.get("control") in spec.get("conditions", []):
            ctrl.setCurrentText(spec["control"])
        ctrl.currentTextChanged.connect(lambda g, a=arm: self._set_control(a, g))
        top.addWidget(ctrl)
        rm = QtWidgets.QToolButton()
        rm.setText("✕")
        rm.setToolTip("Remove this comparison")
        rm.clicked.connect(lambda _=0, a=arm: self._remove_comparison(a))
        top.addWidget(rm)
        cv.addLayout(top)

        grid = QtWidgets.QGridLayout()
        for idx, g in enumerate(self.project.all_groups):
            cb = QtWidgets.QCheckBox(g)
            cb.setChecked(g in spec.get("conditions", []))
            cb.setStyleSheet(f"color: {self.project.design.color(g)};")
            cb.toggled.connect(lambda on, a=arm, gg=g: self._set_member(a, gg, on))
            grid.addWidget(cb, idx // 4, idx % 4)
        cv.addLayout(grid)
        return card

    # ---- recording edits -----------------------------------------------
    def _on_include(self, label, on):
        if self._updating:
            return
        (self.project.excluded.discard if on else self.project.excluded.add)(label)
        self._emit()

    def _on_group(self, label, text):
        if self._updating:
            return
        self._set_override(label, text)
        QtCore.QTimer.singleShot(0, self._refresh_groups)
        self._emit()

    def _set_override(self, label, text):
        g = (text or "").strip()
        e = self._entry_by_label.get(label)
        orig = (e.condition or "?") if e else "?"
        if not g or g == orig:
            self.project.overrides.pop(label, None)
        else:
            self.project.overrides[label] = g

    def _bulk_include(self, on):
        for lbl in self._selected_labels():
            cb = self._row_include.get(lbl)
            if cb:
                cb.blockSignals(True)
                cb.setChecked(on)
                cb.blockSignals(False)
            (self.project.excluded.discard if on else self.project.excluded.add)(lbl)
        self._emit()

    def _bulk_set_group(self):
        g = self.bulk_group.currentText().strip()
        if not g:
            return
        for lbl in self._selected_labels():
            self._set_override(lbl, g)
            combo = self._row_combos.get(lbl)
            if combo:
                combo.blockSignals(True)
                combo.setCurrentText(g)
                combo.blockSignals(False)
        QtCore.QTimer.singleShot(0, self._refresh_groups)
        self._emit()

    def _selected_labels(self):
        rows = sorted({ix.row() for ix in self.rec_table.selectedIndexes()})
        return [self.rec_table.item(r, 1).text() for r in rows
                if self.rec_table.item(r, 1)]

    # ---- comparison edits ----------------------------------------------
    def _set_member(self, arm, group, on):
        if self._updating:
            return
        spec = self.project.design.arms.get(arm)
        if spec is None:
            return
        members = {c for c in spec.get("conditions", []) if c != group}
        if on:
            members.add(group)
        spec["conditions"] = [g for g in self.project.all_groups if g in members]
        if spec.get("control") not in spec["conditions"]:
            spec["control"] = spec["conditions"][0] if spec["conditions"] else None
        QtCore.QTimer.singleShot(0, self._rebuild_comparisons)
        self._emit()

    def _set_control(self, arm, group):
        if self._updating:
            return
        spec = self.project.design.arms.get(arm)
        if spec is not None and group:
            spec["control"] = group
            self._emit()

    def _rename(self, arm, new):
        new = (new or "").strip()
        arms = self.project.design.arms
        if not new or new == arm or new in arms:
            return
        self.project.design.arms = {(new if k == arm else k): v
                                    for k, v in arms.items()}
        QtCore.QTimer.singleShot(0, self._rebuild_comparisons)
        self._emit()

    def _add_comparison(self):
        arms = self.project.design.arms
        name, i = "comparison", 2
        while name in arms:
            name = f"comparison {i}"
            i += 1
        groups = self.project.conditions
        arms[name] = {"control": projmod._guess_control(groups),
                      "conditions": list(groups)}
        QtCore.QTimer.singleShot(0, self._rebuild_comparisons)
        self._emit()

    def _remove_comparison(self, arm):
        self.project.design.arms.pop(arm, None)
        QtCore.QTimer.singleShot(0, self._rebuild_comparisons)
        self._emit()

    def _vehicle_changed(self):
        if self._updating:
            return
        a, b = self.veh_a.currentText(), self.veh_b.currentText()
        self.project.design.vehicle = ([a, b] if a != _NONE and b != _NONE
                                       and a != b else None)
        self._emit()

    # ---- whole-design actions ------------------------------------------
    def _auto_detect(self):
        self.project.design = projmod.auto_design(self.project.conditions)
        self._post_design()

    def _reset(self):
        self.project.excluded = set()
        self.project.overrides = {}
        self.project.design = projmod.auto_design(self.project.conditions)
        self._post_design()

    def _post_design(self):
        projmod.ensure_colors(self.project.design, self.project.all_groups)
        self._refresh()
        self.designChanged.emit()

    def _emit(self):
        projmod.ensure_colors(self.project.design, self.project.all_groups)
        self.designChanged.emit()

    # ---- small helpers -------------------------------------------------
    @staticmethod
    def _ro_item(text):
        item = QtWidgets.QTableWidgetItem(text)
        item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
        return item

    @staticmethod
    def _checkbox_cell(checked, on_toggle):
        w = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setAlignment(QtCore.Qt.AlignCenter)
        cb = QtWidgets.QCheckBox()
        cb.setChecked(checked)
        cb.toggled.connect(on_toggle)
        h.addWidget(cb)
        return w, cb
