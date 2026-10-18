"""ตรวจ association ด้วยกล่องสังเคราะห์ ไม่ต้องโหลด YOLO."""
import unittest

import numpy as np

from src.core.models import FaceDetection, FrameSample
from src.vision.character_tracking import calculate_iou, track_faces


class TrackingTests(unittest.TestCase):
    def samples(self, times=(0, 125, 250)):
        return [FrameSample(t, np.zeros((100, 200, 3), np.uint8)) for t in times]

    def test_two_people_keep_ids_even_when_detector_order_changes(self):
        detections = [[FaceDetection((10, 10, 30, 30)), FaceDetection((100, 10, 30, 30))],
                      [FaceDetection((102, 10, 30, 30)), FaceDetection((12, 10, 30, 30))],
                      [FaceDetection((14, 10, 30, 30)), FaceDetection((104, 10, 30, 30))]]
        tracks = track_faces(self.samples(), detections)
        self.assertEqual(len(tracks), 2)
        self.assertEqual([o.box[0] for o in tracks[0].observations], [10, 12, 14])
        self.assertEqual([o.box[0] for o in tracks[1].observations], [100, 102, 104])

    def test_one_detection_cannot_extend_two_tracks(self):
        face = FaceDetection((10, 10, 30, 30))
        tracks = track_faces(self.samples((0, 125)), [[face, face], [face]])
        self.assertEqual(sorted(len(t.observations) for t in tracks), [1, 2])

    def test_gap_and_scene_cut_start_new_ids(self):
        face = FaceDetection((10, 10, 30, 30))
        for samples in (self.samples((0, 2000)), self.samples((0, 125))):
            if samples[-1].timestamp_ms == 125:
                samples[-1].frame[:] = 255
            self.assertEqual(len(track_faces(samples, [[face], [face]])), 2)

    def test_empty_and_mismatched_inputs(self):
        self.assertEqual(track_faces(self.samples(), [[], [], []]), [])
        with self.assertRaises(ValueError):
            track_faces(self.samples(), [[]])

    def test_iou(self):
        self.assertEqual(calculate_iou((0, 0, 10, 10), (0, 0, 10, 10)), 1)
        self.assertAlmostEqual(calculate_iou((0, 0, 10, 10), (5, 0, 10, 10)), 1 / 3)
