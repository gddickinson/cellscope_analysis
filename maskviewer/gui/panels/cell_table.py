"""Cell-table panel — the per-cell summary as a sortable, clickable table.

Shows `exporters.per_cell_table` (track length + shape + motion aggregates) for
every cell; click a column header to sort, click a row to select that cell in the
view. Lazy compute (one regionprops pass), and a CSV export of exactly this table.
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from ...analysis import exporters, lineage
from ..task_runner import AsyncComputeMixin


class CellTablePanel(AsyncComputeMixin, QtWidgets.QWidget):
    cellSelected = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels = None
        self._um = None
        self._dt = None
        self._df = None
        self._divisions = []

        self.title = QtWidgets.QLabel("Per-cell table")
        self.title.setStyleSheet("font-weight: bold;")
        self.compute_btn = QtWidgets.QPushButton("Compute table")
        self.compute_btn.setToolTip("Measure every cell (one pass) → sortable table")
        self.compute_btn.clicked.connect(self._compute)
        self.export_btn = QtWidgets.QPushButton("Export CSV…")
        self.export_btn.setToolTip("Save this per-cell table as CSV")
        self.export_btn.clicked.connect(self._export)
        self.export_btn.setEnabled(False)
        self.table = QtWidgets.QTableWidget()
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.cellClicked.connect(self._row_clicked)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(self.title)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.compute_btn)
        row.addWidget(self.export_btn)
        lay.addLayout(row)
        lay.addWidget(self.table, 1)

    # -- public ----------------------------------------------------------
    def set_recording(self, labels, um_per_px=None, dt_min=None, divisions=None):
        self._labels, self._um, self._dt = labels, um_per_px, dt_min
        self._divisions = divisions or []
        self._df = None
        self.table.setRowCount(0)
        self.export_btn.setEnabled(False)
        self.title.setText("Per-cell table — click Compute")

    def select_in_table(self, cid):
        """Highlight the row for ``cid`` (view → table sync) without re-emitting."""
        if self._df is None:
            return
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and int(float(it.text())) == cid:
                self.table.blockSignals(True)
                self.table.selectRow(r)
                self.table.blockSignals(False)
                return

    # -- internal --------------------------------------------------------
    def _compute(self):
        if self._labels is None:
            return
        self._dispatch("Per-cell table", self._work, self._apply)

    def _work(self, progress_cb):
        return exporters.per_cell_table(self._labels, self._um, self._dt,
                                        progress_cb=progress_cb)

    def _apply(self, df):
        self._df = df
        self._add_division_columns()
        self._fill()
        self.export_btn.setEnabled(True)
        self.title.setText(f"Per-cell table — {len(self._df)} cells")

    def _add_division_columns(self):
        """Insert parent / daughters columns (label IDs) from the divisions
        inferred from the masks — a cell with a `parent` is a child; a cell with
        `daughters` is a parent. Only added when a real relationship exists."""
        if self._df is None or self._df.empty or not self._divisions:
            return
        present = {int(c) for c in self._df["cell_id"]}     # only real, in-table cells
        parents, daughters = [], []
        for cid in self._df["cell_id"]:
            p, d = lineage.relatives(self._divisions, int(cid))
            p = [x for x in p if x in present]
            d = [x for x in d if x in present]
            parents.append(p[0] if p else "")
            daughters.append(", ".join(map(str, d)) if d else "")
        if not any(parents) and not any(daughters):          # nothing real → no columns
            return
        self._df.insert(1, "parent", parents)
        self._df.insert(2, "daughters", daughters)

    def _fill(self):
        df = self._df
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setColumnCount(len(df.columns))
        self.table.setRowCount(len(df))
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for r in range(len(df)):
            for c, col in enumerate(df.columns):
                v = df.iloc[r, c]
                item = QtWidgets.QTableWidgetItem()
                try:
                    item.setData(QtCore.Qt.DisplayRole, float(v)
                                 if col != "cell_id" else int(v))
                except (TypeError, ValueError):
                    item.setText(str(v))
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()

    def _row_clicked(self, row, _col):
        it = self.table.item(row, 0)
        if it is not None:
            try:
                self.cellSelected.emit(int(float(it.text())))
            except ValueError:
                pass

    def _export(self):
        if self._df is None:
            return
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export per-cell CSV", "per_cell.csv", "CSV (*.csv)")
        if fn:
            self._df.to_csv(fn, index=False)
