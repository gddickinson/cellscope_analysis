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
from .compare_tables import (StatsTablesMixin, ResultsIOMixin, ComputeWorker,
                             show_metrics_help)
from ..io import recording as _recording
from .compare_filters import FilterMixin
from .plot_style import PlotStyle, PlotStyleMixin
from ..analysis import compare, metric_docs
from ..config import PROJECT_ROOT

_DIST_KINDS = ["Strip (mean ± SEM)", "Box (+ Bonferroni)", "Superplot",
               "Bars (mean ± SEM)"]


class CompareWindow(StatsTablesMixin, ResultsIOMixin, PlotStyleMixin, FilterMixin,
                    QtWidgets.QMainWindow):
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
        self._settings = QtCore.QSettings("cellscope_analysis", "compare")
        self.style = PlotStyle.from_settings(self._settings)
        self._style_dialog = None
        self.hidden_groups = set()       # groups hidden from the graphs (display only)

        self._build_ui()
        self.set_project(project)

    # -- ui --------------------------------------------------------------
    def _build_ui(self):
        self.compute_btn = QtWidgets.QPushButton("Compute")
        self.compute_btn.setToolTip("Measure every cell in every recording "
                                    "(threaded; result cached per project)")
        self.compute_btn.clicked.connect(self._compute)
        self.recompute = QtWidgets.QCheckBox("ignore cache")
        self.recompute.setToolTip("Recompute from masks instead of the cached result")
        self.lags = QtWidgets.QSpinBox()
        self.lags.setRange(5, 300)
        self.lags.setValue(compare.MAX_LAG)
        self.lags.setPrefix("lags ")
        self.lags.setToolTip("Number of MSD lags computed (max τ = lags × frame "
                             "interval) — click Compute to apply (recompute)")
        self.fluor = QtWidgets.QComboBox()
        self.fluor.addItem("(no fluor)")
        self.fluor.setToolTip("Correlate edge protrusion/retraction with a "
                              "fluorescence channel (e.g. tagged PIEZO1) per cell "
                              "→ edge_piezo_corr metric — click Compute to apply")
        self.metric = QtWidgets.QComboBox()
        self.metric.setToolTip("Primary metric — drives the left plots, the "
                               "histogram, stats and data tables. _spread / "
                               "_rounded columns are state-segmented (see Help)")
        self.metric.currentIndexChanged.connect(self._replot)
        self.metric_y = QtWidgets.QComboBox()
        self.metric_y.setToolTip("Y metric (Scatter tab)")
        self.metric_y.currentIndexChanged.connect(self._replot)
        self._build_filter_widgets()         # min_frames / quality / cells / state
        self.filters_btn = QtWidgets.QPushButton("Filters…")          # + crowding /
        self.filters_btn.setToolTip("Restrict the cells / recordings compared: "    # edge
                                    "frames, track-quality, cells/recording, state, "
                                    "nearest-neighbour crowding, distance from edge")
        self.filters_btn.clicked.connect(self._open_filters_dialog)
        self.ols = QtWidgets.QCheckBox("OLS-adjust")
        self.ols.setToolTip("Treatment effect after frac_spread + density")
        self.ols.toggled.connect(self._replot)
        self.control = QtWidgets.QComboBox()
        self.control.setToolTip("Control condition (single-arm designs)")
        self.control.currentIndexChanged.connect(self._control_changed)
        self.stat = QtWidgets.QComboBox()
        self.stat.addItems(["mean ± SEM", "median ± 95% CI"])
        self.stat.setToolTip("Ensemble-MSD band: mean ± SEM, or median + "
                             "bootstrap 95% CI (over recordings)")
        self.stat.currentIndexChanged.connect(self._replot)
        self.results_btn = QtWidgets.QToolButton()
        self.results_btn.setText("Results ▾")
        self.results_btn.setToolTip("Save / load the computed comparison results, "
                                    "or export them as CSVs")
        self.results_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        rmenu = QtWidgets.QMenu(self.results_btn)
        rmenu.addAction("Multivariate test…", self._show_multivariate)
        rmenu.addSeparator()
        rmenu.addAction("Save results…", self._save_results)
        rmenu.addAction("Load results…", self._load_results)
        rmenu.addSeparator()
        rmenu.addAction("Export CSVs…", self._export)
        self.results_btn.setMenu(rmenu)
        self.groups_btn = QtWidgets.QPushButton("Groups…")
        self.groups_btn.setToolTip("Assign recordings to groups, pick controls, "
                                   "include/exclude — applies instantly")
        self.groups_btn.clicked.connect(self._open_design_editor)
        self.style_btn = QtWidgets.QPushButton("Style…")
        self.style_btn.setToolTip("Plot style: fonts, marker/line sizes, fill, "
                                  "grid, log axes, histogram bins, bars-vs-points "
                                  "(or shift-right-click any plot)")
        self.style_btn.clicked.connect(self._open_style_dialog)
        self.help_btn = QtWidgets.QPushButton("Help")
        self.help_btn.setToolTip("Metrics & methods reference (what each metric "
                                 "means + how the comparison is computed)")
        self.help_btn.clicked.connect(lambda: show_metrics_help(self))

        bar = QtWidgets.QToolBar()
        bar.setMovable(False)
        for w in (self.compute_btn, self.recompute, self.lags, self.fluor,
                  self.groups_btn, self.filters_btn):
            bar.addWidget(w)
        bar.addSeparator()
        for lbl, w in (("Metric", self.metric), ("Y", self.metric_y),
                       ("Control", self.control), ("MSD", self.stat)):
            bar.addWidget(QtWidgets.QLabel(" " + lbl + " "))
            bar.addWidget(w)
        bar.addWidget(self.ols)
        bar.addSeparator()
        bar.addWidget(self.results_btn)
        bar.addWidget(self.style_btn)
        bar.addWidget(self.help_btn)
        self.addToolBar(bar)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.currentChanged.connect(self._replot)
        self.dist_kind = QtWidgets.QComboBox()
        self.dist_kind.addItems(_DIST_KINDS)
        self.dist_kind.setToolTip("Strip = recording points + mean±SEM · Box = "
                                  "quartiles + Bonferroni stars · Superplot = cells "
                                  "coloured by recording behind the recording means")
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
        self.tabs.setTabToolTip(0, "Per-recording values by group: strip (mean±SEM) "
                                   "/ box (+Bonferroni stars) / superplot")
        self.tabs.setTabToolTip(1, "Ensemble MSD by condition (recording = unit) — "
                                   "mean±SEM or median+bootstrap CI")
        self.tabs.setTabToolTip(2, "One recording-level metric vs another (+Spearman)")

        self.right_tabs = QtWidgets.QTabWidget()
        self.right_tabs.addTab(self._build_stats_tab(), "Stats")
        self.right_tabs.addTab(self._build_hist_tab(), "Histogram")
        self.right_tabs.addTab(self._build_data_tab(), "Data")
        self.right_tabs.setTabToolTip(0, "Per-contrast tests (recording = unit): "
                                         "KW + Bonferroni MWU vs control + Cohen d + OLS")
        self.right_tabs.setTabToolTip(1, "Per-cell distribution of the chosen metric, "
                                         "one curve per group")
        self.right_tabs.setTabToolTip(2, "Per-recording + per-group tables for the "
                                         "chosen metric (unit-tagged, exportable)")

        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.addWidget(self.tabs)
        split.addWidget(self.right_tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)
        self.status = self.statusBar()
        self.busy = StatusProgress()                  # bottom-bar progress + ETA
        self.status.addPermanentWidget(self.busy)
        # shift-right-click any plot → the plot-style dialog
        self._install_style_filters([self.dist_plot, self.msd_plot,
                                     self.scatter_plot, self.hist_plot])
        self._legends = {
            self.dist_plot: self.dist_plot.addLegend(offset=(-10, 10)),
            self.scatter_plot: self.scatter_plot.addLegend(offset=(-10, 10)),
            self.msd_plot: self.msd_plot.addLegend(offset=(-10, 10)),
            self.hist_plot: self._hist_legend}

    def _style_groups(self):
        """(conditions, hidden-set, design) for the graph-options Show-groups list."""
        if self._per_cell is not None and not self._per_cell.empty:
            pc = self.project.regroup(self._per_cell)
            conds = compare.order_conditions(pc["condition"].unique(),
                                             order=self.project.design.condition_order())
        else:
            conds = self.project.conditions
        return conds, self.hidden_groups, self.project.design

    def _prep_legend(self, plot):
        lg = self._legends.get(plot)
        if lg is not None:
            lg.clear()
            lg.setVisible(self.style.legend)
            lg.setLabelTextColor("k" if self.style.background == "white" else "w")

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
        self.data_note = QtWidgets.QLabel("")
        self.data_note.setWordWrap(True)
        self.data_note.setVisible(False)
        lay.addWidget(self.data_note)
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
        self._safe = "".join(c if c.isalnum() else "_" for c in project.name)[:40]
        self._cache = self._cache_path()
        for p in (self.dist_plot, self.msd_plot, self.scatter_plot, self.hist_plot):
            p.clear()
        self._hist_legend.clear()
        for t in (self.table, self.rec_table, self.cond_table):
            t.setRowCount(0)
        self.omnibus.setText("")
        self._refresh_control_combo()
        self._refresh_fluor_combo()
        if self._design_editor is not None:
            self._design_editor.set_project(project, None)
        self.setWindowTitle(f"Comparison — {project.name}")
        self.status.showMessage(
            f"{project.name}: {project.n_recordings} recordings · "
            f"{len(project.conditions)} groups — click Compute")

    def _refresh_fluor_combo(self):
        names = next((n for e in self.project.entries        # from the first sidecar
                      if (n := _recording.channel_names_of(e.recording_path))), [])
        cur = self.fluor.currentText()
        self.fluor.blockSignals(True)
        self.fluor.clear()
        self.fluor.addItem("(no fluor)")
        self.fluor.addItems(names)
        self.fluor.setCurrentText(cur if cur in (["(no fluor)"] + names) else "(no fluor)")
        self.fluor.blockSignals(False)

    def _fluor_choice(self):
        name = self.fluor.currentText()
        return None if name == "(no fluor)" else name

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
    def _cache_path(self):
        fl = self._fluor_choice()
        ch = "_" + "".join(c if c.isalnum() else "" for c in fl) if fl else ""
        return os.path.join(PROJECT_ROOT, "analysis_out",
                            f"_compare_{self._safe}_lag{self.lags.value()}{ch}.pkl")

    def _compute(self):
        if self._thread is not None and self._thread.isRunning():
            if self._worker:
                self._worker.cancel = True
            return
        if not self.project.entries:
            return
        self._cache = self._cache_path()              # cache is keyed by lag count
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
        self._worker = ComputeWorker(self.project.entries, self.lags.value(),
                                     self._fluor_choice())
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
                combo.setItemData(i, metric_docs.comparison_tooltip(c),
                                  QtCore.Qt.ToolTipRole)
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
        # annotate every plot title when filters/visibility are active
        compare_plots.set_filter_note(
            self._filter_note() if self.style.show_filter_note else "")
        # graph subset: hidden groups are dropped from the plots (display only —
        # the Stats / Data tables still cover every group)
        hg = self.hidden_groups
        gpr = per_rec[~per_rec["condition"].isin(hg)] if (per_rec is not None and hg) else per_rec
        gpc = pc[~pc["condition"].isin(hg)] if (pc is not None and hg) else pc
        tab = self.tabs.currentIndex()
        if tab == 1:
            self.msd_plot.clear()
            self._prep_legend(self.msd_plot)
            self.msd_plot.setLogMode(x=False, y=False)
            stat = "median" if self.stat.currentText().startswith("median") else "mean"
            msd = self._filtered_msd()
            if msd is not None and gpr is not None:
                msd = msd[msd["recording"].isin(set(gpr["recording"]))]
            compare_plots.ensemble_msd(self.msd_plot, msd, design, stat, style=self.style)
        elif gpr is not None and metric in gpr.columns:
            if tab == 2:
                self.scatter_plot.clear()
                self._prep_legend(self.scatter_plot)
                compare_plots.scatter(self.scatter_plot, gpr, metric,
                                      self.metric_y.currentText(), design, self._pick,
                                      style=self.style)
            else:
                self.dist_plot.clear()
                self._prep_legend(self.dist_plot)
                kind = self.dist_kind.currentIndex()
                if kind == 1:
                    compare_plots.box(self.dist_plot, gpr, metric, design,
                                      style=self.style)
                elif kind == 2:
                    compare_plots.superplot(self.dist_plot, gpc, gpr, metric,
                                            design, style=self.style)
                elif kind == 3:
                    compare_plots.bars(self.dist_plot, gpr, metric, design,
                                       style=self.style)
                else:
                    compare_plots.strip(self.dist_plot, gpr, metric, design,
                                        self._pick, style=self.style)
        # right panel: Stats / Data over ALL groups; histogram shows the visible set
        if per_rec is not None and metric and metric in per_rec.columns:
            self._update_stats(per_rec, metric)
            self.hist_plot.clear()
            self._prep_legend(self.hist_plot)
            compare_plots.histogram(self.hist_plot, gpc, metric, design, style=self.style)
            self._fill_data(per_rec, pc, metric)

    # -- misc ------------------------------------------------------------
    def _current_plot(self):
        return [self.dist_plot, self.msd_plot, self.scatter_plot][self.tabs.currentIndex()]

    def _save_current_plot(self):
        save_plot(self._current_plot(), self, "comparison.png")
