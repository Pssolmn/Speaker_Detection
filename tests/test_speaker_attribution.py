import unittest
from unittest.mock import patch

import numpy as np

from src.core.control import AnalysisCancelled
from src.core.models import Candidate, FaceDetection, FrameSample, SubtitleSegment
from src.pipeline.speaker_attribution import attribute_segment


class FakeIdentifier:
    def identify_portrait_with_reason(self, image, bbox=None):
        return [Candidate("Aqua", 0.9)], None


class AttributionTests(unittest.TestCase):
    @patch("src.pipeline.speaker_attribution.detect_faces", return_value=[])
    @patch("src.pipeline.speaker_attribution.sample_mouth_frames")
    def test_empty_detection_is_default_but_read_error_is_error(self, sampler, detector):
        segment = SubtitleSegment(1, 0, 1000, "Hi")
        sampler.return_value = [FrameSample(100, np.zeros((64, 64, 3), np.uint8))]
        self.assertEqual(attribute_segment("x", segment, FakeIdentifier()).status, "DEFAULT")
        sampler.return_value = []
        self.assertEqual(attribute_segment("x", segment, FakeIdentifier()).status, "ERROR")

    @patch("src.pipeline.speaker_attribution.sample_mouth_frames")
    def test_no_cue_does_not_run_video(self, sampler):
        segment = SubtitleSegment(1, 0, 1000, "")
        self.assertEqual(attribute_segment("x", segment, FakeIdentifier(), []).status, "NO_SPEECH")
        self.assertEqual(attribute_segment("x", segment, FakeIdentifier(), None).status, "NO_CUE")
        sampler.assert_not_called()

    @patch("src.pipeline.speaker_attribution.detect_faces", return_value=[FaceDetection((0, 0, 64, 64))])
    @patch("src.pipeline.speaker_attribution.sample_mouth_frames")
    def test_dialogue_with_silent_audio_still_checks_faces(self, sampler, detector):
        sampler.return_value = [FrameSample(i * 125, np.zeros((64, 64, 3), np.uint8)) for i in range(4)]
        result = attribute_segment("x", SubtitleSegment(1, 0, 1000, "Hi"), FakeIdentifier(), [])
        self.assertEqual(result.status, "UNKNOWN")
        self.assertIn("dialogue_without_detected_audio_energy", result.evidence["warnings"])
        self.assertEqual(len(result.evidence["tracks"]), 1)

    def test_cancellation_propagates(self):
        with self.assertRaises(AnalysisCancelled):
            attribute_segment("x", SubtitleSegment(1, 0, 1000, "Hi"), FakeIdentifier(), cancel=lambda: True)

    @patch("src.pipeline.speaker_attribution.sample_mouth_frames")
    def test_explicit_music_and_effects_are_not_dialogue(self, sampler):
        for text in ("[Door slams]", "♪ a song ♪"):
            result = attribute_segment("x", SubtitleSegment(1, 0, 1000, text), FakeIdentifier(), [(0, 1000)])
            self.assertEqual(result.status, "NON_DIALOGUE")
        sampler.assert_not_called()

    @patch("src.pipeline.speaker_attribution.detect_faces", return_value=[])
    @patch("src.pipeline.speaker_attribution.sample_mouth_frames")
    def test_long_segment_records_every_window(self, sampler, detector):
        sampler.side_effect = lambda video, segment, *args, **kwargs: [
            FrameSample(segment.start_ms + 1, np.zeros((64, 64, 3), np.uint8))]
        result = attribute_segment("x", SubtitleSegment(1, 1000, 23000, "Hi"), FakeIdentifier())
        self.assertEqual([(w["start_ms"], w["end_ms"]) for w in result.evidence["windows"]],
                         [(1000, 11000), (11000, 21000), (21000, 23000)])
