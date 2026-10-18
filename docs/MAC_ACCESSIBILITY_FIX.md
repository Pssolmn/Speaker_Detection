# macOS Accessibility ownership guard — 17 October 2026

## What failed

The local runtime is PyQt6 6.11.0 with **Qt 6.11.2**. Native accessibility
traversal of a selected table could crash in `libqcocoa.dylib`, reached from
`NSAccessibility` / `_AXXMIGCopyHierarchy`. It is not a video decoder failure.

Qt's synthesized table rows/cells borrow the parent table's accessibility ID.
The affected cleanup paths delete that ID as if the synthesized element owned
it. Replacing a placeholder with the selected real cell can therefore invalidate
the table's accessibility interface while the hierarchy is being traversed.
The ownership and cleanup paths can be inspected in the primary source:
[Qt 6.11.2 qcocoaaccessibilityelement.mm](https://raw.githubusercontent.com/qt/qtbase/v6.11.2/src/plugins/platforms/cocoa/qcocoaaccessibilityelement.mm)
and its [header](https://raw.githubusercontent.com/qt/qtbase/v6.11.2/src/plugins/platforms/cocoa/qcocoaaccessibilityelement.h).

## Scope of this workaround

- `src/ui/mac_accessibility.py` installs the guard only in native Cocoa processes
  using Qt 6.11.0–6.11.2. The version exercised here is **6.11.2**; the other two
  allowed versions have not been tested locally. Other platforms/backends and
  versions are left untouched.
- `src/ui/native/accessibility_guard.m` checks the class, ivar types, offsets and
  method argument counts before replacing two cleanup implementations inside
  **this process only**. An unexpected ABI refuses installation with an error.
- A synthesized element's borrowed ID is cleared immediately before its original
  destructor. Realized table-cell interfaces are also excluded from Cocoa-array
  cleanup because `QAccessibleTable::childToId`, not the transient native cell,
  owns them. The table's model-change/destructor path still performs the real
  interface cleanup.
- It does not disable accessibility, change accessibility attributes, modify
  system/venv libraries, patch another process, or install/downgrade Qt.
- Both the Workspace and legacy window install the guard before creating tables.
  The native library remains loaded for the process lifetime; there is no Python
  callback from a native object's destructor.

## Build and deployment

The first native launch compiles a small app-owned dylib with the Mac's existing
`/usr/bin/clang` and Foundation framework. This requires Apple's Command Line
Tools. No installation is performed automatically. A build/ABI failure is shown
as an error rather than quietly disabling accessibility.

The result is reused under `data/output/runtime/macos-ax/<source-and-architecture-hash>/`.
Building uses a lock and temporary file followed by atomic replacement. This
folder is runtime cache, not user annotation data. A packaged/hardened app would
need a signed, bundled build instead; packaging is not part of this change.

## Verification and removal criteria

- Synthetic native table control **without** the guard: SIGSEGV, exit 139.
- Same selected-row/clear/repopulate traversal **with** the guard: 30 successful
  scans, 34–142 nodes, report in `data/output/ax-guarded-timer-2026-10-16/`.
- Actual Home/Editor/Dashboard/visual/voice UI on a read-only backup copy:
  24 native accessibility scans, 148–330 nodes, no crash; edit/save/undo,
  decoded video and preserving the Editor draft/playhead also passed.
  Report: `data/output/studio-ax-2026-10-17/report.json`.

These checks use an app-owned Objective-C probe through native accessibility
attributes in the disposable test process, not another app's screen contents.
They reproduce the ownership path but do not certify every assistive technology
or every future Qt/macOS version.

The later MKV test logged Qt `Invalid child in QAccessibleEvent` selection
notifications. Two real crash reports then showed the same path in
`QTableWidget::setRowCount` → `QAbstractItemModel::endRemoveRows` →
`QAccessible::updateAccessibility`. Clearing selection first was insufficient:
the crash occurs in `QAccessibleTable::modelChange`, whose `childToId` cache can
contain an ID already deleted when Cocoa releases a realized cell. The guard now
preserves both placeholders and realized table cells until their owning C++
table removes them. `src/ui/table_safety.py` still clears selected/current
indexes before replacing rows as an additional ordering safeguard. Complete
behavior for every screen reader remains uncertified.

To repeat the guarded test, use new output directories:

```bash
QT_QPA_PLATFORM=cocoa venv/bin/python -m scripts.verify_accessibility data/output/new-ax-check
QT_QPA_PLATFORM=cocoa venv/bin/python -m scripts.verify_studio \
  data/output/workspace-demo data/output/new-native-studio-check --accessibility-probe
```

The deliberate `--unguarded` crash control belongs only in the disposable
synthetic script, never in the user's live project. Do not remove the guard on
the affected version. After adopting an upstream ownership fix, repeat the
synthetic and real-window tests on that exact Qt runtime before retiring it.
