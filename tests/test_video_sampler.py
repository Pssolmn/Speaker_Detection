import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from src.core.models import SubtitleSegment
from src.vision.video_sampler import sample_segment_frames, sample_mouth_frames
from src.core.control import AnalysisCancelled


class VideoSamplerTests(unittest.TestCase):
    @patch("src.vision.video_sampler.sample_segment_frames")
    def test_mouth_samples_are_bounded_to_one_window(self, sampler):
        sample_mouth_frames("x", SubtitleSegment(1, 1000, 50000, "Hi"))
        args = sampler.call_args.args
        self.assertEqual((args[1].start_ms, args[1].end_ms, args[2]), (1000, 11000, 80))

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_cancel_between_reads_releases_capture(self, video_capture):
        capture = self.make_capture(np.zeros((20, 20, 3), np.uint8))
        video_capture.return_value = capture
        checks = iter((False, False, True))
        with self.assertRaises(AnalysisCancelled):
            sample_segment_frames("x", SubtitleSegment(1, 0, 1000, "Hi"), cancel=lambda: next(checks))
        self.assertEqual(capture.read.call_count, 1)
        capture.release.assert_called_once()

    @staticmethod
    def make_capture(frame):
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.return_value = 10.0
        capture.set.return_value = True
        capture.read.return_value = (True, frame)
        return capture

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_samples_are_bounded_and_resized(self, video_capture):
        frame = np.zeros((480, 1280, 3), dtype=np.uint8)
        capture = self.make_capture(frame)
        video_capture.return_value = capture

        segment = SubtitleSegment(1, 1000, 2000, "Hello")
        samples = sample_segment_frames(
            "movie.mp4", segment, max_frames=3, max_width=640
        )

        self.assertEqual(len(samples), 3)
        self.assertTrue(all(sample.frame.shape[1] <= 640 for sample in samples))
        self.assertEqual(samples[0].frame.shape[:2], (240, 640))
        self.assertEqual(capture.set.call_count, 3)
        capture.release.assert_called_once()

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_invalid_limits_are_rejected_before_opening_video(self, video_capture):
        segment = SubtitleSegment(1, 1000, 2000, "Hello")

        with self.assertRaises(ValueError):
            sample_segment_frames("movie.mp4", segment, max_frames=0)
        with self.assertRaises(ValueError):
            sample_segment_frames("movie.mp4", segment, max_width=-1)

        video_capture.assert_not_called()

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_negative_start_is_rejected(self, video_capture):
        # model ตรวจตั้งแต่สร้างแล้ว; sampler ยังต้องกัน object ที่ถูกแก้ภายหลังด้วย
        segment = SubtitleSegment(1, 0, 2000, "Hello")
        segment.start_ms = -100

        with self.assertRaises(ValueError):
            sample_segment_frames("movie.mp4", segment)

        video_capture.assert_not_called()

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_unreadable_target_is_skipped_and_capture_is_released(self, video_capture):
        capture = self.make_capture(np.zeros((20, 20, 3), dtype=np.uint8))
        capture.read.return_value = (False, None)
        video_capture.return_value = capture

        segment = SubtitleSegment(1, 1000, 2000, "Hello")
        samples = sample_segment_frames("movie.mp4", segment, max_frames=2)

        self.assertEqual(samples, [])
        capture.release.assert_called_once()

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_targets_exclude_segment_end(self, video_capture):
        capture = self.make_capture(np.zeros((20, 20, 3), dtype=np.uint8))
        video_capture.return_value = capture

        samples = sample_segment_frames(
            "movie.mp4", SubtitleSegment(1, 1000, 2000, "Hello"),
            max_frames=3,
        )

        self.assertEqual([s.timestamp_ms for s in samples], [1166, 1500, 1833])
        self.assertEqual(
            [call.args for call in capture.set.call_args_list],
            [
                (cv2.CAP_PROP_POS_FRAMES, 11),
                (cv2.CAP_PROP_POS_FRAMES, 15),
                (cv2.CAP_PROP_POS_FRAMES, 18),
            ],
        )
        capture.release.assert_called_once()

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_short_segment_does_not_round_into_future(self, video_capture):
        capture = self.make_capture(np.zeros((20, 20, 3), dtype=np.uint8))
        video_capture.return_value = capture

        samples = sample_segment_frames(
            "movie.mp4", SubtitleSegment(1, 960, 990, "Hi"),
            max_frames=5,
        )

        # ทุกเวลาอยู่ในเฟรม 9 จึงอ่านแค่ครั้งเดียว
        self.assertEqual(len(samples), 1)
        capture.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 9)
        capture.read.assert_called_once()
        capture.release.assert_called_once()

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_failed_seek_raises_before_reading(self, video_capture):
        for fps in (10.0, 0.0):
            with self.subTest(fps=fps):
                capture = self.make_capture(np.zeros((20, 20, 3), dtype=np.uint8))
                capture.get.return_value = fps
                capture.set.return_value = False
                video_capture.return_value = capture

                with self.assertRaises(OSError):
                    sample_segment_frames(
                        "movie.mp4", SubtitleSegment(1, 1000, 2000, "Hello")
                    )

                capture.read.assert_not_called()
                capture.release.assert_called_once()

    @patch("src.vision.video_sampler.cv2.VideoCapture")
    def test_invalid_fps_falls_back_to_time(self, video_capture):
        for fps in (0.0, float("nan"), float("inf")):
            with self.subTest(fps=fps):
                capture = self.make_capture(np.zeros((20, 20, 3), dtype=np.uint8))
                capture.get.return_value = fps
                video_capture.return_value = capture

                samples = sample_segment_frames(
                    "movie.mp4", SubtitleSegment(1, 1000, 1001, "Hi"),
                    max_frames=5,
                )

                # ช่วงยาว 1 ms จึงไม่ seek เวลาเดิมซ้ำ 5 ครั้ง
                self.assertEqual(len(samples), 1)
                capture.set.assert_called_once_with(cv2.CAP_PROP_POS_MSEC, 1000)
                capture.read.assert_called_once()
                capture.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
