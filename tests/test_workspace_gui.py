"""เปิดหน้าจอใหม่ offscreen และตรวจการไหลของ ID/ชื่อ/worker."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QEventLoop, QTimer, QItemSelectionModel
from PyQt6.QtWidgets import QApplication, QMessageBox

from src.core.models import SubtitleSegment
from src.ui.workspace_window import WorkspaceWindow


class WorkspaceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / "test.mp4"
        source.write_bytes(b"synthetic media")
        self.window = WorkspaceWindow(library_path=self.root / "library.json")
        # unit tests ใช้วิดีโอปลอม: ไม่สกัดเสียงจริง; integration แยกต่างหาก.
        self.wave_patch = patch.object(self.window, "start_waveform")
        self.wave_patch.start()
        self.window.load_workspace(self.root / "workspace", create=True)
        self.window.tabs.setCurrentIndex(1)
        self.store = self.window.store
        self.media = self.store.add_media(source)
        run = self.store.begin_run(self.media, "voice", {})
        self.store.put_observation(identifier="v", media_id=self.media, run_key=run["key"], kind="voice",
            start_ms=0, end_ms=1000, model_key="test", features=[1, 0])
        self.profile = self.store.auto_assign("v", new=True)
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        self.window.profile_kind.setCurrentIndex(2)
        self.window.refresh()

    def tearDown(self):
        self.window.editor.load(None, force=True)
        self.window.close()
        self.app.processEvents()
        self.wave_patch.stop()
        self.temp.cleanup()

    def test_gallery_render_rename_and_manual_subtitle(self):
        self.window.profiles.setCurrentRow(1)
        self.assertEqual(self.window.current_profile()[1], self.profile)
        self.assertEqual(self.window.observations.rowCount(), 1)
        with patch("src.ui.workspace_window.QInputDialog.getText", return_value=("Ruby", True)):
            self.window.rename()
        self.assertEqual(self.window.subtitle_table.item(0, 4).text(), "Ruby")
        self.window.subtitle_table.item(0, 6).setText("manual")
        self.assertEqual(self.window.subtitle_table.item(0, 4).text(), "manual")
        self.window.undo()
        self.assertEqual(self.window.subtitle_table.item(0, 4).text(), "Ruby")
        self.window.show()
        self.app.processEvents()
        self.assertFalse(self.window.grab().isNull())

    def test_worker_completes_and_reenables_edits(self):
        with patch("src.ui.workspace_window.scan_visual") as scan:
            scan.side_effect = lambda *args, **kwargs: kwargs["progress"](1, 1, "done")
            self.window.start_job("visual")
            loop = QEventLoop()
            self.window.worker.finished.connect(loop.quit)
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            self.app.processEvents()
        self.assertIsNone(self.window.worker)
        self.assertTrue(self.window.open_button.isEnabled())
        self.assertFalse(self.window.cancel_button.isEnabled())

    def test_text_time_edit_undo_and_shared_player_survive_tab_switch(self):
        self.window.editor.text.setPlainText("สวัสดี อควา")
        self.window.editor.end.setText("00:00:01,500")
        self.assertTrue(self.window.save_subtitle())
        self.assertEqual(self.store.subtitle(self.media, 1).text, "สวัสดี อควา")
        self.assertEqual(self.window.subtitle_table.item(0, 2).text(), "00:00:01,500")
        with patch.object(self.window.player, "setSource") as source, patch.object(self.window.player, "setPosition") as position:
            self.window.tabs.setCurrentIndex(2)
            self.window.tabs.setCurrentIndex(1)
            self.window.refresh()
            source.assert_not_called()
            position.assert_not_called()
        self.window.undo()
        self.assertEqual(self.store.subtitle(self.media, 1).text, "hello")
        self.assertEqual(self.window.editor.end.text(), "00:00:01,000")

    def test_profile_rename_preserves_draft_and_cue_selection(self):
        self.window.editor.text.setPlainText("ยังพิมพ์ไม่เสร็จ")
        self.window.review_subtitle()
        with patch("src.ui.workspace_window.QInputDialog.getText", return_value=("อควา", True)):
            self.window.rename()
        self.assertEqual(self.window.editor.text.toPlainText(), "ยังพิมพ์ไม่เสร็จ")
        self.assertTrue(self.window.editor.dirty)
        self.assertEqual(self.window._selected_id, 1)
        self.assertEqual(self.window.subtitle_table.item(0, 4).text(), "อควา")

    def test_cancel_navigation_keeps_draft_and_save_moves_to_new_cue(self):
        second = self.store.add_subtitle(self.media, 2000, 3000, "second")
        self.window.refresh_subtitles()
        self.window.editor.text.setPlainText("draft")
        with patch("src.ui.workspace_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            self.window.subtitle_table.selectRow(1)
        self.assertEqual(self.window._selected_id, 1)
        self.assertEqual(self.window.subtitle_table.currentRow(), 0)
        self.assertEqual(self.window.editor.text.toPlainText(), "draft")
        with patch("src.ui.workspace_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Save):
            self.window.subtitle_table.selectRow(1)
        self.assertEqual(self.store.subtitle(self.media, 1).text, "draft")
        self.assertEqual(self.window._selected_id, second)
        self.assertEqual(self.window.subtitle_table.currentRow(), 1)
        self.assertEqual(self.window.editor.text.toPlainText(), "second")

    def test_invalid_time_leaves_editor_and_store_unchanged(self):
        self.window.editor.start.setText("invalid")
        with patch("src.ui.workspace_window.QMessageBox.warning") as warning:
            self.assertFalse(self.window.save_subtitle())
        warning.assert_called_once()
        self.assertEqual(self.store.subtitle(self.media, 1).start_ms, 0)
        self.assertEqual(self.window.editor.start.text(), "invalid")

    def test_follow_playback_never_steals_edit_selection(self):
        self.store.add_subtitle(self.media, 2000, 3000, "second")
        self.window.refresh_subtitles()
        self.window.follow.setChecked(True)
        self.window.editor.text.setPlainText("draft")
        self.window.on_position(2500)
        self.assertIn("second", self.window.caption.text())
        self.assertEqual(self.window._selected_id, 1)
        self.assertEqual(self.window.subtitle_table.currentRow(), 0)
        self.assertEqual(self.window.editor.text.toPlainText(), "draft")

    def test_plain_srt_export_contains_current_text_without_injected_names(self):
        output = self.root / "plain.srt"
        self.store.label_subtitle(self.media, 1, name="Ruby")
        self.window.editor.text.setPlainText("edited")
        with patch("src.ui.workspace_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Save), \
             patch("src.ui.workspace_window.QFileDialog.getSaveFileName", return_value=(str(output), "")):
            self.window.export("plain_srt")
        self.assertIn("edited", output.read_text())
        self.assertNotIn("Ruby", output.read_text())
        self.assertEqual(self.store.rows("SELECT manual_name FROM subtitles")[0]["manual_name"], "Ruby")

    def test_switch_episode_does_not_reuse_editor_or_caption_from_previous_episode(self):
        source = self.root / "second.mp4"
        source.write_bytes(b"different video")
        other = self.store.add_media(source)
        self.store.import_subtitles(other, [SubtitleSegment(1, 0, 1000, "other episode")])
        self.window.refresh()
        self.window.episodes.setCurrentIndex(self.window.episodes.findData(other))
        self.assertEqual(self.window.editor.text.toPlainText(), "other episode")
        self.assertEqual(self.window.media_id, other)
        self.window.on_position(500)
        self.assertIn("other episode", self.window.caption.text())
        self.window.episodes.setCurrentIndex(self.window.episodes.findData(self.media))
        self.assertEqual(self.window.editor.text.toPlainText(), "hello")

    def test_multiselection_is_not_cleared_when_changing_current_cue(self):
        second = self.store.add_subtitle(self.media, 2000, 3000, "second")
        self.window.refresh_subtitles()
        model = self.window.subtitle_table.selectionModel()
        model.select(self.window.subtitle_table.model().index(1, 0),
                     QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.window.subtitle_table.setCurrentCell(1, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.window.select_subtitle()
        self.assertEqual(set(self.window.selected_subtitle_ids()), {1, second})
        self.window.join_subtitles()
        self.assertEqual(self.store.subtitle(self.media, 1).text, "hello\nsecond")

    def test_editor_draft_badge_and_export_discard_do_not_claim_saved_draft(self):
        self.window.editor.text.setPlainText("draft")
        self.assertEqual(self.window.saved_badge.text(), "มีบรรทัดรอบันทึก")
        self.assertTrue(self.window.editor.apply.isEnabled())
        with patch("src.ui.workspace_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.window.resolve_draft())
        self.assertFalse(self.window.editor.dirty)
        self.assertEqual(self.window.saved_badge.text(), "บันทึกในเครื่อง")

    def test_closed_editor_waits_for_waveform_without_destroying_thread(self):
        import time
        from src.ui.waveform_worker import WaveformWorker
        from src.core.control import check_cancel

        def extract(source, path, **kwargs):
            for _ in range(30):
                check_cancel(kwargs["cancel"])
                time.sleep(.002)
            return path

        with patch("src.ui.waveform_worker.extract_audio", side_effect=extract), \
             patch("src.ui.waveform_worker.waveform_peaks", return_value=([.5], 1000)):
            self.window._wave_worker = worker = WaveformWorker(self.media, self.root / "test.mp4", self.root / "wave", parent=self.window)
            worker.finished.connect(self.window.waveform_finished)
            loop = QEventLoop()
            worker.finished.connect(loop.quit)
            worker.start()
            self.window.close()
            QTimer.singleShot(3000, loop.quit)
            loop.exec()
            self.app.processEvents()
        self.assertIsNone(self.window._wave_worker)
        self.assertIsNone(self.window.store)


if __name__ == "__main__":
    unittest.main()
