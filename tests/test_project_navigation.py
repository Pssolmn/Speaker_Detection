"""Home / เมนู / การแยก player และการลบแบบกู้คืนได้ (mock ถังขยะจริง)."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PyQt6.QtCore import Qt, QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QToolButton
from PyQt6.QtMultimedia import QMediaPlayer
from src.core.models import SubtitleSegment
from src.ui.workspace_window import WorkspaceWindow
from src.ui.project_dialog import NewProjectDialog
from src.workspace.library import ProjectLibrary


class ProjectNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.window = WorkspaceWindow(library_path=self.root / "library.json")
        self.wave_patch = patch.object(self.window, "start_waveform")
        self.wave_patch.start()
        self.window.load_workspace(self.root / "project", create=True)
        self.store = self.window.store

    def tearDown(self):
        self.window.editor.load(None, force=True)
        self.window.close()
        self.app.processEvents()
        self.wave_patch.stop()
        self.temp.cleanup()

    def add_media(self):
        source = self.root / "test.mp4"
        source.write_bytes(b"synthetic video")
        media = self.store.add_media(source)
        self.store.import_subtitles(media, [SubtitleSegment(1, 0, 1000, "draft source")])
        run = self.store.begin_run(media, "voice", {})
        self.store.put_observation(identifier="voice", media_id=media, run_key=run["key"], kind="voice",
                                   start_ms=100, end_ms=900, model_key="test", features=[1, 0])
        profile = self.store.auto_assign("voice", new=True)
        self.window.refresh()
        return media, profile

    def test_home_is_default_and_does_not_load_video_or_waveform(self):
        self.add_media()
        self.assertEqual(self.window.tabs.currentIndex(), 0)
        self.assertTrue(self.window.player.source().isEmpty())
        self.assertIsNone(self.window._wave_worker)
        self.assertEqual(self.window.projects.count(), 1)
        self.assertFalse(self.window.file_menu_bar.isNativeMenuBar())

    def test_three_pages_do_not_show_each_others_tools(self):
        self.add_media()
        self.window.show()
        self.assertTrue(self.window.file_menu_bar.isVisible())
        self.window.tabs.setCurrentIndex(1)
        self.app.processEvents()
        self.assertTrue(self.window.editor.isVisible())
        self.assertFalse(self.window.profiles.isVisible())
        self.assertFalse(self.window.projects.isVisible())
        self.window.tabs.setCurrentIndex(2)
        self.assertFalse(self.window.editor.isVisible())
        self.assertTrue(self.window.dashboard.isVisible())
        self.window.profile_kind.setCurrentIndex(1)
        self.assertTrue(self.window.profiles.isVisible())
        self.assertFalse(self.window.waveform_widget.isVisible())
        self.assertIsNot(self.window.player, self.window.review_player)

    def test_manager_playback_does_not_change_editor_media_selection_or_draft(self):
        media, profile = self.add_media()
        self.window.tabs.setCurrentIndex(1)
        self.window.editor.text.setPlainText("ยังพิมพ์ไม่เสร็จ")
        self.window.profile_kind.setCurrentIndex(2)
        self.window.profiles.setCurrentRow(1)
        self.window.observations.selectRow(0)
        with patch.object(self.window.player, "setPosition") as editor_seek, \
             patch.object(self.window.player, "setSource") as editor_source, \
             patch.object(self.window.review_player, "setSource") as review_source, \
             patch.object(self.window.review_player, "setPosition") as review_seek, \
             patch.object(self.window.review_player, "play"):
            self.window.play_observation()
            self.window.review_ready(QMediaPlayer.MediaStatus.LoadedMedia)
            self.window.on_review_position(400)
            review_source.assert_called_once()
            review_seek.assert_called_once_with(100)
            editor_seek.assert_not_called()
            editor_source.assert_not_called()
        self.window.tabs.setCurrentIndex(1)
        self.assertEqual(self.window.media_id, media)
        self.assertEqual(self.window._selected_id, 1)
        self.assertEqual(self.window.editor.text.toPlainText(), "ยังพิมพ์ไม่เสร็จ")

    def test_hidden_review_does_not_autoplay_when_loading_finishes(self):
        self.window.tabs.setCurrentIndex(2)
        self.window._review_pending, self.window._review_autoplay = 100, True
        self.window.tabs.setCurrentIndex(0)
        with patch.object(self.window.review_player, "play") as play:
            self.window.review_ready(QMediaPlayer.MediaStatus.LoadedMedia)
            play.assert_not_called()

    def test_changing_visual_voice_page_cancels_old_review_autoplay(self):
        self.window.tabs.setCurrentIndex(2)
        self.window._review_pending, self.window._review_autoplay = 100, True
        with patch.object(self.window.review_player, "pause") as pause:
            self.window.profile_kind.setCurrentIndex(2)
            pause.assert_called_once()
        self.assertIsNone(self.window._review_pending)
        self.assertFalse(self.window._review_autoplay)

    def test_manager_filters_visual_and_voice_groups(self):
        _, voice = self.add_media()
        visual = self.store.create_profile("visual", "Aqua")
        self.window.show_empty.setChecked(True)
        self.window.refresh()
        self.assertEqual(self.window.profiles.count(), 2)
        self.assertEqual(self.window.profiles.item(1).data(Qt.ItemDataRole.UserRole), ("visual", visual))
        self.window.profile_kind.setCurrentIndex(2)
        self.assertEqual(self.window.profiles.count(), 2)
        self.assertEqual(self.window.profiles.item(1).data(Qt.ItemDataRole.UserRole), ("voice", voice))

    def test_home_rename_changes_name_not_path(self):
        with patch("src.ui.project_navigation.QInputDialog.getText", return_value=("My Series", True)):
            self.window.rename_project()
        self.assertEqual(self.store.project_name(), "My Series")
        self.assertEqual(self.store.root, self.root / "project")
        self.assertEqual(self.window.library.entries()[0]["name"], "My Series")

    def test_forget_requires_confirmation_and_preserves_files(self):
        with patch("src.ui.project_navigation.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            self.window.forget_project()
        self.assertEqual(len(self.window.library.entries()), 1)
        with patch("src.ui.project_navigation.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window.forget_project()
        self.assertEqual(self.window.library.entries(), [])
        self.assertTrue((self.root / "project" / "workspace.sqlite3").exists())
        self.assertIsNone(self.window.store)

    def test_trash_confirmation_targets_only_selected_project_and_no_permanent_fallback(self):
        with patch("src.ui.project_navigation.QFile.moveToTrash", return_value=(False, "")) as trash, \
             patch("src.ui.project_navigation.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            self.window.trash_project()
            trash.assert_not_called()
        with patch("src.ui.project_navigation.QFile.moveToTrash", return_value=(False, "")) as trash, \
             patch("src.ui.project_navigation.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            with self.assertRaises(OSError):
                self.window.trash_project()
            trash.assert_called_once_with(str(self.root / "project"))
        self.assertTrue((self.root / "project" / "workspace.sqlite3").exists())
        self.assertEqual(len(self.window.library.entries()), 1)

    def test_new_project_dialog_validates_location_and_video_before_subtitles(self):
        dialog = NewProjectDialog(self.window)
        dialog.name.setText("../bad")
        dialog.location.setText(str(self.root))
        with self.assertRaises(ValueError):
            dialog.values()
        dialog.name.setText("new")
        self.assertEqual(dialog.values(), (self.root / "new", None, None))
        dialog.subtitle.setText("test.srt")
        with self.assertRaises(ValueError):
            dialog.values()

    def test_setup_worker_imports_video_and_srt_in_home(self):
        source = self.root / "video.mp4"
        source.write_bytes(b"video")
        subtitles = self.root / "subtitle.srt"
        subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")
        self.window.start_job("setup", str(source), subtitle_path=str(subtitles))
        loop = QEventLoop()
        self.window.worker.finished.connect(loop.quit)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        self.app.processEvents()
        self.assertIsNone(self.window.worker)
        self.assertEqual(self.window.tabs.currentIndex(), 0)
        self.assertEqual(self.store.subtitle(self.window.media_id, 1).text, "hello")

    def test_icon_buttons_have_accessible_names_and_secondary_commands_live_in_menus(self):
        for button in self.window.findChildren(QToolButton):
            # Qt also creates private tab-scroll buttons; check our own controls.
            if button.property("studioTool"):
                self.assertTrue(button.accessibleName() or button.text())
        self.assertTrue(any("แยก" in item.text() for item in self.window.subtitle_menu.actions()))
        self.assertTrue(any("รวม" in item.text() for item in self.window.profile_menu.actions()))

    def test_library_deduplicates_and_does_not_overwrite_broken_catalog(self):
        self.window.library.register(self.store.root, "second name")
        self.assertEqual(len(self.window.library.entries()), 1)
        broken = self.root / "broken.json"
        broken.write_text('{"version":99}', encoding="utf-8")
        library = ProjectLibrary(broken)
        with self.assertRaises(ValueError):
            library.register(self.store.root, "not saved")
        self.assertEqual(json.loads(broken.read_text())["version"], 99)


if __name__ == "__main__":
    unittest.main()
