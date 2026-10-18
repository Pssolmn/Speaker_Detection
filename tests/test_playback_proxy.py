import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QSignalBlocker, QUrl
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication
from src.core.control import AnalysisCancelled
from src.ui.playback_proxy import prepare_proxy, cached_proxy, cache_directory
from src.ui.workspace_window import WorkspaceWindow
from src.workspace.store import fingerprint


class PlaybackCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.mkv"
        self.source.write_bytes(b"original")
        self.digest = fingerprint(self.source)
        self.info = {"format": {"duration": "10"}, "streams": [
            {"codec_type": "video", "codec_name": "h264"}, {"codec_type": "audio", "codec_name": "aac"}]}

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        commands = []
        def ffmpeg(command, *args):
            commands.append(command)
            Path(command[-1]).write_bytes(b"preview")
        with patch("src.ui.playback_proxy.probe", return_value=self.info), \
             patch("src.ui.playback_proxy.run_process", side_effect=ffmpeg):
            result = prepare_proxy(self.root, self.source, self.digest)
        return result, commands

    def test_build_and_cache_hit_preserve_source(self):
        result, commands = self.build()
        self.assertEqual(self.source.read_bytes(), b"original")
        self.assertEqual(cached_proxy(self.root, self.source, self.digest), result)
        self.assertIn("pcm_s16le", commands[0])
        self.assertIn("0:a?", commands[0])
        self.assertIn("copy", commands[0])
        with patch("src.ui.playback_proxy.run_process") as process:
            self.assertEqual(prepare_proxy(self.root, self.source, self.digest), result)
            process.assert_not_called()

    def test_changed_source_or_truncated_cache_is_not_reused(self):
        result, _ = self.build()
        result.write_bytes(b"bad")
        self.assertIsNone(cached_proxy(self.root, self.source, self.digest))
        self.build()
        self.source.write_bytes(b"changed input")
        self.assertIsNone(cached_proxy(self.root, self.source, self.digest))
        with self.assertRaises(ValueError):
            prepare_proxy(self.root, self.source, self.digest)

    def test_cancel_and_failure_do_not_publish_ready(self):
        with self.assertRaises(AnalysisCancelled):
            prepare_proxy(self.root, self.source, self.digest, cancel=lambda: True)
        with patch("src.ui.playback_proxy.probe", return_value=self.info), \
             patch("src.ui.playback_proxy.run_process", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                prepare_proxy(self.root, self.source, self.digest)
        self.assertFalse((cache_directory(self.root, self.digest) / "ready.json").exists())
        self.assertEqual(self.source.read_bytes(), b"original")

    def test_duration_mismatch_is_rejected(self):
        for duration in ("12", "nan", "inf", "0"):
            with self.subTest(duration=duration):
                wrong = {**self.info, "format": {"duration": duration}}
                with patch("src.ui.playback_proxy.probe", side_effect=[self.info, wrong]), \
                     patch("src.ui.playback_proxy.run_process", side_effect=lambda command, *args: Path(command[-1]).write_bytes(b"bad")):
                    with self.assertRaises(ValueError):
                        prepare_proxy(self.root, self.source, self.digest)
                self.assertIsNone(cached_proxy(self.root, self.source, self.digest))


class PlaybackUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = WorkspaceWindow(library_path=self.root / "library.json")
        self.window.load_workspace(self.root / "work", create=True)
        self.source = self.root / "source.mkv"
        self.source.write_bytes(b"fake")
        self.media = self.window.store.add_media(self.source)
        self.window.refresh()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def test_auto_prepare_once_and_explicit_retry(self):
        self.window.tabs.setCurrentIndex(2)
        with patch.object(self.window, "start_job") as start:
            self.window.prepare_playback(automatic=True)
            self.window.prepare_playback(automatic=True)
            start.assert_called_once_with("proxy", self.media)
            self.window.prepare_playback()
            self.assertEqual(start.call_count, 2)

    def test_proxy_is_used_for_playback_only_and_can_be_disabled(self):
        proxy = self.root / "preview.mov"
        with patch("src.ui.playback_proxy.cached_proxy", return_value=proxy):
            self.assertEqual(self.window.playback_path(self.source), proxy)
            self.assertEqual(self.window.store.media_path(self.media), self.source.resolve())
            with QSignalBlocker(self.window.compatibility):
                self.window.compatibility.setChecked(False)
            self.assertEqual(self.window.playback_path(self.source), self.source)

    def test_position_updates_do_not_feed_back_into_seeking(self):
        with patch.object(self.window.player, "setPosition") as seek, \
             patch.object(self.window.review_player, "setPosition") as review_seek:
            self.window.on_duration(10000)
            self.window.on_position(1000)
            self.window.on_review_duration(10000)
            self.window.on_review_position(2000)
            seek.assert_not_called()
            review_seek.assert_not_called()
        slider = self.window.seek_slider
        signals = QSignalSpy(slider.valueChanged)
        slider.setSliderDown(True)
        for position in range(2000, 4000, 100):
            slider.setSliderPosition(position)
        self.assertEqual(len(signals), 0)
        slider.setSliderDown(False)
        self.assertEqual(len(signals), 1)

    def test_unchanged_review_source_does_not_leave_pending_seek(self):
        window = self.window
        window._review_observation = {"media_id": self.media}
        window._review_pending = 1234
        url = QUrl.fromLocalFile(str(self.source.resolve()))
        with patch.object(window.review_player, "source", return_value=url), \
             patch.object(window.review_player, "mediaStatus", return_value=QMediaPlayer.MediaStatus.LoadedMedia), \
             patch.object(window.review_player, "setPosition") as seek, \
             patch.object(window.review_player, "setSource") as source:
            window.reload_playback_sources()
            source.assert_not_called()
            seek.assert_called_once_with(1234)
            self.assertIsNone(window._review_pending)

    def test_playback_mode_does_not_replace_editor_vocal_audio(self):
        self.window._loaded_media = self.media
        self.window._vocal_only = True
        with patch.object(self.window, "load_playback") as load:
            self.window.reload_playback_sources()
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
