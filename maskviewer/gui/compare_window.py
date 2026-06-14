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
from .status_progress import StatusProgress
from .compare_tables import StatsTablesMixin
from ..analysis import compare, metric_docs
from ..config import PROJECT_ROOT

_DIST_KINDS = ["Strip (mean ± SEM)", "Box (+ Bonferroni)", "Superplot"]


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


class CompareWindow(StatsTablesMixin, QtWidgets.QMainWindow):
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
        self.metric = QtWidgets.QComboBox()
        self.metric.currentIndexChanged.connect(self._replot)
        self.metric_y = QtWidgets.QComboBox()
        self.metric_y.setToolTip("Y metric (Scatter tab)")
        self.metric_y.currentIndexChanged.connect(self._replot)
        self.min_frames = QtWidgets.QSpinBox()
        self.min_frames.setRange(1, 9999)
        self.min_frames.setPrefix("≥")
        self.min_frames.setToolTip("Keep cells tracked for at least this many frames")
        self.min_frames.valueChanged.connect(self._replot)
        self.min_quality = QtWidgets.QDoubleSpinBox()
        self.min_quality.setRange(0.0, 1.0)
        self.min_quality.setSingleStep(0.05)
        self.min_quality.setPrefix("≥")
        self.min_quality.setToolTip("Keep cells with at least this track_quality (0–1)")
        self.min_quality.valueChanged.connect(self._replot)
        self.min_cells = QtWidgets.QSpinBox()
        self.min_cells.setRange(0, 99999)
        self.min_cells.setPrefix("≥")
        self.min_cells.setToolTip("Drop recordings with fewer than this many "
                                  "(filtered) cells — recording = unit")
        self.min_cells.valueChanged.connect(self._replot)
        self.state_sel = QtWidgets.QComboBox()
        self.state_sel.addItems(["all cells", "mostly spread", "mostly rounded"])
        self.state_sel.setToolTip("Keep cells that spend most of their time in "
                                  "this state (frac_spread / frac_rounded ≥ 0.5)")
        self.state_sel.currentIndexChanged.connect(self._replot)
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
        for w in (self.compute_btn, self.recompute, self.groups_btn):
            bar.addWidget(w)
        bar.addSeparator()
        for lbl, w in (("Metric", self.metric), ("Y", self.metric_y),
                       ("Control", self.control), ("MSD", self.stat)):
            bar.addWidget(QtWidgets.QLabel(" " + lbl + " "))
            bar.addWidget(w)
        bar.addWidget(self.ols)
        bar.addSeparator()
        bar.addWidget(export)
        self.addToolBar(bar)

        fbar = QtWidgets.QToolBar()          # second row: cell / recording filters
        fbar.setMovable(False)
        fbar.addWidget(QtWidgets.QLabel(" Filters: "))
        for lbl, w in (("frames", self.min_frames), ("quality", self.min_quality),
                       ("cells/rec", self.min_cells), ("state", self.state_sel)):
            fbar.addWidget(QtWidgets.QLabel(" " + lbl + " "))
            fbar.addWidget(w)
        self.addToolBarBreak()
        self.addToolBar(fbar)

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

        self.right_tabs = QtWidgets.QTabWidget()
        self.right_tabs.addTab(self._build_stats_tab(), "Stats")
        self.right_tabs.addTab(self._build_hist_tab(), "Histogram")
        self.right_tabs.addTab(self._build_data_tab(), "Data")

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.addWidget(self.tabs)
        split.addWidget(self.right_tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)
        self.status = self.statusBar()
        self.busy = StatusProgress()                  # bottom-bar progress + ETA
        self.status.addPermanentWidget(self.busy)

    # -- right-panel tabs ------------------------------------------------
    def _build_stats_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.addWidget(QtWidgets.QLabel("<b>Per-contrast stats</b> (recording = unit)"))
        self.omnibus = QtWidgets.QLabel("")
        self.omnibus.setWordWrap(True)
        lay.addWidget(self.omnibus)
        self.table = self._mk_table()
        lay.addWidget(self.table, 1)
        self._save_btn = QtWidgets.QPushButton("Save plot…")
        self._save_btn.clicked.connect(self._save_current_plot)
        lay.addWidget(self._save_btn)
        return w

    def _build_hist_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.addWidget(QtWidgets.QLabel("Per-cell distribution of the chosen metric"))
        self.hist_plot = pg.PlotWidget()
        self._hist_legend = self.hist_plot.addLegend(offset=(-10, 10))
        lay.addWidget(self.hist_plot, 1)
        b = QtWidgets.QPushButton("Save histogram…")
        b.clicked.connect(lambda: save_plot(self.hist_plot, self, "histogram.png"))
        lay.addWidget(b)
        return w

    def _build_data_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.addWidget(QtWidgets.QLabel("<b>Per recording</b> (unit) — current metric"))
        self.rec_table = self._mk_table()
        lay.addWidget(self.rec_table, 2)
        lay.addWidget(QtWidgets.QLabel("<b>Per group</b> — recordings summary"))
        self.cond_table = self._mk_table()
        lay.addWidget(self.cond_table, 1)
        b = QtWidgets.QPushButton("Export tables…")
        b.clicked.connect(self._export)
        lay.addWidget(b)
        return w

    @staticmethod
    def _mk_table():
        t = QtWidgets.QTableWidget()
        t.setSortingEnabled(True)
        t.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        return t

    # -- project ---------------------------------------------------------
    def set_project(self, project):
        self.project = project
        self._per_cell = self._msd = None
        safe = "".join(c if c.isalnum() else "_" for c in project.name)[:40]
        self._cache = os.path.join(PROJECT_ROOT, "analysis_out",
                                   f"_compare_{safe}.pkl")
        for p in (self.dist_plot, self.msd_plot, self.scatter_plot, self.hist_plot):
            p.clear()
        self._hist_legend.clear()
        for t in (self.table, self.rec_table, self.cond_table):
            t.setRowCount(0)
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
        self.busy.start(f"Measuring {len(self.project.entries)} recordings")
        self._thread = QtCore.QThread(self)
        self._worker = _Worker(self.project.entries)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.busy.update)
        self._worker.done.connect(lambda r: self._on_done(r, cached=False))
        self._thread.start()

    def _on_done(self, result, cached):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = self._worker = None
        self.compute_btn.setText("Compute")
        if isinstance(result, Exception):
            self.busy.fail("compute failed")
            self.status.showMessage(f"Compute failed: {result}")
            return
        per_cell, msd = result
        if not cached:
            self.busy.finish()
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
        if pc is None or pc.empty:
            return pc
        mf = self.min_frames.value()
        if mf > 1 and "frames_tracked" in pc.columns:
            pc = pc[pc["frames_tracked"] >= mf]
        q = self.min_quality.value()
        if q > 0 and "track_quality" in pc.columns:
            pc = pc[pc["track_quality"] >= q]
        state = self.state_sel.currentText()
        if state == "mostly spread" and "frac_spread" in pc.columns:
            pc = pc[pc["frac_spread"] >= 0.5]
        elif state == "mostly rounded" and "frac_rounded" in pc.columns:
            pc = pc[pc["frac_rounded"] >= 0.5]
        return pc

    def _filtered_msd(self):
        return self.project.regroup(self._msd)           # excluded/regroup-aware

    def _pick(self, label):
        self.recordingPicked.emit(label)

    def _replot(self):
        if self._per_cell is None or self._per_cell.empty:
            return
        design = self.project.design
        pc = self._filtered()
        metric = self.metric.currentText()
        per_rec = compare.aggregate(pc) if pc is not None and not pc.empty else None
        if (per_rec is not None and self.min_cells.value() > 0
                and "n_cells" in per_rec.columns):           # drop low-N recordings
            keep = set(per_rec[per_rec["n_cells"] >= self.min_cells.value()]["recording"])
            per_rec = per_rec[per_rec["recording"].isin(keep)]
            pc = pc[pc["recording"].isin(keep)]
        tab = self.tabs.currentIndex()
        if tab == 1:
            self.msd_plot.clear()
            self.msd_plot.setLogMode(x=False, y=False)
            stat = "median" if self.stat.currentText().startswith("median") else "mean"
            msd = self._filtered_msd()
            if msd is not None and per_rec is not None:
                msd = msd[msd["recording"].isin(set(per_rec["recording"]))]
            compare_plots.ensemble_msd(self.msd_plot, msd, design, stat)
        elif per_rec is not None and metric in per_rec.columns:
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
        # right panel (stats + histogram + data) always tracks the current metric
        if per_rec is not None and metric and metric in per_rec.columns:
            self._update_stats(per_rec, metric)
            self.hist_plot.clear()
            self._hist_legend.clear()
            compare_plots.histogram(self.hist_plot, pc, metric, design)
            self._fill_data(per_rec, pc, metric)

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
        import pandas as pd
        pc = self._filtered()
        per_rec = compare.aggregate(pc)
        pc.to_csv(os.path.join(d, "comparison_per_cell.csv"), index=False)
        per_rec.to_csv(os.path.join(d, "comparison_per_recording.csv"), index=False)
        summ = compare.per_condition_summary(per_rec, self.metric.currentText())
        if summ:
            pd.DataFrame(summ).to_csv(
                os.path.join(d, "comparison_per_group_summary.csv"), index=False)
        if self._msd is not None and not self._msd.empty:
            self._msd.to_csv(os.path.join(d, "comparison_ensemble_msd.csv"),
                             index=False)
        QtWidgets.QMessageBox.information(self, "Exported", f"CSVs written to {d}")
