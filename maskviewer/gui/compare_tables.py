"""Stats + data table population for the Comparison window.

Split out of `compare_window.py` (file-size hygiene). `StatsTablesMixin` fills the
right-panel tables from the per-recording table + the project Design: the
per-contrast **Stats** table (KW / Bonferroni / Cohen d / OLS) and the **Data**
tab's per-recording + per-group tables (unit-tagged). GUI-thread only.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from ..analysis import compare, feature_tables, metric_docs

_STAT_COLS = ["arm", "contrast", "n ctrl", "n test", "p", "Bonferroni",
              "Cohen d", "OLS β", "OLS p"]


class StatsTablesMixin:
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
        self._set_table(self.table, _STAT_COLS, rows)

    def _fill_data(self, per_rec, pc, metric):
        """Per-recording + per-group tables (the Data tab), with unit headers."""
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
