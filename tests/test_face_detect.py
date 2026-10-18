import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from src.vision.face_detect import detect_faces


class FakeTensor:
    """Tensor ตัวเล็กสำหรับ test เฉพาะ API cpu().tolist()."""

    def __init__(self, values):
        self.values = values

    def cpu(self):
        return self

    def tolist(self):
        return self.values


class FakeBoxes:
    def __init__(self, coordinates, confidences, class_ids):
        self.xyxy = FakeTensor(coordinates)
        self.conf = FakeTensor(confidences)
        self.cls = FakeTensor(class_ids)

    def __len__(self):
        return len(self.conf.values)


class FakeResult:
    def __init__(self, boxes, names=None):
        self.boxes = boxes
        self.names = names or {0: "face"}


class FaceDetectTests(unittest.TestCase):
    @patch("src.vision.face_detect._load_model")
    def test_converts_xyxy_to_clamped_xywh(self, load_model):
        model = MagicMock()
        model.predict.return_value = [
            FakeResult(
                FakeBoxes(
                    coordinates=[[-2.2, 10.4, 110.7, 90.1]],
                    confidences=[0.85],
                    class_ids=[0],
                )
            )
        ]
        load_model.return_value = model
        frame = np.zeros((100, 100, 3), dtype=np.uint8)

        detections = detect_faces(frame, model_path=Path("model.pt"))

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].box, (0, 10, 100, 81))
        self.assertAlmostEqual(detections[0].confidence, 0.85)

    @patch("src.vision.face_detect._load_model")
    def test_non_face_classes_are_skipped(self, load_model):
        model = MagicMock()
        model.predict.return_value = [
            FakeResult(
                FakeBoxes([[10, 10, 30, 30]], [0.9], [1]),
                names={0: "face", 1: "person"},
            )
        ]
        load_model.return_value = model
        frame = np.zeros((40, 40, 3), dtype=np.uint8)

        self.assertEqual(detect_faces(frame, model_path="model.pt"), [])

    @patch("src.vision.face_detect._load_model")
    def test_no_boxes_returns_empty_list(self, load_model):
        model = MagicMock()
        model.predict.return_value = [FakeResult(FakeBoxes([], [], []))]
        load_model.return_value = model
        frame = np.zeros((40, 40, 3), dtype=np.uint8)

        self.assertEqual(detect_faces(frame, model_path="model.pt"), [])

    @patch("src.vision.face_detect._load_model")
    def test_invalid_frame_is_rejected_before_loading_model(self, load_model):
        with self.assertRaises(TypeError):
            detect_faces(None)
        with self.assertRaises(ValueError):
            detect_faces(np.zeros((10, 10), dtype=np.uint8))
        with self.assertRaises(ValueError):
            detect_faces(np.zeros((10, 10, 3), dtype=np.float32))

        load_model.assert_not_called()

    @patch("src.vision.face_detect._load_model")
    def test_invalid_confidence_is_rejected_before_loading_model(self, load_model):
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        with self.assertRaises(ValueError):
            detect_faces(frame, confidence_threshold=1.1)
        with self.assertRaises(ValueError):
            detect_faces(frame, confidence_threshold=True)

        load_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
