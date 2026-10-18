"""Verify the shared FFmpeg boundary without processing a real video."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from src.audio.audio_extract import extract_audio
from src.core.control import AnalysisCancelled


class AudioExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.video = Path(self.temp.name) / "input.mp4"
        self.output = Path(self.temp.name) / "output.wav"
        self.video.touch()

    def test_verified_output_and_requested_sample_rate(self):
        def successful_run(command, **kwargs):
            self.assertEqual(command[command.index("-ar") + 1], "8000")
            self.assertEqual(command[command.index("-ac") + 1], "1")
            self.assertEqual(command[-1], str(self.output.resolve()))
            self.output.write_bytes(b"generated audio fixture")
            return SimpleNamespace(returncode=0, stderr="")
        with patch("src.audio.audio_extract.subprocess.run", side_effect=successful_run):
            self.assertEqual(extract_audio(self.video, self.output, 8000), self.output.resolve())

    def test_ffmpeg_failure_is_reported(self):
        with patch("src.audio.audio_extract.subprocess.run", return_value=SimpleNamespace(returncode=1, stderr="missing stream")):
            with self.assertRaisesRegex(RuntimeError, "missing stream"):
                extract_audio(self.video, self.output)

    def test_success_without_output_is_rejected(self):
        with patch("src.audio.audio_extract.subprocess.run", return_value=SimpleNamespace(returncode=0, stderr="")):
            with self.assertRaises(RuntimeError):
                extract_audio(self.video, self.output)

    def test_input_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            extract_audio(self.video, self.video)

    def test_cancel_terminates_owned_ffmpeg_process(self):
        process = MagicMock()
        process.poll.return_value = None
        process.communicate.return_value = ("", "")
        checks = iter((False, True))
        with patch("src.audio.audio_extract.subprocess.Popen", return_value=process):
            with self.assertRaises(AnalysisCancelled):
                extract_audio(self.video, self.output, cancel=lambda: next(checks))
        process.terminate.assert_called_once()
