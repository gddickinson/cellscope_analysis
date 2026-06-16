"""Stats + data table population for the Comparison window.

Split out of `compare_window.py` (file-size hygiene). `StatsTablesMixin` fills the
right-panel tables from the per-recording table + the project Design: the
per-contrast **Stats** table (KW / Bonferroni / Cohen d / OLS) and the **Data**
tab's per-recording + per-group tables (unit-tagged). GUI-thread only.
"""
from __future__ import annotations

import hashlib
import json
import os

from PyQt5 import QtCore, QtWidgets

from ..analysis import compare, feature_tables, metric_docs
from .. import project as projmod

_STAT_COLS = ["arm", "contrast", "n ctrl", "n test", "p", "Bonferroni",
              "Cohen d", "OLS β", "OLS p"]

# Comparison-analysis families the Config window toggles (what build_comparison
# computes). Keyed for QSettings ("compare/opt_<key>"); the cache key folds them in,
# so changing a toggle recomputes. Edge↔fluorescence is set by the channel selector.
COMPARE_OPTIONS = [
    ("contacts", "Cell–cell contacts", False,
     "Per-cell contact fraction / count / interface / class + episode dynamics."),
    ("state_segmented", "State-segmented metrics (rounded / spread)", False,
     "Speed / persistence / area split by cell state — the CellScope reproduction."),
    ("solidity", "Solidity (convex hull)", False,
     "area ÷ convex-hull area per frame — slower (a SciPy hull per cell-frame)."),
    ("edge_dynamics", "Edge dynamics (protrusion / retraction / polarity)", False,
     "Per-cell membrane protrusion/retraction summary + events + front–rear "
     "polarity — slowest (a radial edge-velocity kymograph per cell)."),
    ("cil", "Contact-inhibition of locomotion (CIL)", False,
     "Per-cell speed free-vs-in-contact, speed change at contact onset, and "
     "velocity alignment with contacting neighbours."),
    ("fluor_metrics", "Fluorescence intensity + membrane (per channel)", False,
     "Per-cell mean intensity + membrane score / boundary gradient / contrast for "
     "every channel (e.g. SiR-actin / tagged-PIEZO1 level + cortical enrichment)."),
    ("shape_modes", "Shape-mode usage (VAMPIRE)", False,
     "Per-cell dominant shape mode, # modes visited, mode entropy + switch rate."),
]


def compare_options(settings=None) -> dict:
    """``{key: bool}`` comparison-analysis toggles from QSettings (Config window)."""
    s = settings or QtCore.QSettings("cellscope_analysis", "viewer")
    return {k: s.value(f"compare/opt_{k}", d, type=bool)
            for k, _label, d, _tip in COMPARE_OPTIONS}


