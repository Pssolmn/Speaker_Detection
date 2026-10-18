"""ทดสอบ Home / Editor / Manager บนสำเนา Workspace — ไม่แก้งานจริงของผู้ใช้.

สร้าง screenshot และรายงานในโฟลเดอร์ใหม่; playback ปิดเสียงเพื่อทดสอบเวลา
ไม่อ้างว่าได้ตรวจคุณภาพเสียงผ่านลำโพงหรือความแม่นยำของ AI.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("output", help="new directory only")
    parser.add_argument("--accessibility-probe", action="store_true",
                        help="macOS only: inspect native accessibility on this test process")
    args = parser.parse_args()
    original, output = Path(args.workspace).resolve(), Path(args.output).resolve()
    if output.exists():
        raise FileExistsError("Choose a new output directory")
    output.mkdir(parents=True)
    snapshot = output / "workspace-copy"
    snapshot.mkdir()
    # SQLite backup จับ snapshot ที่สอดคล้องกันแม้ต้นทางอยู่ใน WAL mode.
    with sqlite3.connect((original / "workspace.sqlite3").as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(snapshot / "workspace.sqlite3") as destination:
            source.backup(destination)
    if (original / "evidence").is_dir():
        shutil.copytree(original / "evidence", snapshot / "evidence")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import Qt, QEventLoop, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication
    from src.ui.workspace_window import WorkspaceWindow

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)

    def wait_for(predicate, timeout=15000):
        if predicate():
            return
        loop, timer = QEventLoop(), QTimer()
        timer.setInterval(25)
        timer.timeout.connect(lambda: loop.quit() if predicate() else None)
        timer.start()
        QTimer.singleShot(timeout, loop.quit)
        loop.exec()
        timer.stop()
        if not predicate():
            raise TimeoutError("UI integration condition not met")

    window = WorkspaceWindow(library_path=output / "library.json")
    window.audio_output.setMuted(True)
    window.review_audio.setMuted(True)
    report = {"original": str(original), "test_copy": str(snapshot), "muted": True,
              "platform": app.platformName(), "screenshots": []}
    if args.accessibility_probe:
        import ctypes
        import subprocess
        if app.platformName() != "cocoa":
            raise ValueError("Accessibility probe requires native macOS/Cocoa")
        library = output / "ax_probe.dylib"
        subprocess.run(["/usr/bin/clang", "-dynamiclib", "-fno-objc-arc", "-framework", "AppKit",
                        str(Path(__file__).with_name("native") / "ax_probe.m"), "-o", str(library)],
                       check=True, capture_output=True)
        probe = ctypes.CDLL(str(library))
        probe.studio_ax_probe.restype = ctypes.c_ulong
        probe.studio_ax_probe.argtypes = []
        report["accessibility_guard"] = window.accessibility_status

    def screenshot(name):
        app.processEvents()
        if not window.grab().save(str(output / name)):
            raise OSError("Cannot save screenshot")
        report["screenshots"].append(name)

    try:
        window.load_workspace(snapshot)
        # จอ Mac อาจจำกัดความสูงหน้าต่าง ใช้ขนาดที่มีจริง ไม่บังคับเลยขอบจอ.
        available = app.primaryScreen().availableGeometry()
        requested = (1280, 800)
        if app.platformName() == "offscreen":
            window.resize(*requested)
        else:
            window.resize(*(min(value, limit) for value, limit in zip(
                requested, (available.width(), max(600, available.height() - 40)))))
        window.show()
        app.processEvents()
        menu = window.file_menu_bar
        report["menu_bar"] = {"native": menu.isNativeMenuBar(), "visible": menu.isVisible(),
                              "size": [menu.width(), menu.height()],
                              "actions": [action.text() for action in menu.actions()]}
        print(json.dumps(report["menu_bar"], ensure_ascii=False))
        assert not menu.isNativeMenuBar() and menu.isVisible()
        file_action = menu.actions()[0]
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=menu.actionGeometry(file_action).center())
        app.processEvents()
        assert file_action.menu().isVisible()
        assert file_action.menu().grab().save(str(output / "file-menu.png"))
        file_action.menu().hide()
        report["file_menu_opens"] = True
        assert window.tabs.currentIndex() == 0
        assert window.player.source().isEmpty() and window._wave_worker is None
        report["home_lazy_media"] = True
        screenshot("home.png")
        from src.ui.project_dialog import NewProjectDialog
        dialog = NewProjectDialog(window)
        dialog.show()
        app.processEvents()
        assert dialog.grab().save(str(output / "new-project.png"))
        dialog.close()
        report["size"] = [window.width(), window.height()]
        window.tabs.setCurrentIndex(1)
        wait_for(lambda: window.player.duration() > 0 and window._wave_worker is None)
        if not window.waveform_widget.peaks:
            raise RuntimeError("Waveform was not loaded")
        report["duration_ms"] = window.player.duration()
        report["waveform_peaks"] = len(window.waveform_widget.peaks)
        row = next((index for index, item in enumerate(window._segments) if item.start_ms >= 18000), 0)
        window.subtitle_table.selectRow(row)
        segment = window._segments[row]
        window.play_subtitle()
        wait_for(lambda: window.player.position() >= segment.start_ms + 100
                 and window.video.videoSink().videoFrame().isValid())
        window.player.pause()
        frame = window.video.videoSink().videoFrame().toImage()
        assert not frame.isNull()
        frame.save(str(output / "decoded-frame.png"))
        report["decoded_frame"] = [frame.width(), frame.height()]
        position, selected, source_url = window.player.position(), window._selected_id, window.player.source()
        before = window.store.subtitle(window.media_id, selected)
        window.editor.text.setPlainText(before.text + "\n[ทดสอบบนสำเนาเท่านั้น]")
        window.review_subtitle()
        assert window.tabs.currentIndex() == 2
        # ตัวอย่างเสียง/ภาพใช้ player แยก ไม่ seek หรือทิ้ง draft ในหน้าแก้ซับ.
        if not window.selected_observations():
            window.profiles.setCurrentRow(1)
            window.observations.selectRow(0)
        observation = window.selected_observations()[0]
        window.play_observation()
        wait_for(lambda: window.review_player.position() >= observation["start_ms"] + 100
                 and window.review_video.videoSink().videoFrame().isValid())
        window.review_player.pause()
        report["review_position_ms"] = window.review_player.position()
        screenshot("manager-voice.png")
        window.profile_kind.setCurrentIndex(1)
        window.profiles.setCurrentRow(1)
        window.observations.selectRow(0)
        screenshot("manager-visual.png")
        window.tabs.setCurrentIndex(1)
        app.processEvents()
        assert window.player.position() == position and window.player.source() == source_url
        assert window._selected_id == selected
        assert window.editor.text.toPlainText().endswith("[ทดสอบบนสำเนาเท่านั้น]")
        report["editor_playhead_ms"] = position
        report["tab_switch_preserves_playhead"] = True
        report["manager_preserves_editor_draft"] = True

        assert window.save_subtitle()
        assert window.store.subtitle(window.media_id, selected).text.endswith("[ทดสอบบนสำเนาเท่านั้น]")
        window.undo()
        assert window.store.subtitle(window.media_id, selected) == before
        report["edit_save_undo"] = True
        report["integrity"] = window.store.db.execute("PRAGMA integrity_check").fetchone()[0]
        report["foreign_key_errors"] = window.store.rows("PRAGMA foreign_key_check")

        screenshot("editor.png")
        if args.accessibility_probe:
            counts = []
            for iteration in range(24):
                # Includes selected table rows, synthetic placeholders, refresh
                # and tab destruction/hiding — the original crash's ownership path.
                window.tabs.setCurrentIndex(1 if iteration % 2 else 2)
                window.profile_kind.setCurrentIndex(iteration % 3)
                window.subtitle_table.selectRow(iteration % len(window._segments))
                window.refresh()
                QTest.qWait(100)
                counts.append(probe.studio_ax_probe())
            assert min(counts) > 20
            report["accessibility_scans"] = counts
            window.tabs.setCurrentIndex(1)
        for width, height in ((1440, 900), (1280, 800)):
            window.resize(width, height)
            app.processEvents()
            actual = [window.width(), window.height()]
            report[f"size_{width}"] = actual
            if app.platformName() == "offscreen" and actual != [width, height]:
                raise AssertionError(f"Layout does not fit {width}x{height}: {actual}")
            screenshot(f"editor-{width}.png")
    finally:
        window.editor.load(None, force=True)
        window.close()
        wait_for(lambda: window.store is None)
        app.processEvents()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
