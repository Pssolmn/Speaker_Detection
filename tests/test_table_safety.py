"""Regression tests for replacing selected Qt table rows."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem

from src.ui.table_safety import replace_table_rows


class TableSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_selection_is_detached_before_selected_row_is_removed(self):
        table = QTableWidget(12, 2)
        for row in range(table.rowCount()):
            table.setItem(row, 0, QTableWidgetItem(str(row)))
        table.selectRow(9)
        table.setCurrentCell(9, 0)
        state_during_removal = []
        table.model().rowsAboutToBeRemoved.connect(
            lambda *_: state_during_removal.append(
                (table.currentRow(), len(table.selectionModel().selectedIndexes()))
            )
        )

        replace_table_rows(table, 1)

        self.assertEqual(state_during_removal, [(-1, 0)])
        self.assertEqual(table.rowCount(), 1)
        self.assertEqual(table.currentRow(), -1)

    def test_negative_row_count_is_rejected(self):
        with self.assertRaises(ValueError):
            replace_table_rows(QTableWidget(), -1)


if __name__ == "__main__":
    unittest.main()