# Tunable analysis parameters (Config ▸ Analysis parameters). Each:
# (key, label, default, min, max, decimals, section, tooltip). Applied to the analysis
# module globals so they take effect everywhere — comparison + interactive views — by
# being read at call time (the functions reference the globals, not bound defaults).
ANALYSIS_PARAMS = [
    ("nn_radius", "Neighbour radius (µm)", 50.0, 1.0, 2000.0, 0, "Neighbours & contact",
     "Cells within this centroid distance count as neighbours (n_neighbors / crowding "
     "/ density-stratified speed)."),
    ("contact_gap", "Contact gap tolerance (px)", 1.5, 0.5, 10.0, 1,
     "Neighbours & contact",
     "Max boundary-pixel separation treated as a cell–cell contact (touching masks "
     "sit ~1 px apart)."),
    ("extensive_frac", "Extensive-contact threshold", 0.25, 0.05, 1.0, 2,
     "Neighbours & contact",
     "A neighbour interface ≥ this fraction of the cell's boundary is 'extensive' "
     "(else 'point')."),
    ("contact_min_px", "Min contact size (px)", 2.0, 1.0, 50.0, 0,
     "Neighbours & contact",
     "Boundary-pixel contacts smaller than this are ignored (noise floor for cell–cell "
     "touching)."),
    ("rounded_area_um2", "Rounded: max area (µm²)", 960.0, 50.0, 10000.0, 0,
     "State classification (rounded vs spread)",
     "A cell is 'rounded' only if its footprint is ≤ this AND not elongated; drives "
     "state / frac_rounded / all state-segmented metrics."),
    ("rounded_ecc", "Rounded: max eccentricity", 0.85, 0.1, 1.0, 2,
     "State classification (rounded vs spread)",
     "A cell is 'rounded' only if its eccentricity is ≤ this (and small)."),
    ("state_min_area_px", "Min cell area (px)", 200.0, 0.0, 5000.0, 0,
     "State classification (rounded vs spread)",
     "Cells smaller than this footprint are 'unknown' (too small to classify, and "
     "excluded from shape-mode fitting)."),
    ("shape_n_modes", "Number of shape modes", 5, 2, 12, 0, "Shape modes (VAMPIRE)",
     "How many clusters the VAMPIRE shape-mode model uses (re-fits + re-caches)."),
    ("run_tumble_turn_deg", "Run/tumble turn angle (°)", 60.0, 5.0, 175.0, 0, "Motion",
     "Turning angle above which a step counts as a reorientation 'tumble' (run-and-"
     "tumble decomposition / tumble rate)."),
    ("jump_factor", "Jump-step factor (× median)", 5.0, 1.5, 50.0, 1, "Motion",
     "A step longer than this × the median step length is flagged as a tracking jump "
     "(track-quality QC)."),
    ("edge_front_deg", "Front/rear half-cone (°)", 60.0, 10.0, 90.0, 0, "Edge dynamics",
     "Half-angle from the migration direction defining 'front' vs 'rear' edge sectors "
     "(polarity index / rear-retraction fraction)."),
    ("edge_temporal_sigma", "Kymograph time smoothing (σ frames)", 1.0, 0.0, 5.0, 1,
     "Edge dynamics",
     "Gaussian σ (frames) applied along time to the edge-velocity kymograph (0 = none)."),
    ("edge_angular_window", "Kymograph angular window (sectors)", 5.0, 3.0, 15.0, 0,
     "Edge dynamics",
     "Savitzky-Golay window (odd, in sectors) smoothing each frame's boundary radius "
     "around the cell."),
    ("edge_rect_depth_px", "Sampling rectangle depth (px)", 12.0, 2.0, 60.0, 0,
     "Edge ↔ fluorescence sampling",
     "How far each edge-intensity sampling rectangle reaches inward from the boundary."),
    ("edge_rect_width_px", "Sampling rectangle width (px)", 7.0, 2.0, 60.0, 0,
     "Edge ↔ fluorescence sampling",
     "Width of each edge-intensity sampling rectangle along the boundary."),
    ("edge_min_coverage", "Sampling min in-cell coverage", 0.3, 0.0, 1.0, 2,
     "Edge ↔ fluorescence sampling",
     "A sampling rectangle is dropped if less than this fraction of it lies inside the "
     "cell mask."),
    ("cil_window", "CIL speed window (frames)", 3.0, 1.0, 20.0, 0,
     "Contact inhibition (CIL)",
     "± frames around a contact event over which the speed change is measured "
     "(negative = slowing as contact forms)."),
]


def analysis_params(settings=None) -> dict:
    s = settings or QtCore.QSettings("cellscope_analysis", "viewer")
    return {k: float(s.value(f"analysis/{k}", d, type=float))
            for k, _l, d, *_ in ANALYSIS_PARAMS}


def apply_analysis_params(settings=None):
    """Push the configured analysis parameters onto the analysis module globals so
    every computation (comparison + interactive) reads them at call time."""
    from ..analysis import (neighbors, contacts, state, shape_modes, motion,
                            edge_dynamics, edge_intensity, cil)
    p = analysis_params(settings)
    neighbors.DEFAULT_RADIUS_UM = p["nn_radius"]
    contacts.DEFAULT_GAP_PX = p["contact_gap"]
    contacts.EXTENSIVE_FRAC = p["extensive_frac"]
    contacts.MIN_CONTACT_PX = int(p["contact_min_px"])
    state.ROUNDED_AREA_UM2 = p["rounded_area_um2"]
    state.ROUNDED_ECC = p["rounded_ecc"]
    state.MIN_AREA_PX = int(p["state_min_area_px"])
    shape_modes.N_MODES = int(p["shape_n_modes"])
    motion.RUN_TUMBLE_TURN_DEG = p["run_tumble_turn_deg"]
    motion.JUMP_FACTOR = p["jump_factor"]
    edge_dynamics.POLARITY_FRONT_DEG = p["edge_front_deg"]
    edge_dynamics.TEMPORAL_SIGMA = p["edge_temporal_sigma"]
    edge_dynamics.ANGULAR_SG_WINDOW = int(p["edge_angular_window"])
    edge_intensity.DEPTH_PX = int(p["edge_rect_depth_px"])
    edge_intensity.WIDTH_PX = int(p["edge_rect_width_px"])
    edge_intensity.MIN_COVERAGE = p["edge_min_coverage"]
    cil.DEFAULT_WINDOW = int(p["cil_window"])


