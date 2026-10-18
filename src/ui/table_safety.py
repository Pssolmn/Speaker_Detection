"""Safe replacement of ``QTableWidget`` rows on macOS.

Qt 6.11 can ask Accessibility to remove a selected table child after that
child has already disappeared from the model.  On Cocoa that stale child can
crash inside ``QAccessible::updateAccessibility``.  Always detach the current
selection while the old rows still exist, then resize the table.
"""

from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWidgets import QTableWidget


def replace_table_rows(table: QTableWidget, count: int) -> None:
    """Set a table's row count without leaving Accessibility a stale child.

    Callers that want to preserve a logical selection should remember its ID
    before this call and select the matching new row after repopulating it.
    """
    if count < 0:
        raise ValueError("table row count must not be negative")
    with QSignalBlocker(table):
        selection = table.selectionModel()
        if selection is not None:
            # ``clear()`` removes both selected indexes and the current index.
            # Crucially this happens before QTableWidget removes any row.
            selection.clear()
        table.setRowCount(count)
