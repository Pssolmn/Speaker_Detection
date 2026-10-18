"""ตรวจการต่อ widget/worker แบบ offscreen; ไม่อ้างว่าเป็นการทดสอบ codec ทุกไฟล์."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from src.core.models import AttributionResult, SubtitleSegment
from src.main import SubtitleEditStudio
from src.ui.worker import AnalysisWorker
from src.core.control import check_cancel


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = SubtitleEditStudio()
        self.window.set_segments([SubtitleSegment(7, 1000, 2000, "Hello")])

    def tearDown(self):
        self.window._dirty = False
        self.window.close()
        self.app.processEvents()

    def test_manual_name_survives_analysis_result_and_rerun(self):
        self.window.sub_table.item(0, 5).setText("Ruby")
        self.window.on_result_ready(AttributionResult(7, "Aqua", 0.9, "ACCEPTED"))
        self.assertEqual(self.window.results[7].manual_character, "Ruby")
        self.assertEqual(self.window.sub_table.item(0, 5).text(), "Ruby")
        self.assertEqual(self.window.sub_table.item(0, 4).text(), "Aqua")

    def test_import_srt_and_preview_render(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sub.srt"
            path.write_text("5\n00:00:00,100 --> 00:00:01,000\n[Ruby]: Hello\n", encoding="utf-8")
            self.window.load_subtitles(path)
        self.assertEqual(self.window.sub_table.rowCount(), 1)
        self.assertEqual(self.window.sub_table.item(0, 3).text(), "Ruby")
        self.window.on_preview_ready({"segment_id": 5, "timestamp_ms": 200,
                                      "frame": np.zeros((100, 160, 3), np.uint8),
                                      "boxes": [{"track_id": 1, "box": [10, 10, 30, 40],
                                                 "name": "Ruby", "visual_score": 0.8}]})
        self.window.show()
        self.app.processEvents()
        self.assertFalse(self.window.grab().isNull())

    @patch("src.ui.worker.prepare_audio")
    def test_worker_delivers_signal_and_releases_busy_state(self, prepare):
        prepare.return_value = {"ranges": [], "peaks": [0.0], "duration_ms": 1000, "warning": None}
        worker = AnalysisWorker("prepare", "unused.mp4", wav_path="unused.wav", parent=self.window)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        self.window.start_worker(worker)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        self.app.processEvents()
        self.assertIsNone(self.window.worker)
        self.assertEqual(self.window.audio["ranges"], [])
        self.assertTrue(self.window.btn_open.isEnabled())

    @patch("src.ui.worker.prepare_audio")
    def test_cancel_keeps_completed_results_and_finishes_thread(self, prepare):
        import time

        def cancellable_work(video, wav, cancel):
            for _ in range(100):
                check_cancel(cancel)
                time.sleep(0.002)
            return {"ranges": [], "peaks": [], "duration_ms": 0, "warning": None}

        prepare.side_effect = cancellable_work
        self.window.on_result_ready(AttributionResult(7, "UNKNOWN", 0.2, "UNKNOWN", manual_character="Ruby"))
        worker = AnalysisWorker("prepare", "unused.mp4", wav_path="unused.wav", parent=self.window)
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        self.window.start_worker(worker)
        QTimer.singleShot(10, self.window.cancel_analysis)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        self.app.processEvents()
        self.assertIsNone(self.window.worker)
        self.assertEqual(self.window.results[7].manual_character, "Ruby")
        self.assertIn("Cancelled", self.window.progress_label.text())
