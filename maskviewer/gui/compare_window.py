"""Comparison window — a dedicated space for cross-recording / treatment analysis.

A standalone QMainWindow (Analysis ▸ Comparison window) for the loaded project:
compute per-cell metrics across every recording (recording = experimental unit;
background thread + per-project disk cache), then explore by condition in a big
tabbed plot area (Distributions: strip/box/superplot · Ensemble MSD · Scatter)
beside a sortable stats table (per-contrast p / Bonferroni / Cohen's d / OLS).
Uses the project's Design (arms, controls, colours); click a point → load that
recording in the main viewer.
"""
from __future__ import annotations

import os
import pickle

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets

from . import compare_plots
from .plot_export import save_plot
from ..analysis import compare, metric_docs, feature_tables
from ..config import PROJECT_ROOT

_DIST_KINDS = ["Strip (mean ± SEM)", "Box (+ Bonferroni)", "Superplot"]
_STAT_COLS = ["arm", "contrast", "n ctrl", "n test", "p", "Bonferroni",
              "Cohen d", "OLS β", "OLS p"]


class _Worker(QtCore.QObject):
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(object)

    def __init__(self, entries):
        super().__init__()
        self.entries = entries
        self.cancel = False

    def run(self):
        try:
            res = compare.build_comparison(
                self.entries, progress_cb=lambda i, n: (self.progress.emit(i, n)
                                                        or not self.cancel))
        except Exception as exc:                          # surface, don't crash
            res = exc
        self.done.emit(res)


