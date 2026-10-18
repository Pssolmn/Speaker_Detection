"""ทดสอบ bounded sampling / checkpoint / cancellation ด้วยวิดีโอสังเคราะห์."""

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from src.audio.speaker_features import SpeakerEncoder
from src.core.control import AnalysisCancelled
from src.core.models import FaceDetection
from src.core.process import run_process
from src.pipeline.workspace_scan import ScanSettings, iter_video_windows, scan_visual
from src.workspace.store import WorkspaceStore
from src.pipeline.workspace_av import analyze_av


class FakeEncoder:
    model_key = "fake-ccip"
    threshold = .2

    def encode(self, frames):
        return np.tile([1., 0.], (len(frames), 1))

    def distances(self, query, references):
        return np.zeros(len(references))


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.video = self.root / "synthetic.avi"
        writer = cv2.VideoWriter(str(self.video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (200, 100))
        self.assertTrue(writer.isOpened())
        for index in range(40):
            frame = np.full((100, 200, 3), 100, np.uint8)
            cv2.rectangle(frame, (20, 20), (60, 60), (160, 160, 160), -1)
            writer.write(frame)
        writer.release()
        self.settings = ScanSettings(sample_fps=4, max_width=160, window_ms=1000, device="cpu")
        self.store = WorkspaceStore(self.root / "workspace", create=True)
        self.media = self.store.add_media(self.video)
        self.model = self.root / "fake.pt"
        self.model.write_bytes(b"fake model version")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def scan(self, **kwargs):
        return scan_visual(self.store, self.media, settings=self.settings, encoder=FakeEncoder(),
                           detector=lambda frame: [FaceDetection((16, 16, 32, 32), .9)],
                           model_path=self.model, **kwargs)

    def test_sampling_bounded_monotonic_and_resume(self):
        windows = list(iter_video_windows(self.video, self.settings))
        self.assertEqual(len(windows), 4)
        times = [sample.timestamp_ms for _, _, samples, _ in windows for sample in samples]
        self.assertEqual(times, sorted(set(times)))
        self.assertTrue(all(len(samples) <= 5 for _, _, samples, _ in windows))
        self.assertTrue(all(sample.frame.shape[1] == 160 for _, _, samples, _ in windows for sample in samples))
        resumed = list(iter_video_windows(self.video, self.settings, start_ms=2000))
        self.assertEqual(resumed[0][0], 2000)
        self.assertTrue(all(sample.timestamp_ms >= 2000 for _, _, samples, _ in resumed for sample in samples))
        self.assertEqual([sample.timestamp_ms for _, _, samples, _ in resumed for sample in samples],
                         [time for time in times if time >= 2000])

    def test_cancel_resume_completed_cache_and_manual_names(self):
        stop = [False]
        with self.assertRaises(AnalysisCancelled):
            self.scan(cancel=lambda: stop[0], progress=lambda *args: stop.__setitem__(0, True))
        run = self.store.rows("SELECT * FROM runs")[0]
        self.assertEqual((run["state"], run["cursor_ms"]), ("cancelled", 1000))
        profile = self.store.profiles()[0]["id"]
        self.store.rename(profile, "Ruby")
        self.store.confirm(profile)
        first_ids = {item["id"] for item in self.store.observations()}
        key = self.scan()
        self.assertEqual(self.store.rows("SELECT state FROM runs WHERE key=?", (key,))[0]["state"], "complete")
        self.assertTrue(first_ids <= {item["id"] for item in self.store.observations()})
        self.assertEqual(self.store.profile(profile)["name"], "Ruby")
        before = len(self.store.observations())
        with patch("src.pipeline.workspace_scan.iter_video_windows", side_effect=AssertionError("cached")):
            self.scan()
        self.assertEqual(len(self.store.observations()), before)

    def test_invalid_sampling_settings(self):
        for kwargs in ({"sample_fps": 0}, {"sample_fps": float("nan")}, {"max_width": 0},
                       {"window_ms": 0}, {"device": "wrong"}):
            with self.assertRaises(ValueError):
                ScanSettings(**kwargs)

    def voice_turn(self, start=1000, end=2000):
        run = self.store.begin_run(self.media, "voice", {"test": True})
        self.store.put_observation(identifier="speech", media_id=self.media, run_key=run["key"], kind="voice",
                                   start_ms=start, end_ms=end, model_key="test", features=[1., 0.])
        self.store.auto_assign("speech", new=True)
        self.store.checkpoint(run["key"], 4000, "complete")

    def test_new_scan_only_detects_near_speech_after_audio_is_complete(self):
        self.voice_turn()
        frames = []
        scan_visual(self.store, self.media, settings=self.settings, encoder=FakeEncoder(),
                    detector=lambda frame: frames.append(frame) or [FaceDetection((16, 16, 32, 32), .9)],
                    model_path=self.model)
        self.assertLess(len(frames), 10)
        self.assertGreater(len(frames), 0)
        visuals = self.store.observations(kind="visual")
        self.assertTrue(all(item["start_ms"] >= 750 and item["end_ms"] <= 2500 for item in visuals))
        self.assertTrue(all(item["evidence"]["speech_focused"] for item in visuals))

    def test_existing_visual_run_is_preserved_when_audio_is_added_later(self):
        key = self.scan()
        before = {item["id"] for item in self.store.observations(kind="visual")}
        self.voice_turn()
        self.assertEqual(self.scan(), key)
        self.assertEqual({item["id"] for item in self.store.observations(kind="visual")}, before)

    def test_av_enrichment_keeps_manual_groups_and_resumes_per_window(self):
        self.scan()
        self.voice_turn(0, 4000)
        profile = self.store.profiles("visual")[0]["id"]
        self.store.rename(profile, "Ruby")
        self.store.confirm(profile)
        original = self.store.rows("SELECT * FROM memberships")
        stop = [False]
        with self.assertRaises(AnalysisCancelled):
            analyze_av(self.store, self.media, cancel=lambda: stop[0], progress=lambda *_: stop.__setitem__(0, True))
        count = sum("mouth_activity" in item["evidence"] for item in self.store.observations(kind="visual"))
        self.assertEqual(count, 1)
        self.assertEqual(analyze_av(self.store, self.media), 3)
        self.assertEqual(self.store.rows("SELECT * FROM memberships"), original)
        self.assertEqual(self.store.profile(profile)["name"], "Ruby")
        with patch("src.pipeline.workspace_av.iter_video_windows", side_effect=AssertionError("must reuse cache")):
            self.assertEqual(analyze_av(self.store, self.media), 0)

    def test_thumbnails_are_bounded_per_profile_across_episodes(self):
        self.scan()
        second = self.root / "second.avi"
        writer = cv2.VideoWriter(str(second), cv2.VideoWriter_fourcc(*"MJPG"), 10, (200, 100))
        for _ in range(50):
            writer.write(np.full((100, 200, 3), 120, np.uint8))
        writer.release()
        self.media = self.store.add_media(second)
        self.scan()
        self.assertGreater(len(self.store.observations(kind="visual")), 4)
        self.assertLessEqual(len(list((self.store.root / "evidence").glob("*.jpg"))), 4)
        self.assertTrue(all(max(cv2.imread(str(path)).shape[:2]) <= 256 for path in (self.store.root / "evidence").glob("*.jpg")))

    def test_subprocess_failure_and_cancellation(self):
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            run_process([sys.executable, "-c", "raise ValueError('test failure')"], self.root / "failure.log")
        with self.assertRaises(AnalysisCancelled):
            run_process([sys.executable, "-c", "import time; time.sleep(30)"], self.root / "cancel.log", lambda: True)

    def test_overlapping_and_short_audio_do_not_create_identity(self):
        encoder = SpeakerEncoder.__new__(SpeakerEncoder)
        encoder.sample_rate = 16000
        turns = [SimpleNamespace(start=0, end=2, speaker=0), SimpleNamespace(start=1, end=3, speaker=1),
                 SimpleNamespace(start=4, end=4.5, speaker=0)]
        encoder.diarizer = SimpleNamespace(process=lambda audio, callback: SimpleNamespace(sort_by_start_time=lambda: turns))
        encoder.extractor = SimpleNamespace(create_stream=lambda: self.fail("unsafe identity extraction"))
        results = encoder.analyze(np.zeros(80000, np.float32))
        self.assertEqual([item["overlap"] for item in results], [True, True, False])
        self.assertTrue(all(item["features"] is None for item in results))


if __name__ == "__main__":
    unittest.main()