def analysis_params_tag(settings=None) -> str:
    """Cache-key fragment for the analysis params (only when non-default) so the
    comparison recomputes when they change."""
    p = analysis_params(settings)
    if all(abs(p[k] - d) < 1e-9 for k, _l, d, *_ in ANALYSIS_PARAMS):
        return ""
    return "_p" + "_".join(f"{p[k]:g}" for k, *_ in ANALYSIS_PARAMS)


def corrections_tag(corrections, scale=None):
    """Short stable fingerprint of the project's pre-analysis corrections + manual
    scale overrides, for keying the compute cache (alignment / FOV / pixel-size /
    time-scale changes ⇒ different results)."""
    if not corrections and not (scale and any(scale)):
        return ""
    blob = {"c": corrections or None, "s": list(scale) if scale else None}
    digest = hashlib.md5(json.dumps(blob, sort_keys=True).encode())
    return "_c" + digest.hexdigest()[:6]


def channel_tag(name):
    """Cache-key fragment for a fluor channel: a readable alphanumeric slug **plus** a
    short hash of the raw name, so distinct channels whose alphanumerics coincide
    (e.g. ``Cy5`` vs ``Cy-5``) never collide on the same cache file."""
    if not name:
        return ""
    return "_" + "".join(c for c in name if c.isalnum()) + hashlib.md5(
        name.encode()).hexdigest()[:4]


class ComputeWorker(QtCore.QObject):
    """Runs `compare.build_comparison` off the GUI thread (lag count + optional
    edge↔fluorescence channel); emits per-recording progress, then the result."""
    progress = QtCore.pyqtSignal(int, int)
    done = QtCore.pyqtSignal(object)

    def __init__(self, entries, max_lag=0, piezo_channel=None, corrections=None,
                 scale_override=None, options=None):
        super().__init__()
        self.entries = entries
        self.max_lag = max_lag
        self.piezo_channel = piezo_channel
        self.corrections = corrections or {}
        self.scale_override = scale_override
        self.options = options or {}
        self.cancel = False

    def run(self):
        o = self.options
        try:
            res = compare.build_comparison(
                self.entries, max_lag=self.max_lag,
                piezo_channel=self.piezo_channel, corrections=self.corrections,
                scale_override=self.scale_override,
                with_solidity=o.get("solidity", False),
                with_contacts=o.get("contacts", True),
                with_state_segmented=o.get("state_segmented", True),
                with_edge=o.get("edge_dynamics", False),
                with_cil=o.get("cil", False),
                with_fluor_metrics=o.get("fluor_metrics", False),
                with_shape_modes=o.get("shape_modes", False),
                progress_cb=lambda i, n: (self.progress.emit(i, n)
                                          or not self.cancel))
        except Exception as exc:                          # surface, don't crash
            res = exc
        self.done.emit(res)