class CompareWindow(QtWidgets.QMainWindow):
    recordingPicked = QtCore.pyqtSignal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Comparison")
        self.resize(1100, 720)
        self.project = project
        self._per_cell = None
        self._msd = None
        self._thread = self._worker = None
        self._design_editor = None

        self._build_ui()
        self.set_project(project)

    # -- ui --------------------------------------------------------------
    def _build_ui(self):
        self.compute_btn = QtWidgets.QPushButton("Compute")
        self.compute_btn.clicked.connect(self._compute)
        self.recompute = QtWidgets.QCheckBox("ignore cache")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setMaximumWidth(160)
        self.progress.hide()
        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.metric_y = QtWidgets.QComboBox()
        self.metric_y.setToolTip("Y metric (Scatter tab)")
        self.metric_y.currentIndexChanged.connect(self._replot)
        self.min_frames = QtWidgets.QSpinBox()
        self.min_frames.setRange(1, 9999)
        self.min_frames.setPrefix("≥")
        self.min_frames.setToolTip("Min frames tracked per cell")
        self.min_frames.valueChanged.connect(self._replot)
        self.ols = QtWidgets.QCheckBox("OLS-adjust")
        self.ols.setToolTip("Treatment effect after frac_spread + density")
        self.ols.toggled.connect(self._replot)
        self.control = QtWidgets.QComboBox()
        self.control.setToolTip("Control condition (single-arm designs)")
        self.control.currentIndexChanged.connect(self._control_changed)
        self.stat = QtWidgets.QComboBox()
        self.stat.addItems(["mean ± SEM", "median ± 95% CI"])
        self.stat.currentIndexChanged.connect(self._replot)
        export = QtWidgets.QPushButton("Export…")
        export.clicked.connect(self._export)
        self.groups_btn = QtWidgets.QPushButton("Groups…")
        self.groups_btn.setToolTip("Assign recordings to groups, pick controls, "
                                   "include/exclude — applies instantly")
        self.groups_btn.clicked.connect(self._open_design_editor)

        bar = QtWidgets.QToolBar()
        bar.setMovable(False)
        for w in (self.compute_btn, self.recompute, self.progress, self.groups_btn):
            bar.addWidget(w)
        bar.addSeparator()
        for lbl, w in (("Metric", self.metric), ("Y", self.metric_y),
                       ("Control", self.control), ("MSD", self.stat),
                       ("Frames", self.min_frames)):
            bar.addWidget(QtWidgets.QLabel(" " + lbl + " "))
            bar.addWidget(w)
        bar.addWidget(self.ols)
        bar.addSeparator()
        bar.addWidget(export)
        self.addToolBar(bar)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(self._replot)
        self.dist_kind = QtWidgets.QComboBox()
        self.dist_kind.addItems(_DIST_KINDS)
        self.dist_kind.currentIndexChanged.connect(self._replot)
        self.dist_plot = pg.PlotWidget()
        dist = QtWidgets.QWidget()
        dl = QtWidgets.QVBoxLayout(dist)
        kr = QtWidgets.QHBoxLayout()
        kr.addWidget(QtWidgets.QLabel("View"))
        kr.addWidget(self.dist_kind)
        kr.addStretch(1)
        dl.addLayout(kr)
        dl.addWidget(self.dist_plot)
        self.msd_plot = pg.PlotWidget()
        self.scatter_plot = pg.PlotWidget()
        self.tabs.addTab(dist, "Distributions")
        self.tabs.addTab(self.msd_plot, "Ensemble MSD")
        self.tabs.addTab(self.scatter_plot, "Scatter")

        self.omnibus = QtWidgets.QLabel("")
        self.omnibus.setWordWrap(True)
        self.table = QtWidgets.QTableWidget()
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        right = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(right)
        rl.addWidget(QtWidgets.QLabel("<b>Per-contrast stats</b> (recording = unit)"))
        rl.addWidget(self.omnibus)
        rl.addWidget(self.table, 1)
        self._save_btn = QtWidgets.QPushButton("Save plot…")
        self._save_btn.clicked.connect(self._save_current_plot)
        rl.addWidget(self._save_btn)

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.addWidget(self.tabs)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)
        self.status = self.statusBar()

    # -- project ---------------------------------------------------------
    def set_project(self, project):
        self.project = project
        self._per_cell = self._msd = None
        safe = "".join(c if c.isalnum() else "_" for c in project.name)[:40]
        self._cache = os.path.join(PROJECT_ROOT, "analysis_out",
                                   f"_compare_{safe}.pkl")
        self.dist_plot.clear()
        self.msd_plot.clear()
        self.scatter_plot.clear()
        self.table.setRowCount(0)
        self.omnibus.setText("")
        self._refresh_control_combo()
        if self._design_editor is not None:
            self._design_editor.set_project(project, None)
        self.setWindowTitle(f"Comparison — {project.name}")
        self.status.showMessage(
            f"{project.name}: {project.n_recordings} recordings · "
            f"{len(project.conditions)} groups — click Compute")

    def _refresh_control_combo(self):
        arms = self.project.design.arms
        single = len(arms) == 1
        self.control.blockSignals(True)
        self.control.clear()
        if single:
            self.control.setEnabled(True)
            self.control.addItems(self.project.conditions)
            arm = next(iter(arms.values()))
            if arm["control"] in self.project.conditions:
                self.control.setCurrentText(arm["control"])
        else:
            self.control.setEnabled(False)
            self.control.addItem("(per-arm)")
        self.control.blockSignals(False)

    def _control_changed(self):
        arms = self.project.design.arms
        if len(arms) == 1 and self.control.isEnabled():
            next(iter(arms.values()))["control"] = self.control.currentText()
            self._replot()

    # -- groups & comparisons editor -------------------------------------
    def _open_design_editor(self):
        if self._design_editor is None:
            from .design_editor import DesignEditor
            self._design_editor = DesignEditor(self.project, self._per_cell, self)
            self._design_editor.designChanged.connect(self._on_design_changed)
        else:
            self._design_editor.set_data(self._per_cell)
        self._design_editor.show()
        self._design_editor.raise_()

    def _on_design_changed(self):
        """Grouping / control / include changed — remap + replot, no recompute."""
        self._refresh_control_combo()
        if self._per_cell is not None and not self._per_cell.empty:
            pc = self._filtered()
            self.status.showMessage(
                f"{self.project.name}: {pc['recording'].nunique()} recordings · "
                f"{pc['condition'].nunique()} groups · {len(pc)} cells")
        self._replot()

    # -- compute ---------------------------------------------------------
    def _compute(self):
        if self._thread is not None and self._thread.isRunning():
            if self._worker:
                self._worker.cancel = True
            return
        if not self.project.entries:
            return
        if os.path.exists(self._cache) and not self.recompute.isChecked():
            try:
                with open(self._cache, "rb") as f:
                    blob = pickle.load(f)
                return self._on_done((blob["per_cell"], blob.get("msd")), cached=True)
            except Exception:
                pass
        self.compute_btn.setText("Cancel")
        self.progress.setValue(0)
        self.progress.show()
        self._thread = QtCore.QThread(self)
        self._worker = _Worker(self.project.entries)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(
            lambda i, n: self.progress.setValue(int(100 * i / n) if n else 0))
        self._worker.done.connect(lambda r: self._on_done(r, cached=False))
        self._thread.start()

    def _on_done(self, result, cached):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = self._worker = None
        self.compute_btn.setText("Compute")
        self.progress.hide()
        if isinstance(result, Exception):
            self.status.showMessage(f"Compute failed: {result}")
            return
        per_cell, msd = result
        if per_cell is None or per_cell.empty:
            self.status.showMessage("No cells found across recordings.")
            return
        self._per_cell, self._msd = per_cell, msd
        if not cached:
            try:
                os.makedirs(os.path.dirname(self._cache), exist_ok=True)
                with open(self._cache, "wb") as f:
                    pickle.dump({"per_cell": per_cell, "msd": msd}, f)
            except Exception:
                pass
        cols = compare.metric_columns(per_cell)
        for combo in (self.metric, self.metric_y):
            cur = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(cols)
            for i, c in enumerate(cols):
                base = c.replace("mean_", "").replace("median_", "")
                tip = metric_docs.tooltip(base.rsplit("_um", 1)[0].rsplit("_px", 1)[0])
                if tip:
                    combo.setItemData(i, tip, QtCore.Qt.ToolTipRole)
            default = "mean_area_um2" if "mean_area_um2" in cols else (cols[0] if cols else "")
            combo.setCurrentText(cur if cur in cols else default)
            combo.blockSignals(False)
        if self._design_editor is not None:
            self._design_editor.set_data(per_cell)
        self.status.showMessage(
            f"{self.project.name}: {per_cell['recording'].nunique()} recordings · "
            f"{per_cell['condition'].nunique()} groups · {len(per_cell)} cells"
            + ("  (cached)" if cached else ""))
        self._replot()

    # -- plot / stats ----------------------------------------------------
    def _filtered(self):
        pc = self.project.regroup(self._per_cell)        # drop excluded + regroup
        mf = self.min_frames.value()
        if mf > 1 and pc is not None and "frames_tracked" in pc.columns:
            pc = pc[pc["frames_tracked"] >= mf]
        return pc

    def _filtered_msd(self):
        return self.project.regroup(self._msd)           # excluded/regroup-aware

    def _pick(self, label):
        self.recordingPicked.emit(label)

    def _replot(self):
        if self._per_cell is None or self._per_cell.empty:
            return
        design = self.project.design
        tab = self.tabs.currentIndex()
        if tab == 1:
            self.msd_plot.clear()
            self.msd_plot.setLogMode(x=False, y=False)
            stat = "median" if self.stat.currentText().startswith("median") else "mean"
            compare_plots.ensemble_msd(self.msd_plot, self._filtered_msd(), design, stat)
            return
        pc = self._filtered()
        metric = self.metric.currentText()
        if pc.empty or not metric:
            return
        per_rec = compare.aggregate(pc)
        if metric not in per_rec.columns:
            return
        if tab == 2:
            self.scatter_plot.clear()
            compare_plots.scatter(self.scatter_plot, per_rec, metric,
                                  self.metric_y.currentText(), design, self._pick)
        else:
            self.dist_plot.clear()
            kind = self.dist_kind.currentIndex()
            if kind == 1:
                compare_plots.box(self.dist_plot, per_rec, metric, design)
            elif kind == 2:
                compare_plots.superplot(self.dist_plot, pc, per_rec, metric, design)
            else:
                compare_plots.strip(self.dist_plot, per_rec, metric, design, self._pick)
        self._update_stats(per_rec, metric)

    def _update_stats(self, per_rec, metric):
        d = self.project.design
        bc = compare.by_condition(per_rec, metric)
        kw = feature_tables._kw(list(bc.values()))
        r = feature_tables.arm_tests(bc, arms=d.arms, vehicle=d.vehicle)
        eff = {(e["arm"], e["contrast"]): e
               for e in compare.effect_sizes(bc, arms=d.arms)}
        ols = {}
        if self.ols.isChecked():
            for o in compare.ols_adjusted(per_rec, metric, arms=d.arms):
                ols[(o["arm"], o["contrast"])] = o
        veh = r.get("vehicle", {}).get("p")
        txt = f"omnibus KW ({len(bc)} conditions): {feature_tables.stars(kw)}"
        if d.vehicle:
            txt += f"  ·  vehicle {d.vehicle[0]}–{d.vehicle[1]}: {feature_tables.stars(veh)}"
        self.omnibus.setText(txt)
        rows = []
        for arm, spec in d.arms.items():
            ctrl = spec["control"]
            for t in [c for c in spec["conditions"] if c != ctrl]:
                key = f"{t} vs {ctrl}"
                pr = r[arm]["pairs"].get(f"{ctrl}_vs_{t}", {})
                e = eff.get((arm, key), {})
                o = ols.get((arm, key))
                rows.append([arm, key, e.get("n_ctrl"), e.get("n_test"),
                             pr.get("p"), pr.get("p_bonf"), e.get("cohen_d"),
                             o["coef"] if o else None, o["p"] if o else None])
        self._fill_table(rows)

    def _fill_table(self, rows):
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(_STAT_COLS))
        self.table.setHorizontalHeaderLabels(_STAT_COLS)
        self.table.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            for ci, v in enumerate(row):
                item = QtWidgets.QTableWidgetItem()
                if isinstance(v, str) or v is None:
                    item.setText("" if v is None else v)
                else:
                    item.setData(QtCore.Qt.DisplayRole, round(float(v), 4))
                self.table.setItem(ri, ci, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    # -- misc ------------------------------------------------------------
    def _current_plot(self):
        return [self.dist_plot, self.msd_plot, self.scatter_plot][self.tabs.currentIndex()]

    def _save_current_plot(self):
        save_plot(self._current_plot(), self, "comparison.png")

    def _export(self):
        if self._per_cell is None:
            return
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "Export comparison CSVs")
        if not d:
            return
        pc = self._filtered()
        pc.to_csv(os.path.join(d, "comparison_per_cell.csv"), index=False)
        compare.aggregate(pc).to_csv(
            os.path.join(d, "comparison_per_recording.csv"), index=False)
        if self._msd is not None and not self._msd.empty:
            self._msd.to_csv(os.path.join(d, "comparison_ensemble_msd.csv"),
                             index=False)
        QtWidgets.QMessageBox.information(self, "Exported", f"CSVs written to {d}")
