"""Ranked group-comparison report dialog (Comparison window ▸ Stats).

For the current metric, a sortable table of **every** group-vs-group comparison
ordered by the likelihood of a significant difference (smallest p first), with a
Bonferroni column, effect size and significance stars. Recording = unit
(`compare.ranked_group_comparisons`). Exportable to CSV.
"""
from __future__ import annotations

import csv
import math

from PyQt5 import QtCore, QtWidgets

from ..analysis import metric_docs

_COLS = ["group A", "group B", "n A", "n B", "mean A", "mean B", "p", "Bonferroni",
         "q (FDR)", "Cohen d", "Cohen d 95% CI", "cell-level p", "sig"]
_KEYS = ["group_a", "group_b", "n_a", "n_b", "mean_a", "mean_b",
         "p", "p_bonferroni", "q_fdr", "cohen_d", "cohen_d_lo", "cohen_d_hi",
         "cluster_p"]


def _fmt(v, n=3):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, float):
        return f"{v:.{n}g}"
    return str(v)


class RankedReportDialog(QtWidgets.QDialog):
    def __init__(self, metric, rows, parent=None):
        super().__init__(parent)
        self.metric = metric
        self.rows = rows
        self.setWindowTitle("Ranked group comparisons")
        self.resize(700, 440)
        lay = QtWidgets.QVBoxLayout(self)
        u = metric_docs.column_units(metric)
        name = metric_docs.column_label(metric) + (f" ({u})" if u else "")
        n_tested = sum(1 for r in rows if not _is_nan(r.get("p")))
        head = QtWidgets.QLabel(
            f"<b>{name}</b> — every group pair, ranked by the likelihood of a "
            f"significant difference (smallest p first).<br>Recording = unit · "
            f"Mann-Whitney U · Bonferroni + Benjamini-Hochberg <b>q</b> over "
            f"{n_tested} pairs · Cohen's d ±95% bootstrap CI · <b>cell-level p</b> = "
            f"recording-clustered robust test · ★ p&lt;0.05, ★★★ q&lt;0.05.")
        head.setWordWrap(True)
        lay.addWidget(head)

        table = QtWidgets.QTableWidget(len(rows), len(_COLS))
        table.setHorizontalHeaderLabels(_COLS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for i, r in enumerate(rows):
            ci = ("" if _is_nan(r.get("cohen_d_lo"))
                  else f"[{_fmt(r['cohen_d_lo'], 2)}, {_fmt(r['cohen_d_hi'], 2)}]")
            cells = [r["group_a"], r["group_b"], r["n_a"], r["n_b"],
                     _fmt(r["mean_a"]), _fmt(r["mean_b"]), _fmt(r["p"], 4),
                     _fmt(r["p_bonferroni"], 4), _fmt(r.get("q_fdr"), 4),
                     _fmt(r["cohen_d"]), ci, _fmt(r.get("cluster_p"), 4), _stars(r)]
            for j, c in enumerate(cells):
                table.setItem(i, j, QtWidgets.QTableWidgetItem(str(c)))
        table.resizeColumnsToContents()
        lay.addWidget(table, 1)

        exp = QtWidgets.QPushButton("Export CSV…")
        exp.clicked.connect(self._export)
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(exp)
        row.addStretch(1)
        row.addWidget(bb)
        lay.addLayout(row)

    def _export(self):
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export ranked report", f"ranked_{self.metric}.csv", "CSV (*.csv)")
        if not fn:
            return
        with open(fn, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(_KEYS)
            for r in self.rows:
                w.writerow([r.get(k) for k in _KEYS])


def _is_nan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def _stars(r):
    q, p = r.get("q_fdr"), r.get("p")
    if not _is_nan(q) and q < 0.05:
        return "★★★"
    return "★" if (not _is_nan(p) and p < 0.05) else ""
