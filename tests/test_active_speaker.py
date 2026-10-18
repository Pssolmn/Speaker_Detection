import unittest

import numpy as np

from src.core.models import FaceTrack, FrameSample, TrackObservation
from src.vision.active_speaker import score_active_speakers, mouth_motion_series


class ActiveSpeakerTests(unittest.TestCase):
    def samples(self, moving=False):
        samples = []
        for index in range(4):
            frame = np.full((64, 64, 3), 100, np.uint8)
            if moving and index % 2:
                frame[36:56, 16:48] = 240
            samples.append(FrameSample(index * 125, frame))
        return samples

    def track(self):
        return FaceTrack(1, [TrackObservation(i, (0, 0, 64, 64)) for i in range(4)])

    def test_static_is_zero_and_moving_mouth_is_higher(self):
        static = score_active_speakers(self.samples(), [self.track()], [(0, 1000)])[1]
        moving = score_active_speakers(self.samples(True), [self.track()], [(0, 1000)])[1]
        self.assertEqual(static, 0)
        self.assertGreater(moving, 0.5)

    def test_unknown_audio_and_insufficient_pairs_are_unknown(self):
        self.assertIsNone(score_active_speakers(self.samples(), [self.track()], None)[1])
        track = FaceTrack(2, [TrackObservation(0, (0, 0, 64, 64))])
        self.assertIsNone(score_active_speakers(self.samples(), [track], [(0, 1000)])[2])

    def test_uniform_brightness_change_is_not_mouth_motion(self):
        samples = self.samples()
        samples[1].frame[:] = 150
        samples[3].frame[:] = 150
        self.assertAlmostEqual(score_active_speakers(samples, [self.track()], [(0, 1000)])[1], 0)

    def test_localized_motion_detects_small_anime_mouth_without_whole_face_motion(self):
        samples = self.samples()
        for index, sample in enumerate(samples):
            if index % 2:
                sample.frame[44:48, 28:32] = 240
        localized = mouth_motion_series(samples, self.track(), localized=True)
        self.assertTrue(all(pair[2] > .3 for pair in localized))
        self.assertTrue(all(pair[2] == 0 for pair in mouth_motion_series(self.samples(), self.track(), localized=True)))

    def test_localized_metric_does_not_call_uniform_flash_speech(self):
        samples = self.samples()
        samples[1].frame[:] = 180
        samples[3].frame[:] = 180
        self.assertTrue(all(pair[2] == 0 for pair in mouth_motion_series(samples, self.track(), localized=True)))