class ResultsIOMixin:
    """Save / load the computed comparison results + CSV export (compare_window)."""

    def _save_results(self):
        if self._per_cell is None:
            return
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save comparison results", f"{self.project.name}.cmp",
            "Comparison results (*.cmp)")
        if not fn:
            return
        meta = {"name": self.project.name, "design": self.project.design.to_dict(),
                "excluded": sorted(self.project.excluded),
                "overrides": self.project.overrides}
        compare.save_results(fn, self._per_cell, self._msd, meta, self._autocorr)
        self.status.showMessage(f"Saved comparison results → {fn}", 5000)

    def _load_results(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load comparison results", "", "Comparison results (*.cmp *.pkl)")
        if not fn:
            return
        try:
            blob = compare.load_results(fn)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._apply_loaded_results(blob)
        self.status.showMessage(f"Loaded comparison results from {fn}", 5000)

    def _apply_loaded_results(self, blob):
        """Adopt saved (per_cell, msd, autocorr) + design into the window (no recompute)."""
        per_cell, msd = blob.get("per_cell"), blob.get("msd")
        if per_cell is None or getattr(per_cell, "empty", True):
            QtWidgets.QMessageBox.warning(self, "Empty", "No results in that file.")
            return
        meta = blob.get("meta", {})
        d = meta.get("design")
        if d:
            self.project.design = projmod.Design(d.get("arms", {}), d.get("vehicle"),
                                                 d.get("colors", {}))
        self.project.excluded = set(meta.get("excluded", []))
        self.project.overrides = dict(meta.get("overrides", {}))
        self._refresh_control_combo()
        self._on_done((per_cell, msd, blob.get("autocorr")), cached=True)  # combos + replot

    def _show_multivariate(self):
        if self._per_cell is None:
            return
        pc = self._filtered()
        if pc is None or pc.empty:
            return
        show_multivariate(self, compare.aggregate(pc), self.project.design)

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


def show_multivariate(parent, per_rec, design):
    """Modal table of per-arm PERMANOVA p + leave-one-recording-out AUC."""
    multivariate_dialog(parent, per_rec, design).exec_()


def multivariate_dialog(parent, per_rec, design):
    """Build (don't show) the multivariate-results dialog."""
    rows = compare.multivariate_contrasts(per_rec, arms=design.arms)
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Multivariate phenotype (recording = unit)")
    dlg.resize(580, 360)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.addWidget(QtWidgets.QLabel(
        "PERMANOVA + leave-one-recording-out classifier AUC over <i>all</i> metrics "
        "— detects multivariate separation that single-metric tests can miss "
        "(permutation tests; recording = experimental unit)."))
    cols = ["arm", "contrast", "n ctrl", "n test", "# metrics", "PERMANOVA p", "LORO AUC"]
    keys = ["arm", "contrast", "n_ctrl", "n_test", "n_features", "permanova_p", "loro_auc"]
    tbl = QtWidgets.QTableWidget(len(rows), len(cols))
    tbl.setHorizontalHeaderLabels(cols)
    tbl.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    for ri, r in enumerate(rows):
        for ci, k in enumerate(keys):
            v = r.get(k)
            item = QtWidgets.QTableWidgetItem()
            if isinstance(v, str) or v is None:
                item.setText("" if v is None else v)
            else:
                item.setData(QtCore.Qt.DisplayRole, round(float(v), 4))
            tbl.setItem(ri, ci, item)
    tbl.resizeColumnsToContents()
    lay.addWidget(tbl, 1)
    btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    return dlg


def show_metrics_help(parent):
    """Modal Metrics & methods reference (the comparison column docs + methods)."""
    dlg = QtWidgets.QDialog(parent)
    dlg.setWindowTitle("Metrics & methods reference")
    dlg.resize(680, 680)
    lay = QtWidgets.QVBoxLayout(dlg)
    br = QtWidgets.QTextBrowser()
    br.setHtml(metric_docs.as_html())
    lay.addWidget(br)
    btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
    btns.rejected.connect(dlg.reject)
    lay.addWidget(btns)
    dlg.exec_()


class StatsTablesMixin:
    def _table_filter_note(self):
        """Filter summary for the tables (group-visibility excluded — tables show
        every group); '' when the annotation option is off or nothing is filtered."""
        if getattr(self, "style", None) is None or not self.style.show_filter_note:
            return ""
        return self._filter_note(groups=False)

    def _add_stats_buttons(self, lay):
        """Stats-tab action row: Save plot · Ranked report · Forest · Phenotype map
        (built here to keep compare_window lean)."""
        row = QtWidgets.QHBoxLayout()
        self._save_btn = QtWidgets.QPushButton("Save plot…")
        self._save_btn.clicked.connect(self._save_current_plot)
        row.addWidget(self._save_btn)
        for label, tip, slot in (
                ("Ranked report…", "All group-pair comparisons for the current metric,"
                 " ranked by significance", self._show_ranked_report),
                ("Forest…", "Effect size (Cohen's d ± CI) of every metric for a "
                 "contrast", self._show_forest),
                ("Phenotype map…", "Per-cell 2-D phenotype cloud with per-group "
                 "covariance ellipses", self._show_phenotype_map)):
            b = QtWidgets.QPushButton(label); b.setToolTip(tip)
            b.clicked.connect(slot); row.addWidget(b)
        lay.addLayout(row)

    def _show_forest(self):
        from .forest_plot import ForestPlotDialog
        per_rec = getattr(self, "_stats_per_rec", None)
        if per_rec is None or per_rec.empty:
            QtWidgets.QMessageBox.information(self, "Forest plot",
                                             "Compute the comparison first.")
            return
        d = self.project.design
        conds = compare.order_conditions(per_rec["condition"].unique(),
                                         order=d.condition_order())
        ctrl = next(iter(d.arms.values()))["control"] if d.arms else conds[0]
        ctrl = ctrl if ctrl in conds else conds[0]
        test = next((c for c in conds if c != ctrl), conds[-1])
        ForestPlotDialog(per_rec, conds, ctrl, test, self).exec_()

    def _show_phenotype_map(self):
        from .phenotype_map import PhenotypeMapDialog
        pc = self._filtered() if hasattr(self, "_filtered") else None
        if pc is None or pc.empty:
            QtWidgets.QMessageBox.information(self, "Phenotype map",
                                             "Compute the comparison first.")
            return
        PhenotypeMapDialog(pc, self.project.design, self).exec_()

    def _show_ranked_report(self):
        from .ranked_report import RankedReportDialog
        per_rec = getattr(self, "_stats_per_rec", None)
        metric = self.metric.currentText()
        if per_rec is None or per_rec.empty or not metric:
            QtWidgets.QMessageBox.information(
                self, "Ranked report", "Compute the comparison first.")
            return
        pc = self._filtered() if hasattr(self, "_filtered") else None
        rows = compare.ranked_group_comparisons(per_rec, metric, per_cell=pc)
        if not rows:
            QtWidgets.QMessageBox.information(
                self, "Ranked report", "Need at least two groups with data.")
            return
        RankedReportDialog(metric, rows, self).exec_()

    def _update_stats(self, per_rec, metric):
        self._stats_per_rec = per_rec                 # cache for the ranked report
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
        note = self._table_filter_note()
        if note:
            txt += f"<br><i>filtered: {note}</i>"
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
        self._set_table(self.table, _STAT_COLS, rows)

    def _fill_data(self, per_rec, pc, metric):
        """Per-recording + per-group tables (the Data tab), with unit headers."""
        note = self._table_filter_note()
        if getattr(self, "data_note", None) is not None:
            self.data_note.setText(f"<i>filtered: {note}</i>" if note else "")
            self.data_note.setVisible(bool(note))
        conds = compare.order_conditions(per_rec["condition"].unique(),
                                         order=self.project.design.condition_order())
        u = metric_docs.column_units(metric)
        vh = metric_docs.column_label(metric) + (f" ({u})" if u else "")
        rec_rows = []
        for cond in conds:
            for _, r in per_rec[per_rec["condition"] == cond].iterrows():
                rec_rows.append([str(r["recording"]), cond,
                                 int(r.get("n_cells", 0)), float(r[metric])])
        self._set_table(self.rec_table, ["recording", "group", "n cells", vh], rec_rows)
        summ = {s["group"]: s for s in compare.per_condition_summary(per_rec, metric)}
        unit = f" ({u})" if u else ""
        cond_rows = [[c, summ[c]["n"], summ[c]["mean"], summ[c]["sem"], summ[c]["median"]]
                     for c in conds if c in summ]
        self._set_table(self.cond_table,
                        ["group", "n rec", "mean" + unit, "SEM" + unit, "median" + unit],
                        cond_rows)

    @staticmethod
    def _set_table(table, headers, rows):
        table.setSortingEnabled(False)
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            for ci, v in enumerate(row):
                item = QtWidgets.QTableWidgetItem()
                if isinstance(v, str) or v is None:
                    item.setText("" if v is None else v)
                else:
                    item.setData(QtCore.Qt.DisplayRole, round(float(v), 4))
                table.setItem(ri, ci, item)
        table.setSortingEnabled(True)
        table.resizeColumnsToContents()
