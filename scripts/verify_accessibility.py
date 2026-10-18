"""Exercise native AX on synthetic tables only; --unguarded is a crash control."""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess

from PyQt6.QtCore import QEventLoop, QTimer, Qt, qVersion
from PyQt6.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QAbstractItemView
from src.ui.mac_accessibility import install_guard
from src.ui.table_safety import replace_table_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    parser.add_argument("--unguarded", action="store_true")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).with_name("native") / "ax_probe.m"
    probe_file = output / "ax_probe.dylib"
    subprocess.run(["/usr/bin/clang", "-dynamiclib", "-fno-objc-arc", "-framework", "AppKit",
                    str(source), "-o", str(probe_file)], check=True, capture_output=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    status = "unguarded-control" if args.unguarded else install_guard()
    print("Guard: " + status, flush=True)
    probe = ctypes.CDLL(str(probe_file))
    probe.studio_ax_probe.restype = ctypes.c_ulong
    probe.studio_ax_probe.argtypes = []
    guard = None
    if not args.unguarded:
        from src.ui import mac_accessibility
        guard = mac_accessibility._library
        guard.studio_ax_guard_preserved_borrowed.restype = ctypes.c_uint64
        guard.studio_ax_guard_preserved_cells.restype = ctypes.c_uint64
    table = QTableWidget(12, 4)
    table.setWindowTitle("Speaker Studio — disposable accessibility check")
    table.resize(720, 400)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    counts = []
    for iteration in range(30):
        table.clearContents()
        # Row 9 reproduces the real crash: it used to remain selected while
        # setRowCount removed it and Cocoa handled SelectionRemove too late.
        replace_table_rows(table, 1 if iteration % 3 == 0 else 12)
        for row in range(table.rowCount()):
            for column in range(4):
                table.setItem(row, column, QTableWidgetItem(f"cue {row} / field {column}"))
        table.selectRow(9 if table.rowCount() > 9 else 0)
        table.show()
        loop, tick = QEventLoop(), QTimer()
        tick.setInterval(200)
        tick.timeout.connect(loop.quit)
        tick.start()
        loop.exec()
        tick.stop()
        counts.append(probe.studio_ax_probe())
        print(f"AX scan {iteration + 1}: {counts[-1]} nodes", flush=True)
        assert table.item(0, 0).text() == "cue 0 / field 0"
    table.close()
    app.processEvents()
    assert min(counts) > 8, "AX traversal did not reach the table"
    preserved = ({"borrowed": guard.studio_ax_guard_preserved_borrowed(),
                  "cells": guard.studio_ax_guard_preserved_cells()} if guard else {})
    if guard:
        assert preserved["cells"] > 0, "test did not exercise realized Cocoa table-cell cleanup"
    report = {"qt": qVersion(), "guard": status, "cycles": len(counts), "nodes": counts,
              "preserved": preserved}
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(report)


if __name__ == "__main__":
    main()
