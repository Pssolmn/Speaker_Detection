"""ลอง GUI/decoder/worker กับไฟล์จริงและบันทึก screenshot โดยไม่แก้ input.

รันจาก root: QT_QPA_PLATFORM=offscreen venv/bin/python -m scripts.verify_local_demo
  --video ... --results ... --output ...png
"""

import argparse
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from src.main import SubtitleEditStudio


def wait_worker(window, timeout_ms=45000):
    """ใช้ event loop เพื่อให้ UI รับ signal ระหว่างรอ ไม่ใช้ sleep บล็อก UI"""
    if window.worker is None:
        return
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    window.worker.finished.connect(loop.quit)
    timer.start(timeout_ms)
    loop.exec()
    timer.stop()
    QApplication.processEvents()
    if window.worker is not None:
        window.cancel_analysis()
        raise TimeoutError("GUI worker exceeded smoke-test timeout")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--analyze-selected", action="store_true", help="Run the real analysis worker on the first row")
    args = parser.parse_args()
    app = QApplication([])
    window = SubtitleEditStudio()
    window.show()
    errors = []
    window.player.errorOccurred.connect(lambda error, message: errors.append(message))
    # เปลี่ยน error dialog เป็น exception ที่ตรวจจาก command line ได้
    window.on_worker_failed = errors.append
    try:
        window.load_video(args.video)
        wait_worker(window)
        window.load_subtitles(args.results)
        window.sub_table.selectRow(0)
        # ตรวจว่าตัวเล่นเดินเวลาได้จริง แล้วหยุดก่อนทำ preview
        before = window.player.position()
        window.player.play()
        loop = QEventLoop()
        QTimer.singleShot(1200, loop.quit)
        loop.exec()
        window.player.pause()
        after = window.player.position()
        if after <= before:
            raise RuntimeError(f"Player did not advance: {before} -> {after}")
        window.preview_frame()
        wait_worker(window)
        if errors:
            raise RuntimeError("; ".join(errors))
        if window.preview_widget.image is None:
            raise RuntimeError("No real preview image received")
        if args.analyze_selected:
            window.run_speaker_attribution(selected_only=True)
            wait_worker(window)
            result = window.results[window.segments[0].id]
            if result.status == "ERROR" or errors:
                raise RuntimeError(f"Analysis worker failed: {result.evidence}")
            print(f"Real analysis worker: segment {result.segment_id} -> {result.status}")
        app.processEvents()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.output)):
            raise OSError("Cannot save GUI screenshot")
        print(f"GUI OK: {len(window.segments)} rows; playback {before}->{after} ms; "
              f"preview {len(window.preview_widget.boxes)} faces; audio={window.audio['method']}")
        print(args.output.resolve())
    finally:
        window._dirty = False
        if window.worker is not None:
            window.cancel_analysis()
            wait_worker(window)
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
